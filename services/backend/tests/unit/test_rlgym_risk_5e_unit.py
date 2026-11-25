"""BANK-OPERATING-RULES-DRAFT §5e for risk_rating (decision_next_action fix version 3, config "rule": "5e"):
missing information takes precedence. With a request outstanding, a high-risk case recommends request_information
(the EDD referral is still made); with nothing outstanding it is specialist_review with the EDD referral. A medium
risk with a request outstanding is request_information too. The level is graded as before. Version 2 is unchanged."""

from anvil.rlgym.catalog import evaluators, judgment_configs
from anvil.rlgym.scoring import judgment

V2 = {"grader": "kyc-judgment.g2.decision_next_action"}
V3 = {**V2, "rule": "5e"}
RR = {"required": True, "level": "high", "factors": ["custodian_not_parent_or_guardian"]}


def final(rec, parties, level="high"):
    return {
        "recommendation": rec,
        "officer_verification": False,
        "risk_rating": {**RR, "level": level},
        "assessments": parties,
    }


EDD_P1 = {"party_id": "p1", "outcome": "specialist_review", "requests": [], "referral": "edd"}
ASK_P2 = {"party_id": "p2", "outcome": "request_information", "requests": ["relationship_proof"]}
REF = {"status": "complete", "gradable": True, "risk_rating": RR}


def v(check, f, level="high"):
    return judgment.evaluate(
        check, {"final": f, "reference": {**REF, "risk_rating": {**RR, "level": level}}}
    )["verdict"]


def test_high_risk_with_a_request_outstanding_is_request_information():
    f = final("request_information", [EDD_P1, ASK_P2])  # kj-05588b6043's reference
    assert v("risk_rating_5e", f) == "pass"
    assert v("risk_rating", f) == "fail"  # version 2 unchanged


def test_the_edd_referral_is_still_required():
    f = final("request_information", [{**EDD_P1, "referral": None, "outcome": "clear"}, ASK_P2])
    assert v("risk_rating_5e", f) == "fail"


def test_without_a_request_high_risk_is_specialist_review_with_edd():
    assert v("risk_rating_5e", final("specialist_review", [EDD_P1])) == "pass"
    assert v("risk_rating_5e", final("request_information", [EDD_P1])) == "fail"
    assert v("risk_rating_5e", final("ready_for_approval", [EDD_P1])) == "fail"


def test_medium_risk_with_a_request_outstanding_is_request_information():
    clear = {"party_id": "p1", "outcome": "clear", "requests": []}
    assert (
        v("risk_rating_5e", final("request_information", [clear, ASK_P2], "medium"), "medium")
        == "pass"
    )
    f = {**final("ready_for_approval", [clear], "medium"), "officer_verification": True}
    assert v("risk_rating_5e", f, "medium") == "pass"


def test_the_level_is_still_graded():
    assert (
        v("risk_rating_5e", final("request_information", [EDD_P1, ASK_P2], "low"), "high") == "fail"
    )


def test_the_configuration_chooses_the_rule():
    assert judgment_configs.checks_for("decision_next_action", V2) == ["decision", "risk_rating"]
    assert judgment_configs.checks_for("decision_next_action", V3) == ["decision", "risk_rating_5e"]


def test_a_5e_fix_version_carries_its_known_cases_and_they_qualify():
    out = evaluators.fix_known_cases(V3, {"allowed": {"evidence": {}, "reference": {}}}, {})
    added = set(out) - {"allowed"}
    assert added == set(judgment_configs.DECISION_5E_KNOWN_CASES)
    for name, case in judgment_configs.DECISION_5E_KNOWN_CASES.items():
        got = judgment.combine(
            judgment_configs.known_case_lines("decision_next_action", case, config=V3)
        )
        assert got["verdict"] == case["expect"], (name, got)
