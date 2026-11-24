"""E-007 phase 1 (shadow): the independent assertions never import the grader; the regression fixtures show the
phase 1 exit test (the Minor wrong-party fixture is a MISMATCH under next_action v1); checks name their outcome from
the five allowed; the report is made after a run completes without touching the run. No database, no Docker."""

import ast
import inspect
from pathlib import Path

from anvil.rlgym.runs import worker
from anvil.rlgym.verification import assertions, fixtures
from anvil.rlgym.verification import service as verification


def test_assertions_never_import_the_grader():
    tree = ast.parse(Path(assertions.__file__).read_text())
    names = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    names += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not [n for n in names if "scoring" in n], names


def test_exit_test_minor_wrong_party_is_a_mismatch_under_v1():
    rows = {r["id"]: r for r in verification.fixture_rows()}
    fx1 = rows["FX-1"]
    assert fx1["assertions"]["KYC.REQUEST_PARTY"] == "FAIL"
    assert fx1["next_action"] == {"v1": "pass", "v2_d041": "fail"} and fx1["v1_mismatch"] is True
    for fid in ("FX-2", "FX-3", "FX-4"):
        assert rows[fid]["v1_mismatch"] is False
        assert all(
            rows[fid]["assertions"][k] == v
            for k, v in fixtures.FIXTURES[int(fid[-1]) - 1]["expect"].items()
        )
    assert all(r["status"].startswith("awaiting SME") for r in rows.values())


def test_request_party_assertion_on_each_rule():
    fx = {f["id"]: f for f in fixtures.FIXTURES}
    assert assertions.party_lacking("tin", fx["FX-1"]["bundle"]) == {"p-minor"}
    assert assertions.party_lacking("id_document", fx["FX-3"]["bundle"]) == {"p-b"}
    assert assertions.party_lacking("proof_of_address", fx["FX-4"]["bundle"]) == {"p-s"}
    assert assertions.party_lacking("street_address", fx["FX-4"]["bundle"]) is None


def test_roster_reconciles_and_outcomes_are_the_five():
    eps = [
        {"id": "e1", "state": "scored", "bundle_ref": "b"},
        {"id": "e2", "state": "errored", "bundle_ref": None},
    ]
    assert verification.roster({"episodes": 2}, eps)["outcome"] == "PASS"
    bad = verification.roster({"episodes": 3}, eps)
    assert bad["outcome"] == "FAIL" and "plans 3" in bad["detail"]
    assert (
        verification.roster({"episodes": 0}, [])["outcome"] == "FAIL"
    )  # run-0229: admitted with nothing
    assert set(verification.WORDS) == set(verification.OUTCOMES)


def test_leakage_sees_labels_and_the_known_tin_leak_but_not_other_cases():
    obs = {"records": [{"document_id": "d-2", "content": {"tin": "missing"}}]}
    ep = {"id": "e1", "edge_cases": ["minor_without_tin"]}
    b = {"e1": {"transcript": [{"step": 1, "observation": obs}]}}
    got = verification.leakage({}, [ep], b, {"e1": {"request_type": "tin"}})
    assert got["outcome"] == "FAIL" and "known data leak" in got["detail"]
    clean = verification.leakage(
        {}, [{"id": "e1", "edge_cases": []}], b, {"e1": {"request_type": "none"}}
    )
    assert (
        clean["outcome"] == "PASS"
    )  # another case's missing TIN in a listing is not this case's answer
    tagged = {"e1": {"transcript": [{"step": 1, "observation": {"id": "kyc-x-passport-only-001"}}]}}
    assert (
        verification.leakage({}, [{"id": "e1", "edge_cases": ["passport_only"]}], tagged, {})[
            "outcome"
        ]
        == "FAIL"
    )


def test_report_is_made_after_a_completed_run_in_its_own_transaction():
    src = inspect.getsource(worker.finish_runs)
    assert 'verification.build(c, ws, run_id, requested_by="rlgym:after-run")' in src
    assert "except Exception:" in src and "the run is unaffected" in src
    build = inspect.getsource(verification.build)
    assert "INSERT INTO verification.reports" in build and "UPDATE" not in build
