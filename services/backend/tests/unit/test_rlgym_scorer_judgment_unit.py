"""Run-3 page: every kyc-judgment-rubric-v1 configuration (config.grader kyc-judgment.g2.<criterion>) showed
"Unknown scorer". Scoring already ran them (judgment_results); the description now names them too."""

from anvil.rlgym.results import scorer

V2 = {
    "grader": "kyc-judgment.g2.consistency",
    "evidence": "final_output",
    "reference": "adi.utility.reference.v2",
    "rule": "5e",
}


def test_a_bridge_grader_is_described():
    d = scorer.describe(V2, "pramaana")
    assert not d["scored_by"].startswith(scorer.UNKNOWN)
    assert "KYC Judgment" in d["scored_by"] and "consistency" in d["scored_by"]
    assert [c["id"] for c in d["checks"]] == ["consistency.consistency_5e"]
    assert d["evidence"] == [scorer.EVIDENCE["final_output"]]
    assert d["expected_values"] == scorer.SOURCES["case_reference"]


def test_every_bridge_criterion_is_described():
    from anvil.rlgym.catalog import judgment_configs

    for crit in judgment_configs.GRADERS:
        d = scorer.describe({"grader": f"kyc-judgment.g2.{crit}"}, None)
        assert not d["scored_by"].startswith(scorer.UNKNOWN), crit
        assert d["checks"], crit


def test_an_unknown_grader_name_is_still_unknown():
    assert scorer.describe({"grader": "kyc-judgment.g2.nope"}, None)["scored_by"] == scorer.UNKNOWN
