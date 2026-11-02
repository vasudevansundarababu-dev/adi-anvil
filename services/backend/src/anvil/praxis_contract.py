"""Versioned Praxis handoff. Descriptive text is never executable code."""

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")]
Text = Annotated[str, Field(min_length=1, max_length=20000)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Binding(Model):
    kind: Literal["json_equals", "json_number_min", "json_number_max"]
    field: Identifier
    value: str | int | float | bool

    @model_validator(mode="after")
    def numeric(self):
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("Binding value must be finite")
        if self.kind != "json_equals" and type(self.value) not in (int, float):
            raise ValueError("Numeric bindings require a number")
        return self


class Evidence(Model):
    id: Identifier
    visibility: Literal["actor", "private"]
    content: Text


class Constraint(Model):
    id: Identifier
    description: Text
    hard_failure: bool
    binding: Binding


class Environment(Model):
    binding: Literal["structured-decision-v1"]
    initial_state: dict


class Action(Model):
    id: Identifier
    description: Text


class Stage(Model):
    id: Identifier
    instruction: Text
    evidence_ids: list[Identifier] = Field(max_length=100)
    completion: Text


class Deliverable(Model):
    id: Identifier
    path: Literal["output.json"]
    description: Text


class Criterion(Model):
    id: Identifier
    description: Text
    weight_bps: int = Field(ge=1, le=10000)
    binding: Binding


class Rubric(Model):
    criteria: list[Criterion] = Field(min_length=1, max_length=50)
    reference_output: dict


class Rights(Model):
    status: Literal["declared"]
    basis: Text


class Review(Model):
    status: Literal["draft", "approved"]
    reviewer_ref: Text
    reviewed_revision_id: Identifier


class Provenance(Model):
    classification: Literal["synthetic"]
    source: Text
    rights: Rights
    review: Review


class PraxisTask(Model):
    schema_version: Literal["praxis.anvil.task.v1"]
    task_id: Identifier
    task_version: Identifier
    revision_id: Identifier
    title: Text
    objective: Text
    evidence: list[Evidence] = Field(max_length=100)
    constraints: list[Constraint] = Field(max_length=50)
    environment: Environment
    actions: list[Action] = Field(min_length=1, max_length=50)
    stages: list[Stage] = Field(min_length=1, max_length=1)
    deliverables: list[Deliverable] = Field(min_length=1, max_length=1)
    rubric: Rubric
    provenance: Provenance

    @model_validator(mode="after")
    def consistent(self):
        groups = [
            self.evidence,
            self.constraints,
            self.actions,
            self.stages,
            self.deliverables,
            self.rubric.criteria,
        ]
        ids = [item.id for group in groups for item in group]
        if len(ids) != len(set(ids)):
            raise ValueError(
                "All evidence/rule/action/stage/deliverable/criterion IDs must be unique"
            )
        if sum(c.weight_bps for c in self.rubric.criteria) != 10000:
            raise ValueError("Rubric weights must total 10000")
        actor_ids = {e.id for e in self.evidence if e.visibility == "actor"}
        if any(set(s.evidence_ids) - actor_ids for s in self.stages):
            raise ValueError("Stage evidence must exist and be actor-visible")
        if self.provenance.review.reviewed_revision_id != self.revision_id:
            raise ValueError("Source review must bind the exact revision")
        bounds = {}
        for rule in [*self.constraints, *self.rubric.criteria]:
            b = rule.binding
            bounds.setdefault(b.field, []).append(b)
        for rules in bounds.values():
            low = max((b.value for b in rules if b.kind == "json_number_min"), default=-math.inf)
            high = min((b.value for b in rules if b.kind == "json_number_max"), default=math.inf)
            equals = [b.value for b in rules if b.kind == "json_equals"]
            if low > high or any(v != equals[0] for v in equals):
                raise ValueError("Contradictory executable bindings")
            if equals and (low != -math.inf or high != math.inf):
                if type(equals[0]) not in (int, float) or not low <= equals[0] <= high:
                    raise ValueError("Equality contradicts numeric binding")
        return self


def matches(binding, output):
    if binding.field not in output:
        return False
    value = output[binding.field]
    if binding.kind == "json_equals":
        return type(value) is type(binding.value) and value == binding.value
    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        return False
    return value >= binding.value if binding.kind == "json_number_min" else value <= binding.value


def grade(task: PraxisTask, output: dict):
    """Reward v1 zeros hard failures; criterion evidence is retained independently."""
    criteria = {
        c.id: {"passed": matches(c.binding, output), "weight_bps": c.weight_bps}
        for c in task.rubric.criteria
    }
    failures = [c.id for c in task.constraints if not matches(c.binding, output)]
    hard = [c.id for c in task.constraints if c.hard_failure and c.id in failures]
    diagnostic = sum(c["weight_bps"] for c in criteria.values() if c["passed"]) / 10000
    return {
        "reward_version": "hard-failure-zero-v1",
        "reward": 0.0 if hard else diagnostic,
        "diagnostic_score": diagnostic,
        "criteria": criteria,
        "constraint_failures": failures,
        "hard_failures": hard,
    }


def actor_view(task: PraxisTask):
    if task.schema_version == "praxis.anvil.task.v3":
        from anvil.praxis_executable import actor_view as executable_actor

        return executable_actor(task)
    if task.schema_version == "praxis.anvil.task.v2":
        from anvil.praxis_staged import actor_view_v2

        return actor_view_v2(task)
    return {
        "task_id": task.task_id,
        "task_version": task.task_version,
        "title": task.title,
        "objective": task.objective,
        "evidence": [e.model_dump() for e in task.evidence if e.visibility == "actor"],
        "constraints": [{"id": c.id, "description": c.description} for c in task.constraints],
        "environment": task.environment.model_dump(),
        "actions": [a.model_dump() for a in task.actions],
        "stages": [s.model_dump() for s in task.stages],
        "deliverables": [d.model_dump() for d in task.deliverables],
    }
