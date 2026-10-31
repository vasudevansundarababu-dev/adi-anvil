import json
import logging
from dataclasses import asdict
from urllib.parse import quote

import httpx
import pytest
from test_api_security import USERS
from test_praxis_harbor import BASE

from anvil import providers, workspace_credentials, workspace_secrets
from anvil.cli import OUTSIDER_PROJECT, PROJECT
from anvil.db import transaction, uid
from anvil.workspace_adapter_contracts import ENV_OVERRIDES, ContractBlocked, execute_mock
from anvil.workspace_preparation import model_snapshot


def response_body(provider, text="Unrepaired actor answer"):
    if provider == "openai":
        return {
            "id": "resp-test",
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
                    "content": [{"type": "output_text", "text": text, "annotations": []}],
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
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    return {
        "responseId": "response-test",
        "modelVersion": "test-model",
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15},
    }


@pytest.fixture
def configured(provider, client_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_secrets, "ROOT", tmp_path)
    monkeypatch.setattr(workspace_secrets, "CLOUD", False)
    for name in ENV_OVERRIDES:
        monkeypatch.delenv(name, raising=False)
    # Explicit scoped auth must win over SDK global key defaults and Vertex mode.
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(name, "unrelated-global-test-key-never-use")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setattr(
        providers, "secret_presence", lambda *args: pytest.fail("Global key lookup")
    )
    admin, _ = client_factory("admin-1")
    path = BASE + "/workspace"
    key = "test-only-scoped-" + uid() + '-"\\'

    def post(endpoint, body, version=None):
        response = admin.post(
            endpoint,
            json=body,
            headers={"Idempotency-Key": uid(), **({"If-Match": str(version)} if version else {})},
        )
        assert response.status_code == 200, response.text
        assert key not in response.text
        return response.json()["data"]

    credential = post(
        path + "/credentials",
        {"name": "Test-only SDK contract key", "provider": provider, "secret": key},
    )
    model = post(
        path + "/models",
        {
            "name": "Test-only scoped " + provider,
            "provider": provider,
            "model_id": "test-model",
            "max_output_tokens": 2048,
            "credential_id": credential["id"],
            "credential_version_id": credential["current_version_id"],
        },
    )
    with transaction(PROJECT, USERS["admin-1"]) as c:
        binding = model_snapshot(
            c.execute("SELECT * FROM anvil.connections WHERE id=%s", (model["id"],)).fetchone()
        )
    return key, credential, model, binding, post


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "invalid_json",
        "missing_usage",
        "refusal",
        "truncated",
        "timeout",
        "connection",
        "exception_echo",
        "body_echo",
        "usage_echo",
        "header_echo",
        "malformed_echo",
        "encoded_header_echo",
        "oversized",
        "401",
        "429",
        "500",
        "redirect",
    ],
)
def test_scoped_native_sdk_contracts_no_retry_no_key_leak(provider, scenario, configured, caplog):
    key, _, _, binding, _ = configured
    calls = []
    caplog.set_level(logging.DEBUG)

    def handler(req):
        calls.append(req)
        header = {"openai": "authorization", "anthropic": "x-api-key", "gemini": "x-goog-api-key"}[
            provider
        ]
        assert req.headers[header] == ("Bearer " + key if provider == "openai" else key)
        assert "unrelated-global-test-key" not in str(req.headers)
        body = json.loads(req.content)
        assert "ACTOR_ONLY_CONTEXT" in req.content.decode() and "reference" not in body
        assert (
            "private/reference" not in req.content.decode()
            and "expected_answer" not in req.content.decode()
        )
        assert body.get("tools") in (None, [])
        if scenario == "timeout":
            raise httpx.ReadTimeout(key, request=req)
        if scenario == "connection":
            raise httpx.ConnectError(key, request=req)
        if scenario == "exception_echo":
            raise RuntimeError(key)
        if scenario.isdigit():
            return httpx.Response(
                int(scenario),
                json={"error": {"message": "test rejection", "type": "test_error", "code": "test"}},
            )
        if scenario == "redirect":
            return httpx.Response(
                307, headers={"location": "https://unreviewed.example.test/steal"}
            )
        if scenario == "malformed_echo":
            return httpx.Response(200, content=("not-json " + json.dumps(key)).encode())
        if scenario == "oversized":
            return httpx.Response(200, content=b"x" * 2000001)
        data = response_body(
            provider,
            "{invalid JSON is retained"
            if scenario == "invalid_json"
            else key
            if scenario == "body_echo"
            else "Unrepaired actor answer",
        )
        usage_name = "usageMetadata" if provider == "gemini" else "usage"
        if scenario == "missing_usage":
            data.pop(usage_name)
        if scenario == "usage_echo":
            data[usage_name] = {"unexpected": key}
        if scenario in ("refusal", "truncated"):
            if provider == "openai":
                if scenario == "refusal":
                    data["output"][0]["content"] = [{"type": "refusal", "refusal": "Blocked"}]
                else:
                    data["status"] = "incomplete"
            elif provider == "anthropic":
                data["stop_reason"] = "refusal" if scenario == "refusal" else "max_tokens"
            else:
                data["candidates"][0]["finishReason"] = (
                    "SAFETY" if scenario == "refusal" else "MAX_TOKENS"
                )
        return httpx.Response(
            200,
            json=data,
            headers={"x-request-id": key if scenario == "header_echo" else quote(key, safe="")}
            if scenario in ("header_echo", "encoded_header_echo")
            else {},
        )

    with transaction(PROJECT, USERS["admin-1"]) as c:
        tables = (
            "jobs",
            "harbor_agent_plans",
            "harbor_agent_calls",
            "budget_reservations",
            "provider_approvals",
        )
        before = {t: c.execute(f"SELECT count(*) n FROM anvil.{t}").fetchone()["n"] for t in tables}
        result = execute_mock(
            c,
            PROJECT,
            binding,
            providers.ActorRequest(
                model="test-model", actor_text="ACTOR_ONLY_CONTEXT", max_output_tokens=100
            ),
            transport=httpx.MockTransport(handler),
        )
        assert {
            t: c.execute(f"SELECT count(*) n FROM anvil.{t}").fetchone()["n"] for t in tables
        } == before
    assert len(calls) == 1, "Mock inference must not be retried or redirected"
    assert result.actual_cost_micro_usd is None
    assert key not in str(asdict(result)) and key not in caplog.text
    if scenario in ("success", "invalid_json", "missing_usage"):
        assert result.status == "completed", result
        assert result.text == (
            "{invalid JSON is retained" if scenario == "invalid_json" else "Unrepaired actor answer"
        )
        if scenario == "missing_usage":
            assert result.usage is None
    elif scenario == "refusal":
        assert result.status == "refused"
    elif scenario == "truncated":
        assert result.status == "truncated"
    elif scenario in ("timeout", "connection", "exception_echo", "500"):
        assert result.status == "execution_unknown", result
    else:
        assert result.status == "failed_operational", result
        if scenario.endswith("_echo"):
            assert result.error_code == "credential_echo_suppressed"


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
def test_binding_access_limits_revocation_fail_before_secret_or_sdk(
    provider, configured, monkeypatch
):
    key, credential, model, binding, post = configured
    request = providers.ActorRequest(
        model="test-model", actor_text="ACTOR_ONLY_CONTEXT", max_output_tokens=100
    )
    transport = httpx.MockTransport(lambda req: pytest.fail("SDK invoked for blocked contract"))
    original_resolve = workspace_credentials.resolve
    monkeypatch.setattr(
        workspace_credentials,
        "resolve",
        lambda *args: pytest.fail("Secret resolved before admission"),
    )
    with transaction(PROJECT, USERS["admin-1"]) as c:
        for bad in (
            {**binding, "config_hash": "0" * 64},
            {**binding, "destination": "https://unreviewed.example.test"},
            {**binding, "credential": None},
        ):
            with pytest.raises(ContractBlocked):
                execute_mock(c, PROJECT, bad, request, transport=transport)
        for actor, tokens in (("é" * 16385, 100), ("ACTOR_ONLY_CONTEXT", 2049)):
            with pytest.raises(ContractBlocked):
                execute_mock(
                    c,
                    PROJECT,
                    binding,
                    providers.ActorRequest(
                        model="test-model", actor_text=actor, max_output_tokens=tokens
                    ),
                    transport=transport,
                )
        # Pydantic already rejects this at construction; also defend against a
        # trusted caller mutating a previously validated request object.
        malformed = request.model_copy(update={"actor_text": "\ud800"})
        with pytest.raises(ContractBlocked, match="actor_or_output_limits_not_admitted"):
            execute_mock(c, PROJECT, binding, malformed, transport=transport)
    with transaction(PROJECT, USERS["researcher"]) as c:
        with pytest.raises(ContractBlocked, match="contract_admin_required"):
            execute_mock(c, PROJECT, binding, request, transport=transport)
    with transaction(OUTSIDER_PROJECT, USERS["outsider"]) as c:
        with pytest.raises(ContractBlocked):
            execute_mock(c, PROJECT, binding, request, transport=transport)
    with transaction(PROJECT, USERS["outsider"]) as c:
        with pytest.raises(ContractBlocked):
            execute_mock(c, PROJECT, binding, request, transport=transport)
    monkeypatch.setattr(workspace_credentials, "resolve", original_resolve)
    with transaction(PROJECT, USERS["admin-1"]) as c:
        with pytest.raises(ContractBlocked, match="credential_in_actor_payload"):
            execute_mock(
                c,
                PROJECT,
                binding,
                providers.ActorRequest(model="test-model", actor_text=key, max_output_tokens=100),
                transport=transport,
            )
    rotated = post(
        BASE + f"/workspace/credentials/{credential['id']}/versions",
        {"secret": "test-only-rotated-key-" + uid()},
    )
    monkeypatch.setattr(
        workspace_credentials, "resolve", lambda *args: pytest.fail("Rotated secret resolved")
    )
    with transaction(PROJECT, USERS["admin-1"]) as c:
        with pytest.raises(ContractBlocked, match="credential_binding_not_current_or_enabled"):
            execute_mock(c, PROJECT, binding, request, transport=transport)
    successor = post(
        BASE + f"/workspace/models/{model['id']}/versions",
        {
            "name": "Test-only successor SDK contract",
            "provider": provider,
            "model_id": "test-model",
            "max_output_tokens": 2048,
            "credential_id": credential["id"],
            "credential_version_id": rotated["current_version_id"],
        },
        model["profile_row_version"],
    )
    with transaction(PROJECT, USERS["admin-1"]) as c:
        with pytest.raises(ContractBlocked, match="model_binding_not_current_or_enabled"):
            execute_mock(c, PROJECT, binding, request, transport=transport)
        current_binding = model_snapshot(
            c.execute("SELECT * FROM anvil.connections WHERE id=%s", (successor["id"],)).fetchone()
        )
    post(BASE + f"/workspace/credentials/{credential['id']}/revoke", {})
    with transaction(PROJECT, USERS["admin-1"]) as c:
        with pytest.raises(ContractBlocked, match="credential_binding_not_current_or_enabled"):
            execute_mock(c, PROJECT, current_binding, request, transport=transport)
    post(
        BASE + f"/workspace/models/{successor['id']}/disable", {}, successor["profile_row_version"]
    )
    with transaction(PROJECT, USERS["admin-1"]) as c:
        with pytest.raises(ContractBlocked, match="model_binding_not_current_or_enabled"):
            execute_mock(c, PROJECT, current_binding, request, transport=transport)
