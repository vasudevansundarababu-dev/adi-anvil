"""reference.v2 statuses that mean "not graded yet": awaiting_sme (the SME decides) and awaiting_pm (the reference
depends on a placeholder rule the PM hasn't approved). Both are not applicable with the reason kept, skipped by the
reference-agent and lookup runs, never counted by V-04/V-01, and counted apart in the report."""

import inspect

from anvil.rlgym.results import skills
from anvil.rlgym.scoring import judgment
from anvil.rlgym.verification import lookup, reference_run
from anvil.rlgym.verification import service as verification


def test_the_statuses():
    assert judgment.AWAITING == ("awaiting_sme", "awaiting_pm")
    assert judgment.awaiting(
        {"status": "awaiting_pm", "awaiting_pm": ["R-CA-01 is a placeholder"]}
    ) == (
        "awaiting_pm",
        ["R-CA-01 is a placeholder"],
    )
    assert judgment.awaiting({"status": "complete"}) is None


def test_awaiting_pm_is_not_applicable_with_its_reason():
    ref = {
        "status": "awaiting_pm",
        "awaiting_pm": ["R-CA-01 is a placeholder"],
        "recommendation": None,
    }
    out = judgment.evaluate("decision", {"reference": ref, "final": {}, "transcript": []})
    assert out["verdict"] == "not_applicable"
    assert out["expected"] == {"awaiting_pm": ["R-CA-01 is a placeholder"]}


def test_runs_and_v04_skip_both():
    assert "judgment.awaiting(" in inspect.getsource(reference_run.run)
    assert "judgment.awaiting(" in inspect.getsource(lookup.run)
    assert 'cs.get("awaiting")' in inspect.getsource(verification.reference_rows)


def test_the_report_counts_both():
    counts = skills.awaiting_counts(
        [
            {"status": "awaiting_sme"},
            {"status": "awaiting_pm"},
            {"status": "awaiting_pm"},
            {"status": "complete"},
            {},
        ]
    )
    assert counts == {"awaiting_sme": 1, "awaiting_pm": 2}
    assert '"not_graded"' in inspect.getsource(skills.run_profile)
