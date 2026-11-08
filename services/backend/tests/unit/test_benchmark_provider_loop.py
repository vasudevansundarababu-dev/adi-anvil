"""Offline BM05: only the paid vendor boundary uses MockTransport; tools use real files."""

import json

import httpx
import pytest
from pydantic import ValidationError

from anvil.benchmark_conversation import Binding, Limits, Tool, run_contract
from anvil.benchmark_tool_gateway import ArtifactTools
from anvil.providers import PROVIDERS

PROVIDERS_UNDER_TEST = ("openai", "anthropic", "gemini")


def binding(provider):
    return Binding(
        provider=provider, model_id="anvil-fixture-model", destination=PROVIDERS[provider][2]
    )


def tool():
    return Tool(
        name="write_artifact",
        description="Write one declared actor deliverable",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}, "text": {"type": "string"}},
            "required": ["path", "text"],
            "additionalProperties": False,
        },
    )


def response(provider, *, calls=(), text="", model="anvil-fixture-model", finish=None, usage=True):
    if provider == "openai":
        output = [
            {
                "id": "fc-" + str(i),
                "type": "function_call",
                "call_id": identifier,
                "name": name,
                "arguments": args if isinstance(args, str) else json.dumps(args),
                "status": "completed",
            }
            for i, (identifier, name, args) in enumerate(calls)
        ]
        if text:
            output.append(
                {
                    "id": "message",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": text, "annotations": []}],
                }
            )
        data = {
            "id": "response-fixture",
            "object": "response",
            "created_at": 1,
            "model": model,
            "status": finish or "completed",
            "output": output,
        }
        if usage:
            data["usage"] = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    elif provider == "anthropic":
        content = [
            {"type": "tool_use", "id": identifier, "name": name, "input": args}
            for identifier, name, args in calls
        ]
        if text:
            content.append({"type": "text", "text": text})
        data = {
            "id": "message-fixture",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            "stop_reason": finish or ("tool_use" if calls else "end_turn"),
        }
        if usage:
            data["usage"] = {"input_tokens": 10, "output_tokens": 5}
    else:
        parts = [
            {
                "functionCall": {"id": identifier, "name": name, "args": args},
                "thoughtSignature": "AQID",
            }
            for identifier, name, args in calls
        ]
        if text:
            parts.append({"text": text})
        data = {
            "responseId": "response-fixture",
            "modelVersion": model,
            "candidates": [
                {"content": {"role": "model", "parts": parts}, "finishReason": finish or "STOP"}
            ],
        }
        if usage:
            data["usageMetadata"] = {
                "promptTokenCount": 10,
                "candidatesTokenCount": 5,
                "totalTokenCount": 15,
            }
    return data


def observations(provider, body):
    if provider == "openai":
        return [x for x in body["input"] if x.get("type") == "function_call_output"]
    if provider == "anthropic":
        return [
            x
            for msg in body["messages"]
            if msg["role"] == "user" and isinstance(msg["content"], list)
            for x in msg["content"]
            if x.get("type") == "tool_result"
        ]
    return [
        x["functionResponse"]
        for msg in body["contents"]
        for x in msg["parts"]
        if "functionResponse" in x
    ]


@pytest.mark.parametrize("provider", PROVIDERS_UNDER_TEST)
def test_multi_call_error_then_final_real_sdk_and_files(provider, tmp_path):
    root = tmp_path / "outputs"
    root.mkdir(mode=0o700)
    runner = ArtifactTools(root, {"report.md": 4096, "answers.json": 4096})
    first = response(
        provider,
        calls=[
            ("call-a", "write_artifact", {"path": "report.md", "text": "Actor-only report"}),
            ("call-b", "undeclared", {}),
            ("call-c", "write_artifact", {"path": "answers.json", "text": "{}"}),
        ],
        text="Working",
    )
    requests = []

    def send(req):
        requests.append(req)
        body = json.loads(req.content)
        assert req.method == "POST" and req.url.scheme == "https"
        assert req.url.host == httpx.URL(PROVIDERS[provider][2]).host
        header = {"openai": "authorization", "anthropic": "x-api-key", "gemini": "x-goog-api-key"}[
            provider
        ]
        expected = (
            "Bearer anvil-offline-contract-only"
            if provider == "openai"
            else "anvil-offline-contract-only"
        )
        assert req.headers[header] == expected
        assert not any(
            req.headers.get(k) for k in {"authorization", "x-api-key", "x-goog-api-key"} - {header}
        )
        assert "private-canary" not in req.content.decode()
        if len(requests) == 1:
            assert body.get("tools") or body.get("config", {}).get("tools")
            return httpx.Response(200, json=first)
        obs = observations(provider, body)
        assert len(obs) == 3
        encoded = json.dumps(obs)
        assert "call-a" in encoded and "call-b" in encoded and "call-c" in encoded
        assert "undeclared_tool" in encoded and "Actor-only report" not in encoded
        if provider == "gemini":
            assert "AQID" in req.content.decode(), "Opaque signature must survive replay"
        return httpx.Response(200, json=response(provider, text="Finished"))

    result = run_contract(
        binding(provider),
        "Use only the supplied actor inputs",
        [tool()],
        runner,
        httpx.MockTransport(send),
    )
    assert result.status == "completed" and result.text == "Finished", result
    assert len(requests) == 2 and len(result.turns) == 2
    assert [x.call_id for x in result.turns[0].observations] == ["call-a", "call-b", "call-c"]
    assert result.turns[0].observations[1].error == "undeclared_tool"
    assert (root / "report.md").read_text() == "Actor-only report"
    assert (root / "answers.json").read_text() == "{}"
    assert result.origin == "sdk_mock" and result.actual_cost_micro_usd is None
    assert result.turns[0].usage.input_tokens == 10 and result.turns[1].usage.output_tokens == 5


@pytest.mark.parametrize("provider", PROVIDERS_UNDER_TEST)
@pytest.mark.parametrize(
    "scenario",
    [
        "timeout",
        "500",
        "429",
        "redirect",
        "malformed",
        "wrong_model",
        "missing_model",
        "missing_usage",
        "refused",
        "truncated",
        "duplicate_id",
        "too_many_calls",
    ],
)
def test_failures_never_retry_or_execute_unvalidated_calls(provider, scenario, tmp_path):
    root = tmp_path / "outputs"
    root.mkdir(mode=0o700)
    runner = ArtifactTools(root, {"report.md": 4096})
    requests = []

    def send(req):
        requests.append(req)
        if scenario == "timeout":
            raise httpx.ReadTimeout("private-canary", request=req)
        if scenario in {"500", "429"}:
            return httpx.Response(int(scenario), json={"error": {"message": "private-canary"}})
        if scenario == "redirect":
            return httpx.Response(307, headers={"location": "https://evil.invalid/private-canary"})
        if scenario == "malformed":
            return httpx.Response(200, content=b"bad-json")
        calls = (
            [
                (
                    "duplicate" if scenario == "duplicate_id" else "call-" + str(i),
                    "write_artifact",
                    {"path": "report.md", "text": "unsafe"},
                )
                for i in range(2 if scenario == "duplicate_id" else 9)
            ]
            if scenario in {"duplicate_id", "too_many_calls"}
            else []
        )
        data = response(provider, calls=calls, text="Final", usage=scenario != "missing_usage")
        if scenario == "wrong_model":
            data["modelVersion" if provider == "gemini" else "model"] = "other-model"
        if scenario == "missing_model":
            data.pop("modelVersion" if provider == "gemini" else "model")
        if scenario == "refused":
            if provider == "openai":
                data["output"][0]["content"] = [{"type": "refusal", "refusal": "Denied"}]
            elif provider == "anthropic":
                data["stop_reason"] = "refusal"
            else:
                data["candidates"][0]["finishReason"] = "SAFETY"
        if scenario == "truncated":
            if provider == "openai":
                data["status"] = "incomplete"
            elif provider == "anthropic":
                data["stop_reason"] = "max_tokens"
            else:
                data["candidates"][0]["finishReason"] = "MAX_TOKENS"
        return httpx.Response(200, json=data)

    result = run_contract(
        binding(provider), "Actor only", [tool()], runner, httpx.MockTransport(send)
    )
    assert len(requests) == 1 and not list(root.iterdir())
    assert "private-canary" not in repr(result)
    if scenario == "missing_usage":
        assert result.status == "completed" and result.turns[0].usage is None
    elif scenario == "refused":
        assert result.status == "refused"
    elif scenario == "truncated":
        assert result.status == "truncated"
    elif scenario in {
        "timeout",
        "500",
        "malformed",
        "duplicate_id",
        "too_many_calls",
        "wrong_model",
        "missing_model",
    }:
        assert result.status == "execution_unknown", result
    else:
        assert result.status == "failed_operational", result


@pytest.mark.parametrize("provider", PROVIDERS_UNDER_TEST)
def test_turn_limit_is_exact_and_same_call_ids_cannot_be_reused(provider, tmp_path):
    root = tmp_path / "outputs"
    root.mkdir(mode=0o700)
    runner = ArtifactTools(root, {"report.md": 4096})
    requests = []

    def send(req):
        requests.append(req)
        return httpx.Response(200, json=response(provider, calls=[("repeat", "unknown", {})]))

    result = run_contract(
        binding(provider),
        "Actor only",
        [tool()],
        runner,
        httpx.MockTransport(send),
        limits=Limits(max_turns=3),
    )
    assert (
        len(requests) == 2
        and result.status == "execution_unknown"
        and result.error_code == "reused_tool_call_id"
    )
    requests.clear()

    def unique(req):
        requests.append(req)
        return httpx.Response(
            200, json=response(provider, calls=[("call-" + str(len(requests)), "unknown", {})])
        )

    result = run_contract(
        binding(provider),
        "Actor only",
        [tool()],
        runner,
        httpx.MockTransport(unique),
        limits=Limits(max_turns=2),
    )
    assert (
        len(requests) == 2
        and result.status == "turn_limit"
        and result.actual_cost_micro_usd is None
    )


def test_offline_only_and_strict_frozen_limits(tmp_path):
    with pytest.raises(ValueError, match="mock_transport_required"):
        run_contract(binding("openai"), "Actor", [tool()], None, httpx.HTTPTransport())
    for invalid in (
        {"max_turns": 16},
        {"max_tool_calls": 9},
        {"max_argument_bytes": 65537},
        {"max_turns": True},
        {"private_reference": "hidden"},
    ):
        with pytest.raises(ValidationError):
            Limits(**invalid)
    with pytest.raises(ValidationError):
        Binding(provider="anthropic", model_id="test", destination="x", private_reference="hidden")


@pytest.mark.parametrize("provider", PROVIDERS_UNDER_TEST)
@pytest.mark.parametrize(
    "fault",
    [
        "large_arguments",
        "invalid_arguments",
        "secret_echo",
        "response_bound",
        "context_bound",
        "text_bound",
        "invalid_usage",
        "tool_failure",
        "empty",
    ],
)
def test_byte_limits_redaction_and_error_observations(provider, fault, tmp_path):
    root = tmp_path / "outputs"
    root.mkdir(mode=0o700)
    runner = ArtifactTools(root, {"report.md": 4096})
    requests = []

    def send(req):
        requests.append(req)
        if len(requests) > 1:
            obs = observations(provider, json.loads(req.content))
            assert "invalid_arguments" in json.dumps(obs) or "tool_execution_error" in json.dumps(
                obs
            )
            return httpx.Response(200, json=response(provider, text="Finished"))
        text = (
            ""
            if fault == "empty"
            else "anvil-offline-contract-only"
            if fault == "secret_echo"
            else "x" * 65537
            if fault == "text_bound"
            else "Final"
        )
        calls = []
        if fault in {"large_arguments", "invalid_arguments", "tool_failure"}:
            args = (
                {"path": "report.md", "text": "x" * 65537}
                if fault == "large_arguments"
                else {"path": "../private-canary", "text": "rejected"}
                if fault == "tool_failure"
                else {"path": 1}
            )
            calls = [("call-a", "write_artifact", args)]
        data = response(provider, calls=calls, text=text)
        if fault == "invalid_usage":
            data["usageMetadata" if provider == "gemini" else "usage"][
                "promptTokenCount" if provider == "gemini" else "input_tokens"
            ] = -1
        if fault == "response_bound":
            return httpx.Response(200, content=b"x" * 2000001)
        return httpx.Response(200, json=data)

    result = run_contract(
        binding(provider),
        "Actor only",
        [tool()],
        runner,
        httpx.MockTransport(send),
        limits=Limits(max_input_bytes=20) if fault == "context_bound" else Limits(),
    )
    assert not list(root.iterdir())
    assert "anvil-offline-contract-only" not in repr(result)
    if fault == "context_bound":
        assert len(requests) == 0 and result.status == "failed_operational"
    elif fault in {"invalid_arguments", "tool_failure"}:
        assert len(requests) == 2 and result.status == "completed", result
    else:
        assert len(requests) == 1 and result.status == "execution_unknown", result


@pytest.mark.parametrize("provider", PROVIDERS_UNDER_TEST)
def test_15_turns_are_real_responses_not_individual_tool_calls(provider, tmp_path):
    root = tmp_path / "outputs"
    root.mkdir(mode=0o700)
    requests = []

    def send(req):
        requests.append(req)
        return httpx.Response(
            200,
            json=response(
                provider, calls=[(f"t{len(requests)}-c{i}", "undeclared", {}) for i in range(8)]
            ),
        )

    result = run_contract(
        binding(provider),
        "Actor only",
        [tool()],
        ArtifactTools(root, {"report.md": 1}),
        httpx.MockTransport(send),
    )
    assert (
        len(requests) == 15
        and len(result.turns) == 15
        and sum(len(t.calls) for t in result.turns) == 120
    )
    assert result.status == "turn_limit"


def test_openai_invalid_json_is_correlated_error_not_execution(tmp_path):
    root = tmp_path / "outputs"
    root.mkdir(mode=0o700)
    requests = []

    def send(req):
        requests.append(req)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=response(
                    "openai",
                    calls=[("call-a", "write_artifact", '{"path":"report.md","text":NaN}')],
                ),
            )
        assert "invalid_arguments" in req.content.decode()
        return httpx.Response(200, json=response("openai", text="Finished"))

    result = run_contract(
        binding("openai"),
        "Actor",
        [tool()],
        ArtifactTools(root, {"report.md": 4096}),
        httpx.MockTransport(send),
    )
    assert result.status == "completed" and len(requests) == 2 and not list(root.iterdir())


@pytest.mark.parametrize("provider", PROVIDERS_UNDER_TEST)
def test_sdk_environment_overrides_block_without_send(provider, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", "unsafe")
    calls = []
    result = run_contract(
        binding(provider),
        "Actor",
        [tool()],
        None,
        httpx.MockTransport(lambda req: calls.append(req)),
    )
    assert not calls and result.status == "failed_operational"


def test_gemini_optional_ids_are_stable_and_content_order_is_preserved(tmp_path):
    root = tmp_path / "outputs"
    root.mkdir(mode=0o700)
    requests = []

    def send(req):
        requests.append(req)
        if len(requests) > 1:
            body = json.loads(req.content)
            obs = observations("gemini", body)
            assert obs[0]["id"] == "anvil-1-1"
            return httpx.Response(200, json=response("gemini", text="Finished"))
        data = response("gemini", calls=[("remove", "undeclared", {})])
        parts = data["candidates"][0]["content"]["parts"]
        parts[0]["functionCall"].pop("id")
        parts.insert(0, {"text": "Before"})
        parts.append({"text": "After"})
        return httpx.Response(200, json=data)

    result = run_contract(
        binding("gemini"),
        "Actor",
        [tool()],
        ArtifactTools(root, {"report.md": 1}),
        httpx.MockTransport(send),
    )
    assert result.status == "completed" and len(requests) == 2
    assert [part.type for part in result.turns[0].content] == ["text", "tool_call", "text"]
