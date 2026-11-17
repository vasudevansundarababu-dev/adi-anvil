"""Offline priced physical-request manifest; no provider or dispatch authority."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from anvil.dataset_export_contract import Identifier, Model, Sha
from anvil.praxis_generic_contract import digest

QA_MODELS = {
    ("openai", "gpt-6.1-sol"),
    ("anthropic", "claude-opus-5-5"),
    ("gemini", "gemini-4-argon"),
}


class PaidRequestBound(Model):
    id: Identifier
    plan_id: str
    stage_index: int = Field(ge=0, le=999)
    maximum_micro_usd: int = Field(ge=1, le=2000000)
    purpose: Literal["actor", "evaluator", "retry"]
    case_id: Identifier
    provider: Identifier
    model_id: Identifier
    model_version: str = Field(min_length=1, max_length=200)
    credential_version_ref: str = Field(min_length=1, max_length=300)
    account_verification_sha256: Sha
    rate_verification_sha256: Sha
    input_tokens: int = Field(ge=1, le=1000000)
    output_tokens: int = Field(ge=1, le=1000000)
    input_micro_usd_per_million: int = Field(ge=1)
    output_micro_usd_per_million: int = Field(ge=1)
    extra_bound_micro_usd: int = Field(ge=0)
    parameters_sha256: Sha
    rate_expires_at: str

    @model_validator(mode="after")
    def exact_model(self):
        from uuid import UUID

        UUID(self.plan_id)
        if (self.provider, self.model_id) not in QA_MODELS:
            raise ValueError("Exact QA model allowlist required; no substitution")
        instant = datetime.fromisoformat(self.rate_expires_at.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("Timezone-aware rate expiry required")
        if self.maximum_micro_usd != self.bound():
            raise ValueError("Exact conservative physical request bound required")
        return self

    def bound(self):
        # Integer arithmetic: every physical request rounds conservatively upward.
        tokens = (
            self.input_tokens * self.input_micro_usd_per_million
            + self.output_tokens * self.output_micro_usd_per_million
        )
        return (tokens + 999999) // 1000000 + self.extra_bound_micro_usd


class PaidKYCManifest(Model):
    schema_version: Literal["anvil.golden-kyc-paid-manifest.v1"]
    group_id: str
    project_id: str
    import_sha256: Sha
    runtime_sha256: Sha
    evaluator_sha256: Sha
    input_rights_receipt_sha256: Sha
    requests: list[PaidRequestBound] = Field(min_length=1, max_length=1000)
    aggregate_cap_micro_usd: int = Field(ge=1, le=2000000)
    automatic_retries: Literal[False]

    @model_validator(mode="after")
    def aggregate(self):
        from uuid import UUID

        UUID(self.group_id)
        UUID(self.project_id)
        ids = [r.id for r in self.requests]
        if len(ids) != len(set(ids)):
            raise ValueError("Unique physical request IDs required")
        slots=[(r.plan_id,r.stage_index) for r in self.requests]
        if len(slots)!=len(set(slots)):
            raise ValueError("Each physical request requires its own priced plan/stage slot")
        if sum(r.bound() for r in self.requests) > self.aggregate_cap_micro_usd:
            raise ValueError("All actor/evaluator/retry requests exceed shared group cap")
        return self

    def preflight(self, now):
        if now.tzinfo is None:
            raise ValueError("Explicit timezone-aware verification clock required")
        missing = []
        if any(
            datetime.fromisoformat(r.rate_expires_at.replace("Z", "+00:00")) <= now
            for r in self.requests
        ):
            missing.append("verified_rates_expired")
        if now >= datetime.fromisoformat("2026-12-11T05:48:04+00:00"):
            missing.append("pilot_expired")
        return {
            "manifest_sha256": digest(self.model_dump()),
            "physical_request_count": len(self.requests),
            "maximum_micro_usd": sum(r.bound() for r in self.requests),
            "aggregate_cap_micro_usd": self.aggregate_cap_micro_usd,
            "missing": missing,
            "dispatch_authorized": False,
            "required_fence": "same SQL071 workspace execution group reservation and one-use broker ticket",
            "account_rate_refs_are_not_verification": True,
        }
