"""D-056: show the agent the environment's policy ids in S4, from Authoring's per-task policy_id_map.

Authoring's S4 names its own rule ids (for example a rule-set document id); the environment's policies collection uses
its own (KYC-01, GB-02, ...). A task entry in the export may carry:

    "policy_id_map": {
      "environment_version": "golden-kyc-openenv@12",
      "map": {"<S4 ruleId>": ["KYC-01", "KYC-02"], ...},
      "policies": {"KYC-01": {"content_sha256": "<sha256>"}, ...}   (or a list of {"policy_id", "content_sha256"})
    }

`content_sha256` is the sha256 of the policy's UTF-8 `text` (Studio's text_sha256) or the RL Gym's canonical hash of
the whole row (`common.sha`); either matches.

At reset the map is applied only if its environment version is the one being run and every policy id it names is in
that environment's policies collection with a matching hash. Otherwise S4 is left exactly as authored and the reason is
recorded. The frozen task payload is never edited: the agent's view is a copy, and the evidence keeps the original ids.
A task without a map is untouched (no record at all).
"""

import copy
import hashlib

from anvil.rlgym.common import sha


def _hashes(row):
    out = {sha(row)}
    if isinstance(row.get("text"), str):
        out.add(hashlib.sha256(row["text"].encode()).hexdigest())
    return out


def _expected(policies):
    """{policy id: content_sha256} from the dict or list form, or None if malformed."""
    if isinstance(policies, dict):
        items = policies.items()
    elif isinstance(policies, list):
        items = [
            (p.get("policy_id") or p.get("rule_id"), p) for p in policies if isinstance(p, dict)
        ]
    else:
        return None
    out = {}
    for pid, p in items:
        digest = p.get("content_sha256") if isinstance(p, dict) else None
        if not (isinstance(pid, str) and isinstance(digest, str) and digest):
            return None
        out[pid] = digest
    return out


def problem(spec, environment_version, env_policies):
    """None when the map can be applied, else why not (one sentence)."""
    if not isinstance(spec, dict):
        return "policy_id_map is not an object; S4 left as authored"
    want_env = spec.get("environment_version")
    if not isinstance(want_env, str) or not want_env:
        return "policy_id_map names no environment version; S4 left as authored"
    if want_env != environment_version:
        return f"policy_id_map is for {want_env}, but this run uses {environment_version}; S4 left as authored"
    mapping = spec.get("map")
    if (
        not isinstance(mapping, dict)
        or not mapping
        or not all(
            isinstance(v, list) and v and all(isinstance(x, str) and x for x in v)
            for v in mapping.values()
        )
    ):
        return "policy_id_map has no usable map (each rule id needs a list of policy ids); S4 left as authored"
    expected = _expected(spec.get("policies"))
    if not expected:
        return "policy_id_map gives no content_sha256 per policy; S4 left as authored"
    if not isinstance(env_policies, list):
        return (
            f"the policies of {environment_version} could not be read at reset; S4 left as authored"
        )
    rows = {r.get("rule_id") or r.get("policy_id"): r for r in env_policies if isinstance(r, dict)}
    named = sorted({x for v in mapping.values() for x in v})
    missing = [p for p in named if p not in rows]
    if missing:
        return f"{environment_version} has no policy {', '.join(missing)}; S4 left as authored"
    unhashed = [p for p in named if p not in expected]
    if unhashed:
        return (
            f"policy_id_map gives no content_sha256 for {', '.join(unhashed)}; S4 left as authored"
        )
    changed = [p for p in named if expected[p] not in _hashes(rows[p])]
    if changed:
        return (
            f"the text of {', '.join(changed)} in {environment_version} does not match the map's content_sha256; "
            "S4 left as authored"
        )
    return None


def apply(actor, spec, environment_version, env_policies):
    """(the actor payload the agent is shown, the record for the evidence). No map → (actor, None), unchanged."""
    if spec is None:
        return actor, None
    record = {
        "environment_version": environment_version,
        "map_environment_version": spec.get("environment_version")
        if isinstance(spec, dict)
        else None,
        "applied": False,
        "warning": None,
        "rules": [],
        "unmapped": [],
    }
    why = problem(spec, environment_version, env_policies)
    if why:
        record["warning"] = why
        return actor, record
    sections = (actor or {}).get("sections")
    s4 = sections.get("S4") if isinstance(sections, dict) else None
    rules = s4.get("statePolicies") if isinstance(s4, dict) else None
    if not isinstance(rules, list) or not rules:
        record["warning"] = "the task's S4 lists no policy rules; nothing to map"
        return actor, record
    shown = copy.deepcopy(actor)
    for rule in shown["sections"]["S4"]["statePolicies"]:
        if not isinstance(rule, dict):
            continue
        original = rule.get("ruleId")
        ids = spec["map"].get(original)
        if ids:
            rule["ruleId"] = ", ".join(ids)
            record["rules"].append({"original": original, "shown": list(ids)})
        else:
            record["unmapped"].append(original)
    if not record["rules"]:
        record["warning"] = "no S4 rule id is in the map; S4 left as authored"
        return actor, record
    record["applied"] = True
    return shown, record


def summarize(records):
    """Run-level counts from the per-episode records (D-056): how many episodes had the map applied, how many warned
    (with each distinct reason), and the ids the agent was shown. `records` are the sealed records; None means the
    episode's task carried no map."""
    out = {"applied": 0, "warned": 0, "warnings": [], "rules": []}
    reasons, rules = {}, {}
    for r in records:
        if not r:
            continue
        if r.get("applied"):
            out["applied"] += 1
            for rule in r.get("rules") or []:
                rules[(rule["original"], tuple(rule["shown"]))] = True
        else:
            out["warned"] += 1
            why = r.get("warning") or "not applied"
            reasons[why] = reasons.get(why, 0) + 1
    out["warnings"] = [{"reason": k, "episodes": v} for k, v in sorted(reasons.items())]
    out["rules"] = [{"original": o, "shown": list(s)} for o, s in rules]
    return out
