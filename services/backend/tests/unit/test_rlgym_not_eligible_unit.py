"""Spec §13 (owner, 25 Nov 2026): a 4th decision, not_eligible. It is right when the reference says not_eligible and
wrong otherwise, in decision_next_action (decision, risk_rating) and consistency (v1 and §5e); procedure_output accepts
it; skill profiles and comparisons work from criterion verdicts, so they take any decision value."""

from anvil.rlgym.results import skills
from anvil.rlgym.scoring import judgment

REF_BASE = {"status": "complete", "gradable": True, "conditions_approved": True}


def final(rec, outcome="not_eligible", level=None, referral=None):
    return {
        "recommendation": rec,
        "officer_verification": False,
        "assessments": [
            {
                "party_id": "p1",
                "outcome": outcome,
                "requests": [],
                **({"referral": referral} if referral else {}),
            }
        ],
        "risk_rating": {"required": level is not None, "level": level, "factors": []},
        "rules_applied": [{"rule_id": "R-ELIG", "version": 1}],
        "notices_considered": [],
        "audit_trail": [],
        "rationale": "Recommendation: not_eligible. Rules applied: R-ELIG v1.",
    }


def ref(rec, outcome="not_eligible", level=None):
    return {
        **REF_BASE,
        "recommendation": rec,
        "officer_verification": False,
        "parties": [{"party_id": "p1", "outcome": outcome, "requests": [], "referral": None}],
        "risk_rating": {"required": level is not None, "level": level, "factors": []},
    }


def v(check, f, r):
    return judgment.evaluate(check, {"final": f, "reference": r})["verdict"]


def test_not_eligible_is_right_when_the_reference_says_so():
    f, r = final("not_eligible"), ref("not_eligible")
    for check in ("decision", "consistency", "consistency_5e", "procedure_output"):
        assert v(check, f, r) == "pass", check


def test_not_eligible_is_wrong_otherwise():
    f = final("not_eligible")
    r = ref("ready_for_approval", outcome="clear")
    for check in ("decision", "consistency", "consistency_5e"):
        assert v(check, f, r) == "fail", check


def test_missing_a_not_eligible_is_wrong():
    f = final("ready_for_approval", outcome="clear")
    r = ref("not_eligible")
    for check in ("decision", "consistency", "consistency_5e"):
        assert v(check, f, r) == "fail", check


def test_a_risk_rating_doesnt_demand_an_approval_path_for_an_ineligible_account():
    for level in ("medium", "high"):
        f, r = final("not_eligible", level=level), ref("not_eligible", level=level)
        assert v("risk_rating", f, r) == "pass", level
        # The level itself is still graded.
        assert v("risk_rating", final("not_eligible", level="low"), r) == "fail"


def test_the_three_values_keep_their_rules():
    f = final("ready_for_approval", outcome="clear")
    r = ref("ready_for_approval", outcome="clear")
    assert v("consistency", f, r) == "pass" and v("procedure_output", f, r) == "pass"
    assert v("procedure_output", final("approve"), ref("not_eligible")) == "fail"


def test_skill_profiles_take_any_decision_value():
    rows = [
        {
            "system_id": "m",
            "case_id": f"c{i}",
            "criterion_id": "decision_next_action",
            "skill": "decisioning",
            "fraction": 1.0,
        }
        for i in range(10)
    ]
    out = skills.profile(rows, {f"c{i}" for i in range(10)})["m"]["decisioning"]
    assert out == {"value": 100.0, "n": 10, "measured": True}
