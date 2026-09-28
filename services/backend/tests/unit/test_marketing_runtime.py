import importlib.util
import json

import httpx
import pytest

from anvil import marketing_env as env
from anvil import providers
from anvil.config import ROOT
from anvil.marketing_runtime import parse_response


def weekly(week):
    return {
        "action": {
            "week": week,
            "spend_usd": {"search": 3000, "social": 0, "webinar": 0, "email": 0},
            "message": "visibility",
            "refresh_creative": False,
            "rationale": "Observe accepted leads and delayed conversions.",
        },
        "strategy": "Test the operations segment, preserve budget and measure delayed conversion."
        if week == 1
        else None,
        "creative": {
            "headlines": ["See task owners", "Track due dates", "Export your workflow"],
            "landing_page": "Shared workflow boards and due-date reminders.",
        }
        if week in (1, 5, 9)
        else None,
        "decision_log": "Compare accepted leads with eventual customers; do not count pending leads as sales.",
    }


def test_thirteen_responses_and_offline_environment_parity():
    spec = importlib.util.spec_from_file_location(
        "offline_marketing", ROOT / "scripts/marketing_task.py"
    )
    offline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(offline)
    state = env.reset()
    for week in range(1, 13):
        obj = weekly(week)
        _, after = parse_response(json.dumps(obj), state)
        assert after == offline.step(state, obj["action"])
        state = after
    assert env.observe(state)["done"]
    final = {
        "board_memo": "Describe the receipts, targets and limitations.",
        "ledger": [
            {
                "week": w,
                "spend_usd": dict.fromkeys(("search", "social", "webinar", "email"), 0),
                **dict.fromkeys(
                    (
                        "creative_cost_usd",
                        "leads",
                        "accepted_qualified_leads",
                        "new_customers",
                        "cumulative_customers",
                        "remaining_budget_usd",
                        "pending_qualified_leads",
                    ),
                    0,
                ),
            }
            for w in range(1, 13)
        ],
    }
    assert parse_response(json.dumps(final), state)[1] == state
    assert env.initial_input() == offline.initial_input()


@pytest.mark.parametrize(
    "change", ["stale", "extra", "strategy", "creative", "budget", "boolean", "negative"]
)
def test_malformed_candidate_is_not_repaired(change):
    obj = weekly(1)
    if change == "stale":
        obj["action"]["week"] = 2
    if change == "extra":
        obj["tools"] = ["read_private_state"]
    if change == "strategy":
        obj["strategy"] = None
    if change == "creative":
        obj["creative"]["headlines"] = []
    if change == "budget":
        obj["action"]["spend_usd"]["search"] = 6001
    if change == "boolean":
        obj["action"]["spend_usd"]["search"] = True
    if change == "negative":
        obj["action"]["spend_usd"]["search"] = -1
    state = env.reset()
    with pytest.raises(ValueError):
        parse_response(json.dumps(obj), state)
    assert state == env.reset()


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', "```json\n{}\n```", "[]"])
def test_strict_json(text):
    with pytest.raises(ValueError):
        parse_response(text, env.reset())


def test_live_transport_contract_has_no_hidden_retries(monkeypatch):
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        assert str(request.url) == "https://api.openai.com/v1/responses"
        raise httpx.ReadTimeout("synthetic ambiguous timeout")

    client = httpx.Client
    monkeypatch.setenv("OPENAI_API_KEY", "anvil-contract-test-only")
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)

    class MockClient(client):
        def __init__(self, **kw):
            super().__init__(transport=httpx.MockTransport(handle), **kw)

    monkeypatch.setattr(providers.httpx, "Client", MockClient)
    result = providers.execute_marketing(
        providers.ActorRequest(
            model="gpt-6-sol",
            actor_text="Return JSON for this synthetic test.",
            max_output_tokens=8192,
        )
    )
    assert result.status == "execution_unknown"
    assert len(seen) == 1
    assert seen[0]["store"] is False
    assert seen[0]["service_tier"] == "default"
    assert seen[0]["max_output_tokens"] == 8192
    assert "tools" not in seen[0] and "previous_response_id" not in seen[0]
