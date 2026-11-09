"""Manufactured capture metadata tests real SQL/results, NEVER native qualification.

No actor/provider/evaluator is run here. Deliberately seeded zero-point reports
verify custody/finalization/score/review transactions in the disposable test lab.
"""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException
from test_benchmark_pipeline import login
from test_benchmark_pipeline import signed_lab as pipeline_lab
from test_benchmark_scheduler_security import actor_connection, launch
from test_benchmark_scheduler_security import frozen as scheduler_frozen
from test_private_storage import connection
from test_private_storage import lab as storage_lab

from anvil import benchmark_results as results
from anvil import benchmark_scheduler as scheduler
from anvil.benchmark_evaluator_program import canonical, seal
from anvil.benchmark_offline_worker import finalize
from anvil.benchmark_storage import bind_private, stage_private
from anvil.db import uid
from anvil.domain import get_revision

lab = storage_lab
signed_lab = pipeline_lab
frozen = scheduler_frozen


@contextmanager
def evaluator():
    with connection("anvil_benchmark_evaluator") as c:
        yield c


def manufactured_capture(case, run, *, omitted=(), empty=(), credit=0):
    with actor_connection(case) as c:
        claimed = scheduler.claim(c, case["lab"]["project"], run)
        assert claimed
        scheduler.intent(c, case["lab"]["project"], claimed)
        task = get_revision(c, claimed["task_revision_id"], "task")["content"]
    report = {
        "criteria": {criterion["id"]: credit for criterion in task["criteria"]},
        "fixture_notice": "MANUFACTURED SQL METADATA: NO NATIVE EXECUTION",
    }
    files = {"answers.json": b"{}", "report.md": b"Manufactured SQL custody fixture"}
    files = {
        path: b"" if path in empty else data for path, data in files.items() if path not in omitted
    }
    output = seal(
        files,
        list(omitted),
        task_id=task["task_id"],
    )
    prepared_report = stage_private(
        case["lab"]["project"], canonical(report), "benchmark_trace", "application/json"
    )
    prepared_output = stage_private(
        case["lab"]["project"], canonical(output), "benchmark_sealed", "application/json"
    )
    prepared_files = {
        path: stage_private(case["lab"]["project"], data, "benchmark_sealed")
        for path, data in files.items()
    }
    with actor_connection(case) as c:
        report_id = bind_private(c, prepared_report, created_by=case["lab"]["admin"])
        output_id = bind_private(c, prepared_output, created_by=case["lab"]["admin"])
        c.execute(
            "UPDATE anvil.benchmark_offline_runtime SET state='captured',report_artifact_id=%s,output_artifact_id=%s,duration_ms=12 WHERE attempt_id=%s",
            (report_id, output_id, claimed["attempt_id"]),
        )
        c.execute(
            "INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence,sealed_output_artifact_id) VALUES(%s,%s,%s,'collecting','pending',%s,%s)",
            (uid(), case["lab"]["project"], claimed["attempt_id"], claimed["fence"], output_id),
        )
        from anvil.benchmark_offline_worker import record_outputs

        record_outputs(
            c,
            case["lab"]["project"],
            case["lab"]["admin"],
            claimed,
            output_id,
            task["outputs"],
            prepared_files,
        )
    return claimed


@pytest.mark.parametrize(
    "omitted,empty,credit,validity",
    [
        (("answers.json",), (), 0, "valid"),
        ((), ("answers.json",), 0, "valid"),
        (("report.md",), (), 1, "unresolved"),
        ((), ("report.md",), 1, "unresolved"),
    ],
)
def test_missing_output_uses_only_declared_criterion_policy(
    frozen, omitted, empty, credit, validity
):
    case = frozen
    run = launch(case).json()["data"]["run_id"]
    claimed = manufactured_capture(case, run, omitted=omitted, empty=empty, credit=credit)
    assert (
        finalize(case["lab"]["project"], case["lab"]["admin"], claimed, evaluator_connect=evaluator)
        == "completed"
    )
    with actor_connection(case) as c:
        event = c.execute(
            "SELECT validity FROM anvil.benchmark_attempt_events WHERE attempt_id=%s ORDER BY event_seq DESC LIMIT 1",
            (claimed["attempt_id"],),
        ).fetchone()
        assert event["validity"] == validity
        policy = c.execute(
            "SELECT hard_constraint_ids,unresolved_required_paths FROM anvil.benchmark_attempt_policy_outcomes WHERE attempt_id=%s",
            (claimed["attempt_id"],),
        ).fetchone()
        assert policy["hard_constraint_ids"] == []
        assert policy["unresolved_required_paths"] == (
            ["report.md"] if validity == "unresolved" else []
        )
        observations = c.execute(
            "SELECT r.earned_points,r.output_sha256,r.absence_event_id FROM anvil.benchmark_criterion_results r JOIN anvil.benchmark_evaluator_calls ec ON ec.id=r.evaluator_call_id WHERE ec.attempt_id=%s",
            (claimed["attempt_id"],),
        ).fetchall()
        assert all(row["earned_points"] == credit for row in observations)
        if "answers.json" in omitted or "answers.json" in empty:
            assert all(
                row["absence_event_id"] and row["output_sha256"] is None for row in observations
            )
        stored = results.latest(c, run)
        assert all(model["primary"] is None for model in stored["projection"]["models"])


def test_captured_restart_finalizes_exactly_once_and_keeps_incomplete_primary_null(frozen):
    case = frozen
    run = launch(case).json()["data"]["run_id"]
    claimed = manufactured_capture(case, run)
    assert (
        finalize(case["lab"]["project"], case["lab"]["admin"], claimed, evaluator_connect=evaluator)
        == "completed"
    )
    with pytest.raises(HTTPException) as error:
        finalize(case["lab"]["project"], case["lab"]["admin"], claimed, evaluator_connect=evaluator)
    assert error.value.status_code == 409
    with actor_connection(case) as c:
        stored = results.latest(c, run)
        assert not stored["projection"]["complete"]
        assert all(model["primary"] is None for model in stored["projection"]["models"])
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.benchmark_evaluator_calls WHERE attempt_id=%s",
                (claimed["attempt_id"],),
            ).fetchone()["n"]
            == 1
        )
        assert (
            c.execute(
                "SELECT state FROM anvil.benchmark_capacity_claims WHERE attempt_id=%s",
                (claimed["attempt_id"],),
            ).fetchone()["state"]
            == "released"
        )
        before = stored["score_revision_id"]
        assert (
            results.publish(c, case["lab"]["project"], case["lab"]["admin"], run)[
                "score_revision_id"
            ]
            == before
        )


def test_all_eighteen_valid_zeroes_are_complete_and_exports_use_same_stored_revision(frozen):
    case = frozen
    run = launch(case).json()["data"]["run_id"]
    for _ in range(18):
        claimed = manufactured_capture(case, run)
        finalize(case["lab"]["project"], case["lab"]["admin"], claimed, evaluator_connect=evaluator)
    response = case["admin"].get(case["base"] + "/comparisons/" + run + "/results")
    assert response.status_code == 200, response.text
    stored = response.json()["data"]
    assert stored["projection"]["execution_complete"] and not stored["projection"]["complete"]
    assert all(model["primary"] is None for model in stored["projection"]["models"])
    assert all(
        model["diagnostic"]["complete_repetition_mean"]
        == {"earned_points": "0", "possible_points": "81", "percent": "0.00"}
        for model in stored["projection"]["models"]
    )
    assert all(
        model["duration"] == {"median_ms": 12, "samples": 6}
        for model in stored["projection"]["models"]
    )
    # Real stored SQL fixture projection, not native execution or a user demo.
    dashboard = case["admin"].get(case["base"] + "/dashboard", params={"run_id": run})
    assert dashboard.status_code == 200, dashboard.text
    overview = dashboard.json()["data"]["overview"]
    assert overview["model_trace_count"] == 0 and overview["control_trace_count"] == 18
    assert len(dashboard.json()["data"]["traces"]) == 18
    assert all(row["kind"] == "comparison_cell" for row in dashboard.json()["data"]["traces"])
    assert overview["ranked_models"] == 0 and overview["leader"] is None
    assert all(row["primary"] is None for row in overview["models"])
    assert all(row["diagnostic"]["earned_points"] == "0" for row in overview["models"])
    assert overview["ranking"]["observed_win_rate"]["pair_count"] == 0
    trace = dashboard.json()["data"]["traces"][0]
    detail = case["admin"].get(
        case["base"] + "/dashboard/traces/" + trace["id"], params={"run_id": run}
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["outputs"] and detail.json()["data"]["criteria"]
    json_export = case["admin"].get(case["base"] + "/comparisons/" + run + "/exports/json")
    assert json_export.status_code == 200 and json_export.json() == stored
    csv_export = case["admin"].get(case["base"] + "/comparisons/" + run + "/exports/csv")
    assert csv_export.status_code == 200 and stored["score_revision_id"] in csv_export.text
    assert "expected" not in json_export.text and "private_canary" not in json_export.text
    # Review is a real human command with frozen duty and exact evidence binding.
    policy = case["protocol_body"]["review_policy"]
    body = {
        "score_revision_id": stored["score_revision_id"],
        "expected_projection_sha256": stored["projection_sha256"],
        "assignment_id": policy["first_assignment_id"],
        "decision": "approved",
        "evidence_sha256": stored["projection_sha256"],
        "rationale": "Explicit fictional SQL review evidence, not human release approval",
    }
    review = case["admin"].post(
        case["base"] + "/comparisons/" + run + "/reviews",
        json=body,
        headers={"idempotency-key": str(uuid4())},
    )
    assert review.status_code == 200, review.text
    required = stored["projection"]["review_requirements"]["second_required"]
    assert review.json()["data"]["review_state"] == (
        "second_review_required" if required else "approved"
    )
    if required:
        second_body = {**body, "assignment_id": policy["second_assignment_id"]}
        review = case["client"].post(
            case["base"] + "/comparisons/" + run + "/reviews",
            json=second_body,
            headers={"idempotency-key": str(uuid4())},
        )
        assert review.status_code == 200, review.text
    approved = review.json()["data"]
    assert approved["score_revision_id"] != stored["score_revision_id"]
    assert approved["review_state"] == "approved" and approved["projection"]["complete"]
    assert all(
        model["primary"] == {"earned_points": "0", "possible_points": "81", "percent": "0.00"}
        for model in approved["projection"]["models"]
    )
    reviewed = case["admin"].get(
        case["base"] + "/dashboard",
        params={"run_id": run, "score_revision_id": approved["score_revision_id"]},
    )
    assert reviewed.status_code == 200, reviewed.text
    reviewed_overview = reviewed.json()["data"]["overview"]
    assert (
        reviewed_overview["ranked_models"] == 0 and reviewed_overview["control_trace_count"] == 18
    )
    assert reviewed_overview["leader"] is None
    assert all(
        not row["ranking_eligible"] and row["measurement_notice"]
        for row in reviewed_overview["models"]
    )
    assert all(not row["official"] for row in reviewed.json()["data"]["traces"])
    assert all(row["primary"]["earned_points"] == "0" for row in reviewed_overview["models"])
    with actor_connection(case) as c:
        assert (
            results.publish(c, case["lab"]["project"], case["lab"]["admin"], run)[
                "score_revision_id"
            ]
            == approved["score_revision_id"]
        )
    changed = {**body, "evidence_sha256": "f" * 64}
    invalid = case["admin"].post(
        case["base"] + "/comparisons/" + run + "/reviews",
        json=changed,
        headers={"idempotency-key": str(uuid4())},
    )
    assert invalid.status_code == 409


def test_assigned_adjudicator_correction_creates_successor_without_mutating_native_points(frozen):
    case = frozen
    run = launch(case).json()["data"]["run_id"]
    claimed = manufactured_capture(case, run)
    finalize(case["lab"]["project"], case["lab"]["admin"], claimed, evaluator_connect=evaluator)
    with actor_connection(case) as c:
        stored = results.latest(c, run)
        native = c.execute(
            "SELECT cr.criterion_id,cr.output_sha256 FROM anvil.benchmark_criterion_results cr JOIN anvil.benchmark_evaluator_calls ec ON ec.project_id=cr.project_id AND ec.id=cr.evaluator_call_id WHERE ec.attempt_id=%s ORDER BY cr.criterion_id LIMIT 1",
            (claimed["attempt_id"],),
        ).fetchone()
    policy = case["protocol_body"]["review_policy"]
    body = {
        "score_revision_id": stored["score_revision_id"],
        "expected_projection_sha256": stored["projection_sha256"],
        "assignment_id": policy["first_assignment_id"],
        "decision": "disputed",
        "evidence_sha256": stored["projection_sha256"],
        "rationale": "Original manufactured SQL correction workflow only",
    }
    response = case["admin"].post(
        case["base"] + "/comparisons/" + run + "/reviews",
        json=body,
        headers={"idempotency-key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    response = case["client"].post(
        case["base"] + "/comparisons/" + run + "/reviews",
        json={**body, "assignment_id": policy["second_assignment_id"], "decision": "approved"},
        headers={"idempotency-key": str(uuid4())},
    )
    assert (
        response.status_code == 200
        and response.json()["data"]["review_state"] == "adjudication_required"
    ), response.text
    adjudicator = login(case["lab"], "third")
    correction = {
        "score_revision_id": stored["score_revision_id"],
        "expected_projection_sha256": stored["projection_sha256"],
        "assignment_id": policy["adjudicator_assignment_id"],
        "rationale": "Explicit fictional adjudication, not native or human acceptance evidence",
        "corrections": [
            {
                "cell_id": str(claimed["cell_id"]),
                "criterion_id": native["criterion_id"],
                "earned_points": "1",
                "evidence_sha256": native["output_sha256"],
            }
        ],
    }
    response = adjudicator.post(
        case["base"] + "/comparisons/" + run + "/corrections",
        json=correction,
        headers={"idempotency-key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    successor = response.json()["data"]
    assert successor["score_revision_id"] != stored["score_revision_id"]
    assert successor["review_state"] == "pending" and not successor["projection"]["complete"]
    assert successor["projection"]["adjudications"][0]["earned_points"] == "1"
    with actor_connection(case) as c:
        assert (
            c.execute(
                "SELECT sum(cr.earned_points) n FROM anvil.benchmark_criterion_results cr JOIN anvil.benchmark_evaluator_calls ec ON ec.project_id=cr.project_id AND ec.id=cr.evaluator_call_id WHERE ec.attempt_id=%s",
                (claimed["attempt_id"],),
            ).fetchone()["n"]
            == 0
        )
        assert (
            results.publish(c, case["lab"]["project"], case["lab"]["admin"], run)[
                "score_revision_id"
            ]
            == successor["score_revision_id"]
        )
    stale = adjudicator.post(
        case["base"] + "/comparisons/" + run + "/corrections",
        json=correction,
        headers={"idempotency-key": str(uuid4())},
    )
    assert stale.status_code == 409
    adjudicator.close()
