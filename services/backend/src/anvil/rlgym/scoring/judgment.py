"""G2 (KYC Judgment v1 §6, §15.2): graders as pure functions.

- `rules_applied`: the output's `rules_applied` against the rules whose conditions the case's facts trigger (from the
  whole library, the version in force at the recommend call). Exact set → pass; one rule missing or extra, or one wrong
  "governs" mark, with the decision right → partial; otherwise fail. A cited version older than the one in force is
  "stale" (after a bulletin, the new version is used).
- `expected_rules`: those rules, as of the recommend call's sequence (the episode clock is the call sequence, C3).
- `audit_faithfulness`: every `data_seen` id was returned to the agent by a successful call (anything else is invented
  evidence: critical); every `facts_learnt` value is in the cited record; every cited rule was read through policy.read
  and applies.
Precedence waits for the reference shape (RL Gym review B2). Nothing here reads the database or changes a score; a new
evaluator version wires it in.
"""

from anvil.rlgym.runs import library


def _key(r):
    return (r.get("rule_id"), int(r.get("version") or 0))


def recommend_sequence(transcript):
    """The sequence of the first successful recommend call, else one past the last call."""
    last = 0
    for t in transcript or []:
        # The runtime's call sequence (C3's episode clock) is on the observation; older entries carry step only.
        obs = t.get("observation") or {}
        # Studio's clock: only calls that reached an operation carry a sequence; calls rejected before running
        # (schema, undeclared tool, past the limit) never count. Never the transcript index.
        raw = obs.get("sequence") if obs.get("sequence") is not None else t.get("sequence")
        if raw is None:
            continue
        seq = int(raw)
        last = max(last, seq)
        if t.get("tool") == "recommend" and (t.get("observation") or {}).get("ok"):
            return seq
    return last + 1


def expected_rules(lib, case, fired, transcript, submitted_at=None):
    return library.applicable(
        lib,
        case,
        fired=fired,
        as_of_sequence=recommend_sequence(transcript),
        submitted_at=submitted_at,
    )["applies"]


def rules_applied(expected, got, governs_truth, decision_right):
    exp = {_key(e) for e in expected or []}
    have = {_key(g) for g in got or [] if isinstance(g, dict)}
    missing = sorted(exp - have)
    extra = sorted(have - exp)
    exp_ids = {r for r, _ in exp}
    stale = [{"rule_id": r, "version": n} for r, n in extra if r in exp_ids]
    governs_wrong, governs_note = [], None
    if governs_truth is None:
        governs_note = "not graded: no reference for which rule governs"
    else:
        marks = {_key(g): bool(g.get("governs")) for g in got or [] if isinstance(g, dict)}
        for t in governs_truth:
            k = _key(t)
            if k in marks and marks[k] != bool(t.get("governs")):
                governs_wrong.append(
                    {"rule_id": k[0], "version": k[1], "expected": bool(t.get("governs"))}
                )
    off = len(missing) + len(extra) + len(governs_wrong)
    verdict = "pass" if off == 0 else "partial" if off == 1 and decision_right else "fail"
    return {
        "verdict": verdict,
        "missing": [{"rule_id": r, "version": n} for r, n in missing],
        "extra": [{"rule_id": r, "version": n} for r, n in extra],
        "stale": stale,
        "governs_wrong": governs_wrong,
        **({"governs": governs_note} if governs_note else {}),
    }


def _ids(value, out):
    if isinstance(value, dict):
        for k, v in value.items():
            if (k == "id" or k.endswith("_id")) and isinstance(v, str):
                out.add(v)
            _ids(v, out)
    elif isinstance(value, list):
        for v in value:
            _ids(v, out)


def _scalars(value, out):
    if isinstance(value, dict):
        for v in value.values():
            _scalars(v, out)
    elif isinstance(value, list):
        for v in value:
            _scalars(v, out)
    elif value is not None:
        out.add(str(value))


def audit_faithfulness(trail, transcript, aliases, expected):
    """Checks the final output's audit trail against what the agent was actually given (RL Gym's sealed transcript:
    real ids; the agent writes the ids it saw, mapped back through the episode's aliases)."""
    back = {alias: real for real, alias in (aliases or {}).items()}
    seen, records, read = set(), {}, set()
    for t in transcript or []:
        obs = t.get("observation") or {}
        if not obs.get("ok"):
            continue
        recs = (obs.get("output") or {}).get("records") or []
        _ids(recs, seen)
        for r in recs:
            if not isinstance(r, dict):
                continue
            for k, v in r.items():
                if (k == "id" or k.endswith("_id")) and isinstance(v, str):
                    records.setdefault(v, r)
            if t.get("tool") == "policy.read" and r.get("rule_id"):
                read.add(_key(r))
    applies = {_key(e) for e in expected or []}
    out = {"invented": [], "fact_mismatches": [], "rules_not_read": [], "rules_not_applicable": []}
    for e in trail or []:
        step = e.get("sop_step")
        for d in e.get("data_seen") or []:
            if isinstance(d, dict):
                if _key(d) not in read:
                    out["invented"].append(
                        {"sop_step": step, "id": f"{d.get('rule_id')}@v{d.get('version')}"}
                    )
            elif back.get(d, d) not in seen:
                out["invented"].append({"sop_step": step, "id": d})
        for f in e.get("facts_learnt") or []:
            rec = records.get(back.get(f.get("evidence"), f.get("evidence")))
            vals = set()
            _scalars(rec, vals)
            if rec is None or str(f.get("value")) not in vals:
                out["fact_mismatches"].append(
                    {
                        "sop_step": step,
                        "fact": f.get("fact"),
                        "value": f.get("value"),
                        "evidence": f.get("evidence"),
                    }
                )
        for r in e.get("rules_applied") or []:
            k = _key(r)
            if k not in read:
                out["rules_not_read"].append({"sop_step": step, "rule_id": k[0], "version": k[1]})
            if k not in applies:
                out["rules_not_applicable"].append(
                    {"sop_step": step, "rule_id": k[0], "version": k[1]}
                )
    out["critical"] = bool(out["invented"])
    return out


# --- one check per verifier line (computed by the scoring service outside the sandbox, like a plug-in) -----------------


def _line(verdict, actual=None, expected=None, critical=False):
    return {"verdict": verdict, "actual": actual, "expected": expected, "critical": critical}


def _real(aliases, value):
    back = {alias: real for real, alias in (aliases or {}).items()}
    return back.get(value, value)


def evaluate(check, x):
    """One KYC Judgment check. x: {library, case, fired, transcript, aliases, final, reference (v2)}. Verdicts: pass,
    partial, fail, not_applicable (excluded from points and maximum), blocked (evidence or truth missing; never a
    pass). `critical`: invented evidence fails the task whatever its total (§15.4)."""
    ref, final = x.get("reference"), x.get("final") or {}
    if ref is None:
        return _line("blocked", expected="the case's reference answers (reference.v2)")
    if ref.get("status") == "awaiting_sme" or ref.get("awaiting_sme") is True:
        reasons = ref.get("awaiting_sme") if isinstance(ref.get("awaiting_sme"), list) else []
        return _line("not_applicable", expected={"awaiting_sme": reasons or ["awaiting the SME"]})
    fired = [
        f
        for f in x.get("fired") or []
        if (f.get("published_at_sequence") or 0) < recommend_sequence(x.get("transcript"))
    ]
    if not fired and isinstance(ref.get("reference_if_not_fired"), dict):
        # A rule-change case whose bulletin never fired before the decision: the answer without the change.
        ref = ref["reference_if_not_fired"]
    if check == "rules_applied":
        if not x.get("library") or not x.get("case"):
            return _line("blocked", expected="the pinned policy library and the case's facts")
        exp = expected_rules(x["library"], x["case"], x.get("fired"), x.get("transcript"))
        # governs comes only from the SME's outcome; null (no overlap decided yet) is not graded.
        truth = [r for r in ref.get("rules_applied") or [] if r.get("governs") is not None]
        out = rules_applied(
            exp,
            final.get("rules_applied"),
            truth or None,
            final.get("recommendation") == ref.get("recommendation"),
        )
        return _line(
            out["verdict"],
            {k: out[k] for k in ("missing", "extra", "stale", "governs_wrong")},
            [{"rule_id": e["rule_id"], "version": e["version"]} for e in exp],
        )
    if check == "rule_in_force":
        if not fired:
            return _line("not_applicable", expected="no bulletin was published in this episode")
        cited = {
            g.get("rule_id"): int(g.get("version") or 0)
            for g in final.get("rules_applied") or []
            if isinstance(g, dict)
        }
        stale = [
            {"rule_id": f["rule_id"], "cited": cited[f["rule_id"]], "in_force": f["to_version"]}
            for f in fired
            if f["rule_id"] in cited and cited[f["rule_id"]] != f["to_version"]
        ]
        considered = set(final.get("notices_considered") or [])
        missed = [
            f["notice_id"] for f in fired if f.get("notice_id") and f["notice_id"] not in considered
        ]
        ok = not stale and not missed
        return _line(
            "pass" if ok else "fail",
            {"stale": stale, "notices_missed": missed},
            {
                "in_force": {f["rule_id"]: f["to_version"] for f in fired},
                "notices": [f.get("notice_id") for f in fired],
            },
        )
    if check == "audit_faithfulness":
        trail = final.get("audit_trail")
        if not isinstance(trail, list) or not trail:
            return _line("fail", {"audit_trail": None}, "an audit trail, one entry per SOP step")
        exp = (
            expected_rules(x["library"], x["case"], x.get("fired"), x.get("transcript"))
            if x.get("library") and x.get("case")
            else []
        )
        out = audit_faithfulness(trail, x.get("transcript"), x.get("aliases"), exp)
        bad = out["invented"] or out["fact_mismatches"] or out["rules_not_read"]
        return _line(
            "fail" if bad else "pass",
            {k: v for k, v in out.items() if k != "critical" and v},
            "every id seen, every fact as recorded, every rule read",
            critical=out["critical"],
        )
    if check == "risk_rating":
        rr = ref.get("risk_rating")
        if rr is None:
            return _line("blocked", expected="the reference's risk rating")
        given = final.get("risk_rating") if isinstance(final.get("risk_rating"), dict) else None
        if not rr.get("required"):
            if given and given.get("level"):
                return _line(
                    "fail", {"risk_rating": given}, "no risk rating (not required for this account)"
                )
            return _line("not_applicable", expected="no risk rating required for this account")
        level = (given or {}).get("level")
        problems = []
        if level != rr.get("level"):
            problems.append(f"level {level!r}, expected {rr.get('level')!r}")
        if rr.get("level") == "medium" and not (
            final.get("recommendation") == "ready_for_approval"
            and final.get("officer_verification") is True
        ):
            problems.append("medium risk: ready_for_approval with the officer verification flag")
        if rr.get("level") == "high":
            referrals = {
                a.get("referral") for a in final.get("assessments") or [] if isinstance(a, dict)
            }
            if final.get("recommendation") != "specialist_review" or "edd" not in referrals:
                problems.append("high risk: an edd referral and specialist_review, no approval")
        return _line(
            "fail" if problems else "pass", {"risk_rating": given, "problems": problems}, rr
        )
    if check == "decision":
        if final.get("recommendation") != ref.get("recommendation"):
            return _line(
                "fail",
                {"recommendation": final.get("recommendation")},
                {"recommendation": ref.get("recommendation")},
            )
        got = {
            _real(x.get("aliases"), a.get("party_id")): a
            for a in final.get("assessments") or []
            if isinstance(a, dict)
        }
        off = []
        if bool(final.get("officer_verification")) != bool(ref.get("officer_verification")):
            off.append("officer_verification")
        for p in ref.get("parties") or []:
            a = got.get(p["party_id"]) or {}
            if a.get("outcome") != p.get("outcome"):
                off.append(f"{p['party_id']}: outcome")
            if set(a.get("requests") or []) != set(p.get("requests") or []):
                off.append(f"{p['party_id']}: requests")
            if (a.get("referral") or None) != (p.get("referral") or None):
                off.append(f"{p['party_id']}: referral")
        verdict = "pass" if not off else "partial" if len(off) == 1 else "fail"
        return _line(
            verdict,
            {"off": off},
            {
                "parties": ref.get("parties"),
                "officer_verification": ref.get("officer_verification"),
            },
        )
    raise ValueError(f"unknown judgment check {check}")
