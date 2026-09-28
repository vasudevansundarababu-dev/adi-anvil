from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Objective(Strict):
    title: str = Field(min_length=3, max_length=200)
    origin: Literal["adi_initiated", "customer_requested"]
    entry_type: Literal["capability", "benchmark"]
    hypothesis: str = Field(min_length=10, max_length=5000)
    business_context: str = Field(min_length=3, max_length=5000)
    measurement_plan: str = Field(min_length=20, max_length=10000)
    researcher_id: UUID
    advisor_id: UUID
    product_owner_id: UUID


class Criterion(Strict):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,30}$")
    label: str = Field(min_length=1)
    weight_bps: int = Field(ge=1, le=10000)
    anchors: dict[str, str]

    @model_validator(mode="after")
    def anchors_complete(self):
        if set(self.anchors) != set("01234") or any(not x.strip() for x in self.anchors.values()):
            raise ValueError("All five anchors required")
        return self


class Rubric(Strict):
    title: str
    criteria: list[Criterion] = Field(min_length=1, max_length=30)
    threshold: float = Field(ge=0, le=100)
    critical_rules: list[str]
    calibration: dict[str, str]
    reviewer_id: UUID
    advisor_id: UUID
    origin: Literal["original_synthetic_fixture"]

    @model_validator(mode="after")
    def valid_weights(self):
        if sum(c.weight_bps for c in self.criteria) != 10000:
            raise ValueError("Weights must total 10000")
        if len(set(c.id for c in self.criteria)) != len(self.criteria):
            raise ValueError("Duplicate criteria")
        if set(self.calibration) != {
            "clear_pass",
            "clear_fail",
            "valid_alternative",
            "critical_error",
            "ambiguous_reference",
        }:
            raise ValueError("All calibration categories required")
        return self


class Task(Strict):
    title: str
    external_case_id: str
    source_revision_id: UUID
    rubric_revision_id: UUID
    actor_artifact_ids: list[UUID] = Field(min_length=2)
    reference_artifact_ids: list[UUID] = Field(min_length=1)
    family_id: str
    capabilities: list[str] = Field(min_length=1)
    mode: Literal["static", "interactive", "tool_enabled"]
    split: Literal["development", "calibration", "protected_test"]
    reviewer_id: UUID
    advisor_id: UUID
    origin: Literal["original_synthetic_fixture"]


class Suite(Strict):
    title: str = Field(min_length=3)
    objective_revision_id: UUID
    task_revision_ids: list[UUID] = Field(min_length=1, max_length=200)
    selection_method: str = Field(min_length=10)
    exposure_note: str = Field(min_length=10)
    advisor_id: UUID
    planned_source_count: int = Field(default=200, ge=1)


class Protocol(Strict):
    title: str = Field(min_length=3)
    objective_revision_id: UUID
    suite_revision_id: UUID
    candidates: list[Literal["fixture-correct", "fixture-constraint-blind"]] = Field(
        min_length=1, max_length=2
    )
    repetitions: Literal[1] = 1
    reviewer_ids: list[UUID] = Field(min_length=2, max_length=2)
    adjudicator_id: UUID
    advisor_id: UUID
    max_output_tokens: int = Field(default=4096, ge=1, le=8192)
    episode_timeout_seconds: int = Field(default=60, ge=1, le=600)
    comparison_policy: str = Field(min_length=20)
    pass_policy: str = Field(min_length=10)
    mode: Literal["fixture"] = "fixture"


class Decision(Strict):
    purpose: Literal[
        "research",
        "advisor",
        "scope",
        "content",
        "calibration",
        "technical",
        "domain",
        "audience",
        "release",
    ]
    decision: Literal["approve", "reject", "changes_requested"]
    rationale: str = Field(min_length=10, max_length=5000)


class FixtureImport(Strict):
    case_ids: list[Literal["MKT-001", "FIN-001", "STR-001"]] = Field(min_length=1, max_length=3)
    reviewer_id: UUID
    advisor_id: UUID


class Rights(Strict):
    operation: Literal["managed_evaluation", "report_sharing"]
    destination: Literal["local_fixture", "internal_fixture"]
    status: Literal["approved", "revoked"]
    evidence: str = Field(min_length=20, max_length=5000)


class Assessment(Strict):
    scores: dict[str, int]
    critical: list[str]
    evidence: dict[str, str]
    rationale: str = Field(min_length=10, max_length=5000)


class Finding(Strict):
    title: str
    episode_id: UUID
    observation: str = Field(min_length=10)
    hypothesis: str | None = None
    alternatives: list[str]
    confidence: Literal["low", "medium", "high", "unknown"]
    criterion: str
    output_quote: str = Field(min_length=3)
    capability: str
    advisor_id: UUID


class Report(Strict):
    title: str
    run_id: UUID
    finding_revision_ids: list[UUID]
    advisor_id: UUID
    reviewer_id: UUID
    product_owner_id: UUID
    audience: Literal["internal_fixture"] = "internal_fixture"


SCHEMAS = {
    "objective": Objective,
    "rubric": Rubric,
    "task": Task,
    "suite": Suite,
    "protocol": Protocol,
    "finding": Finding,
    "report": Report,
}
