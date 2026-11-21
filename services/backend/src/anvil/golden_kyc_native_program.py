"""Typed identities for the private sealed-trace KYC grader, never actor facts.

Software controls qualify scoring/gating mechanics only. They neither review a
case expectation nor establish legal applicability or model performance.
"""

import hashlib
from importlib.metadata import version
from typing import Literal

from pydantic import field_validator

from anvil.dataset_export_contract import Model, Sha
from anvil.db import digest, one
from anvil.golden_kyc_evaluators import CRITERIA
from anvil.qualification_resources import qualification_path, qualification_root

VERSION = "anvil.sealed-kyc-criterion.v1"
SOURCE_PATHS = tuple("services/backend/src/anvil/" + name for name in (
    "golden_kyc_native_program.py", "golden_kyc_grader.py",
    "golden_kyc_evaluators.py", "golden_kyc_criterion_support.py",
    "golden_kyc_state_checks.py", "golden_kyc_tables.py", "policy_rules.py",
    "kyc_expectation_reviews.py",
))


class Program(Model):
    schema_version: Literal[VERSION]
    criterion: str
    normalizer_source_sha256: Sha
    evidence: Literal["private_sealed_trace"] = "private_sealed_trace"
    anchors: Literal["fail0_partial2_pass5_unknown_unscored"] = "fail0_partial2_pass5_unknown_unscored"
    expectation_review: Literal["required"] = "required"
    state_policy_review: Literal["required_for_state_criteria"] = "required_for_state_criteria"

    @field_validator("criterion")
    @classmethod
    def criterion_supported(cls, value):
        if value not in CRITERIA:
            raise ValueError("Exact supported KYC criterion required")
        return value


def source_hash(*, _resource_proof=None):
    if _resource_proof is None:
        root = qualification_root()
        values = {p: hashlib.sha256(qualification_path(root, p).read_bytes()).hexdigest()
                  for p in SOURCE_PATHS}
    else:
        from anvil.software_resource_proof import checked_sha256

        values = {p: checked_sha256(_resource_proof, p) for p in SOURCE_PATHS}
    return digest(values)


def program(criterion, *, _resource_proof=None):
    return Program(schema_version=VERSION, criterion=criterion,
                   normalizer_source_sha256=source_hash(_resource_proof=_resource_proof))


def checked(value, *, _resource_proof=None):
    result = Program.model_validate(value)
    if result.normalizer_source_sha256 != source_hash(_resource_proof=_resource_proof):
        raise ValueError("Current sealed KYC normalizer required")
    return result


def controls(value, *, _resource_proof=None):
    """Actual pinned ZEN scoring controls; no uploaded cases or database writes."""
    from anvil.golden_kyc_evaluators import evaluate

    selected = checked(value, _resource_proof=_resource_proof)
    rows = []
    # These are deliberately manufactured internal software observations. Real
    # grading obtains its checks from normalize(sealed state), never this path.
    for name, truth, citations, reviewed, legal, expected in (
        ("positive", True, True, True, True, 5),
        ("partial_citation", True, False, True, True, 2),
        ("negative", False, True, True, True, 0),
        ("missing", None, True, True, True, None),
        ("expectation_review_pending", True, True, False, True, None),
        ("legal_review_pending", True, True, True, False,
         None if selected.criterion.startswith("state_") else 5),
    ):
        observations = dict.fromkeys(CRITERIA, truth)
        observations["citation_complete"] = dict.fromkeys(CRITERIA, citations)
        observations["mandatory_conditions"] = True
        expectation = {"independent_expectation_review": "approved" if reviewed else "pending",
                       "legal_qualification": "approved" if legal else "pending"}
        state = {"final": {"decision": "request_information"}}
        if truth is not None:
            expectation["intended_decision"] = "request_information" if truth else "specialist_review"
        result = evaluate(state, expectation, observations)
        actual = result["checks"][selected.criterion]
        if actual != expected or result["rubric_score"]["maximum_points"] != 100:
            raise ValueError("Sealed KYC scoring controls failed")
        rows.append({"control": name, "expected": expected, "actual": actual, "matched": True})
    return {"kind": "sealed_kyc_scoring_software_controls", "version": VERSION,
            "program_sha256": digest(selected.model_dump(mode="json")),
            "normalizer_source_sha256": selected.normalizer_source_sha256,
            "cases": rows, "passed": True, "provider_calls": 0,
            "case_review_granted": False, "legal_review_granted": False,
            "model_performance": False}


def qualified(value, receipt, *, _resource_proof=None):
    try:
        selected = checked(value, _resource_proof=_resource_proof)
        evidence = receipt["evidence"]
        expected_cases = [
            ("positive", 5), ("partial_citation", 2), ("negative", 0), ("missing", None),
            ("expectation_review_pending", None),
            ("legal_review_pending", None if selected.criterion.startswith("state_") else 5),
        ]
        cases = evidence.get("cases")
        if not isinstance(cases, list) or len(cases) != len(expected_cases):
            return False
        return (digest(evidence) == receipt["evidence_sha256"]
                and version("zen-engine") == "2.1.3"
                and evidence.get("kind") == "sealed_kyc_scoring_software_controls"
                and evidence.get("version") == VERSION
                and evidence.get("program_sha256") == digest(selected.model_dump(mode="json"))
                and evidence.get("normalizer_source_sha256") == selected.normalizer_source_sha256
                and evidence.get("passed") is True and type(evidence.get("provider_calls")) is int
                and evidence["provider_calls"] == 0
                and all(type(case) is dict and case.get("control") == name
                        and case.get("matched") is True
                        and type(case.get("actual")) is type(expected)
                        and type(case.get("expected")) is type(expected)
                        and case["actual"] == case["expected"] == expected
                        for case, (name, expected) in zip(cases, expected_cases, strict=True)))
    except (ValueError, TypeError, KeyError, OSError, ImportError):
        return False


def selected(c, project, paid):
    """Read exact frozen selections under the real private grader identity."""
    execution = one(c, "SELECT snapshot FROM anvil.workspace_execution_groups WHERE project_id=%s AND id=%s",
                    (project, paid["group_id"]))
    frozen = (execution or {}).get("snapshot", {}).get("preparation", {}).get("project_binding")
    if not frozen:
        raise ValueError("Frozen KYC execution selection required")
    binding = one(c, "SELECT * FROM anvil.project_binding_versions WHERE project_id=%s AND id=%s AND task_group_id=%s",
                  (project, frozen["id"], frozen["task_group_id"]))
    if (not binding or digest(binding["snapshot"]) != binding["snapshot_sha256"]
            or binding["snapshot_sha256"] != frozen["snapshot_sha256"]):
        raise ValueError("Frozen KYC evaluator selection changed")
    resolved = one(c, "SELECT task_key,revision,private_reference_sha256 FROM anvil.praxis_resolved_tasks WHERE project_id=%s AND id=%s",
                   (project, paid["resolved_task_id"]))
    if not resolved:
        raise ValueError("Exact resolved KYC task required")
    identity = {"task_id": resolved["task_key"], "task_version": resolved["revision"],
                "payload_sha256": resolved["private_reference_sha256"]}
    from anvil import evaluator_configurations as configurations

    output = []
    for criterion in CRITERIA:
        target = "criterion:" + digest(identity | {"criterion_id": criterion})
        refs = [r for r in binding["snapshot"]["rubric"] if r["target"] == target]
        if len(refs) != 1:
            raise ValueError("One exact KYC evaluator per criterion required")
        ref = refs[0]
        if ref["kind"] == "custom_python":
            # The existing isolated override path independently verifies this
            # program, its qualification and private receipt before scoring.
            output.append({"criterion": criterion, "target": target, "mode": "custom_python"})
            continue
        if ref["kind"] != "evaluator":
            raise ValueError("Unsupported KYC criterion evaluator")
        row = configurations.get(c, ref["id"])
        native = row["configuration"].get("native_kyc")
        if (str(row["project_id"]) != str(project) or row["configuration_sha256"] != ref["sha256"]
                or digest({"adapter": row["adapter"], "adapter_version": row["adapter_version"],
                           "configuration": row["configuration"]}) != ref["sha256"]
                or set(row["configuration"]) != {"native_kyc"}
                or row["status"] != "ready" or row["adapter"] != "builtin" or native is None
                or checked(native).criterion != criterion):
            raise ValueError("Exact qualified sealed-trace KYC evaluator required")
        output.append({"criterion": criterion, "target": target, "mode": "sealed_kyc",
                       "configuration_id": str(row["id"]), "configuration_sha256": ref["sha256"],
                       "validation_id": str(row["validation"]["id"]),
                       "validation_sha256": row["validation"]["evidence_sha256"],
                       "program_sha256": digest(native),
                       "normalizer_source_sha256": native["normalizer_source_sha256"]})
    return output


def receipts(selection, result, snapshot, state, events):
    """Private result provenance only; never includes private expected answers."""
    provenance = {"snapshot_sha256": digest(snapshot), "state_sha256": digest(state),
                  "events_sha256": digest(events)}
    return [entry | provenance | {"points": result["checks"][entry["criterion"]],
                                  "maximum_points": 5,
                                  "status": "unscored" if result["checks"][entry["criterion"]] is None else "scored"}
            for entry in selection]


def frozen_expectation_review(c, project, paid):
    execution = one(c, "SELECT snapshot FROM anvil.workspace_execution_groups WHERE project_id=%s AND id=%s",
                    (project, paid["group_id"]))
    ref = (execution or {}).get("snapshot", {}).get("preparation", {}).get("project_binding")
    if not ref:
        return None
    row = one(c, "SELECT snapshot,snapshot_sha256 FROM anvil.project_binding_versions WHERE project_id=%s AND id=%s AND task_group_id=%s",
              (project, ref["id"], ref["task_group_id"]))
    if not row or digest(row["snapshot"]) != row["snapshot_sha256"] or row["snapshot_sha256"] != ref["snapshot_sha256"]:
        raise ValueError("Frozen KYC expectation binding changed")
    return row["snapshot"].get("kyc_expectation_review")
