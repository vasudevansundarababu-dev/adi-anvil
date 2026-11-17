"""New private projection controls through the actual published read helper.

No SQL, HTTP, worker, native framework or model execution is exercised.
"""

from copy import deepcopy

import pytest
from test_marketing_component_finance import source as selected_source
from test_marketing_outcome_reports import source as report_source
from test_marketing_world_authority import book
from test_marketing_world_readiness import setup

from anvil.marketing_task2_persistence import freeze
from anvil.marketing_task2_tools import execute
from anvil.marketing_world_authority import prepare as prepare_authority
from anvil.marketing_world_finance import normalize
from anvil.marketing_world_finance_transition import prepare as prepare_finance
from anvil.marketing_world_outcome_data import compile_reports
from anvil.marketing_world_report_activation import prepare
from anvil.praxis_generic_contract import canonical


def ready(branch="positive"):
    controller, execution, node, inputs, sources, *_ = setup()
    controller._outcome = branch
    files, pins = report_source(branch=branch)
    program = compile_reports(controller.case_id, files, pins, branch=branch)
    controller._initial["reports"] = [{"actor_visible": True, "outcome_binding": None,
                                       "released_at": row["released_at"], "public": deepcopy(row)}
                                      for row in program["baseline"]]
    baseline = book(controller.case_id)
    controller, *_ = prepare_authority(controller, execution, node, inputs, sources, baseline)
    files, pins, _ = selected_source(branch=branch)
    selected = normalize(controller.case_id, files, pins, branch=branch)
    controller = prepare_finance(controller, baseline, selected, controller._clock)
    return controller, program, execution


@pytest.mark.parametrize("branch", ["positive", "null", "negative"])
def test_selected_reports_are_invisible_until_actual_release_and_hide_outcome(branch):
    controller, program, execution = ready(branch)
    before = freeze(controller)
    successor = prepare(controller, program)
    assert freeze(controller) == before
    query = {"window": 7, "filters": {"locale": "en-US", "channel": "search", "report_detail": True, "report_grain": "daily"}}
    pending = execute(successor, "performance", "reports.query", query, execution)
    assert pending["status"] == "pending" and not pending["result"].get("records")
    successor.advance("2027-02-18T00:00:00Z")
    result = execute(successor, "performance", "reports.query", query, execution)
    assert result["status"] == "completed" and result["result"]["records"]
    assert all(row["content"]["released_at"] <= "2027-02-18T00:00:00Z" for row in result["result"]["records"])
    encoded = canonical(result)
    assert not any(label in encoded for label in (b"_positive_", b"_negative_", b"_null_", b"reuse-test-"))


def test_past_released_observation_cannot_be_rewritten_even_by_prepared_program():
    controller, program, _ = ready()
    row = next(r for r in program["selected"] if r["released_at"] < controller._clock)
    row["verified_visits"] += 1
    before = freeze(controller)
    with pytest.raises(ValueError, match="already released observations"):
        prepare(controller, program)
    assert freeze(controller) == before


def test_report_activation_denies_missing_baseline_and_replay():
    controller, program, _ = ready()
    successor = prepare(controller, program)
    with pytest.raises(ValueError, match="one-use"):
        prepare(successor, program)
    controller._initial["reports"].pop()
    with pytest.raises(ValueError, match="Complete original"):
        prepare(controller, program)


def test_another_outcome_program_cannot_activate():
    controller, _, _ = ready()
    files, pins = report_source(branch="negative")
    program = compile_reports(controller.case_id, files, pins, branch="negative")
    with pytest.raises(ValueError, match="Selected private report program"):
        prepare(controller, program)
