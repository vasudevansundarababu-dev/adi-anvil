"""New combined source transition controls; no actual API commit or benchmark."""

from test_marketing_activation_definition import proposal
from test_marketing_world_readiness import setup

from anvil.marketing_task2_persistence import freeze
from anvil.marketing_world_campaign_effect import prepare
from anvil.marketing_world_definition import definition
from anvil.praxis_generic_contract import canonical


def test_complete_private_transition_binds_approval_finance_ledger_budget_reports_before_return():
    _, value = proposal()
    world = definition(value)
    controller, execution, node, inputs, *_ = setup()
    controller._initial = world.controller(0)._initial
    before = freeze(controller)
    successor, public, port = prepare(controller, world, execution, node, inputs)
    assert freeze(controller) == before
    assert port == "responded" and public["decision"] == "approved"
    assert successor._settled == 11535890 and successor._committed == 154762
    assert sum(successor._reservations.values()) == 200000
    assert any(r["outcome_binding"] == controller._outcome for r in successor._initial["reports"])
    assert sum(r["outcome_binding"] == controller._outcome for r in successor._initial["ledger"]) == 14
    current = successor._initial["budget-snapshots"][-1]["public"]
    assert current["active_reservations_usd_minor"] == 200000
    assert current["actual_settled_usd_minor"] == successor._settled
    assert b"reuse-test-" not in canonical(public)


def test_unresolved_readiness_returns_timeout_without_partial_finance_or_report_changes():
    _, value = proposal()
    world = definition(value)
    finding = {"id": "F1", "mandatory": True, "check": "rights", "status": "open", "evidence_refs": []}
    controller, execution, node, inputs, *_ = setup(finding=finding)
    controller._initial = world.controller(0)._initial
    before = freeze(controller)
    successor, public, port = prepare(controller, world, execution, node, inputs)
    assert successor is None and port == "timeout"
    assert public["decision"] == "pending" and public["campaign_authority_issued"] is False
    assert freeze(controller) == before
