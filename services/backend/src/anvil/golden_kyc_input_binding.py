"""Anvil-owned immutable v7 input planning, never task or domain approval."""

from uuid import UUID

from fastapi import HTTPException

from anvil.db import digest as db_digest
from anvil.db import one
from anvil.golden_component_qualification import installed
from anvil.golden_kyc_anvil import source_hash, validate
from anvil.golden_kyc_resolved_dataset import BindingScope, ReviewedTask, resolve_candidate
from anvil.golden_kyc_resolved_store import persist_candidate
from anvil.golden_kyc_v7_candidate import DecodedCandidate, DecodedTask
from anvil.praxis_case_dataset import CaseDataset
from anvil.praxis_generic_contract import digest
from anvil.project_bindings import group


def blocked(code):
    raise HTTPException(409, {"code": code, "owner": "anvil", "ready": False, "run_authority": "not_granted"})


def authenticated_resolution(c, project, resolution):
    """Verify server-stored upload provenance, never ZIP-authored approval.

    Offline Admin uploads retain their user-session identity. This does not
    authenticate Authoring publication or grant policy/runtime qualification.
    """
    receipt = resolution["receipt"]
    actor = receipt.get("authenticated_actor", {})
    if type(actor) is not dict:
        blocked("AV_KYC_AUTHENTICATED_SOURCE_PROVENANCE_REQUIRED")
    if (resolution["project_id"] != project
            or digest(receipt) != resolution["receipt_sha256"]
            or receipt.get("package_sha256") != resolution["package_sha256"]
            or receipt.get("source_sha256") is None
            or actor.get("sponsor_user_id") != str(resolution["created_by"])):
        blocked("AV_KYC_AUTHENTICATED_SOURCE_PROVENANCE_REQUIRED")
    if actor.get("kind") == "user_session" and actor.get("client_id") is None:
        sponsor = one(c, "SELECT u.id FROM anvil.users u WHERE u.id=%s AND u.active "
                      "AND EXISTS(SELECT 1 FROM anvil.memberships m WHERE m.user_id=u.id "
                      "AND m.project_id=%s AND m.active AND m.role='admin')",
                      (resolution["created_by"], project))
        if sponsor:
            return
    elif actor.get("kind") == "workload_identity" and actor.get("client_id"):
        return
    blocked("AV_KYC_AUTHENTICATED_SOURCE_PROVENANCE_REQUIRED")


def bind(c, project, user, *, resolution_id, case_import_id, preparation_binding_id):
    """Freeze exact original B0/data before packages and a separate Run B1.

    Authenticated Authoring approval is source provenance only. The actual
    immutable Anvil resolution receipt is retained as such, never promoted to
    Anvil human/domain approval or made by hashing an opaque review URI.
    """
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    resolution = one(c, "SELECT * FROM anvil.praxis_export_resolutions WHERE project_id=%s AND id=%s", (project, resolution_id))
    imported = one(c, "SELECT * FROM banking.anvil_imports WHERE project_id=%s AND id=%s", (project, case_import_id))
    preparation = one(c, "SELECT * FROM anvil.project_binding_versions WHERE project_id=%s AND id=%s", (project, preparation_binding_id))
    if not resolution or not imported or not preparation:
        blocked("AV_KYC_EXACT_SOURCE_INPUT_PREPARATION_REQUIRED")
    receipt = resolution["receipt"]
    authenticated_resolution(c, project, resolution)
    from anvil.praxis_template_registry import source_hash as export_source_hash

    if receipt["source_sha256"] != export_source_hash():
        blocked("AV_KYC_CURRENT_SOURCE_RESOLUTION_REQUIRED")
    if (db_digest(preparation["snapshot"]) != preparation["snapshot_sha256"]
            or imported["manifest"].get("task_mode") != "reusable_application_workflow"):
        blocked("AV_KYC_PRODUCT_INPUT_RUNTIME_REQUIRED")
    validate(c, imported)
    qualified = installed()
    if not qualified["ready"]:
        blocked("AV_KYC_INSTALLED_COMPONENT_QUALIFICATION_REQUIRED")
    source = group(c, project, preparation["task_group_id"])
    if preparation["snapshot"]["source_sha256"] != source["content_sha256"] or db_digest(source["content"]) != source["content_sha256"]:
        blocked("AV_KYC_PREPARATION_SOURCE_CHANGED")
    packages = source["content"].get("source_origin", {}).get("packages", [])
    if (len(packages) != 1 or packages[0] != {"id": resolution["package_key"], "version": resolution["version"],
                                           "sha256": resolution["package_sha256"]}):
        blocked("AV_KYC_COMPLETE_RESOLUTION_REQUIRED")
    rows = c.execute("SELECT r.*,t.template_key,t.version,t.spec_sha256 FROM anvil.praxis_resolved_tasks r "
                     "JOIN anvil.praxis_template_versions t ON t.project_id=r.project_id AND t.id=r.template_id "
                     "WHERE r.project_id=%s AND r.resolution_id=%s ORDER BY r.task_key,r.revision",
                     (project, resolution_id)).fetchall()
    source_tasks = {(t["task_id"], t["revision_id"]): t for t in source["content"]["tasks"]}
    if not 0 < len(rows) <= 200 or len(rows) != len(source_tasks):
        blocked("AV_KYC_COMPLETE_SOURCE_TASK_MEMBERSHIP_REQUIRED")
    decoded, reviewed, manifest_sha = [], [], set()
    for row in rows:
        value = row["binding"]
        task = source_tasks.get((row["task_key"], row["revision"]))
        provenance = value.get("source_review_provenance")
        if (not task or digest(value) != row["binding_sha256"] or digest(row["actor"]) != row["actor_sha256"]
                or value.get("task_mode") != "reusable_application_workflow" or row["version"] < 7
                or type(provenance) is not dict or set(provenance) != {"status", "revision_id", "receipt_ref"}
                or provenance["status"] != "approved" or provenance["revision_id"] != row["revision"]
                or type(provenance["receipt_ref"]) is not str or not provenance["receipt_ref"]
                or task["source"]["review"] != provenance or task["payload_sha256"] != row["private_reference_sha256"]
                or task["case_selector"] != value["case_selector"]):
            blocked("AV_KYC_EXACT_APPROVED_SOURCE_PROVENANCE_REQUIRED")
        if not any(b["id"] == str(row["id"]) and b["task_id"] == row["task_key"]
                   and b["binding_sha256"] == row["binding_sha256"] for b in receipt["bindings"]):
            blocked("AV_KYC_SOURCE_RECEIPT_TASK_BINDING_REQUIRED")
        manifest_sha.add(value["source_manifest_sha256"])
        item = DecodedTask(row["task_key"], row["revision"], row["template_key"], row["version"], row["spec_sha256"],
                           value["qualification_sha256"], value["case_selector"]["value"], value["authored_sha256"],
                           row["actor_sha256"], row["private_reference_sha256"], provenance["receipt_ref"], None)
        decoded.append(item)
        reviewed.append(ReviewedTask(item, resolution["receipt_sha256"], "source_resolution_receipt"))
    if len(manifest_sha) != 1:
        blocked("AV_KYC_EXACT_SOURCE_MANIFEST_REQUIRED")
    dataset = CaseDataset.model_validate(imported["manifest"]["case_dataset_manifest"])
    snapshots = c.execute("SELECT id,snapshot,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id",
                          (project, imported["pack_id"])).fetchall()
    if preparation["snapshot"].get("execution_data"):
        from anvil.project_inputs import execution_overlay

        overlay = execution_overlay(c, project, preparation["snapshot"]["execution_data"])
        if (overlay["family"] != "kyc" or overlay["pack_id"] != str(imported["pack_id"])
                or {item["id"]: item["snapshot_sha256"] for item in overlay["cases"]}
                != {item["id"]: item["snapshot_sha256"] for item in snapshots}):
            blocked("AV_KYC_PREPARATION_COMPLETE_INPUT_POPULATION_REQUIRED")
    scope = BindingScope(project, UUID(str(preparation["id"])), preparation["snapshot_sha256"], source_hash(),
                         qualified["evidence"]["runtime_image_sha256"], imported["manifest"]["environment_manifest_sha256"],
                         digest(imported["manifest"]["evaluators"]))
    candidate = resolve_candidate(scope, DecodedCandidate(resolution["package_sha256"], next(iter(manifest_sha)), tuple(decoded)),
                                  tuple(reviewed), dataset, dataset.reference(), snapshots)
    stored = persist_candidate(c, project, user, resolution_id, case_import_id, candidate)
    return stored | {"review_provenance_kind": "source_resolution_receipt", "anvil_human_review_approved": False,
                     "policy_review": "not_granted", "package_preparation": "separate", "ready": False}
