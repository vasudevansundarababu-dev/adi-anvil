"""API-side private verifier semantics, never physical acceptance or scoring proof.

Original binding and complete result bytes must come from actual protected API
custody and an independently observed qualified process. This pure checker cannot
create that custody. It is not reachable from the current unqualified raw intake.
"""

import hashlib
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from anvil.dataset_export_contract import Model, Sha, json_object
from anvil.marketing_native_wire_bounds import bounded_json
from anvil.marketing_task2_contract import CRITICAL, GROUPS
from anvil.marketing_world_quiescence import Scope
from anvil.praxis_generic_contract import canonical

SCORING = "marketing-task2-native-23-ordinal-v1"
CRITERION_WEIGHTS = {
    "A1": 4, "A2": 4, "A3": 2, "B1": 5, "B2": 5, "B3": 5, "B4": 5,
    "C1": 6, "C2": 5, "C3": 4, "D1": 6, "D2": 4,
    "E1": 5, "E2": 5, "E3": 5, "F1": 5, "F2": 4, "F3": 3, "F4": 3,
    "G1": 4, "G2": 4, "G3": 4, "G4": 3,
}
FILES = frozenset({"actor-output.json", "private-evidence.json", "evaluation-profile.json"})
RESULT_CAP = 1048576  # Private original file bound, NOT the4096 metadata-kind cap.


class Identity(Model):
    job_id: UUID
    framework_trial_id: UUID
    operation_nonce: Sha
    request_sha256: Sha
    plan_sha256: Sha


class ScoringSourcePins(Model):
    criterion_map_jcs_sha256: Literal["3bc563cf8d9f59b964c818d5518ec468a1b9d44334c1860d701ce0add894883a"]
    rubric_jcs_sha256: Literal["8287e05c7dbf57ebb8b000c437d30ad2ca2fc37ff6c91206630ef06109fc601e"]


class OriginalVerifierBinding(Model):
    """API's original qualified rubric projection; never trust a submitted SDK binding."""

    schema_version: Literal["anvil.marketing-private-sdk-binding.v1"]
    scoring_contract: Literal[SCORING]
    scoring_source_pins: ScoringSourcePins
    identity: Identity
    scope: Scope
    source_sha256: Sha
    input_sha256: Sha
    input_files: dict[str, Sha] = Field(min_length=3, max_length=3)
    rubric_id: str = Field(min_length=1, max_length=200)
    rubric_version: str = Field(min_length=1, max_length=200)
    criterion_weights: dict[str, int] = Field(min_length=23, max_length=23)

    @model_validator(mode="after")
    def original_contract(self):
        if (set(self.input_files) != FILES or self.identity.job_id != self.scope.job_id
                or self.criterion_weights != CRITERION_WEIGHTS):
            raise ValueError("Exact original private verifier input and scope required")
        totals = dict.fromkeys(GROUPS, 0)
        for key, weight in self.criterion_weights.items():
            if (key not in CRITERION_WEIGHTS
                    or type(weight) is not int or not 1 <= weight <= GROUPS[key[0]]):
                raise ValueError("Exact23 native criterion identities and weights required")
            totals[key[0]] += weight
        if totals != GROUPS:
            raise ValueError("Exact original100-point native group denominator required")
        return self


class Rational(Model):
    numerator: int = Field(ge=0, le=400)
    denominator: int = Field(ge=1, le=4)


class PrivateResult(Model):
    schema_version: Literal["anvil.marketing-private-result.v1"]
    profile: Literal["anvil.marketing-private-verifier.v1"]
    scoring_contract: Literal[SCORING]
    scoring_source_pins: ScoringSourcePins
    identity: Identity
    scope: Scope
    source_sha256: Sha
    input_sha256: Sha
    input_files: dict[str, Sha] = Field(min_length=3, max_length=3)
    rubric_id: str = Field(min_length=1, max_length=200)
    rubric_version: str = Field(min_length=1, max_length=200)
    scale: Literal["zero_to_four"]
    levels: dict[str, int | None] = Field(min_length=23, max_length=23)
    groups: dict[str, Rational] = Field(min_length=7, max_length=7)
    total: Rational
    result: Literal["passed", "failed", "unscored"]
    output_gate: bool | None
    unscored_criteria: list[str] = Field(max_length=23)
    unknown_critical_rules: list[str] = Field(max_length=6)
    critical_failures: list[str] = Field(max_length=6)
    human_legal_acceptance: Literal["not_established"]
    model_performance_validated: Literal[False]
    native_qualification_granted: Literal[False]
    paid_calls: Literal[False]


@dataclass(frozen=True, slots=True)
class CheckedResult:
    raw: bytes = field(repr=False)
    sha256: str
    status: str
    complete: bool
    # A self-consistent grade is neither an accepted capture nor actual native
    # model performance. The independent process/custody gates remain separate.
    capture_accepted: bool = False
    native_qualified: bool = False
    run_authority: str = "not_granted"


def validate_private_result(raw, original):
    """Recompute exact native23 arithmetic/status; no process claim is accepted.

    Do not feed a caller's metadata dictionary as original. Full original result
    and private rubric must already be held/authenticated by the API. Raw hashes
    preserve the producer's original serialization, not an invented JCS rewrite.
    """
    if (type(raw) is not bytes or not 0 < len(raw) <= RESULT_CAP
            or type(original) is not OriginalVerifierBinding):
        raise ValueError("Complete original private result and API binding required")
    try:
        value = json_object(raw)
        bounded_json(value, RESULT_CAP, max_nodes=10000, max_depth=8)
        bound = original.model_dump(mode="json")
        bounded_json(bound, 32768, max_nodes=2000, max_depth=8)
        original = OriginalVerifierBinding.model_validate_json(canonical(bound))
        if any(value.get(key) is not False for key in
               ("model_performance_validated", "native_qualification_granted", "paid_calls")):
            raise ValueError("flags")
        result = PrivateResult.model_validate_json(raw)
        result_value = result.model_dump(mode="json")
        if any(value[key] != bound[key] for key in
               ("scoring_contract", "scoring_source_pins", "identity", "scope", "source_sha256", "input_sha256",
                "input_files", "rubric_id", "rubric_version")):
            raise ValueError("original binding")
        if set(result.levels) != set(original.criterion_weights):
            raise ValueError("original criterion set")
        for rows in (result.critical_failures, result.unknown_critical_rules):
            if rows != sorted(set(rows)) or not set(rows) <= CRITICAL:
                raise ValueError("original critical rule identities")
        if set(result.critical_failures) & set(result.unknown_critical_rules):
            raise ValueError("critical evidence conflict")
        totals = dict.fromkeys(GROUPS, Fraction(0))
        missing = sorted(key for key, level in result.levels.items() if level is None)
        for key, weight in original.criterion_weights.items():
            level = result.levels[key]
            if level is not None:
                if type(level) is not int or not 0 <= level <= 4:
                    raise ValueError("original0-4 scale")
                totals[key[0]] += Fraction(weight * level, 4)
        total = sum(totals.values(), Fraction(0))
        status = ("failed" if result.critical_failures or result.output_gate is False else "unscored"
                  if missing or result.unknown_critical_rules or result.output_gate is None else "passed"
                  if total >= 80 and totals["B"] >= 12 else "failed")
        exact_groups = {key: {"numerator": amount.numerator, "denominator": amount.denominator}
                        for key, amount in totals.items()}
        exact_total = {"numerator": total.numerator, "denominator": total.denominator}
        if (result_value["groups"] != exact_groups or result_value["total"] != exact_total
                or result.unscored_criteria != missing or result.result != status):
            raise ValueError("exact native arithmetic or status")
        complete = not (result.unscored_criteria or result.unknown_critical_rules or result.output_gate is None)
        return CheckedResult(raw, hashlib.sha256(raw).hexdigest(), result.result, complete)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise ValueError("Original private verifier semantics rejected; no acceptance") from None
