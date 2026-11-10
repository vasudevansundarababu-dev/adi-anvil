"""Independent actual SQL/API scripted-execution checks, never model evidence."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from psycopg import sql
from test_benchmark_pipeline import login
from test_private_storage import connection
from test_private_storage import lab as storage_lab

from anvil import benchmark_rehearsal as rehearsal
from anvil.api import context, idempotent, wrap
from anvil.benchmark_rehearsal_api import routes
from anvil.benchmark_rehearsal_report import routes as report_routes
from anvil.db import digest

lab = storage_lab
ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("ANVIL_BENCHMARK_REHEARSAL_ENABLED", "true")
    monkeypatch.setenv("ANVIL_LOCAL_FIXTURE_ENABLED", "true")
    for flag in rehearsal.PAID_FLAGS:
        monkeypatch.setenv(flag, "false")


def client(lab, identity="engineer"):
    original = login(lab, identity)
    app = FastAPI()

    @app.middleware("http")
    async def ids(request: Request, call_next):
        request.state.request_id = uuid4().hex
        return await call_next(request)

    app.include_router(routes(context, wrap, idempotent))
    app.include_router(report_routes(context, wrap))
    c = TestClient(app)
    c.cookies.update(original.cookies)
    c.headers.update(original.headers)
    original.close()
    return c


def base(lab):
    return f"/api/v1/projects/{lab['project']}/workspace/benchmarks/rehearsals"


def create(c, lab, key=None):
    response = c.post(
        base(lab),
        json={"name": "Actual scripted software execution QA"},
        headers={"idempotency-key": key or str(uuid4())},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def execute(c, lab, row, key=None):
    return c.post(
        base(lab) + "/" + str(row["id"]) + "/execute",
        json={"expected_manifest_sha256": row["manifest_sha256"]},
        headers={"idempotency-key": key or str(uuid4())},
    )


def privileged_counts(lab):
    with connection(project=lab["project"], user=lab["admin"]) as c:
        tables = c.execute(
            "SELECT t.table_name FROM information_schema.tables t JOIN information_schema.columns col USING(table_schema,table_name) WHERE t.table_schema='anvil' AND t.table_name LIKE 'benchmark_%' AND t.table_name<>'benchmark_rehearsals' AND t.table_name NOT LIKE 'benchmark_report_%' AND col.column_name='project_id'"
        ).fetchall()
        return {
            row["table_name"]: c.execute(
                sql.SQL("SELECT count(*) n FROM anvil.{} WHERE project_id=%s").format(
                    sql.Identifier(row["table_name"])
                ),
                (lab["project"],),
            ).fetchone()["n"]
            for row in tables
        }


def test_actual_eighteen_cells_have_independent_outputs_and_eighty_one_point_mean(lab):
    c = client(lab)
    before = privileged_counts(lab)
    row = create(c, lab)
    assert row["state"] == "draft" and row["result"] is None
    response = execute(c, lab, row)
    assert response.status_code == 200, response.text
    saved = response.json()["data"]
    result = saved["result"]
    assert saved["state"] == "completed" and result["provider_calls"] == 0
    assert result["official_primary"] is None and result["model_performance"] is False
    assert result["ranking_scope"] == "fictional_scripted_profiles_only"
    cells = result["cells"]
    assert len(cells) == 18
    assert len({(x["profile_id"], x["task_id"], x["repetition"]) for x in cells}) == 18
    assert len({x["id"] for x in cells}) == 18
    for cell in cells:
        public = json.loads(
            (
                ROOT
                / "fixtures/benchmark-bundle/fictional-points-v1/runtime_pack"
                / cell["task_id"]
                / "items.json"
            ).read_text()
        )["items"]
        assert cell["output_sha256"] == digest(cell["outputs"])
        assert set(cell["outputs"]["answers_json"]) == {x["id"] for x in public}
        earned = 0
        for index, item in enumerate(public):
            n = item["n"]
            expected_answer = (
                n * n
                if cell["profile_id"] == "square-all-v1"
                or (cell["profile_id"] == "square-even-v1" and n % 2 == 0)
                or (cell["profile_id"] == "square-first-six-v1" and index < 6)
                else n
            )
            actual = cell["outputs"]["answers_json"][item["id"]]
            assert actual == expected_answer
            earned += actual == n**2
        assert Decimal(cell["earned_points"]) == earned
        assert len(cell["criteria"]) == len(public)
        assert sum(Decimal(x["earned_points"]) for x in cell["criteria"]) == earned
    for profile in result["profiles"]:
        raw = sum(
            Decimal(x["earned_points"]) for x in cells if x["profile_id"] == profile["profile_id"]
        )
        assert Decimal(profile["mean_points"]) == raw / 2
        assert profile["possible_points"] == "81"
    square = next(x for x in result["profiles"] if x["profile_id"] == "square-all-v1")
    assert Decimal(square["mean_points"]) == 81
    assert c.get(base(lab) + "/" + saved["id"]).json()["data"]["result"] == result
    assert privileged_counts(lab) == before


def test_cross_project_rls_and_worker_denial(lab):
    c = client(lab)
    row = create(c, lab)
    outsider = client(lab, "outsider")
    other = base(lab).replace(lab["project"], lab["other_project"])
    assert outsider.get(other + "/" + row["id"]).status_code == 404
    assert outsider.get(base(lab) + "/" + row["id"]).status_code in {403, 404}
    with connection("anvil_app", lab["other_project"], lab["outsider"]) as db:
        assert (
            db.execute(
                "SELECT id FROM anvil.benchmark_rehearsals WHERE id=%s", (row["id"],)
            ).fetchone()
            is None
        )
    with connection("anvil_worker", lab["project"], lab["engineer"]) as db:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute("SELECT * FROM anvil.benchmark_rehearsals")


def test_exact_manifest_idempotency_and_terminal_result_are_immutable(lab):
    c = client(lab)
    key = str(uuid4())
    row = create(c, lab, key)
    assert create(c, lab, key)["id"] == row["id"]
    bad = c.post(
        base(lab) + "/" + row["id"] + "/execute", json={"expected_manifest_sha256": "0" * 64}
    )
    assert bad.status_code == 409
    first = execute(c, lab, row)
    assert first.status_code == 200, first.text
    assert execute(c, lab, row).json()["data"]["result"] == first.json()["data"]["result"]
    with connection("anvil_app", lab["project"], lab["engineer"]) as db:
        with pytest.raises(psycopg.errors.RaiseException):
            db.execute(
                "UPDATE anvil.benchmark_rehearsals SET state='draft',result=NULL,executed_at=NULL WHERE id=%s",
                (row["id"],),
            )


def test_concurrent_execute_invokes_algorithms_once_and_returns_same_result(lab):
    clients = [client(lab), client(lab)]
    row = create(clients[0], lab)
    barrier = threading.Barrier(2)
    calls = []
    original = rehearsal.run

    def observed(frozen):
        calls.append(1)
        return original(frozen)

    def invoke(index):
        barrier.wait(timeout=10)
        return execute(clients[index], lab, row)

    with patch.object(rehearsal, "run", observed), ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(invoke, range(2)))
    assert [x.status_code for x in responses] == [200, 200]
    assert len(calls) == 1
    assert responses[0].json()["data"]["result"] == responses[1].json()["data"]["result"]


def test_paid_flag_and_untrusted_execution_parameters_fail_closed(lab, monkeypatch):
    c = client(lab)
    assert (
        c.post(base(lab), json={"name": "Denied", "model_id": "fake", "expected": {}}).status_code
        == 422
    )
    monkeypatch.setenv("ANVIL_LIVE_PROVIDERS_ENABLED", "true")
    assert c.post(base(lab), json={"name": "Denied paid mode"}).status_code == 409


def test_candidate_receives_only_public_integer_records_and_never_private_files(lab):
    c = client(lab)
    row = create(c, lab)
    original = rehearsal.candidate
    observed = []

    def candidate(profile, items):
        assert all(set(item) == {"id", "n"} for item in items)
        with (
            patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("Candidate attempted filesystem read"),
            ),
            patch.object(
                Path, "read_text", side_effect=AssertionError("Candidate attempted filesystem read")
            ),
        ):
            outputs = original(profile, items)
        observed.append(profile)
        return outputs

    with patch.object(rehearsal, "candidate", candidate):
        response = execute(c, lab, row)
    assert response.status_code == 200, response.text
    assert len(observed) == 18


def test_changed_frozen_source_refuses_execution_without_completed_rows(lab):
    c = client(lab)
    row = create(c, lab)
    original = rehearsal.manifest

    def changed():
        frozen = original()
        frozen["source_hashes"]["executor_evaluator"] = "0" * 64
        return frozen

    with patch.object(rehearsal, "manifest", changed):
        response = execute(c, lab, row)
    assert response.status_code == 409
    assert c.get(base(lab) + "/" + row["id"]).json()["data"]["state"] == "draft"


def test_source_change_during_execution_rolls_back_terminal_result(lab):
    c = client(lab)
    row = create(c, lab)
    original = rehearsal.manifest
    calls = []

    def changed_after_preflight():
        frozen = original()
        calls.append(1)
        if len(calls) > 1:
            frozen["source_hashes"]["executor_evaluator"] = "0" * 64
        return frozen

    with patch.object(rehearsal, "manifest", changed_after_preflight):
        response = execute(c, lab, row)
    assert response.status_code == 409
    saved = c.get(base(lab) + "/" + row["id"]).json()["data"]
    assert saved["state"] == "draft" and saved["result"] is None
