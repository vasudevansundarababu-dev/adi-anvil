"""Versioned report release contracts; no fabricated human decisions."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from anvil.benchmark_protocol import ReviewPolicy
from anvil.benchmark_report_policy import Configure
from anvil.db import digest


def task_policy():
    return [
        {
            "task_revision_id": str(uuid4()),
            "pass_threshold_percent": "50",
            "critical_criterion_ids": [],
        }
        for _ in range(3)
    ]


def test_legacy_policy_json_and_hash_are_not_rewritten():
    raw = {
        "tasks": task_policy(),
        "calibration_sha256": "a" * 64,
        "first_assignment_id": str(uuid4()),
        "second_assignment_id": str(uuid4()),
        "adjudicator_assignment_id": str(uuid4()),
        "sample_percent": 10,
        "borderline_percentage_points": 5,
    }
    restored = ReviewPolicy.model_validate(raw).model_dump(mode="json")
    assert restored == raw
    assert digest(restored) == digest(raw)


@pytest.mark.parametrize("count", [0, 1, 4, 10])
def test_v2_no_three_person_stage_requirement(count):
    policy = ReviewPolicy.model_validate(
        {
            "version": 2,
            "tasks": task_policy(),
            "calibration_sha256": "a" * 64,
            "reviewer_assignment_ids": [str(uuid4()) for _ in range(count)],
        }
    )
    assert len(policy.reviewer_assignment_ids) == count
    assert policy.first_assignment_id is None
    assert policy.model_dump(mode="json")["version"] == 2


@pytest.mark.parametrize("value", [-1, 11, True, "1"])
def test_configuration_is_a_bounded_strict_count(value):
    with pytest.raises(ValidationError):
        Configure(required_reviewers=value)
