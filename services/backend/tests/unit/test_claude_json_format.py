import json

import httpx
import pytest
from pydantic import SecretStr
from test_providers import success

from anvil import providers


def invoke(text, *, structured=True, finish="end_turn"):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        body = success("anthropic")
        body["model"] = "claude-opus-5-5"
        body["content"] = [{"type": "text", "text": text}]
        body["stop_reason"] = finish
        return httpx.Response(200, json=body)

    result = providers._execute_native(
        "anthropic",
        providers.ActorRequest(
            model="claude-opus-5-5", actor_text="Return a JSON action", max_output_tokens=2048
        ),
        httpx.MockTransport(handler),
        credential=SecretStr("test-only-credential"),
        structured=structured,
    )
    assert len(requests) == 1
    return result, requests[0]


def test_claude_json_mode_preserves_arbitrary_nested_arguments_and_usage():
    action = {
        "tool": "save_result",
        "arguments": {"output": {"dynamic-key": [0, False, None, {"unicode": "£"}]}},
    }
    result, request = invoke(json.dumps({"json": json.dumps(action)}))
    assert request["output_config"]["format"]["type"] == "json_schema"
    schema = request["output_config"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["json"]
    assert schema["properties"]["json"]["type"] == "string"
    assert "tools" not in request and "tool_choice" not in request
    assert result.status == "completed" and json.loads(result.text) == action
    assert result.model_returned == "claude-opus-5-5"
    assert result.request_id == "msg-test"
    assert result.usage["input_tokens"] == 10 and result.usage["output_tokens"] == 5


@pytest.mark.parametrize(
    "text",
    [
        'prose before {"json":"{\\"done\\":true}"}',
        '{"json":"not JSON"}',
        '{"json":"[]"}',
        '{"json":17}',
        '{"json":"{\\"done\\":true}","extra":1}',
    ],
)
def test_malformed_envelopes_are_never_repaired_or_extracted(text):
    result, _ = invoke(text)
    assert result.text == text


@pytest.mark.parametrize("finish,status", [("refusal", "refused"), ("max_tokens", "truncated")])
def test_claude_format_does_not_turn_refusal_or_truncation_into_completion(finish, status):
    text = json.dumps({"json": '{"done":true}'})
    result, _ = invoke(text, finish=finish)
    assert result.status == status and result.text == text
    assert result.usage["input_tokens"] == 10 and result.usage["output_tokens"] == 5


def test_unstructured_claude_contract_does_not_change():
    text = json.dumps({"json": '{"done":true}'})
    result, request = invoke(text, structured=False)
    assert "output_config" not in request
    assert result.text == text
