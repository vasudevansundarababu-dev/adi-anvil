"""Small deterministic policy templates; input must be captured evaluator evidence."""

import math
from typing import Literal

from pydantic import Field, model_validator

from anvil.praxis_contract import Model


class Rule(Model):
    kind: Literal["number_max", "number_min", "equals", "allowlist", "required", "forbidden_text"]
    field: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
    value: str | int | float | bool | list[str] | None = None

    @model_validator(mode="after")
    def types(self):
        if type(self.value) is float and not math.isfinite(self.value):
            raise ValueError("Policy values must be finite")
        if self.kind.startswith("number_") and (type(self.value) not in (int, float)):
            raise ValueError("Finite numeric threshold required")
        if self.kind.startswith("number_") and abs(self.value) > 9007199254740991:
            raise ValueError("Numeric threshold exceeds the interoperable safe range")
        if self.kind == "allowlist" and (not isinstance(self.value, list) or not self.value):
            raise ValueError("Nonempty destination allowlist required")
        if self.kind == "equals" and (self.value is None or isinstance(self.value, list)):
            raise ValueError("Scalar equality value required")
        if self.kind == "required" and self.value is not None:
            raise ValueError("Required-field rule has no comparison value")
        if self.kind == "forbidden_text" and (
            not isinstance(self.value, str) or not 1 <= len(self.value) <= 100
        ):
            raise ValueError("Bounded forbidden literal required")
        return self


def evaluate(rule: Rule, facts: dict):
    value = facts.get(rule.field)
    if value is None:
        return {"outcome": "unknown", "reason": "Required captured evidence is missing"}
    if rule.kind.startswith("number_"):
        if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
            return {"outcome": "unknown", "reason": "Captured value is not a finite number"}
        if abs(value) > 9007199254740991:
            return {
                "outcome": "unknown",
                "reason": "Captured number exceeds the interoperable safe range",
            }
        passed = value <= rule.value if rule.kind == "number_max" else value >= rule.value
    elif rule.kind == "forbidden_text":
        if not isinstance(value, str):
            return {"outcome": "unknown", "reason": "Captured text is not a string"}
        passed = rule.value not in value
    elif rule.kind == "equals":
        passed = type(value) is type(rule.value) and value == rule.value
    elif rule.kind == "allowlist":
        if not isinstance(value, str):
            return {"outcome": "unknown", "reason": "Captured destination is not text"}
        passed = value in rule.value
    else:
        passed = True
    return {"outcome": "pass" if passed else "fail", "reason": "Captured evidence compared"}


def zen_graph(rule: Rule):
    """Generate a bounded JDM graph, never accept uploaded function/loader nodes."""
    import json

    field = rule.field
    if rule.kind == "required":
        expression = f"{field} != null"
    elif rule.kind == "allowlist":
        expression = f"{field} in {json.dumps(rule.value)}"
    else:
        op = {"equals": "==", "number_max": "<=", "number_min": ">="}[rule.kind]
        expression = f"{field} {op} {json.dumps(rule.value)}"
    return {
        "nodes": [
            {"id": "input", "name": "Request", "type": "inputNode", "position": {"x": 0, "y": 0}},
            {
                "id": "rule",
                "name": "Policy rule",
                "type": "expressionNode",
                "position": {"x": 200, "y": 0},
                "content": {"expressions": [{"id": "allow", "key": "allow", "value": expression}]},
            },
            {
                "id": "output",
                "name": "Result",
                "type": "outputNode",
                "position": {"x": 400, "y": 0},
            },
        ],
        "edges": [
            {"id": "a", "sourceId": "input", "targetId": "rule", "type": "edge"},
            {"id": "b", "sourceId": "rule", "targetId": "output", "type": "edge"},
        ],
    }


def evaluate_zen(rule: Rule, facts: dict):
    """Use actual upstream ZEN; reject missing/type-invalid facts before engine coercion."""
    import json

    import zen

    preflight = evaluate(rule, facts)
    if preflight["outcome"] == "unknown":
        return preflight
    if rule.kind == "equals" and type(facts[rule.field]) is not type(rule.value):
        return preflight
    result = zen.ZenEngine().create_decision(json.dumps(zen_graph(rule))).evaluate(facts)
    allow = result.get("result", {}).get("allow")
    if type(allow) is not bool:
        raise ValueError("ZEN returned an invalid decision schema")
    return {"outcome": "pass" if allow else "fail", "reason": "GoRules ZEN decision"}


def coverage(outcomes: list[str]):
    valid = {"pass", "fail", "unknown", "not_applicable", "not_evaluated", "error"}
    if any(v not in valid for v in outcomes):
        raise ValueError("Unsupported evaluation outcome")
    counts = {v: outcomes.count(v) for v in sorted(valid)}
    decided = counts["pass"] + counts["fail"]
    return {
        "counts": counts,
        "decided": decided,
        "planned": len(outcomes),
        "percent": 100 * counts["pass"] / decided if decided else None,
    }


def evaluate_opa(rule: Rule, facts: dict, binary, *, expected_sha256):
    """Pinned local OPA with an Anvil-generated template, not an uploaded Rego module."""
    import hashlib
    import json
    import stat
    import subprocess
    import tempfile
    from pathlib import Path

    preflight = evaluate(rule, facts)
    if preflight["outcome"] == "unknown":
        return preflight
    path = Path(binary)
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or path.is_symlink()
        or info.st_mode & 0o022
        or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256
    ):
        raise ValueError("Unqualified OPA binary")
    target = "input." + rule.field
    if rule.kind == "allowlist":
        expression = f"{target} in {json.dumps(rule.value)}"
    elif rule.kind == "required":
        expression = f"{target} != null"
    else:
        op = {"equals": "==", "number_max": "<=", "number_min": ">="}[rule.kind]
        expression = f"{target} {op} {json.dumps(rule.value)}"
    module = (
        "package anvil\nimport rego.v1\ndefault allow := false\nallow if { " + expression + " }\n"
    )
    with tempfile.TemporaryDirectory(prefix="anvil-opa-") as directory:
        source = Path(directory) / "policy.rego"
        source.write_text(module)
        # No server, HTTP builtins, shell, inherited credentials, plugins or arbitrary modules.
        process = subprocess.run(
            [
                str(path),
                "eval",
                "--format=json",
                "--stdin-input",
                "--data",
                str(source),
                "data.anvil.allow",
            ],
            input=json.dumps(facts, allow_nan=False).encode(),
            capture_output=True,
            timeout=5,
            cwd=directory,
            env={"PATH": "/usr/bin:/bin", "HOME": directory, "DO_NOT_TRACK": "1"},
        )
    if process.returncode or len(process.stdout) > 100000:
        raise ValueError("OPA runtime failed")
    try:
        result = json.loads(process.stdout)["result"][0]["expressions"][0]["value"]
        if type(result) is not bool:
            raise ValueError()
    except (KeyError, IndexError, TypeError, ValueError):
        raise ValueError("OPA returned an invalid boolean decision") from None
    return {"outcome": "pass" if result else "fail", "reason": "Local OPA decision"}
