"""E-002 §4.3.5 acceptance tests (offline, one export) and E-001 §3.6 pre-run hold, on Studio's draft contracts
(clause-condition.v1, clause-receipt.v1, registry-case.v1 facts, the release's policy_bindings). Synthetic clauses,
facts and environments only; no agent, model, Studio or external call. Receipts are checked against a copy of
Studio's clause-receipt.v1 schema (tests/fixtures/contracts)."""

import inspect
import json
import pathlib

import pytest

from anvil.rlgym.common import GymError
from anvil.rlgym.runs import clauses

HERE = pathlib.Path(__file__)
SCHEMA = json.loads(
    (HERE.parents[1] / "fixtures/contracts/clause-receipt.v1.schema.json").read_text()
)
ZEN = json.loads((HERE.parents[3] / "plugins/gorules-zen/manifest.json").read_text())


def conforms(r):
    """Required and allowed keys of clause-receipt.v1, top level and nested (no jsonschema dependency)."""
    props = SCHEMA["properties"]
    assert set(SCHEMA["required"]) <= set(r), set(SCHEMA["required"]) - set(r)
    assert set(r) <= set(props), set(r) - set(props)
    assert r["schema_version"] == props["schema_version"]["const"]
    assert r["outcome"] in props["outcome"]["enum"] and r["scored"] == (r["outcome"] == "applies")
    for key in ("clause", "approval", "binding", "task"):
        if key in r:
            assert set(r[key]) <= set(props[key]["properties"]), (key, set(r[key]))
            assert set(props[key].get("required") or []) <= set(r[key]), key
    for key in ("facts_used", "setup_gaps"):
        spec = props[key]["items"]
        for x in r.get(key) or []:
            assert set(spec["required"]) <= set(x) <= set(spec["properties"]), (key, x)
    for x in r.get("consumed_by") or []:
        assert set(x) <= set(props["consumed_by"]["items"]["properties"])
    if "phase" in r:
        assert r["phase"] in props["phase"]["enum"]
    for g in r.get("setup_gaps") or []:
        assert g["kind"] in props["setup_gaps"]["items"]["properties"]["kind"]["enum"]
    return r


def case_fact(name, field=None):
    return {
        "id": name,
        "availability": "case_data",
        "source": {"collection": "applications", "field": field or name},
    }


ENV = {
    "operations": [
        {"operation_id": "identity.check"},
        {"operation_id": "database.match"},
        {"operation_id": "approval.request"},
        {"operation_id": "recommend"},
    ],
    "schema": {"collections": [{"name": "applications"}, {"name": "approvals"}]},
    "facts": {
        "facts": [
            case_fact("governing_state"),
            case_fact("product"),
            case_fact("charter"),
            case_fact("submitted_at"),
        ]
    },
}


def needs(tools=(), evidence=(), checks=()):
    return {"tools": list(tools), "evidence": list(evidence), "checks": list(checks)}


KYC_BINDINGS = {
    "fact_catalog": "golden-kyc-openenv.facts@1",
    "facts": [
        {"fact": "governing_state", "environment_fact": "governing_state"},
        {"fact": "product", "environment_fact": "product"},
        {"fact": "charter", "environment_fact": "charter"},
        {"fact": "opened_on", "environment_fact": "submitted_at"},
    ],
    "clauses": [
        {
            "clause_id": "pol-ca-remote",
            "needs": needs(
                ["database.match"],
                checks=[{"criterion_id": "ca.non_documentary", "block_ids": ["ca.match_called"]}],
            ),
        },
        {
            "clause_id": "pol-fed-cip",
            "needs": needs(
                ["identity.check"],
                checks=[{"criterion_id": "fed.identity", "block_ids": ["identity.called"]}],
            ),
        },
        {
            "clause_id": "pol-escalate",
            "needs": needs(
                evidence=["escalations"], checks=[{"criterion_id": "esc", "block_ids": ["esc.row"]}]
            ),
        },
    ],
}
SRC = {"document_id": "doc-ca", "document_version": 2, "sha256": "a" * 64, "locator": "§4.2"}
CA = {
    "clause": {
        "clause_id": "pol-ca-remote",
        "version": 3,
        "title": "California remote accounts",
        "source": SRC,
    },
    "approval": {"approval_id": "appr-17", "project_id": "prj-kyc"},
    "condition": {
        "all": [
            {
                "fact": "governing_state",
                "op": "eq",
                "value": "CA",
                "label": "Governing state is CA",
            },
            {"fact": "product", "op": "in", "value": ["individual", "adult_joint"]},
            {"fact": "charter", "op": "eq", "value": "state"},
            {"fact": "opened_on", "op": "gte", "value": "2026-01-01"},
        ]
    },
}
BASELINE = {
    "clause": {
        "clause_id": "pol-fed-cip",
        "version": 1,
        "source": {**SRC, "document_id": "doc-cip"},
    },
    "approval": {"approval_id": "appr-01", "project_id": "prj-kyc"},
    "condition": None,
}
NO_EVIDENCE = {**BASELINE, "clause": {**BASELINE["clause"], "clause_id": "pol-escalate"}}
CA_FACTS = {
    "governing_state": "CA",
    "product": "individual",
    "charter": "state",
    "submitted_at": "2026-03-02",
}
CTX = {
    "run_id": "run-0300",
    "episode_id": "run-0300-e0001",
    "task": {"task_id": "T1", "task_revision": 1},
    "binding": {
        "template_id": "tpl_x5rwt6d5eu",
        "template_version": 8,
        "environment_version_id": "golden-kyc-openenv@8",
    },
}


def outcome(clause, facts, env=ENV, evidence=None, bindings=KYC_BINDINGS):
    r, _ = clauses.resolve(clause, {"case_id": "c1", "facts": facts}, env, evidence, bindings, CTX)
    return conforms(r)


def test_california_applies_with_matched_facts_and_three_identities():
    r = outcome(CA, CA_FACTS)
    assert r["outcome"] == "applies" and r["phase"] == "static"
    assert (
        r["clause"]["clause_id"] == "pol-ca-remote" and r["clause"]["source"]["sha256"] == "a" * 64
    )
    assert r["approval"] == {"approval_id": "appr-17", "project_id": "prj-kyc"}
    assert r["binding"] == {**CTX["binding"], "fact_catalog": "golden-kyc-openenv.facts@1"}
    assert r["consumed_by"] == [
        {"criterion_id": "ca.non_documentary", "block_ids": ["ca.match_called"]}
    ]
    assert {
        "fact": "opened_on",
        "value": "2026-03-02",
        "source": "case_data:applications.submitted_at",
    } in r["facts_used"]
    assert r["receipt_id"].startswith("cr-") and r["run_id"] == "run-0300"


def test_new_york_skips_california_while_the_federal_baseline_still_applies():
    ny = {**CA_FACTS, "governing_state": "NY"}
    r = outcome(CA, ny)
    assert r["outcome"] == "skipped"
    assert r["failed_conditions"] == ["Governing state is CA (it is NY)"]
    assert outcome(BASELINE, ny)["outcome"] == "applies"


def test_missing_state_is_unresolved_never_guessed():
    facts = {k: v for k, v in CA_FACTS.items() if k != "governing_state"}
    r = outcome(CA, facts)
    assert r["outcome"] == "unresolved" and r["missing_facts"] == ["governing_state"]
    assert "excluded from the score" in r["scenario"]


@pytest.mark.parametrize(
    "fact,value,text",
    [
        ("product", "custodial", "product is one of individual, adult_joint (it is custodial)"),
        ("charter", "national", "charter is state (it is national)"),
        ("submitted_at", "2025-12-31", "opened_on is at least 2026-01-01 (it is 2025-12-31)"),
    ],
)
def test_wrong_product_charter_or_date_is_skipped_each_on_its_own(fact, value, text):
    r = outcome(CA, {**CA_FACTS, fact: value})
    assert r["outcome"] == "skipped" and r["failed_conditions"] == [text]


def test_a_decided_false_wins_over_a_missing_fact():
    facts = {"product": "custodial", "charter": "state", "submitted_at": "2026-03-02"}
    assert outcome(CA, facts)["outcome"] == "skipped"


def test_evidence_unavailable_is_a_setup_gap_and_blocks_admission():
    r = outcome(NO_EVIDENCE, CA_FACTS)
    assert r["outcome"] == "setup_gap" and r["setup_gaps"] == [
        {
            "kind": "evidence",
            "ref": "escalations",
            "message": "The environment does not capture escalations",
        }
    ]
    tasks = [{"task_id": "T1", "actor": {"policy_clauses": [BASELINE, NO_EVIDENCE]}}]
    gaps = clauses.admission_gaps(tasks, ENV, KYC_BINDINGS)
    assert [g["clause"] for g in gaps] == ["pol-escalate@1"]


def test_a_missing_tool_is_a_setup_gap_not_an_agent_failure():
    env = {**ENV, "operations": [{"operation_id": "identity.check"}]}
    r = outcome(CA, CA_FACTS, env=env)
    assert r["outcome"] == "setup_gap" and r["setup_gaps"][0]["kind"] == "tool"
    assert r["setup_gaps"][0]["ref"] == "database.match"


def test_a_condition_fact_the_template_does_not_bind_is_a_setup_gap():
    pb = {**KYC_BINDINGS, "facts": [f for f in KYC_BINDINGS["facts"] if f["fact"] != "charter"]}
    r = outcome(CA, CA_FACTS, bindings=pb)
    assert r["outcome"] == "setup_gap" and r["setup_gaps"][0] == {
        "kind": "fact_binding",
        "ref": "charter",
        "message": "The template binds no environment fact to charter",
    }
    tasks = [{"task_id": "T", "actor": {"policy_clauses": [CA]}}]
    assert clauses.admission_gaps(tasks, ENV, pb)


# Cross-template: the SAME clause version; each template binds the logical fact `audience` to its own environment fact.
PUBLIC = {
    "clause": {
        "clause_id": "pol-public-release-approval",
        "version": 1,
        "title": "Public release needs approval",
        "source": {**SRC, "document_id": "doc-release"},
    },
    "approval": {"approval_id": "appr-07", "project_id": "prj-q4"},
    "condition": {"fact": "audience", "op": "eq", "value": "public", "label": "Audience is public"},
}


def bindings_for(env_fact, catalog):
    check = {"criterion_id": "release_control", "block_ids": ["release.approval_before_launch"]}
    return {
        "fact_catalog": catalog,
        "facts": [{"fact": "audience", "environment_fact": env_fact}],
        "clauses": [
            {
                "clause_id": "pol-public-release-approval",
                "needs": needs(["approval.request"], ["approvals"], [check]),
            }
        ],
    }


MARKETING = bindings_for("audience", "marketing-campaign-openenv.facts@1")
SOFTWARE = bindings_for("release_visibility", "software-release-openenv.facts@1")
CROSS = [(MARKETING, "audience"), (SOFTWARE, "release_visibility")]


def end_with(approvals):
    return {"snapshots": {"end": {"approvals": approvals}}}


@pytest.mark.parametrize("pb,field", CROSS)
def test_cross_template_public_applies_with_and_without_a_confirmed_approval(pb, field):
    approved = outcome(
        PUBLIC, {field: "public"}, evidence=end_with([{"state": "approved"}]), bindings=pb
    )
    assert approved["outcome"] == "applies" and approved["phase"] == "dynamic"
    # No approval row, but the approvals table WAS captured: the absence is confirmed, so the clause applies and its
    # check scores (a fail), unlike unavailable evidence below.
    without = outcome(PUBLIC, {field: "public"}, evidence=end_with([]), bindings=pb)
    assert without["outcome"] == "applies" and clauses.criterion_effects([without]) == {}


@pytest.mark.parametrize("pb,field", CROSS)
def test_cross_template_internal_only_is_skipped(pb, field):
    r = outcome(PUBLIC, {field: "internal"}, evidence=end_with([]), bindings=pb)
    assert r["outcome"] == "skipped"
    assert clauses.criterion_effects([r]) == {"release_control": "not_applicable"}


@pytest.mark.parametrize("pb,field", CROSS)
def test_cross_template_missing_audience_is_unresolved_and_excluded(pb, field):
    r = outcome(PUBLIC, {}, evidence=end_with([]), bindings=pb)
    assert r["outcome"] == "unresolved" and r["missing_facts"] == ["audience"]
    assert clauses.criterion_effects([r]) == {"release_control": "unresolved"}


def test_uncaptured_evidence_in_an_episode_is_a_setup_gap_not_a_fail():
    evidence = {"snapshots": {"end": {}}}
    r = outcome(PUBLIC, {"audience": "public"}, evidence=evidence, bindings=MARKETING)
    assert r["outcome"] == "setup_gap"
    assert clauses.criterion_effects([r]) == {"release_control": "setup_gap"}


def test_same_clause_same_decision_across_templates_except_the_binding():
    a = outcome(PUBLIC, {"audience": "public"}, bindings=MARKETING)
    b = outcome(PUBLIC, {"release_visibility": "public"}, bindings=SOFTWARE)
    for key in ("clause", "approval", "condition", "outcome", "consumed_by"):
        assert a[key] == b[key], key
    assert a["binding"]["fact_catalog"] != b["binding"]["fact_catalog"]
    assert a["facts_used"][0]["source"] == "case_data:facts.audience"
    assert b["facts_used"][0]["source"] == "case_data:facts.release_visibility"


def test_episode_evidence_facts_are_read_after_the_episode_only():
    spec = {
        "id": "approval_recorded",
        "availability": "episode_evidence",
        "source": {"path": "snapshots.end.approval_recorded"},
    }
    env = {**ENV, "facts": [spec]}
    pb = {
        "fact_catalog": "x@1",
        "facts": [{"fact": "approved", "environment_fact": "approval_recorded"}],
        "clauses": [],
    }
    clause = {**BASELINE, "condition": {"fact": "approved", "op": "eq", "value": True}}
    assert outcome(clause, {}, env=env, bindings=pb)["outcome"] == "unresolved"
    evidence = {"snapshots": {"end": {"approval_recorded": True}}}
    after = outcome(clause, {}, env=env, bindings=pb, evidence=evidence)
    assert after["outcome"] == "applies" and after["phase"] == "dynamic"


def test_present_absent_and_between():
    def run(cond, facts):
        return outcome({**BASELINE, "condition": cond}, facts, bindings=None)["outcome"]

    assert run({"fact": "tin", "op": "present"}, {"tin": "1"}) == "applies"
    assert run({"fact": "tin", "op": "present"}, {}) == "skipped"
    assert run({"fact": "tin", "op": "absent"}, {}) == "applies"
    assert run({"fact": "age", "op": "between", "value": [13, 17]}, {"age": 15}) == "applies"
    assert run({"fact": "age", "op": "between", "value": [13, 17]}, {"age": 18}) == "skipped"
    expr = clauses.compile_zen(
        {"fact": "d", "op": "between", "value": ["2026-01-01", "2026-12-31"]}
    )
    assert expr == '(date(d) >= date("2026-01-01") and date(d) <= date("2026-12-31"))'


def test_exceptions_skip_and_say_so():
    clause = {**BASELINE, "exceptions": [{"fact": "existing_customer", "op": "eq", "value": True}]}
    r = outcome(clause, {"existing_customer": True}, bindings=None)
    assert r["outcome"] == "skipped" and r["failed_conditions"][0].startswith("exception holds")


def test_a_criterion_scores_when_any_consuming_clause_applies():
    applies = outcome(BASELINE, CA_FACTS)
    ny = outcome(CA, {**CA_FACTS, "governing_state": "NY"})
    skipped = {**ny, "consumed_by": applies["consumed_by"]}
    assert clauses.criterion_effects([applies, skipped]) == {}


@pytest.mark.parametrize(
    "bad",
    [
        {"fact": "x", "op": "like", "value": 1},
        {"fact": "x", "op": "in", "value": "CA"},
        {"fact": "x", "op": "between", "value": [1]},
        {"all": []},
        {"op": "eq", "value": 1},
    ],
)
def test_invalid_predicates_are_refused(bad):
    with pytest.raises(GymError) as e:
        clauses.resolve({**BASELINE, "condition": bad}, {"facts": {}}, ENV)
    assert e.value.code == "CLAUSE_INVALID"
    tasks = [{"task_id": "T", "actor": {"policy_clauses": [{**BASELINE, "condition": bad}]}}]
    assert clauses.admission_gaps(tasks, ENV)


def test_receipts_are_reproducible_from_the_export():
    case = {"case_id": "c1", "facts": CA_FACTS}
    one, _ = clauses.receipts([CA, BASELINE], case, ENV, bindings=KYC_BINDINGS, context=CTX)
    two, _ = clauses.receipts([CA, BASELINE], case, ENV, bindings=KYC_BINDINGS, context=CTX)
    assert one == two and len({r["receipt_id"] for r in one}) == 2


def test_the_provisional_flat_form_is_still_read():
    flat = {
        "clause_id": "cl-1",
        "clause_version": 2,
        "approval_id": "pa-1",
        "source_sha256": "b" * 64,
        "condition": {"fact": "audience", "op": "eq", "value": "public"},
        "obligation": {"tools": ["approval.request"]},
        "criteria": ["c1"],
    }
    r, _ = clauses.resolve(flat, {"case_id": "c", "facts": {"audience": "public"}}, ENV)
    assert r["outcome"] == "applies" and r["clause"]["clause_id"] == "cl-1"
    assert r["consumed_by"] == [{"criterion_id": "c1", "block_ids": []}]


def test_studio_fixture_style_unresolved_receipt():
    # Studio's fixture unresolved.clause-receipt.json: a CA clause on a case with no governing_state.
    clause = {
        "clause": {
            "clause_id": "pol-ca-demo",
            "version": 1,
            "source": {"document_id": "doc-ca", "document_version": 1, "sha256": "0" * 64},
        },
        "approval": {"approval_id": "appr-0011", "project_id": "prj-kyc"},
        "condition": {
            "all": [
                {"fact": "governing_state", "op": "eq", "value": "CA"},
                {"fact": "product", "op": "in", "value": ["individual"]},
            ]
        },
    }
    r = outcome(clause, {"product": "individual"})
    assert r["outcome"] == "unresolved" and r["missing_facts"] == ["governing_state"]
    assert r["scored"] is False


# --- additive: no clauses, no change ---------------------------------------------------------------------------


def test_tasks_without_clauses_select_nothing_and_change_nothing():
    assert clauses.task_clauses({"sections": {"S4": {"statePolicies": [{"ruleId": "r"}]}}}) == []
    assert clauses.task_clauses({"assignment": "x"}) == [] and clauses.task_clauses(None) == []
    assert clauses.admission_gaps([{"task_id": "T", "actor": {"assignment": "x"}}], ENV) == []
    assert clauses.criterion_effects(None) == {} and clauses.criterion_effects([]) == {}


def test_s4_policy_bindings_are_read_as_selected_clauses():
    assert clauses.task_clauses({"sections": {"S4": {"policyBindings": [CA]}}}) == [CA]


def test_worker_scoring_admission_and_activation_are_wired_and_guarded():
    from anvil.rlgym.catalog import templates
    from anvil.rlgym.runs import service, worker
    from anvil.rlgym.scoring import service as scoring

    w = inspect.getsource(worker.execute)
    assert "selected = clauses.task_clauses(actor)" in w
    assert 'bundle["clause_receipts"], bundle["clause_engine"]' in w
    assert 'bindings=m.get("policy_bindings")' in w
    s = inspect.getsource(scoring.score_case)
    assert 'clauses.criterion_effects(bundle.get("clause_receipts"))' in s
    a = inspect.getsource(service)
    assert '"policy_clauses",' in a and "clauses.edge_holds(" in a
    assert 'resolved["policy_bindings"] = pb' in a
    assert "_policy_binding_checks(doc)" in inspect.getsource(templates.validate)


def test_release_policy_bindings_must_name_real_criteria_and_blocks():
    from anvil.rlgym.catalog import templates

    def entry(cid, crit, block):
        return {
            "clause_id": cid,
            "needs": needs(checks=[{"criterion_id": crit, "block_ids": [block]}]),
        }

    doc = {
        "criteria": [
            {"criterion_id": "fed.identity", "verifier_blocks": [{"id": "identity.called"}]}
        ],
        "policy_bindings": {
            "fact_catalog": "f@1",
            "facts": [],
            "clauses": [
                entry("a", "fed.identity", "identity.called"),
                entry("b", "nope", "x"),
                entry("c", "fed.identity", "x"),
            ],
        },
    }
    (chk,) = templates._policy_binding_checks(doc)
    assert not chk["ok"] and chk["reasons"] == [
        "b: criterion nope is not in this template",
        "c: block x is not a verifier block of fed.identity",
    ]
    assert templates._policy_binding_checks({"criteria": []}) == []  # v7: no check, unchanged


# --- the decision replayed on the ZEN plug-in (fake Docker; the real image is checked by hand, see BUILD-STATUS) ----


def fake_zen(verdict_for):
    def invoke(args, payload, timeout):
        job = json.loads(payload)
        results = [
            {"block_id": b["id"], "verdict": verdict_for(b, job), "points": None, "detail": ""}
            for b in job["blocks"]
        ]
        out = {"schema": "adi.verifier-result.v1", "results": results}
        return 0, json.dumps(out).encode(), b""

    return invoke


def zen_run(selected, facts, invoke):
    case = {"case_id": "c1", "facts": facts}
    return clauses.receipts(
        selected, case, ENV, bindings=KYC_BINDINGS, context=CTX, zen=ZEN, invoke=invoke
    )


def test_zen_rules_carry_the_compiled_condition_and_dates_compare_as_dates():
    expr = clauses.compile_zen(CA["condition"])
    assert 'date(opened_on) >= date("2026-01-01")' in expr
    node = clauses.zen_rules(expr)["nodes"][1]
    assert node["type"] == "expressionNode"
    assert node["content"]["expressions"][0]["value"] == expr


def test_zen_agreeing_is_recorded_beside_the_receipt():
    def verdict(block, job):
        facts = job["evidence"]["clause_facts"][block["id"].split("-")[1]]
        return "pass" if facts.get("governing_state") == "CA" else "fail"

    (r,), (note,) = zen_run([CA], {**CA_FACTS, "governing_state": "NY"}, fake_zen(verdict))
    assert conforms(r)["outcome"] == "skipped"
    assert note["engine"] == {"plugin": "gorules-zen 1.0.0", "result": "agrees"}
    assert note["receipt_id"] == r["receipt_id"]


def test_zen_disagreeing_makes_a_setup_gap_never_a_score():
    (r,), (note,) = zen_run([CA], CA_FACTS, fake_zen(lambda b, j: "fail"))
    assert conforms(r)["outcome"] == "setup_gap" and note["outcome_before_engine"] == "applies"
    assert note["engine"]["result"] == "disagrees" and r["scored"] is False


def test_zen_not_running_keeps_the_resolver_answer_and_says_so():
    def broken(args, payload, timeout):
        return 1, b"", b"docker: not running"

    (r,), (note,) = zen_run([CA], CA_FACTS, broken)
    assert r["outcome"] == "applies" and note["engine"]["result"] == "not_run"


def test_unresolved_and_unconditional_clauses_are_not_sent_to_zen():
    sent = []

    def invoke(args, payload, timeout):
        sent.append(payload)
        return 0, b"", b""

    facts = {k: v for k, v in CA_FACTS.items() if k != "governing_state"}
    zen_run([CA, BASELINE], facts, invoke)
    assert sent == []


# --- E-001 §3.6: pre-run hold, the report and the agent's instructions --------------------------------------------


def test_a_task_focused_on_an_edge_case_with_no_cases_is_held():
    cases = [{"case_id": "a", "edge_cases": ["passport_only"]}, {"case_id": "b", "edge_cases": []}]
    tasks = [
        {"task_id": "T1", "case_selector": {"edge_cases": ["passport_only"]}},
        {"task_id": "T2", "case_selector": {"edge_cases": ["expired_document"]}},
        {"task_id": "T3", "case_selector": {}},
    ]
    assert clauses.edge_holds(tasks, cases, "golden-kyc-openenv@7") == [
        {
            "task_id": "T2",
            "edge_case": "expired_document",
            "detail": "waiting for a version of golden-kyc-openenv with expired_document cases",
        }
    ]
    assert clauses.edge_holds(tasks[:1] + tasks[2:], cases, "x@1") == []


def test_report_lists_clauses_that_could_not_be_evaluated_per_case():
    from anvil.rlgym.results import report

    class D:
        manifest = {"tasks": [{"task_id": "T1", "clauses": [{"clause": {"clause_id": "x"}}]}]}
        cases = [{"id": "e1", "case_id": "c1", "task_id": "T1", "bundle_ref": "x"}]

        def bundle(self, e):
            facts = {k: v for k, v in CA_FACTS.items() if k != "governing_state"}
            case = {"case_id": "c1", "facts": facts}
            rs, _ = clauses.receipts([CA, BASELINE], case, ENV, bindings=KYC_BINDINGS)
            return {"clause_receipts": rs}

    out = report.clause_outcomes(D())
    assert out["counts"] == {"applies": 1, "skipped": 0, "unresolved": 1, "setup_gap": 0}
    (row,) = out["not_evaluated"]
    assert row["clause"] == "pol-ca-remote@3" and row["outcome"] == "unresolved"
    assert row["why"] == "missing facts: governing_state"
    assert row["excluded_criteria"] == ["ca.non_documentary"]
    assert "cannot be resolved" in row["scenario"]


def test_s4_instructions_show_clause_text_never_conditions_or_criteria():
    from anvil.rlgym.runs import instructions

    clause = {**CA, "text": "Remote accounts need one non-documentary check."}
    t = instructions.build({"sections": {"S4": {"policyBindings": [clause]}}})["text"]
    assert "- Clause pol-ca-remote v3 [§4.2]: Remote accounts need one non-documentary check." in t
    for hidden in ("governing_state", "ca.non_documentary", "appr-17", "database.match"):
        assert hidden not in t, hidden
    s4 = {
        "statePolicies": [
            {"ruleId": "r-1", "locator": "x", "ruleVersion": "1", "contentSha256": "ab"}
        ]
    }
    assert "These policy clauses" not in instructions.build({"sections": {"S4": s4}})["text"]
