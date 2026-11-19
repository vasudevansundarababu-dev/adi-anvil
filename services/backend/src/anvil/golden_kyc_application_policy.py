"""Private original-application policy read; no caller-selected state or date.

All runtime SQL uses one existing bounded read-only connection and original
deadline. A registry candidate still grants no model, policy/legal or Run authority.
"""

import asyncio
import hashlib
from dataclasses import dataclass

from pydantic import TypeAdapter

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import Identifier, json_object
from anvil.db import digest as snapshot_digest
from anvil.golden_kyc_policy_registry import ProductRegistryScope, RegistryResult, load_async
from anvil.marketing_capture_database import remaining
from anvil.praxis_case_dataset import PolicyRef
from anvil.praxis_generic_contract import canonical, digest
from anvil.project_input_contract import MAX_BYTES, Application, actor_json

ORIGINAL_SQL = """
SELECT CASE WHEN octet_length(v.body_canonical)<=%s THEN v.body_canonical ELSE NULL END AS body,
 v.content_sha256,CASE WHEN octet_length(a.snapshot::text)<=%s THEN a.snapshot ELSE NULL END AS snapshot,
 a.snapshot_sha256,CASE WHEN octet_length(template.spec::text)<=2097152 THEN template.spec ELSE NULL END AS spec,
 template.spec_sha256,CASE WHEN octet_length(q.receipt::text)<=2097152 THEN q.receipt ELSE NULL END AS receipt,
 q.receipt_sha256,t.id AS resolved_task_id,t.private_reference_sha256,
 CASE WHEN octet_length(t.actor::text)<=2097152 THEN t.actor ELSE NULL END AS actor,t.actor_sha256,
 CASE WHEN octet_length(t.binding::text)<=2097152 THEN t.binding ELSE NULL END AS binding,t.binding_sha256
FROM anvil.kyc_resolved_input_versions v
JOIN banking.anvil_imports imported ON imported.project_id=v.project_id AND imported.id=v.case_import_id
JOIN banking.applications a ON a.project_id=v.project_id AND a.pack_id=imported.pack_id AND a.id=%s
JOIN anvil.praxis_resolved_tasks t ON t.project_id=v.project_id AND t.resolution_id=v.resolution_id
 AND t.task_key=%s AND t.revision=%s
JOIN anvil.praxis_template_versions template ON template.project_id=t.project_id AND template.id=t.template_id
JOIN anvil.praxis_template_qualifications q ON q.project_id=t.project_id AND q.template_id=template.id
 AND q.id::text=t.binding->>'qualification_id'
WHERE v.project_id=%s AND v.id=%s AND v.content_sha256=%s AND q.status='qualified'
 AND anvil.template_publication_current(q.project_id,q.template_id,q.receipt)
 AND q.receipt_sha256=%s AND NOT EXISTS(SELECT 1 FROM anvil.praxis_template_revocations revoked
 WHERE revoked.project_id=q.project_id AND revoked.qualification_id=q.id)
"""


@dataclass(frozen=True, slots=True)
class ApplicationPolicyResult:
    application_id: str
    resolved_input_sha256: str
    registry: RegistryResult
    application_sha256: str | None = None
    party_document_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()
    public_actor: dict | None = None
    resolved_task_id: str | None = None
    run_authority: str = "not_granted"


def _blocked(scope, application_id, code):
    return ApplicationPolicyResult(application_id, scope.resolved_input_sha256,
                                   RegistryResult("blocked", code, None))


async def load_application(connection, scope, application_id, *, absolute_deadline):
    """Application identity is the only selector; derive all policy applicability.

    The original scope must already be authenticated by the owning Anvil plan.
    No requested_product, example state, coverage count, charter override, date or
    policy list is accepted from an agent/SDK. Missing business documents remain
    in the evidence projection and are not used to drop rows from the population.
    """
    if type(scope) is not ProductRegistryScope:
        raise ValueError("Original unchanged-v1 product policy scope required")
    TypeAdapter(Identifier).validate_python(application_id, strict=True)
    scope_value = scope.model_dump(mode="json")
    bounded_json(scope_value, 16384, max_nodes=1000, max_depth=8)
    scope = ProductRegistryScope.model_validate_json(canonical(scope_value))
    remaining(absolute_deadline)
    remaining(connection.capture_deadline)
    hard = min(absolute_deadline, connection.capture_deadline)
    connection.capture_deadline = hard
    async with asyncio.timeout(remaining(hard)):
        row = await (await connection.execute(ORIGINAL_SQL, (
            MAX_BYTES, MAX_BYTES, application_id, scope.task_id, scope.revision_id, scope.project_id,
            scope.resolved_input_id, scope.resolved_input_sha256, scope.template_qualification_receipt_sha256,
        ))).fetchone()
        remaining(hard)
        if not row:
            return _blocked(scope, application_id, "AV_KYC_ORIGINAL_INPUT_AND_TEMPLATE_REQUIRED")
        try:
            raw = row["body"].encode()
            body = json_object(raw)
            bounded_json(body, MAX_BYTES, max_nodes=150512, max_depth=12)
            if (canonical(body) != raw or hashlib.sha256(raw).hexdigest() != scope.resolved_input_sha256
                    or row["content_sha256"] != scope.resolved_input_sha256 or body.get("source_anvil_requirements")
                    or body["source_package_sha256"] != scope.export_sha256
                    or body["scope"]["project_id"] != str(scope.project_id)
                    or body["scope"]["project_binding_id"] != str(scope.project_binding_id)
                    or any(body["scope"][key] != scope_value[key] for key in
                           ("project_binding_sha256", "runtime_source_sha256", "runtime_image_sha256",
                            "environment_binding_sha256", "evaluator_bindings_sha256"))):
                raise ValueError("input binding")
            tasks = [task for task in body["tasks"] if task["task_id"] == scope.task_id
                     and task["revision_id"] == scope.revision_id]
            members = [member for member in body["rows"] if member["application_id"] == application_id]
            if len(tasks) != 1 or len(members) != 1:
                raise ValueError("exact input membership")
            task, member = tasks[0], members[0]
            if (task["template"] != scope_value["template"]
                    or task["template_qualification_receipt_sha256"] != scope.template_qualification_receipt_sha256
                    or task["private_reference_sha256"] != scope.payload_sha256
                    or task["review_receipt_sha256"] != scope.workflow_review_receipt_sha256
                    or task["case_selector"] != {"field": "product", "value": scope.workflow_product}
                    or member["task_id"] != scope.task_id or member["revision_id"] != scope.revision_id
                    or member["status"] != "assigned_pending_policy_and_runtime_qualification"):
                return _blocked(scope, application_id, "AV_KYC_APPLICATION_WORKFLOW_REQUIRED")
            snapshot, spec, receipt = row["snapshot"], row["spec"], row["receipt"]
            actor, binding = row["actor"], row["binding"]
            for value, bound in ((snapshot, MAX_BYTES), (spec, 2097152), (receipt, 2097152), (actor,2097152), (binding,2097152)):
                bounded_json(value, bound, max_nodes=100000, max_depth=24)
            actor_json(snapshot)
            if (snapshot_digest(snapshot) != row["snapshot_sha256"] or snapshot["id"] != application_id
                    or member["application_sha256"] != row["snapshot_sha256"]
                    or member["product"] != snapshot["product"] or snapshot["product"] != scope.workflow_product
                    or member["governing_state"] != snapshot["governing_state"]
                    or digest(spec) != scope.template.sha256 or row["spec_sha256"] != scope.template.sha256
                    or spec["template_id"] != scope.template.id or spec["version"] != scope.template.version
                    or digest(receipt) != row["receipt_sha256"]
                    or receipt["template_sha256"] != scope.template.sha256
                    or not (receipt.get("publication_verified") is True
                            or receipt.get("publication_accepted") is True
                            and receipt.get("publication_basis", {}).get("kind") == "po_attested_offline")
                    or receipt.get("conformance", {}).get("passed") is not True
                    or receipt.get("conformance", {}).get("export_selector_field") != "product"
                    or row["private_reference_sha256"] != scope.payload_sha256
                    or digest(actor) != row["actor_sha256"] or digest(binding) != row["binding_sha256"]
                    or binding.get("actor_sha256") != row["actor_sha256"]
                    or binding.get("source_sha256") != receipt["source_sha256"]
                    or binding.get("task_mode") != "reusable_application_workflow"
                    or binding.get("case_selector") != task["case_selector"]
                    or binding.get("qualification_sha256") != scope.template_qualification_receipt_sha256):
                raise ValueError("original hashes")
            from anvil.praxis_template_source import source_hash

            if receipt["source_sha256"] != source_hash():
                return _blocked(scope, application_id, "AV_KYC_CURRENT_TEMPLATE_SOURCE_REQUIRED")
            application = Application.model_validate(snapshot)
            federal = tuple(PolicyRef.model_validate(value) for value in spec["execution"]["federalPolicies"])
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            return _blocked(scope, application_id, "AV_KYC_ORIGINAL_APPLICATION_INTEGRITY_REQUIRED")
        remaining(hard)
        result = await load_async(connection, scope, absolute_deadline=hard,
                                  product=application.product, governing_state=application.governing_state,
                                  charter_profile=application.charter_applicability.profile,
                                  assessment_date=application.assessment_date, federal_refs=federal)
        evidence = tuple((party.id, tuple(sorted(document.id for document in application.documents
                                                if document.party_id == party.id))) for party in application.parties)
        remaining(hard)
        return ApplicationPolicyResult(application_id, scope.resolved_input_sha256, result,
                                       row["snapshot_sha256"], evidence, actor, str(row["resolved_task_id"]))


async def load_public_application(connection, scope, application_id, *, absolute_deadline):
    """Original application -> unique current policy -> exact public artifact bytes.

    Both reads share the same original scoped connection and cutoff. A missing,
    overlapping, revoked or expired policy/materialization blocks delivery; this
    never falls back to legacy state text or creates qualification/Run authority.
    """
    from anvil.golden_kyc_policy_delivery import PolicyDelivery
    from anvil.golden_kyc_policy_delivery import load_async as load_text

    result = await load_application(connection, scope, application_id, absolute_deadline=absolute_deadline)
    if result.registry.requirement:
        return result, PolicyDelivery("blocked", result.registry.requirement)
    if len(result.registry.qualification_record_ids) != 1:
        return result, PolicyDelivery("blocked", "AV_KYC_POLICY_QUALIFICATION_REQUIRED")
    delivery = await load_text(connection, scope, application_id, result.registry.qualification_record_ids[0],
                               absolute_deadline=absolute_deadline)
    return result, delivery
