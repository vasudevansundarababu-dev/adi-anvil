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
        seq = int(obs.get("sequence") or t.get("sequence") or t.get("step") or 0)
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
