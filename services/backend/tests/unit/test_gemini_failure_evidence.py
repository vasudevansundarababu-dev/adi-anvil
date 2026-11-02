"""Gemini error diagnosis must retain uncertainty, privacy and one dispatch."""

from dataclasses import asdict

import httpx
import pytest
from pydantic import SecretStr

from anvil import providers, workspace_dispatch, workspace_execution


@pytest.mark.parametrize(
    "provider,model,episode,expected",
    [
        ("gemini", "gemini-3.8-flash", 300, 180),
        ("gemini", "gemini-3.8-flash", 45, 45),
        ("gemini", "another-model", 300, 90),
        ("openai", "gpt-6-astra", 300, 90),
        ("anthropic", "claude-opus-5-5", 300, 90),
    ],
)
def test_new_plan_timeout_policy_is_model_specific_and_episode_bounded(
    provider, model, episode, expected
):
    assert (
        workspace_execution.request_timeout_seconds(
            {"provider": provider, "model_id": model}, episode
        )
        == expected
    )


@pytest.mark.parametrize("remaining", [0, -1, True, 601, 1.5])
def test_expired_or_invalid_episode_budget_blocks_before_dispatch(remaining):
    with pytest.raises(RuntimeError, match="agent_timeout"):
        workspace_execution.decision(None, None, None, 0, remaining_seconds=remaining)


@pytest.mark.parametrize(
    "status,rpc", [(500, "INTERNAL"), (503, "UNAVAILABLE"), (504, "DEADLINE_EXCEEDED")]
)
def test_gemini_server_error_retains_safe_evidence_without_retry(status, rpc):
    calls = []
    secret = "synthetic-gemini-error-private-key"

    def handle(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={"error": {"code": status, "status": rpc, "message": "PRIVATE ACTOR BODY"}},
        )

    result = workspace_dispatch.execute(
        {
            "provider": "gemini",
            "model_id": "gemini-3.8-flash",
            "destination": providers.PROVIDERS["gemini"][2],
            "max_output_tokens": 128,
        },
        SecretStr(secret),
        providers.ActorRequest(
            model="gemini-3.8-flash", actor_text="Synthetic actor only", max_output_tokens=128
        ),
        transport=httpx.MockTransport(handle),
    )
    assert len(calls) == 1
    assert result.status == "execution_unknown"
    assert result.error_code == "provider_error_after_dispatch"
    assert result.actual_cost_micro_usd is None
    assert result.text is None
    evidence = workspace_execution.provider_evidence(result)
    assert evidence["provider_http_status"] == status
    assert evidence["provider_status"] == rpc
    assert evidence["token_usage"] == {}
    assert "PRIVATE ACTOR BODY" not in str(asdict(result))
    assert secret not in str(evidence)


@pytest.mark.parametrize(
    "status,rpc", [(True, "UNAVAILABLE secret"), (999, {"status": "UNAVAILABLE"}), ("503", [])]
)
def test_reconciliation_drops_untrusted_error_metadata(status, rpc):
    result = providers.Result(
        "execution_unknown",
        usage={"provider_http_status": status, "provider_status": rpc, "message": "PRIVATE"},
    )
    evidence = workspace_execution.provider_evidence(result)
    assert "provider_http_status" not in evidence
    assert "provider_status" not in evidence
    assert "PRIVATE" not in str(evidence)
