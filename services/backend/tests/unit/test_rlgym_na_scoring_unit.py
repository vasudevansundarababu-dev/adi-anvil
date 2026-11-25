"""Spec §16 (one task covers all four account types): a check that doesn't apply to a case (a risk rating or custodial
authority on a single account; a bulletin check in a case without one) is "not applicable". It is excluded from both the
points earned and the maximum, never a pass or a fail; the percentage is over the applicable checks only."""

import inspect

from anvil.rlgym.scoring import s7
from anvil.rlgym.scoring import sandbox_runner as runner
from anvil.rlgym.scoring import service as scoring

PROF = {
    "anchors": {"pass": 5, "partial": 2, "fail": 0},
    "max_points": 15,
    "threshold_points": 10,
    "weights": {"a": 5, "b": 5, "c": 5},
    "critical": ["c"],
}


def test_s7_outcome_over_applicable_checks_only():
    # c is not applicable: it isn't passed in, so the maximum is 10 and the threshold the same share (10/15 of 10).
    out = s7.outcome(PROF, {"a": "pass", "b": "partial"}, PROF["weights"])
    assert out["max_points"] == 10 and out["points"] == 7
    assert out["passed"] is True and out["critical_failed"] == []


def blk(i, verdict, critical=False):
    return (
        {"id": i, "kind": "judgment", "check": "decision"},
        {"verdict": verdict, "critical": critical},
    )


def run(pairs):
    return runner.run_blocks(
        {
            "config": {"runner": "verifier_blocks", "runner_version": 2},
            "blocks": [b for b, _ in pairs],
            "judgment_results": {b["id"]: r for b, r in pairs},
            "case_id": "c",
        }
    )


def test_a_criterion_whose_checks_all_do_not_apply_is_not_applicable():
    out = run([blk("x", "not_applicable"), blk("y", "not_applicable")])
    assert out["verdict"] == "not_applicable" and out["points"] is None


def test_a_not_applicable_line_never_decides_a_pass_or_a_fail():
    assert run([blk("x", "pass"), blk("y", "not_applicable")])["verdict"] == "pass"
    assert run([blk("x", "fail"), blk("y", "not_applicable")])["verdict"] == "fail"


def test_scoring_excludes_not_applicable_from_points_maximum_and_blocked():
    src = inspect.getsource(scoring)
    assert 'verdict == "not_applicable"' in src
    assert "not_applicable.append(criterion_id)" in src


def test_a_critical_line_fails_the_criterion_and_says_so():
    out = run([blk("x", "pass"), blk("y", "fail", critical=True)])
    assert out["verdict"] == "fail" and out["critical"] is True


def test_a_judgment_line_that_did_not_run_is_blocked_never_a_pass():
    out = runner.run_blocks(
        {
            "config": {"runner": "verifier_blocks", "runner_version": 2},
            "blocks": [{"id": "x", "kind": "judgment", "check": "decision"}],
            "case_id": "c",
        }
    )
    assert out["verdict"] == "blocked"


def test_scoring_fails_the_task_on_a_critical_line():
    assert 'v.get("critical")' in inspect.getsource(scoring)
