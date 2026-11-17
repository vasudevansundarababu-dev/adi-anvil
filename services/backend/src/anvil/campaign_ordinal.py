"""Private native-ordinal dispatch from frozen, currently qualified bindings.

Neither known-case tests nor a model's claimed success supplies calibration.
Native awards use explicit anchors. Critical/output gates and original weights
are applied separately by campaign_grader, and expert awards remain additive.
"""

import os

from fastapi import HTTPException

from anvil.db import digest, one
from anvil.diagnostic_measures import valid_sha
from anvil.evaluator_configurations import get as evaluator
from anvil.native_ordinal import VERSION, evaluate


def source_hash():
    import hashlib
    from pathlib import Path

    return digest(
        {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("campaign_ordinal.py", "native_ordinal.py", "evaluator_configurations.py")
        }
    )


def calibrated(calibration, context):
    return bool(
        isinstance(calibration, dict)
        and calibration.get("status") == "reviewed"
        and calibration.get("native_scale") == [0, 1, 2, 3, 4]
        and all(type(value) is int for value in calibration["native_scale"])
        and all(calibration.get(key) == value for key, value in context.items())
        and all(
            valid_sha(calibration.get(key))
            for key in (
                "reviewed_examples_sha256",
                "reference_set_sha256",
                "blind_holdout_receipt_sha256",
            )
        )
    )


def binding_record(ref, config):
    """Server-derived metadata only; never trust a client's claimed capability."""
    program = config["configuration"].get("native_ordinal")
    if program is None:
        return None
    return {
        "target": ref["target"],
        "configuration_id": str(ref["id"]),
        "configuration_sha256": ref["sha256"],
        "program_sha256": digest(program),
    }


def supports_target(descriptor):
    levels = (descriptor.get("scale") or {}).get("levels")
    return bool(
        descriptor.get("domain") == "marketing"
        and descriptor.get("official") is True
        and levels == [0, 1, 2, 3, 4]
        and all(type(level) is int for level in levels)
    )


def qualification_gaps(snapshot, evidence):
    required = snapshot.get("native_ordinal_bindings", [])
    controls = evidence.get("native_ordinal", []) if isinstance(evidence, dict) else []
    if not isinstance(required, list) or not isinstance(controls, list):
        return [
            {"section": "rubric", "code": "native_ordinal_qualification_invalid", "owner": "anvil"}
        ]
    gaps = []
    for item in required:
        if not isinstance(item, dict) or not all(
            key in item
            for key in ("target", "configuration_id", "configuration_sha256", "program_sha256")
        ):
            return [
                {"section": "rubric", "code": "native_ordinal_binding_invalid", "owner": "anvil"}
            ]
        expected = item | {"source_sha256": source_hash(), "status": "passed"}
        if not any(
            isinstance(control, dict)
            and all(control.get(key) == value for key, value in expected.items())
            and valid_sha(control.get("calibration_sha256"))
            and valid_sha(control.get("evidence_sha256"))
            for control in controls
        ):
            gaps.append(
                {
                    "section": "rubric",
                    "target": item["target"],
                    "code": "native_ordinal_target_program_calibration_qualification_required",
                    "owner": "anvil",
                }
            )
    return gaps


def collect(c, project, prepared, task, sealed, reference, case):
    """Call only inside the private grader transaction, before final award writes."""
    from anvil.golden_targets import requirements
    from anvil.project_bindings import evidence_gaps

    descriptors = [row for row in requirements(task) if row["official"]]
    results = {
        row["id"]: {
            "award": None,
            "status": "unscored",
            "reason": "native_ordinal_binding_required",
            "evaluator": VERSION,
        }
        for row in descriptors
    }
    frozen = prepared.get("project_binding")
    release = os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256")
    if not isinstance(frozen, dict) or not release:
        return results
    available = c.execute(
        "SELECT to_regprocedure('anvil.lock_native_ordinal_award(uuid,uuid)') AS function"
    ).fetchone()
    if not available["function"]:
        return {
            key: value | {"reason": "native_ordinal_authority_runtime_required"}
            for key, value in results.items()
        }
    binding = one(
        c,
        "SELECT * FROM anvil.project_binding_versions WHERE project_id=%s AND task_group_id=%s AND id=%s",
        (project, frozen.get("task_group_id"), frozen.get("id")),
    )
    if (
        not binding
        or digest(binding["snapshot"]) != binding["snapshot_sha256"]
        or binding["snapshot_sha256"] != frozen.get("snapshot_sha256")
    ):
        return {
            key: value | {"reason": "native_ordinal_frozen_binding_mismatch"}
            for key, value in results.items()
        }
    qualification = one(
        c,
        "SELECT q.* FROM anvil.project_binding_qualifications q WHERE q.project_id=%s AND q.binding_id=%s AND q.release_sha256=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id) ORDER BY q.created_at DESC,q.id DESC LIMIT 1",
        (project, binding["id"], release),
    )
    if (
        not qualification
        or digest(qualification["evidence"]) != qualification["evidence_sha256"]
        or evidence_gaps(binding["snapshot"], qualification["evidence"])
    ):
        return {
            key: value | {"reason": "native_ordinal_current_qualification_required"}
            for key, value in results.items()
        }
    controls = qualification["evidence"].get("native_ordinal", [])
    if not isinstance(controls, list):
        controls = []
    calibrations = reference.get("native_ordinal_calibrations", {})
    contexts = reference.get("criterion_references", {})
    if not isinstance(calibrations, dict) or not isinstance(contexts, dict):
        return results
    for descriptor in descriptors:
        identifier, target = descriptor["id"], descriptor["target"]
        refs = [ref for ref in binding["snapshot"].get("rubric", []) if ref.get("target") == target]
        if len(refs) != 1 or refs[0].get("kind") != "evaluator":
            continue
        ref = refs[0]
        # Narrow definer helper coordinates binding/qualification/evaluator
        # revocations and author access through final INSERT. No table access
        # to users or memberships is granted to the private grader.
        active = one(
            c,
            "SELECT anvil.lock_native_ordinal_award(%s,%s) AS allowed",
            (binding["id"], ref["id"]),
        )
        if not active or not active["allowed"]:
            results[identifier]["reason"] = "native_ordinal_author_access_revoked"
            continue
        if not one(
            c,
            "SELECT q.id FROM anvil.project_binding_qualifications q WHERE q.project_id=%s AND q.id=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id)",
            (project, qualification["id"]),
        ):
            results[identifier]["reason"] = "native_ordinal_qualification_expired_or_revoked"
            continue
        try:
            config = evaluator(c, ref["id"])
        except HTTPException:
            continue
        program = config["configuration"].get("native_ordinal")
        if (
            config["configuration_sha256"] != ref["sha256"]
            or config["status"] != "ready"
            or config["adapter"] != "builtin"
            or program is None
        ):
            results[identifier]["reason"] = "native_ordinal_exact_ready_configuration_required"
            continue
        if binding_record(ref, config) not in binding["snapshot"].get(
            "native_ordinal_bindings", []
        ):
            results[identifier]["reason"] = "native_ordinal_frozen_program_binding_required"
            continue
        context = {key: task[key] for key in ("task_id", "task_version", "payload_sha256")}
        context.update(
            criterion_id=identifier,
            target=target,
            role=descriptor["role"],
            case_id=case["case_id"],
            snapshot_sha256=case["snapshot_sha256"],
        )
        calibration = calibrations.get(identifier)
        if not calibrated(calibration, context):
            results[identifier]["reason"] = "native_ordinal_reviewed_calibration_required"
            continue
        expected_control = {
            "target": target,
            "configuration_id": str(ref["id"]),
            "configuration_sha256": ref["sha256"],
            "program_sha256": digest(program),
            "calibration_sha256": digest(calibration),
            "source_sha256": source_hash(),
            "status": "passed",
        }
        if not any(
            isinstance(control, dict)
            and all(control.get(key) == value for key, value in expected_control.items())
            and valid_sha(control.get("evidence_sha256"))
            for control in controls
        ):
            results[identifier]["reason"] = (
                "native_ordinal_target_program_calibration_qualification_required"
            )
            continue
        try:
            actual = evaluate(
                program, {"capture": sealed["capture"], "reference": contexts.get(identifier)}
            )
        except (ValueError, TypeError, RecursionError):
            results[identifier]["reason"] = "native_ordinal_evidence_invalid_or_outside_bound"
            continue
        if not one(
            c,
            "SELECT q.id FROM anvil.project_binding_qualifications q WHERE q.project_id=%s AND q.id=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id)",
            (project, qualification["id"]),
        ):
            results[identifier]["reason"] = "native_ordinal_qualification_expired_or_revoked"
            continue
        results[identifier] = actual | {
            "configuration_id": str(ref["id"]),
            "configuration_sha256": ref["sha256"],
            "calibration_sha256": digest(calibration),
            "qualification_id": str(qualification["id"]),
            "binding_id": str(binding["id"]),
            "binding_sha256": binding["snapshot_sha256"],
            "capture_sha256": sealed["capture_sha256"],
            "target": target,
            "human_calibration_established_by_software": False,
        }
    return results
