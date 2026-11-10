"""Manufactured SQL qualification/capture fixture, never native or release evidence.

Exercises the existing official-comparison transaction path under v2 report
policy; no actor/provider is invoked and no human approval is manufactured.
"""

from copy import deepcopy
from uuid import uuid4

from test_benchmark_pipeline import signed_lab as pipeline_fixture
from test_benchmark_report_policy_security import configure
from test_benchmark_results import evaluator, manufactured_capture
from test_benchmark_scheduler_security import frozen as scheduler_fixture
from test_benchmark_scheduler_security import launch
from test_private_storage import connection
from test_private_storage import lab as storage_fixture

from anvil.benchmark_offline_worker import finalize

lab = storage_fixture
signed_lab = pipeline_fixture
frozen = scheduler_fixture


def v2(case):
    before = deepcopy(case["protocol"])
    body = deepcopy(case["protocol_body"])
    policy = body["review_policy"]
    body["review_policy"] = {
        "version": 2,
        "tasks": policy["tasks"],
        "calibration_sha256": policy["calibration_sha256"],
        "reviewer_assignment_ids": [],
    }
    response = case["admin"].post(
        case["base"] + "/protocols", json=body, headers={"idempotency-key": str(uuid4())}
    )
    assert response.status_code == 200, response.text
    protocol = response.json()["data"]
    assert protocol["protocol"]["review_policy"]["version"] == 2
    assert protocol["protocol"]["review_policy"]["reviewer_assignment_ids"] == []
    old = case["admin"].get(case["base"] + "/protocols/" + before["protocol_revision_id"])
    assert old.status_code == 200, old.text
    assert old.json()["data"]["subject_sha256"] == before["subject_sha256"]
    case["protocol"] = protocol
    return case


def test_v2_actual_admin_admission_releases_completed_task_primary_without_fake_legacy_reviews(
    frozen,
):
    configure(frozen["lab"], 4)
    case = v2(frozen)
    response = launch(case)
    assert response.status_code == 200, response.text
    run = response.json()["data"]["run_id"]
    for _ in range(18):
        claimed = manufactured_capture(case, run)
        finalize(case["lab"]["project"], case["lab"]["admin"], claimed, evaluator_connect=evaluator)
    response = case["admin"].get(case["base"] + "/comparisons/" + run + "/results")
    assert response.status_code == 200, response.text
    stored = response.json()["data"]
    assert stored["review_state"] == "admin_run_exempt"
    assert stored["projection"]["complete"]
    assert all(
        x["primary"] == {"earned_points": "0", "possible_points": "81", "percent": "0.00"}
        for x in stored["projection"]["models"]
    )
    basis = stored["projection"]["review_basis"]
    assert basis["decisions"] == [] and basis["reviewer_verified"] is False
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.benchmark_score_reviews r JOIN anvil.benchmark_score_revisions s ON s.id=r.score_revision_id WHERE s.run_id=%s",
                (run,),
            ).fetchone()["n"]
            == 0
        )
        authority = c.execute(
            "SELECT admin_run_exempt,actor_id FROM anvil.benchmark_report_authorizations WHERE target_kind='comparison' AND target_id=%s",
            (run,),
        ).fetchone()
        assert authority["admin_run_exempt"] and str(authority["actor_id"]) == case["lab"]["admin"]
        before = c.execute(
            "SELECT count(*) n FROM anvil.benchmark_score_revisions WHERE run_id=%s", (run,)
        ).fetchone()["n"]
        qualification = case["protocol"]["protocol"]["tasks"][0]["qualification_id"]
        c.execute(
            "INSERT INTO anvil.benchmark_qualification_events(id,project_id,qualification_id,decision,rationale,actor_id) VALUES(%s,%s,%s,'revoked','Post-capture manufactured qualification revocation',%s)",
            (str(uuid4()), case["lab"]["project"], qualification, case["lab"]["admin"]),
        )
    denied = case["admin"].post(
        case["base"] + "/comparisons/" + run + "/report-approval",
        headers={"idempotency-key": str(uuid4())},
        json={
            "expected_result_sha256": stored["projection_sha256"],
            "rationale": "Admin report approval must retain current qualification gates",
        },
    )
    assert denied.status_code == 409, denied.text
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.benchmark_score_revisions WHERE run_id=%s", (run,)
            ).fetchone()["n"]
            == before
        )
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.benchmark_report_decisions WHERE target_kind='comparison' AND target_id=%s",
                (run,),
            ).fetchone()["n"]
            == 0
        )


def test_admin_report_exemption_never_bypasses_current_qualification_gate(frozen):
    case = v2(frozen)
    qualification = case["protocol"]["protocol"]["tasks"][0]["qualification_id"]
    with connection() as c:
        c.execute(
            "INSERT INTO anvil.benchmark_qualification_events(id,project_id,qualification_id,decision,rationale,actor_id) VALUES(%s,%s,%s,'revoked','Explicit manufactured SQL qualification revocation',%s)",
            (str(uuid4()), case["lab"]["project"], qualification, case["lab"]["admin"]),
        )
    response = launch(case)
    assert response.status_code == 409, response.text
