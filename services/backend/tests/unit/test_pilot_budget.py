"""Broker admission control with manufactured durable-state doubles; no model calls."""

import hashlib
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_pilot_profiles import configure

from anvil import pilot_budget, workspace_execution


def setup_broker(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("ANVIL_WORKER_BROKER_ENABLED", "true")
    t = {key: str(uuid4()) for key in ["project", "actor", "group", "plan", "call"]}
    binding = {"provider": "openai", "model_id": "gpt-6.1-sol"}
    request = SimpleNamespace(actor_text="Manufactured actor-only input")
    state = {
        "group": {
            "id": t["group"],
            "project_id": t["project"],
            "created_by": t["actor"],
            "state": "launched",
        },
        "plan": {
            "check_id": str(uuid4()),
            "config": {"workspace_execution_group": t["group"], "workspace_model": dict(binding)},
        },
        "check": {"state": "running", "cancel_requested": False},
        "call": {
            "status": "dispatching",
            "usage": {
                "worker_broker_job": str(uuid4()),
                "worker_broker_lease_sha256": hashlib.sha256(b"manufactured-lease").hexdigest(),
            },
            "request_sha256": hashlib.sha256(request.actor_text.encode()).hexdigest(),
        },
        "writes": 0,
        "job": {
            "kind": "harbor_check",
            "status": "leased",
            "current": True,
            "lease_token": "manufactured-lease",
        },
        "ready": True,
        "capacity": True,
    }
    state["job"]["target_id"] = state["plan"]["check_id"]

    class Connection:
        def execute(self, query, args):
            assert "pilot_broker_claimed" in query
            state["writes"] += 1
            state["call"]["usage"]["pilot_broker_claimed"] = True

    @contextmanager
    def transaction(project, actor):
        assert (project, actor) == (t["project"], t["actor"])
        yield Connection()

    def one(c, query, args=()):
        if "pilot_dispatch_capacity" in query:
            return {"ok": state["capacity"]}
        if "workspace_execution_groups" in query:
            return state["group"]
        if "harbor_agent_plans" in query:
            return state["plan"]
        if "harbor_checks" in query:
            return state["check"]
        if "harbor_agent_calls" in query:
            return state["call"]
        if "anvil.jobs" in query:
            return state["job"]
        raise AssertionError(query)

    monkeypatch.setattr(pilot_budget, "transaction", transaction)
    monkeypatch.setattr(pilot_budget, "one", one)
    monkeypatch.setattr(pilot_budget, "issues", lambda c, row: [])
    monkeypatch.setattr(
        workspace_execution, "plan_readiness", lambda c, plan: {"ready": state["ready"]}
    )
    return t, binding, request, state


def test_global_capacity_denial_never_claims_sdk_slot(monkeypatch):
    ticket, binding, request, state = setup_broker(monkeypatch)
    state["capacity"] = False
    assert not pilot_budget.dispatch_allowed(binding, ticket, False, request)
    assert state["writes"] == 0


def test_bounded_golden_switch_does_not_open_other_workspace_plans(monkeypatch):
    ticket, binding, request, state = setup_broker(monkeypatch)
    monkeypatch.setenv("ANVIL_GOLDEN_KYC_PAID_ENABLED", "true")
    assert not pilot_budget.dispatch_allowed(binding, ticket, False, request)
    assert state["writes"] == 0


def test_broker_intent_claim_is_one_way_and_unknown_is_never_resent(monkeypatch):
    t, binding, request, state = setup_broker(monkeypatch)
    assert pilot_budget.dispatch_allowed(binding, t, False, request)
    assert not pilot_budget.dispatch_allowed(binding, t, False, request)
    assert state["writes"] == 1
    state["call"]["status"] = "execution_unknown"
    state["call"]["usage"] = {}
    assert not pilot_budget.dispatch_allowed(binding, t, False, request)
    assert state["writes"] == 1


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s["group"].update(state="draft"),
        lambda s: s["check"].update(cancel_requested=True),
        lambda s: s["check"].update(state="cancelled"),
        lambda s: s.update(ready=False),
        lambda s: s["call"].update(request_sha256="0" * 64),
        lambda s: s["call"].update(status="completed"),
        lambda s: s["plan"]["config"]["workspace_model"].update(model_id="gpt-6-astra"),
        lambda s: s["job"].update(current=False),
        lambda s: s["job"].update(lease_token="rotated"),
        lambda s: s["call"]["usage"].pop("worker_broker_job"),
    ],
)
def test_cancel_authority_prompt_and_model_changes_prevent_claim(monkeypatch, change):
    t, binding, request, state = setup_broker(monkeypatch)
    change(state)
    assert not pilot_budget.dispatch_allowed(binding, t, False, request)
    assert state["writes"] == 0


def test_missing_forged_ticket_generation_and_unapproved_models_fail_before_io(monkeypatch):
    t, binding, request, state = setup_broker(monkeypatch)
    for ticket in [None, {}, {**t, "call": "not-a-uuid"}]:
        assert not pilot_budget.dispatch_allowed(binding, ticket, False, request)
    assert not pilot_budget.dispatch_allowed(binding, t, True, request)
    assert not pilot_budget.dispatch_allowed(
        {**binding, "model_id": "gpt-6-astra"}, t, False, request
    )
    assert state["writes"] == 0
