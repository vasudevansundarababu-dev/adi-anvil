"""New owner-rule controls; actual fixture inputs and manufactured local records.

No API, database, native execution or model benchmark is exercised.
"""

from copy import deepcopy

import pytest
from test_marketing_world_descriptor_services import source

from anvil.marketing_task2_contract import WIRE_ROLES
from anvil.marketing_task2_runtime import Task2Controller
from anvil.marketing_world_readiness import assess
from anvil.praxis_generic_contract import digest


def save(controller, role, kind, identifier, content, *, version=0):
    value = controller.call(controller.credential(WIRE_ROLES[role]), controller.generation, kind,
                            {"id": identifier, "expected_version": version,
                             "idempotency_key": f"{kind}:{identifier}:{version}", "content": content})
    assert value.get("status") != "denied"
    return {"id": value["id"], "version": value["version"], "sha256": digest(value)}


def setup(case="GT2-R01", *, finding=None, recommendation="ready", cap=200000):
    _, _, execution, sources = source(case)
    controller = Task2Controller(case, records={}, start="2027-02-12T12:00:00Z",
                                 outcome="positive", budget_minor=20000000)
    contract = sources["case"]["experiment_proposal_contract"]
    contract_ref = {"id": contract["id"], "version": contract["version"], "sha256": digest(contract)}
    experiment = save(controller, "performance", "experiments", "test-experiment",
                      {"source_contract_ref": contract_ref, "parameters": deepcopy(contract)})
    conditional = sources["conditional_campaign_approval_sources"]["positive"]
    action = {"service_contract": sources["schema_version"], "mode": "conditional_reuse_campaign",
              "experiment_ref": experiment, "experiment_contract_ref": contract_ref,
              "scope": deepcopy(conditional["scope"]), "creative_refs": deepcopy(conditional["creative_refs"]),
              "planned_cap_usd_minor": cap}
    action_ref = save(controller, "orchestrator", "readiness-requests", "test-readiness-action", action)
    findings = []
    if finding is not None:
        findings = [save(controller, "policy", "campaign-findings", "test-findings",
                         {"service_contract": sources["schema_version"], "action_ref": action_ref, "findings": [finding]})]
    assessment = {"service_contract": sources["schema_version"], "action_ref": action_ref,
                  "recommendation": recommendation, "finding_refs": findings}
    policy_ref = save(controller, "policy", "readiness-assessments", "test-policy", assessment)
    content = {**action, "readiness_ref": policy_ref}
    request = save(controller, "orchestrator", "approval-requests", "test-approval", content)
    node = next(n for n in execution["workflow_graph"]["nodes"] if n["id"] == "approver")
    inputs = {"approval_request": {"request_ref": request}}
    return controller, execution, node, inputs, sources, action_ref, assessment, content


@pytest.mark.parametrize("case", ["GT2-R01", "GT2-R02"])
def test_saved_review_and_actual_source_checks_are_readiness_not_authority(case):
    controller, execution, node, inputs, sources, *_ = setup(case)
    before = digest(controller.capture())
    result = assess(controller, execution, node, inputs, sources)
    assert result["ready"] is True and result["issues"] == []
    assert result["campaign_authority_issued"] is False
    assert digest(controller.capture()) == before
    assert not controller._approvals and not controller._reservations


def test_actual_saved_assessment_hold_cannot_be_relabelled_ready():
    controller, execution, node, inputs, sources, *_ = setup(recommendation="hold")
    result = assess(controller, execution, node, inputs, sources)
    assert result["ready"] is False
    assert any(i["code"] == "saved_policy_assessment_not_ready_for_exact_submitted_versions" for i in result["issues"])


def test_stale_action_reference_denies_an_existing_ready_assessment():
    controller, execution, node, inputs, sources, action_ref, *_ = setup()
    old = controller._objects[action_ref["id"]]
    save(controller, "orchestrator", "readiness-requests", old["id"], deepcopy(old["content"]), version=old["version"])
    assert assess(controller, execution, node, inputs, sources)["ready"] is False


def test_ready_flag_does_not_override_expired_rights_or_retroactive_action():
    controller, execution, node, inputs, sources, *_ = setup()
    controller.advance("2027-04-01T00:00:00Z")
    result = assess(controller, execution, node, inputs, sources)
    assert result["ready"] is False
    assert any(i["code"] == "rights_scope_or_validity_mismatch" for i in result["issues"])


def test_resolved_flag_without_real_evidence_does_not_resolve_mandatory_finding():
    finding = {"id": "F1", "mandatory": True, "check": "claims", "status": "resolved", "evidence_refs": []}
    controller, execution, node, inputs, sources, *_ = setup(finding=finding)
    result = assess(controller, execution, node, inputs, sources)
    assert result["ready"] is False
    assert any(i["code"] == "mandatory_finding_has_no_passing_underlying_resolution" for i in result["issues"])


def test_mandatory_finding_resolution_uses_exact_actual_source_record():
    _, _, _, sources = source()
    claim = sources["case"]["claim_evidence"][0]
    finding = {"id": "F1", "mandatory": True, "check": "claims", "status": "resolved",
               "evidence_refs": [{"id": claim["id"], "version": claim["version"], "sha256": digest(claim)}]}
    controller, execution, node, inputs, sources, *_ = setup(finding=finding)
    assert assess(controller, execution, node, inputs, sources)["ready"] is True


def test_mandatory_finding_cannot_be_removed_by_revision():
    finding = {"id": "F1", "mandatory": True, "check": "claims", "status": "open", "evidence_refs": []}
    controller, execution, node, inputs, sources, action_ref, assessment, content = setup(finding=finding)
    updated = save(controller, "policy", "campaign-findings", "test-findings",
                   {"service_contract": sources["schema_version"], "action_ref": action_ref, "findings": []}, version=1)
    assessment["finding_refs"] = [updated]
    policy = save(controller, "policy", "readiness-assessments", "test-policy", assessment, version=1)
    content["readiness_ref"] = policy
    inputs["approval_request"]["request_ref"] = save(controller, "orchestrator", "approval-requests", "test-approval", content, version=1)
    result = assess(controller, execution, node, inputs, sources)
    assert result["ready"] is False
    assert any(i["code"] == "mandatory_finding_removed_or_downgraded" for i in result["issues"])


def test_scope_cap_contradiction_denies_ready_recommendation():
    controller, execution, node, inputs, sources, *_ = setup(cap=100000)
    result = assess(controller, execution, node, inputs, sources)
    assert result["ready"] is False
    assert any(i["code"] == "conditional_controller_scope_version_or_cap_mismatch" for i in result["issues"])


def test_current_rejection_cannot_be_bypassed_by_ready_flag():
    controller, execution, node, inputs, sources, *_ = setup()
    # Manufactured contradictory source is a negative helper control only;
    # it could not pass the independently pinned v2 source definition.
    ref = sources["conditional_campaign_approval_sources"]["positive"]["creative_refs"][0]
    sources["case"]["approval_fixtures"].append({"target_id": ref["id"], "target_version": ref["version"],
                                               "decision": "REJECTED", "released_at": "2027-02-12T00:00:00Z"})
    result = assess(controller, execution, node, inputs, sources)
    assert result["ready"] is False
    assert any(i["code"] == "current_rejection_revision_or_supersession" for i in result["issues"])
