"""E-007 / Authoring 7c12b835: an SME decision stores its verdict, score pass and evidence digest (additive)."""

import inspect

import pytest

from anvil.rlgym.results import sme


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("Accept", "accept"),
        ("Dispute grader", "dispute_grader"),
        ("dispute_task", "dispute_task"),
        ("DISPUTE  environment", "dispute_environment"),
        ("Dispute-rubric", "dispute_rubric"),
        (None, None),
    ],
)
def test_verdicts_normalise(raw, want):
    assert sme.review_verdict(raw) == want


@pytest.mark.parametrize("raw", ["Can't assess", "maybe", 3])
def test_other_verdicts_are_refused(raw):
    assert sme.review_verdict(raw) is sme.MISSING  # "Can't assess" stays in Authoring


def test_the_fields_are_stored_with_the_decision():
    src = inspect.getsource(sme.receive_decisions)
    assert "review_verdict=%s, score_pass=%s, evidence_sha256=%s" in src
