"""SME review loop (SPEC 07.9; SCREENS 3.39; ARCHITECTURE 9.2 run-reviews and decisions).

1. A person selects episodes of a completed run; the RL Gym builds one immutable `rlgym.sme-review-package.v1` and
   sends it to ADI Forge (`POST /api/v1/projects/{project_id}/run-reviews`) through the outbox. SMEs work only in ADI
   Forge.
2. ADI Forge posts the decisions back (`POST /sme-review-batches/{id}/decisions`, ADI Forge key). Each decision is final.
3. Follow-ups by owner (D20): agent failure → nothing; task needs correction → wait for the corrected revision in the
   project's re-export, then a validation run; grader is wrong → the RL Gym's own fix version (the episode added as a
   known case), then an explicit re-score if someone wants one; rubric needs correction → one Studio `evaluator_defect`
   item per criterion; environment is wrong → one `environment_defect` item per environment version.
4. The automated score never changes. The reviewed score leaves out episodes the SMEs found invalid.
"""

import datetime as dt
import statistics
import uuid

from psycopg.types.json import Jsonb

from anvil.rlgym.catalog import evaluators, inbox
from anvil.rlgym.common import GymError, audit, emit, require, sha
from anvil.rlgym.results import episodes as episode_view
from anvil.rlgym.scoring import service as scoring

DECISIONS = {
    "agent_failure": "Agent failure confirmed",
    "task_correction": "Task needs correction",
    "rubric_correction": "Rubric needs correction",
    "grader_wrong": "Grader is wrong",
    "environment_wrong": "Environment is wrong",
}
WRITERS = ("admin", "rl_engineer")


def _writer(actor):
    actor.require_person()
    require(actor.profile in WRITERS, "FORBIDDEN", "Viewers cannot change SME review")


def _run(c, ws, run_id):
    run = c.execute(
        "SELECT * FROM runs.runs WHERE workspace_id=%s AND id=%s", (ws, run_id)
    ).fetchone()
    if not run:
        raise GymError("NOT_FOUND", "Run not found")
    return run


def _batch(c, ws, batch_id):
    b = c.execute(
        "SELECT * FROM results.sme_review_batches WHERE workspace_id=%s AND id=%s", (ws, batch_id)
    ).fetchone()
    if not b:
        raise GymError("NOT_FOUND", "SME review batch not found")
    return b


# --- send ------------------------------------------------------------------------------------------------------------


def create_batch(c, ws, actor, run_id, body):
    _writer(actor)
    run = _run(c, ws, run_id)
    require(run["state"] == "completed", "CONFLICT", "SME review is for completed runs")
    ids = sorted(set(body.get("episode_ids") or []))
    require(ids, "VALIDATION_FAILED", "Choose at least one episode", field="episode_ids")
    rows = c.execute(
        """SELECT e.*, x.sealed_sha256 FROM runs.episodes e JOIN runs.sealed_evidence x ON x.episode_id=e.id
           WHERE e.run_id=%s AND e.id = ANY(%s) AND e.kind='case'""",
        (run_id, ids),
    ).fetchall()
    require(
        len(rows) == len(ids),
        "VALIDATION_FAILED",
        "Only sealed benchmark episodes of this run can be reviewed",
        missing=sorted(set(ids) - {r["id"] for r in rows}),
    )
    manifest = c.execute(
        "SELECT manifest, manifest_sha256 FROM runs.run_manifests WHERE run_id=%s", (run_id,)
    ).fetchone()
    m = manifest["manifest"]
    batch_id = (
        "smr-"
        + f"{c.execute('SELECT nextval(%s) n', ('results.batch_number',)).fetchone()['n']:04d}"
    )
    latest = scoring.latest_pass(c, run_id)
    tasks = {}
    items = []
    for e in rows:
        v = episode_view.view(c, ws, actor, e["id"])
        item_id = f"smi-{uuid.uuid4().hex[:8]}"
        items.append((item_id, e))
        task = next(t for t in m["tasks"] if t["task_id"] == e["task_id"])
        tasks.setdefault(
            e["task_id"],
            {
                "task_id": e["task_id"],
                "revision": e["task_revision"],
                "package_sha256": task["package_sha256"],
                "episodes": [],
            },
        )
        tasks[e["task_id"]]["episodes"].append(
            {
                "item_id": item_id,
                "episode_id": e["id"],
                "system": {
                    "id": e["system_id"],
                    "version": e["system_version"],
                    "name": v["model"],
                },
                "attempt": e["attempt"],
                "case_id": e["case_id"],
                "score": v["score"],
                "criteria": [
                    {
                        k: cr[k]
                        for k in (
                            "criterion_id",
                            "verdict",
                            "points",
                            "evaluator",
                            "detail",
                            "nodes",
                            "block_lines",
                        )
                        if k in cr
                    }
                    for cr in v["criteria"]
                ],
                "path": {
                    k: v["path"][k]
                    for k in (
                        "order",
                        "failed_node",
                        "failed_why",
                        "summary",
                        "reached",
                        "missing_for",
                    )
                },
                "timeline": [
                    {k: t[k] for k in ("step", "tool", "args", "status", "node")}
                    for t in v["timeline"]
                ],
                "final_output": v["output"]["final"],
                "evidence": {
                    "sealed_sha256": e["sealed_sha256"],
                    "manifest_sha256": manifest["manifest_sha256"],
                },
                "suspected_cause": e["likely_cause"],
                "suspected_cause_source": e["likely_cause_source"],
            }
        )
    package = {
        "schema": "rlgym.sme-review-package.v1",
        "batch_id": batch_id,
        "run_id": run_id,
        "project_id": run["project_id"],
        "template": m["template"],
        "scoring_pass": {"pass": latest["pass"], "reason": latest["reason"]},
        "rubric": [
            {
                k: ev.get(k)
                for k in (
                    "criterion_id",
                    "configuration_id",
                    "version",
                    "weight",
                    "is_gate",
                    "skill_group",
                )
            }
            for ev in latest["evaluator_versions"]
        ],
        "tasks": [tasks[k] for k in sorted(tasks)],
        "synthetic": True,
        "note": m["note"],
    }
    digest = sha(package)
    c.execute(
        """INSERT INTO results.sme_review_batches(id,workspace_id,project_id,run_id,template_id,template_version,state,batch_sha256,created_by)
           VALUES(%s,%s,%s,%s,%s,%s,'building',%s,%s)""",
        (
            batch_id,
            ws,
            run["project_id"],
            run_id,
            m["template"]["id"],
            m["template"]["version"],
            digest,
            actor.id,
        ),
    )
    for item_id, e in items:
        c.execute(
            """INSERT INTO results.sme_review_items(id,batch_id,workspace_id,episode_id,task_id,task_revision,suspected_cause)
               VALUES(%s,%s,%s,%s,%s,%s,%s)""",
            (item_id, batch_id, ws, e["id"], e["task_id"], e["task_revision"], e["likely_cause"]),
        )
    emit(
        c,
        ws,
        "forge.run_review",
        batch_id,
        {
            "_path": f"/api/v1/projects/{run['project_id']}/run-reviews",
            "_batch_id": batch_id,
            **package,
            "batch_sha256": digest,
        },
        destination="forge",
    )
    audit(
        c,
        ws,
        actor,
        "sme_batch.created",
        batch_id,
        details={"run_id": run_id, "items": len(items), "sha256": digest},
    )
    return batch_view(c, ws, batch_id)


def sent(c, ws, batch_id, result):
    """The dispatcher delivered the batch: ADI Forge answered {forge_batch_ref}."""
    row = c.execute(
        """UPDATE results.sme_review_batches SET state='sent', sent_at=now(), forge_batch_ref=%s
           WHERE workspace_id=%s AND id=%s AND state='building' RETURNING *""",
        ((result or {}).get("forge_batch_ref"), ws, batch_id),
    ).fetchone()
    if row:
        emit(
            c,
            ws,
            "sme_batch.sent",
            batch_id,
            {"batch_id": batch_id, "run_id": row["run_id"], "project_id": row["project_id"]},
        )


# --- decisions -------------------------------------------------------------------------------------------------------


def _inbox_for(c, ws, actor, kind, b, item, key, summary, extra):
    """One item per criterion (evaluator_defect) or environment version (environment_defect): reuse an open one."""
    if kind == "evaluator_defect":
        open_item = c.execute(
            """SELECT id FROM catalog.inbox_items WHERE workspace_id=%s AND kind='evaluator_defect' AND evaluator_configuration=%s
               AND state NOT IN ('declined','closed','released')""",
            (ws, key),
        ).fetchone()
    else:
        open_item = c.execute(
            """SELECT id FROM catalog.inbox_items WHERE workspace_id=%s AND kind='environment_defect' AND environment_version_id=%s
               AND state NOT IN ('declined','closed','released')""",
            (ws, key),
        ).fetchone()
    if open_item:
        return open_item["id"]
    row = inbox.create(
        c,
        ws,
        actor,
        {
            "kind": kind,
            "template_id": b["template_id"],
            "version": b["template_version"],
            "project_id": b["project_id"],
            "summary": summary,
            "evidence": {
                "batch_id": b["id"],
                "run_id": b["run_id"],
                "episode_id": item["episode_id"],
                "rationale": item["rationale"],
            },
            **extra,
        },
    )
    return row["id"]


MISSING = object()
VERDICTS = ("accept", "dispute_task", "dispute_rubric", "dispute_grader", "dispute_environment")


def review_verdict(raw):
    """Authoring's "Accept" / "Dispute grader" (any case, space or underscore) → accept / dispute_grader; None when
    absent; MISSING when it is something else."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        return MISSING
    v = "_".join(raw.strip().lower().replace("-", " ").split())
    return v if v in VERDICTS else MISSING


def receive_decisions(c, ws, actor, batch_id, body):
    require(
        body.get("schema") == "rlgym.sme-decisions.v1",
        "VALIDATION_FAILED",
        "schema must be rlgym.sme-decisions.v1",
    )
    b = _batch(c, ws, batch_id)
    require(
        b["state"] in ("sent", "in_review", "decided"),
        "CONFLICT",
        f"Batch {batch_id} is {b['state']}",
    )
    decisions = body.get("decisions") or []
    require(decisions, "VALIDATION_FAILED", "decisions are required", field="decisions")
    items = {
        i["id"]: i
        for i in c.execute(
            "SELECT * FROM results.sme_review_items WHERE batch_id=%s", (batch_id,)
        ).fetchall()
    }
    by_episode = {i["episode_id"]: i for i in items.values()}
    run = _run(c, ws, b["run_id"])
    manifest = c.execute(
        "SELECT manifest FROM runs.run_manifests WHERE run_id=%s", (b["run_id"],)
    ).fetchone()["manifest"]
    applied = []
    for d in decisions:
        item = items.get(d.get("item_id")) or by_episode.get(d.get("episode_id"))
        require(
            item,
            "VALIDATION_FAILED",
            "Unknown item in this batch",
            item=d.get("item_id") or d.get("episode_id"),
        )
        decision = d.get("decision")
        require(
            decision in DECISIONS,
            "VALIDATION_FAILED",
            f"decision must be one of {', '.join(DECISIONS)}",
            item=item["id"],
        )
        require(
            (d.get("rationale") or "").strip(),
            "VALIDATION_FAILED",
            "A rationale is required",
            item=item["id"],
        )
        require(
            (d.get("decided_by") or "").strip(),
            "VALIDATION_FAILED",
            "decided_by is required",
            item=item["id"],
        )
        if item["decision"]:
            require(
                item["decision"] == decision,
                "CONFLICT",
                "An SME decision is final",
                item=item["id"],
            )
            continue
        # E-007 (Authoring 7c12b835): what the SME reviewed, stored with the decision so publication can require an
        # accepted review of the same score pass and evidence. Optional; absent on older decisions.
        verdict = review_verdict(d.get("verdict"))
        require(
            verdict is not MISSING,
            "VALIDATION_FAILED",
            "verdict must be Accept or Dispute task|rubric|grader|environment",
            item=item["id"],
        )
        score_pass = d.get("score_pass")
        require(
            score_pass is None or (isinstance(score_pass, int) and score_pass >= 1),
            "VALIDATION_FAILED",
            "score_pass must be a pass number",
            item=item["id"],
        )
        evidence_sha = d.get("evidence_sha256")
        require(
            evidence_sha is None
            or (
                isinstance(evidence_sha, str)
                and len(evidence_sha) == 64
                and all(ch in "0123456789abcdef" for ch in evidence_sha)
            ),
            "VALIDATION_FAILED",
            "evidence_sha256 must be a SHA-256 hex digest",
            item=item["id"],
        )
        criterion = d.get("criterion_id")
        if decision in ("grader_wrong", "rubric_correction"):
            ev = next((x for x in manifest["evaluators"] if x["criterion_id"] == criterion), None)
            require(
                ev,
                "VALIDATION_FAILED",
                "Name the criterion (criterion_id) for a grader or rubric decision",
                item=item["id"],
            )
        c.execute(
            """UPDATE results.sme_review_items SET decision=%s, rationale=%s, decided_by=%s, decided_at=now(), criterion_id=%s,
                 evidence_refs=%s, excluded_from_reviewed=%s, review_verdict=%s, score_pass=%s, evidence_sha256=%s
               WHERE id=%s""",
            (
                decision,
                d["rationale"].strip(),
                d["decided_by"].strip(),
                criterion,
                Jsonb(d.get("evidence_refs") or []),
                decision != "agent_failure",
                verdict,
                score_pass,
                evidence_sha,
                item["id"],
            ),
        )
        item = {
            **item,
            "decision": decision,
            "rationale": d["rationale"].strip(),
            "criterion_id": criterion,
        }
        follow, inbox_id = {}, None
        if decision == "agent_failure":
            follow = {"kind": "none", "text": "Agent failure confirmed; nothing changes."}
        elif decision == "task_correction":
            follow = {
                "kind": "awaiting_correction",
                "text": "Waiting for the corrected revision in the project's next re-export.",
            }
        elif decision == "grader_wrong":
            follow = {
                "kind": "grader_fix",
                "criterion_id": criterion,
                "text": "Fixed in the RL Gym, no Studio inbox item: create a fix version of the evaluator with this episode as a known case.",
            }
        elif decision == "rubric_correction":
            ev = next(x for x in manifest["evaluators"] if x["criterion_id"] == criterion)
            inbox_id = _inbox_for(
                c,
                ws,
                actor,
                "evaluator_defect",
                b,
                item,
                ev["configuration_id"],
                f"SME review {batch_id}: the S7 criterion {criterion} needs correction"
                + (f" (verifier block {d['block_id']})" if d.get("block_id") else ""),
                {
                    "criterion_text_must_change": True,
                    "evaluator_configuration": ev["configuration_id"],
                    # A wrong block is the template's (Studio); the code that runs it would be a fix version.
                    **({"block_id": d["block_id"]} if d.get("block_id") else {}),
                },
            )
            follow = {
                "kind": "studio_item",
                "text": f"Sent to Studio inbox · evaluator defect (criterion definition) · {inbox_id}",
            }
        elif decision == "environment_wrong":
            vid = manifest["environment"]["version_id"]
            inbox_id = _inbox_for(
                c,
                ws,
                actor,
                "environment_defect",
                b,
                item,
                vid,
                f"SME review {batch_id}: {vid} behaves wrongly",
                {"environment_version": vid},
            )
            follow = {
                "kind": "studio_item",
                "text": f"Sent to Studio inbox · environment defect · {inbox_id}",
            }
        c.execute(
            "UPDATE results.sme_review_items SET follow_up=%s, inbox_item_id=%s WHERE id=%s",
            (Jsonb(follow), inbox_id, item["id"]),
        )
        applied.append(item["id"])
    _reviewed_scores(c, ws, b, run)
    left = c.execute(
        "SELECT count(*) n FROM results.sme_review_items WHERE batch_id=%s AND decision IS NULL",
        (batch_id,),
    ).fetchone()["n"]
    state = "decided" if not left else "in_review"
    if b["state"] != state and b["state"] in ("sent", "in_review"):
        c.execute(
            "UPDATE results.sme_review_batches SET state=%s, decided_at=CASE WHEN %s='decided' THEN now() ELSE decided_at END WHERE id=%s",
            (state, state, batch_id),
        )
        if state == "decided":
            emit(
                c,
                ws,
                "sme_batch.decided",
                batch_id,
                {"batch_id": batch_id, "run_id": b["run_id"], "project_id": b["project_id"]},
            )
    audit(c, ws, actor, "sme_batch.decisions", batch_id, details={"applied": applied})
    corrections_arrived(c, ws, batch_id)
    return batch_view(c, ws, batch_id)


def _reviewed_scores(c, ws, b, run):
    latest = scoring.latest_pass(c, run["id"])
    rows = c.execute(
        """SELECT e.id, e.system_id, e.system_version, s.score FROM runs.episodes e
           JOIN scoring.episode_scores s ON s.episode_id=e.id AND s.pass_id=%s WHERE e.run_id=%s AND e.kind='case'""",
        (latest["id"], run["id"]),
    ).fetchall()
    excluded = {
        r["episode_id"]
        for r in c.execute(
            """SELECT i.episode_id FROM results.sme_review_items i JOIN results.sme_review_batches b ON b.id=i.batch_id
               WHERE b.run_id=%s AND i.excluded_from_reviewed""",
            (run["id"],),
        ).fetchall()
    }
    c.execute(
        "DELETE FROM results.reviewed_scores WHERE run_id=%s AND batch_id=%s", (run["id"], b["id"])
    )
    systems = {}
    for r in rows:
        systems.setdefault((r["system_id"], r["system_version"]), []).append(r)
    for (sid, ver), rs in systems.items():
        auto = [float(r["score"]) for r in rs if r["score"] is not None]
        kept = [float(r["score"]) for r in rs if r["score"] is not None and r["id"] not in excluded]
        c.execute(
            """INSERT INTO results.reviewed_scores(run_id,workspace_id,system_id,system_version,batch_id,pass_id,automated,reviewed,excluded)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                run["id"],
                ws,
                sid,
                ver,
                b["id"],
                latest["id"],
                round(statistics.fmean(auto), 2) if auto else None,
                round(statistics.fmean(kept), 2) if kept else None,
                sum(1 for r in rs if r["id"] in excluded),
            ),
        )


# --- follow-ups ------------------------------------------------------------------------------------------------------


def corrections_arrived(c, ws, batch_id):
    """Called after a re-export: link corrected revisions; all task items corrected → corrections_imported."""
    b = _batch(c, ws, batch_id)
    task_items = c.execute(
        "SELECT * FROM results.sme_review_items WHERE batch_id=%s AND decision='task_correction'",
        (batch_id,),
    ).fetchall()
    if not task_items:
        return
    done = 0
    for item in task_items:
        corrected = _corrected(c, ws, b, item)
        if corrected:
            done += 1
            if (item["follow_up"] or {}).get("kind") == "awaiting_correction":
                c.execute(
                    "UPDATE results.sme_review_items SET follow_up=%s WHERE id=%s",
                    (
                        Jsonb(
                            {
                                "kind": "validation_ready",
                                "corrected_task_import_id": str(corrected["id"]),
                                "text": f"{item['task_id']} r{corrected['revision']} arrived: start a validation run.",
                            }
                        ),
                        item["id"],
                    ),
                )
    if done == len(task_items) and b["state"] == "decided":
        c.execute(
            "UPDATE results.sme_review_batches SET state='corrections_imported' WHERE id=%s",
            (batch_id,),
        )
        emit(
            c,
            ws,
            "sme_batch.corrections_imported",
            batch_id,
            {"batch_id": batch_id, "run_id": b["run_id"]},
        )


def _corrected(c, ws, b, item):
    return c.execute(
        """SELECT * FROM projects.task_imports WHERE workspace_id=%s AND project_id=%s AND task_id=%s AND revision>%s
           AND state='ready' AND (sme_batch_id=%s OR sme_batch_id IS NULL) ORDER BY revision DESC LIMIT 1""",
        (ws, b["project_id"], item["task_id"], item["task_revision"], b["id"]),
    ).fetchone()


def on_export(c, ws, project_id, batch_ids):
    for batch_id in sorted(set(filter(None, batch_ids))):
        if c.execute(
            "SELECT 1 FROM results.sme_review_batches WHERE workspace_id=%s AND id=%s AND project_id=%s",
            (ws, batch_id, project_id),
        ).fetchone():
            corrections_arrived(c, ws, batch_id)


def grader_fix(c, ws, actor, item_id, body):
    """The RL Gym's own fix for 'grader is wrong': a new configuration version with the episode as a known case."""
    _writer(actor)
    item = c.execute(
        "SELECT * FROM results.sme_review_items WHERE workspace_id=%s AND id=%s", (ws, item_id)
    ).fetchone()
    require(item, "NOT_FOUND", "Item not found")
    require(
        item["decision"] == "grader_wrong",
        "CONFLICT",
        "A fix version answers a 'grader is wrong' decision",
    )
    require(not item["fix_version"], "CONFLICT", "A fix version was already made for this item")
    b = _batch(c, ws, item["batch_id"])
    latest = scoring.latest_pass(c, b["run_id"])
    ev = next(x for x in latest["evaluator_versions"] if x["criterion_id"] == item["criterion_id"])
    e = c.execute(
        "SELECT e.*, x.bundle_ref, x.sealed_sha256, m.manifest FROM runs.episodes e JOIN runs.sealed_evidence x ON x.episode_id=e.id "
        "JOIN runs.run_manifests m ON m.run_id=e.run_id WHERE e.id=%s",
        (item["episode_id"],),
    ).fetchone()
    bundle = scoring.read_sealed(e)
    ref = c.execute(
        "SELECT reference FROM scoring.case_references WHERE workspace_id=%s AND environment_version_id=%s AND case_id=%s",
        (ws, e["manifest"]["environment"]["version_id"], e["case_id"]),
    ).fetchone()
    expect = body.get("expect", "pass")
    require(
        expect in ("pass", "partial", "fail", "blocked"),
        "VALIDATION_FAILED",
        "expect is a verdict",
        field="expect",
    )
    out = evaluators.create_fix_version(
        c,
        ws,
        actor,
        ev["configuration_id"],
        {
            "fix_of": ev["version"],
            "reason": (body.get("reason") or "").strip()
            or f"SME review {b['id']}: {item['rationale']}",
            "config": body.get("config"),
            "source": f"sme:{b['id']}:{item['id']}",
            "known_cases": {
                f"sme_{item['episode_id']}": {
                    "case_id": e["case_id"],
                    "evidence": {
                        "tool_events": bundle.get("tool_events"),
                        "final_output": bundle.get("final_output"),
                    },
                    "reference": ref["reference"],
                    "expect": expect,
                }
            },
        },
    )
    cfg = out["configuration"]
    c.execute(
        "UPDATE results.sme_review_items SET fix_configuration=%s, fix_version=%s, follow_up=%s WHERE id=%s",
        (
            cfg["id"],
            cfg["version"],
            Jsonb(
                {
                    "kind": "grader_fix",
                    "criterion_id": item["criterion_id"],
                    "text": f"Fixed in the RL Gym, no Studio inbox item: {cfg['id']} v{cfg['version']} · {cfg['state']}",
                }
            ),
            item_id,
        ),
    )
    if cfg["state"] == "qualified":
        emit(
            c,
            ws,
            "sme_item.fix_qualified",
            item_id,
            {
                "id": cfg["id"],
                "version": cfg["version"],
                "run_id": b["run_id"],
                "project_id": b["project_id"],
            },
        )
    return {
        "configuration": {k: cfg[k] for k in ("id", "version", "state")},
        "known_case_test": out["known_case_test"],
    }


def validation_run(c, ws, actor, item_id):
    """Re-run only the corrected task on the original cases, systems and attempts, with the original environment and
    evaluator versions, so before and after compare per criterion. The original run never changes."""
    from anvil.rlgym.runs import service as runs

    _writer(actor)
    item = c.execute(
        "SELECT * FROM results.sme_review_items WHERE workspace_id=%s AND id=%s", (ws, item_id)
    ).fetchone()
    require(item, "NOT_FOUND", "Item not found")
    require(
        item["decision"] == "task_correction",
        "CONFLICT",
        "A validation run follows a 'task needs correction' decision",
    )
    b = _batch(c, ws, item["batch_id"])
    corrected = _corrected(c, ws, b, item)
    require(corrected, "CONFLICT", "The corrected revision has not arrived in a re-export yet")
    original = c.execute("SELECT * FROM runs.runs WHERE id=%s", (b["run_id"],)).fetchone()
    m = c.execute(
        "SELECT manifest FROM runs.run_manifests WHERE run_id=%s", (b["run_id"],)
    ).fetchone()["manifest"]
    env = c.execute(
        "SELECT state FROM catalog.environment_versions WHERE id=%s",
        (m["environment"]["version_id"],),
    ).fetchone()
    reasons = []
    if not env or env["state"] != "qualified":
        reasons.append(
            {
                "key": "environment",
                "label": "Environments qualified",
                "detail": f"{m['environment']['version_id']} is {env and env['state']}",
            }
        )
    latest = scoring.latest_pass(c, b["run_id"])
    for ev in latest["evaluator_versions"]:
        st = c.execute(
            "SELECT state FROM catalog.evaluator_configurations WHERE workspace_id=%s AND id=%s AND version=%s",
            (ws, ev["configuration_id"], ev["version"]),
        ).fetchone()
        if not st or st["state"] == "revoked":
            reasons.append(
                {
                    "key": "evaluators",
                    "label": "Evaluators qualified",
                    "detail": f"{ev['configuration_id']} v{ev['version']} is revoked",
                }
            )
    if reasons:
        raise GymError("ADMISSION_REFUSED", "The validation run cannot start", {"items": reasons})
    originals = c.execute(
        "SELECT * FROM runs.episodes WHERE run_id=%s AND task_id=%s AND kind='case'",
        (b["run_id"], item["task_id"]),
    ).fetchall()
    run_id = runs._next_id(c)
    manifest = {
        **m,
        "run_id": run_id,
        "purpose": "validation",
        "validation_of": {
            "run_id": b["run_id"],
            "batch_id": b["id"],
            "item_id": item_id,
            "task_id": item["task_id"],
            "from_revision": item["task_revision"],
            "to_revision": corrected["revision"],
        },
        "tasks": [
            {
                "task_import_id": str(corrected["id"]),
                "task_id": corrected["task_id"],
                "revision": corrected["revision"],
                "package_sha256": corrected["package_sha256"],
                "case_selector": corrected["case_selector"],
            }
        ],
        "evaluators": latest["evaluator_versions"],
        "trust_and_safety": {**m["trust_and_safety"], "enabled": False, "prompts": []},
        "data_plan": {
            **m["data_plan"],
            "case_ids": sorted({e["case_id"] for e in originals}),
            "case_ids_sha256": sha(sorted({e["case_id"] for e in originals})),
        },
        "episodes": len(originals),
        "episode_formula": "the original episodes of the corrected task (cases × models × attempts)",
    }
    c.execute(
        """INSERT INTO runs.runs(id,workspace_id,project_id,name,suite_version_id,model_set,attempts,budget_usd,episode_timeout_s,
             infra_retries,created_by,execution_mode,state,purpose) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'admitted','validation')""",
        (
            run_id,
            ws,
            original["project_id"],
            f"Validation · {item['task_id']} r{corrected['revision']} (from {b['id']})",
            original["suite_version_id"],
            Jsonb(original["model_set"]),
            original["attempts"],
            original["budget_usd"],
            original["episode_timeout_s"],
            original["infra_retries"],
            actor.id,
            original["execution_mode"],
        ),
    )
    c.execute(
        "INSERT INTO runs.run_manifests(run_id,workspace_id,manifest,manifest_sha256) VALUES(%s,%s,%s,%s)",
        (run_id, ws, Jsonb(manifest), sha(manifest)),
    )
    scoring.create_pass(c, ws, run_id, "initial", latest["evaluator_versions"], actor.id)
    for n, e in enumerate(
        sorted(originals, key=lambda x: (x["system_id"], x["case_id"], x["attempt"])), start=1
    ):
        c.execute(
            """INSERT INTO runs.episodes(id,run_id,workspace_id,kind,task_import_id,task_id,task_revision,case_id,application_type,
                 completeness,edge_cases,system_id,system_version,attempt,state) VALUES(%s,%s,%s,'case',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued')""",
            (
                f"{run_id}-e{n:04d}",
                run_id,
                ws,
                corrected["id"],
                corrected["task_id"],
                corrected["revision"],
                e["case_id"],
                e["application_type"],
                e["completeness"],
                e["edge_cases"],
                e["system_id"],
                e["system_version"],
                e["attempt"],
            ),
        )
    c.execute(
        "INSERT INTO results.validation_links(item_id,workspace_id,validation_run_id,corrected_task_import_id) VALUES(%s,%s,%s,%s)",
        (item_id, ws, run_id, corrected["id"]),
    )
    c.execute(
        "UPDATE results.sme_review_items SET follow_up=%s WHERE id=%s",
        (
            Jsonb({"kind": "validation", "run_id": run_id, "text": f"Validation run {run_id}"}),
            item_id,
        ),
    )
    audit(c, ws, actor, "run.admitted", run_id, details={"purpose": "validation", "item": item_id})
    emit(
        c,
        ws,
        "run.admitted",
        run_id,
        {
            "run_id": run_id,
            "project_id": original["project_id"],
            "purpose": "validation",
            "batch_id": b["id"],
        },
    )
    return {"run_id": run_id, "episodes": len(originals)}


def _validation(c, link, item):
    run = c.execute(
        "SELECT state FROM runs.runs WHERE id=%s", (link["validation_run_id"],)
    ).fetchone()
    out = {
        "run_id": link["validation_run_id"],
        "state": run["state"],
        "result": "pending",
        "criteria": [],
    }
    if run["state"] != "completed":
        return out
    before_pass = c.execute(
        "SELECT pass_id FROM scoring.episode_scores WHERE episode_id=%s ORDER BY created_at DESC LIMIT 1",
        (item["episode_id"],),
    ).fetchone()
    before = {
        r["criterion_id"]: r["verdict"]
        for r in c.execute(
            "SELECT criterion_id, verdict FROM scoring.criterion_receipts WHERE episode_id=%s AND pass_id=%s",
            (item["episode_id"], before_pass and before_pass["pass_id"]),
        ).fetchall()
    }
    original = c.execute(
        "SELECT * FROM runs.episodes WHERE id=%s", (item["episode_id"],)
    ).fetchone()
    after_ep = c.execute(
        """SELECT e.id FROM runs.episodes e WHERE e.run_id=%s AND e.case_id=%s AND e.system_id=%s AND e.attempt=%s""",
        (
            link["validation_run_id"],
            original["case_id"],
            original["system_id"],
            original["attempt"],
        ),
    ).fetchone()
    after = {}
    passed = None
    if after_ep:
        latest = scoring.latest_pass(c, link["validation_run_id"])
        after = {
            r["criterion_id"]: r["verdict"]
            for r in c.execute(
                "SELECT criterion_id, verdict FROM scoring.criterion_receipts WHERE episode_id=%s AND pass_id=%s",
                (after_ep["id"], latest["id"]),
            ).fetchall()
        }
        s = c.execute(
            "SELECT passed FROM scoring.episode_scores WHERE episode_id=%s AND pass_id=%s",
            (after_ep["id"], latest["id"]),
        ).fetchone()
        passed = s and s["passed"]
    out["criteria"] = [
        {"criterion_id": k, "before": before.get(k), "after": after.get(k)}
        for k in sorted(set(before) | set(after))
        if before.get(k) != after.get(k) or before.get(k) != "pass"
    ]
    out["result"] = "fixed" if passed else "still_failing"
    return out


# --- views -----------------------------------------------------------------------------------------------------------


def batch_view(c, ws, batch_id):
    b = _batch(c, ws, batch_id)
    items = c.execute(
        """SELECT i.*, e.system_id, e.system_version, e.case_id, e.attempt, s.score, s.passed
           FROM results.sme_review_items i JOIN runs.episodes e ON e.id=i.episode_id
           LEFT JOIN scoring.episode_scores s ON s.episode_id=e.id AND s.pass_id=(SELECT id FROM scoring.scoring_passes WHERE run_id=e.run_id AND pass=1)
           WHERE i.batch_id=%s ORDER BY i.task_id, e.system_id, e.case_id""",
        (batch_id,),
    ).fetchall()
    validations = {}
    for link in c.execute(
        "SELECT l.* FROM results.validation_links l JOIN results.sme_review_items i ON i.id=l.item_id WHERE i.batch_id=%s",
        (batch_id,),
    ).fetchall():
        item = next(i for i in items if i["id"] == link["item_id"])
        validations[link["item_id"]] = _validation(c, link, item)
    for i in items:
        i["decision_label"] = DECISIONS.get(i["decision"])
        i["validation"] = validations.get(i["id"])
        if i["inbox_item_id"]:
            row = c.execute(
                "SELECT id, state, studio_id FROM catalog.inbox_items WHERE id=%s",
                (i["inbox_item_id"],),
            ).fetchone()
            i["inbox_item"] = row
        if i["fix_configuration"]:
            i["fix"] = c.execute(
                "SELECT id, version, state FROM catalog.evaluator_configurations WHERE workspace_id=%s AND id=%s AND version=%s",
                (ws, i["fix_configuration"], i["fix_version"]),
            ).fetchone()
        i["corrected_revision"] = (
            (lambda r: r and r["revision"])(_corrected(c, ws, b, i))
            if i["decision"] == "task_correction"
            else None
        )
    task_items = [i for i in items if i["decision"] == "task_correction"]
    if (
        b["state"] == "corrections_imported"
        and task_items
        and all(i["validation"] and i["validation"]["state"] == "completed" for i in task_items)
    ):
        c.execute(
            "UPDATE results.sme_review_batches SET state='validated' WHERE id=%s", (batch_id,)
        )
        b = _batch(c, ws, batch_id)
    decided = sum(1 for i in items if i["decision"])
    deciders = sorted({i["decided_by"] for i in items if i["decided_by"]})
    reviewed = c.execute(
        "SELECT * FROM results.reviewed_scores WHERE batch_id=%s ORDER BY system_id", (batch_id,)
    ).fetchall()
    return {
        **b,
        "items": items,
        "progress": {
            "sent": b["state"] != "building",
            "decided": decided,
            "total": len(items),
            "deciders": deciders,
            "all_decided": decided == len(items),
            "follow_ups_done": b["state"] in ("corrections_imported", "validated")
            or (decided == len(items) and not task_items),
        },
        "reviewed_scores": reviewed,
    }


def run_view(c, ws, run_id):
    run = _run(c, ws, run_id)
    batches = [
        batch_view(c, ws, r["id"])
        for r in c.execute(
            "SELECT id FROM results.sme_review_batches WHERE workspace_id=%s AND run_id=%s ORDER BY created_at DESC",
            (ws, run_id),
        ).fetchall()
    ]
    in_batch = {i["episode_id"] for bt in batches for i in bt["items"]}
    latest = scoring.latest_pass(c, run_id)
    candidates = (
        c.execute(
            """SELECT e.id, e.task_id, e.task_revision, e.case_id, e.system_id, e.attempt, e.likely_cause, e.likely_cause_source,
                  s.score, s.passed, s.failed_criteria
           FROM runs.episodes e JOIN scoring.episode_scores s ON s.episode_id=e.id AND s.pass_id=%s
           WHERE e.run_id=%s AND e.kind='case' ORDER BY s.passed, e.task_id, e.system_id, e.case_id""",
            (latest and latest["id"], run_id),
        ).fetchall()
        if latest
        else []
    )
    for cnd in candidates:
        cnd["in_batch"] = cnd["id"] in in_batch
    return {
        "run_id": run_id,
        "project_id": run["project_id"],
        "state": run["state"],
        "can_send": run["state"] == "completed",
        "candidates": candidates,
        "batches": batches,
        "decision_labels": DECISIONS,
    }


def reviewed_for_run(c, run_id):
    """Latest reviewed score per system from a decided batch (None until one is decided)."""
    rows = c.execute(
        """SELECT DISTINCT ON (r.system_id) r.* FROM results.reviewed_scores r JOIN results.sme_review_batches b ON b.id=r.batch_id
           WHERE r.run_id=%s AND b.state IN ('decided','corrections_imported','validated')
           ORDER BY r.system_id, r.computed_at DESC""",
        (run_id,),
    ).fetchall()
    return {r["system_id"]: r for r in rows}


def now():
    return dt.datetime.now(dt.UTC)
