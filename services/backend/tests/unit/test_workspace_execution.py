import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pydantic import SecretStr
from test_providers import success

from anvil import providers, workspace_dispatch
from anvil import workspace_execution as execution


def test_group_cost_is_integer_conservative_and_usage_fails_closed():
    config = {
        "pricing": {
            "input_micro_usd_per_million_tokens": 1,
            "output_micro_usd_per_million_tokens": 1,
        },
        "max_output_tokens": 2048,
        "max_calls": 3,
    }
    assert execution.required_cost(config) == 3
    assert execution.required_cost({**config, "pricing": None}) is None
    assert execution.billed_usage(
        "gemini",
        {
            "prompt_token_count": 10,
            "candidates_token_count": 5,
            "thoughts_token_count": 2,
            "total_token_count": 17,
        },
    ) == (10, 7)
    for usage in (
        {},
        {"prompt_token_count": 10, "candidates_token_count": 5, "total_token_count": 20},
    ):
        with pytest.raises(ValueError):
            execution.billed_usage("gemini", usage)
    with pytest.raises(ValueError):
        execution.billed_usage(
            "anthropic", {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 2}
        )
    with pytest.raises(ValueError):
        execution.billed_usage("openai", {"input_tokens": True, "output_tokens": 5})


def test_exact_authority_file_requires_owner_only_current_file(tmp_path, monkeypatch):
    monkeypatch.setattr(execution, "ROOT", tmp_path)
    folder = tmp_path / ".local"
    folder.mkdir()
    path = folder / "workspace-authority.json"
    assert execution.authority() is None
    path.write_text(
        json.dumps(
            {
                "reference": "harbor:contract-tests",
                "project_id": "a0000000-0000-4000-8000-000000000002",
                "group_subject_hash": "a" * 64,
                "total_cap_micro_usd": 1000000,
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            }
        )
    )
    path.chmod(0o644)
    assert execution.authority() is None
    path.chmod(0o600)
    assert execution.authority().total_cap_micro_usd == 1000000


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
@pytest.mark.parametrize("scenario", ["success", "timeout", "echo", "status500"])
def test_guarded_broker_native_sdk_exact_auth_single_request_no_secret_output(
    provider, scenario, caplog
):
    caplog.set_level(logging.DEBUG)
    key = "test-only-workspace-native-key"
    binding = {
        "provider": provider,
        "model_id": "test-model",
        "destination": providers.PROVIDERS[provider][2],
        "max_output_tokens": 2048,
    }
    requests = []

    def handle(req):
        requests.append(req)
        assert req.headers[
            {"openai": "authorization", "anthropic": "x-api-key", "gemini": "x-goog-api-key"}[
                provider
            ]
        ] == ("Bearer " + key if provider == "openai" else key)
        assert "PRIVATE-NORTHSTAR" not in req.content.decode()
        payload = json.loads(req.content)
        if provider == "openai":
            assert payload["max_output_tokens"] == 1024 and payload["store"] is False
            assert payload["service_tier"] == "default" and payload["text"]["format"] == {
                "type": "json_object"
            }
        elif provider == "anthropic":
            assert (
                payload["max_tokens"] == 1024
                and "thinking" not in payload
                and "tools" not in payload
            )
        else:
            assert payload["generationConfig"]["maxOutputTokens"] == 1024
            assert payload["generationConfig"]["responseMimeType"] == "application/json"
            thinking = payload["generationConfig"]["thinkingConfig"]
            assert thinking.get("thinkingBudget", thinking.get("thinking_budget")) == 0
        if scenario == "timeout":
            raise httpx.ReadTimeout(key, request=req)
        if scenario == "echo":
            return httpx.Response(200, json={"secret": key}, headers={"test": key})
        if scenario == "status500":
            return httpx.Response(500, json={"error": {"message": "synthetic failure"}})
        return httpx.Response(200, json=success(provider))

    result = workspace_dispatch.execute(
        binding,
        SecretStr(key),
        providers.ActorRequest(
            model="test-model", actor_text="ACTOR_ONLY_CONTEXT", max_output_tokens=1024
        ),
        transport=httpx.MockTransport(handle),
    )
    assert len(requests) == 1
    assert key not in str(result)
    assert key not in caplog.text
    assert result.usage["dispatch_origin"] == "sdk_mock"
    assert result.status == (
        "completed"
        if scenario == "success"
        else "execution_unknown"
        if scenario in ("timeout", "echo", "status500")
        else "failed_operational"
    )
