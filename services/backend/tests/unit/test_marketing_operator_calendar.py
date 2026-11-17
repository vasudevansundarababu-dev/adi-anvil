"""New operator-only default calendar; source business dates are immutable."""

import os
from copy import deepcopy
from pathlib import Path

import pytest
from test_marketing_activation_definition import proposal
from test_marketing_world_descriptor_services import source

from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_world_calendar import propose, with_program
from anvil.marketing_world_definition import definition


@pytest.mark.parametrize("case", ["GT2-R01", "GT2-R02"])
def test_each_of_twelve_source_report_reviews_and_approval_event_fit_without_changing_business_dates(case):
    files, pins, _, services = source(case)
    path = f"cases/{case}/weekly_reports.jsonl"
    root = Path(os.environ["ANVIL_MARKETING_SOURCE_FIXTURE_ROOT"])
    files[path] = (root / path).read_bytes()
    before = deepcopy(services)
    program = propose(case, files, pins, services)
    assert services == before and program["campaign_source_dates_changed"] is False
    assert len(program["windows"]) == program["observation_count"] == 12
    assert timestamp(program["windows"][0]["instant"]) == timestamp("2027-01-13T00:00:00Z")
    assert timestamp(program["windows"][4]["instant"]) == timestamp("2027-02-12T12:00:00Z")
    assert timestamp(program["windows"][-1]["instant"]) == timestamp("2027-03-31T00:00:00Z")
    assert program["applied"] is program["qualified"] is False


def test_explicit_operator_application_produces_valid_source_successor_without_modifying_original():
    _, original = proposal()
    files, pins, _, services = source()
    path = "cases/GT2-R01/weekly_reports.jsonl"
    root = Path(os.environ["ANVIL_MARKETING_SOURCE_FIXTURE_ROOT"])
    files[path] = (root / path).read_bytes()
    program = propose("GT2-R01", files, pins, services)
    before = deepcopy(original)
    successor = with_program(original, program)
    parsed = definition(successor)
    assert original == before
    assert len(parsed.windows) == 12
    assert parsed.windows[4].instant == timestamp("2027-02-12T12:00:00Z")
    assert parsed.service_contract == definition(original).service_contract
