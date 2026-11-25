"""G4 (E-011 §3, Judgment v1 §10a.1): the no-AI lookup baseline as a verification check. A fixed decision table over
the case's records (no model) is played through each task's procedure and scored by the project's graders against the
true references. The benchmark needs reasoning only if the lookup scores at or below the gate (default 60%,
configurable per lookup run). Shadow mode: the row reports, it blocks nothing."""

import inspect
from pathlib import Path

import pytest

from anvil.rlgym.common import GymError
from anvil.rlgym.verification import lookup
from anvil.rlgym.verification import service as verification

CASE = "kyc-teen-joint-001"


def snap(**over):
    parties = [
        {"party_id": "p1", "application_id": CASE, "role": "primary", "full_name": "Ann Lee"},
        {"party_id": "p2", "application_id": CASE, "role": "minor", "full_name": "Kit Lee"},
    ]
    docs = [
        {
            "document_id": "d1",
            "party_id": "p1",
            "kind": "government_id",
            "content": {"name_on_document": "Ann Lee", "expires_on": "2030-01-01", "tin": "123"},
        },
        {"document_id": "d2", "party_id": "p1", "kind": "proof_of_address", "content": {}},
        {
            "document_id": "d3",
            "party_id": "p2",
            "kind": "government_id",
            "content": {"name_on_document": "Kit Lee", "expires_on": "2030-01-01", "tin": "456"},
        },
    ]
    s = {
        "applications": [{"application_id": CASE, "submitted_at": "2026-10-15T14:00:00Z"}],
        "parties": parties,
        "documents": docs,
    }
    for k, v in over.items():
        s[k] = v(s) if callable(v) else v
    return s


def with_content(i, **content):
    def f(s):
        docs = [dict(d, content=dict(d["content"])) for d in s["documents"]]
        docs[i]["content"].update(content)
        return docs

    return f


def decide(s):
    d = lookup.LOOKUPS["golden-kyc-openenv"](CASE, s)
    return d["request_type"], d["recommendation"], d["referral"]


def test_the_kyc_lookup_is_the_published_decision_table():
    assert decide(snap()) == ("none", "ready_for_approval", "none")
    assert decide(snap(documents=with_content(2, name_on_document="Kit Smith")))[:2] == (
        "id_document",
        "request_information",
    )
    assert decide(snap(documents=with_content(0, expires_on="2026-01-01")))[0] == "id_document"
    assert (
        decide(
            snap(documents=lambda s: [d for d in s["documents"] if d["kind"] != "proof_of_address"])
        )[0]
        == "proof_of_address"
    )
    assert decide(snap(documents=with_content(2, tin="missing")))[0] == "tin"
    hit = snap(
        documents=lambda s: (
            s["documents"]
            + [{"document_id": "d9", "party_id": "p1", "kind": "screening_result", "content": {}}]
        )
    )
    assert decide(hit) == ("none", "specialist_review", "sanctions")


def test_a_lookup_is_chosen_by_environment_and_none_means_not_measured():
    assert lookup.lookup_for("golden-kyc-openenv@12") is lookup.LOOKUPS["golden-kyc-openenv"]
    assert lookup.lookup_for("kyc-judgment-openenv@1") is None


def test_the_gate_threshold_defaults_to_60_and_is_validated():
    assert lookup.DEFAULT_THRESHOLD == 60
    assert lookup.threshold({}) == 60
    assert lookup.threshold({"threshold_percent": 45}) == 45
    for bad in (-1, 101, "x", None):
        if bad is None:
            continue
        with pytest.raises(GymError):
            lookup.threshold({"threshold_percent": bad})


def test_the_summary_counts_points_full_marks_and_right_decisions():
    rows = [
        {"points": "25/25", "full_marks": True, "decision_right": True},
        {"points": "15/25", "full_marks": False, "decision_right": False},
    ]
    s = lookup.summarize(rows, 60)
    assert s["points_percent"] == 80.0
    assert s["full_marks"] == 1 and s["cases"] == 2 and s["decisions_right"] == 1
    assert s["gate"] == {"threshold_percent": 60, "passed": False}
    assert lookup.summarize(rows, 85)["gate"]["passed"] is True


def test_the_verification_row():
    none = verification.lookup_row(None, "golden-kyc-openenv@12")
    assert none["id"] == "G-01" and none["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert "Run lookup baseline" in none["detail"]
    na = verification.lookup_row(None, "kyc-judgment-openenv@1")
    assert na["outcome"] == "INSUFFICIENT_EVIDENCE" and "no lookup" in na["detail"]
    high = {
        "id": "lb-1",
        "summary": lookup.summarize(
            [{"points": "24/25", "full_marks": False, "decision_right": True}], 60
        ),
    }
    assert verification.lookup_row(high, "golden-kyc-openenv@12")["outcome"] == "FAIL"
    low = {
        "id": "lb-2",
        "summary": lookup.summarize(
            [{"points": "10/25", "full_marks": False, "decision_right": False}], 60
        ),
    }
    out = verification.lookup_row(low, "golden-kyc-openenv@12")
    assert out["outcome"] == "PASS" and "40%" in out["detail"] and "60%" in out["detail"]
    assert "lookup_row(" in inspect.getsource(verification.build)


def test_storage_is_an_additive_append_only_table():
    sql = (Path(__file__).resolve().parents[2] / "migrations/067_rlgym_lookup_runs.sql").read_text()
    assert "CREATE TABLE verification.lookup_runs" in sql
    assert "forbid_change" in sql and "ROW LEVEL SECURITY" in sql
    assert "GRANT SELECT, INSERT ON verification.lookup_runs TO anvil_app" in sql
    for word in ("DROP", "ALTER TABLE verification.reference", "DELETE FROM"):
        assert word not in sql
    assert not any(line.lstrip().upper().startswith("UPDATE") for line in sql.splitlines())


def test_the_run_plays_the_lookup_through_the_procedure_and_scores_against_the_truth():
    src = inspect.getsource(lookup.run)
    assert "reference_run._episode" in src and "reference_run._score" in src
    # The lookup's decision drives the episode; the score is always against the true reference.
    assert "_score(c, ws, project, evaluators, t, ep, truth)" in src
    from anvil.rlgym.suites import routes

    assert "lookup-run" in inspect.getsource(routes)
