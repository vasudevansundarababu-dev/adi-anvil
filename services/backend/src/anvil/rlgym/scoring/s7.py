"""D-036 (E-007 §7.1, owner decision 24 Nov 2026): episodes are scored with the task's published S7, not the RL Gym's
own scale.

S7 (in the task's private part, as published; no template change) carries:
- `criteria[]`: each criterion's `weight` and whether it is `critical`;
- `scoringRule`: the anchors (e.g. "5 for pass, 2 for partial, 0 for fail"), the maximum and the pass threshold
  (e.g. "Maximum 25 points. The pass threshold is 22.5"), written by the SME.

`profile()` reads those into numbers once, at admission; the manifest freezes the profile per task (with the rule
text's hash, never the private text). A rule it cannot read is refused at admission: there is no silent fallback to the
RL Gym's old scale. Scoring then gives each criterion the anchor of its verdict (pass, partial, fail), passes the task
only at or above the threshold, and a fail on a critical criterion fails the task whatever the total.
"""

import hashlib
import re

NUMBER = r"(\d+(?:\.\d+)?)"


def _num(x):
    v = float(x)
    return int(v) if v.is_integer() else v


def profile(s7):
    """→ (profile, None) or (None, reason)."""
    if not isinstance(s7, dict):
        return None, "the task has no S7 section"
    criteria = [c for c in s7.get("criteria") or [] if isinstance(c, dict) and c.get("id")]
    if not criteria:
        return None, "S7 lists no criteria"
    rule = s7.get("scoringRule") or ""
    if not isinstance(rule, str) or not rule.strip():
        return None, "S7 has no scoring rule"
    text = rule.lower()
    anchors = [_num(x) for x in re.findall(NUMBER + r"\s*(?:points?\s*)?for\b", text)]
    top = re.search(r"\bmax(?:imum)?\b[^0-9]{0,12}" + NUMBER, text)
    threshold = re.search(r"(?:threshold[^0-9]{0,12}|at least\s*)" + NUMBER, text)
    if len(anchors) < 3:
        return None, f"S7 scoring rule: expected pass/partial/fail points, found {anchors}"
    anchors = anchors[:3]
    if not (anchors[0] > anchors[1] > anchors[2] >= 0):
        return None, f"S7 scoring rule: points {anchors} are not pass > partial > fail"
    if not top or not threshold:
        return None, "S7 scoring rule: no maximum or no pass threshold"
    weights = {c["id"]: _num(c.get("weight") or 0) for c in criteria}
    top_v, threshold_v = _num(top.group(1)), _num(threshold.group(1))
    if any(w != anchors[0] for w in weights.values()):
        return None, (
            f"S7: a criterion's weight differs from the pass points {anchors[0]} "
            f"({', '.join(f'{k} {v}' for k, v in weights.items())})"
        )
    if sum(weights.values()) != top_v:
        return None, f"S7: the weights add up to {sum(weights.values())}, not the maximum {top_v}"
    if not 0 < threshold_v <= top_v:
        return None, f"S7: pass threshold {threshold_v} is outside 0–{top_v}"
    return {
        "source": "S7",
        "anchors": {"pass": anchors[0], "partial": anchors[1], "fail": anchors[2]},
        "max_points": top_v,
        "threshold_points": threshold_v,
        "weights": weights,
        "critical": sorted(c["id"] for c in criteria if c.get("critical") is True),
        "rule_sha256": hashlib.sha256(rule.encode()).hexdigest(),
    }, None


def fraction(prof, verdict):
    """The share of a criterion's weight a verdict earns: pass 1, partial e.g. 2/5, fail 0."""
    a = prof["anchors"]
    return {"pass": 1.0, "partial": a["partial"] / a["pass"], "fail": a["fail"] / a["pass"]}.get(
        verdict
    )


def outcome(prof, verdicts, weights):
    """verdicts: {criterion: verdict} of the criteria that count (scorable or blocked; clause-excluded criteria are not
    passed in). → {"points", "max_points", "threshold_points", "passed", "critical_failed"}. A blocked criterion earns
    0 for the pass decision (its evidence is missing), and the threshold is the same share of what counts."""
    counted = {k: v for k, v in verdicts.items()}
    max_points = sum(float(weights.get(k, prof["weights"].get(k, 0))) for k in counted)
    points = sum(
        float(weights.get(k, prof["weights"].get(k, 0))) * (fraction(prof, v) or 0.0)
        for k, v in counted.items()
    )
    share = prof["threshold_points"] / prof["max_points"]
    critical_failed = sorted(k for k, v in counted.items() if v == "fail" and k in prof["critical"])
    return {
        "points": round(points, 4),
        "max_points": round(max_points, 4),
        "threshold_points": round(share * max_points, 4),
        "passed": bool(max_points) and points >= share * max_points - 1e-9 and not critical_failed,
        "critical_failed": critical_failed,
    }
