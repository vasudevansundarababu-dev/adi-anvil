"""Original product trial policy delivery; no legacy state-text fallback."""

from anvil.db import digest as snapshot_digest
from anvil.golden_kyc_policy_delivery import load_async as load_text
from anvil.golden_kyc_policy_registry import ProductRegistryScope, load_async
from anvil.marketing_native_wire_bounds import bounded_json, remaining
from anvil.praxis_case_dataset import PolicyRef
from anvil.praxis_generic_contract import canonical
from anvil.project_input_contract import MAX_BYTES, Application, actor_json


async def public_policy(c, project, trial, generation, governing_state, *, absolute_deadline):
    from anvil.golden_kyc_source import source_hash as runtime_source
    from anvil.praxis_template_source import source_hash as template_source

    remaining(absolute_deadline)
    row = await (await c.execute("SELECT banking.product_policy_trial_binding(%s,%s) AS value", (trial,generation))).fetchone()
    remaining(absolute_deadline)
    value = row["value"] if row else None
    if not value:
        raise ValueError("Exact current original product trial binding required")
    bounded_json(value, MAX_BYTES, max_nodes=100000, max_depth=24)
    scope = ProductRegistryScope.model_validate_json(canonical(value["policy_scope"]))
    snapshot = value["snapshot"]
    actor_json(snapshot)
    application = Application.model_validate(snapshot)
    if (str(scope.project_id) != str(project) or scope.runtime_source_sha256 != runtime_source()
            or value["template_qualification_source_sha256"] != template_source()
            or snapshot_digest(snapshot) != value["snapshot_sha256"]
            or application.id != value["application_id"] or application.product != scope.workflow_product
            or application.governing_state != governing_state
            or value["native_binding"].get("resolved_input") != value["resolved_input"]):
        raise ValueError("Original product application or policy source changed")
    registry = await load_async(c, scope, absolute_deadline=absolute_deadline, product=application.product, governing_state=application.governing_state,
                    charter_profile=application.charter_applicability.profile, assessment_date=application.assessment_date,
                    federal_refs=tuple(PolicyRef.model_validate(ref) for ref in value["federal_refs"]))
    if registry.requirement or len(registry.qualification_record_ids) != 1:
        raise ValueError(registry.requirement or "AV_KYC_POLICY_QUALIFICATION_REQUIRED")
    delivery = await load_text(c, scope, application.id, registry.qualification_record_ids[0], absolute_deadline=absolute_deadline)
    if delivery.requirement or not delivery.public:
        raise ValueError(delivery.requirement or "AV_KYC_EXACT_POLICY_TEXT_PROVISIONING_REQUIRED")
    return delivery.public
