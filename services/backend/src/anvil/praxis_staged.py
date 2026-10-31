"""Explicit sequential-decision contract; state projection is the only consequence."""

import math
from typing import Literal

from pydantic import Field, model_validator

from anvil.praxis_contract import (
    Action,
    Constraint,
    Environment,
    Evidence,
    Identifier,
    Model,
    PraxisTask,
    Rubric,
    Text,
    grade,
)


class EvidenceV2(Evidence):
    visibility: Literal["actor", "private", "future"]
    reveal_stage_id: Identifier | None = None

    @model_validator(mode="after")
    def reveal(self):
        if (self.visibility == "future") != (self.reveal_stage_id is not None):
            raise ValueError("Only future evidence requires reveal_stage_id")
        return self


class ActionV2(Action):
    kind: Literal["submit_json"]


class EnvironmentV2(Environment):
    binding: Literal["staged-decision-v1"]
    initial_state: dict[Identifier, str | int | float | bool | None]


class StateUpdate(Model):
    id: Identifier
    key: Identifier
    from_field: Identifier


class StageV2(Model):
    id: Identifier
    instruction: Text
    evidence_ids: list[Identifier] = Field(max_length=100)
    completion: Literal["submit_output_json"]
    action_id: Identifier
    constraints: list[Constraint] = Field(max_length=50)
    rubric: Rubric
    state_updates: list[StateUpdate] = Field(max_length=50)


class PraxisTaskV2(PraxisTask):
    schema_version: Literal["praxis.anvil.task.v2"]
    environment: EnvironmentV2
    evidence: list[EvidenceV2] = Field(max_length=100)
    actions: list[ActionV2] = Field(min_length=1, max_length=50)
    stages: list[StageV2] = Field(min_length=2, max_length=12)

    @model_validator(mode="after")
    def consistent(self):
        groups = [
            self.evidence,
            self.actions,
            self.constraints,
            self.stages,
            self.deliverables,
            self.rubric.criteria,
        ]
        for stage in self.stages:
            groups.extend([stage.constraints, stage.rubric.criteria, stage.state_updates])
        ids = [item.id for group in groups for item in group]
        if len(ids) != len(set(ids)):
            raise ValueError(
                "All IDs including state updates and per-stage rules must be globally unique"
            )
        if self.provenance.review.reviewed_revision_id != self.revision_id:
            raise ValueError("Source review must bind the exact revision")
        if sum(c.weight_bps for c in self.rubric.criteria) != 10000:
            raise ValueError("Final rubric weights must total 10000")
        order = {s.id: i for i, s in enumerate(self.stages)}
        evidence = {e.id: e for e in self.evidence}
        for e in self.evidence:
            if e.visibility == "future" and order.get(e.reveal_stage_id, 0) <= 0:
                raise ValueError("Future evidence must reveal at a later declared stage")
        actions = {a.id for a in self.actions}
        for i, stage in enumerate(self.stages):
            if stage.action_id not in actions:
                raise ValueError("Stage action_id must name a declared submit_json action")
            for eid in stage.evidence_ids:
                e = evidence.get(eid)
                if (
                    not e
                    or e.visibility == "private"
                    or (e.visibility == "future" and order[e.reveal_stage_id] > i)
                ):
                    raise ValueError("Stage references unavailable or hidden evidence")
            if sum(c.weight_bps for c in stage.rubric.criteria) != 10000:
                raise ValueError("Stage rubric weights must total 10000")
            if grade(stage, stage.rubric.reference_output)["reward"] != 1:
                raise ValueError("Each stage reference must satisfy its executable bindings")
            if len({u.key for u in stage.state_updates}) != len(stage.state_updates):
                raise ValueError("State update keys must be unique within a stage")
            for update in stage.state_updates:
                value = stage.rubric.reference_output.get(update.from_field)
                if update.from_field not in stage.rubric.reference_output or not scalar(value):
                    raise ValueError(
                        "State updates require declared finite scalar reference fields"
                    )
        if any(not scalar(v) for v in self.environment.initial_state.values()):
            raise ValueError("Initial state must contain finite scalars")
        if grade(self, self.stages[-1].rubric.reference_output)["reward"] != 1:
            raise ValueError("Last stage reference must satisfy final task rubric and constraints")
        return self


def scalar(value):
    return (
        value is None
        or type(value) in (str, int, bool)
        or (type(value) is float and math.isfinite(value))
    )


def actor_view_v2(task):
    stage = task.stages[0]
    return {
        "task_id": task.task_id,
        "task_version": task.task_version,
        "title": task.title,
        "objective": task.objective,
        "evidence": [
            e.model_dump(exclude_none=True) for e in task.evidence if e.visibility == "actor"
        ],
        "constraints": [{"id": c.id, "description": c.description} for c in stage.constraints],
        "environment": task.environment.model_dump(),
        "actions": [a.model_dump() for a in task.actions],
        "stages": [
            {
                "id": stage.id,
                "instruction": stage.instruction,
                "evidence_ids": stage.evidence_ids,
                "completion": stage.completion,
                "action_id": stage.action_id,
            }
        ],
        "deliverables": [d.model_dump() for d in task.deliverables],
    }
