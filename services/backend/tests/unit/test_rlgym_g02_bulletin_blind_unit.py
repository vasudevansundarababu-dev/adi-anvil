"""G-02 "bulletin-blind" (Studio generator 2.1.0): on rule-change cases the honest baseline is an agent that applies
the starting rules correctly and never reads the bulletin: the reference agent driven by the case's
reference_if_not_fired, with notices.read taken away, scored against the true (bulletin-fired) reference. The cases
need the bulletin only if it gets few of them right: the gate passes at or below 40% (configurable). Shadow mode."""

import inspect

import pytest

from anvil.rlgym.common import GymError
from anvil.rlgym.verification import bulletin_blind as bb
from anvil.rlgym.verification import lookup
from anvil.rlgym.verification import service as verification

FIRED = {
    "recommendation": "request_information",
    "parties": [
        {"party_id": "p1", "outcome": "request_information", "requests": ["tin"], "referral": None}
    ],
}
NOT_FIRED = {
    "recommendation": "ready_for_approval",
    "parties": [{"party_id": "p1", "outcome": "clear", "requests": [], "referral": None}],
}
CHANGE = {**FIRED, "reference_if_not_fired": NOT_FIRED, "scenario": [{"event_id": "e"}]}


def test_only_rule_change_cases_count():
    assert bb.is_rule_change(CHANGE) is True
    assert bb.is_rule_change(FIRED) is False


def test_the_blind_agent_never_has_notices_and_decides_by_the_starting_rules():
    actor = {
        "tools": ["notices.read", "policy.read"],
        "sections": {"S3": {"tools": ["policy.read", "notices.read", "recommend"]}},
    }
    blind = bb.blind_actor(actor)
    assert (
        "notices.read" not in blind["sections"]["S3"]["tools"]
        and "notices.read" not in blind["tools"]
    )
    assert "notices.read" in actor["sections"]["S3"]["tools"]  # the task itself is untouched
    assert bb.blind_reference(CHANGE)["recommendation"] == "ready_for_approval"


def test_summary_and_gate():
    rows = [
        {"decision_right": False, "points": "10/30", "full_marks": False},
        {"decision_right": False, "points": "12/30", "full_marks": False},
        {"decision_right": True, "points": "30/30", "full_marks": True},
        {"decision_right": False, "points": "5/30", "full_marks": False},
    ]
    s = bb.summarize(rows, 40)
    assert s["cases"] == 4 and s["decisions_right"] == 1 and s["right_percent"] == 25.0
    assert s["gate"] == {"threshold_percent": 40, "passed": True}
    assert bb.summarize(rows, 20)["gate"]["passed"] is False
    assert bb.DEFAULT_THRESHOLD == 40
    with pytest.raises(GymError):
        bb.threshold({"threshold_percent": 140})


def test_the_verification_row():
    none = verification.blind_row(None)
    assert none["id"] == "G-02" and none["outcome"] == "INSUFFICIENT_EVIDENCE"
    run = {
        "id": "bb-1",
        "summary": bb.summarize(
            [{"decision_right": False, "points": "0/30", "full_marks": False}], 40
        ),
    }
    assert verification.blind_row(run)["outcome"] == "PASS"
    run = {
        "id": "bb-2",
        "summary": bb.summarize(
            [{"decision_right": True, "points": "30/30", "full_marks": True}], 40
        ),
    }
    out = verification.blind_row(run)
    assert out["outcome"] == "FAIL" and "100%" in out["detail"]
    assert "blind_row(" in inspect.getsource(verification.build)


def test_g01_and_g02_runs_are_kept_apart():
    assert "bulletin_blind" in inspect.getsource(lookup.latest)
    assert '"kind": "bulletin_blind"' in inspect.getsource(bb.run)
    src = inspect.getsource(bb.run)
    assert (
        "blind_actor(" in src
        and "reference_run._score(c, ws, project, evaluators, t, ep, truth)" in src
    )
    from anvil.rlgym.suites import routes

    assert "bulletin-blind-run" in inspect.getsource(routes)
