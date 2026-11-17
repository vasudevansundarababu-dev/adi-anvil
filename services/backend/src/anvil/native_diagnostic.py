"""Typed diagnostic evaluator configuration, not a native point award.

Software controls below use manufactured records/labels only. They qualify
serialization and measurement arithmetic, never model judgments, observed
effects, human review, an environment or scientific benchmark methodology.
"""

import hashlib
import sys
from copy import deepcopy
from typing import Literal

from pydantic import Field, model_validator

from anvil.db import digest
from anvil.diagnostic_measures import (
    EFFECT_TARGETS,
    FIELDS,
    SAFETY,
    SEMANTIC,
    TARGETS,
    evaluate,
    measure_contract,
    valid_sha,
)
from anvil.qualification_resources import qualification_path, qualification_root
from anvil.schemas import Strict

VERSION = "anvil-native-diagnostic-v1"
SCOPE = "manufactured_measurement_software_controls_only"


class Program(Strict):
    schema_version: Literal["anvil.native-diagnostic-program.v1"]
    method: Literal["anvil.diagnostic-measure.v1"]
    target_ids: list[str] = Field(min_length=1, max_length=39)

    @model_validator(mode="after")
    def targets(self):
        if len(set(self.target_ids)) != len(self.target_ids) or not set(self.target_ids) <= TARGETS:
            raise ValueError("Exact unique registered diagnostic targets required")
        return self


def source_hash():
    root = qualification_root()
    return digest(
        {
            "files": {
                name: hashlib.sha256(
                    qualification_path(root, "services/backend/src/anvil/" + name).read_bytes()
                ).hexdigest()
                for name in (
                    "native_diagnostic.py",
                    "qualification_resources.py",
                    "diagnostic_measures.py",
                    "diagnostic_effects.py",
                    "task_safety.py",
                    "schemas.py",
                    "db.py",
                )
            },
            "lock": hashlib.sha256(
                qualification_path(root, "services/backend/uv.lock").read_bytes()
            ).hexdigest(),
            "python": sys.version,
        }
    )


def compatible(config, descriptor):
    value = config["configuration"].get("native_diagnostic")
    if value is None:
        return False
    try:
        program = Program.model_validate(value)
    except (ValueError, TypeError):
        return False
    identifier = descriptor.get("skill_id") or descriptor.get("id")
    return bool(
        descriptor.get("official") is False
        and identifier in program.target_ids
        and descriptor.get("scale", {}).get("measures") == measure_contract(identifier)
    )


def controls(target):
    """Known arithmetic, unknown custody and negative controls for every family."""
    context = {
        "task_id": "SOFTWARE-CONTROL",
        "case_id": "NOT-A-BENCHMARK",
        "role": "control-role",
        "revision": "1",
        "snapshot_sha256": "a" * 64,
    }
    actual = {
        "complete_capture": True,
        "context_sha256": digest(context),
        "execution_receipt_sha256": "b" * 64,
        "source_evidence_sha256": "c" * 64,
    }
    reference = {
        "target": target,
        "status": "reviewed",
        "context_sha256": digest(context),
        "applicability": "required",
        "origin": SCOPE,
    }
    if target in FIELDS:
        row = {field: "control:" + field for field in FIELDS[target]}
        actual["observed_records"] = [row]
        reference["required_records"] = [row]
        negative = deepcopy(actual)
        negative["observed_records"][0][FIELDS[target][0]] = "WRONG-SUBJECT"
    elif target in EFFECT_TARGETS:
        from anvil.diagnostic_effects import METHOD

        reference.update(
            comparison_mode=METHOD,
            obligations=[
                {
                    "id": "expected-effect",
                    "operation": "control-operation",
                    "subject_id": "control-subject",
                    "arguments_match": {"requested": True},
                    "persisted_match": {"committed": True},
                }
            ],
        )
        invocation = {
            "invocation_id": "control-call",
            "operation": "control-operation",
            "subject_id": "control-subject",
            "role": context["role"],
            "effect_verified": True,
            "arguments": {"requested": True},
            "response": {"accepted": True},
            "persisted_state": {"committed": True},
        }
        invocation.update(
            {
                field + "_sha256": digest(invocation[field])
                for field in ("arguments", "response", "persisted_state")
            }
        )
        actual.update(normalizer_available=True, observed_invocations=[invocation])
        negative = deepcopy(actual)
        negative["observed_invocations"][0]["persisted_state"] = {"committed": False}
        negative["observed_invocations"][0]["persisted_state_sha256"] = digest({"committed": False})
    elif target in SEMANTIC:
        calibration = {
            "status": "qualified",
            "blind_holdout_receipt_sha256": "d" * 64,
            "reviewed_examples_sha256": "e" * 64,
            "judge_model_binding_sha256": "f" * 64,
        }
        reference.update(
            calibration=calibration,
            obligations=[{"id": "control-obligation", "reference_sha256": "a" * 64}],
        )
        actual["calibrated_labels"] = [
            {
                "obligation_id": "control-obligation",
                "reference_sha256": "a" * 64,
                "calibration_sha256": digest(calibration),
                "source_evidence_sha256": actual["source_evidence_sha256"],
                "correct": True,
                "judgment_receipt_sha256": "b" * 64,
            }
        ]
        negative = deepcopy(actual)
        negative["calibrated_labels"][0]["correct"] = False
    elif target == "K.PROCESS":
        reference["obligations"] = [{"id": "control-obligation", "after": []}]
        actual["obligation_events"] = [
            {"obligation_id": "control-obligation", "sequence": 1, "effect_verified": True}
        ]
        negative = deepcopy(actual)
        negative["obligation_events"][0]["effect_verified"] = False
    elif target in SAFETY:
        actual.update(
            episode_completed=True,
            safety_trace={
                "prompt_id": "control-prompt",
                "prompt_sha256": "d" * 64,
                "category_id": "control-category",
                "payload_sha256": "e" * 64,
                "exposed": True,
                "attempts": [],
                "effects": [],
                "detections": [],
                "recovery": None,
            },
        )
        negative = deepcopy(actual)
        negative["safety_trace"]["effects"] = [{"forbidden": True, "verified": True}]
    else:
        raise ValueError("Diagnostic software control not implemented")
    return context, actual, negative, reference


def validate(value):
    program = Program.model_validate(value)
    before, rows = source_hash(), []
    for target in program.target_ids:
        context, positive, negative, reference = controls(target)
        cases = []
        expected_pass = {
            name: {"kind": "ratio", "numerator": 1, "denominator": 1}
            for name in measure_contract(target)
        }
        expected_fail = {
            name: {"kind": "ratio", "numerator": 0, "denominator": 1}
            for name in measure_contract(target)
        }
        if target in SAFETY:
            expected_pass.pop("environment_containment")
        checks = [
            ("positive", positive, reference, "pass", expected_pass),
            ("negative", negative, reference, "fail", expected_fail),
            ("missing", positive, None, "unscored", {}),
            ("wrong_context", positive, reference | {"context_sha256": "0" * 64}, "unscored", {}),
        ]
        if target in SAFETY:
            blocked = deepcopy(positive)
            blocked["safety_trace"]["attempts"] = [
                {"forbidden": True, "blocked": True, "evidence_sha256": "f" * 64}
            ]
            checks.append(
                (
                    "blocked",
                    blocked,
                    reference,
                    "fail",
                    {
                        "candidate_adherence": {"kind": "ratio", "numerator": 0, "denominator": 1},
                        "environment_containment": {
                            "kind": "ratio",
                            "numerator": 1,
                            "denominator": 1,
                        },
                    },
                )
            )
        for name, actual, ref, expected, measurements in checks:
            outcome = evaluate(target, context, actual, ref)
            cases.append(
                {
                    "case": name,
                    "passed": outcome["status"] == expected
                    and outcome["measurements"] == measurements
                    and outcome["official_points"] == 0
                    and outcome["model_performance"] is False,
                    "result_sha256": digest(outcome),
                }
            )
        rows.append({"target": target, "controls": cases})
    if source_hash() != before:
        raise ValueError("Diagnostic software source changed during validation")
    return {
        "kind": "native_diagnostic_software_validation",
        "validation_scope": SCOPE,
        "runtime_version": "anvil-evaluator-v1",
        "native_diagnostic_version": VERSION,
        "program_sha256": digest(program.model_dump(mode="json")),
        "source_sha256": before,
        "targets": rows,
        "passed": all(case["passed"] for row in rows for case in row["controls"]),
        "provider_calls": 0,
        "paid_calls": 0,
        "human_calibration_established": False,
        "model_performance_validated": False,
    }


def qualified_receipt(program, receipt):
    if not isinstance(receipt, dict) or not isinstance(receipt.get("evidence"), dict):
        return False
    evidence = receipt["evidence"]
    try:
        parsed, current_source = Program.model_validate(program), source_hash()
    except (ValueError, TypeError, OSError, ImportError, RuntimeError):
        return False
    rows = evidence.get("targets")
    if not isinstance(rows, list) or any(
        not isinstance(row, dict)
        or not isinstance(row.get("controls"), list)
        or any(
            not isinstance(case, dict) or not isinstance(case.get("case"), str)
            for case in row["controls"]
        )
        for row in rows
    ):
        return False
    return bool(
        digest(evidence) == receipt.get("evidence_sha256")
        and evidence.get("kind") == "native_diagnostic_software_validation"
        and evidence.get("validation_scope") == SCOPE
        and evidence.get("native_diagnostic_version") == VERSION
        and evidence.get("source_sha256") == current_source
        and evidence.get("program_sha256") == digest(parsed.model_dump(mode="json"))
        and evidence.get("passed") is True
        and evidence.get("human_calibration_established") is False
        and evidence.get("model_performance_validated") is False
        and type(evidence.get("provider_calls")) is int
        and evidence["provider_calls"] == 0
        and type(evidence.get("paid_calls")) is int
        and evidence["paid_calls"] == 0
        and [row.get("target") for row in evidence.get("targets", [])] == parsed.target_ids
        and all(
            {case.get("case") for case in row.get("controls", [])}
            == (
                {"positive", "negative", "missing", "wrong_context", "blocked"}
                if row["target"] in SAFETY
                else {"positive", "negative", "missing", "wrong_context"}
            )
            and len(row["controls"]) == (5 if row["target"] in SAFETY else 4)
            and all(
                case.get("passed") is True and valid_sha(case.get("result_sha256"))
                for case in row["controls"]
            )
            for row in evidence["targets"]
        )
    )
