"""New reuse-route source controls, not SQL/native/Task3 execution evidence."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_marketing_world_descriptor_services import request
from test_marketing_world_readiness import save, setup

from anvil.db import digest as stored_digest
from anvil.marketing_paid_world import BaselineDescriptors
from anvil.marketing_task2_persistence import freeze
from anvil.marketing_task2_tools import execute
from anvil.marketing_task2_workflow import advance, initial
from anvil.marketing_world_service_api import effect
from anvil.marketing_world_services import baseline_manifest
from anvil.praxis_generic_contract import digest


def released_sources(controller, sources):
    controller._initial["task3-deliveries"] = [
        {"actor_visible": True, "outcome_binding": None, "released_at": row["released_at"], "public": deepcopy(row)}
        for row in sources["case"]["task3_delivery_fixtures"] if row.get("locale") == "en-US"]


def attachment(controller):
    return {"world_binding_id": str(uuid4()), "world_binding_sha256": "b" * 64,
            "episode_id": controller.trial_id, "generation": controller.generation, "case_id": controller.case_id}


def release(controller, sources, bound, week=1):
    return {"week": week, "baseline_delivery_manifest": baseline_manifest(controller, sources, bound, week)}


@pytest.mark.parametrize("case", ["GT2-R01", "GT2-R02"])
def test_direct_reuse_policy_route_uses_actual_existing_descriptors_without_task3(case):
    controller, execution, _, _, sources, *_ = setup(case)
    released_sources(controller, sources)
    window = release(controller, sources, attachment(controller))
    state = initial({"case_id": case}, window)
    state.update(pending=["route"])
    state["artifacts"]["campaign_plan"] = {"action": "change"}
    calls = []

    def adapter(node, inputs, week, visit):
        calls.append(node["id"])
        assert inputs["delivery_manifest"]["provenance"] == "PREEXISTING_STANDALONE_DESCRIPTOR_FIXTURES"
        return {"artifact": {"outcome": "clear"}, "receipt": {"input_sha256": stored_digest(inputs)}}

    state = advance(execution, state, adapter, lambda _: None)
    state = advance(execution, state, adapter, lambda _: None)
    assert calls == ["policy_step"]
    assert state["terminal"] is None
    assert state["artifacts"]["delivery_manifest"]["new_task3_effect"] is False
    assert not controller._approvals and not controller._reservations


def test_week_reset_replaces_prior_manifest_with_current_baseline():
    controller, execution, _, _, sources, *_ = setup()
    released_sources(controller, sources)
    bound = attachment(controller)
    state = initial({"case_id": controller.case_id}, release(controller, sources, bound))
    state["pending"] = ["campaign_over"]
    state["artifacts"]["weekly_review"] = {"campaign_complete": False}
    state["artifacts"]["delivery_manifest"] = {"prior_week_task3_control": True}
    state = advance(execution, state, lambda *_: None, lambda week: release(controller, sources, bound, week))
    assert state["week"] == 2
    assert state["artifacts"]["delivery_manifest"]["week"] == 2
    assert "prior_week_task3_control" not in state["artifacts"]["delivery_manifest"]


def test_no_released_delivery_stays_missing():
    controller, _, _, _, sources, *_ = setup()
    controller._initial["task3-deliveries"] = []
    window = release(controller, sources, attachment(controller))
    assert window["baseline_delivery_manifest"] is None
    assert "delivery_manifest" not in initial({"case_id": controller.case_id}, window)["artifacts"]


def test_open_mandatory_finding_blocks_baseline_until_source_linked_correction():
    finding = {"id": "F1", "mandatory": True, "check": "claims", "status": "open", "evidence_refs": []}
    controller, _, _, _, sources, action_ref, *_ = setup(finding=finding)
    released_sources(controller, sources)
    bound = attachment(controller)
    before = baseline_manifest(controller, sources, bound, 1)
    denied = {r["id"] for r in sources["conditional_campaign_approval_sources"]["positive"]["creative_refs"]}
    assert not denied & {r["creative_id"] for r in before["deliveries"]}
    claim = sources["case"]["claim_evidence"][0]
    finding.update(status="resolved", evidence_refs=[{"id": claim["id"], "version": claim["version"], "sha256": digest(claim)}])
    save(controller, "policy", "campaign-findings", "test-findings",
         {"service_contract": sources["schema_version"], "action_ref": action_ref, "findings": [finding]}, version=1)
    after = baseline_manifest(controller, sources, bound, 1)
    assert len(after["deliveries"]) == 6
    assert after["campaign_authority_issued"] is False


def test_current_rejection_withholds_that_baseline_version():
    controller, _, _, _, sources, *_ = setup()
    released_sources(controller, sources)
    ref = sources["conditional_campaign_approval_sources"]["positive"]["creative_refs"][0]
    sources["case"]["approval_fixtures"].append({"target_id": ref["id"], "target_version": ref["version"],
                                               "decision": "REJECTED", "released_at": "2027-02-12T00:00:00Z"})
    manifest = baseline_manifest(controller, sources, attachment(controller), 1)
    assert ref["id"] not in {r["creative_id"] for r in manifest["deliveries"]}


def test_mocked_api_service_return_replaces_baseline_without_physical_claims():
    controller, execution, node, inputs, sources, _ = request()
    released_sources(controller, sources)
    bound = attachment(controller)
    project, job, plan, actor, source_id, qualification_id = [str(uuid4()) for _ in range(6)]
    state, state_sha = freeze(controller)
    row = {**bound, "source_id": source_id, "qualification_id": qualification_id,
           "controller_state": state, "controller_state_sha256": state_sha}
    intent = {"id": str(uuid4()), "node_sha256": digest(node), "input_sha256": digest(inputs)}
    commits = []

    class MockSQL:
        def execute(self, sql, values):
            if "private_world_service_context" in sql:
                return SimpleNamespace(fetchone=lambda: {"value": {"session": row, "effect": intent}})
            assert "commit_private_world_service" in sql
            commits.append(values)
            return SimpleNamespace(fetchone=lambda: {"allowed": True})

    claim = SimpleNamespace(job_id=job, lease_token=str(uuid4()), plan_id=plan, project_id=project, actor_id=actor,
                            value={**{k: bound[k] for k in ("world_binding_id", "world_binding_sha256", "episode_id", "generation")},
                                   "node_id": "task3", "week": 1, "visit": 1, "inputs": inputs})
    reply = effect(MockSQL(), claim, SimpleNamespace(case_id=controller.case_id, service_contract=sources),
                   {"id": source_id}, {"id": qualification_id}, execution)
    graph = initial({"case_id": controller.case_id}, release(controller, sources, bound))
    graph["pending"] = ["task3"]
    graph["artifacts"].update(inputs)
    graph = advance(execution, graph, lambda *_: reply, lambda _: None)
    assert len(commits) == 1
    assert graph["artifacts"]["delivery_manifest"]["schema_version"] == "anvil.marketing-descriptor-service-proposal.v1"
    assert graph["artifacts"]["delivery_manifest"]["actual_media_generated"] is False


def test_baseline_boolean_zero_is_not_false_authority_evidence():
    controller, _, _, _, sources, *_ = setup()
    released_sources(controller, sources)
    manifest = baseline_manifest(controller, sources, attachment(controller), 1)
    manifest["new_task3_effect"] = 0
    with pytest.raises(ValueError):
        BaselineDescriptors.model_validate(manifest)


def test_source_read_supplies_hash_and_assigned_readiness_record_is_retrievable():
    controller, execution, _, _, sources, action_ref, *_ = setup()
    contract = sources["case"]["experiment_proposal_contract"]
    controller._initial["documents"] = [{"actor_visible": True, "outcome_binding": None,
                                        "released_at": "2027-01-04T00:00:00Z", "public": deepcopy(contract)}]
    read = execute(controller, "policy", "source_documents.read", {"resource_ref": contract["id"]}, execution)
    assert read["result"]["records"][0]["source_record_sha256"] == digest(contract)
    execute(controller, "orchestrator", "handoffs.assign", {"id": "test-assignment", "expected_version": 0,
            "idempotency_key": "test-assignment", "content": {"recipient_role": "policy", "artifact_refs": [action_ref]}}, execution)
    assigned = execute(controller, "policy", "handoffs.assigned.read", {"resource_ref": action_ref["id"]}, execution)
    assert assigned["result"]["assigned_artifacts"][0]["record_sha256"] == action_ref["sha256"]
