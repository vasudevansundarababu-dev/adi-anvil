"""Gemini error diagnosis must retain uncertainty, privacy and one dispatch."""

from dataclasses import asdict

import httpx
import pytest
from pydantic import SecretStr

from anvil import providers, workspace_dispatch, workspace_execution


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
