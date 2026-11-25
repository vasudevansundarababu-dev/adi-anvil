"""D-041: next_action must check whose request it is. The fix is an RL Gym evaluator configuration version (runner
version 2, an extra request_party check) qualified by the usual known cases plus wrong-party regression fixtures."""

import inspect

from anvil.rlgym.catalog import evaluators, fixes, verifier
from anvil.rlgym.scoring import sandbox_runner as runner

FRAMEWORK = {
    "id": "fw-python-1.0.0",
    "runtime_id": "python",
    "installed_locally": True,
    "state": "qualified",
}
# golden-kyc v8's own next_action block (template tpl_x5rwt6d5eu v8).
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


def _run(case):
    return runner.run_blocks(
        {
            "config": FIX,
            "blocks": [V8_BLOCK],
            "case_id": case["case_id"],
            "evidence": case["evidence"],
            "reference": case["reference"],
            "expected_values_from": "case_reference",
        }
    )


def test_the_wrong_party_now_fails_and_the_right_party_passes():
    right, wrong, nostart = fixes.request_party_regressions()[:3]
    assert _run(right)["verdict"] == "pass"
    out = _run(wrong)
    assert out["verdict"] == "fail"
    line = next(ln for ln in out["block_lines"] if ln["block_id"] == "next_action.request_party")
    # D-062 (party rules 2) also names the wrong party.
    assert line["actual"] == {
        "requested_for": ["p-adult"],
        "wrong_party": ["p-adult"],
    } and line["expected"] == {"party_lacking": ["p-minor"]}
    # Before the fix (runner 1, template block only) the wrong-party request scored a pass: the bug.
    old = runner.run_blocks(
        {
            **{"config": {"runner": "verifier_blocks"}},
            "blocks": [V8_BLOCK],
            **{k: wrong[k] for k in ("case_id", "evidence", "reference")},
            "expected_values_from": "case_reference",
        }
    )
    assert old["verdict"] == "pass"
    assert _run(nostart)["verdict"] == "blocked"


def test_who_lacks_the_item_follows_the_edge_case_recipes():
    parties = [{"party_id": "a", "role": "primary"}, {"party_id": "b", "role": "joint"}]
    app = {"submitted_at": "2026-11-01"}
    docs = [
        {"party_id": "a", "kind": "government_id", "content": {"expires_on": "2027-01-01"}},
        {"party_id": "b", "kind": "government_id", "content": {"expires_on": "2026-10-01"}},
    ]
    assert runner.lacking("id_document", parties, docs, app) == {"b"}
    passports = [
        {"party_id": "a", "kind": "passport", "content": {}},
        {"party_id": "b", "kind": "passport", "content": {}},
        {"party_id": "b", "kind": "utility_bill", "content": {}},
    ]
    assert runner.lacking("proof_of_address", parties, passports, app) == {"a"}
    minors = [{"party_id": "m", "role": "minor"}, {"party_id": "a", "role": "primary"}]
    assert runner.lacking(
        "tin", minors, [{"party_id": "a", "kind": "x", "content": {"tin": "1"}}], app
    ) == {"m"}
    assert runner.lacking("street_address", parties, docs, app) is None  # no rule: not checked


def test_no_request_expected_is_not_a_party_question():
    case = fixes.request_party_regressions()[0]
    out = _run(
        {
            **case,
            "reference": {"request_type": "none"},
            "evidence": {
                "snapshots": {
                    "start": case["evidence"]["snapshots"]["start"],
                    "end": {"information_requests": []},
                }
            },
        }
    )
    assert out["verdict"] == "pass"


def test_the_fix_qualifies_on_v8_blocks_with_its_regressions():
    blocks = [V8_BLOCK]
    cases = verifier.known_cases(blocks, "case_reference")
    checks = evaluators.block_case_checks(FRAMEWORK, FIX, blocks, cases, "case_reference")
    regressions = {rc["name"]: {**rc, "slots": {}} for rc in FIX["regression_cases"]}
    checks += evaluators.block_case_checks(FRAMEWORK, FIX, blocks, regressions, "case_reference")
    assert [c["result"] for c in checks] == ["pass"] * len(checks), checks
    assert {c["name"] for c in checks} >= {
        "d041_minor_tin_requested_from_minor",
        "d041_minor_tin_requested_from_adult",
        "d041_no_start_state",
    }


def test_known_case_tests_run_regressions_and_studio_is_told():
    src = inspect.getsource(evaluators.run_known_case_tests)
    assert 'row["config"].get("regression_cases")' in src
    fix = inspect.getsource(evaluators.create_fix_version)
    assert '"fix_reason": reason' in fix and "fold into the next template version" in fix
    assert (
        fixes.suggested("golden-kyc-blocks:next_action", {"runner": "verifier_blocks"})["defect"]
        == "D-041, D-062"
    )
    assert fixes.suggested("golden-kyc-blocks:next_action", FIX) is None  # already the fix
