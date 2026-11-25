"""E-007 V-04 (reference-solvable) and V-01 (replay) for a suite version.

The reference agent runs every task on its cases from the suite's case set, on one fresh local instance of the bound
environment (identity-checked image; nothing built or pulled; no model). It goes through the same opaque IDs a model
sees. Its episodes are scored by the project's current graders on their real IDs (judge blocks use the local mock
judge: no live call, no spend; said in the result), with the task's S7 points. V-04 passes only when every task scores
full marks and no critical criterion fails, and the task's reference approach has been confirmed by a person.

V-01 replays each reference episode on a second fresh instance with the same inputs and compares, step by step, the
observation the environment returned, the end-state snapshot and the verdicts: every digest must match.
"""

import json
import time
import uuid

from psycopg.types.json import Jsonb

from anvil.rlgym import integrations
from anvil.rlgym.common import GymError, require, sha
from anvil.rlgym.runs import aliasing, images, openenv, sampling
from anvil.rlgym.scoring import judgment
from anvil.rlgym.verification import reference

MOCK_JUDGE = "mock-judge"


def _context(c, ws, sv_id):
    sv = c.execute(
        "SELECT * FROM suites.suite_versions WHERE workspace_id=%s AND id=%s", (ws, sv_id)
    ).fetchone()
    require(sv, "NOT_FOUND", "Suite version not found")
    project = c.execute(
        "SELECT * FROM projects.projects WHERE workspace_id=%s AND project_id=%s",
        (ws, sv["project_id"]),
    ).fetchone()
    env = c.execute(
        "SELECT * FROM catalog.environment_versions WHERE id=%s", (sv["planned_on_env_version"],)
    ).fetchone()
    require(
        env and openenv.is_openenv(env),
        "CONFLICT",
        "V-04/V-01 run on Studio OpenEnv environments only",
    )
    tasks = c.execute(
        """SELECT t.id, t.task_id, t.revision, t.package_sha256, t.case_selector, a.content actor, p.content private
           FROM suites.suite_tasks s JOIN projects.task_imports t ON t.id=s.task_import_id
           LEFT JOIN projects.task_payloads a ON a.workspace_id=t.workspace_id AND a.package_sha256=t.package_sha256 AND a.part='actor'
           LEFT JOIN projects.task_payloads p ON p.workspace_id=t.workspace_id AND p.package_sha256=t.package_sha256 AND p.part='private'
           WHERE s.suite_version_id=%s ORDER BY t.task_id""",
        (sv_id,),
    ).fetchall()
    return sv, project, env, tasks


def _evaluators(c, ws, project):
    from anvil.rlgym.catalog import selection
    from anvil.rlgym.projects import service as projects

    out = []
    for rule in projects._current_eval_rules(c, ws, project["project_id"]):
        pick, _, _ = selection.resolve_evaluator(c, ws, rule)
        if pick:
            crit = (
                c.execute(
                    "SELECT * FROM catalog.template_criteria WHERE workspace_id=%s AND template_id=%s AND version=%s AND criterion_id=%s",
                    (ws, project["template_id"], project["template_version"], rule["criterion_id"]),
                ).fetchone()
                or {}
            )
            out.append(
                {
                    "criterion_id": rule["criterion_id"],
                    "configuration_id": pick["id"],
                    "version": pick["version"],
                    "config_sha256": pick["config_sha256"],
                    "framework": pick["framework_version_id"],
                    "weight": float(crit.get("weight") or pick["weight"]),
                    "is_gate": bool(crit.get("is_gate")),
                }
            )
    return out


def _cases(c, ws, sv_id, env, tasks):
    from anvil.rlgym.suites import cases as suite_cases

    rows = suite_cases._rows(env)
    chosen = {}
    try:
        for x in suite_cases.case_set(c, ws, sv_id)["cases"]:
            if x.get("task"):
                chosen.setdefault((x["task"]["task_id"], x["task"]["revision"]), []).append(
                    x["case_id"]
                )
    except GymError:
        pass
    for t in tasks:  # a task with no case in the set still gets one case it takes
        key = (t["task_id"], t["revision"])
        if not chosen.get(key):
            for r in rows:
                if sampling.match_task(r, [dict(t)], 1):
                    chosen[key] = [r["case_id"]]
                    break
    return chosen


def _episode(session, actor, ref, case_id, start_snapshot_fn, alias=True):
    session.request({"op": "reset", "case_id": case_id, "inject": None})
    start = start_snapshot_fn()
    al = aliasing.Aliaser(case_id, start) if alias else None
    shown = (lambda v: al.out(v)) if al else (lambda v: v)
    real = (lambda v: al.back(v)) if al else (lambda v: v)
    # transcript: real-ID observations for grading only (audit faithfulness, notices read); never stored.
    failures, events, trace, transcript = [], [], [], []
    ops = session.request({"op": "operations"}).get("operations")
    gen = reference.agent(actor, ref, shown(case_id), failures, operations=ops)
    action = next(gen)
    final = None
    for step in range(1, 200):
        if "final" in action:
            final = real(action["final"])
            break
        tool, args = action["tool"], real(action.get("args") or {})
        obs = session.request({"op": "call", "tool": tool, "args": args})
        events.append(
            {
                "tool": tool,
                "args": args,
                "ok": bool(obs.get("ok", False)),
                "blocked": bool(obs.get("blocked")),
            }
        )
        trace.append({"step": step, "tool": tool, "obs_sha256": reference.digest(obs)})
        transcript.append({"step": step, "tool": tool, "args": args, "observation": obs})
        try:
            action = gen.send(shown(obs))
        except StopIteration:
            break
    end = session.request({"op": "snapshot"})["collections"]
    return {
        "case_id": case_id,
        "tool_events": events,
        "final_output": final,
        "snapshots": {"start": start, "end": end},
        "transcript": transcript,
        "failures": failures,
        "trace": trace,
        "end_sha256": reference.digest(end),
    }


def judgment_context(env, case_ids):
    """KYC Judgment v1: the part a run freezes in its manifest (policy library, scenarios, case facts) for these
    cases of the environment; None for any other environment (v8: no call)."""
    from anvil.rlgym.runs import service as runs
    from anvil.rlgym.suites import cases as suite_cases

    ids = set(case_ids)
    selected = [r for r in suite_cases._rows(env) if r["case_id"] in ids]
    return runs.env_judgment_part(env, selected)


def _score(c, ws, project, evaluators, task, ep, ref, judgment=None):
    """Graders on the reference episode (real IDs), judge blocks on the mock judge; S7 points when the task has them.
    KYC Judgment criteria are graded as in a run: `judgment` is judgment_context's part, and a test-only project
    grades placeholder references (never awaiting_sme)."""
    from anvil.rlgym.plugins import service as plugins
    from anvil.rlgym.runs import events as scenario_log
    from anvil.rlgym.scoring import s7, sandbox
    from anvil.rlgym.scoring import service as scoring

    manifest = {
        "template": {"id": project["template_id"], "version": project["template_version"]},
        "plugins": {},
        "placeholder_graded": bool(project.get("test_only")),
        "judgment": judgment,
    }
    episode = {
        "id": f"ref-{task['task_id'][:8]}-{ep['case_id']}",
        "run_id": "reference",
        "workspace_id": ws,
        "case_id": ep["case_id"],
        "task_import_id": task["id"],
    }
    vctx = scoring.verifier_context(c, ws, episode, manifest)
    configs = scoring._configs(c, ws, evaluators)
    if vctx:
        mock = {
            cid: {
                "block_overrides": {
                    b["id"]: {"settings": {"judge": MOCK_JUDGE}}
                    for b in blocks
                    if (b.get("settings") or {}).get("judge")
                }
            }
            for cid, blocks in vctx["blocks"].items()
        }
        vctx = scoring.apply_overrides(
            vctx, configs, {k: v for k, v in mock.items() if v["block_overrides"]}
        )
        for blocks in vctx["blocks"].values():
            for b in blocks:
                if b.get("plugin"):
                    row = plugins.resolve(c, b["plugin"])
                    if row:
                        manifest["plugins"][b["id"]] = {
                            "plugin_id": row["runtime_id"],
                            "version": row["version"],
                            "framework_version_id": row["id"],
                            "image": row["image_digest"],
                            "manifest_sha256": row["manifest_sha256"],
                        }
    bundle = {
        "tool_events": ep["tool_events"],
        "final_output": ep["final_output"],
        "snapshots": ep["snapshots"],
        "transcript": ep.get("transcript"),
    }
    scenario = scenario_log.scenario_events(ep["snapshots"], ep.get("transcript"))
    if scenario:
        bundle["scenario_events"] = scenario
    plugin_lines = scoring.plugin_results(c, episode, manifest, vctx, bundle, ref) if vctx else {}
    evidence = {
        "tool_events": ep["tool_events"],
        "final_output": ep["final_output"],
        "snapshots": ep["snapshots"],
    }
    judgment_lines = scoring.judgment_results(manifest, episode, bundle, ref, vctx, configs)
    verdicts = {}
    by_fw = {}
    for ev, row in configs:
        by_fw.setdefault(row["framework_id"], []).append((ev, row))
    for _, group in by_fw.items():
        fw = {
            "id": group[0][1]["framework_id"],
            "runtime_id": group[0][1]["runtime_id"],
            "installed_locally": group[0][1]["installed_locally"],
            "state": group[0][1]["framework_state"],
        }
        extras = []
        for ev, row in group:
            blocks = (vctx or {}).get("blocks", {}).get(ev["criterion_id"])
            extra = (
                {
                    "blocks": blocks,
                    "case_id": ep["case_id"],
                    "slots": vctx["slots"],
                    "expected_values_from": vctx["expected_values_from"],
                    "plugin_results": plugin_lines,
                }
                if blocks and row["config"].get("runner") == "verifier_blocks"
                else {}
            )
            extras.append(
                scoring.judgment_extra(row["config"], ev["criterion_id"], extra, judgment_lines)
            )
        out = sandbox.run_batch(
            fw, [row["config"] for _, row in group], evidence, ref, extras=extras
        )
        for (ev, _), v in zip(group, out, strict=True):
            verdicts[ev["criterion_id"]] = {
                "verdict": v.get("verdict"),
                "failed_lines": [
                    ln["block_id"]
                    for ln in v.get("block_lines") or []
                    if ln.get("verdict") != "pass"
                ],
            }
    s7_section = ((((task["private"] or {}).get("authored") or {}).get("sections")) or {}).get("S7")
    prof, _ = s7.profile(s7_section) if s7_section else (None, None)
    counted = {
        k: v["verdict"]
        for k, v in verdicts.items()
        if v["verdict"] in ("pass", "partial", "fail", "blocked")
    }
    if prof:
        out = s7.outcome(prof, counted, prof["weights"])
        full = out["points"] == out["max_points"] and out["passed"]
        points = f"{out['points']:g}/{out['max_points']:g}"
    else:
        full = bool(counted) and all(v == "pass" for v in counted.values())
        points = f"{sum(1 for v in counted.values() if v == 'pass')}/{len(counted)}"
    return {
        "verdicts": verdicts,
        "points": points,
        "full_marks": full,
        "verdicts_sha256": reference.digest(counted),
    }


def run(c, ws, sv_id, requested_by, replay=True, max_cases_per_task=3):
    sv, project, env, tasks = _context(c, ws, sv_id)
    # Integration test only: a test-only project grades placeholder references (never awaiting_sme).
    placeholder = bool(project.get("test_only"))
    rec = openenv.recipe(env)
    image = openenv.check_image(
        env, rec
    )  # identity-checked local image: nothing is built or pulled
    evaluators = _evaluators(c, ws, project)
    chosen = _cases(c, ws, sv_id, env, tasks)
    ids = sorted({cid for v in chosen.values() for cid in v[:max_cases_per_task]})
    refs = (
        integrations.registry_get(
            f"/versions/{env['id']}/references",
            params={"ids": ",".join(ids)},
            audience="scorer",
            timeout=30,
            base=env.get("registry"),
        )["references"]
        if ids
        else {}
    )
    confirmations = {
        (r["package_sha256"], r["summary_sha256"]): r
        for r in c.execute(
            "SELECT DISTINCT ON (package_sha256, summary_sha256) * FROM verification.reference_confirmations "
            "WHERE workspace_id=%s ORDER BY package_sha256, summary_sha256, decided_at DESC",
            (ws,),
        ).fetchall()
    }

    def one_pass():
        container, _ = openenv.start_instance(f"ref-{uuid.uuid4().hex[:6]}", env, image)
        out = {}
        try:
            session = openenv.OpenEnvSession(container, rec, time.monotonic() + 3000)
            for t in tasks:
                for cid in chosen.get((t["task_id"], t["revision"]), [])[:max_cases_per_task]:
                    ref = (refs.get(cid) or {}).get("reference") or {}
                    if judgment.awaiting(ref, placeholder_ok=placeholder):
                        continue  # reference.v2: not graded until the SME / PM answers
                    out[(t["task_id"], cid)] = _episode(
                        session,
                        t["actor"],
                        ref,
                        cid,
                        lambda: session.request({"op": "snapshot"})["collections"],
                    )
            session.close()
        finally:
            images.stop_instance(container)
        return out

    graded = sorted(
        {
            cid
            for t in tasks
            for cid in chosen.get((t["task_id"], t["revision"]), [])[:max_cases_per_task]
        }
    )
    jctx = judgment_context(env, graded)
    first = one_pass()
    second = one_pass() if replay else None
    results = []
    for t in tasks:
        summ = reference.summary(t["actor"])
        conf = confirmations.get((t["package_sha256"], summ["sha256"]))
        rows = []
        for cid in chosen.get((t["task_id"], t["revision"]), [])[:max_cases_per_task]:
            ref = (refs.get(cid) or {}).get("reference") or {}
            wait = judgment.awaiting(ref, placeholder_ok=placeholder)
            if wait:
                rows.append(
                    {
                        "case_id": cid,
                        "awaiting": {"status": wait[0], "reasons": wait[1]},
                        "failures": [],
                        "points": None,
                        "full_marks": None,
                        "verdicts": {},
                        "steps": 0,
                    }
                )
                continue
            ep = first[(t["task_id"], cid)]
            score = _score(c, ws, project, evaluators, t, ep, ref, judgment=jctx)
            row = {
                "case_id": cid,
                "failures": ep["failures"],
                "points": score["points"],
                "full_marks": score["full_marks"],
                "verdicts": score["verdicts"],
                "steps": len(ep["trace"]),
            }
            if second is not None:
                ep2 = second[(t["task_id"], cid)]
                score2 = _score(c, ws, project, evaluators, t, ep2, ref, judgment=jctx)
                diffs = [
                    a["step"] for a, b in zip(ep["trace"], ep2["trace"], strict=False) if a != b
                ]
                row["replay"] = {
                    "observations_match": len(ep["trace"]) == len(ep2["trace"]) and not diffs,
                    "first_different_step": diffs[0] if diffs else None,
                    "end_state_match": ep["end_sha256"] == ep2["end_sha256"],
                    "verdicts_match": score["verdicts_sha256"] == score2["verdicts_sha256"],
                }
            rows.append(row)
        results.append(
            {
                "task_id": t["task_id"],
                "revision": t["revision"],
                "package_sha256": t["package_sha256"],
                "summary": summ,
                "confirmed": conf
                and {k: conf[k] for k in ("verdict", "note", "decided_by", "decided_at")},
                "cases": rows,
            }
        )
    report = {
        **({"placeholder_graded": True} if placeholder else {}),
        "suite_version_id": str(sv_id),
        "environment": env["id"],
        "judge": f"{MOCK_JUDGE} (no live call in V-04/V-01)",
        "evaluators": [f"{e['configuration_id']} v{e['version']}" for e in evaluators],
        "tasks": results,
    }
    rid = "rr-" + uuid.uuid4().hex[:12]
    c.execute(
        "INSERT INTO verification.reference_runs(id,workspace_id,suite_version_id,report,report_sha256,requested_by) VALUES(%s,%s,%s,%s,%s,%s)",
        (
            rid,
            ws,
            sv_id,
            Jsonb(json.loads(json.dumps(report, default=str))),
            sha(report),
            requested_by,
        ),
    )
    return {"id": rid, **report}


def confirm(ctx, task_import_id, verdict, note):
    """A person confirms (or rejects) a task's reference approach, bound to the task package and the summary's hash.
    Owner default: an Admin may confirm for the SME."""
    ctx.actor.require_person()
    require(
        ctx.actor.profile in ("admin", "rl_engineer"),
        "FORBIDDEN",
        "An Admin (for the SME) or RL Engineer confirms",
    )
    require(verdict in ("confirmed", "not_right"), "VALIDATION_FAILED", "Confirm or Not right")
    require(
        verdict == "confirmed" or (note or "").strip(), "VALIDATION_FAILED", "Say what's not right"
    )
    t = ctx.c.execute(
        """SELECT t.*, a.content actor FROM projects.task_imports t LEFT JOIN projects.task_payloads a
           ON a.workspace_id=t.workspace_id AND a.package_sha256=t.package_sha256 AND a.part='actor'
           WHERE t.workspace_id=%s AND t.id=%s""",
        (ctx.ws, task_import_id),
    ).fetchone()
    require(t, "NOT_FOUND", "Task not found")
    summ = reference.summary(t["actor"])
    ctx.c.execute(
        """INSERT INTO verification.reference_confirmations(id,workspace_id,task_import_id,package_sha256,summary_sha256,
             summary,verdict,note,decided_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            "rc-" + uuid.uuid4().hex[:10],
            ctx.ws,
            task_import_id,
            t["package_sha256"],
            summ["sha256"],
            summ["text"],
            verdict,
            (note or "").strip() or None,
            str(ctx.actor.id),
        ),
    )
    return {"task_id": t["task_id"], "revision": t["revision"], "verdict": verdict, "summary": summ}


def latest(c, ws, sv_id):
    r = c.execute(
        "SELECT * FROM verification.reference_runs WHERE workspace_id=%s AND suite_version_id=%s ORDER BY created_at DESC LIMIT 1",
        (ws, sv_id),
    ).fetchone()
    return r and {"id": r["id"], "created_at": r["created_at"], **r["report"]}
