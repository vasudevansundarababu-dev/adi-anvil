"""Offline safety controls, not evidence of valid paid admission."""

from contextlib import contextmanager

import pytest

from anvil import marketing_paid_roles as roles


def adapter(dispatch, client):
    return roles.RoleAdapter(None, {}, "episode", 0, {}, dispatch, client)


def test_ambiguous_dispatch_is_attempted_once_without_tool_io_or_reclaim(monkeypatch):
    attempted = []
    monkeypatch.setattr(roles, "claim_turn", lambda *args: (0, {"role": "intent"}))

    def dispatch(stage, context, remaining):
        attempted.append(stage)
        raise TimeoutError("ambiguous broker response")

    def forbidden(*args):
        raise AssertionError("Ambiguous inference must not reach tools or completion")

    monkeypatch.setattr(roles, "response", forbidden)
    with pytest.raises(TimeoutError):
        adapter(dispatch, forbidden)({"id": "intent", "type": "agent_step"}, {}, 1, 1)
    assert attempted == [0]


def test_non_agent_node_cannot_be_impersonated_by_candidate(monkeypatch):
    monkeypatch.setattr(roles, "claim_turn", lambda *args: pytest.fail("No SDK claim permitted"))
    with pytest.raises(RuntimeError, match="qualified_host_adapter"):
        adapter(None, None)({"type": "human_step"}, {}, 1, 1)


def test_artifact_is_derived_from_sql_receipt_not_dispatch_callback_claim(monkeypatch):
    monkeypatch.setattr(roles, "validate_response_protocol", lambda *args: None)
    monkeypatch.setattr(roles, "claim_turn", lambda *args: (2, {"role": "policy"}))
    monkeypatch.setattr(roles, "response", lambda *args: {"id": "physical-call", "text": "actual"})
    monkeypatch.setattr(roles, "apply_turn", lambda *args: {"artifact": {"untrusted": True}})
    monkeypatch.setattr(
        roles,
        "record_turn",
        lambda *args: {"completed_node": True, "artifact": {"trusted_receipt": True}},
    )
    seen = []

    @contextmanager
    def client(role, before):
        seen.append(role)
        yield object()

    result = adapter(lambda *args: "actual", client)(
        {"id": "policy_step", "type": "agent_step"}, {"brief": {}}, 1, 1
    )
    assert result["artifact"] == {"trusted_receipt": True}
    assert seen == ["policy"]
    assert result["receipt"]["model_performance_validated"] is False


def test_elapsed_campaign_limit_precedes_any_new_sdk_intent(monkeypatch):
    now = [0]
    monkeypatch.setattr(
        roles, "claim_turn", lambda *args: pytest.fail("Expired campaign cannot claim")
    )
    runtime = roles.RoleAdapter(
        None,
        {},
        "episode",
        0,
        {},
        None,
        None,
        episode_timeout_seconds=600,
        clock=lambda: now[0],
    )
    now[0] = 600
    with pytest.raises(TimeoutError, match="no_truncation_or_replay"):
        runtime({"id": "intent", "type": "agent_step"}, {}, 1, 1)
