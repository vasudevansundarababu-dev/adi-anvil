"""D-062 (G2, part): whose request it is, judged from the case reference and the environment's published rules.

D-041's suggested next_action fix (never created) read the party lacking an ID document only as "expired, else no ID".
@12's KYC-01 also names a name that does not match the identity document; 77 untagged id_document cases are exactly
that, so the party check could not tell whose request it was. The corrected check (party rules 2, a new evaluator
version when a person creates it; nothing already scored changes):
- id_document: every party whose identity document has a different name, has expired before submission, or who has no
  identity document (KYC-01, GB-02); tin: the minor whose TIN is missing (GB-03); proof_of_address: a party with no
  proof of address (KYC-02, application-level: one such party is enough).
- A request of that type to a party who does not lack the item is a wrong call and fails.
- Where the start records show no party lacking the item, the party is not determinable: the line says so and the
  type check alone decides (never a guessed party).
The reference agent and E-007's assertions use the same rules."""

import inspect

from anvil.rlgym.catalog import evaluators, fixes, verifier
from anvil.rlgym.scoring import sandbox_runner as runner
from anvil.rlgym.verification import assertions

FRAMEWORK = {
    "id": "fw-python-1.0.0",
    "runtime_id": "python",
    "installed_locally": True,
    "state": "qualified",
}
V8_BLOCK = {
    "id": "next_action.request",
    "op": "exists_where",
    "row": "any",
    "kind": "state",
    "name": "Request the missing information, or none",
    "table": "information_requests",
    "value": {"case_reference": "reference_answers.request_type"},
    "column": "type",
    "on_fail": "STATE_MUTATION_ERROR",
}
FIX = fixes.SUGGESTED["golden-kyc-blocks:next_action"]["config"]
CASE = "kyc-adult-joint-012"
APP = {"application_id": CASE, "submitted_at": "2026-10-15T14:00:00Z"}
PARTIES = [
    {"party_id": "p1", "application_id": CASE, "role": "primary", "full_name": "Emerson Juniper"},
    {"party_id": "p2", "application_id": CASE, "role": "joint", "full_name": "Rowan Juniper"},
]


def doc(pid, kind, **content):
    return {"document_id": f"{pid}-{kind}", "party_id": pid, "kind": kind, "content": content}


GOOD = [
    doc("p1", "government_id", name_on_document="Emerson Juniper", expires_on="2030-01-01"),
    doc("p1", "proof_of_address", name_on_document="Emerson Juniper"),
    doc("p2", "government_id", name_on_document="Rowan Juniper", expires_on="2030-01-01"),
    doc("p2", "proof_of_address", name_on_document="Rowan Juniper"),
]


def with_doc(i, **content):
    docs = [dict(d, content=dict(d["content"])) for d in GOOD]
    docs[i]["content"].update(content)
    return docs


def start(docs):
    return {
        "applications": [APP],
        "parties": PARTIES,
        "documents": docs,
        "information_requests": [],
    }


def run(docs, requests, request_type="id_document", config=FIX, with_start=True):
    end = {**start(docs), "information_requests": requests}
    return runner.run_blocks(
        {
            "config": config,
            "blocks": [V8_BLOCK],
            "case_id": CASE,
            "evidence": {"snapshots": {"start": start(docs) if with_start else None, "end": end}},
            "reference": {"request_type": request_type},
            "expected_values_from": "case_reference",
        }
    )


def party_line(out):
    return next(ln for ln in out["block_lines"] if ln["kind"] == "request_party")


def req(pid, kind="id_document"):
    return {"request_id": f"r-{pid}", "type": kind, "party_id": pid}


# --- who lacks the item (party rules 2) -------------------------------------------------------------------------------


def test_a_name_that_differs_from_the_id_document_lacks_a_valid_id():
    docs = with_doc(2, name_on_document="Rowan Lindqvist")
    assert runner.lacking("id_document", PARTIES, docs, APP, rules=2) == {"p2"}
    # Party rules 1 (D-041 as written) could not tell: the reason the check went blind on untagged cases.
    assert runner.lacking("id_document", PARTIES, docs, APP) == set()


def test_expired_and_missing_ids_still_count_and_combine():
    expired = with_doc(0, expires_on="2026-10-01")
    assert runner.lacking("id_document", PARTIES, expired, APP, rules=2) == {"p1"}
    missing = [d for d in GOOD if d["document_id"] != "p2-government_id"]
    assert runner.lacking("id_document", PARTIES, missing, APP, rules=2) == {"p2"}
    both = [
        d for d in with_doc(0, expires_on="2026-10-01") if d["document_id"] != "p2-government_id"
    ]
    assert runner.lacking("id_document", PARTIES, both, APP, rules=2) == {"p1", "p2"}


def test_a_clean_record_shows_no_party():
    assert runner.lacking("id_document", PARTIES, GOOD, APP, rules=2) == set()


def test_tin_and_proof_of_address_rules_are_unchanged():
    no_poa = [d for d in GOOD if d["document_id"] != "p2-proof_of_address"]
    assert runner.lacking("proof_of_address", PARTIES, no_poa, APP, rules=2) == {"p2"}
    assert runner.lacking("street_address", PARTIES, GOOD, APP, rules=2) is None


# --- the check ----------------------------------------------------------------------------------------------------------


def test_the_right_party_passes_and_the_wrong_party_fails():
    docs = with_doc(2, name_on_document="Rowan Lindqvist")
    assert run(docs, [req("p2")])["verdict"] == "pass"
    out = run(docs, [req("p1")])
    assert out["verdict"] == "fail"
    assert party_line(out)["expected"] == {"party_lacking": ["p2"]}
    assert party_line(out)["actual"] == {"requested_for": ["p1"], "wrong_party": ["p1"]}


def test_a_request_to_a_party_who_has_the_item_is_a_wrong_call_even_beside_the_right_one():
    docs = with_doc(2, name_on_document="Rowan Lindqvist")
    out = run(docs, [req("p2"), req("p1")])
    assert out["verdict"] == "fail"
    assert party_line(out)["actual"]["wrong_party"] == ["p1"]


def test_every_party_lacking_an_id_must_be_asked():
    both = [
        d for d in with_doc(0, expires_on="2026-10-01") if d["document_id"] != "p2-government_id"
    ]
    assert run(both, [req("p1")])["verdict"] == "fail"
    assert run(both, [req("p1"), req("p2")])["verdict"] == "pass"


def test_proof_of_address_is_application_level_one_lacking_party_is_enough():
    none = [d for d in GOOD if d["kind"] != "proof_of_address"]
    assert run(none, [req("p1", "proof_of_address")], "proof_of_address")["verdict"] == "pass"


def test_when_the_records_show_no_party_the_party_is_not_guessed():
    out = run(GOOD, [req("p1")])
    assert out["verdict"] == "pass"  # the type check decides
    line = party_line(out)
    assert line["verdict"] == "pass"
    assert "not determinable" in line["expected"]
    assert line["actual"] == {"requested_for": ["p1"]}


def test_missing_start_state_is_still_blocked():
    assert run(GOOD, [req("p1")], with_start=False)["verdict"] == "blocked"


def test_party_rules_1_behave_exactly_as_before():
    d041 = {**FIX, "extra_blocks": [fixes.REQUEST_PARTY_V1]}
    docs = with_doc(2, name_on_document="Rowan Lindqvist")
    # Rules 1 can't see the name mismatch: blocked, as D-041 was written.
    assert run(docs, [req("p1")], config=d041)["verdict"] == "blocked"
    assert "party_rules" not in fixes.REQUEST_PARTY_V1


# --- the suggested fix version ---------------------------------------------------------------------------------------------


def test_the_suggested_fix_is_party_rules_2_with_d062_regressions_and_qualifies():
    blk = FIX["extra_blocks"][0]
    assert blk["kind"] == "request_party" and blk["party_rules"] == 2
    names = {rc["name"] for rc in FIX["regression_cases"]}
    assert {
        "d041_minor_tin_requested_from_minor",
        "d041_minor_tin_requested_from_adult",
        "d041_no_start_state",
        "d062_name_mismatch_requested_from_that_party",
        "d062_name_mismatch_requested_from_the_other_party",
        "d062_extra_request_to_a_party_with_a_valid_id",
        "d062_party_not_determinable",
    } <= names
    blocks = [V8_BLOCK]
    cases = verifier.known_cases(blocks, "case_reference")
    checks = evaluators.block_case_checks(FRAMEWORK, FIX, blocks, cases, "case_reference")
    regressions = {rc["name"]: {**rc, "slots": {}} for rc in FIX["regression_cases"]}
    checks += evaluators.block_case_checks(FRAMEWORK, FIX, blocks, regressions, "case_reference")
    assert [c["result"] for c in checks] == ["pass"] * len(checks), checks


def test_the_fix_is_a_new_version_never_a_rewrite():
    src = inspect.getsource(evaluators.create_fix_version)
    assert "latest + 1" in src and "UPDATE catalog.evaluator_configurations SET config" not in src


# --- the reference agent and E-007 assertions share the rules --------------------------------------------------------------


def test_assertions_apply_the_same_party_rules_independently():
    docs = with_doc(2, name_on_document="Rowan Lindqvist")
    bundle = {"case_id": CASE, "snapshots": {"start": start(docs)}}
    assert assertions.party_lacking("id_document", bundle) == {"p2"}
    end = {**start(docs), "information_requests": [req("p1")]}
    res = assertions.request_party(
        {**bundle, "snapshots": {"start": start(docs), "end": end}}, {"request_type": "id_document"}
    )
    assert res["outcome"] == "FAIL"
    # Independent of the grader (E-007): its own copy of the rules, never an import of anvil.rlgym.scoring.
    assert "anvil.rlgym.scoring" not in inspect.getsource(assertions).split('"""', 2)[2]


def _drive(docs, request_type="id_document"):
    from anvil.rlgym.verification import reference

    actor = {
        "sections": {
            "S3": {
                "tools": [
                    "application.read",
                    "documents.list",
                    "document.read",
                    "information.request",
                    "recommend",
                    "parties.list",
                ]
            },
            "S5": {
                "steps": [
                    {"tool": "application.read"},
                    {"tool": "documents.list"},
                    {"tool": "document.read"},
                    {"tool": "information.request"},
                    {"tool": "recommend"},
                ]
            },
        }
    }
    ref = {
        "request_type": request_type,
        "recommendation": "request_information",
        "referral": "none",
    }
    failures, calls = [], []
    gen = reference.agent(actor, ref, CASE, failures)
    obs = None
    by_party = {p["party_id"]: [d for d in docs if d["party_id"] == p["party_id"]] for p in PARTIES}
    while True:
        step = gen.send(obs) if calls else next(gen)
        if "final" in step:
            break
        calls.append(step)
        tool, args = step["tool"], step["args"]
        if tool == "application.read":
            obs = {"ok": True, "output": {"records": [{**APP, "revision": 1}]}}
        elif tool == "parties.list":
            obs = {"ok": True, "output": {"records": PARTIES}}
        elif tool == "documents.list":
            obs = {"ok": True, "output": {"records": by_party[args["party_id"]]}}
        else:
            obs = {"ok": True, "output": {"records": []}}
    return [c["args"]["party_id"] for c in calls if c["tool"] == "information.request"], failures


def test_the_reference_agent_asks_the_party_the_records_show():
    asked, failures = _drive(with_doc(2, name_on_document="Rowan Lindqvist"))
    assert asked == ["p2"] and failures == []
    both = [
        d for d in with_doc(0, expires_on="2026-10-01") if d["document_id"] != "p2-government_id"
    ]
    asked, failures = _drive(both)
    assert asked == ["p1", "p2"] and failures == []


def test_the_reference_agent_says_so_when_the_records_show_no_party():
    asked, failures = _drive(GOOD)
    assert len(asked) == 1
    assert any("don't show which party lacks" in f["reason"] for f in failures)
