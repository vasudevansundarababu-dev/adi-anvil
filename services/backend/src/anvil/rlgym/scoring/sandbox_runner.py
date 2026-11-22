"""Sandboxed Python evaluator runtime (framework `python` 1.0.0). Standalone: imports nothing from Anvil.

Reads one JSON job on stdin: {"config": {...}, "evidence": {...}, "reference": {...}} and writes one JSON verdict on
stdout. It runs in an isolated interpreter (python -I) with an empty environment, CPU and time limits. The reference
(private) is visible here, in the scoring sandbox, and never to the candidate.

Verdicts: pass, partial, fail, blocked (required evidence missing).
"""

import json
import sys


def _missing(evidence, section):
    return section not in evidence or evidence[section] is None


def _tool_count(events, tool):
    return sum(
        1 for e in events if isinstance(e, dict) and e.get("tool") == tool and e.get("ok", True)
    )


def check(rule, evidence, reference):
    kind = rule.get("kind")
    out = evidence.get("final_output") or {}
    events = evidence.get("tool_events") or []
    if kind == "tool_called":
        need = (
            int(reference.get(rule["min_count_reference"], 1))
            if rule.get("min_count_reference")
            else int(rule.get("min_count", 1))
        )
        have = _tool_count(events, rule["tool"])
        return have >= need, f"{rule['tool']} called {have} of {need} times"
    if kind == "tool_not_called":
        have = _tool_count(events, rule["tool"])
        return have == 0, f"{rule['tool']} called {have} times (must be 0)"
    if kind == "output_equals":
        if rule["field"] not in out:
            return None, f"final output has no {rule['field']}"
        expected = reference.get(rule["reference"])
        return out[rule["field"]] == expected, f"{rule['field']} = {out[rule['field']]!r}"
    if kind == "output_set_equals":
        if rule["field"] not in out or not isinstance(out[rule["field"]], list):
            return None, f"final output has no list {rule['field']}"
        expected = set(map(str, reference.get(rule["reference"], [])))
        return set(
            map(str, out[rule["field"]])
        ) == expected, f"{rule['field']} = {sorted(map(str, out[rule['field']]))}"
    if kind == "output_nonempty":
        if rule["field"] not in out:
            return None, f"final output has no {rule['field']}"
        return bool(
            out[rule["field"]]
        ), f"{rule['field']} has {len(out[rule['field']] or [])} entries"
    raise ValueError(f"unknown rule kind {kind}")


def evaluate(job):
    config, evidence, reference = (
        job["config"],
        job.get("evidence") or {},
        job.get("reference") or {},
    )
    section = config.get("evidence")
    if section and _missing(evidence, section):
        return {
            "verdict": "blocked",
            "points": None,
            "detail": [f"required evidence '{section}' is missing"],
        }
    results, detail = [], []
    for rule in config.get("rules", []):
        ok, note = check(rule, evidence, reference)
        if ok is None:
            return {"verdict": "blocked", "points": None, "detail": [note]}
        results.append(ok)
        detail.append(("✓ " if ok else "✕ ") + note)
    if all(results):
        verdict = "pass"
    elif any(results) and config.get("allow_partial"):
        verdict = "partial"
    else:
        verdict = "fail"
    fraction = sum(results) / len(results) if results else 0
    return {"verdict": verdict, "points": round(fraction, 4), "detail": detail}


def _safe(job):
    try:
        return evaluate(job)
    except Exception as exc:  # a broken configuration is an evaluator defect, never a pass
        return {"verdict": "error", "points": None, "detail": [f"{type(exc).__name__}: {exc}"]}


def main():
    job = json.loads(sys.stdin.read())
    # A batch is several configurations of the same framework version over one episode's evidence; each gets its own
    # verdict, and one configuration's error never changes another's.
    if "jobs" in job:
        sys.stdout.write(json.dumps([_safe(j) for j in job["jobs"]]))
        return
    sys.stdout.write(json.dumps(_safe(job)))


if __name__ == "__main__":
    main()
