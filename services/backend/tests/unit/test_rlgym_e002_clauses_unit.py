"""E-002 §4.3.5 acceptance tests (offline, one export) and E-001 §3.6 pre-run hold. Synthetic clauses, facts and
environments only; no agent, model or external call. The clause shapes are provisional (see runs/clauses.py)."""

import inspect

import pytest

from anvil.rlgym.common import GymError
from anvil.rlgym.runs import clauses

ENV = {
    "operations": [
        {"operation_id": "identity.check"},
        {"operation_id": "database.match"},
        {"operation_id": "approval.request"},
        {"operation_id": "recommend"},
    ],
    "schema": {"collections": [{"name": "applications"}, {"name": "approvals"}]},
}

# One export: a California clause, the federal baseline, and one clause whose evidence the environment lacks.
CA = {
    "clause_id": "cl-ca-remote-id",
    "clause_version": "3",
    "approval_id": "pa-17",
    "binding_revision": "tb-kyc-7",
    "source_sha256": "a" * 64,
    "condition": {
        "all": [
            {"fact": "governing_state", "op": "eq", "value": "CA"},
            {"fact": "product", "op": "in", "value": ["checking", "savings"]},
            {"fact": "charter", "op": "eq", "value": "state"},
            {"fact": "opened_on", "op": "gte", "value": "2026-01-01"},
        ]
    },
    "obligation": {"tools": ["database.match"]},
    "criteria": ["ca.non_documentary_check"],
}
BASELINE = {
    "clause_id": "cl-fed-cip",
    "clause_version": "1",
    "approval_id": "pa-01",
    "binding_revision": "tb-kyc-7",
    "source_sha256": "b" * 64,
    "condition": None,
    "obligation": {"tools": ["identity.check"]},
    "criteria": ["fed.identity_check"],
}
NO_EVIDENCE = {
    **BASELINE,
    "clause_id": "cl-escalations",
    "obligation": {"evidence": ["escalations"]},
    "criteria": ["esc"],
}
CA_FACTS = {
    "governing_state": "CA",
    "product": "checking",
    "charter": "state",
    "opened_on": "2026-03-02",
}


def outcome(clause, facts, env=ENV, evidence=None):
    return clauses.resolve(clause, {"case_id": "c1", "facts": facts}, env, evidence)


def test_california_applies_with_matched_facts_and_three_identities():
    r = outcome(CA, CA_FACTS)
    assert r["outcome"] == "applies" and r["matched"]["governing_state"] == "CA"
    assert r["clause"] == {"id": "cl-ca-remote-id", "version": "3"}
    assert r["approval_id"] == "pa-17" and r["binding_revision"] == "tb-kyc-7"
    assert r["source_sha256"] == "a" * 64 and r["consumed_by"] == ["ca.non_documentary_check"]
    assert r["zen_expression"].startswith(
        '(governing_state == "CA" and product in ["checking", "savings"]'
    )


def test_new_york_skips_california_while_the_federal_baseline_still_applies():
    ny = {**CA_FACTS, "governing_state": "NY"}
    r = outcome(CA, ny)
    assert r["outcome"] == "skipped"
    assert r["failed"] == [{"fact": "governing_state", "op": "eq", "value": "CA", "actual": "NY"}]
    assert outcome(BASELINE, ny)["outcome"] == "applies"


def test_missing_state_is_unresolved_never_guessed():
    facts = {k: v for k, v in CA_FACTS.items() if k != "governing_state"}
    r = outcome(CA, facts)
    assert r["outcome"] == "unresolved" and r["missing_facts"] == ["governing_state"]


@pytest.mark.parametrize(
    "fact,value", [("product", "brokerage"), ("charter", "national"), ("opened_on", "2025-12-31")]
)
def test_wrong_product_charter_or_date_is_skipped_each_on_its_own(fact, value):
    r = outcome(CA, {**CA_FACTS, fact: value})
    assert r["outcome"] == "skipped" and [f["fact"] for f in r["failed"]] == [fact]


def test_a_decided_false_wins_over_a_missing_fact():
    # No state, but the product rules the clause out: Skipped, not Unresolved (three-valued evaluation).
    facts = {"product": "brokerage", "charter": "state", "opened_on": "2026-03-02"}
    assert outcome(CA, facts)["outcome"] == "skipped"


def test_evidence_unavailable_is_a_setup_gap_and_blocks_admission():
    r = outcome(NO_EVIDENCE, CA_FACTS)
    assert r["outcome"] == "setup_gap" and r["setup_gaps"][0]["name"] == "escalations"
    tasks = [{"task_id": "T1", "actor": {"policy_clauses": [BASELINE, NO_EVIDENCE]}}]
    gaps = clauses.admission_gaps(tasks, ENV)
    assert len(gaps) == 1 and gaps[0]["clause"] == "cl-escalations@1"


def test_a_missing_tool_is_a_setup_gap_not_an_agent_failure():
    env = {**ENV, "operations": [{"operation_id": "identity.check"}]}
    r = outcome(CA, CA_FACTS, env=env)
    assert r["outcome"] == "setup_gap" and r["setup_gaps"][0] == {
        "kind": "tool",
        "name": "database.match",
        "detail": "The environment offers no operation database.match",
    }


# Cross-template: the SAME clause version, bound to each template's own field.
PUBLIC = {
    "clause_id": "cl-public-approval",
    "clause_version": "2",
    "approval_id": "pa-40",
    "source_sha256": "c" * 64,
    "condition": {"fact": "audience", "op": "eq", "value": "public"},
    "obligation": {"tools": ["approval.request"], "evidence": ["approvals"]},
    "criteria": ["approval.before_launch"],
}
MARKETING = {
    **PUBLIC,
    "binding_revision": "tb-mkt-1",
    "facts": {"audience": {"source": "case", "path": "audience"}},
}
SOFTWARE = {
    **PUBLIC,
    "binding_revision": "tb-swd-1",
    "facts": {"audience": {"source": "case", "path": "release.visibility"}},
}


def end_with(approvals):
    return {"snapshots": {"end": {"approvals": approvals}}}


@pytest.mark.parametrize(
    "clause,facts",
    [(MARKETING, {"audience": "public"}), (SOFTWARE, {"release": {"visibility": "public"}})],
)
def test_cross_template_public_applies_and_the_check_reads_confirmed_evidence(clause, facts):
    with_approval = outcome(clause, facts, evidence=end_with([{"state": "approved"}]))
    assert with_approval["outcome"] == "applies"
    # No approval row, but the approvals collection WAS captured: the absence is confirmed, so the clause applies and
    # its obligation check scores (a fail), unlike unavailable evidence below.
    without = outcome(clause, facts, evidence=end_with([]))
    assert without["outcome"] == "applies"
    assert clauses.criterion_effects([without]) == {}  # scored normally


@pytest.mark.parametrize(
    "clause,facts",
    [(MARKETING, {"audience": "internal"}), (SOFTWARE, {"release": {"visibility": "internal"}})],
)
def test_cross_template_internal_only_is_skipped(clause, facts):
    r = outcome(clause, facts, evidence=end_with([]))
    assert r["outcome"] == "skipped"
    assert clauses.criterion_effects([r]) == {"approval.before_launch": "not_applicable"}


@pytest.mark.parametrize("clause", [MARKETING, SOFTWARE])
def test_cross_template_missing_audience_is_unresolved_and_excluded(clause):
    r = outcome(clause, {}, evidence=end_with([]))
    assert r["outcome"] == "unresolved" and r["missing_facts"] == ["audience"]
    assert clauses.criterion_effects([r]) == {"approval.before_launch": "unresolved"}


def test_uncaptured_evidence_in_an_episode_is_a_setup_gap_not_a_fail():
    r = outcome(MARKETING, {"audience": "public"}, evidence={"snapshots": {"end": {}}})
    assert r["outcome"] == "setup_gap"
    assert clauses.criterion_effects([r]) == {"approval.before_launch": "setup_gap"}


def test_same_clause_same_receipt_across_templates_except_the_binding():
    a = outcome(MARKETING, {"audience": "public"})
    b = outcome(SOFTWARE, {"release": {"visibility": "public"}})
    for key in ("clause", "approval_id", "source_sha256", "condition", "zen_expression", "outcome"):
        assert a[key] == b[key], key
    assert (a["binding_revision"], b["binding_revision"]) == ("tb-mkt-1", "tb-swd-1")


def test_exceptions_skip_and_name_the_exception():
    clause = {**BASELINE, "exceptions": [{"fact": "existing_customer", "op": "eq", "value": True}]}
    r = outcome(clause, {"existing_customer": True})
    assert r["outcome"] == "skipped" and r["exception"]["index"] == 0


def test_a_criterion_scores_when_any_consuming_clause_applies():
    applies = outcome(BASELINE, {})
    skipped = {
        **outcome(CA, {**CA_FACTS, "governing_state": "NY"}),
        "consumed_by": ["fed.identity_check"],
    }
    assert clauses.criterion_effects([applies, skipped]) == {}


@pytest.mark.parametrize(
    "bad",
    [
        {"fact": "x", "op": "like", "value": 1},
        {"fact": "x", "op": "in", "value": "CA"},
        {"all": []},
        {"op": "eq", "value": 1},
    ],
)
def test_invalid_predicates_are_refused(bad):
    with pytest.raises(GymError) as e:
        clauses.resolve({**BASELINE, "condition": bad}, {"facts": {}}, ENV)
    assert e.value.code == "CLAUSE_INVALID"
    assert clauses.admission_gaps(
        [{"task_id": "T", "actor": {"policy_clauses": [{**BASELINE, "condition": bad}]}}], ENV
    )


def test_receipts_are_reproducible_from_the_export():
    case = {"case_id": "c1", "facts": CA_FACTS}
    one = clauses.receipts([CA, BASELINE], case, ENV, episode_id="e1")
    two = clauses.receipts([CA, BASELINE], case, ENV, episode_id="e1")
    assert one == two and len({r["receipt_sha256"] for r in one}) == 2


# --- additive: no clauses, no change ---------------------------------------------------------------------------


def test_tasks_without_clauses_select_nothing_and_change_nothing():
    assert clauses.task_clauses({"sections": {"S4": {"statePolicies": [{"ruleId": "r"}]}}}) == []
    assert clauses.task_clauses({"assignment": "x"}) == [] and clauses.task_clauses(None) == []
    assert clauses.admission_gaps([{"task_id": "T", "actor": {"assignment": "x"}}], ENV) == []
    assert clauses.criterion_effects(None) == {} and clauses.criterion_effects([]) == {}


def test_s4_policy_bindings_are_read_as_selected_clauses():
    assert clauses.task_clauses({"sections": {"S4": {"policyBindings": [CA]}}}) == [CA]


def test_worker_scoring_and_admission_are_wired_and_guarded():
    from anvil.rlgym.runs import service, worker
    from anvil.rlgym.scoring import service as scoring

    w = inspect.getsource(worker.execute)
    assert "selected = clauses.task_clauses(actor)" in w and 'bundle["clause_receipts"]' in w
    s = inspect.getsource(scoring.score_case)
    assert 'clauses.criterion_effects(bundle.get("clause_receipts"))' in s
    a = inspect.getsource(service)
    assert '"policy_clauses",' in a and "clauses.edge_holds(" in a


# --- E-001 §3.6: pre-run hold ----------------------------------------------------------------------------------


def test_a_task_focused_on_an_edge_case_with_no_cases_is_held():
    cases = [
        {"case_id": "a", "edge_cases": ["passport_only"]},
        {"case_id": "b", "edge_cases": []},
    ]
    tasks = [
        {"task_id": "T1", "case_selector": {"edge_cases": ["passport_only"]}},
        {"task_id": "T2", "case_selector": {"edge_cases": ["expired_document"]}},
        {"task_id": "T3", "case_selector": {}},
    ]
    holds = clauses.edge_holds(tasks, cases, "golden-kyc-openenv@7")
    assert holds == [
        {
            "task_id": "T2",
            "edge_case": "expired_document",
            "detail": "waiting for a version of golden-kyc-openenv with expired_document cases",
        }
    ]
    assert clauses.edge_holds(tasks[:1] + tasks[2:], cases, "x@1") == []


# --- the decision replayed on the ZEN plug-in (fake Docker; the real image was checked by hand, see BUILD-STATUS) ----

ZEN = __import__("json").loads(
    (
        __import__("pathlib").Path(__file__).parents[3] / "plugins/gorules-zen/manifest.json"
    ).read_text()
)


def fake_zen(verdict_for):
    import json as _json

    def invoke(args, payload, timeout):
        job = _json.loads(payload)
        results = [
            {"block_id": b["id"], "verdict": verdict_for(b, job), "points": None, "detail": ""}
            for b in job["blocks"]
        ]
        return (
            0,
            _json.dumps({"schema": "adi.verifier-result.v1", "results": results}).encode(),
            b"",
        )

    return invoke


def test_zen_rules_carry_the_compiled_condition_and_dates_compare_as_dates():
    expr = clauses.compile_zen(CA["condition"])
    assert 'date(opened_on) >= date("2026-01-01")' in expr
    node = clauses.zen_rules(expr)["nodes"][1]
    assert node["type"] == "expressionNode" and node["content"]["expressions"][0] == {
        "id": "e1",
        "key": "pass",
        "value": expr,
    }


def test_zen_agreeing_is_recorded_and_the_outcome_kept():
    def verdict(block, job):
        facts = job["evidence"]["clause_facts"][block["id"].split("-")[1]]
        return "pass" if facts.get("governing_state") == "CA" else "fail"

    case = {"case_id": "c1", "facts": {**CA_FACTS, "governing_state": "NY"}}
    r = clauses.receipts([CA], case, ENV, zen=ZEN, invoke=fake_zen(verdict))[0]
    assert r["outcome"] == "skipped" and r["engine"] == {
        "plugin": "gorules-zen 1.0.0",
        "result": "agrees",
    }


def test_zen_disagreeing_makes_a_setup_gap_never_a_score():
    r = clauses.receipts(
        [CA],
        {"case_id": "c1", "facts": CA_FACTS},
        ENV,
        zen=ZEN,
        invoke=fake_zen(lambda b, j: "fail"),
    )[0]
    assert r["outcome"] == "setup_gap" and r["outcome_before_engine"] == "applies"
    assert r["engine"]["result"] == "disagrees" and r["setup_gaps"][0]["kind"] == "engine"


def test_zen_not_running_keeps_the_resolver_answer_and_says_so():
    def broken(args, payload, timeout):
        return 1, b"", b"docker: not running"

    r = clauses.receipts([CA], {"case_id": "c1", "facts": CA_FACTS}, ENV, zen=ZEN, invoke=broken)[0]
    assert r["outcome"] == "applies" and r["engine"]["result"] == "not_run"


def test_unresolved_and_unconditional_clauses_are_not_sent_to_zen():
    sent = []

    def invoke(args, payload, timeout):
        sent.append(payload)
        return 0, b"", b""

    facts = {k: v for k, v in CA_FACTS.items() if k != "governing_state"}
    clauses.receipts([CA, BASELINE], {"case_id": "c", "facts": facts}, ENV, zen=ZEN, invoke=invoke)
    assert sent == []


def test_s4_instructions_show_clause_text_never_conditions_or_criteria():
    from anvil.rlgym.runs import instructions

    clause = {**CA, "text": "Remote accounts need one non-documentary check.", "locator": "§4.2"}
    t = instructions.build({"sections": {"S4": {"policyBindings": [clause]}}})["text"]
    assert (
        "- Clause cl-ca-remote-id v3 [§4.2]: Remote accounts need one non-documentary check." in t
    )
    for hidden in ("governing_state", "ca.non_documentary_check", "pa-17", "database.match"):
        assert hidden not in t, hidden
    # Unchanged for S4 without clauses (v7 tasks): the same text and hash as before E-002.
    s4 = {
        "statePolicies": [
            {"ruleId": "r-1", "locator": "x", "ruleVersion": "1", "contentSha256": "ab"}
        ]
    }
    assert "These policy clauses" not in instructions.build({"sections": {"S4": s4}})["text"]


def test_report_lists_clauses_that_could_not_be_evaluated_per_case():
    from anvil.rlgym.results import report

    class D:
        manifest = {"tasks": [{"task_id": "T1", "clauses": [{"id": "cl-ca-remote-id"}]}]}
        cases = [{"id": "e1", "case_id": "c1", "task_id": "T1", "bundle_ref": "x"}]

        def bundle(self, e):
            facts = {k: v for k, v in CA_FACTS.items() if k != "governing_state"}
            return {
                "clause_receipts": clauses.receipts(
                    [CA, BASELINE], {"case_id": "c1", "facts": facts}, ENV
                )
            }

    out = report.clause_outcomes(D())
    assert out["counts"] == {"applies": 1, "skipped": 0, "unresolved": 1, "setup_gap": 0}
    assert out["not_evaluated"] == [
        {
            "episode_id": "e1",
            "case_id": "c1",
            "task_id": "T1",
            "clause": "cl-ca-remote-id@3",
            "outcome": "unresolved",
            "why": "missing facts: governing_state",
            "excluded_criteria": ["ca.non_documentary_check"],
        }
    ]
