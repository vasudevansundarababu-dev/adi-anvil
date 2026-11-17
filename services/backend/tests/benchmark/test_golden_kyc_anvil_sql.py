"""Canonical Anvil import/run/report with actual SQL, SDK and local evaluators."""

import os
import secrets
import subprocess
import sys
from contextlib import contextmanager

import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from test_golden_kyc_sql import connection
from test_golden_kyc_sql import owned as owned_fixture

from anvil.db import digest
from anvil.golden_kyc_anvil import register, start

owned = owned_fixture


@pytest.fixture
def imported(owned):
    _, project, user, _, pack = owned
    with connection(owned) as c:
        c.execute(
            "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
            (project, user),
        )
        c.execute("SET LOCAL ROLE anvil_app")
        imported = register(c, project, user, pack, reusable=True)
    return owned, imported


def scoped(owned, role):
    @contextmanager
    def connections():
        with connection(owned) as c:
            c.execute(
                "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                (owned[1], owned[2]),
            )
            # Fixed roles, never caller-controlled SQL identifiers.
            c.execute(
                {
                    "scheduler": "SET LOCAL ROLE anvil_golden_scheduler",
                    "grader": "SET LOCAL ROLE anvil_golden_grader",
                    "app": "SET LOCAL ROLE anvil_app",
                }[role]
            )
            yield c

    return connections


def test_import_registers_five_state_tasks_shared200_cases_and50_evaluators(imported):
    owned, item = imported
    with scoped(owned, "app")() as c:
        assert item["binding_count"] == 5 and item["evaluator_count"] == 50
        group = c.execute(
            "SELECT content FROM anvil.benchmark_task_groups WHERE id=%s", (item["task_group_id"],)
        ).fetchone()
        assert len(group["content"]["tasks"]) == 5
        assert "intended_decision" not in str(group)
        assert "future_documents" not in str(group)
        assert register(c, owned[1], owned[2], owned[4], reusable=True)["id"] == item["id"]
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.environment_task_bindings WHERE environment_id=%s",
                (item["environment_id"],),
            ).fetchone()["n"]
            == 5
        )
        assert item["readiness"]["software_run"] == "ready"
        assert item["readiness"]["model_benchmark"] == "blocked"


def test_revoked_evaluator_blocks_new_run_without_rewriting_import(imported):
    owned, item = imported
    with scoped(owned, "app")() as c:
        identifier = item["manifest"]["evaluators"][0]["configuration_id"]
        c.execute(
            "INSERT INTO anvil.evaluator_revocations(id,project_id,configuration_id,created_by) VALUES(gen_random_uuid(),%s,%s,%s)",
            (owned[1], identifier, owned[2]),
        )
        with pytest.raises(Exception, match="Evaluator binding revoked or changed"):
            start(c, owned[1], owned[2], item["id"])


def test_anvil_sdk_run_separate_grade_and_standard_report(imported):
    from anvil import benchmark_run_views

    owned, item = imported
    with scoped(owned, "app")() as c:
        run = start(c, owned[1], owned[2], item["id"])
        assert run["planned_cells"] == 200
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_run_jobs WHERE run_id=%s",
                (run["run_id"],),
            ).fetchone()["n"]
            == 0
        )
    roles = []

    def worker(mode):
        grading = mode == "grade"
        login = "golden_qual_" + ("grader_" if grading else "scheduler_") + secrets.token_hex(5)
        password = secrets.token_urlsafe(32)
        capability = "anvil_golden_grader" if grading else "anvil_golden_scheduler"
        with connection(owned) as c:
            c.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS").format(
                    sql.Identifier(login), sql.Literal(password)
                )
            )
            c.execute(
                sql.SQL("GRANT {} TO {}").format(sql.Identifier(capability), sql.Identifier(login))
            )
        roles.append(login)
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            in {
                "PATH",
                "PYTHONPATH",
                "ANVIL_ROOT",
                "ANVIL_ENV",
                "WEB_ORIGIN",
                "ANVIL_LOCAL_WEB_PORT",
                "ANVIL_OPA_BINARY",
                "ANVIL_OPA_SHA256",
                "SYSTEMROOT",
                "LANG",
                "PGOPTIONS",
            }
        }
        env.update(
            ANVIL_GOLDEN_KYC_ENABLED="true",
            ANVIL_LIVE_PROVIDERS_ENABLED="false",
            ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED="false",
        )
        env[
            "ANVIL_GOLDEN_GRADER_DATABASE_URL" if grading else "ANVIL_GOLDEN_SCHEDULER_DATABASE_URL"
        ] = make_conninfo(str(owned[0]), user=login, password=password)
        result = subprocess.run(
            [
                os.environ.get("ANVIL_GOLDEN_COMPONENT_PYTHON", sys.executable),
                "-m",
                "anvil.golden_kyc_service",
                "--project",
                owned[1],
                "--role",
                "grader" if grading else "scheduler",
                "--max-cycles",
                "1",
                "--max-seconds",
                "600",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        safe = (result.stdout + result.stderr).replace(password, "[private runtime credential]")
        assert result.returncode == 0, safe

    try:
        worker("capture")
        with scoped(owned, "app")() as c:
            assert (
                c.execute(
                    "SELECT count(*) AS n FROM anvil.benchmark_run_cells WHERE run_id=%s",
                    (run["run_id"],),
                ).fetchone()["n"]
                == 200
            )
        worker("grade")
        worker("finish")
    finally:
        with connection(owned) as c:
            for role in roles:
                c.execute(sql.SQL("ALTER ROLE {} NOLOGIN").format(sql.Identifier(role)))
    with scoped(owned, "app")() as c:
        report = benchmark_run_views.view(c, run["run_id"])
        assert report["run"]["state"] == "completed"
        assert report["run"]["result"]["unscored_cells"] == 200
        assert len(report["cells"]) == 200
        assert report["summary"]["models"][0]["possible_points"] == "100"
        assert report["summary"]["models"][0]["mean_points"] is None
        assert report["run"]["model_performance"] is False
        assert report["run"]["provider_calls"] == 0
        assert report["failures"]["unknown_cells"] == 200
        assert "intended_decision" not in str(report)
        from anvil.expert_reviews import projection

        reviewed = projection(c, owned[1], run["run_id"], {"admin"})
        assert len(reviewed["items"]) == 7000
        assert sum(item["official"] for item in reviewed["items"]) == 4000
        assert reviewed["coverage"]["eligible"] == 7000 and reviewed["coverage"]["assessed"] == 0
        diagnostics = [item for item in reviewed["items"] if not item["official"]]
        assert len(diagnostics) == 3000
        assert all(
            item["weight"] == 0 and item["automated"]["award"] is None for item in diagnostics
        )
        assert all(item["automated"]["status"] == "unscored" for item in diagnostics)
        assert all(item["evidence_contract"]["source_evidence_sha256"] for item in diagnostics)
        assert reviewed["full_expert_score"] is None
        assert reviewed["expected_scope"]["episodes_per_model"] == 200
        assert len(reviewed["expected_scope"]["criterion_ids"]) == 20
        assert "intended_decision" not in str(reviewed)
        assert all(
            digest(cell["assessment"]) == cell["assessment_sha256"] for cell in report["cells"]
        )
        from anvil.benchmark_run_pdf import render

        assert render(report).startswith(b"%PDF")


def test_real_api_import_idempotency_rbac_and_bound_run_queue(imported):
    from fastapi.testclient import TestClient

    from anvil.api import app
    from anvil.auth import hashed

    owned, item = imported
    sessions = []

    def client(user):
        token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
        with connection(owned) as c:
            c.execute(
                "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
                (hashed(token), user, hashed(csrf)),
            )
        sessions.append(hashed(token))
        result = TestClient(app)
        result.cookies.set("anvil_session", token)
        result.headers.update(
            {
                "Origin": "http://127.0.0.1:3202",
                "X-CSRF-Token": csrf,
                "Idempotency-Key": secrets.token_hex(16),
            }
        )
        return result

    base = f"/api/v1/projects/{owned[1]}/golden-banking/v1"
    admin = client(owned[2])
    try:
        assert TestClient(app).get(base + "/anvil/imports").status_code == 401
        body = {"pack_id": owned[4]}
        first = admin.post(base + "/anvil/import", json=body)
        assert first.status_code == 200, first.text
        # Both the fixture and public import use the same five reusable tasks.
        assert first.json()["data"]["id"] == item["id"]
        assert first.json()["data"]["binding_count"] == 5
        assert first.json()["data"]["manifest"]["case_dataset"]["case_count"] == 200
        assert admin.post(base + "/anvil/import", json=body).json()["data"] == first.json()["data"]
        started = admin.post(
            base + "/anvil/runs",
            json={"import_id": item["id"], "repetitions": 1},
            headers={"Idempotency-Key": secrets.token_hex(16)},
        )
        assert started.status_code == 202, started.text
        assert started.json()["data"]["planned_cells"] == 200
        catalog = admin.get(f"/api/v1/projects/{owned[1]}/workspace/benchmark")
        assert catalog.status_code == 200, catalog.text
        assert any(g["id"] == item["task_group_id"] for g in catalog.json()["data"]["groups"])
        assert any(
            p["id"] == started.json()["data"]["plan_id"] and p["runnable"]
            for p in catalog.json()["data"]["plans"]
        )
        with connection(owned) as c:
            c.execute(
                "UPDATE anvil.memberships SET role='rl-engineer' WHERE project_id=%s AND user_id=%s",
                (owned[1], owned[3]),
            )
        engineer = client(owned[3])
        assert engineer.post(base + "/anvil/import", json=body).status_code == 403
        legacy = admin.post(
            f"/api/v1/projects/{owned[1]}/workspace/benchmark/plans",
            json={
                "name": "Wrong legacy path",
                "task_group_id": item["task_group_id"],
                "task_ids": ["GB-001"],
                "models": ["fictional-compliant-v1"],
                "environment_ids": ["golden-kyc-v1"],
                "method_ids": ["task-rubric-v1"],
                "repetitions": 1,
            },
            headers={"Idempotency-Key": secrets.token_hex(16)},
        )
        assert legacy.status_code == 409
    finally:
        with connection(owned) as c:
            for token in sessions:
                c.execute(
                    "UPDATE anvil.sessions SET revoked_at=now() WHERE token_hash=%s", (token,)
                )
