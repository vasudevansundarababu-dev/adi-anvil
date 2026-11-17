"""New already-activated window accounting controls; no actual SQL release."""

import pytest
from test_marketing_activation_definition import proposal
from test_marketing_world_readiness import setup

from anvil.marketing_task2_persistence import freeze
from anvil.marketing_world_campaign_effect import prepare as prepare_effect
from anvil.marketing_world_campaign_release import prepare
from anvil.marketing_world_definition import definition
from anvil.marketing_world_finance import position


@pytest.fixture(scope="module")
def world():
    _, value = proposal()
    return definition(value)


def approved(world):
    controller, execution, node, inputs, *_ = setup()
    controller._initial = world.controller(0)._initial
    successor, _, port = prepare_effect(controller, world, execution, node, inputs)
    assert port == "responded"
    return successor


def test_selected_finance_and_current_balance_advance_together_without_reactivating_reports(world):
    controller = approved(world)
    selected, _ = world.selected_programs(controller._outcome)
    report_rows = controller._initial["reports"]
    for instant in ["2027-02-22T00:00:00Z", "2027-03-01T00:00:00Z", "2027-03-31T00:00:00Z"]:
        before = freeze(controller)
        successor = prepare(controller, world, instant)
        assert freeze(controller) == before
        assert successor._initial["reports"] == report_rows
        expected = position(selected, instant)
        current = next(r["public"] for r in successor._initial["budget-snapshots"]
                       if r["public"]["provenance"] == "CURRENT_SOURCE_RECONCILED_SIMULATED_CONTROLLER_ACCOUNTING")
        assert current["as_of"] == instant
        assert current["actual_settled_usd_minor"] == successor._settled == expected["settled"]
        assert current["binding_outstanding_usd_minor"] == successor._committed == expected["committed"]
        assert current["active_reservations_usd_minor"] == sum(successor._reservations.values()) == expected["reserved"]
        controller = successor
    assert sum(controller._reservations.values()) == 0


def test_passage_of_time_without_independent_decision_does_not_activate_any_alternative(world):
    controller = world.controller(0)
    before = freeze(controller)
    assert prepare(controller, world, "2027-03-31T00:00:00Z") is None
    assert freeze(controller) == before


def test_unreconciled_visible_current_balance_denies_release(world):
    controller = approved(world)
    current = next(r for r in controller._initial["budget-snapshots"]
                   if r["public"]["provenance"] == "CURRENT_SOURCE_RECONCILED_SIMULATED_CONTROLLER_ACCOUNTING")
    current["public"]["active_reservations_usd_minor"] = 0
    before = freeze(controller)
    with pytest.raises(ValueError, match="prior current balance"):
        prepare(controller, world, "2027-02-22T00:00:00Z")
    assert freeze(controller) == before
