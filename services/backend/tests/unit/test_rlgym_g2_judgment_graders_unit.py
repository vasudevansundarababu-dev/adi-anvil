"""G2 (KYC Judgment v1 §6, §15.2): the graders, as pure functions on the library, the case, the trajectory and the
final output. Wired in as a new evaluator version once Studio's reference v2, library endpoint and the C4 audit-trail
fields land (RL Gym review B1-B3); nothing here changes an existing score."""

from anvil.rlgym.runs import library
from anvil.rlgym.scoring import judgment

ACC = {"fact": "process", "op": "eq", "value": "account_opening"}


def v(n, cond, eff=None, effect="obligation"):
    t = f"rule text {n}"
    return {
        "version": n,
        "effective": eff or {"mode": "from_date", "from": "2026-01-01"},
        "effect": effect,
        "condition": cond,
        "text": t,
        "text_sha256": library.text_sha(t),
    }


LIB = {
    "derived_facts": [],
    "rules": [
        {"rule_id": "FED-ID", "subject": "party", "versions": [v(1, ACC)]},
        {
            "rule_id": "CA-ID",
            "subject": "party",
            "versions": [
                v(1, {"all": [ACC, {"fact": "governing_state", "op": "eq", "value": "CA"}]})
            ],
        },
        {
            "rule_id": "GB-03",
            "subject": "party",
            "versions": [
                v(1, {"all": [ACC, {"fact": "party_role", "op": "eq", "value": "minor"}]}),
                {
                    **v(
                        2,
                        {"all": [ACC, {"fact": "party_role", "op": "eq", "value": "minor"}]},
                        {"mode": "scenario_only"},
                    ),
                    "supersedes": 1,
                },
            ],
        },
        {
            "rule_id": "R-CTR",
            "subject": "case",
            "versions": [
                v(1, {"fact": "process", "op": "eq", "value": "currency_transaction_reporting"})
            ],
        },
    ],
}
CASE = {
    "case_id": "kj-1",
    "submitted_at": "2026-10-15",
    "facts": {"process": "account_opening", "governing_state": "CA"},
    "parties": [
        {"party_id": "p1", "facts": {"party_role": "primary"}},
        {"party_id": "p2", "facts": {"party_role": "minor"}},
    ],
}
EXPECTED = library.applicable(LIB, CASE)["applies"]
GOVERNS = [
    {"rule_id": "CA-ID", "version": 1, "governs": True},
    {"rule_id": "FED-ID", "version": 1, "governs": False},
]


def cited(*pairs, governs=("CA-ID",)):
    return [
        {
            "rule_id": r,
            "version": n,
            **({"governs": r in governs} if r in ("CA-ID", "FED-ID") else {}),
        }
        for r, n in pairs
    ]


ALL = (("FED-ID", 1), ("CA-ID", 1), ("GB-03", 1))


# --- rules applied ---------------------------------------------------------------------------------------------------------


def test_exact_set_with_the_stricter_rule_governing_passes():
    out = judgment.rules_applied(EXPECTED, cited(*ALL), GOVERNS, decision_right=True)
    assert out["verdict"] == "pass" and out["missing"] == [] and out["extra"] == []


def test_one_off_with_the_decision_right_is_partial_otherwise_fail():
    one_missing = cited(("FED-ID", 1), ("CA-ID", 1))
    assert (
        judgment.rules_applied(EXPECTED, one_missing, GOVERNS, decision_right=True)["verdict"]
        == "partial"
    )
    assert (
        judgment.rules_applied(EXPECTED, one_missing, GOVERNS, decision_right=False)["verdict"]
        == "fail"
    )
    distractor = cited(*ALL, ("R-CTR", 1))
    out = judgment.rules_applied(EXPECTED, distractor, GOVERNS, decision_right=True)
    assert out["verdict"] == "partial" and out["extra"] == [{"rule_id": "R-CTR", "version": 1}]
    two_off = cited(("FED-ID", 1), ("R-CTR", 1), ("CA-ID", 1))
    assert (
        judgment.rules_applied(EXPECTED, two_off, GOVERNS, decision_right=True)["verdict"] == "fail"
    )


def test_marking_the_wrong_rule_as_governing_counts_as_one_off():
    out = judgment.rules_applied(
        EXPECTED, cited(*ALL, governs=("FED-ID",)), GOVERNS, decision_right=True
    )
    assert out["verdict"] == "fail"  # two marks wrong (CA-ID not marked, FED-ID marked)
    assert sorted(g["rule_id"] for g in out["governs_wrong"]) == ["CA-ID", "FED-ID"]
    unmarked = [{k: x[k] for k in ("rule_id", "version")} for x in cited(*ALL)]
    out = judgment.rules_applied(EXPECTED, unmarked, GOVERNS, decision_right=True)
    assert out["verdict"] == "partial" and [g["rule_id"] for g in out["governs_wrong"]] == ["CA-ID"]


def test_without_a_governs_reference_the_mark_is_not_graded_and_says_so():
    out = judgment.rules_applied(EXPECTED, cited(*ALL), None, decision_right=True)
    assert (
        out["verdict"] == "pass"
        and out["governs"] == "not graded: no reference for which rule governs"
    )


# --- the rule in force at the recommend call ----------------------------------------------------------------------------------


TRANSCRIPT = [
    {"sequence": 1, "tool": "application.read", "observation": {"ok": True}},
    {"sequence": 2, "tool": "screening.check", "observation": {"ok": True}},
    {"sequence": 3, "tool": "notices.read", "observation": {"ok": True}},
    {"sequence": 4, "tool": "recommend", "observation": {"ok": True}},
]
FIRED = [
    {
        "rule_id": "GB-03",
        "from_version": 1,
        "to_version": 2,
        "trigger_sequence": 2,
        "published_at_sequence": 2,
    }
]


def test_after_a_bulletin_the_new_version_is_expected_and_the_old_one_is_stale():
    seq = judgment.recommend_sequence(TRANSCRIPT)
    assert seq == 4
    exp = judgment.expected_rules(LIB, CASE, FIRED, TRANSCRIPT)
    assert ("GB-03", 2) in {(e["rule_id"], e["version"]) for e in exp}
    stale = judgment.rules_applied(exp, cited(*ALL), GOVERNS, decision_right=True)
    assert stale["verdict"] == "fail"
    assert {"rule_id": "GB-03", "version": 1} in stale["stale"]
    ok = judgment.rules_applied(
        exp, cited(("FED-ID", 1), ("CA-ID", 1), ("GB-03", 2)), GOVERNS, decision_right=True
    )
    assert ok["verdict"] == "pass"


def test_a_publication_after_the_recommend_call_does_not_count():
    late = [{**FIRED[0], "published_at_sequence": 9}]
    exp = judgment.expected_rules(LIB, CASE, late, TRANSCRIPT)
    assert ("GB-03", 1) in {(e["rule_id"], e["version"]) for e in exp}


# --- the audit trail (§15.2; SOP proposal §3) ---------------------------------------------------------------------------------

OBS = [
    {
        "sequence": 1,
        "tool": "application.read",
        "observation": {
            "ok": True,
            "output": {"records": [{"application_id": "kj-1", "governing_state": "CA"}]},
        },
    },
    {
        "sequence": 2,
        "tool": "documents.list",
        "observation": {
            "ok": True,
            "output": {
                "records": [
                    {
                        "document_id": "kj-1-p1-pass",
                        "party_id": "kj-1-p1",
                        "kind": "passport",
                        "content": {"nationality": "MX"},
                    }
                ]
            },
        },
    },
    {
        "sequence": 3,
        "tool": "policy.read",
        "observation": {
            "ok": True,
            "output": {
                "records": [
                    {"rule_id": "FED-ID", "version": 1, "text": "rule text 1"},
                    {"rule_id": "CA-ID", "version": 1, "text": "rule text 1"},
                ]
            },
        },
    },
    {
        "sequence": 4,
        "tool": "identity.check",
        "observation": {"ok": False, "output": {"records": [{"document_id": "never-returned"}]}},
    },
]
ALIASES = {"kj-1": "APP-1", "kj-1-p1": "PTY-1", "kj-1-p1-pass": "DOC-1"}


def entry(**over):
    e = {
        "sop_step": 2,
        "status": "done",
        "data_seen": ["APP-1", "DOC-1", {"rule_id": "FED-ID", "version": 1}],
        "facts_learnt": [
            {"fact": "citizenship", "value": "MX", "party": "PTY-1", "evidence": "DOC-1"}
        ],
        "rules_applied": [{"rule_id": "FED-ID", "version": 1}],
        "principle": "x",
        "conclusion": "y",
    }
    e.update(over)
    return e


def test_a_faithful_trail_passes():
    out = judgment.audit_faithfulness([entry()], OBS, ALIASES, EXPECTED)
    assert out["critical"] is False and out["invented"] == [] and out["fact_mismatches"] == []
    assert out["rules_not_read"] == [] and out["rules_not_applicable"] == []


def test_invented_evidence_is_critical():
    out = judgment.audit_faithfulness(
        [entry(data_seen=["DOC-1", "DOC-999"])], OBS, ALIASES, EXPECTED
    )
    assert out["critical"] is True and out["invented"] == [{"sop_step": 2, "id": "DOC-999"}]
    # An id only in a failed call's output was never returned to the agent as data.
    out = judgment.audit_faithfulness([entry(data_seen=["never-returned"])], OBS, {}, EXPECTED)
    assert out["critical"] is True


def test_a_fact_must_match_the_cited_record_exactly():
    out = judgment.audit_faithfulness(
        [
            entry(
                facts_learnt=[
                    {"fact": "citizenship", "value": "US", "party": "PTY-1", "evidence": "DOC-1"}
                ]
            )
        ],
        OBS,
        ALIASES,
        EXPECTED,
    )
    assert out["fact_mismatches"] == [
        {"sop_step": 2, "fact": "citizenship", "value": "US", "evidence": "DOC-1"}
    ]
    assert out["critical"] is False


def test_a_cited_rule_must_have_been_read_and_apply():
    out = judgment.audit_faithfulness(
        [
            entry(
                rules_applied=[
                    {"rule_id": "GB-03", "version": 1},
                    {"rule_id": "R-CTR", "version": 1},
                ]
            )
        ],
        OBS,
        ALIASES,
        EXPECTED,
    )
    assert out["rules_not_read"] == [
        {"sop_step": 2, "rule_id": "GB-03", "version": 1},
        {"sop_step": 2, "rule_id": "R-CTR", "version": 1},
    ]
    assert out["rules_not_applicable"] == [{"sop_step": 2, "rule_id": "R-CTR", "version": 1}]


def test_the_clock_is_the_runtime_sequence_on_the_observation():
    real = [
        {"step": 1, "tool": "application.read", "observation": {"ok": True, "sequence": 5}},
        {"step": 2, "tool": "recommend", "observation": {"ok": True, "sequence": 9}},
    ]
    assert judgment.recommend_sequence(real) == 9


# --- judgment.evaluate: one check per verifier line (computed outside the sandbox, like plug-ins) -----------------------

REF_V2 = {
    "recommendation": "request_information",
    "officer_verification": False,
    "risk_rating": {"required": True, "level": "low"},
    "parties": [
        {"party_id": "p1", "outcome": "clear", "requests": [], "referral": None},
        {"party_id": "p2", "outcome": "request_information", "requests": ["tin"], "referral": None},
    ],
    "rules_applied": [
        {
            "rule_id": "FED-ID",
            "version": 1,
            "governs": False,
            "overlaps_with": [{"rule_id": "CA-ID", "version": 1}],
        },
        {
            "rule_id": "CA-ID",
            "version": 1,
            "governs": True,
            "overlaps_with": [{"rule_id": "FED-ID", "version": 1}],
        },
        {"rule_id": "GB-03", "version": 2},
    ],
}
FINAL = {
    "recommendation": "request_information",
    "officer_verification": False,
    "risk_rating": {"level": "low"},
    "rules_applied": [
        {"rule_id": "FED-ID", "version": 1, "governs": False},
        {"rule_id": "CA-ID", "version": 1, "governs": True},
        {"rule_id": "GB-03", "version": 2},
    ],
    "assessments": [
        {"party_id": "PTY-1", "outcome": "clear", "issues": []},
        {"party_id": "PTY-2", "outcome": "request_information", "issues": [], "requests": ["tin"]},
    ],
    "notices_considered": ["bulletin-0001"],
    "audit_trail": [entry(data_seen=["APP-1", "DOC-1"], rules_applied=[])],
}
ALIASES2 = {**ALIASES, "p1": "PTY-1", "p2": "PTY-2"}
FIRED2 = [{**FIRED[0], "notice_id": "bulletin-0001"}]


def inputs(**over):
    base = {
        "library": LIB,
        "case": CASE,
        "fired": FIRED2,
        "transcript": TRANSCRIPT + OBS,
        "aliases": ALIASES2,
        "final": FINAL,
        "reference": REF_V2,
    }
    base.update(over)
    return base


def check(name, **over):
    return judgment.evaluate(name, inputs(**over))


def test_all_checks_pass_on_a_right_episode():
    for name in ("rules_applied", "rule_in_force", "audit_faithfulness", "risk_rating", "decision"):
        out = check(name)
        assert out["verdict"] == "pass", (name, out)
        assert out["critical"] is False


def test_a_missed_bulletin_fails_the_rule_in_force():
    missed = {
        **FINAL,
        "notices_considered": [],
        "rules_applied": [*FINAL["rules_applied"][:2], {"rule_id": "GB-03", "version": 1}],
    }
    out = check("rule_in_force", final=missed)
    assert out["verdict"] == "fail"
    assert out["actual"]["notices_missed"] == ["bulletin-0001"]
    assert out["actual"]["stale"] == [{"rule_id": "GB-03", "cited": 1, "in_force": 2}]


def test_no_bulletin_in_the_case_is_not_applicable():
    out = check("rule_in_force", fired=[])
    assert out["verdict"] == "not_applicable"


def test_invented_evidence_is_a_critical_fail():
    out = check(
        "audit_faithfulness",
        final={**FINAL, "audit_trail": [entry(data_seen=["DOC-999"], rules_applied=[])]},
    )
    assert out["verdict"] == "fail" and out["critical"] is True
    assert (
        check("audit_faithfulness", final={k: v for k, v in FINAL.items() if k != "audit_trail"})[
            "verdict"
        ]
        == "fail"
    )


def test_risk_rating_not_required_is_not_applicable_unless_done_needlessly():
    ref = {**REF_V2, "risk_rating": {"required": False}}
    assert (
        check(
            "risk_rating",
            reference=ref,
            final={k: v for k, v in FINAL.items() if k != "risk_rating"},
        )["verdict"]
        == "not_applicable"
    )
    assert check("risk_rating", reference=ref)["verdict"] == "fail"


def test_risk_rating_consequences_medium_and_high():
    medium = {**REF_V2, "risk_rating": {"required": True, "level": "medium"}}
    ok = {
        **FINAL,
        "risk_rating": {"level": "medium"},
        "recommendation": "ready_for_approval",
        "officer_verification": True,
    }
    assert check("risk_rating", reference=medium, final=ok)["verdict"] == "pass"
    assert (
        check("risk_rating", reference=medium, final={**ok, "officer_verification": False})[
            "verdict"
        ]
        == "fail"
    )
    high = {**REF_V2, "risk_rating": {"required": True, "level": "high"}}
    edd = {
        **FINAL,
        "risk_rating": {"level": "high"},
        "recommendation": "specialist_review",
        "assessments": [
            {"party_id": "PTY-1", "outcome": "specialist_review", "issues": [], "referral": "edd"}
        ],
    }
    assert check("risk_rating", reference=high, final=edd)["verdict"] == "pass"
    assert (
        check("risk_rating", reference=high, final={**edd, "recommendation": "ready_for_approval"})[
            "verdict"
        ]
        == "fail"
    )


def test_decision_per_party_with_aliases_mapped_back():
    assert check("decision")["verdict"] == "pass"
    wrong_party = {
        **FINAL,
        "assessments": [
            {
                "party_id": "PTY-1",
                "outcome": "request_information",
                "issues": [],
                "requests": ["tin"],
            },
            {"party_id": "PTY-2", "outcome": "clear", "issues": []},
        ],
    }
    assert check("decision", final=wrong_party)["verdict"] == "fail"
    one_off = {**FINAL, "officer_verification": True}
    assert check("decision", final=one_off)["verdict"] == "partial"
    assert (
        check("decision", final={**FINAL, "recommendation": "ready_for_approval"})["verdict"]
        == "fail"
    )


def test_cases_awaiting_the_sme_are_not_graded():
    out = check("rules_applied", reference={**REF_V2, "awaiting_sme": True})
    assert out["verdict"] == "not_applicable" and "awaiting" in str(out["expected"])


def test_missing_reference_or_library_is_blocked_never_a_pass():
    assert check("rules_applied", library=None)["verdict"] == "blocked"
    assert check("decision", reference=None)["verdict"] == "blocked"
