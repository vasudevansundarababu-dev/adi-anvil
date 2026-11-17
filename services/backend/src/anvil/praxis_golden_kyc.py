"""Qualified native KYC template binding; never grades a case in the authoring API."""

from anvil.db import one
from anvil.golden_component_qualification import installed
from anvil.golden_kyc_anvil import source_hash, validate
from anvil.golden_kyc_data import VERSION
from anvil.golden_kyc_evaluators import CRITERIA
from anvil.golden_kyc_paid_session import TOOLS
from anvil.golden_kyc_policy import RULES
from anvil.golden_kyc_tool_contract import tools
from anvil.praxis_generic_contract import digest


def conformance(c, project, spec):
    from anvil.golden_kyc_v7_export import product_template

    qualified = installed()
    if not qualified["ready"]:
        return {
            "passed": False,
            "origin": "installed_golden_qualification_missing",
            "requirements": qualified["missing"],
        }
    execution = spec.execution
    application_workflow = product_template(spec.model_dump())
    expected_mode = ("reusable_application_workflow" if application_workflow else "reusable_state_workflow"
                     if execution.environment.version == "2" else "per_application")
    if application_workflow:
        checks = qualified.get("evidence", {}).get("checks", {})
        required = ("kyc_product_routing", "all_original_rows_conserved", "per_application_policy_registry",
                    "shared_task_evaluator_binding")
        from anvil.golden_component_qualification import sha

        if any(type(checks.get(key)) is not dict or checks[key].get("status") != "passed"
               or not sha(checks[key].get("evidence_sha256")) for key in required):
            return {"passed": False, "origin": "application_workflow_component_qualification_missing",
                    "requirements": ["AV_KYC_PRODUCT_RUNTIME_QUALIFICATION_REQUIRED"]}
    if (
        (execution.catalogue_version, execution.environment.version) not in {("1.1.0", "1"), ("1.2.0", "2")}
        or set(e.criterion_id for e in execution.evaluators) != set(CRITERIA)
        or any(
            e.capability.id != "golden-kyc-rubric-v1"
            or e.capability.version != "1"
            or e.evidence_source != "run_evidence"
            for e in execution.evaluators
        )
        or set(t.id for t in execution.tools) != set(TOOLS)
        or digest([t.model_dump() for t in execution.tools]) != digest(tools())
        or execution.graph_node_types
    ):
        raise ValueError("Exact single-agent Golden tool and20criterion bindings required")
    if set(r.id for r in execution.rules) != set(RULES) or any(
        r.id not in RULES or r.version != VERSION or r.content_sha256 != digest(RULES[r.id])
        for r in execution.rules
    ):
        raise ValueError("Exact published bank-choice rule references required")
    imported = one(
        c,
        "SELECT * FROM banking.anvil_imports WHERE project_id=%s AND manifest->>'source_sha256'=%s "
        "AND COALESCE(manifest->>'task_mode','per_application')=%s ORDER BY created_at DESC,id DESC LIMIT 1",
        (project, source_hash(), expected_mode),
    )
    if not imported:
        raise ValueError("Current qualified Golden import required")
    validate(c, imported)
    if execution.environment.version == "2" and imported["manifest"].get("task_mode") != expected_mode:
        raise ValueError("Exact qualified reusable workflow import required; legacy state qualification cannot authorize application routing")
    return {
        "passed": True,
        "origin": "independently_qualified_installed_golden_runtime",
        "golden_source_sha256": source_hash(),
        "import_sha256": imported["manifest_sha256"],
        "evaluator_bindings_sha256": digest(imported["manifest"]["evaluators"]),
        "installed_review_sha256": qualified["evidence"]["review_receipt_sha256"],
        "installed_image_sha256": qualified["evidence"]["runtime_image_sha256"],
        "installed_broker_sha256": qualified["evidence"]["broker_source_sha256"],
        "case_grading_performed": False,
        "legal_acceptance": False,
        "model_performance": False,
        **({"export_selector_field": "product"} if application_workflow else {}),
    }
