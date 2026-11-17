"""Real local controller objects; no SQL, private world, approval or SDK call."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from anvil.marketing_paid_contract import phase, role_prompt
from anvil.marketing_task2_contract import WIRE_ROLES
from anvil.marketing_task2_runtime import Task2Controller
from anvil.marketing_world_requests import resolve_request
from anvil.praxis_generic_contract import digest


def setup():
    execution = json.loads(
        (Path(__file__).parents[1] / "fixtures/veyra-template-execution-v3.json").read_text()
    )
    controller = Task2Controller(
        "GT2-R01", records={}, start="2026-11-14T00:00:00Z", outcome="null", budget_minor=20000000
    )
    node = next(item for item in execution["workflow_graph"]["nodes"] if item["id"] == "task3")
    result = controller.call(
        controller.credential(WIRE_ROLES["brief"]),
        0,
        "production-requests",
        {
            "id": "request-one",
            "expected_version": 0,
            "idempotency_key": "manufactured-create",
            "content": {"source": "manufactured software control"},
        },
    )
    artifact = {
        "production_request": {
            "request_ref": {
                "id": result["id"],
                "version": result["version"],
                "sha256": digest(result),
            }
        }
    }
    return controller, execution, node, result, artifact


def test_resolves_actual_versioned_request_without_effect_or_approval():
    controller, execution, node, actual, inputs = setup()
    before = controller.capture()
    result = resolve_request(controller, execution, node, inputs)
    assert result["request"] == actual
    assert result["producer_role"] == "brief"
    assert controller.capture() == before
    result["request"]["content"]["source"] = "changed caller copy"
    assert controller._objects[actual["id"]] == actual


def test_forged_artifact_cannot_replace_missing_real_request():
    controller, execution, node, actual, inputs = setup()
    del controller._objects[actual["id"]]
    with pytest.raises(ValueError, match="Current stored request"):
        resolve_request(controller, execution, node, inputs)
    with pytest.raises(ValueError):
        resolve_request(controller, execution, node, {"production_request": actual})


def test_request_revision_invalidates_old_reference():
    controller, execution, node, _, inputs = setup()
    controller.call(
        controller.credential(WIRE_ROLES["brief"]),
        0,
        "production-requests",
        {
            "id": "request-one",
            "expected_version": 1,
            "idempotency_key": "manufactured-revise",
            "content": {"revised": True},
        },
    )
    with pytest.raises(ValueError, match="Current stored request"):
        resolve_request(controller, execution, node, inputs)


def test_wrong_kind_or_author_does_not_gain_task3_authority():
    controller, execution, node, actual, inputs = setup()
    for field, value in (("kind", "approval-requests"), ("created_by_role", WIRE_ROLES["policy"])):
        changed = deepcopy(actual)
        changed[field] = value
        controller._objects[actual["id"]] = changed
        inputs["production_request"]["request_ref"]["sha256"] = digest(changed)
        with pytest.raises(ValueError, match="Current stored request"):
            resolve_request(controller, execution, node, inputs)


def test_changed_node_or_extra_context_is_not_a_published_effect_request():
    controller, execution, node, _, inputs = setup()
    changed = deepcopy(node)
    changed["system"] = "unreviewed effect"
    with pytest.raises(ValueError, match="Exact published"):
        resolve_request(controller, execution, changed, inputs)
    with pytest.raises(ValueError, match="Exact supported"):
        resolve_request(controller, execution, node, inputs | {"approval": True})


def test_request_producer_prompt_uses_existing_server_hash_not_new_authoring_fields():
    _, execution, _, _, _ = setup()
    for artifact_name in ("production_request", "approval_request"):
        node = next(
            item
            for item in execution["workflow_graph"]["nodes"]
            if item.get("outputArtifact") == artifact_name
        )
        context = phase(execution, node["id"], {key: {} for key in node["inputRefs"]}, 1, 1)
        prompt = role_prompt("manufactured-task", execution, context, [])
        protocol = json.loads(prompt.split("\n", 1)[1])["control_protocol"]
        assert set(protocol["complete_node"]["artifact"]) == {"request_ref"}
        assert (
            "server-issued result.record_sha256"
            in protocol["complete_node"]["artifact"]["request_ref"]["sha256"]
        )
