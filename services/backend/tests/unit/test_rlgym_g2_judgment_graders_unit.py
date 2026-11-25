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
