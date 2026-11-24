"""D-034: "Scored by" / "How it's scored" from the grader that actually runs, frozen per run; leaderboard eligibility
(E-004 §3.4). Synthetic configurations shaped like golden-kyc v8."""

import inspect

from anvil.rlgym.catalog import fixes
from anvil.rlgym.results import report, scorer
from anvil.rlgym.runs import service as runs

BLOCKS = {
    "decision": [
        {
            "id": "decision.recommendation",
            "kind": "state",
            "op": "equals",
            "table": "recommendations",
            "column": "recommendation",
            "value": {"case_reference": "reference_answers.recommendation"},
            "name": "Recommendation recorded",
        },
        {
            "id": "decision.rationale_quality",
            "name": "Rationale explains the decision",
            "share_percent": 20,
            "plugin": {"id": "promptfoo"},
            "settings": {
                "judge": "gemini-3.8-flash",
                "rubric": "States the reason.",
                "target": "state.end.recommendations[0].rationale",
                "threshold": 0.7,
            },
        },
    ],
    "screening": [
        {
            "id": "screening.order",
            "kind": "process",
            "must_call": "screening.check",
            "before": "recommend",
            "name": "Screen before recommending",
        },
        {
            "id": "screening.finding",
            "name": "Screening hit recorded as a finding",
            "plugin": {"id": "gorules-zen"},
            "settings": {"mode": "rule_check", "rules": {"sha256": "fb6f14000f359feaf0"}},
        },
    ],
    "evidence": [
        {
            "id": "evidence.documents_read",
            "kind": "process",
            "must_call": "documents.list",
            "before": "recommend",
            "name": "Read the party documents before recommending",
        },
    ],
}
V1 = {"runner": "verifier_blocks", "runner_version": 1, "evidence": "snapshots"}


def test_each_kind_is_named_and_the_judge_is_shown_in_full():
    d = scorer.describe(
        V1, "python", BLOCKS["decision"], "case_reference", {}, {"gemini-3.8-flash": "la-1"}
    )
    assert (
        d["scored_by"]
        == "Python checks (verifier blocks, runner v1) + Promptfoo with LLM judge gemini-3.8-flash"
    )
    j = d["judges"][0]
    assert (j["model"], j["approval"], j["live"], j["threshold"], j["share_percent"]) == (
        "gemini-3.8-flash",
        "la-1",
        True,
        0.7,
        20.0,
    )
    assert j["system_prompt"].startswith("You are a strict grader") and j["prompt"].startswith(
        "Rubric: States the reason."
    )
    assert d["expected_values"] == "this case's reference answers (hidden from the agent)"
    zen = scorer.describe(
        V1, "python", BLOCKS["screening"], "case_reference", {"screening.finding": "v1.0.0"}
    )
    assert (
        zen["scored_by"].endswith("+ GoRules ZEN decision rules")
        and "rules file fb6f14000f35" in zen["checks"][1]["what"]
    )
    plain = scorer.describe(V1, "python", BLOCKS["evidence"], "case_reference")
    assert (
        plain["scored_by"] == "Python checks (verifier blocks, runner v1)"
        and plain["expected_values"] is None
    )


def test_unknown_is_said_never_left_blank():
    assert scorer.describe(None, None)["scored_by"] == scorer.UNKNOWN
    assert scorer.describe(V1, "python", [], "case_reference")["scored_by"].startswith(
        scorer.UNKNOWN
    )
    assert scorer.describe({}, "zen")["scored_by"] == "GoRules ZEN decision rules"
    rules = scorer.describe(
        {"rules": [{"kind": "tool_called", "tool": "screening.check"}]}, "python"
    )
    assert (
        rules["scored_by"] == "Python rule checks"
        and "called screening.check" in rules["checks"][0]["what"]
    )


def test_the_d041_fix_is_described_and_changes_the_grader_hash():
    fix = fixes.SUGGESTED["golden-kyc-blocks:next_action"]["config"]
    block = [
        {
            "id": "next_action.request",
            "kind": "state",
            "op": "exists_where",
            "table": "information_requests",
            "column": "type",
            "value": {"case_reference": "reference_answers.request_type"},
        }
    ]
    d = scorer.describe(fix, "python", block, "case_reference")
    assert d["scored_by"] == "Python checks (verifier blocks, runner v2) + RL Gym party check"
    assert scorer.grader_sha256(fix, block, {}) != scorer.grader_sha256(V1, block, {})


def _lines(*live):
    return [{"system_id": f"m{i}", "name": f"m{i}", "live": lv or None} for i, lv in enumerate(live)]


ENV8 = {
    "id": "golden-kyc-openenv@8",
    "state": "qualified",
    "operations": [
        {"operation_id": o}
        for o in (
            "recommend",
            "screening.check",
            "identity.check",
            "information.request",
            "finding.write",
            "finding.resolve",
        )
    ],
    "schema": {
        "collections": [
            {"name": "parties"},
            {"name": "documents"},
            {
                "name": "reference_answers",
                "fields": [{"name": "recommendation"}, {"name": "screening_issue"}],
            },
        ]
    },
}


def test_leaderboard_eligibility_names_every_reason():
    ok = runs.leaderboard_eligibility(
        {
            "evaluator_versions": [{"criterion_id": "decision"}],
            "env_row": ENV8,
            "prompts": [{"category_key": "aml_tipping_off"}],
        },
        _lines({"approval_id": "la"}),
    )
    assert ok == {"eligible": True, "reasons": []}
    bad = runs.leaderboard_eligibility(
        {
            "evaluator_versions": [],
            "env_row": {**ENV8, "state": "registered", "operations": [{"operation_id": "x"}]},
            "prompts": [{"category_key": "aml_tipping_off"}, {"category_key": "made_up"}],
        },
        _lines(None),
    )
    text = "; ".join(bad["reasons"])
    assert not bad["eligible"]
    for want in (
        "no criterion is bound",
        "not qualified",
        "aml_tipping_off needs information.request",
        "no local detector",
        "are mocks, not live: m0",
    ):
        assert want in text, want


def test_admission_freezes_graders_and_refuses_an_ineligible_tick():
    src = inspect.getsource(runs.admission_check)
    assert 'body.get("leaderboard") is True and not eligibility["eligible"]' in src
    assert '"leaderboard": eligibility' in src and "scorer.for_admission(" in src
    assert '**({"graders": r["graders"]} if r.get("graders") else {})' in inspect.getsource(
        runs._manifest
    )
    assert "scorer.for_run(" in inspect.getsource(report)
