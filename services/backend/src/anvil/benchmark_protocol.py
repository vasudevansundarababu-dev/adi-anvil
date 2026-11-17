"""Immutable benchmark protocol contracts; validation never grants dispatch authority."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_serializer, model_validator

from anvil.benchmark_conversation import Binding, Frozen, Limits
from anvil.config import ROOT
from anvil.db import digest

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
CriterionId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")]


def runtime_sha256():
    import hashlib

    paths = (
        "benchmark_protocol.py",
        "benchmark_execution.py",
        "benchmark_scheduler.py",
        "benchmark_offline_worker.py",
        "benchmark_offline_actor.py",
        "benchmark_scores.py",
        "benchmark_results.py",
        "benchmark_conversation.py",
        "benchmark_provider_wire.py",
    )
    paths += (
        "benchmark_review_policy.py",
        "benchmark_report_policy.py",
        "benchmark_atif.py",
        "benchmark_reconciliation.py",
    )
    paths += (
        "benchmark_qualification.py",
        "benchmark_compiler.py",
        "benchmark_pipeline.py",
        "benchmark_evaluator_program.py",
        "benchmark_storage.py",
        "auth.py",
    )
    bound = {
        name: hashlib.sha256((ROOT / "services/backend/src/anvil" / name).read_bytes()).hexdigest()
        for name in paths
    }
    bound["harbor_atif"] = hashlib.sha256(
        (ROOT / "services/harbor/src/anvil_harbor/atif.py").read_bytes()
    ).hexdigest()
    return digest(bound)


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


class TaskReviewPolicy(Frozen):
    task_revision_id: UUID
    pass_threshold_percent: str = Field(
        pattern=r"^(?:[0-9]{1,2}(?:\.[0-9]{1,8})?|100(?:\.0{1,8})?)$"
    )
    critical_criterion_ids: tuple[CriterionId, ...] = Field(max_length=1000)


class ReviewPolicy(Frozen):
    version: Literal[1, 2] = 1
    tasks: tuple[TaskReviewPolicy, TaskReviewPolicy, TaskReviewPolicy]
    calibration_sha256: Hash
    first_assignment_id: UUID | None = None
    second_assignment_id: UUID | None = None
    adjudicator_assignment_id: UUID | None = None
    reviewer_assignment_ids: tuple[UUID, ...] = Field(default=(), max_length=10)
    report_policy: dict | None = None
    sample_percent: Literal[10] = 10
    borderline_percentage_points: Literal[5] = 5

    @model_serializer(mode="wrap")
    def preserve_legacy_bytes(self, handler):
        result = handler(self)
        if self.version == 1:
            for key in ("version", "reviewer_assignment_ids", "report_policy"):
                result.pop(key, None)
        return result

    @model_validator(mode="after")
    def distinct(self):
        if self.version == 2:
            if len({t.task_revision_id for t in self.tasks}) != 3 or len(
                set(self.reviewer_assignment_ids)
            ) != len(self.reviewer_assignment_ids):
                raise ValueError("Exact task thresholds and distinct report duties required")
            if any(
                x is not None
                for x in (
                    self.first_assignment_id,
                    self.second_assignment_id,
                    self.adjudicator_assignment_id,
                )
            ):
                raise ValueError("Version2 uses configurable report duties, not legacy stages")
            return self
        if (
            any(
                x is None
                for x in (
                    self.first_assignment_id,
                    self.second_assignment_id,
                    self.adjudicator_assignment_id,
                )
            )
            or len({t.task_revision_id for t in self.tasks}) != 3
            or len(
                {
                    self.first_assignment_id,
                    self.second_assignment_id,
                    self.adjudicator_assignment_id,
                }
            )
            != 3
        ):
            raise ValueError("Review requires exact task thresholds and three distinct duties")
        if any(Decimal(t.pass_threshold_percent) > 100 for t in self.tasks):
            raise ValueError("Invalid point-percent review threshold")
        return self


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
    replacement_policy: Literal["no_replacements"] = "no_replacements"
    resume_policy: Literal["untouched_queue_or_captured_only"] = "untouched_queue_or_captured_only"
    limits: Limits = Field(default_factory=Limits)
    scoring_policy_sha256: Hash
    evaluator_policy_sha256: Hash
    runtime_sha256: Hash
    review_policy: ReviewPolicy | None = None
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
            raise ValueError(
                "Offline conformance requires fictional origin and no paid spend/judge"
            )
        if self.judge_binding_id is not None and self.calibration_sha256 is None:
            raise ValueError("A semantic judge requires exact calibration")
        if sum(t.possible_points for t in self.tasks) != 81 or sorted(
            t.possible_points for t in self.tasks
        ) != [6, 24, 51]:
            raise ValueError("The approved primary metric requires 24/6/51 task points")
        if any(t.criterion_count != t.possible_points for t in self.tasks):
            raise ValueError("The initial profile requires its complete 81 one-point criteria")
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
