"""T06 real dedicated PostgreSQL/API/filesystem checks, fictional local inputs only."""

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from test_benchmark_pipeline import login
from test_private_storage import assign, connection
from test_private_storage import lab as storage_lab

from anvil.benchmark_evaluation import PROGRAM, canonical, seal
from anvil.benchmark_evaluator_worker import claim, finish, prepare_job, process_job, scoped
from anvil.benchmark_storage import bind_private, read_private, stage_private
from anvil.db import transaction

lab = storage_lab


def policy():
    return {
        "profile": "anvil-fictional-numeric-v1",
        "task_id": "FX-T06",
        "origin": "original_synthetic_fixture",
        "criteria": [
            {
                "id": "fx-number",
                "possible_points": "2",
                "path": "report.json",
                "field": "value",
                "expected": "10",
                "absolute_tolerance": "0.5",
                "relative_tolerance": "0",
                "kind": "numeric",
            }
        ],
    }


@contextmanager
def evaluator():
    with connection("anvil_benchmark_evaluator") as c:
        yield c


@pytest.fixture
def case(lab):
    assignment = assign(lab, "admin", scope="evaluation_review")
    assign(lab, "engineer", scope="evaluation_review")
    p = stage_private(lab["project"], canonical(policy()), "benchmark_eval")
    e = stage_private(
        lab["project"],
        b"Human scoped fictional deterministic evaluator review evidence; no paid authority",
        "benchmark_eval",
    )
    s = stage_private(
        lab["project"],
        canonical(seal({"report.json": b'{"value":10}'}, [], task_id="FX-T06")),
        "benchmark_sealed",
    )
    with transaction(lab["project"], lab["admin"]) as c:
        ids = [bind_private(c, item, created_by=lab["admin"]) for item in (p, e, s)]
    client = login(lab, "admin")
    engineer = login(lab, "engineer")
    base = "/api/v1/projects/" + lab["project"] + "/workspace/benchmarks"
    review = client.post(
        base + "/evaluators/reviews",
        json={
            "policy_artifact_id": ids[0],
            "evidence_artifact_id": ids[1],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
    )
    assert review.status_code == 200, review.text
    registry = review.json()["data"]["registry_id"]
    client.headers["idempotency-key"] = uuid4().hex
    body = {"registry_id": registry, "sealed_output_artifact_id": ids[2]}
    response = client.post(base + "/evaluations", json=body)
    assert response.status_code == 202, response.text
    yield {
        "lab": lab,
        "client": client,
        "engineer": engineer,
        "base": base,
        "registry": registry,
        "job": response.json()["data"]["job_id"],
        "body": body,
        "assignment": assignment,
        "policy_id": ids[0],
        "output_id": ids[2],
    }
    client.close()
    engineer.close()


def execute(job):
    result = subprocess.run(
        [sys.executable, str(PROGRAM)],
        input=canonical(job),
        capture_output=True,
        timeout=5,
        env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0
    return result.stdout


def get_claim(case):
    with evaluator() as c:
        return claim(c, case["lab"]["project"], case["job"])


def test_real_queue_scope_separate_program_and_private_result(case):
    assert (
        case["client"]
        .post(case["base"] + "/evaluations", json=case["body"])
        .json()["data"]["job_id"]
        == case["job"]
    )
    result = process_job(evaluator, case["lab"]["project"], case["job"], execute)
    assert result == {"state": "finished", "evaluation_state": "evaluated"}
    status = case["engineer"].get(case["base"] + "/evaluations/" + case["job"])
    assert status.status_code == 200
    assert status.json()["data"]["evaluation_state"] == "evaluated"
    assert not any(
        key in status.text
        for key in ("expected", "report.json", "report_artifact_id", "lease_token", "private")
    )
    with connection() as c:
        row = c.execute(
            "SELECT * FROM anvil.benchmark_evaluation_results WHERE job_id=%s", (case["job"],)
        ).fetchone()
    with transaction(case["lab"]["project"], case["lab"]["admin"]) as c:
        data = read_private(c, row["report_artifact_id"])
        assert hashlib.sha256(data).hexdigest() == row["report_sha256"]
        assert json.loads(data)["total_points"] == "2"
    assert (
        case["client"]
        .get(
            "/api/v1/projects/"
            + case["lab"]["project"]
            + "/artifacts/"
            + str(row["report_artifact_id"])
            + "/content"
        )
        .status_code
        == 403
    )
    assert (
        process_job(evaluator, case["lab"]["project"], case["job"], execute)["state"]
        == "not_claimed"
    )


def test_claim_has_no_wildcard_and_duplicate_claim_is_atomic(case):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: get_claim(case), range(2)))
    assert sum(r is not None for r in results) == 1
    claimed = next(r for r in results if r)
    with evaluator() as c:
        assert c.execute("SELECT * FROM anvil.artifacts").fetchall() == []
        scoped(c, claimed)
        assert {str(r["id"]) for r in c.execute("SELECT * FROM anvil.artifacts")} == {
            case["policy_id"],
            case["output_id"],
        }
        c.execute("SELECT set_config('anvil.benchmark_fence',%s,true)", (str(uuid4()),))
        assert c.execute("SELECT * FROM anvil.artifacts").fetchall() == []
    for role in ("anvil_app", "anvil_worker"):
        with connection(role, case["lab"]["project"], case["lab"]["admin"]) as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(
                    "SELECT * FROM anvil.claim_benchmark_evaluation(%s,%s)",
                    (case["lab"]["project"], case["job"]),
                )


@pytest.mark.parametrize(
    "fault", ["revoked", "expired", "cancelled", "forged_report", "foreign_project"]
)
def test_late_forged_or_cross_project_result_cannot_be_captured(case, fault):
    claimed = get_claim(case)
    job = prepare_job(evaluator, claimed)
    report = json.loads(execute(job))
    if fault == "revoked":
        with connection() as c:
            c.execute(
                "INSERT INTO anvil.benchmark_private_revocations(project_id,assignment_id,revoked_by,rationale) VALUES(%s,%s,%s,'Fictional revoke during evaluation')",
                (case["lab"]["project"], case["assignment"], case["lab"]["admin"]),
            )
    elif fault == "expired":
        with connection() as c:
            c.execute(
                "UPDATE anvil.benchmark_evaluator_jobs SET lease_until=now()-interval '1 second' WHERE id=%s",
                (case["job"],),
            )
    elif fault == "cancelled":
        case["client"].headers["idempotency-key"] = uuid4().hex
        assert (
            case["client"]
            .post(case["base"] + "/evaluations/" + case["job"] + "/cancel")
            .status_code
            == 200
        )
    elif fault == "forged_report":
        report["criteria"][0]["earned_points"] = "0"
    else:
        claimed["project_id"] = case["lab"]["other_project"]
    with pytest.raises((PermissionError, ValueError)):
        finish(evaluator, claimed, job, report)
    with connection() as c:
        rows = c.execute(
            "SELECT * FROM anvil.benchmark_evaluation_results WHERE job_id=%s", (case["job"],)
        ).fetchall()
    assert len(rows) == (1 if fault == "cancelled" else 0)
    if rows:
        assert rows[0]["status"] == "cancelled"


def test_api_defaults_off_cross_project_and_input_data_is_not_downloadable(case, monkeypatch):
    monkeypatch.delenv("ANVIL_BENCHMARK_EVALUATION_ENABLED")
    case["client"].headers["idempotency-key"] = uuid4().hex
    assert case["client"].post(case["base"] + "/evaluations", json=case["body"]).status_code == 503
    outsider = login(case["lab"], "outsider")
    try:
        assert outsider.get(case["base"] + "/evaluations/" + case["job"]).status_code in (403, 404)
        other = (
            "/api/v1/projects/"
            + case["lab"]["other_project"]
            + "/workspace/benchmarks/evaluations/"
            + case["job"]
        )
        assert outsider.get(other).status_code == 404
    finally:
        outsider.close()


def test_worker_is_not_a_db_admin_or_general_private_reader(case):
    with evaluator() as c:
        row = c.execute(
            "SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert not any(row.values())
        for table in ("users", "benchmark_evaluation_results"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with c.transaction():
                    c.execute("INSERT INTO anvil." + table + " DEFAULT VALUES")
        assert c.execute("SELECT * FROM anvil.benchmark_evaluator_jobs").fetchall() == []
