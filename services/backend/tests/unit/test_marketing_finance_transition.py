"""New isolated selected-book controls; no persistence or report activation."""

from copy import deepcopy

import pytest
from test_marketing_component_finance import source as selected_source
from test_marketing_world_authority import book
from test_marketing_world_readiness import setup

from anvil.marketing_task2_persistence import freeze
from anvil.marketing_world_authority import prepare as prepare_authority
from anvil.marketing_world_finance import normalize, position
from anvil.marketing_world_finance_transition import prepare, validate_transition


@pytest.mark.parametrize("case", ["GT2-R01", "GT2-R02"])
@pytest.mark.parametrize("branch", ["positive", "null", "negative"])
def test_selected_finance_advances_actual_parent_totals_and_releases_unused_cap(case, branch):
    controller, execution, node, inputs, sources, *_ = setup(case)
    controller._outcome = branch
    baseline = book(case)
    controller, *_ = prepare_authority(controller, execution, node, inputs, sources, baseline)
    files, pins, _ = selected_source(case, branch)
    selected = normalize(case, files, pins, branch=branch)
    for at in ["2027-02-12T12:00:00Z", "2027-02-15T00:00:00Z", "2027-02-22T00:00:00Z",
               "2027-03-01T00:00:00Z", "2027-03-29T00:00:00Z"]:
        before = freeze(controller)
        successor = prepare(controller, baseline, selected, at)
        assert freeze(controller) == before
        actual = position(selected, at)
        assert successor._settled == actual["settled"]
        assert successor._committed == actual["committed"]
        assert sum(successor._reservations.values()) == actual["reserved"]
        controller = successor
    assert sum(controller._reservations.values()) == 0
    assert controller._committed == 0


def test_selected_accounting_cannot_change_global_production_cost_or_dates():
    baseline = book("GT2-R01")
    files, pins, _ = selected_source()
    selected = normalize("GT2-R01", files, pins, branch="positive")
    selected["commitments"][0]["committed_minor"] += 1
    with pytest.raises(ValueError, match="global cost"):
        validate_transition(baseline, selected)


def test_actor_like_outcome_substitution_and_unexplained_spend_are_denied():
    controller, execution, node, inputs, sources, *_ = setup()
    baseline = book(controller.case_id)
    controller, *_ = prepare_authority(controller, execution, node, inputs, sources, baseline)
    files, pins, _ = selected_source(branch="negative")
    selected = normalize(controller.case_id, files, pins, branch="negative")
    with pytest.raises(ValueError, match="Another private outcome"):
        prepare(controller, baseline, selected, "2027-02-15T00:00:00Z")
    files, pins, _ = selected_source()
    selected = normalize(controller.case_id, files, pins, branch="positive")
    controller._settled += 1
    before = freeze(controller)
    with pytest.raises(ValueError, match="Unreconciled"):
        prepare(controller, baseline, selected, "2027-02-15T00:00:00Z")
    assert freeze(controller) == before


def test_missing_independent_controller_authority_never_activates_financial_branch():
    controller, *_ = setup()
    baseline = book(controller.case_id)
    files, pins, _ = selected_source()
    selected = normalize(controller.case_id, files, pins, branch="positive")
    before = deepcopy(freeze(controller))
    with pytest.raises(ValueError, match="Exactly one independent"):
        prepare(controller, baseline, selected, "2027-02-15T00:00:00Z")
    assert freeze(controller) == before
