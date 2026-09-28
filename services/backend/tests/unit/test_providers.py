import json

import httpx
import pytest
from pydantic import ValidationError

from anvil.providers import PROVIDERS, ActorRequest, execute_contract


def success(provider):
    if provider in ("openai", "meta_muse"):
        return {
            "id": "response-test",
            "object": "response",
            "created_at": 1,
            "model": "test-model",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "msg-test",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {"type": "output_text", "text": "Actor-only answer", "annotations": []}
                    ],
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }
    if provider == "anthropic":
        return {
            "id": "msg-test",
            "type": "message",
            "role": "assistant",
            "model": "test-model",
            "content": [{"type": "text", "text": "Actor-only answer"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    if provider == "gemini":
        return {
            "responseId": "response-test",
            "modelVersion": "test-model",
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": "Actor-only answer"}]},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 5,
                "totalTokenCount": 15,
            },
        }
    return {
        "id": "chat-test",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Actor-only answer"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "missing_usage",
        "empty",
        "malformed",
        "refusal",
        "truncated",
        "401",
        "403",
        "404",
        "429",
        "500",
        "timeout",
    ],
)
def test_provider_contract(provider, scenario):
    calls = []

    def transport(req):
        calls.append(req)
        body = json.loads(req.content)
        assert "private/reference" not in req.content.decode()
        assert "expected" not in req.content.decode()
        assert "tools" not in body or body["tools"] is None
        assert "Actor only input" in req.content.decode()
        if scenario == "timeout":
            raise httpx.ReadTimeout("redacted", request=req)
        if scenario.isdigit():
            return httpx.Response(
                int(scenario),
                json={"error": {"message": "redacted", "type": "test_error", "code": "test"}},
            )
        if scenario == "malformed":
            return httpx.Response(
                200, content=b"not-json", headers={"content-type": "application/json"}
            )
        data = success(provider)
        if scenario == "missing_usage":
            data.pop("usage" if provider != "gemini" else "usageMetadata")
        if scenario in ("empty", "refusal", "truncated"):
            if provider in ("openai", "meta_muse"):
                if scenario == "empty":
                    data["output"] = []
                elif scenario == "refusal":
                    data["output"][0]["content"] = [{"type": "refusal", "refusal": "Blocked"}]
                else:
                    data["status"] = "incomplete"
            elif provider == "anthropic":
                if scenario == "empty":
                    data["content"] = []
                elif scenario == "refusal":
                    data["stop_reason"] = "refusal"
                else:
                    data["stop_reason"] = "max_tokens"
            elif provider == "gemini":
                if scenario == "empty":
                    data["candidates"] = []
                elif scenario == "refusal":
                    data["candidates"][0]["finishReason"] = "SAFETY"
                else:
                    data["candidates"][0]["finishReason"] = "MAX_TOKENS"
            else:
                if scenario == "empty":
                    data["choices"] = []
                elif scenario == "refusal":
                    data["choices"][0]["finish_reason"] = "content_filter"
                else:
                    data["choices"][0]["finish_reason"] = "length"
        return httpx.Response(200, json=data)

    result = execute_contract(
        provider,
        ActorRequest(model="test-model", actor_text="Actor only input", max_output_tokens=100),
        httpx.MockTransport(transport),
    )
    assert len(calls) == 1, "SDK must never retry inference"
    assert result.actual_cost_micro_usd is None
    if scenario in ("success", "missing_usage"):
        assert result.status == "completed", result
        assert result.text == "Actor-only answer"
        if scenario == "missing_usage":
            assert result.usage is None
    elif scenario == "refusal":
        assert result.status == "refused", result
    elif scenario == "truncated":
        assert result.status == "truncated", result
    elif scenario in ("timeout", "500"):
        assert result.status == "execution_unknown", result
    else:
        assert result.status == "failed_operational", result
    if provider in ("openai", "meta_muse"):
        assert json.loads(calls[0].content)["store"] is False


def test_actor_contract_rejects_private_fields_and_real_transport():
    with pytest.raises(ValidationError):
        ActorRequest(model="test", actor_text="x", max_output_tokens=1, reference="hidden")
    with pytest.raises(ValueError):
        execute_contract(
            "openai",
            ActorRequest(model="test", actor_text="x", max_output_tokens=1),
            httpx.HTTPTransport(),
        )
