"""Declared fictional review mechanics, not actual SME policy/calibration."""

from uuid import uuid4

from test_benchmark_scores import HASH, cells, protocol

from anvil.benchmark_protocol import ReviewPolicy
from anvil.benchmark_review_policy import requirements, review_state


def reviewed(threshold="50", critical=False):
    p = protocol()
    policy = ReviewPolicy.model_validate(
        {
            "tasks": [
                {
                    "task_revision_id": str(t.task_revision_id),
                    "pass_threshold_percent": threshold,
                    "critical_criterion_ids": ["fictional-C0"] if critical else [],
                }
                for t in p.tasks
            ],
            "calibration_sha256": HASH,
            "first_assignment_id": str(uuid4()),
            "second_assignment_id": str(uuid4()),
            "adjudicator_assignment_id": str(uuid4()),
        }
    )
    return p.model_copy(update={"review_policy": policy})


def test_frozen_sample_does_not_depend_on_outputs_success_or_rerun():
    p = reviewed()
    before, after = requirements(p, []), requirements(p, cells(p))

    def sample(value):
        return {c["cell_key"] for c in value["cells"] if "frozen_sample" in c["reasons"]}

    assert sample(before) == sample(after) == sample(requirements(p, cells(p, zero=True)))
    assert len(before["cells"]) == 18


def test_five_percentage_points_is_inclusive_using_task_percent():
    p = reviewed(threshold="95")
    assert all(
        "within_five_percentage_points" in c["reasons"] for c in requirements(p, cells(p))["cells"]
    )
    outside = reviewed(threshold="94.99999999")
    assert all(
        "within_five_percentage_points" not in c["reasons"]
        for c in requirements(outside, cells(outside))["cells"]
    )


def test_declared_critical_zero_requires_second_review_without_changing_points():
    p = reviewed(critical=True)
    result = requirements(p, cells(p, zero=True))
    assert result["second_required"]
    assert all("critical_failure" in c["reasons"] for c in result["cells"])


def test_first_approval_cannot_satisfy_mandatory_second_review():
    p = reviewed(threshold="100")
    required = requirements(p, cells(p))
    projection = {"review_requirements": required}
    first = {"assignment_id": required["first_assignment_id"], "decision": "approved"}
    second = {"assignment_id": required["second_assignment_id"], "decision": "approved"}
    assert review_state(projection, []) == "pending"
    assert review_state(projection, [first]) == "second_review_required"
    assert review_state(projection, [first, second]) == "approved"
    second["decision"] = "disputed"
    assert review_state(projection, [first, second]) == "adjudication_required"
    adjudication = {
        "assignment_id": required["adjudicator_assignment_id"],
        "decision": "adjudicated",
    }
    assert review_state(projection, [first, second, adjudication]) == "adjudicated"


def test_missing_declared_policy_never_implies_review_approval():
    assert requirements(protocol(), [])["state"] == "blocked_missing_policy"
    assert review_state({}, []) == "blocked_missing_policy"
