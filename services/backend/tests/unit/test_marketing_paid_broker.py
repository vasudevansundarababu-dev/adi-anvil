"""Manufactured broker-state controls; no SDK calls or valid admission claim."""

import pytest
from test_pilot_budget import setup_broker

from anvil import marketing_paid_budget, pilot_budget


def test_marketing_switch_does_not_open_unrelated_workspace_plans(monkeypatch):
    ticket, binding, request, state = setup_broker(monkeypatch)
    monkeypatch.setenv("ANVIL_MARKETING_PAID_ENABLED", "true")
    assert not pilot_budget.dispatch_allowed(binding, ticket, False, request)
    assert state["writes"] == 0


@pytest.mark.parametrize("kind", ["harbor_check", "benchmark_golden_paid"])
def test_marketing_plan_cannot_borrow_other_job_kinds(monkeypatch, kind):
    ticket, binding, request, state = setup_broker(monkeypatch)
    state["plan"]["config"]["marketing_paid"] = True
    state["job"]["kind"] = kind
    monkeypatch.setattr(
        marketing_paid_budget, "claim", lambda *args: pytest.fail("Wrong job cannot claim")
    )
    assert not pilot_budget.dispatch_allowed(binding, ticket, False, request)
    assert state["writes"] == 0


def test_marketing_native_claim_denial_precedes_shared_slot_consumption(monkeypatch):
    ticket, binding, request, state = setup_broker(monkeypatch)
    state["plan"]["config"]["marketing_paid"] = True
    state["job"]["kind"] = "benchmark_marketing_paid"
    claims = []
    monkeypatch.setattr(
        marketing_paid_budget, "claim", lambda *args: claims.append("denied") or False
    )
    assert not pilot_budget.dispatch_allowed(binding, ticket, False, request)
    assert claims == ["denied"] and state["writes"] == 0


def test_dual_native_flags_are_rejected_before_any_domain_claim(monkeypatch):
    ticket, binding, request, state = setup_broker(monkeypatch)
    state["plan"]["config"].update(marketing_paid=True, golden_kyc_paid=True)
    monkeypatch.setattr(marketing_paid_budget, "claim", lambda *args: pytest.fail("No mixed claim"))
    assert not pilot_budget.dispatch_allowed(binding, ticket, False, request)
    assert state["writes"] == 0
