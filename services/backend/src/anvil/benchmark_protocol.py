"""Immutable benchmark protocol contracts; validation never grants dispatch authority."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from anvil.benchmark_conversation import Binding, Frozen, Limits
from anvil.db import digest

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class TaskBinding(Frozen):
    task_revision_id: UUID
    source_id: UUID
    package_id: UUID
    qualification_id: UUID
    package_sha256: Hash
    environment_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    tool_schema_sha256: Hash
    evaluator_binding_id: UUID
    possible_points: int = Field(strict=True, ge=1, le=1000000)
    criterion_count: int = Field(strict=True, ge=1, le=1000)


class Slot(Frozen):
    connection_id: UUID
    binding: Binding
    configuration_sha256: Hash
    # No credential value or opaque credential reference is part of a public protocol.
    transport: Literal["offline_contract", "live"]
    provider_concurrency: int = Field(default=1, strict=True, ge=1, le=3)


class Spend(Frozen):
    currency: Literal["USD"]
    candidate_cap_micro_usd: int = Field(strict=True, ge=0, le=1000000000)
    judge_cap_micro_usd: int = Field(strict=True, ge=0, le=1000000000)
    pricing_sha256: Hash
    authority_sha256: Hash
    expires_at: AwareDatetime


class Protocol(Frozen):
    profile: Literal["sme-comparison-v1"] = "sme-comparison-v1"
    benchmark_revision_id: UUID
    benchmark_subject_sha256: Hash
    tasks: tuple[TaskBinding, TaskBinding, TaskBinding]
    slots: tuple[Slot, Slot, Slot]
    repetitions: Literal[2] = 2
    max_active_trials: Literal[3] = 3
    order_policy: Literal["task-slot-repetition-v1"] = "task-slot-repetition-v1"
    retry_policy: Literal["no-ambiguous-dispatch-retry"] = "no-ambiguous-dispatch-retry"
    limits: Limits = Field(default_factory=Limits)
    scoring_policy_sha256: Hash
    evaluator_policy_sha256: Hash
    judge_binding_id: UUID | None = None
    calibration_sha256: Hash | None = None
    origin: Literal["original_synthetic_fixture", "authorized_benchmark"]
    spend: Spend

    @model_validator(mode="after")
    def exact_matrix(self):
        if len({t.task_revision_id for t in self.tasks}) != 3:
            raise ValueError("Three distinct frozen task revisions are required")
        if len({(s.binding.provider, s.binding.model_id) for s in self.slots}) != 3:
            raise ValueError("Three distinct candidate model bindings are required")
        offline = all(s.transport == "offline_contract" for s in self.slots)
        if any(s.transport == "offline_contract" for s in self.slots) != offline:
            raise ValueError("Offline and live candidates cannot share a comparison")
        if offline and (
            self.origin != "original_synthetic_fixture"
            or self.spend.candidate_cap_micro_usd != 0
            or self.spend.judge_cap_micro_usd != 0
            or self.judge_binding_id is not None
        ):
            raise ValueError("Offline conformance requires fictional origin and no paid spend/judge")
        if self.judge_binding_id is not None and self.calibration_sha256 is None:
            raise ValueError("A semantic judge requires exact calibration")
        if sum(t.possible_points for t in self.tasks) != 81 or sorted(
            t.possible_points for t in self.tasks
        ) != [6, 24, 51]:
            raise ValueError("The approved primary metric requires 24/6/51 task points")
        return self

    @property
    def subject_sha256(self):
        return digest(self.model_dump(mode="json"))

    def cells(self):
        return [
            {"task_revision_id": str(task.task_revision_id), "slot": slot, "repetition": rep}
            for task in self.tasks
            for slot in range(3)
            for rep in range(self.repetitions)
        ]

    def authority_blockers(self, *, now=None):
        """Read-only gates: even a valid live protocol is not paid-call permission."""
        blockers = []
        if self.spend.expires_at <= (now or datetime.now(timezone.utc)):
            blockers.append("protocol_authority_expired")
        if any(s.transport == "live" for s in self.slots):
            blockers.append("live_dispatch_not_activated")
        return blockers
