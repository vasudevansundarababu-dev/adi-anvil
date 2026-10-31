import json

import httpx
import pytest

from anvil.config import ROOT
from anvil.harbor_agents import (
    MAX_OUTPUT_TOKENS,
    MAX_PROMPT_BYTES,
    Authority,
    actor_prompt,
    call_bound,
    execute_provider,
)
from anvil.harbor_package import agent_admission, compile_package


def admission():
    task, _, _ = compile_package(
        (ROOT / "contracts/praxis/synthetic-marketing-staged.task.json").read_bytes()
    )
    return agent_admission(task)


def test_mediator_never_reads_reference_examples_or_early_future():
    admitted = admission()
    assert "reference_output" not in json.dumps(admitted)
    first = actor_prompt(admitted, 0, [])
    assert "FUTURE-NORTHSTAR" not in first and "PRIVATE-NORTHSTAR" not in first
    assert "s1-channel" not in first
    previous = {"channel": "search", "spend_usd": 1000, "evidence_id": "ev-channel-costs"}
    second = actor_prompt(admitted, 1, [previous])
    assert "FUTURE-NORTHSTAR" in second
    assert '"committed_spend":1000' in second
    assert "PRIVATE-NORTHSTAR" not in second and "s2-channel" not in second
    with pytest.raises(RuntimeError, match="previous_stage"):
        actor_prompt(admitted, 1, [{**previous, "spend_usd": 1001}])
    with pytest.raises(RuntimeError, match="unsupported_stage"):
        actor_prompt(admitted, 1, [])


def test_mocked_sdk_is_bounded_json_only_without_retries(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-contract-key")
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["model"] == "synthetic-model"
        assert body["max_output_tokens"] == MAX_OUTPUT_TOKENS
        assert body["store"] is False
        assert "tools" not in body
        return httpx.Response(
            200,
            json={
                "id": "test-response",
                "model": "synthetic-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"channel":"search"}'}],
                    }
                ],
                "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
            },
        )

    result = execute_provider(
        "synthetic-model", actor_prompt(admission(), 0, []), httpx.MockTransport(handler)
    )
    assert result.status == "completed" and len(calls) == 1
    assert "PRIVATE-NORTHSTAR" not in json.dumps(calls)
    with pytest.raises(ValueError, match="bound"):
        execute_provider(
            "synthetic-model", "x" * (MAX_PROMPT_BYTES + 1), httpx.MockTransport(handler)
        )
    assert len(calls) == 1

    def ambiguous(request):
        calls.append("ambiguous")
        raise httpx.ReadTimeout("synthetic ambiguous dispatch", request=request)

    result = execute_provider("synthetic-model", "actor only", httpx.MockTransport(ambiguous))
    assert result.status == "execution_unknown" and calls.count("ambiguous") == 1


def test_conservative_bound_uses_prompt_and_output_limits():
    policy = Authority.model_validate(
        {
            "reference": "harbor:synthetic-test",
            "project_id": "a0000000-0000-4000-8000-000000000002",
            "provider": "openai",
            "model": "synthetic-model",
            "total_cap_micro_usd": 1000000,
            "input_micro_usd_per_million_tokens": 2000000,
            "output_micro_usd_per_million_tokens": 8000000,
            "pricing_revision": "synthetic-not-real-pricing",
            "expires_at": "2099-01-01T00:00:00Z",
            "pricing_expires_at": "2099-01-01T00:00:00Z",
        }
    )
    assert call_bound(policy) == ((MAX_PROMPT_BYTES + 1024) * 2 + MAX_OUTPUT_TOKENS * 8)
