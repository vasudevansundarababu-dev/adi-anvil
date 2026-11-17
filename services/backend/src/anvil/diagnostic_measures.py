"""Typed evidence measures for the39 Golden diagnostics, without extra points.

Inputs belong to the private normalizer, never an actor-submitted compliance flag.
Exact reference scope and capture completeness are prerequisites. Semantic
judgments require separately calibrated, evidence-bound labels; string matching
is never described as semantic evaluation.
"""

import re
from collections import Counter

from anvil.db import digest
from anvil.diagnostic_effects import TARGETS as EFFECT_TARGETS
from anvil.diagnostic_effects import evaluate as evaluate_effects

FIELDS = {
    "K.FILE": ("document_id", "sha256"),
    "K.EXTRACT": ("document_id", "revision", "party_id", "field", "value", "source_locator"),
    "K.PURPOSE": ("document_id", "party_id", "document_type", "evidentiary_use"),
    "K.COMPARE": (
        "left_document_id",
        "left_revision",
        "right_document_id",
        "right_revision",
        "party_id",
        "field",
        "old_value",
        "new_value",
    ),
    "K.COMPLETE": ("document_id", "party_id", "field", "gap_kind", "assessment_date"),
    "K.CLAUSE": ("policy_id", "version", "clause_id", "source_locator"),
    "K.RISK": ("party_id", "risk_id", "disposition"),
    "K.REPLY": (
        "request_id",
        "response_sha256",
        "input_revision",
        "reassessment_revision",
        "finding_id",
    ),
    "K.ASYNC": ("operation_id", "terminal_status", "input_revision", "request_id", "disposition"),
    "K.RULEAPPLY": ("policy_id", "version", "rule_id", "condition", "exception", "disposition"),
    "M.BRIEF": ("requirement_id", "source_locator", "artifact_id", "owner", "deadline"),
    "M.FACT": ("fact_id", "value", "unit", "source_id", "version", "placement"),
    "M.VERSION": ("work_order_id", "asset_id", "asset_version", "content_sha256", "rights_scope"),
    "M.OUTPUT": ("window", "recipient", "artifact_id", "version", "sha256", "hold_disposition"),
    "M.LOCALE": ("locale", "rule_id", "version", "placement", "wording"),
    "M.PLANINPUT": ("requirement_id", "source_locator", "artifact_id", "owner", "deadline"),
    "M.DISAGREE": (
        "disagreement_id",
        "role",
        "step",
        "revision_limit",
        "disposition",
        "rationale_evidence_sha256",
    ),
}
SEMANTIC = {"K.SUPPORT", "K.TRANSLATE", "M.CLAIM", "M.TRANSLATE"}
ROLE_SUFFIXES = ("Intent", "Performance", "Orchestrator", "Creative", "Policy")
for role in ROLE_SUFFIXES:
    FIELDS["M.ROLE." + role] = ("action_id", "role", "operation", "window", "permission")
SAFETY = {"K.SAFETY", *("M.SAFETY." + role for role in ROLE_SUFFIXES)}
TARGETS = frozenset(FIELDS) | SEMANTIC | SAFETY | EFFECT_TARGETS | {"K.PROCESS"}
assert len(TARGETS) == 39


def valid_sha(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def measure_contract(target):
    if target not in TARGETS:
        raise ValueError("Unknown diagnostic target")
    names = (
        ("candidate_adherence", "environment_containment")
        if target in SAFETY
        else ("reviewed_obligations_preserved",)
        if target in SEMANTIC
        else ("ordered_obligations",)
        if target == "K.PROCESS"
        else ("precision", "recall")
    )
    denominators = {
        "precision": "reported_records_including_duplicates",
        "recall": "released_eligible_reference_records",
        "reviewed_obligations_preserved": "qualified_evidence_bound_semantic_labels",
        "ordered_obligations": "declared_ordered_obligations",
        "candidate_adherence": "exposed_candidate_episode_with_determinate_adherence",
        "environment_containment": "exercised_boundary_episode_with_determinate_containment",
    }
    return {name: {"kind": "ratio", "denominator_source": denominators[name]} for name in names}


def ratio(numerator, denominator):
    if (
        type(numerator) is not int
        or type(denominator) is not int
        or not 0 <= numerator <= denominator
    ):
        raise ValueError("Explicit valid integer counts required")
    return (
        {"kind": "ratio", "numerator": numerator, "denominator": denominator}
        if denominator
        else None
    )


def unknown(target, reason, *, ran=False, owner="reference_or_evidence_owner"):
    return {
        "schema_version": "anvil.diagnostic-measure.v1",
        "target": target,
        "status": "unscored",
        "ran": ran,
        "official_points": 0,
        "measurements": {},
        "unscored_reason": reason,
        "owner": owner,
        "model_performance": False,
    }


def records(value, fields):
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError("Bounded explicit diagnostic record list required")
    if any(not isinstance(row, dict) or not set(fields) <= row.keys() for row in value):
        raise ValueError("Exact subject/source/value fields required by diagnostic")
    return Counter(digest({key: row[key] for key in fields}) for row in value)


def evaluate(target, context, actual, reference):
    result = _evaluate(target, context, actual, reference)
    required = set(measure_contract(target))
    measured = set(result["measurements"])
    return result | {
        "measure_coverage": {
            "required": sorted(required),
            "measured": sorted(measured),
            "missing": sorted(required - measured),
            "complete": required == measured
            and result.get("population_coverage", {}).get("complete", True),
        }
    }


def _evaluate(target, context, actual, reference):
    if target not in TARGETS:
        raise ValueError("Unknown diagnostic target")
    ran = bool(isinstance(actual, dict) and actual.get("execution_receipt_sha256"))
    if (
        not isinstance(reference, dict)
        or reference.get("status") != "reviewed"
        or reference.get("context_sha256") != digest(context)
        or reference.get("target") != target
    ):
        return unknown(target, "exact_reviewed_reference_required", ran=ran)
    if reference.get("applicability") == "not_applicable":
        return unknown(target, "explicitly_inapplicable", ran=ran) | {"status": "not_applicable"}
    if reference.get("applicability") != "required":
        return unknown(target, "applicability_unresolved", ran=ran)
    if (
        not isinstance(actual, dict)
        or actual.get("complete_capture") is not True
        or actual.get("context_sha256") != digest(context)
    ):
        return unknown(target, "exact_complete_capture_required", ran=ran, owner="anvil")
    if target in EFFECT_TARGETS:
        return evaluate_effects(target, context, actual, reference)
    if target in SAFETY:
        from anvil.task_safety import assess

        result = assess(
            actual["safety_trace"],
            completed=actual.get("episode_completed") is True,
            evaluator_evidence_complete=True,
        )
        return {
            "schema_version": "anvil.diagnostic-measure.v1",
            "target": target,
            "status": result["candidate_outcome"]
            if result["candidate_outcome"] != "unknown"
            else "unscored",
            "ran": ran,
            "official_points": 0,
            "measurements": {
                name: ratio(int(result[key] == "pass"), 1)
                for name, key in (
                    ("candidate_adherence", "candidate_outcome"),
                    ("environment_containment", "containment_outcome"),
                )
                if result[key] in {"pass", "fail"}
            },
            "safety_outcome": result,
            "critical_incidents": result["critical_incidents"],
            "model_performance": False,
        }
    if target in SEMANTIC:
        calibration = reference.get("calibration")
        labels = actual.get("calibrated_labels")
        obligations = reference.get("obligations")
        if not valid_sha(actual.get("source_evidence_sha256")):
            return unknown(
                target, "valid_sealed_semantic_evidence_digest_required", ran=ran, owner="anvil"
            )
        if (
            not isinstance(calibration, dict)
            or calibration.get("status") != "qualified"
            or any(
                not valid_sha(calibration.get(key))
                for key in (
                    "blind_holdout_receipt_sha256",
                    "reviewed_examples_sha256",
                    "judge_model_binding_sha256",
                )
            )
            or not isinstance(labels, list)
            or len(labels) > 1000
        ):
            return unknown(target, "calibrated_semantic_or_bilingual_assessment_required", ran=ran)
        if (
            not isinstance(obligations, list)
            or not 1 <= len(obligations) <= 1000
            or any(
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or not item["id"]
                or not valid_sha(item.get("reference_sha256"))
                for item in obligations
            )
            or len({item["id"] for item in obligations}) != len(obligations)
        ):
            return unknown(target, "frozen_unique_semantic_obligation_population_required", ran=ran)
        if any(
            not isinstance(label, dict)
            or label.get("calibration_sha256") != digest(calibration)
            or label.get("source_evidence_sha256") != actual.get("source_evidence_sha256")
            or type(label.get("correct")) is not bool
            or not valid_sha(label.get("judgment_receipt_sha256"))
            for label in labels
        ):
            return unknown(target, "semantic_label_provenance_mismatch", ran=ran, owner="anvil")
        population = {item["id"]: item for item in obligations}
        identities = [label.get("obligation_id") for label in labels]
        receipts = [label["judgment_receipt_sha256"] for label in labels]
        if (
            any(identity not in population for identity in identities)
            or len(set(identities)) != len(identities)
            or len(set(receipts)) != len(receipts)
            or any(
                label.get("reference_sha256")
                != population[label["obligation_id"]]["reference_sha256"]
                for label in labels
            )
        ):
            return unknown(
                target, "duplicate_foreign_or_unbound_semantic_judgment", ran=ran, owner="anvil"
            )
        correct, total = sum(label["correct"] for label in labels), len(population)
        complete = set(identities) == set(population)
        return {
            "schema_version": "anvil.diagnostic-measure.v1",
            "target": target,
            "status": "unscored"
            if not complete
            else "pass"
            if correct == total
            else "partial"
            if correct
            else "fail",
            "ran": ran,
            "official_points": 0,
            "measurements": {"reviewed_obligations_preserved": ratio(correct, total)},
            "calibration_sha256": digest(calibration),
            "population_coverage": {
                "eligible": total,
                "judged": len(labels),
                "missing_obligation_ids": sorted(set(population) - set(identities)),
                "complete": complete,
            },
            "model_performance": False,
        }
    if target == "K.PROCESS":
        obligations, events = reference.get("obligations"), actual.get("obligation_events")
        if not isinstance(obligations, list) or not obligations or not isinstance(events, list):
            return unknown(target, "ordered_obligations_and_actual_events_required", ran=ran)
        if len(obligations) > 1000 or len(events) > 1000:
            raise ValueError("Bounded obligation graph required")
        by_id = {event["obligation_id"]: event for event in events}
        if len(by_id) != len(events):
            return unknown(target, "ambiguous_duplicate_obligation_events", ran=ran)
        correct = sum(
            1
            for item in obligations
            if item["id"] in by_id
            and by_id[item["id"]].get("effect_verified") is True
            and all(
                prior in by_id and by_id[prior]["sequence"] < by_id[item["id"]]["sequence"]
                for prior in item["after"]
            )
        )
        return {
            "schema_version": "anvil.diagnostic-measure.v1",
            "target": target,
            "status": "pass" if correct == len(obligations) else "partial" if correct else "fail",
            "ran": ran,
            "official_points": 0,
            "measurements": {"ordered_obligations": ratio(correct, len(obligations))},
            "model_performance": False,
        }
    fields = FIELDS[target]
    try:
        expected = records(reference.get("required_records"), fields)
        observed = records(actual.get("observed_records"), fields)
        invalid = actual.get("invalid_record_count", 0)
        if type(invalid) is not int or invalid < 0 or invalid + sum(observed.values()) > 1000:
            raise ValueError("Bounded observed invalid-record count required")
    except ValueError:
        return unknown(target, "typed_subject_source_evidence_required", ran=ran)
    eligible, reported = sum(expected.values()), sum(observed.values()) + invalid
    if not eligible:
        return unknown(target, "zero_eligible_denominator", ran=ran)
    correct = sum((expected & observed).values())
    invented, missed = reported - correct, eligible - correct
    return {
        "schema_version": "anvil.diagnostic-measure.v1",
        "target": target,
        "status": "pass" if not invented and not missed else "partial" if correct else "fail",
        "ran": ran,
        "official_points": 0,
        "measurements": {
            name: value
            for name, value in (
                ("precision", ratio(correct, reported)),
                ("recall", ratio(correct, eligible)),
            )
            if value is not None
        },
        "counts": {
            "eligible": eligible,
            "reported": reported,
            "correct": correct,
            "invented_or_duplicate": invented,
            "missed": missed,
        },
        "unit_fields": list(fields),
        "model_performance": False,
    }
