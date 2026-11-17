"""Manufactured proof-consistency controls, not actual SQL receipt qualification."""

from copy import deepcopy
from uuid import uuid4

import pytest
from test_marketing_world_descriptor_services import request

from anvil.marketing_task2_persistence import freeze
from anvil.marketing_world_service_api import verify_records
from anvil.marketing_world_services import descriptor_proposal
from anvil.praxis_generic_contract import digest


def evidence():
    controller, execution, node, inputs, sources, _ = request()
    artifact = descriptor_proposal(controller, execution, node, inputs, sources)
    _, state_hash = freeze(controller)
    receipt = {"input_sha256": digest(inputs), "artifact_sha256": digest(artifact),
               "post_state_sha256": state_hash, "world_binding_sha256": "b" * 64,
               "world_effect_id": str(uuid4()), "episode_id": controller.trial_id,
               "generation": controller.generation, "node_id": "task3", "week": 1, "visit": 1,
               "origin": "persisted_environment_effect", "simulated_environment": True}
    receipt["world_receipt_sha256"] = digest({"artifact": artifact, "receipt": receipt, "port": None})
    reply = {"artifact": artifact, "receipt": receipt, "port": None}
    key = str(uuid4())
    effect = {"id": key, "state": "completed", "node_id": "task3", "week": 1, "visit": 1,
              "input_sha256": digest(inputs), "node_sha256": digest(node), "result": reply}
    metadata = {"effect_id": key, "receipt_id": receipt["world_effect_id"], "reply_sha256": digest(reply),
                "source_contract_sha256": digest(sources), "post_state_sha256": state_hash,
                "request_id": artifact["request_ref"]["id"], "request_version": artifact["request_ref"]["version"],
                "request_sha256": artifact["request_ref"]["sha256"], "input_sha256": digest(inputs), "node_sha256": digest(node)}
    return {"effects": [effect]}, execution, {"records": [metadata], "source_contract_sha256": digest(sources)}


def test_scope_correct_completed_effect_requires_independent_api_record():
    graph, execution, value = evidence()
    value["records"] = []
    with pytest.raises(ValueError, match="no actual API service proof"):
        verify_records(graph, execution, value)


def test_self_consistent_forged_worker_reply_cannot_replace_api_return_hash():
    graph, execution, value = evidence()
    reply = graph["effects"][0]["result"]
    reply["artifact"]["status"] = "manufactured-foreign-result"
    reply["receipt"]["artifact_sha256"] = digest(reply["artifact"])
    base = {**reply, "receipt": {k: v for k, v in reply["receipt"].items() if k != "world_receipt_sha256"}}
    reply["receipt"]["world_receipt_sha256"] = digest(base)
    with pytest.raises(ValueError, match="immutable actual API service return"):
        verify_records(graph, execution, value)


def test_boolean_version_is_not_an_actual_request_version():
    graph, execution, value = evidence()
    value["records"][0]["request_version"] = True
    with pytest.raises(ValueError, match="Exact bounded immutable"):
        verify_records(graph, execution, value)


def test_private_api_return_does_not_repair_unknown_workflow_state():
    graph, execution, value = evidence()
    graph["effects"][0].update(state="execution_unknown", result=None)
    original = digest(deepcopy(graph))
    verify_records(graph, execution, value)
    assert digest(graph) == original
    assert graph["effects"][0]["state"] == "execution_unknown"


def test_broken_private_request_snapshot_metadata_is_rejected():
    graph, execution, value = evidence()
    value["records"][0]["request_id"] = "other-request"
    with pytest.raises(ValueError, match="immutable actual API service return"):
        verify_records(graph, execution, value)
