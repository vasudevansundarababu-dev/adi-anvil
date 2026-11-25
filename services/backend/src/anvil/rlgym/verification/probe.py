"""Grader probe "invents evidence" (KYC Judgment v1): proves evidence_faithfulness catches invented evidence.

The reference agent plays each case of the suite's case set on a fresh local instance (no model, no spend), exactly as
the reference run does; then its final output gets one defect only: an audit-trail data_seen id the environment never
returned. Scored by the project's graders against the case's reference, every gradable case must fail
evidence_faithfulness as CRITICAL. A verification check beside G-01 and G-02: never a run, never a model, never
comparable to models (AGENTS.md: expected answers are read only here, never by a candidate). Runs share
verification.lookup_runs with kind "probe_invents_evidence".
"""

import copy
import json
import time
import uuid

from psycopg.types.json import Jsonb

from anvil.rlgym import integrations
from anvil.rlgym.common import GymError, sha
from anvil.rlgym.runs import images, openenv

KIND = "probe_invents_evidence"
FABRICATED = "PROBE-NEVER-RETURNED-0001"


def invent(final):
    """The final output with one data_seen id that was never returned (the episode's own output is not changed)."""
    out = copy.deepcopy(final or {})
    trail = [e for e in out.get("audit_trail") or [] if isinstance(e, dict)]
    if not trail:
        trail = [{"sop_step": "1", "status": "done", "data_seen": []}]
    trail[0]["data_seen"] = list(trail[0].get("data_seen") or []) + [FABRICATED]
    out["audit_trail"] = trail
    return out


def summarize(rows):
    caught = sum(1 for r in rows if r["critical"])
    return {
        "cases": len(rows),
        "caught": caught,
        "caught_percent": round(100 * caught / len(rows), 1) if rows else None,
        # The grader works when every gradable case's invented id is caught as critical.
        "passed": bool(rows) and caught == len(rows),
    }


def run(c, ws, sv_id, requested_by):
    from anvil.rlgym.scoring import judgment
    from anvil.rlgym.verification import reference_run

    sv, project, env, tasks = reference_run._context(c, ws, sv_id)
    rec = openenv.recipe(env)
    image = openenv.check_image(env, rec)  # identity-checked local image: nothing built or pulled
    evaluators = reference_run._evaluators(c, ws, project)
    chosen = reference_run._cases(c, ws, sv_id, env, tasks)
    ids = sorted({cid for v in chosen.values() for cid in v})
    refs = {}
    for i in range(0, len(ids), 50):
        refs.update(
            integrations.registry_get(
                f"/versions/{env['id']}/references",
                params={"ids": ",".join(ids[i : i + 50])},
                audience="scorer",
                timeout=30,
                base=env.get("registry"),
            )["references"]
        )
    jctx = reference_run.judgment_context(env, ids)
    placeholder = bool(project.get("test_only"))
    container, _ = openenv.start_instance(f"probe-{uuid.uuid4().hex[:6]}", env, image)
    rows = []
    try:
        session = openenv.OpenEnvSession(container, rec, time.monotonic() + 3000)

        def snapshot():
            return session.request({"op": "snapshot"})["collections"]

        for t in tasks:
            for cid in chosen.get((t["task_id"], t["revision"]), []):
                truth = (refs.get(cid) or {}).get("reference")
                if not truth:
                    rows.append(
                        {"case_id": cid, "task_id": t["task_id"], "skipped": "no reference"}
                    )
                    continue
                wait = judgment.awaiting(truth, placeholder_ok=placeholder)
                if wait:
                    rows.append({"case_id": cid, "task_id": t["task_id"], "skipped": wait[0]})
                    continue
                ep = reference_run._episode(session, t["actor"], truth, cid, snapshot)
                ep = {**ep, "final_output": invent(ep["final_output"])}
                score = reference_run._score(
                    c, ws, project, evaluators, t, ep, truth, judgment=jctx
                )
                ef = score["verdicts"].get("evidence_faithfulness") or {}
                lines = judgment.audit_faithfulness(
                    ep["final_output"].get("audit_trail"), ep.get("transcript"), {}, []
                )
                rows.append(
                    {
                        "case_id": cid,
                        "task_id": t["task_id"],
                        "evidence_faithfulness": ef.get("verdict"),
                        "critical": bool(lines.get("critical")) and ef.get("verdict") == "fail",
                        "points": score["points"],
                    }
                )
        session.close()
    finally:
        images.stop_instance(container)
    scored = [r for r in rows if "skipped" not in r]
    if not scored:
        raise GymError("CONFLICT", "No case of the suite's case set has a gradable reference")
    report = {
        "kind": KIND,
        **({"placeholder_graded": True} if placeholder else {}),
        "suite_version_id": str(sv_id),
        "environment": env["id"],
        "probe": "reference agent + one audit-trail id never returned (no model; never a run)",
        "invented_id": FABRICATED,
        "evaluators": [f"{e['configuration_id']} v{e['version']}" for e in evaluators],
        "judge": f"{reference_run.MOCK_JUDGE} (no live call)",
        "summary": summarize(scored),
        "cases": rows,
    }
    pid = "pr-" + uuid.uuid4().hex[:12]
    c.execute(
        "INSERT INTO verification.lookup_runs(id,workspace_id,suite_version_id,report,report_sha256,requested_by) VALUES(%s,%s,%s,%s,%s,%s)",
        (
            pid,
            ws,
            sv_id,
            Jsonb(json.loads(json.dumps(report, default=str))),
            sha(report),
            requested_by,
        ),
    )
    return {"id": pid, **report}


def latest(c, ws, sv_id):
    r = c.execute(
        """SELECT * FROM verification.lookup_runs WHERE workspace_id=%s AND suite_version_id=%s
           AND report->>'kind' = %s ORDER BY created_at DESC LIMIT 1""",
        (ws, sv_id, KIND),
    ).fetchone()
    return r and {"id": r["id"], "created_at": r["created_at"], **r["report"]}
