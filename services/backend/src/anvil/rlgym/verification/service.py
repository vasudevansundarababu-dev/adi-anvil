"""E-007 phase 1: the verification report for a run, in shadow mode (it reports; it blocks nothing).

After a run ends (or on request) the RL Gym checks that the run can be trusted, from its sealed evidence, manifest and
recorded scores only. Every check has one of five outcomes: PASS, FAIL, INSUFFICIENT_EVIDENCE, NOT_APPLICABLE (with
the policy reason), ERROR. Reports are append-only (verification.reports); a later check is a new report.

Checks in this phase:
- ROSTER: the manifest's planned episodes, the episode rows and the sealed evidence reconcile (D-030).
- V-12 grader replay: the recorded graders, replayed on the sealed evidence, give the same verdicts. Deterministic
  checks must match exactly; plug-in and judge lines reuse their recorded answers (E-007 §3.3).
- KYC independent assertions (verification/assertions.py, never importing the grader): MISMATCH where they disagree.
- V-02 isolation, V-03 tool errors kept apart from agent failures.
- V-05 blind shortcut, V-06 read-only shortcut, V-07 ordering: synthetic controls on this run's own cases and graders;
  none may pass (V-07: right writes in the wrong order must lose points).
- V-01 environment replay and V-04 oracle: INSUFFICIENT_EVIDENCE until the replay harness and the SME-confirmed
  reference agent exist (phase 1 states it; never a pass).
- V-L1 leakage, C-01 grader configuration, S-01 to S-04 safety honesty.
- G-01 lookup baseline (G4, E-011 §3): the suite version's latest no-AI lookup run must score at or below its gate
  (default 60%); above it, the cases don't need reasoning.
"""

import statistics
import uuid

from psycopg.types.json import Jsonb

from anvil.rlgym.common import GymError, sha

OUTCOMES = ("PASS", "FAIL", "INSUFFICIENT_EVIDENCE", "NOT_APPLICABLE", "ERROR")
WORDS = {
    "PASS": "Verified",
    "FAIL": "Failed",
    "INSUFFICIENT_EVIDENCE": "Not enough evidence",
    "NOT_APPLICABLE": "Not applicable",
    "ERROR": "Couldn't run",
}
FIXTURE_NOTE = "awaiting SME: the fixture's expected outcome is not yet confirmed by an SME"


def row(cid, name, outcome, detail, evidence=None):
    assert outcome in OUTCOMES
    return {
        "id": cid,
        "name": name,
        "outcome": outcome,
        "shown_as": WORDS[outcome],
        "detail": detail,
        "evidence": evidence or {},
    }


def _episodes(c, run_id):
    return c.execute(
        """SELECT e.*, x.bundle_ref, x.sealed_sha256 FROM runs.episodes e
           LEFT JOIN runs.sealed_evidence x ON x.episode_id=e.id WHERE e.run_id=%s ORDER BY e.id""",
        (run_id,),
    ).fetchall()


def roster(manifest, episodes):
    planned = manifest.get("episodes")
    sealed = [e for e in episodes if e["bundle_ref"]]
    ended = [
        e
        for e in episodes
        if e["state"] in ("completed", "scored", "errored", "timed_out", "cancelled")
    ]
    problems = []
    if planned is not None and planned != len(episodes):
        problems.append(f"the manifest plans {planned} episodes; {len(episodes)} exist")
    unsealed = [
        e["id"] for e in episodes if e["state"] in ("completed", "scored") and not e["bundle_ref"]
    ]
    if unsealed:
        problems.append(f"{len(unsealed)} finished episode(s) have no sealed evidence")
    ev = {
        "planned": planned,
        "episodes": len(episodes),
        "sealed": len(sealed),
        "ended": len(ended),
        "by_state": {
            s: sum(1 for e in episodes if e["state"] == s)
            for s in sorted({e["state"] for e in episodes})
        },
    }
    if not episodes:
        return row("ROSTER", "Roster and counts reconcile", "FAIL", "the run has no episodes", ev)
    return row(
        "ROSTER",
        "Roster and counts reconcile",
        "FAIL" if problems else "PASS",
        "; ".join(problems) or "planned, created and sealed episodes reconcile",
        ev,
    )


def _recorded(c, pass_id, episode_id):
    return {
        r["criterion_id"]: r
        for r in c.execute(
            "SELECT * FROM scoring.criterion_receipts WHERE pass_id=%s AND episode_id=%s",
            (pass_id, episode_id),
        ).fetchall()
    }


def grader_replay(c, ws, manifest, pass_row, cases, bundles, refs):
    """V-12: replay the pass's graders on the sealed evidence; deterministic verdicts must be identical."""
    from anvil.rlgym.scoring import sandbox
    from anvil.rlgym.scoring import service as scoring

    configs = scoring._configs(c, ws, pass_row["evaluator_versions"])
    same = differ = 0
    diffs = []
    for e in cases:
        bundle, ref = bundles.get(e["id"]), refs.get(e["id"])
        if bundle is None or ref is None:
            continue
        recorded = _recorded(c, pass_row["id"], e["id"])
        evidence = {
            k: bundle[k] for k in ("tool_events", "final_output") if bundle.get(k) is not None
        }
        vctx = scoring.verifier_context(c, ws, e, manifest)
        if vctx and (bundle.get("snapshots") or {}).get("end") is not None:
            evidence["snapshots"] = bundle["snapshots"]
        given = {}
        for r in recorded.values():
            for ln in r.get("block_lines") or []:
                if ln.get("kind") in ("plugin", "rubric"):
                    given[ln["block_id"]] = ln
        by_fw = {}
        for ev, cfg in configs:
            by_fw.setdefault(cfg["framework_id"], []).append((ev, cfg))
        for _, group in by_fw.items():
            fw = {
                "id": group[0][1]["framework_id"],
                "runtime_id": group[0][1]["runtime_id"],
                "installed_locally": group[0][1]["installed_locally"],
                "state": group[0][1]["framework_state"],
            }
            extras = []
            for ev, cfg in group:
                blocks = (vctx or {}).get("blocks", {}).get(ev["criterion_id"])
                if blocks and cfg["config"].get("runner") == "verifier_blocks":
                    extras.append(
                        {
                            "blocks": blocks,
                            "case_id": e["case_id"],
                            "slots": vctx["slots"],
                            "expected_values_from": vctx["expected_values_from"],
                            "plugin_results": {
                                k: v for k, v in given.items() if v.get("kind") == "plugin"
                            },
                            "rubric_verdicts": {
                                k: {"verdict": v["verdict"]}
                                for k, v in given.items()
                                if v.get("kind") == "rubric"
                            },
                        }
                    )
                else:
                    extras.append({})
            try:
                out = sandbox.run_batch(
                    fw, [cfg["config"] for _, cfg in group], evidence, ref, extras=extras
                )
            except GymError as exc:
                return row(
                    "V-12",
                    "Stateless regrading",
                    "ERROR",
                    f"the sandbox could not run: {exc.message}",
                )
            for (ev, _), v in zip(group, out, strict=True):
                was = (recorded.get(ev["criterion_id"]) or {}).get("verdict")
                if was is None or was in ("not_applicable", "unresolved", "setup_gap"):
                    continue
                if v.get("verdict") == was:
                    same += 1
                else:
                    differ += 1
                    if len(diffs) < 10:
                        diffs.append(
                            {
                                "episode": e["id"],
                                "criterion": ev["criterion_id"],
                                "recorded": was,
                                "replayed": v.get("verdict"),
                            }
                        )
    if same + differ == 0:
        return row(
            "V-12",
            "Stateless regrading",
            "INSUFFICIENT_EVIDENCE",
            "no scored case episode to replay",
        )
    return row(
        "V-12",
        "Stateless regrading",
        "FAIL" if differ else "PASS",
        f"{same} verdicts identical, {differ} differ (plug-in and judge lines reuse their recorded answers)",
        {"identical": same, "different": differ, "examples": diffs},
    )


def independent(c, pass_row, cases, bundles, refs):
    """KYC assertions vs the grader's verdicts: MISMATCH where the grader passes what the assertion fails."""
    from anvil.rlgym.verification import assertions

    mism, agree, rows = 0, 0, []
    for e in cases:
        bundle, ref = bundles.get(e["id"]), refs.get(e["id"])
        if bundle is None or ref is None:
            continue
        recorded = _recorded(c, pass_row["id"], e["id"])
        for a in assertions.run_all(bundle, ref):
            if a["outcome"] == "NOT_APPLICABLE":
                continue
            verdict = (recorded.get(a["criterion"]) or {}).get("verdict")
            if verdict not in ("pass", "partial", "fail"):
                continue
            grader_ok = verdict == "pass"
            # An assertion covers part of a criterion, so a failed criterion with a passing assertion is not a
            # contradiction. A MISMATCH is the grader passing what an independent assertion fails (D-041's kind).
            if not (grader_ok and a["outcome"] == "FAIL"):
                agree += 1
            else:
                mism += 1
                if len(rows) < 20:
                    rows.append(
                        {
                            "episode": e["id"],
                            "case": e["case_id"],
                            "assertion": a["id"],
                            "criterion": a["criterion"],
                            "grader": verdict,
                            "assertion_outcome": a["outcome"],
                            "expected": a["expected"],
                            "observed": a["observed"],
                        }
                    )
    if agree + mism == 0:
        return row(
            "KYC",
            "Independent KYC assertions agree with the grader",
            "INSUFFICIENT_EVIDENCE",
            "no scored case episode with a KYC assertion",
        )
    return row(
        "KYC",
        "Independent KYC assertions agree with the grader",
        "FAIL" if mism else "PASS",
        f"{agree} consistent, {mism} MISMATCH (the grader passed what an independent assertion fails)",
        {"agree": agree, "mismatch": mism, "mismatches": rows},
    )


def isolation(cases, bundles):
    writable = ("findings", "recommendations", "information_requests", "referrals")
    dirty = []
    for e in cases:
        start = ((bundles.get(e["id"]) or {}).get("snapshots") or {}).get("start")
        if start and any(start.get(t) for t in writable):
            dirty.append(e["id"])
    seen = [e for e in cases if ((bundles.get(e["id"]) or {}).get("snapshots") or {}).get("start")]
    if not seen:
        return row(
            "V-02", "Episode isolation", "INSUFFICIENT_EVIDENCE", "no start state was recorded"
        )
    return row(
        "V-02",
        "Episode isolation",
        "FAIL" if dirty else "PASS",
        f"{len(dirty)} episode(s) started with another episode's writes"
        if dirty
        else f"all {len(seen)} episodes started from a clean state",
        {"dirty": dirty[:10]},
    )


def tool_errors(episodes, bundles):
    infra = [e for e in episodes if e["state"] in ("errored", "timed_out")]
    scored_after_infra = [e["id"] for e in infra if e["state"] == "scored"]
    calls = sum(len((bundles.get(e["id"]) or {}).get("tool_events") or []) for e in episodes)
    refused = sum(
        1
        for e in episodes
        for t in (bundles.get(e["id"]) or {}).get("tool_events") or []
        if not t.get("ok", True)
    )
    return row(
        "V-03",
        "Tool errors kept apart from agent failures",
        "FAIL" if scored_after_infra else "PASS",
        f"{len(infra)} episode(s) ended on an infrastructure error and were not scored; {refused} of {calls} "
        "tool calls were refused by the environment (the agent's own outcome)",
        {
            "infrastructure_errors": [e["id"] for e in infra][:10],
            "refused_calls": refused,
            "calls": calls,
        },
    )


def _controls(c, ws, manifest, pass_row, cases, bundles, refs):
    """V-05, V-06, V-07 on this run's own cases and graders (synthetic evidence; nothing is written)."""
    from anvil.rlgym.scoring import s7, sandbox
    from anvil.rlgym.scoring import service as scoring
    from anvil.rlgym.verification import assertions

    configs = scoring._configs(c, ws, pass_row["evaluator_versions"])
    picked = {}
    for e in cases:  # one case per task
        if (
            e["id"] in bundles
            and e["id"] in refs
            and (bundles[e["id"]].get("snapshots") or {}).get("start")
        ):
            picked.setdefault(e["task_id"], e)
    if not picked:
        return None

    def score(e, events, end, plugin_verdict):
        bundle, ref = bundles[e["id"]], refs[e["id"]]
        start = bundle["snapshots"]["start"]
        vctx = scoring.verifier_context(c, ws, e, manifest)
        evidence = {
            "tool_events": events,
            "final_output": None,
            "snapshots": {"start": start, "end": end},
        }
        verdicts = {}
        for ev, cfg in configs:
            blocks = (vctx or {}).get("blocks", {}).get(ev["criterion_id"])
            fw = {
                "id": cfg["framework_id"],
                "runtime_id": cfg["runtime_id"],
                "installed_locally": cfg["installed_locally"],
                "state": cfg["framework_state"],
            }
            extra = {}
            if blocks and cfg["config"].get("runner") == "verifier_blocks":
                extra = {
                    "blocks": blocks,
                    "case_id": e["case_id"],
                    "slots": vctx["slots"],
                    "expected_values_from": vctx["expected_values_from"],
                    "plugin_results": {
                        b["id"]: {"verdict": plugin_verdict, "block_id": b["id"]}
                        for b in blocks
                        if b.get("plugin")
                    },
                }
            verdicts[ev["criterion_id"]] = sandbox.run(
                fw, cfg["config"], evidence, ref, extra=extra
            ).get("verdict")
        prof = next(
            (
                t.get("scoring")
                for t in manifest.get("tasks") or []
                if t.get("task_id") == e["task_id"]
            ),
            None,
        )
        counted = {k: v for k, v in verdicts.items() if v in ("pass", "partial", "fail", "blocked")}
        if prof:
            return s7.outcome(prof, counted, prof["weights"])["passed"], verdicts
        scorable = [v for v in counted.values() if v != "blocked"]
        return bool(scorable) and all(v == "pass" for v in scorable), verdicts

    blind, readonly, order = [], [], []
    for e in picked.values():
        start = bundles[e["id"]]["snapshots"]["start"]
        ref = refs[e["id"]]
        guess = {
            **start,
            "recommendations": [{"recommendation": "ready_for_approval", "rationale": "approved"}],
        }
        blind.append(
            (
                e["id"],
                *score(
                    e,
                    [{"tool": "recommend", "args": {"decision": "ready_for_approval"}, "ok": True}],
                    guess,
                    "fail",
                ),
            )
        )
        reads = [
            {"tool": t, "args": {}, "ok": True}
            for t in ("application.read", "parties.list", "documents.list", "document.read")
        ]
        readonly.append((e["id"], *score(e, reads, start, "fail")))
        # The right writes for this case, made after the checks (control) and before them (V-07).
        parties = [
            p.get("party_id")
            for p in assertions._parties({"case_id": e["case_id"], "snapshots": {"start": start}})
        ]
        need = ref.get("request_type")
        lacking = (
            assertions.party_lacking(need, {"case_id": e["case_id"], "snapshots": {"start": start}})
            if need not in (None, "", "none")
            else set()
        )
        end = {
            **start,
            "recommendations": [
                {"recommendation": ref.get("recommendation"), "rationale": "per the evidence"}
            ],
            "information_requests": [
                {"type": need, "party_id": sorted(lacking or parties or [None])[0]}
            ]
            if need not in (None, "", "none")
            else [],
            "referrals": [{"specialty": ref["referral"]}]
            if ref.get("referral") not in (None, "", "none")
            else [],
        }
        checks = [
            {"tool": t, "args": {"party_id": p}, "ok": True}
            for p in parties
            for t in ("identity.check", "screening.check")
        ]
        head = [{"tool": t, "args": {}, "ok": True} for t in ("application.read", "documents.list")]
        rec = [{"tool": "recommend", "args": {"decision": ref.get("recommendation")}, "ok": True}]
        right, _ = score(e, head + checks + rec, end, "pass")
        wrong, _ = score(e, rec + head + checks, end, "pass")
        order.append((e["id"], right, wrong))
    return blind, readonly, order


def shortcuts(c, ws, manifest, pass_row, cases, bundles, refs):
    try:
        got = _controls(c, ws, manifest, pass_row, cases, bundles, refs)
    except GymError as exc:
        err = f"the sandbox could not run: {exc.message}"
        return [
            row(k, n, "ERROR", err)
            for k, n in (
                ("V-05", "Blind shortcut fails"),
                ("V-06", "Read-only shortcut fails"),
                ("V-07", "Ordering matters"),
            )
        ]
    if not got:
        why = "no scored case episode with a recorded start state"
        return [
            row(k, n, "INSUFFICIENT_EVIDENCE", why)
            for k, n in (
                ("V-05", "Blind shortcut fails"),
                ("V-06", "Read-only shortcut fails"),
                ("V-07", "Ordering matters"),
            )
        ]
    blind, readonly, order = got
    out = []
    for cid, name, rows_ in (
        ("V-05", "Blind shortcut fails", blind),
        ("V-06", "Read-only shortcut fails", readonly),
    ):
        passed = [r[0] for r in rows_ if r[1]]
        out.append(
            row(
                cid,
                name,
                "FAIL" if passed else "PASS",
                f"{len(passed)} of {len(rows_)} tasks pass a shortcut agent"
                if passed
                else f"the shortcut fails on all {len(rows_)} tasks",
                {"passed_by_shortcut": passed, "verdicts": {r[0]: r[2] for r in rows_}},
            )
        )
    right_ok = [r for r in order if r[1]]
    unordered = [r[0] for r in right_ok if r[2]]
    if not right_ok:
        out.append(
            row(
                "V-07",
                "Ordering matters",
                "INSUFFICIENT_EVIDENCE",
                "no task's correct-order control passes (needs the reference agent, V-04)",
                {"controls": [r[0] for r in order]},
            )
        )
    else:
        out.append(
            row(
                "V-07",
                "Ordering matters",
                "FAIL" if unordered else "PASS",
                f"{len(unordered)} task(s) still pass with the recommendation made before the checks"
                if unordered
                else f"recommending before the checks fails on all {len(right_ok)} tasks whose correct order passes",
                {"order_ignored": unordered},
            )
        )
    return out


def leakage(manifest, episodes, bundles, refs):
    import json

    leaks = []
    for e in episodes:
        b = bundles.get(e["id"])
        if not b:
            continue
        tags = [t for t in (e.get("edge_cases") or []) if t]
        alias = ((b.get("id_aliases") or {}).get("aliases")) or {}
        for step in b.get("transcript") or []:
            obs = json.dumps(step.get("observation") or {})
            for real, al in alias.items():
                obs = obs.replace(real, al)
            hit = [t for t in tags if t in obs or t.replace("_", "-") in obs]
            needs_tin = (
                "minor_without_tin" in tags
                or (refs.get(e["id"]) or {}).get("request_type") == "tin"
            )
            if '"tin": "missing"' in obs and needs_tin:
                hit.append('tin: "missing"')
            if hit:
                leaks.append(
                    {"episode": e["id"], "step": step.get("step"), "found": sorted(set(hit))}
                )
                break
    known = [x for x in leaks if x["found"] == ['tin: "missing"']]
    if leaks and len(known) == len(leaks):
        return row(
            "V-L1",
            "No answer leaks to the agent",
            "FAIL",
            f'{len(leaks)} episode(s) saw a known data leak on this environment (documents.content.tin = "missing"; fixed from @9)',
            {"episodes": leaks[:10]},
        )
    return row(
        "V-L1",
        "No answer leaks to the agent",
        "FAIL" if leaks else "PASS",
        f"{len(leaks)} episode(s) saw an edge-case label or answer"
        if leaks
        else (
            "no edge-case label in any observation"
            + (" (IDs hidden from the agent)" if manifest.get("ids_aliased") else "")
        ),
        {"episodes": leaks[:10]},
    )


def config_sanity(c, run_id, manifest):
    rows_ = c.execute(
        "SELECT block_lines FROM scoring.criterion_receipts r JOIN runs.episodes e ON e.id=r.episode_id WHERE e.run_id=%s AND block_lines IS NOT NULL",
        (run_id,),
    ).fetchall()
    judged = [
        ln
        for r in rows_
        for ln in r["block_lines"] or []
        if isinstance(ln, dict) and ln.get("judge")
    ]
    live = manifest.get("execution_mode") == "live"
    mocks = [
        ln
        for r in rows_
        for ln in r["block_lines"] or []
        if isinstance(ln, dict)
        and ln.get("kind") == "plugin"
        and ((ln.get("actual") or {}).get("judge") == "mock")
    ]
    agent_family = {m.get("provider") for m in manifest.get("models") or [] if m.get("live")}
    problems = []
    if live and mocks:
        problems.append(f"{len(mocks)} judge line(s) used the mock judge in a live run")
    scores = [
        (ln.get("actual") or {}).get("score") for ln in judged if isinstance(ln.get("actual"), dict)
    ]
    binary = [s for s in scores if s in (0, 1)]
    if scores and len(binary) == len(scores):
        problems.append("every judge score is 0 or 1: the threshold has no effect (D-037)")
    providers = {
        str((ln.get("actual") or {}).get("judge", "")).split(":")[0]
        for ln in judged
        if isinstance(ln.get("actual"), dict)
    }
    same = sorted(p for p in providers if p and p in agent_family)
    if same:
        problems.append(
            f"the judge and the agent are from the same provider family ({', '.join(same)})"
        )
    if not judged and not mocks:
        return row(
            "C-01",
            "Effective grader configuration",
            "NOT_APPLICABLE",
            "no judge line in this run's scoring",
        )
    return row(
        "C-01",
        "Effective grader configuration",
        "FAIL" if problems else "PASS",
        "; ".join(problems)
        or "judge scores vary, no mock judge in a live run, judge family differs from the agent's",
        {"judge_lines": len(judged), "mock_lines": len(mocks)},
    )


def safety_rows(c, run_id, manifest):
    from anvil.rlgym.results import report
    from anvil.rlgym.scoring import safety

    ts = manifest.get("trust_and_safety") or {}
    if not ts.get("enabled"):
        why = "Trust & Safety is off for this run"
        return [
            row(k, n, "NOT_APPLICABLE", why)
            for k, n in (
                ("S-01", "Attack placement verified"),
                ("S-02", "Every category can be graded"),
                ("S-03", "Safety judge from another family, qualified"),
                ("S-04", "Unscored never counted as resisted"),
            )
        ]
    delivered = report.delivered_as(c, manifest)
    s1 = row(
        "S-01",
        "Attack placement verified",
        "PASS" if delivered == ts.get("placement") else "FAIL",
        f"asked for {ts.get('placement')}, delivered in the {delivered}"
        + (
            ""
            if delivered == ts.get("placement")
            else " (D-040: hidden instructions were not tested)"
        ),
    )
    env = c.execute(
        "SELECT operations, schema FROM catalog.environment_versions WHERE id=%s",
        ((manifest.get("environment") or {}).get("version_id"),),
    ).fetchone()
    cats = sorted({p["category_key"] for p in ts.get("prompts") or []})
    bad = [why for cat in cats for ok, why in [safety.can_grade(cat, env)] if not ok]
    s2 = row(
        "S-02",
        "Every category can be graded",
        "FAIL" if bad else "PASS",
        "; ".join(bad)
        or f"all {len(cats)} categories have a detector that works on this environment",
    )
    s3 = row(
        "S-03",
        "Safety judge from another family, qualified",
        "NOT_APPLICABLE",
        "safety is graded by action checks only (no LLM judge in safety grading yet; E-006 layer 2)",
    )
    out = c.execute(
        """SELECT o.outcome, o.grader FROM scoring.safety_outcomes o JOIN runs.episodes e ON e.id=o.episode_id
           WHERE e.run_id=%s""",
        (run_id,),
    ).fetchall()
    unscored = sum(1 for o in out if o["outcome"] == "unscored")
    old = sum(1 for o in out if "1.0.0" in (o["grader"] or ""))
    s4 = row(
        "S-04",
        "Unscored never counted as resisted",
        "INSUFFICIENT_EVIDENCE" if unscored else ("PASS" if out else "INSUFFICIENT_EVIDENCE"),
        (
            f"{unscored} attack(s) unscored: the safety gate can't be read as passed for them"
            if unscored
            else (
                f"{len(out)} attacks graded; none unscored" if out else "no safety outcome recorded"
            )
        )
        + (f"; {old} outcome(s) graded by the old detectors (1.0.0, D-035)" if old else ""),
        {
            "outcomes": {
                k: sum(1 for o in out if o["outcome"] == k)
                for k in sorted({o["outcome"] for o in out})
            }
        },
    )
    return [s1, s2, s3, s4]


def fixture_rows():
    """The 4 regression fixtures (E-007 §3.12), run through the independent assertions; their outcomes await an SME."""
    from anvil.rlgym.catalog import fixes
    from anvil.rlgym.verification import fixtures

    v1 = {"runner": "verifier_blocks", "runner_version": 1}
    v2 = fixes.SUGGESTED["golden-kyc-blocks:next_action"]["config"]
    out = []
    for f in fixtures.FIXTURES:
        got = {a["id"]: a["outcome"] for a in fixtures.assert_fixture(f)}
        g1, g2 = fixtures.grader_next_action(f, v1), fixtures.grader_next_action(f, v2)
        party = got.get("KYC.REQUEST_PARTY")
        out.append(
            {
                "id": f["id"],
                "title": f["title"],
                "status": FIXTURE_NOTE,
                "assertions": got,
                "expected_assertion": f["expect"],
                "shows": f["shows"],
                "next_action": {"v1": g1, "v2_d041": g2},
                "v1_mismatch": party in ("PASS", "FAIL") and (g1 == "pass") != (party == "PASS"),
            }
        )
    return out


def reference_rows(c, ws, run, manifest):
    """V-04 and V-01 from the latest reference-agent run of this run's suite version (E-007 §7.2)."""
    from anvil.rlgym.verification import reference_run

    rr = reference_run.latest(c, ws, run["suite_version_id"])
    if not rr:
        why = "the reference agent hasn't been run for this suite version (Suite → Reference agent → Run)"
        return (
            row("V-04", "Reference-solvable", "INSUFFICIENT_EVIDENCE", why),
            row("V-01", "Environment replay", "INSUFFICIENT_EVIDENCE", why),
        )
    by = {(t["task_id"], t["revision"]): t for t in rr["tasks"]}
    unconfirmed, failures, missing = [], [], []
    for mt in manifest.get("tasks") or []:
        t = by.get((mt["task_id"], mt["revision"]))
        if not t:
            missing.append(f"{mt['task_id'][:8]} r{mt['revision']}")
            continue
        if not t.get("confirmed") or t["confirmed"].get("verdict") != "confirmed":
            unconfirmed.append(f"{mt['task_id'][:8]} r{mt['revision']}")
        for cs in t["cases"]:
            if cs.get("awaiting"):
                continue  # reference.v2 awaiting the SME or PM: not graded, not a failure
            for f in cs.get("failures") or []:
                failures.append(f"task {t['task_id'][:8]}: {f['reason']}")
            if not cs.get("full_marks"):
                bad = [
                    k for k, v in (cs.get("verdicts") or {}).items() if v.get("verdict") != "pass"
                ]
                failures.append(
                    f"task {t['task_id'][:8]} on {cs['case_id']}: {cs['points']} ({', '.join(bad)})"
                )
    ev = {"reference_run": rr["id"], "at": str(rr.get("created_at")), "judge": rr.get("judge")}
    if failures:
        v04 = row(
            "V-04",
            "Reference-solvable",
            "FAIL",
            "; ".join(failures[:6]),
            {**ev, "failures": failures},
        )
    elif missing:
        v04 = row(
            "V-04",
            "Reference-solvable",
            "INSUFFICIENT_EVIDENCE",
            f"the reference run doesn't cover task(s) {', '.join(missing)}: run it again",
            ev,
        )
    elif unconfirmed:
        v04 = row(
            "V-04",
            "Reference-solvable",
            "INSUFFICIENT_EVIDENCE",
            f"Not enough evidence: reference approach not confirmed ({', '.join(unconfirmed)})",
            ev,
        )
    else:
        v04 = row(
            "V-04",
            "Reference-solvable",
            "PASS",
            "the reference agent scores full marks on every task",
            ev,
        )
    replays = [cs.get("replay") for t in rr["tasks"] for cs in t["cases"] if not cs.get("awaiting")]
    if not replays or any(r is None for r in replays):
        v01 = row(
            "V-01",
            "Environment replay",
            "INSUFFICIENT_EVIDENCE",
            "the reference run had no replay",
            ev,
        )
    else:
        bad = [
            r
            for r in replays
            if not (r["observations_match"] and r["end_state_match"] and r["verdicts_match"])
        ]
        v01 = row(
            "V-01",
            "Environment replay",
            "FAIL" if bad else "PASS",
            f"{len(bad)} of {len(replays)} replays differ"
            if bad
            else f"all {len(replays)} reference episodes replayed identically on a fresh instance "
            "(observations, end state and verdicts)",
            ev,
        )
    return v04, v01


def lookup_row(latest_run, environment_version_id):
    """G-01 from the suite version's latest lookup run (verification/lookup.py)."""
    from anvil.rlgym.verification import lookup

    name = "Lookup baseline can't solve the cases"
    if not latest_run:
        if not lookup.lookup_for(environment_version_id):
            return row(
                "G-01",
                name,
                "INSUFFICIENT_EVIDENCE",
                f"no lookup for {environment_version_id} yet (it comes with the environment's lookup data)",
            )
        return row(
            "G-01",
            name,
            "INSUFFICIENT_EVIDENCE",
            "the lookup baseline hasn't been run for this suite version (Suite → Reference agent → Run lookup "
            "baseline)",
        )
    s = latest_run["summary"]
    gate = s["gate"]["threshold_percent"]
    detail = (
        f"the no-AI lookup scores {s['points_percent']:g}% of points (gate {gate:g}%), full marks on "
        f"{s['full_marks']} of {s['cases']} cases, the right decision on {s['decisions_right']}"
    )
    return row(
        "G-01",
        name,
        "PASS" if s["gate"]["passed"] else "FAIL",
        detail,
        {"lookup_run": latest_run["id"], **s},
    )


def build(c, ws, run_id, requested_by=None, profile="experiment"):
    run = c.execute(
        "SELECT * FROM runs.runs WHERE workspace_id=%s AND id=%s", (ws, run_id)
    ).fetchone()
    if not run:
        raise GymError("NOT_FOUND", "Run not found")
    m = c.execute(
        "SELECT manifest, manifest_sha256 FROM runs.run_manifests WHERE run_id=%s", (run_id,)
    ).fetchone()
    if not m:
        raise GymError(
            "CONFLICT", "The run has no manifest (refused at admission): nothing to verify"
        )
    manifest = m["manifest"]
    from anvil.rlgym.scoring import service as scoring

    pass_row = scoring.latest_pass(c, run_id)
    episodes = _episodes(c, run_id)
    bundles, refs = {}, {}
    for e in episodes:
        if not e["bundle_ref"]:
            continue
        try:
            bundles[e["id"]] = scoring.read_sealed(e)
        except (GymError, OSError):
            continue
        ref = c.execute(
            "SELECT reference FROM scoring.case_references WHERE workspace_id=%s AND environment_version_id=%s AND case_id=%s",
            (ws, manifest["environment"]["version_id"], e["case_id"]),
        ).fetchone()
        if ref:
            refs[e["id"]] = ref["reference"]
    cases = [e for e in episodes if e["kind"] == "case" and e["id"] in bundles]
    rows_ = [roster(manifest, episodes)]
    v04, v01 = reference_rows(c, ws, run, manifest)
    rows_.append(v01)
    rows_.append(isolation(cases, bundles))
    rows_.append(tool_errors(episodes, bundles))
    rows_.append(v04)
    from anvil.rlgym.verification import lookup

    rows_.append(
        lookup_row(
            lookup.latest(c, ws, run["suite_version_id"]),
            manifest["environment"]["version_id"],
        )
    )
    if pass_row:
        rows_ += shortcuts(c, ws, manifest, pass_row, cases, bundles, refs)
        rows_.append(grader_replay(c, ws, manifest, pass_row, cases, bundles, refs))
        rows_.append(independent(c, pass_row, cases, bundles, refs))
    else:
        rows_.append(
            row(
                "V-12",
                "Stateless regrading",
                "INSUFFICIENT_EVIDENCE",
                "the run has no scoring pass",
            )
        )
    for cid, name in (
        ("V-08", "Loss masking"),
        ("V-09", "Reward variance"),
        ("V-10", "Training stability"),
    ):
        rows_.append(
            row(
                cid,
                name,
                "NOT_APPLICABLE",
                "evaluation-only profile (the RL Gym doesn't train yet)",
            )
        )
    for cid, name in (
        ("V-11", "Split isolation"),
        ("V-13", "Failure attribution"),
        ("V-14", "Model discrimination"),
    ):
        rows_.append(row(cid, name, "INSUFFICIENT_EVIDENCE", "cohort checks come in phase 4"))
    rows_.append(leakage(manifest, episodes, bundles, refs))
    rows_.append(config_sanity(c, run_id, manifest))
    rows_ += safety_rows(c, run_id, manifest)
    scored = (
        c.execute(
            "SELECT score FROM scoring.episode_scores s JOIN runs.episodes e ON e.id=s.episode_id WHERE e.run_id=%s AND s.pass_id=%s AND s.score IS NOT NULL",
            (run_id, pass_row["id"]),
        ).fetchall()
        if pass_row
        else []
    )
    mismatch = any(r["id"] in ("KYC", "V-12") and r["outcome"] == "FAIL" for r in rows_)
    status = "mismatch" if mismatch else "provisional"
    report = {
        "schema": "rlgym.verification-report.v1",
        "run_id": run_id,
        "manifest_sha256": m["manifest_sha256"],
        "pass": pass_row and {"id": str(pass_row["id"]), "number": pass_row["pass"]},
        "profile": profile,
        "mode": "shadow (reports only; blocks nothing)",
        "status": status,
        "score": round(statistics.mean(float(s["score"]) for s in scored), 2) if scored else None,
        "checks": rows_,
        "fixtures": fixture_rows(),
        "header_note": "V-01 to V-14 plus S-01 to S-04, V-L1, C-01 and the KYC assertions (this specification and E-007 are the standard for now)",
    }
    rid = "vr-" + uuid.uuid4().hex[:12]
    c.execute(
        """INSERT INTO verification.reports(id,workspace_id,run_id,pass_id,profile,status,report,report_sha256,requested_by)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            rid,
            ws,
            run_id,
            pass_row and pass_row["id"],
            profile,
            status,
            Jsonb(report),
            sha(report),
            requested_by,
        ),
    )
    return {"id": rid, **report}


def latest(c, ws, run_id):
    r = c.execute(
        "SELECT * FROM verification.reports WHERE workspace_id=%s AND run_id=%s ORDER BY created_at DESC LIMIT 1",
        (ws, run_id),
    ).fetchone()
    return r and {"id": r["id"], "created_at": r["created_at"], **r["report"]}
