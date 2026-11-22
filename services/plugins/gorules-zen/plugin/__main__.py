"""GoRules ZEN verifier plug-in: adi.verifier-job.v1 on stdin → adi.verifier-result.v1 on stdout.

Modes (per block, settings validated by the RL Gym against the manifest's settings_schema):
- oracle: ZEN computes the decision from the facts (`inputs`: rule input name → evidence path) and the plug-in compares
  the rule outputs with what the agent did (`compare`: rule_output, agent_path, op).
- rule_check: ZEN evaluates facts taken from the agent's state and output and returns `pass` (bool) or `rules`
  ([{rule, pass}]); any false fails the block.
The rules (JDM) arrive in the job's `files`, keyed by SHA-256; the block names it in `settings.rules.sha256`.
Exit 0: results. Exit 2: bad job. No network, no writes outside the result.
"""

import json
import sys

import zen

MISSING = object()


def _tokens(path):
    out = []
    for part in path.split("."):
        name, _, rest = part.partition("[")
        if name:
            out.append(name)
        while rest:
            idx, _, rest = rest.partition("]")
            out.append("*" if idx == "*" else int(idx))
            rest = rest[1:] if rest.startswith("[") else rest
    return out


def resolve(root, path):
    """The shared evidence path syntax: a.b[0].c, a[*].b (a list)."""
    values, many = [root], False
    for tok in _tokens(path):
        nxt = []
        for v in values:
            if tok == "*":
                if not isinstance(v, list):
                    return MISSING
                nxt.extend(v)
                many = True
            elif isinstance(tok, int):
                if not isinstance(v, list) or tok >= len(v):
                    if many:
                        continue
                    return MISSING
                nxt.append(v[tok])
            else:
                if not isinstance(v, dict) or tok not in v:
                    if many:
                        continue
                    return MISSING
                nxt.append(v[tok])
        values = nxt
    return values if many else values[0]


def _compare(op, expected, actual):
    if op == "in":
        return actual in (expected if isinstance(expected, list) else [expected])
    if op == "contains":
        return expected in actual if isinstance(actual, (list, str)) else False
    return actual == expected


def _line(block, verdict, expected=None, actual=None, detail=""):
    return {
        "block_id": block["id"],
        "verdict": verdict,
        "points": None,
        "expected": expected,
        "actual": actual,
        "on_fail": block.get("on_fail") if verdict == "fail" else None,
        "detail": detail,
    }


def run_block(engine, job, root, block):
    s = block.get("settings") or {}
    rules = (job.get("files") or {}).get((s.get("rules") or {}).get("sha256"))
    if rules is None:
        return _line(block, "blocked", actual={"missing": "rules file"}, detail="rules file not in the job")
    facts = {}
    for name, path in (s.get("inputs") or {}).items():
        value = resolve(root, path)
        if value is MISSING:
            return _line(block, "blocked", actual={"missing": path}, detail=f"evidence {path} is missing")
        facts[name] = value
    decision = engine.create_decision(json.dumps(rules))
    result = decision.evaluate(facts).get("result") or {}
    if s.get("mode") == "rule_check":
        checks = result.get("rules")
        if checks is None:
            checks = [{"rule": "rules", "pass": result.get("pass")}]
        failed = [c.get("rule") for c in checks if c.get("pass") is not True]
        verdict = "pass" if not failed else "fail"
        return _line(block, verdict, expected="every rule passes", actual={"failed_rules": failed}, detail=json.dumps(result)[:300])
    for cmp in s.get("compare") or []:
        expected = resolve(result, cmp["rule_output"])
        if expected is MISSING:
            return _line(block, "blocked", actual={"missing": f"rule output {cmp['rule_output']}"}, detail="no rule matched")
        actual = resolve(root, cmp["agent_path"])
        if actual is MISSING:
            return _line(block, "blocked", expected=expected, actual={"missing": cmp["agent_path"]}, detail=f"evidence {cmp['agent_path']} is missing")
        if not _compare(cmp.get("op", "equals"), expected, actual):
            return _line(block, "fail", expected=expected, actual=actual, detail=f"rules say {cmp['rule_output']} = {expected!r}")
    return _line(block, "pass", expected=result, actual="matches", detail="every compared output matches the rules")


def main():
    try:
        job = json.loads(sys.stdin.read())
        assert job.get("schema") == "adi.verifier-job.v1" and isinstance(job.get("blocks"), list)
    except Exception as exc:  # a bad job: exit 2, the RL Gym marks the blocks blocked
        sys.stderr.write(f"bad job: {type(exc).__name__}")
        return 2
    evidence = job.get("evidence") or {}
    root = {**evidence, "case_reference": job.get("case_reference"), "slots": job.get("slots")}
    engine = zen.ZenEngine()
    results = []
    for block in job["blocks"]:
        try:
            results.append(run_block(engine, job, root, block))
        except Exception as exc:  # a broken rules file or setting is the block's problem, never a pass
            results.append(_line(block, "blocked", actual={"error": type(exc).__name__}, detail=str(exc)[:300]))
    json.dump(
        {"schema": "adi.verifier-result.v1", "results": results, "plugin": {"id": "gorules-zen", "version": "1.0.0"}},
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
