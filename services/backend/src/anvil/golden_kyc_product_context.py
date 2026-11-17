"""Exact product-task input planning; no current policy or Run approval."""

import hashlib
from uuid import UUID

from anvil.dataset_export_contract import json_object
from anvil.db import one
from anvil.marketing_native_wire_bounds import bounded_json
from anvil.praxis_generic_contract import canonical, digest
from anvil.project_input_contract import MAX_BYTES


def load(c, project, resolved, reference):
    from anvil.golden_component_qualification import installed
    from anvil.golden_kyc_anvil import source_hash, validate
    from anvil.golden_kyc_resolved_store import policy_scope

    if type(reference) is not dict or set(reference) != {"id", "sha256"}:
        raise ValueError("Explicit immutable product input reference required")
    row = one(c, "SELECT * FROM anvil.kyc_resolved_input_versions WHERE project_id=%s AND id=%s",
              (project, UUID(reference["id"])))
    if not row or row["content_sha256"] != reference["sha256"] or row["resolution_id"] != resolved["resolution_id"]:
        raise ValueError("Exact original resolved input required")
    raw = row["body_canonical"].encode()
    if not 0 < len(raw) <= MAX_BYTES or hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("Exact original resolved input integrity required")
    body = json_object(raw)
    bounded_json(body, MAX_BYTES, max_nodes=150512, max_depth=12)
    if (canonical(body) != raw or body.get("schema_version") != "anvil.private-kyc-resolved-input.v1"
            or body.get("source_anvil_requirements")):
        raise ValueError("Original product input requirements remain unresolved")
    scope = policy_scope(c, UUID(str(project)), UUID(reference["id"]), resolved["task_key"], resolved["revision"])
    current_installation = installed()
    if (scope.payload_sha256 != resolved["private_reference_sha256"]
            or scope.runtime_source_sha256 != source_hash()
            or not current_installation["ready"]
            or scope.runtime_image_sha256 != current_installation.get("evidence", {}).get("runtime_image_sha256")
            or scope.workflow_product != resolved["binding"].get("case_selector", {}).get("value")
            or resolved["binding"].get("task_mode") != "reusable_application_workflow"):
        raise ValueError("Exact product task/runtime input changed")
    imported = one(c, "SELECT * FROM banking.anvil_imports WHERE project_id=%s AND id=%s", (project, row["case_import_id"]))
    if not imported or imported["manifest"].get("task_mode") != "reusable_application_workflow":
        raise ValueError("Exact original shared product environment required")
    validate(c, imported)
    if (scope.environment_binding_sha256 != imported["manifest"]["environment_manifest_sha256"]
            or scope.evaluator_bindings_sha256 != digest(imported["manifest"]["evaluators"])):
        raise ValueError("Exact shared environment/evaluator input changed")
    members = _members(body, resolved["task_key"], resolved["revision"], scope.workflow_product)
    return {"body": body, "members": members, "scope": scope, "import": imported, "reference": reference}


def _members(body, task_id, revision_id, product):
    rows = body["rows"]
    if (body["input_count"] != len(rows) or len({item["application_id"] for item in rows}) != len(rows)
            or any(item["status"] != "assigned_pending_policy_and_runtime_qualification" for item in rows)):
        raise ValueError("Complete unambiguous original application population required")
    members = [item for item in rows if item["task_id"] == task_id and item["revision_id"] == revision_id]
    if any(item["product"] != product for item in members):
        raise ValueError("Application must route by original product")
    return members


def assignment(context, application):
    selected = [row for row in context["members"] if row["application_id"] == application]
    if len(selected) != 1:
        raise ValueError("Application is outside the exact product task population")
    row, scope = selected[0], context["scope"]
    if row["product"] != scope.workflow_product or row["task_id"] != scope.task_id or row["revision_id"] != scope.revision_id:
        raise ValueError("Exact original product/task assignment required")
    return {"schema_version": "anvil.application-type-kyc-case-assignment.v1",
            "task_id": scope.task_id, "revision_id": scope.revision_id,
            "application_id": application, "application_sha256": row["application_sha256"],
            "product": row["product"], "governing_state": row["governing_state"],
            "resolved_input": context["reference"], "run_authority": "not_granted",
            "legal_acceptance": "not_established"}


def actor_context(context, actor, application=None):
    public = {"resolved_input": context["reference"], "case_selector": {"field": "product", "value": context["scope"].workflow_product},
              "application_count": len(context["members"]), "policy_selection": "actual_application_state_charter_and_assessment_date"}
    if application is not None:
        public["execution_assignment"] = assignment(context, application)
    return actor | {"execution_input": public}


