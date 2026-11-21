"""Private append-only input custody; never API registration or Run readiness.

The caller owns one existing authorized transaction and its outcome. No database
factory, role, credentials, retry, publication or model operation is created.
"""

import hashlib
from uuid import UUID

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import json_object
from anvil.db import digest as persistent_digest
from anvil.db import uid
from anvil.golden_kyc_resolved_dataset import BoundRow, ResolvedInput
from anvil.praxis_generic_contract import TemplateRef, canonical
from anvil.praxis_template_registry import lookup
from anvil.project_input_contract import MAX_BYTES


class StaleProductBinding(ValueError):
    """A frozen binding needs explicit refresh, never automatic replacement."""


def persist_candidate(connection, project, user, resolution_id, case_import_id, candidate):
    """One immutable append/idempotent lookup in the caller's transaction.

    Missing template/runtime qualification is Anvil-owned. This is not a public
    resolve endpoint, a qualification writer or a same-operation retry loop.
    Returning this result inside a transaction does not observe COMMIT.
    """
    if (any(type(value) is not UUID for value in (project, user, resolution_id, case_import_id))
            or type(candidate) is not ResolvedInput or type(candidate.canonical_body) is not bytes
            or type(candidate.rows) is not tuple or not 0 < len(candidate.rows) <= 10000
            or not 0 < len(candidate.canonical_body) <= MAX_BYTES
            or candidate.status != "candidate_input_binding_not_qualified" or candidate.run_authority != "not_granted"):
        raise ValueError("Original authorized scope and complete immutable input candidate required")
    raw = candidate.canonical_body
    fingerprint = hashlib.sha256(raw).hexdigest()
    body = json_object(raw)
    bounded_json(body, MAX_BYTES, max_nodes=150512, max_depth=12)
    expected_rows = [{"application_id": row.application_id, "application_sha256": row.application_sha256,
                      "governing_state": row.governing_state, "product": row.product,
                      "task_id": row.task_id, "revision_id": row.revision_id, "status": row.status}
                     for row in candidate.rows if type(row) is BoundRow]
    if (canonical(body) != raw or fingerprint != candidate.sha256
            or body.get("schema_version") != "anvil.private-kyc-resolved-input.v1"
            or body.get("runtime_qualified") is not False or body.get("policy_qualified") is not False
            or body.get("run_authority") != "not_granted"
            or len(expected_rows) != len(candidate.rows) or expected_rows != body.get("rows")
            or type(body.get("scope")) is not dict or body["scope"].get("project_id") != str(project)):
        raise ValueError("Exact original input candidate identity changed")
    binding_id = UUID(body["scope"]["project_binding_id"])
    if not connection.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,)).fetchone():
        raise ValueError("Original project input custody unavailable")
    tasks = body.get("tasks")
    if type(tasks) is not list or not 0 < len(tasks) <= 200:
        raise ValueError("Complete exact original source task references required")
    for task in tasks:
        if type(task) is not dict:
            raise ValueError("Original typed source task reference required")
        reference = TemplateRef.model_validate(task["template"])
        current = lookup(connection, project, reference)
        if (not current or current.get("qualified") is not True or current.get("integrity") is not True
                or current["qualification"]["receipt_sha256"] != task["template_qualification_receipt_sha256"]):
            raise ValueError("Anvil current exact template qualification required")
    old = connection.execute(
        "SELECT id,body_canonical,content_sha256 FROM anvil.kyc_resolved_input_versions "
        "WHERE project_id=%s AND resolution_id=%s AND project_binding_id=%s AND case_import_id=%s AND content_sha256=%s",
        (project, resolution_id, binding_id, case_import_id, fingerprint),
    ).fetchone()
    if old:
        if old["body_canonical"].encode() != raw or old["content_sha256"] != fingerprint:
            raise ValueError("Stored immutable input context integrity changed")
        identifier = old["id"]
    else:
        identifier = uid()
        connection.execute(
            "INSERT INTO anvil.kyc_resolved_input_versions"
            "(id,project_id,resolution_id,project_binding_id,case_import_id,body_canonical,content_sha256,created_by) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (identifier, project, resolution_id, binding_id, case_import_id, raw.decode(), fingerprint, user),
        )
    return {"schema_version": "anvil.private-kyc-input-custody.v1", "id": str(identifier),
            "content_sha256": fingerprint, "resolution_id": str(resolution_id),
            "project_binding_id": str(binding_id), "case_import_id": str(case_import_id),
            "input_count": body["input_count"], "status": "stored_candidate_not_qualified",
            "commit_observed": False, "ready": False, "run_authority": "not_granted"}


def policy_scope(connection, project, input_id, task_id, revision_id):
    """Derive private qualification scope from exact stored original bindings.

    This is a read, never a domain/runtime approval or qualification INSERT.
    Callers may not substitute scope hashes, a latest dataset or a new template.
    """
    from anvil.golden_kyc_policy_registry import ProductRegistryScope

    if type(project) is not UUID or type(input_id) is not UUID:
        raise ValueError("Exact original input scope required")
    record = connection.execute(
        "SELECT v.id,v.body_canonical,v.content_sha256,b.id AS binding_id,"
        "b.snapshot,b.snapshot_sha256 FROM anvil.kyc_resolved_input_versions v "
        "JOIN anvil.project_binding_versions b ON b.project_id=v.project_id AND b.id=v.project_binding_id "
        "WHERE v.project_id=%s AND v.id=%s", (project, input_id),
    ).fetchone()
    if not record:
        raise ValueError("Anvil immutable input binding required")
    raw = record["body_canonical"].encode()
    if not 0 < len(raw) <= MAX_BYTES or hashlib.sha256(raw).hexdigest() != record["content_sha256"]:
        raise ValueError("Stored original input binding integrity changed")
    body = json_object(raw)
    bounded_json(body, MAX_BYTES, max_nodes=150512, max_depth=12)
    bounded_json(record["snapshot"], MAX_BYTES, max_nodes=100000, max_depth=16)
    if (canonical(body) != raw or body.get("source_anvil_requirements")
            or persistent_digest(record["snapshot"]) != record["snapshot_sha256"]
            or body["scope"]["project_id"] != str(project)
            or body["scope"]["project_binding_id"] != str(record["binding_id"])
            or body["scope"]["project_binding_sha256"] != record["snapshot_sha256"]):
        raise ValueError("Anvil original input/runtime binding requirements unresolved")
    tasks = [task for task in body["tasks"] if task["task_id"] == task_id and task["revision_id"] == revision_id]
    if len(tasks) != 1:
        raise ValueError("Exact original workflow task revision required")
    task = tasks[0]
    reference = TemplateRef.model_validate(task["template"])
    current = lookup(connection, project, reference)
    if (not current or current.get("qualified") is not True
            or current["qualification"]["receipt_sha256"] != task["template_qualification_receipt_sha256"]):
        raise StaleProductBinding("Anvil current exact template qualification required")
    scope = body["scope"]
    return ProductRegistryScope.model_validate_json(canonical({
        **scope, "source_sha256": record["snapshot"]["source_sha256"],
        "export_sha256": body["source_package_sha256"], "task_id": task_id, "revision_id": revision_id,
        "workflow_product": task["case_selector"]["value"], "payload_sha256": task["private_reference_sha256"],
        "workflow_review_receipt_sha256": task["review_receipt_sha256"],
        "export_contract": "praxis.authored-task-export.v1", "selector_field": "product",
        "template": task["template"], "template_qualification_receipt_sha256": task["template_qualification_receipt_sha256"],
        "resolved_input_id": str(record["id"]), "resolved_input_sha256": record["content_sha256"],
    }))
