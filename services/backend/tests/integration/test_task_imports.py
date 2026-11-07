import json
import subprocess
import sys
from urllib.parse import urlsplit

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from journey_support import provision_journey
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import sql
from test_api_security import USERS, client_factory  # noqa: F401

from anvil import cli, ingestion, task_imports
from anvil.config import ROOT, setting
from anvil.db import one, transaction, uid


@pytest.fixture
def owned_journey(monkeypatch):
    """A synthetic journey in a fresh, uniquely named database that no worker polls.

    The test leases and processes its own ingestion chunks and checks exact checkpoints, so
    a background worker on the shared database must not be able to claim its jobs.
    """
    target = "anvil_taskimporttest_" + uid().replace("-", "")[:12]
    admin_url = setting("MIGRATION_DATABASE_URL")
    with psycopg.connect(admin_url, autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(target)))
    try:
        for key in ("MIGRATION_DATABASE_URL", "DATABASE_URL", "WORKER_DATABASE_URL"):
            monkeypatch.setenv(key, urlsplit(setting(key))._replace(path="/" + target).geturl())
        with psycopg.connect(setting("MIGRATION_DATABASE_URL"), autocommit=True) as c:
            c.execute("CREATE SCHEMA anvil")
            command.upgrade(Config(str(ROOT / "services/backend/alembic.ini")), "head")
            c.execute("SET search_path TO anvil_checkpoints")
            PostgresSaver(c).setup()
            c.execute(
                "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA anvil_checkpoints TO anvil_worker"
            )
            c.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA anvil_checkpoints TO anvil_worker")
        cli.seed()
        yield provision_journey()
    finally:
        with psycopg.connect(admin_url, autocommit=True) as c:
            c.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(target))
            )


def test_import_publish_versions_run_and_resume(client_factory, monkeypatch, owned_journey):  # noqa: F811
    journey = owned_journey
    project = journey["project_id"]
    base = f"/api/v1/projects/{project}"
    client, _ = client_factory("researcher")

    def call(path, body=None, method="POST", expected=200, headers=None):
        response = client.request(
            method, base + path, json=body, headers={"Idempotency-Key": uid(), **(headers or {})}
        )
        assert response.status_code == expected, response.text
        return response.json().get("data")

    protocols = call("/protocols", method="GET")
    protocol = next(
        p for p in protocols if p["lifecycle"] == "approved" and p["content"]["mode"] == "fixture"
    )
    with transaction(project, USERS["researcher"]) as c:
        objective = one(
            c,
            "SELECT resource_id FROM anvil.revisions WHERE id=%s",
            (protocol["content"]["objective_revision_id"],),
        )["resource_id"]
        suite_id = one(
            c,
            "SELECT resource_id FROM anvil.revisions WHERE id=%s",
            (protocol["content"]["suite_revision_id"],),
        )["resource_id"]
    source = (ROOT / "apps/web/public/examples/synthetic-five-tasks.jsonl").read_bytes()

    def upload(data, dataset=None, classification="adi_synthetic"):
        response = client.post(
            base + "/artifacts?purpose=task_import",
            files={"file": ("tasks.jsonl", data, "application/x-ndjson")},
        )
        assert response.status_code == 200, response.text
        artifact = response.json()["data"]["id"]
        declaration = {
            "classification": classification,
            "source_owner": "ADI test authors",
            "basis": "Original synthetic development fixture; not partner data.",
            **(
                {"generator_version": "manual-v1", "seed": "five-v1"}
                if classification == "adi_synthetic"
                else {}
            ),
        }
        return call(
            f"/objectives/{objective}/task-imports",
            {
                "artifact_id": artifact,
                **({"provenance": declaration} if classification else {}),
                **({"dataset_id": dataset} if dataset else {}),
            },
        )

    def advance(batch):
        # Simulates separately leased worker chunks without relying on wall-clock scheduling.
        for _ in range(20):
            b = call("/task-imports/" + batch["id"], method="GET")
            if b["status"] in ("ready", "invalid"):
                return b
            with transaction(project, USERS["researcher"]) as c:
                job = one(
                    c,
                    "UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds' WHERE target_id=%s RETURNING *",
                    (b["job"]["id"],),
                )
            ingestion.process(job)
        raise AssertionError("ingestion did not complete")

    first = advance(upload(source))
    assert first["counts"]["valid"] == 5
    assert all("reference" not in r["spec"] for r in first["preview"])
    body = {"revision": first["revision"], "normalized_sha256": first["normalized_sha256"]}
    key = uid()
    real_uid = task_imports.uid
    calls = 0

    def broken_second_id():
        nonlocal calls
        calls += 1
        return real_uid() if calls == 1 else "not-a-uuid"

    with monkeypatch.context() as patch:
        patch.setattr(task_imports, "uid", broken_second_id)
        call(f"/task-imports/{first['id']}/publish", body, expected=500)
    with transaction(project, USERS["researcher"]) as c:
        assert (
            one(
                c,
                "SELECT count(*) n FROM anvil.dataset_versions WHERE import_id=%s",
                (first["id"],),
            )["n"]
            == 0
        )
        assert (
            one(c, "SELECT status FROM anvil.task_imports WHERE id=%s", (first["id"],))["status"]
            == "ready"
        )
    v1 = call(f"/task-imports/{first['id']}/publish", body, headers={"Idempotency-Key": key})
    assert v1["source"]["provenance"]["classification"] == "adi_synthetic"
    assert v1["source"]["provenance"]["source_owner"] == "ADI test authors"
    rows = call("/dataset-versions/" + v1["id"] + "/tasks", method="GET")
    assert rows[0]["source_record"]["provenance"] == v1["source"]["provenance"]
    assert rows[0]["source_record"]["sha256"] == v1["source"]["sha256"]
    call(
        f"/objectives/{objective}/task-imports",
        {
            "artifact_id": v1["source"]["artifact_id"],
            "provenance": {
                "classification": "bodhium_restricted",
                "source_owner": "Another owner",
                "basis": "Test-only declaration conflicts with immutable original ownership.",
            },
        },
        expected=409,
    )
    # Never persist synthetic fixtures under partner/SME provenance. All class
    # gate permutations are pure-policy unit tests; this exercises missing provenance.
    blocked = advance(upload(source, classification=None))
    assert blocked["publication_blocker"]
    call(
        f"/objectives/{objective}/task-imports",
        {
            "artifact_id": blocked["source"]["id"],
            "provenance": {
                "classification": "adi_synthetic",
                "source_owner": "ADI test authors",
                "basis": "Original synthetic development fixture; not partner data.",
                "generator_version": "manual-v1",
                "seed": "five-v1",
            },
        },
        expected=409,
    )
    call(
        f"/task-imports/{blocked['id']}/publish",
        {"revision": blocked["revision"], "normalized_sha256": blocked["normalized_sha256"]},
        expected=409,
    )
    assert (
        call(f"/task-imports/{first['id']}/publish", body, headers={"Idempotency-Key": key}) == v1
    )
    second = advance(
        upload(source.replace(b"Choose a campaign", b"Select a campaign"), first["dataset_id"])
    )
    v2 = call(
        f"/task-imports/{second['id']}/publish",
        {"revision": second["revision"], "normalized_sha256": second["normalized_sha256"]},
    )
    assert (v1["version_number"], v2["version_number"]) == (1, 2)
    assert call("/dataset-versions/" + v1["id"], method="GET") == v1
    suite = call("/suites/" + str(suite_id), method="GET")
    call(
        "/suites/" + str(suite_id) + "/dataset-version",
        {"version_id": first["id"]},
        method="PUT",
        expected=409,
        headers={"If-Match": str(suite["row_version"])},
    )
    call(
        "/suites/" + str(suite_id) + "/dataset-version",
        {"version_id": v1["id"]},
        method="PUT",
        headers={"If-Match": str(suite["row_version"])},
    )
    run = call(
        "/runs",
        {"protocol_revision_id": protocol["current_revision_id"], "dataset_version_id": v1["id"]},
        expected=201,
    )
    assert run["dataset_snapshot"]["task_count"] == 5
    assert run["dataset_version_id"] == v1["id"]
    assert run["dataset_snapshot"]["source_provenance"] == v1["source"]["provenance"]
    call(
        "/runs/" + run["id"] + "/launch",
        {},
        expected=409,
        headers={"If-Match": str(run["row_version"])},
    )
    for table, column, identifier in [
        ("dataset_versions", "id", v1["id"]),
        ("dataset_tasks", "version_id", v1["id"]),
    ]:
        with transaction(project, USERS["researcher"]) as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(
                    f"UPDATE anvil.{table} SET {column}={column} WHERE {column}=%s", (identifier,)
                )
    with transaction(project, worker=True) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT * FROM anvil.dataset_references")
    outsider, _ = client_factory("outsider")
    assert outsider.get(base + "/dataset-versions/" + v1["id"]).status_code == 404
    broken = advance(upload(b'{"schema_version":"1.0","external_id":"x","input":{}}'))
    assert any(e["field"] == "instruction" for e in broken["errors"])
    call(
        "/task-imports/" + broken["id"] + "/publish",
        {"revision": 1, "normalized_sha256": broken["normalized_sha256"]},
        expected=409,
    )
    large = b"\n".join(
        json.dumps(
            {
                "schema_version": "1.0",
                "external_id": str(n),
                "instruction": "Synthetic checkpoint test",
                "input": {},
            }
        ).encode()
        for n in range(450)
    )
    pending = upload(large)
    with transaction(project, USERS["researcher"]) as c:
        job = one(
            c,
            "UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds' WHERE target_id=%s RETURNING *",
            (pending["job"]["id"],),
        )
    crashed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,os,signal,sys; from anvil.ingestion import process; process(json.load(sys.stdin)); os.kill(os.getpid(),signal.SIGKILL)",
        ],
        input=json.dumps(
            {key: str(job[key]) for key in ("id", "target_id", "project_id", "lease_token")}
        ),
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert crashed.returncode == -9, crashed.stderr
    with pytest.raises(RuntimeError, match="lease_lost"):
        ingestion.process(job)
    with transaction(project, USERS["researcher"]) as c:
        retry_job = one(
            c,
            "UPDATE anvil.jobs SET status='leased',attempts=1,lease_until=now()+interval '60 seconds' WHERE id=%s RETURNING *",
            (job["id"],),
        )
        assert ingestion.retry_transient(c, retry_job, OSError("test-only transient failure"))
        assert not ingestion.retry_transient(c, {**retry_job, "attempts": 3}, OSError())
        assert not ingestion.retry_transient(c, retry_job, ValueError())
    cancelled = call("/task-imports/" + pending["id"] + "/cancel", {})
    assert cancelled["job"]["checkpoint"] == 200
    call("/task-imports/" + pending["id"] + "/retry", {})
    complete = advance(pending)
    assert complete["counts"]["valid"] == 450
    with transaction(project, USERS["researcher"]) as c:
        assert (
            one(
                c,
                "SELECT count(*) n FROM anvil.ingestion_chunks WHERE ingestion_id=%s",
                (pending["job"]["id"],),
            )["n"]
            == 3
        )
