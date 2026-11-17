"""New clock-contract negatives; source dates and twelve observations stay fixed."""

from datetime import timedelta

import pytest
from test_marketing_activation_definition import proposal
from test_marketing_world_readiness import setup

from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_task2_tools import execute
from anvil.marketing_world_campaign_effect import prepare
from anvil.marketing_world_definition import definition


def test_regular_weekly_program_cannot_qualify_without_a_permitted_approval_observation():
    _, value = proposal()
    start = timestamp(value["start"])
    for index in range(11):
        value["windows"][index]["instant"] = (start + timedelta(days=7 * index)).isoformat()
    assert len(value["windows"]) == 12
    with pytest.raises(ValueError, match="No observation window permits non-retroactive"):
        definition(value)


def test_last_observation_must_cover_actual_delayed_source_closeout_reports():
    _, value = proposal()
    value["windows"][-1]["instant"] = "2027-03-30T00:00:00Z"
    with pytest.raises(ValueError, match="pinned projected source record"):
        definition(value)


def test_earlier_clock_does_not_make_conditional_source_authority_available():
    _, value = proposal()
    world = definition(value)
    controller, execution, node, inputs, *_ = setup()
    controller._clock = "2027-02-12T11:59:59Z"
    controller._initial = world.controller(0)._initial
    successor, public, port = prepare(controller, world, execution, node, inputs)
    assert successor is None and public["campaign_authority_issued"] is False and port == "timeout"


def test_explicit_twelve_observations_cover_approval_interval_and_all_twelve_report_weeks():
    _, value = proposal()
    world = definition(value)
    assert len(world.windows) == 12
    assert world.windows[4].instant.isoformat() == "2027-02-12T12:00:00+00:00"
    assert world.windows[-1].instant.isoformat() == "2027-03-31T00:00:00+00:00"
    controller, execution, *_ = setup()
    controller._initial = world.controller(0)._initial
    controller.advance(world.windows[-1].instant.isoformat())
    for week in range(1, 13):
        result = execute(controller, "performance", "reports.query",
                         {"window": week, "filters": {"locale": "en-US", "channel": "search",
                                                       "report_detail": False, "report_grain": "weekly"}}, execution)
        assert result["status"] == "completed" and len(result["result"]["records"]) == 1
        assert timestamp(result["result"]["records"][0]["content"]["released_at"]) <= world.windows[-1].instant
