from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Withdrawal(Strict):
    reason: str = Field(min_length=10, max_length=2000)


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
    weight_bps: int = Field(ge=1, le=10000, strict=True)
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
        if any(not value.strip() for value in self.calibration.values()):
            raise ValueError("Calibration examples must not be empty")
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

    @model_validator(mode="after")
    def separated_unique_inputs(self):
        if len(set(self.actor_artifact_ids)) != len(self.actor_artifact_ids) or len(
            set(self.reference_artifact_ids)
        ) != len(self.reference_artifact_ids):
            raise ValueError("Input artifact IDs must be unique")
        if set(self.actor_artifact_ids) & set(self.reference_artifact_ids):
            raise ValueError("Actor and hidden-reference artifacts must remain separate")
        return self


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
    candidates: list[
        Literal["fixture-correct", "fixture-constraint-blind", "external-reported"]
    ] = Field(min_length=1, max_length=2)
    repetitions: Literal[1] = 1
    reviewer_ids: list[UUID] = Field(min_length=2, max_length=2)
    adjudicator_id: UUID
    advisor_id: UUID
    max_output_tokens: int = Field(default=4096, ge=1, le=8192)
    episode_timeout_seconds: int = Field(default=60, ge=1, le=600)
    comparison_policy: str = Field(min_length=20)
    pass_policy: str = Field(min_length=10)
    mode: Literal["fixture", "external_result_import_v1"] = "fixture"

    @model_validator(mode="after")
    def candidate_mode(self):
        if self.mode == "external_result_import_v1":
            if self.candidates != ["external-reported"]:
                raise ValueError("External imports bind one reported candidate descriptor")
        elif "external-reported" in self.candidates:
            raise ValueError("External candidate cannot be dispatched as a fixture")
        return self


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
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def bounded_scope(self):
        expected = "local_fixture" if self.operation == "managed_evaluation" else "internal_fixture"
        if self.destination != expected:
            raise ValueError("Operation and reviewed local destination must match")
        if (
            self.status == "approved"
            and self.expires_at
            and self.expires_at <= datetime.now(timezone.utc)
        ):
            raise ValueError("A new approved scope must expire in the future")
        return self


class Assessment(Strict):
    scores: dict[str, StrictInt]
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
