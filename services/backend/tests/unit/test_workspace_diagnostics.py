from decimal import Decimal

from anvil.workspace_diagnostics import planned_attempts, result_public, summarize


def test_only_finalized_valid_scores_enter_denominators():
    rows = [
        {"state": "finalized", "outcome": "pass", "score": Decimal(90)},
        {"state": "finalized", "outcome": "fail", "score": Decimal(50)},
        {"state": "awaiting_review", "outcome": "pending_review", "score": Decimal(99)},
        {"state": "finalized", "outcome": "invalid", "score": Decimal(100)},
        {"state": "execution_unknown", "outcome": "unscorable", "score": None},
    ]
    m = summarize(rows)
    assert m["score"] == 70 and m["scored"] == 2 and m["attempts"] == 5
    assert m["passed"] == m["task_failed"] == m["unknown"] == m["invalid"] == 1
    assert summarize([])["score"] is None


def test_unfinished_output_and_candidate_remain_blinded():
    value = result_public(
        {
            "id": "episode",
            "state": "awaiting_review",
            "outcome": "pass",
            "score": 99,
            "candidate_key": "private-candidate",
            "task_revision_id": "task",
            "output_artifact_id": "output",
        }
    )
    assert value["score"] is None and not value["output_available"]
    assert "private-candidate" not in str(value)
    assert "output_artifact_id" not in value
    assert value["outcome"] == "not_finalized"


def test_unscorable_is_terminal_and_unfinished_invalid_grade_stays_private():
    m = summarize(
        [
            {"state": "unscorable", "outcome": "unscorable", "score": None},
            {"state": "awaiting_review", "outcome": "invalid", "score": None},
        ]
    )
    assert m["unscorable"] == 1 and m["pending"] == 1
    assert m["invalid"] == 0


def test_dataset_snapshot_owns_planned_count_instead_of_template_suite_size():
    suite = {"task_revision_ids": ["one", "two", "three"]}
    protocol = {"candidates": ["A", "B"], "repetitions": 2}
    assert planned_attempts({}, suite, protocol) == 12
    assert planned_attempts({"dataset_snapshot": {"task_count": 5}}, suite, protocol) == 20
    assert planned_attempts({"dataset_snapshot": {"version_id": "legacy"}}, suite, protocol) is None
