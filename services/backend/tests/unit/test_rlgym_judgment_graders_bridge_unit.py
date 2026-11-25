"""KYC Judgment v1 activation bridge (Studio 6779e3f): each of the 10 rubric criteria is an evaluator whose config
names grader `kyc-judgment.g2.<criterion>`. RL Gym runs its own checks for each grader id, computed outside the sandbox
and combined by the runner; known-case tests compute the same lines from each known case."""

import inspect

from anvil.rlgym.catalog import evaluators, judgment_configs
from anvil.rlgym.scoring import judgment
from anvil.rlgym.scoring import sandbox_runner as runner

CRITERIA = [
    "tool_calls",
    "procedure_output",
    "rules_applied",
    "evidence_judgment",
    "decision_next_action",
    "rationale",
    "process_adherence",
    "evidence_faithfulness",
    "missing_facts",
    "consistency",
]
REF = {
    "schema_version": "adi.utility.reference.v2",
    "status": "complete",
    "awaiting_sme": [],
    "recommendation": "request_information",
    "officer_verification": False,
    "risk_rating": {"required": False, "level": None, "factors": []},
    "parties": [
        {"party_id": "p1", "outcome": "clear", "requests": [], "referral": None},
        {"party_id": "p2", "outcome": "request_information", "requests": ["tin"], "referral": None},
    ],
    "rules_applied": [
        {"rule_id": "R-1", "version": 2, "party_ids": ["p2"], "governs": None, "overlaps_with": []}
    ],
    "precedence": [],
}
GOOD = {
    "recommendation": "request_information",
    "rules_applied": [{"rule_id": "R-1", "version": 2}],
    "assessments": [
        {"party_id": "p1", "outcome": "clear", "issues": []},
        {
            "party_id": "p2",
            "outcome": "request_information",
            "requests": ["tin"],
            "issues": [{"issue": "The minor has no TIN on record", "evidence_ids": ["d2"]}],
        },
    ],
    "notices_considered": [],
    "officer_verification": False,
    "risk_rating": {"required": False, "level": None, "factors": []},
    "audit_trail": [
        {
            "sop_step": 1,
            "status": "done",
            "data_seen": ["d2"],
            "facts_learnt": [],
            "rules_applied": [],
        }
    ],
    "rationale": "request information: R-1 v2 requires the minor's TIN.",
}
EVENTS = [
    {"tool": "identity.check", "args": {"party_id": "p1"}, "ok": True},
    {"tool": "identity.check", "args": {"party_id": "p2"}, "ok": True},
    {"tool": "screening.check", "args": {"party_id": "p1"}, "ok": True},
    {"tool": "screening.check", "args": {"party_id": "p2"}, "ok": True},
    {"tool": "information.request", "args": {"party_id": "p2", "type": "tin"}, "ok": True},
    {"tool": "recommend", "args": {}, "ok": True},
]
TRANSCRIPT = [
    {
        "step": 1,
        "tool": "documents.list",
        "observation": {
            "ok": True,
            "sequence": 1,
            "output": {"records": [{"document_id": "d2", "party_id": "p2"}]},
        },
    }
]


def x(final=GOOD, events=EVENTS, ref=REF, **over):
    return {
        "final": final,
        "tool_events": events,
        "transcript": TRANSCRIPT,
        "reference": ref,
        "aliases": {},
        "fired": [],
        **over,
    }


def verdict(criterion, **kw):
    return judgment.grade(criterion, x(**kw))["verdict"]


def test_every_bridge_criterion_has_a_grader():
    assert sorted(judgment_configs.GRADERS) == sorted(CRITERIA)
    for c in CRITERIA:
        assert judgment_configs.grader_of({"grader": f"kyc-judgment.g2.{c}"}) == c
    assert judgment_configs.grader_of({"runner": "verifier_blocks"}) is None


def test_a_right_episode_passes_every_gradable_criterion():
    for c in CRITERIA:
        v = verdict(c)
        expected = "not_applicable" if c in ("process_adherence", "missing_facts") else "pass"
        assert v == expected, (c, judgment.grade(c, x()))


def test_rules_applied_uses_the_references_own_list():
    # One rule missing with the decision right: partial (rubric); with the decision wrong (Studio's disallowed): fail.
    assert verdict("rules_applied", final={**GOOD, "rules_applied": []}) == "partial"
    wrong = {**GOOD, "rules_applied": [], "recommendation": "ready_for_approval"}
    assert verdict("rules_applied", final=wrong) == "fail"


def test_tool_calls_missing_and_wrong_calls():
    assert (
        verdict("tool_calls", events=[e for e in EVENTS if e["args"].get("party_id") != "p1"])
        == "fail"
    )
    extra = EVENTS[:-1] + [
        {"tool": "information.request", "args": {"party_id": "p1", "type": "tin"}, "ok": True},
        EVENTS[-1],
    ]
    assert verdict("tool_calls", events=extra) == "partial"
    assert verdict("tool_calls", events=None) == "blocked"
    late = EVENTS[:2] + [EVENTS[-1], *EVENTS[2:-1]]  # screening after the recommendation
    assert verdict("tool_calls", events=late) == "fail"


def test_evidence_judgment_attribution():
    wrong = {
        **GOOD,
        "assessments": [
            {
                "party_id": "p1",
                "outcome": "clear",
                "issues": [{"issue": "Missing TIN for the minor", "evidence_ids": []}],
            },
            {"party_id": "p2", "outcome": "request_information", "requests": ["tin"], "issues": []},
        ],
    }
    # One stray issue on the clear party (the request still went to the right one): partial.
    assert verdict("evidence_judgment", final=wrong) == "partial"


def test_consistency_procedure_and_rationale():
    assert verdict("consistency", final={**GOOD, "recommendation": "ready_for_approval"}) == "fail"
    assert (
        verdict("procedure_output", final={k: v for k, v in GOOD.items() if k != "audit_trail"})
        == "fail"
    )
    assert verdict("procedure_output", final={**GOOD, "rules_applied": []}) == "fail"
    assert verdict("rationale", final={**GOOD, "rationale": "Done."}) == "fail"
    assert (
        verdict(
            "rationale",
            final={**GOOD, "rationale": "request information because the TIN is missing."},
        )
        == "partial"
    )


def test_evidence_faithfulness_is_the_audit_check_and_critical():
    bad = {
        **GOOD,
        "audit_trail": [
            {"sop_step": 1, "data_seen": ["d999"], "facts_learnt": [], "rules_applied": []}
        ],
    }
    out = judgment.grade("evidence_faithfulness", x(final=bad))
    assert out["verdict"] == "fail" and out["critical"] is True


def test_missing_facts_when_the_reference_lists_them():
    ref = {**REF, "facts_missing": [{"party_id": "p2", "fact": "taxpayer_id"}]}
    final = {
        **GOOD,
        "audit_trail": [
            {**GOOD["audit_trail"][0], "facts_missing": [{"party": "p2", "fact": "taxpayer_id"}]}
        ],
    }
    assert verdict("missing_facts", ref=ref, final=final) == "pass"
    assert verdict("missing_facts", ref=ref) == "fail"


def test_the_runner_combines_a_graders_lines():
    lines = {
        "rules_applied.rules_applied": {"verdict": "pass"},
        "rules_applied.rule_in_force": {"verdict": "not_applicable"},
    }
    cfg = {"grader": "kyc-judgment.g2.rules_applied"}
    out = runner.evaluate({"config": cfg, "judgment_results": lines, "criterion": "rules_applied"})
    assert out["verdict"] == "pass"
    assert runner.evaluate({"config": cfg, "criterion": "rules_applied"})["verdict"] == "blocked"
    crit = {"evidence_faithfulness.audit_faithfulness": {"verdict": "fail", "critical": True}}
    out = runner.evaluate(
        {
            "config": {"grader": "kyc-judgment.g2.evidence_faithfulness"},
            "judgment_results": crit,
            "criterion": "evidence_faithfulness",
        }
    )
    assert out["verdict"] == "fail" and out["critical"] is True


def test_known_case_tests_and_scoring_are_wired():
    assert "judgment_configs.known_case_lines(" in inspect.getsource(
        evaluators.run_known_case_tests
    )
    assert '"not_applicable"' in inspect.getsource(evaluators._validate_known_cases)


# --- process adherence (Studio 6ee777d: the SOP in activation, mandatory steps per case) ------------------------------


def trail(*steps):
    return [
        {"sop_step": s, "status": st, "data_seen": [], "facts_learnt": [], "rules_applied": []}
        for s, st in steps
    ]


def test_process_adherence_every_mandatory_step_done_in_order():
    mand = ["1", "2", "3", "8"]
    good = {
        **GOOD,
        "audit_trail": trail(
            ("1", "done"), ("2", "done"), ("3", "done"), ("5", "skipped"), ("8", "done")
        ),
    }
    assert (
        judgment.grade("process_adherence", x(final=good, mandatory_steps=mand))["verdict"]
        == "pass"
    )
    missing = {
        **GOOD,
        "audit_trail": trail(("1", "done"), ("2", "done"), ("3", "done"), ("8", "skipped")),
    }
    out = judgment.grade("process_adherence", x(final=missing, mandatory_steps=mand))
    assert out["verdict"] == "fail"
    disorder = {
        **GOOD,
        "audit_trail": trail(("2", "done"), ("1", "done"), ("3", "done"), ("8", "done")),
    }
    assert (
        judgment.grade("process_adherence", x(final=disorder, mandatory_steps=mand))["verdict"]
        == "fail"
    )
    # The reference's own list wins; with neither it can't be graded.
    assert (
        judgment.grade("process_adherence", x(final=good, ref={**REF, "mandatory_steps": mand}))[
            "verdict"
        ]
        == "pass"
    )
    assert judgment.grade("process_adherence", x(final=good))["verdict"] == "not_applicable"


def test_known_cases_may_carry_shared_truth_beside_the_cases():
    case = {
        "evidence": {"final_output": {**GOOD, "audit_trail": trail(("1", "done"))}},
        "reference": REF,
    }
    lines = judgment_configs.known_case_lines("process_adherence", case, {"mandatory_steps": ["1"]})
    assert lines["process_adherence.process_adherence"]["verdict"] == "pass"
    evaluators._validate_known_cases(
        {
            "allowed": {**case, "expect": "pass"},
            "disallowed": {**case, "expect": "fail"},
            "missing_evidence": {"evidence": {}, "reference": REF},
            "mandatory_steps": ["1"],
        }
    )


# --- Studio's runtime evidence shape (6ee777d known cases) reads the same as RL Gym's sealed bundle -------------------

STUDIO_EVENTS = [
    {
        "tool": "identity.check",
        "ok": False,
        "arguments": {"party_id": "p1", "method": "documentary"},
    },  # pending
    {"tool": "identity.check", "ok": True, "arguments": {"party_id": "p2"}},
    {"tool": "screening.check", "ok": False, "arguments": {"party_id": "p1"}},
    {"tool": "screening.check", "ok": True, "arguments": {"party_id": "p2"}},
    {"tool": "information.request", "ok": True, "arguments": {"party_id": "p2", "type": "tin"}},
    {"tool": "recommend", "ok": True, "arguments": {}},
]
STUDIO_TRANSCRIPT = [
    {
        "sequence": 1,
        "operation_id": "documents.list",
        "arguments": {},
        "state": "completed",
        "record_ids": ["d2", "p2"],
    },
    {
        "sequence": 2,
        "operation_id": "policy.read",
        "arguments": {},
        "state": "completed",
        "record_ids": ["R-1"],
    },
    {
        "sequence": 3,
        "operation_id": "document.read",
        "arguments": {},
        "state": "rejected",
        "record_ids": ["never"],
    },
    {
        "sequence": 4,
        "operation_id": "recommend",
        "arguments": {},
        "state": "completed",
        "record_ids": [],
    },
]


def test_studio_tool_events_count_calls_that_reached_the_operation():
    assert verdict("tool_calls", events=STUDIO_EVENTS) == "pass"
    blocked = [
        {**e, "blocked": True} if e["arguments"].get("party_id") == "p1" else e
        for e in STUDIO_EVENTS
    ]
    assert verdict("tool_calls", events=blocked) == "fail"


def test_documentary_is_the_default_method():
    ref = {**REF, "identity_methods": {"p1": "documentary", "p2": "non_documentary"}}
    assert (
        verdict("tool_calls", events=STUDIO_EVENTS, ref=ref) == "fail"
    )  # p2's required non_documentary check is missing


def test_studio_transcripts_for_faithfulness_and_the_clock():
    good = {
        **GOOD,
        "audit_trail": [
            {
                "sop_step": 1,
                "data_seen": ["d2", "R-1", {"rule_id": "R-1", "version": 2}],
                "facts_learnt": [],
                "rules_applied": [],
            }
        ],
    }
    out = judgment.grade("evidence_faithfulness", x(final=good, transcript=STUDIO_TRANSCRIPT))
    assert out["verdict"] == "pass", out
    bad = {
        **GOOD,
        "audit_trail": [
            {"sop_step": 1, "data_seen": ["never"], "facts_learnt": [], "rules_applied": []}
        ],
    }
    out = judgment.grade("evidence_faithfulness", x(final=bad, transcript=STUDIO_TRANSCRIPT))
    assert out["verdict"] == "fail" and out["critical"] is True
    assert judgment.recommend_sequence(STUDIO_TRANSCRIPT) == 4


def test_evidence_judgment_reads_attribution_from_outcomes_and_requests_too():
    by_outcome = {
        **GOOD,
        "assessments": [
            {"party_id": "p1", "outcome": "clear", "issues": []},
            {"party_id": "p2", "outcome": "request_information", "requests": ["tin"], "issues": []},
        ],
    }
    assert verdict("evidence_judgment", final=by_outcome) == "pass"
    swapped = {
        **GOOD,
        "assessments": [
            {"party_id": "p1", "outcome": "request_information", "requests": ["tin"], "issues": []},
            {"party_id": "p2", "outcome": "clear", "issues": []},
        ],
    }
    assert verdict("evidence_judgment", final=swapped) == "fail"
