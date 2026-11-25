"""Studio 21c0af7 (B1-B3) wired into RL Gym's grading.
- B1: the library and the cases' scenarios come from the scorer endpoints, and each hash is checked with common.sha
  (sorted-key compact JSON, UTF-8), before both are frozen in the manifest.
- B2: reference.v2. `status: awaiting_sme` is not graded; `governs: null` is not graded; a rule-change case is always
  graded against its fired (post-bulletin) truth (owner, 25 Nov 2026: the trigger is the first documents.list, so an
  agent that never reaches it has failed the work); `reference_if_not_fired` is diagnostics only (G-02).
- The clock is the observation's `sequence`: calls rejected before running (no sequence) never count.
- B3: the output's risk_rating is {required, level, factors}."""

import pytest

from anvil.rlgym.common import GymError, sha
from anvil.rlgym.runs import events as scenario_log
from anvil.rlgym.runs import library
from anvil.rlgym.runs import service as runs
from anvil.rlgym.scoring import judgment

V2 = {
    "schema_version": "adi.utility.registry-case.v2",
    "case_id": "kj-1",
    "facts": {},
    "parties": [],
}
LIB = {
    "library_id": "l",
    "export": {"library_revision": 1},
    "rules": [
        {
            "rule_id": "R",
            "subject": "case",
            "versions": [
                {
                    "version": 1,
                    "text": "t",
                    "text_sha256": library.text_sha("t"),
                    "effective": {"mode": "from_date", "from": "2026-01-01"},
                    "effect": "obligation",
                    "condition": None,
                }
            ],
        }
    ],
}
SCEN = {"scenario_id": "kj-1.scenario", "case_id": "kj-1", "events": []}


def test_b1_hashes_are_checked_and_scenarios_frozen():
    out = runs.judgment_part(
        [V2],
        lambda: {"version_id": "v", "library": LIB, "sha256": sha(LIB)},
        lambda ids: {"scenarios": {"kj-1": {"scenario": SCEN, "sha256": sha(SCEN)}}},
    )
    assert out["library_sha256"] == sha(LIB) and out["scenarios"] == {"kj-1": SCEN}
    with pytest.raises(GymError) as e:
        runs.judgment_part(
            [V2], lambda: {"library": LIB, "sha256": "0" * 64}, lambda ids: {"scenarios": {}}
        )
    assert e.value.code == "HASH_MISMATCH"
    with pytest.raises(GymError):
        runs.judgment_part(
            [V2],
            lambda: {"library": LIB, "sha256": sha(LIB)},
            lambda ids: {"scenarios": {"kj-1": {"scenario": SCEN, "sha256": "0" * 64}}},
        )


REF = {
    "schema_version": "adi.utility.reference.v2",
    "status": "complete",
    "awaiting_sme": [],
    "recommendation": "request_information",
    "officer_verification": False,
    "risk_rating": {"required": False, "level": None, "factors": []},
    "parties": [
        {"party_id": "p1", "outcome": "request_information", "requests": ["tin"], "referral": None}
    ],
    "rules_applied": [
        {"rule_id": "R", "version": 1, "party_ids": [], "governs": None, "overlaps_with": []}
    ],
    "precedence": [],
}
FINAL = {
    "recommendation": "request_information",
    "officer_verification": False,
    "risk_rating": {"required": False, "level": None, "factors": []},
    "assessments": [
        {"party_id": "p1", "outcome": "request_information", "issues": [], "requests": ["tin"]}
    ],
    "rules_applied": [{"rule_id": "R", "version": 1, "governs": True}],
    "notices_considered": [],
}
TRANSCRIPT = [
    {
        "step": 1,
        "tool": "x",
        "observation": {"ok": False, "error": "SCHEMA_INVALID"},
    },  # rejected: no sequence
    {"step": 2, "tool": "recommend", "observation": {"ok": True, "sequence": 1}},
]


def x(**over):
    base = {
        "library": LIB,
        "case": {"facts": {}, "parties": []},
        "fired": [],
        "transcript": TRANSCRIPT,
        "aliases": {},
        "final": FINAL,
        "reference": REF,
    }
    base.update(over)
    return base


def test_awaiting_sme_is_not_graded():
    ref = {
        **REF,
        "status": "awaiting_sme",
        "awaiting_sme": ["precedence: the SME decides"],
        "recommendation": None,
    }
    out = judgment.evaluate("decision", x(reference=ref))
    assert out["verdict"] == "not_applicable" and "precedence" in str(out["expected"])


def test_null_governs_is_not_graded():
    out = judgment.evaluate("rules_applied", x())
    assert out["verdict"] == "pass"


def test_a_rule_change_case_is_always_graded_against_the_fired_truth():
    not_fired = {
        **REF,
        "recommendation": "ready_for_approval",
        "parties": [{"party_id": "p1", "outcome": "clear", "requests": [], "referral": None}],
    }
    ref = {**REF, "reference_if_not_fired": not_fired, "scenario": [{"event_id": "e"}]}
    clean = {
        **FINAL,
        "recommendation": "ready_for_approval",
        "assessments": [{"party_id": "p1", "outcome": "clear", "issues": []}],
    }
    # The starting rules' answer is wrong even when the bulletin never fired.
    assert judgment.evaluate("decision", x(reference=ref, final=clean))["verdict"] == "fail"
    assert judgment.evaluate("decision", x(reference=ref, final=FINAL))["verdict"] == "pass"
    fired = [{"rule_id": "R", "to_version": 1, "published_at_sequence": 0, "notice_id": "n"}]
    assert (
        judgment.evaluate("decision", x(reference=ref, final=FINAL, fired=fired))["verdict"]
        == "pass"
    )


def test_the_clock_counts_only_calls_with_a_sequence():
    assert judgment.recommend_sequence(TRANSCRIPT) == 1
    late = [{"step": 9, "tool": "y", "observation": {"ok": False}}]
    assert judgment.recommend_sequence(late) == 1  # nothing counted: one past zero


def test_g6_keeps_notices_published():
    snaps = {"end": {"scenario_events_fired": [], "notices_published": [{"notice_id": "n1"}]}}
    out = scenario_log.scenario_events(snaps, [])
    assert out["notices_published"] == [{"notice_id": "n1"}]


def test_the_library_must_be_the_one_the_version_pins():
    with pytest.raises(GymError) as e:
        runs.judgment_part(
            [V2],
            lambda: {"library": LIB, "sha256": sha(LIB)},
            lambda ids: {"scenarios": {}},
            pinned={"policy_library_sha256": "1" * 64},
        )
    assert "pins" in e.value.message
