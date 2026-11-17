"""Saved native judge configuration; no provider calls or embedded authority."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter, field_validator, model_validator

from anvil.db import digest
from anvil.diagnostic_measures import valid_sha
from anvil.schemas import Strict

VERSION = "anvil-native-semantic-v1"


class Program(Strict):
    schema_version: Literal["anvil.native-semantic-program.v1"]
    criterion_ids: list[str] = Field(min_length=1, max_length=23)
    model_selection: Literal["candidate"]
    max_input_bytes: int = Field(strict=True, ge=1, le=32768)
    max_output_tokens: int = Field(strict=True, ge=1, le=2048)
    max_calls: Literal[1]

    @field_validator("max_calls", mode="before")
    @classmethod
    def one_call(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Exactly one separately metered judge call required")
        return value

    @model_validator(mode="after")
    def native_criteria(self):
        from anvil.golden_targets import definitions

        supported = {row["id"] for row in definitions("marketing") if row["official"]}
        if (
            len(set(self.criterion_ids)) != len(self.criterion_ids)
            or not set(self.criterion_ids) <= supported
        ):
            raise ValueError("Exact distinct native Marketing criterion IDs required")
        return self


class FixedProgram(Program):
    """Versioned independent judge selection; a saved profile is not authority.

    The API freezes the server-resolved model alongside this program. Keep the
    v1 class separate so loading old evidence never adds fields or changes its
    canonical configuration hash.
    """

    schema_version: Literal["anvil.native-semantic-program.v2"]
    model_selection: Literal["fixed"]
    judge_model_profile_id: UUID


SavedProgram = Annotated[Program | FixedProgram, Field(discriminator="schema_version")]


def parse_program(value):
    return TypeAdapter(SavedProgram).validate_python(value)


def fixed_model(program, configuration, current):
    """Match the current enabled model to the immutable server snapshot.

    Current enablement/revocation is checked by workspace_preparation.model;
    this guard never resolves credentials or substitutes a candidate model.
    """
    program = parse_program(program)
    if not isinstance(program, FixedProgram):
        raise ValueError("An independent fixed-judge program is required")
    saved = configuration.get("semantic_judge_model")
    if (
        not isinstance(saved, dict)
        or str(program.judge_model_profile_id) != current.get("id")
        or saved != current
        or digest(saved) != digest(current)
    ):
        raise ValueError("The fixed judge changed; create and qualify a new evaluator version")
    return saved


def profile_matches(program, configuration, specification):
    """Bind judge selection and bounds, not just a compatible criterion name."""
    from anvil.campaign_semantic_contract import FixedBlueprint

    try:
        parsed = parse_program(program)
    except (ValueError, TypeError):
        return False
    if any(
        getattr(parsed, key) != getattr(specification, key)
        for key in ("criterion_ids", "max_input_bytes", "max_output_tokens", "max_calls")
    ):
        return False
    if isinstance(parsed, FixedProgram):
        saved = configuration.get("semantic_judge_model")
        return bool(
            isinstance(specification, FixedBlueprint)
            and isinstance(saved, dict)
            and str(parsed.judge_model_profile_id) == saved.get("id")
            and parsed.judge_model_profile_id == specification.judge_model_profile_id
            and digest(saved) == specification.model_binding_sha256
        )
    return not isinstance(specification, FixedBlueprint)


def prepare_fixed_models(c, saved_models):
    """Freeze current server prices for the already bound independent judges.

    No credential is opened and no provider is called. Model/profile/credential
    changes require a new binding rather than silently changing the evaluator.
    """
    from fastapi import HTTPException

    from anvil import workspace_costs
    from anvil.campaign_semantic_contract import bounded_json
    from anvil.db import one
    from anvil.workspace_preparation import model, model_snapshot

    if not isinstance(saved_models, dict) or len(saved_models) > 23:
        raise HTTPException(409, "A bounded immutable independent judge set is required")
    models, prices = {}, {}
    for fingerprint, saved in saved_models.items():
        try:
            if not isinstance(saved, dict) or digest(saved) != fingerprint:
                raise ValueError("Invalid snapshot")
            bounded_json(saved, 32768)
            identifier = UUID(saved["id"])
        except (ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(409, "Independent judge snapshot integrity failed")
        current = model(c, identifier)
        row = one(c, "SELECT * FROM anvil.connections WHERE id=%s FOR SHARE", (saved["id"],))
        if current != saved or not row or model_snapshot(row) != saved:
            raise HTTPException(409, "Independent judge changed; update the Project binding")
        price = workspace_costs.for_model(row)
        if not workspace_costs.current(price) or any(
            price.get(key) != saved.get(key) for key in ("provider", "model_id")
        ):
            raise HTTPException(409, "Current exact independent judge pricing is required")
        models[fingerprint], prices[fingerprint] = saved, price
    return {"semantic_judge_models": models, "semantic_judge_pricing": prices} if models else {}


def fixed_runtime_available(c):
    """Schema presence only; this does not replace independent qualification."""
    from anvil.db import one

    present = one(
        c, "SELECT to_regprocedure('marketing_runtime.fixed_judge_schema_version()') AS function"
    )
    if not present or not present["function"]:
        return False
    version = one(c, "SELECT marketing_runtime.fixed_judge_schema_version() AS version")
    return bool(version and type(version["version"]) is int and version["version"] == 2)


def qualified_receipt(program, receipt):
    """Software Pass/Fail cases cannot masquerade as private judge validation."""
    if not isinstance(receipt, dict) or not isinstance(receipt.get("evidence"), dict):
        return False
    evidence = receipt["evidence"]
    models = evidence.get("supported_model_binding_sha256")
    try:
        from anvil.native_semantic_validation import SCOPE, source_hash

        current_source = source_hash()
    except (OSError, ValueError, ImportError, RuntimeError):
        return False
    return bool(
        digest(evidence) == receipt.get("evidence_sha256")
        and evidence.get("kind") == "private_native_semantic_validation"
        and evidence.get("native_semantic_version") == VERSION
        and evidence.get("native_program_sha256") == digest(program)
        and evidence.get("passed") is True
        and evidence.get("validation_scope") == SCOPE
        and evidence.get("validation_source_sha256") == current_source
        and evidence.get("dispatch_origin") == "sdk_mock"
        and evidence.get("structured_request") is True
        and type(evidence.get("provider_calls")) is int
        and evidence["provider_calls"] == 0
        and type(evidence.get("paid_calls")) is int
        and evidence["paid_calls"] == 0
        and evidence.get("human_calibration_established") is False
        and evidence.get("model_performance_validated") is False
        and isinstance(models, list)
        and 1 <= len(models) <= 8
        and all(valid_sha(model) for model in models)
        and len(set(models)) == len(models)
    )
