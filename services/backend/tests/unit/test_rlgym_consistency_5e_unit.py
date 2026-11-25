"""BANK-OPERATING-RULES-DRAFT §5e (expert, confirmed 25 Nov 2026): request information takes precedence when required
information is missing (5e.2); specialist review is the recommendation only when the file can't support a clear one
(5e.3); a possible match plus missing information → request_information, and the match is still referred (5e.4).

The consistency grader's 5e rule is opt-in per evaluator configuration (config `"rule": "5e"`), so version 1's
verdicts keep their meaning and the fix is a new evaluator version qualified on its own known cases."""

from anvil.rlgym.catalog import judgment_configs
from anvil.rlgym.scoring import judgment

V1 = {"grader": "kyc-judgment.g2.consistency"}
V2 = {**V1, "rule": "5e"}


def final(rec, *, requests=(), referral=None, outcome="request_information", level=None):
    return {
        "recommendation": rec,
        "assessments": [
            {
                "party_id": "p1",
                "outcome": outcome,
                "requests": list(requests),
                **({"referral": referral} if referral else {}),
            }
        ],
        "risk_rating": {"required": level is not None, "level": level, "factors": []},
    }


REF = {"status": "complete", "gradable": True, "conditions_approved": True}


def verdict(check, f):
    return judgment.evaluate(check, {"final": f, "reference": REF})["verdict"]


def test_a_referral_with_an_outstanding_request_is_request_information():
    f = final("request_information", requests=["id_document"], referral="sanctions")
    assert verdict("consistency_5e", f) == "pass"
    assert verdict("consistency", f) == "fail"  # v1 unchanged


def test_high_risk_with_an_outstanding_request_is_request_information():
    f = final("request_information", requests=["tin"], level="high")
    assert verdict("consistency_5e", f) == "pass"


def test_without_a_request_a_referral_or_high_risk_is_specialist_review():
    f = final("request_information", referral="sanctions", outcome="clear")
    assert verdict("consistency_5e", f) == "fail"
    f = final("specialist_review", referral="sanctions", outcome="clear")
    assert verdict("consistency_5e", f) == "pass"
    f = final("specialist_review", outcome="clear", level="high")
    assert verdict("consistency_5e", f) == "pass"


def test_plain_cases_are_unchanged():
    assert verdict("consistency_5e", final("ready_for_approval", outcome="clear")) == "pass"
    assert verdict("consistency_5e", final("request_information", outcome="clear")) == "fail"


def test_the_rule_is_chosen_by_the_configuration():
    assert judgment_configs.checks_for("consistency", V1) == ["consistency"]
    assert judgment_configs.checks_for("consistency", V2) == ["consistency_5e"]
    assert (
        judgment_configs.checks_for("rules_applied", V2)
        == judgment_configs.GRADERS["rules_applied"]
    )


def test_known_cases_and_scoring_follow_the_configuration():
    case = {
        "evidence": {
            "final_output": final(
                "request_information", requests=["id_document"], referral="sanctions"
            )
        },
        "reference": REF,
    }
    assert judgment_configs.known_case_lines("consistency", case, config=V2) == {
        "consistency.consistency_5e": judgment.evaluate(
            "consistency_5e",
            {**judgment_configs.inputs_from(case["evidence"], REF), "placeholder_ok": True},
        )
    }
    assert (
        judgment_configs.known_case_lines("consistency", case, config=V2)[
            "consistency.consistency_5e"
        ]["verdict"]
        == "pass"
    )
    import inspect

    from anvil.rlgym.catalog import evaluators
    from anvil.rlgym.scoring import service

    assert "checks_for(" in inspect.getsource(service.judgment_results)
    assert 'config=row["config"]' in inspect.getsource(evaluators.run_known_case_tests)


def test_the_v2_known_cases_qualify():
    cases = judgment_configs.CONSISTENCY_5E_KNOWN_CASES
    for name, case in cases.items():
        lines = judgment_configs.known_case_lines("consistency", case, config=V2)
        got = judgment.combine(lines)["verdict"]
        assert got == case["expect"], (name, got)


def test_a_5e_fix_version_carries_the_rules_known_cases():
    """The owner's fix (Admin → evaluator → Fix version, config JSON + reason) brings §5e's known cases, so the new
    version qualifies on them; the base version's cases stay."""
    from anvil.rlgym.catalog import evaluators

    base = {"allowed": {"evidence": {}, "reference": {}}}
    out = evaluators.fix_known_cases(V2, base, {})
    assert set(out) == {"allowed", "request_with_referral", "referral_without_request"}
    assert evaluators.fix_known_cases(V1, base, {}) == base
    # Cases the owner sends win over the rule's defaults.
    mine = {"request_with_referral": {"expect": "pass", "evidence": {}, "reference": {}}}
    assert (
        evaluators.fix_known_cases(V2, base, mine)["request_with_referral"]
        is mine["request_with_referral"]
    )
