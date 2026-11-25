"""KYC Judgment v1 (C1 policy-library.v1, C2 registry-case.v2, C3 scenario-event.v1): which rules apply to a case.

From the PM-approved conditions (§13: computed, never stated) over the case's facts:
- the version in force: the latest `from_date` version on or before the case's submission date; a `scenario_only`
  version only once a C3 event published it before the decision's call sequence (the episode clock is the sequence);
- a rule with `subject: party` is evaluated once per party over that party's facts plus the case's facts and applies
  when it applies to any party (its party ids are listed); `subject: case` once, over case facts;
- derived facts (`us_person`) are computed per party from the definition in force, never read from case data;
- a version whose `effect` is `withdrawn` applies nothing; a condition of null always applies;
- a fact the condition needs and the case lacks leaves the rule Unresolved, never guessed.
Pure: no database, no Studio call. The library and the case come from the scorer-audience registry (RL Gym review B1).
"""

import hashlib

from anvil.rlgym.runs import clauses


def text_sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_problems(lib):
    """Versions whose text_sha256 isn't the SHA-256 of their text exactly as served (C1 rule identity)."""
    return [
        f"{r['rule_id']} v{v['version']}"
        for r in lib.get("rules") or []
        for v in r.get("versions") or []
        if text_sha(v.get("text") or "") != v.get("text_sha256")
    ]


def _rule(lib, rule_id):
    return next((r for r in lib.get("rules") or [] if r.get("rule_id") == rule_id), None)


def in_force(lib, rule_id, case, fired=None, as_of_sequence=None, submitted_at=None):
    rule = _rule(lib, rule_id)
    if not rule:
        return None
    day = str(submitted_at or case.get("submitted_at") or "")[:10]
    current = None
    for v in rule.get("versions") or []:
        eff = v.get("effective") or {}
        if eff.get("mode") == "from_date" and (not day or str(eff.get("from"))[:10] <= day):
            current = v
    for f in sorted(fired or [], key=lambda x: x.get("published_at_sequence") or 0):
        if f.get("rule_id") != rule_id:
            continue
        if as_of_sequence is not None and (f.get("published_at_sequence") or 0) >= as_of_sequence:
            continue
        current = next(
            (v for v in rule.get("versions") or [] if v.get("version") == f.get("to_version")),
            current,
        )
    return current


def _derived(lib, facts, case, fired, as_of_sequence, submitted_at):
    out = {}
    for d in lib.get("derived_facts") or []:
        definition = d.get("definition")
        by = d.get("defined_by") or {}
        if by.get("rule_id"):
            v = in_force(lib, by["rule_id"], case, fired, as_of_sequence, submitted_at)
            if v and v.get("effect") == "withdrawn":
                continue
        value, _ = clauses.evaluate(definition, facts)
        out[d["id"]] = value
    return out


def applicable(lib, case, fired=None, as_of_sequence=None, submitted_at=None):
    """{"applies": [{rule_id, version, text_sha256, subject, party_ids}], "unresolved": [{rule_id, version,
    party_id, missing}]}."""
    case_facts = dict(case.get("facts") or {})
    parties = [
        {"party_id": p.get("party_id"), "facts": {**case_facts, **(p.get("facts") or {})}}
        for p in case.get("parties") or []
    ]
    for p in parties:
        p["facts"].update(
            {
                k: v
                for k, v in _derived(
                    lib, p["facts"], case, fired, as_of_sequence, submitted_at
                ).items()
                if v is not None
            }
        )
    applies, unresolved = [], []
    for rule in lib.get("rules") or []:
        v = in_force(lib, rule["rule_id"], case, fired, as_of_sequence, submitted_at)
        if not v or v.get("effect") == "withdrawn":
            continue
        cond = v.get("condition")
        entry = {
            "rule_id": rule["rule_id"],
            "version": v["version"],
            "text_sha256": v.get("text_sha256"),
            "subject": rule.get("subject", "case"),
            "party_ids": [],
        }
        if rule.get("subject") == "party" and parties:
            hit = False
            for p in parties:
                ok, trace = clauses.evaluate(cond, p["facts"])
                if ok:
                    hit = True
                    entry["party_ids"].append(p["party_id"])
                elif ok is None:
                    unresolved.append(
                        {
                            "rule_id": rule["rule_id"],
                            "version": v["version"],
                            "party_id": p["party_id"],
                            "missing": trace["missing"],
                        }
                    )
            if hit:
                applies.append(entry)
        else:
            ok, trace = clauses.evaluate(cond, case_facts)
            if ok:
                applies.append(entry)
            elif ok is None:
                unresolved.append(
                    {
                        "rule_id": rule["rule_id"],
                        "version": v["version"],
                        "party_id": None,
                        "missing": trace["missing"],
                    }
                )
    return {"applies": applies, "unresolved": unresolved}
