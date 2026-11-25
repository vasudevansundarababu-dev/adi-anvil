"""G-02 "bulletin-blind" (Studio generator 2.1.0): the honest baseline on rule-change cases.

The lookup (G-01) can be right on a rule-change case by accident when the change loosens a rule. The bulletin-blind
agent applies the starting rules correctly and never reads the bulletin: the reference agent, driven by the case's
`reference_if_not_fired`, with notices.read taken from its tools. It runs on a fresh local instance (no model, no
spend) and is scored by the project's graders against the TRUE reference (the bulletin fired). If it gets more than the
gate's share of decisions right (default 40%), the rule-change cases don't need the bulletin. Shadow mode: the
Verification row G-02 reports, it blocks nothing. Runs share verification.lookup_runs with kind "bulletin_blind".
"""

import copy
import json
import time
import uuid

from psycopg.types.json import Jsonb

from anvil.rlgym import integrations
from anvil.rlgym.common import GymError, require, sha
from anvil.rlgym.runs import images, openenv

DEFAULT_THRESHOLD = 40
KIND = "bulletin_blind"


def is_rule_change(truth):
    return isinstance((truth or {}).get("reference_if_not_fired"), dict)


def blind_actor(actor):
    """The task as the agent reads it, without notices.read (the task's own payload is never changed)."""
    out = copy.deepcopy(actor or {})
    if isinstance(out.get("tools"), list):
        out["tools"] = [t for t in out["tools"] if t != "notices.read"]
    s3 = (out.get("sections") or {}).get("S3")
    if isinstance(s3, dict) and isinstance(s3.get("tools"), list):
        s3["tools"] = [t for t in s3["tools"] if t != "notices.read"]
    return out


def blind_reference(truth):
    """What the starting rules decide: the answer as if no bulletin had been published."""
    return dict(truth["reference_if_not_fired"])


def bulletin_fired(ep):
    """Did the case's bulletin publish before the agent's decision? Only then does the case test the bulletin: an
    unfired bulletin leaves the starting rules in force (the grader grades reference_if_not_fired), so the blind
    agent's answer is simply right. Studio's trigger is an operation (e.g. after document.check), which the task's
    procedure may never reach."""
    from anvil.rlgym.runs import events as scenario_log
    from anvil.rlgym.scoring import judgment

    fired = (scenario_log.scenario_events(ep.get("snapshots"), ep.get("transcript")) or {}).get(
        "fired"
    ) or []
    cut = judgment.recommend_sequence(ep.get("transcript"))
    return any(
        (f.get("published_at_sequence") or 0) < cut for f in fired if f.get("published_at_sequence")
    )


def threshold(body):
    v = (body or {}).get("threshold_percent", DEFAULT_THRESHOLD)
    require(
        isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100,
        "VALIDATION_FAILED",
        "The bulletin-blind gate is a percentage from 0 to 100",
        field="threshold_percent",
    )
    return v


def summarize(rows, gate, unfired=0):
    from anvil.rlgym.verification.lookup import _points

    got = sum(_points(r["points"])[0] for r in rows)
    top = sum(_points(r["points"])[1] for r in rows)
    right = sum(1 for r in rows if r["decision_right"])
    pct = round(100 * right / len(rows), 1) if rows else None
    return {
        "cases": len(rows),
        # Rule-change cases played whose bulletin never published before the decision: not counted (nothing tested).
        "bulletin_not_fired": unfired,
        "decisions_right": right,
        "right_percent": pct,
        "points_percent": round(100 * got / top, 1) if top else None,
        "full_marks": sum(1 for r in rows if r["full_marks"]),
        "gate": {"threshold_percent": gate, "passed": pct is not None and pct <= gate},
    }


def run(c, ws, sv_id, requested_by, body=None):
    from anvil.rlgym.scoring import judgment
    from anvil.rlgym.verification import reference_run
    from anvil.rlgym.verification.lookup import _decision

    gate = threshold(body)
    sv, project, env, tasks = reference_run._context(c, ws, sv_id)
    rec = openenv.recipe(env)
    image = openenv.check_image(env, rec)  # identity-checked local image: nothing built or pulled
    evaluators = reference_run._evaluators(c, ws, project)
    chosen = reference_run._cases(c, ws, sv_id, env, tasks)
    ids = sorted({cid for v in chosen.values() for cid in v})
    jctx = reference_run.judgment_context(env, ids)
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
    placeholder = bool(project.get("test_only"))
    container, _ = openenv.start_instance(f"blind-{uuid.uuid4().hex[:6]}", env, image)
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
                if not is_rule_change(truth):
                    continue  # G-02 is about rule-change cases only
                wait = judgment.awaiting(truth, placeholder_ok=placeholder)
                if wait:
                    rows.append({"case_id": cid, "task_id": t["task_id"], "skipped": wait[0]})
                    continue
                said = blind_reference(truth)
                # The starting rules drive the procedure; no notices are read; the score is against the truth.
                ep = reference_run._episode(session, blind_actor(t["actor"]), said, cid, snapshot)
                if not bulletin_fired(ep):
                    rows.append(
                        {
                            "case_id": cid,
                            "task_id": t["task_id"],
                            "skipped": "bulletin never fired before the decision (its trigger was not reached)",
                        }
                    )
                    continue
                score = reference_run._score(
                    c, ws, project, evaluators, t, ep, truth, judgment=jctx
                )
                blind_d, truth_d = _decision(said), _decision(truth)
                rows.append(
                    {
                        "case_id": cid,
                        "task_id": t["task_id"],
                        "blind": blind_d,
                        "truth": truth_d,
                        "decision_right": blind_d == truth_d,
                        "points": score["points"],
                        "full_marks": score["full_marks"],
                        "not_passed": sorted(
                            k for k, v in score["verdicts"].items() if v["verdict"] != "pass"
                        ),
                    }
                )
        session.close()
    finally:
        images.stop_instance(container)
    scored = [r for r in rows if "skipped" not in r]
    unfired = sum(1 for r in rows if str(r.get("skipped", "")).startswith("bulletin never fired"))
    if not scored:
        raise GymError(
            "CONFLICT",
            "No rule-change case of the suite's case set has a gradable reference whose bulletin fired"
            + (
                f" ({unfired} played; the bulletin never fired before the decision)"
                if unfired
                else ""
            ),
        )
    report = {
        "kind": "bulletin_blind",
        **({"placeholder_graded": True} if placeholder else {}),
        "suite_version_id": str(sv_id),
        "environment": env["id"],
        "baseline": "reference agent on the starting rules, notices never read (no model)",
        "evaluators": [f"{e['configuration_id']} v{e['version']}" for e in evaluators],
        "judge": f"{reference_run.MOCK_JUDGE} (no live call)",
        "summary": summarize(scored, gate, unfired),
        "cases": rows,
    }
    bid = "bb-" + uuid.uuid4().hex[:12]
    c.execute(
        "INSERT INTO verification.lookup_runs(id,workspace_id,suite_version_id,report,report_sha256,requested_by) VALUES(%s,%s,%s,%s,%s,%s)",
        (
            bid,
            ws,
            sv_id,
            Jsonb(json.loads(json.dumps(report, default=str))),
            sha(report),
            requested_by,
        ),
    )
    return {"id": bid, **report}


def latest(c, ws, sv_id):
    r = c.execute(
        """SELECT * FROM verification.lookup_runs WHERE workspace_id=%s AND suite_version_id=%s
           AND report->>'kind' = %s ORDER BY created_at DESC LIMIT 1""",
        (ws, sv_id, KIND),
    ).fetchone()
    return r and {"id": r["id"], "created_at": r["created_at"], **r["report"]}
