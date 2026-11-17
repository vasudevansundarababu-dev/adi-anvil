"""Actual decoder and published fixture schema; no inference or tool execution."""

import json
from pathlib import Path

import pytest

from anvil.marketing_response_diagnostics import inspect


@pytest.fixture
def execution():
    return json.loads(
        (Path(__file__).parents[1] / "fixtures/veyra-template-execution-v3.json").read_text()
    )


def test_valid_control_artifact_is_not_a_task_pass(execution):
    role = execution["workflow_graph"]["roles"][0]["id"]
    finding = inspect('{"artifact":{}}', execution, role)
    assert finding["protocol_status"] == "valid"
    assert finding["observed_failure"] is None
    assert (
        finding["effects_assessed"]
        is finding["model_performance_validated"]
        is finding["internal_reasoning_assessed"]
        is False
    )
    assert "award" not in finding and "score" not in finding


@pytest.mark.parametrize(
    "text,failure",
    [
        ("{", "invalid_json"),
        ('{"actions":[],"artifact":{}}', "invalid_control_envelope"),
        ('{"actions":[]}', "invalid_action_population"),
        (
            '{"actions":[{"operation":"PRIVATE-UNKNOWN-TOOL","arguments":{}}]}',
            "unoffered_tool_requested",
        ),
    ],
)
def test_invalid_completed_response_has_sanitized_observed_finding(execution, text, failure):
    finding = inspect(text, execution, execution["workflow_graph"]["roles"][0]["id"])
    assert finding["observed_failure"] == failure
    assert finding["protocol_status"] == "invalid"
    assert "PRIVATE-UNKNOWN-TOOL" not in str(finding)
    assert finding["effects_assessed"] is False


def test_role_violation_is_a_request_observation_not_executed_action(execution):
    roles = {role["id"] for role in execution["workflow_graph"]["roles"]}
    tool = next(tool for tool in execution["tools"] if set(tool["role_ids"]) != roles)
    forbidden_role = next(iter(roles - set(tool["role_ids"])))
    finding = inspect(
        json.dumps({"actions": [{"operation": tool["id"], "arguments": {}}]}),
        execution,
        forbidden_role,
    )
    assert finding["observed_failure"] == "tool_requested_outside_assigned_role"
    assert finding["known_requested_tool_ids"] == [tool["id"]]
    assert finding["effects_assessed"] is False


def test_bad_host_role_is_not_attributed_to_candidate(execution):
    with pytest.raises(ValueError, match="host-bound"):
        inspect('{"artifact":{}}', execution, "not-a-host-role")


def test_invalid_artifact_and_arguments_are_observed_protocol_failures(execution):
    roles = execution["workflow_graph"]["roles"]
    invalid = inspect('{"artifact":[]}', execution, roles[0]["id"])
    assert invalid["observed_failure"] == "invalid_node_artifact"
    tool = next(tool for tool in execution["tools"] if tool["input_schema"].get("required"))
    role = tool["role_ids"][0]
    invalid = inspect(
        json.dumps({"actions": [{"operation": tool["id"], "arguments": {}}]}), execution, role
    )
    assert invalid["observed_failure"] == "invalid_tool_arguments"
    assert len(invalid["classifier_source_sha256"]) == 64


def test_valid_tool_list_and_transitive_register_provenance_are_explicit(execution, monkeypatch):
    tool = next(tool for tool in execution["tools"] if tool["id"] == "context.read")
    text = json.dumps({"actions": [{"operation": tool["id"], "arguments": {}}]})
    before = inspect(text, execution, tool["role_ids"][0])
    assert before["protocol_status"] == "valid"
    assert before["known_requested_tool_ids"] == ["context.read"]
    assert before["tool_request_list_complete"] is True
    original = Path.read_bytes

    def changed(path):
        value = original(path)
        return (
            value + b"\n# changed target definitions" if path.name == "golden_targets.py" else value
        )

    monkeypatch.setattr(Path, "read_bytes", changed)
    after = inspect(text, execution, tool["role_ids"][0])
    assert after["classifier_source_sha256"] != before["classifier_source_sha256"]
    assert "loaded origins" in after["provenance_limitation"]
