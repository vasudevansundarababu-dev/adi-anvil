"""Explicit native 0-4 anchors over captured facts, never inferred from Pass/Fail.

Programs contain bounded selectors and declarative rules, not executable source.
Their known-case tests establish software behavior, not human calibration. The
private grader separately requires exact target/release/calibration authority.
"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from anvil.db import digest
from anvil.policy_rules import Rule
from anvil.policy_rules import evaluate as evaluate_rule
from anvil.schemas import Strict

VERSION = "anvil-native-ordinal-v1"
Award = Annotated[int, Field(strict=True, ge=0, le=4)]
NAME = r"^[A-Za-z][A-Za-z0-9_]{0,79}$"


class Condition(Strict):
    id: str = Field(pattern=NAME)
    kind: Literal["equals", "number_min", "number_max", "allowlist", "required", "forbidden_text"]
    field: str = Field(pattern=NAME)
    value: str | int | float | bool | list[str] | None = None
    expected_field: str | None = Field(default=None, pattern=NAME)

    @model_validator(mode="after")
    def comparison(self):
        if self.expected_field is not None:
            if self.value is not None or self.kind not in {"equals", "number_min", "number_max"}:
                raise ValueError("A captured comparison field replaces a scalar comparison value")
        else:
            Rule.model_validate(self.model_dump(exclude={"id", "expected_field"}))
        return self


class Anchor(Strict):
    award: Award
    description: str = Field(min_length=1, max_length=1000)
    conditions: list[Condition] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique(self):
        if len({item.id for item in self.conditions}) != len(self.conditions):
            raise ValueError("Distinct condition IDs required within an anchor")
        return self


class Program(Strict):
    schema_version: Literal["anvil.native-ordinal-program.v1"]
    selectors: dict[str, str] = Field(min_length=1, max_length=80)
    anchors: list[Anchor] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def complete(self):
        import re

        if {anchor.award for anchor in self.anchors} != set(range(5)):
            raise ValueError("Explicit distinct native 0, 1, 2, 3 and 4 anchors required")
        for name, pointer in self.selectors.items():
            if not re.fullmatch(NAME, name) or (
                not isinstance(pointer, str)
                or not pointer.startswith("/")
                or len(pointer) > 500
                or len(pointer.split("/")) > 17
                or any(re.search(r"~(?![01])", part) for part in pointer.split("/")[1:])
            ):
                raise ValueError("Bounded JSON pointers and named fact selectors required")
        if any(
            condition.field not in self.selectors
            or (
                condition.expected_field is not None
                and condition.expected_field not in self.selectors
            )
            for anchor in self.anchors
            for condition in anchor.conditions
        ):
            raise ValueError("Every anchor operand needs an explicit fact selector")
        if len(self.model_dump_json().encode()) > 49152:
            raise ValueError("Native ordinal program exceeds its bound")
        return self


def selected(value, pointer):
    for part in pointer.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif (
            isinstance(value, list)
            and part.isascii()
            and part.isdecimal()
            and (part == "0" or not part.startswith("0"))
            and int(part) < len(value)
        ):
            value = value[int(part)]
        else:
            return None
    return value


def bounded_facts(facts):
    """Bound work and bytes before materializing a repeated/deep JSON projection."""
    import json
    import math

    remaining, visited = 1048576, 0
    pending = [(facts, 0)]
    while pending:
        value, depth = pending.pop()
        visited += 1
        if depth > 16 or visited > 20000:
            raise ValueError("Native ordinal evidence nesting or work bound exceeded")
        if type(value) is dict:
            if len(value) > 20000:
                raise ValueError("Native ordinal evidence object bound exceeded")
            if visited + len(pending) + len(value) > 20000:
                raise ValueError("Native ordinal aggregate work bound exceeded before enqueue")
            remaining -= 2 + 2 * len(value)
            if remaining < 0:
                raise ValueError("Native ordinal private execution byte bound exceeded")
            for key, child in value.items():
                if not isinstance(key, str) or len(key) > remaining:
                    raise ValueError("Native ordinal evidence key bound exceeded")
                remaining -= len(json.dumps(key, ensure_ascii=False).encode())
                if remaining < 0:
                    raise ValueError("Native ordinal private execution byte bound exceeded")
                pending.append((child, depth + 1))
        elif type(value) is list:
            if len(value) > 20000:
                raise ValueError("Native ordinal evidence array bound exceeded")
            if visited + len(pending) + len(value) > 20000:
                raise ValueError("Native ordinal aggregate work bound exceeded before enqueue")
            remaining -= 2 + len(value)
            if remaining < 0:
                raise ValueError("Native ordinal private execution byte bound exceeded")
            pending.extend((child, depth + 1) for child in value)
        elif type(value) in {str, int, float, bool, type(None)}:
            if isinstance(value, str) and len(value) > remaining:
                raise ValueError("Native ordinal evidence text bound exceeded")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Finite native ordinal facts required")
            remaining -= len(json.dumps(value, allow_nan=False, ensure_ascii=False).encode())
        else:
            raise ValueError("Native ordinal facts must contain only JSON values")
        if remaining < 0:
            raise ValueError("Native ordinal private execution byte bound exceeded")


def evaluate(program, observation):
    """Exactly one fully determined anchor; no nearest-score or max-score rule."""
    program = Program.model_validate(program)
    if not isinstance(observation, dict):
        raise ValueError("Captured evidence object required")
    facts = {name: selected(observation, pointer) for name, pointer in program.selectors.items()}
    bounded_facts(facts)
    matches, findings, unknown = [], [], False
    for anchor in program.anchors:
        outcomes = []
        for condition in anchor.conditions:
            value = condition.value
            if condition.expected_field is not None:
                value = facts[condition.expected_field]
                if value is None:
                    outcomes.append("unknown")
                    findings.append(
                        {"anchor": anchor.award, "condition": condition.id, "outcome": "unknown"}
                    )
                    continue
            try:
                rule = Rule(kind=condition.kind, field=condition.field, value=value)
                outcome = evaluate_rule(rule, facts)["outcome"]
            except (ValueError, TypeError):
                outcome = "unknown"
            outcomes.append(outcome)
            findings.append({"anchor": anchor.award, "condition": condition.id, "outcome": outcome})
        if all(outcome == "pass" for outcome in outcomes):
            matches.append(anchor.award)
        # A failed conjunct rules out this anchor even when another is absent.
        elif "fail" not in outcomes and "unknown" in outcomes:
            unknown = True
    award = matches[0] if len(matches) == 1 and not unknown else None
    return {
        "evaluator": VERSION,
        "program_sha256": digest(program.model_dump()),
        "input_projection_sha256": digest(facts),
        "status": "scored" if award is not None else "unscored",
        "award": award,
        "reason": "exact_native_anchor"
        if award is not None
        else "ambiguous_native_anchors"
        if len(matches) > 1
        else "missing_or_invalid_anchor_evidence"
        if unknown
        else "no_native_anchor_matched",
        "anchor_findings": findings,
        "provider_calls": 0,
    }
