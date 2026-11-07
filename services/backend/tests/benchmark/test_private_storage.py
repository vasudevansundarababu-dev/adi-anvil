import hashlib
import io
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.rows import dict_row

from anvil import artifacts
from anvil.api import app
from anvil.benchmark_storage import (
    bind_private,
    read_private,
    stage_private,
    stage_private_stream,
    store_private,
)
from anvil.db import transaction

ROOT = Path(__file__).resolve().parents[4]
TABLES = [
    "benchmark_bundle_receipts",
    "benchmark_receipt_events",
    "benchmark_private_assignments",
    "benchmark_private_revocations",
    "benchmark_evaluator_bindings",
    "benchmark_evaluator_jobs",
]


@contextmanager
def connection(role="anvil_migration", project=None, user=None):
    dsn = os.environ["ANVIL_BENCHMARK_TEST_DATABASE_URL"]
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        if role != "anvil_migration":
            c.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        c.execute(
            "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
            (str(project or ""), str(user or "")),
        )
        yield c


@pytest.fixture
def lab():
    ids = {
        name: str(uuid4())
        for name in ["org", "project", "other_project", "admin", "engineer", "outsider"]
    }
    with connection() as c:
        c.execute(
            "INSERT INTO anvil.organizations(id,name) VALUES(%s,'Benchmark isolated synthetic lab')",
            (ids["org"],),
        )
        for key in ["admin", "engineer", "outsider"]:
            c.execute(
                "INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,'benchmark-test',%s,%s)",
                (ids[key], ids["org"], ids[key], "Synthetic " + key),
            )
        for key in ["project", "other_project"]:
            c.execute(
                "INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,'Benchmark isolated test')",
                (ids[key], ids["org"]),
            )
        for key, project, role in [
            ("admin", "project", "admin"),
            ("engineer", "project", "rl-engineer"),
            ("outsider", "other_project", "rl-engineer"),
        ]:
            c.execute(
                "INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,%s)",
                (ids[project], ids[key], role),
            )
    return ids


def assign(lab, user, *, scope="source_review", target=None):
    aid = str(uuid4())
    with connection(project=lab["project"], user=lab["admin"]) as c:
        c.execute(
            "INSERT INTO anvil.benchmark_private_assignments(id,project_id,user_id,scope,artifact_id,granted_by,expires_at) VALUES(%s,%s,%s,%s,%s,%s,now()+interval '1 hour')",
            (aid, lab["project"], lab[user], scope, target, lab["admin"]),
        )
    return aid


def test_new_foundation_relations_force_rls_and_evaluator_has_no_bypass():
    with connection() as c:
        for name in TABLES:
            row = c.execute(
                "SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass",
                ("anvil." + name,),
            ).fetchone()
            assert row["relrowsecurity"] and row["relforcerowsecurity"]
        row = c.execute(
            "SELECT rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolcanlogin FROM pg_roles WHERE rolname='anvil_benchmark_evaluator'"
        ).fetchone()
        assert row and not any(row.values())
        for table in TABLES:
            assert not c.execute(
                "SELECT has_table_privilege('anvil_worker',%s,'SELECT') AS allowed",
                ("anvil." + table,),
            ).fetchone()["allowed"]


def test_ordinary_worker_cannot_claim_benchmark_or_future_benchmark_jobs(lab):
    for kind in ["benchmark_evaluate", "benchmark_orchestrate", "benchmark_future_kind"]:
        with connection() as c:
            c.execute(
                "INSERT INTO anvil.jobs(id,project_id,kind,target_id,operation_key) VALUES(%s,%s,%s,%s,%s)",
                (str(uuid4()), lab["project"], kind, str(uuid4()), str(uuid4())),
            )
    with connection("anvil_worker", lab["project"]) as c:
        assert c.execute("SELECT * FROM anvil.claim_job()").fetchall() == []


def test_private_bytes_require_live_individual_assignment_not_admin_role(lab, tmp_path):
    assign(lab, "engineer")
    with transaction(lab["project"], lab["engineer"]) as c:
        aid = store_private(
            c,
            lab["project"],
            b"PRIVATE-SYNTHETIC-SOURCE",
            "benchmark_raw",
            created_by=lab["engineer"],
        )
    with transaction(lab["project"], lab["engineer"]) as c:
        assert read_private(c, aid) == b"PRIVATE-SYNTHETIC-SOURCE"
        with pytest.raises(HTTPException) as exc:
            artifacts.read(c, aid)
        assert exc.value.status_code == 403
    for user in [lab["admin"], lab["outsider"]]:
        with transaction(lab["project"], user) as c:
            with pytest.raises(HTTPException) as exc:
                read_private(c, aid)
            assert exc.value.status_code == 404
    with connection("anvil_worker", lab["project"], lab["engineer"]) as c:
        assert c.execute("SELECT * FROM anvil.artifacts WHERE id=%s", (aid,)).fetchall() == []
    with connection("anvil_app", lab["other_project"], lab["outsider"]) as c:
        assert c.execute("SELECT * FROM anvil.artifacts WHERE id=%s", (aid,)).fetchall() == []
    with connection("anvil_benchmark_evaluator", lab["project"]) as c:
        assert c.execute("SELECT * FROM anvil.artifacts WHERE id=%s", (aid,)).fetchall() == []


def test_revoked_assignment_denies_reads(lab):
    assignment = assign(lab, "engineer")
    with transaction(lab["project"], lab["engineer"]) as c:
        aid = store_private(
            c,
            lab["project"],
            b"PRIVATE-FICTIONAL-REVOKED",
            "benchmark_eval",
            created_by=lab["engineer"],
        )
    with connection(project=lab["project"], user=lab["admin"]) as c:
        c.execute(
            "INSERT INTO anvil.benchmark_private_revocations(project_id,assignment_id,revoked_by,rationale) VALUES(%s,%s,%s,'Synthetic revoke test')",
            (lab["project"], assignment, lab["admin"]),
        )
    with transaction(lab["project"], lab["engineer"]) as c:
        with pytest.raises(HTTPException) as exc:
            read_private(c, aid)
        assert exc.value.status_code == 404


def test_generic_http_download_denies_even_assigned_private_reference(lab):
    assign(lab, "engineer")
    token = uuid4().hex
    with connection(project=lab["project"], user=lab["engineer"]) as c:
        c.execute(
            "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                lab["engineer"],
                hashlib.sha256(b"test-csrf").hexdigest(),
            ),
        )
    with transaction(lab["project"], lab["engineer"]) as c:
        aid = store_private(
            c, lab["project"], b"PRIVATE-HTTP-CANARY", "benchmark_raw", created_by=lab["engineer"]
        )
    with TestClient(app) as client:
        client.cookies.set("anvil_session", token)
        response = client.get(f"/api/v1/projects/{lab['project']}/artifacts/{aid}/content")
        assert response.status_code == 403
        assert "PRIVATE-HTTP-CANARY" not in response.text


def test_receipt_composite_fk_and_append_only_guards(lab):
    assign(lab, "engineer")
    with transaction(lab["project"], lab["engineer"]) as c:
        aid = store_private(
            c, lab["project"], b"PRIVATE-RECEIPT-TEST", "benchmark_raw", created_by=lab["engineer"]
        )
    rid = str(uuid4())
    digest = hashlib.sha256(b"PRIVATE-RECEIPT-TEST").hexdigest()
    statement = "INSERT INTO anvil.benchmark_bundle_receipts(id,project_id,exporter,bank_id,bank_version,archive_artifact_id,archive_sha256,manifest_sha256,created_by) VALUES(%s,%s,'fixture','original','1.0.0',%s,%s,%s,%s)"
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        c.execute(statement, (rid, lab["project"], aid, digest, digest, lab["engineer"]))
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        assert (
            str(
                c.execute(
                    "SELECT id FROM anvil.benchmark_bundle_receipts WHERE id=%s", (rid,)
                ).fetchone()["id"]
            )
            == rid
        )
    with pytest.raises(psycopg.Error):
        with connection("anvil_app", lab["project"], lab["engineer"]) as c:
            c.execute(
                "UPDATE anvil.benchmark_bundle_receipts SET bank_version='2.0.0' WHERE id=%s",
                (rid,),
            )
    with pytest.raises(psycopg.Error):
        with connection() as c:
            c.execute(
                statement,
                (str(uuid4()), lab["other_project"], aid, digest, digest, lab["outsider"]),
            )


def test_same_bytes_are_content_addressed_but_projects_are_not_deduplicated(lab):
    assign(lab, "engineer")
    with transaction(lab["project"], lab["engineer"]) as c:
        first = store_private(
            c, lab["project"], b"PRIVATE-CONTENT-BOUND", "benchmark_raw", created_by=lab["engineer"]
        )
        second = store_private(
            c, lab["project"], b"PRIVATE-CONTENT-BOUND", "benchmark_raw", created_by=lab["engineer"]
        )
        a = c.execute("SELECT object_key FROM anvil.artifacts WHERE id=%s", (first,)).fetchone()
        b = c.execute("SELECT object_key FROM anvil.artifacts WHERE id=%s", (second,)).fetchone()
        assert first == second and a == b
        assert str(lab["project"]) in a["object_key"]
        assert hashlib.sha256(b"PRIVATE-CONTENT-BOUND").hexdigest() in a["object_key"]
        assert a["object_key"].startswith("benchmark-vault/")


def test_evaluator_can_read_only_its_fenced_job_inputs(lab):
    assign(lab, "engineer", scope="evaluation_review")
    with transaction(lab["project"], lab["engineer"]) as c:
        permitted = store_private(
            c, lab["project"], b"PRIVATE-JOB-BOUND", "benchmark_eval", created_by=lab["engineer"]
        )
        unrelated = store_private(
            c, lab["project"], b"PRIVATE-UNRELATED", "benchmark_eval", created_by=lab["engineer"]
        )
    binding, job, fence, output = [str(uuid4()) for _ in range(4)]
    digest = hashlib.sha256(b"synthetic-evaluator-only").hexdigest()
    with connection(project=lab["project"], user=lab["admin"]) as c:
        c.execute(
            "INSERT INTO anvil.benchmark_evaluator_bindings(id,project_id,registry_id,version,implementation_sha256,image_digest,policy_sha256,reviewed_by,review_evidence_sha256) VALUES(%s,%s,'fictional-unreviewed-test','1.0.0',%s,%s,%s,%s,%s)",
            (binding, lab["project"], digest, "sha256:" + digest, digest, lab["admin"], digest),
        )
        c.execute(
            "INSERT INTO anvil.artifacts(id,project_id,object_key,sha256,byte_size,mime_type,classification,scan_status,origin) VALUES(%s,%s,%s,%s,0,'text/plain','benchmark_output','clean','original_synthetic_fixture')",
            (output, lab["project"], str(uuid4()), digest),
        )
        c.execute(
            "INSERT INTO anvil.benchmark_evaluator_jobs(id,project_id,binding_id,sealed_output_artifact_id,created_by,state,lease_token,lease_until) VALUES(%s,%s,%s,%s,%s,'leased',%s,now()+interval '5 minutes')",
            (job, lab["project"], binding, output, lab["engineer"], fence),
        )
        c.execute(
            "INSERT INTO anvil.benchmark_evaluator_job_inputs(project_id,job_id,artifact_id,artifact_sha256) VALUES(%s,%s,%s,%s)",
            (lab["project"], job, permitted, hashlib.sha256(b"PRIVATE-JOB-BOUND").hexdigest()),
        )
    for current_fence, expected in [(str(uuid4()), False), (fence, True)]:
        with connection("anvil_benchmark_evaluator", lab["project"]) as c:
            c.execute(
                "SELECT set_config('anvil.benchmark_job',%s,true),set_config('anvil.benchmark_fence',%s,true)",
                (job, current_fence),
            )
            rows = c.execute(
                "SELECT id FROM anvil.artifacts WHERE id=ANY(%s::uuid[])", ([permitted, unrelated],)
            ).fetchall()
            assert [str(r["id"]) for r in rows] == ([permitted] if expected else [])
    with connection() as c:
        c.execute(
            "UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s",
            (lab["project"], lab["engineer"]),
        )
    with connection("anvil_benchmark_evaluator", lab["project"]) as c:
        c.execute(
            "SELECT set_config('anvil.benchmark_job',%s,true),set_config('anvil.benchmark_fence',%s,true)",
            (job, fence),
        )
        assert (
            c.execute("SELECT id FROM anvil.artifacts WHERE id=%s", (permitted,)).fetchall() == []
        )


def test_generic_store_rejects_private_class_before_writing(lab):
    assign(lab, "engineer")
    with transaction(lab["project"], lab["engineer"]) as c:
        with pytest.raises(HTTPException) as exc:
            artifacts.store(
                c, lab["project"], b"SYNTHETIC-DO-NOT-STORE-GENERICALLY", "benchmark_raw"
            )
        assert exc.value.status_code == 403


def test_legacy_artifact_metadata_updates_remain_compatible(lab):
    with transaction(lab["project"], lab["engineer"]) as c:
        aid = artifacts.store(c, lab["project"], b'{"synthetic":true}', "internal")
        c.execute("UPDATE anvil.artifacts SET original_filename='fixture.json' WHERE id=%s", (aid,))
        assert (
            c.execute(
                "SELECT original_filename FROM anvil.artifacts WHERE id=%s", (aid,)
            ).fetchone()["original_filename"]
            == "fixture.json"
        )
        assert artifacts.read(c, aid) == b'{"synthetic":true}'


def test_private_metadata_cannot_bind_worker_shared_object_key(lab):
    digest = hashlib.sha256(b"fictional-metadata-only").hexdigest()
    with connection() as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(
                "INSERT INTO anvil.artifacts(id,project_id,object_key,sha256,byte_size,mime_type,classification,scan_status,origin) VALUES(%s,%s,%s,%s,0,'text/plain','benchmark_raw','quarantined','original_synthetic_fixture')",
                (str(uuid4()), lab["project"], str(uuid4()), digest),
            )


def test_engineer_cannot_grant_private_access_to_self(lab):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with connection("anvil_app", lab["project"], lab["engineer"]) as c:
            c.execute(
                "INSERT INTO anvil.benchmark_private_assignments(id,project_id,user_id,scope,granted_by,expires_at) VALUES(%s,%s,%s,'source_review',%s,now()+interval '1 hour')",
                (str(uuid4()), lab["project"], lab["engineer"], lab["engineer"]),
            )


def test_concurrent_private_staging_and_binding_is_idempotent(lab):
    assign(lab, "engineer")
    barrier = threading.Barrier(8)
    data = b"ORIGINAL-SYNTHETIC-CONCURRENCY-FIXTURE" * 16384

    def store(_):
        barrier.wait(timeout=10)
        with transaction(lab["project"], lab["engineer"]) as c:
            return store_private(
                c, lab["project"], data, "benchmark_raw", created_by=lab["engineer"]
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        identifiers = list(pool.map(store, range(8)))
    assert len(set(identifiers)) == 1
    with transaction(lab["project"], lab["engineer"]) as c:
        assert read_private(c, identifiers[0]) == data


def test_expired_assignment_never_grants_private_read(lab):
    prepared = stage_private(lab["project"], b"PRIVATE-EXPIRED-SYNTHETIC", "benchmark_raw")
    with connection(project=lab["project"], user=lab["engineer"]) as c:
        aid = bind_private(c, prepared, created_by=lab["engineer"])
    with connection(project=lab["project"], user=lab["admin"]) as c:
        c.execute(
            "INSERT INTO anvil.benchmark_private_assignments(id,project_id,user_id,scope,granted_by,created_at,expires_at) VALUES(%s,%s,%s,'source_review',%s,now()-interval '2 hours',now()-interval '1 hour')",
            (str(uuid4()), lab["project"], lab["engineer"], lab["admin"]),
        )
    with transaction(lab["project"], lab["engineer"]) as c:
        with pytest.raises(HTTPException) as exc:
            read_private(c, aid)
        assert exc.value.status_code == 404


@pytest.mark.parametrize("tamper", ["bytes", "world_read", "symlink", "hardlink"])
def test_private_storage_rejects_tampering_and_nonregular_aliases(lab, tamper):
    assign(lab, "engineer")
    with transaction(lab["project"], lab["engineer"]) as c:
        aid = store_private(
            c,
            lab["project"],
            b"PRIVATE-TAMPER-SYNTHETIC",
            "benchmark_raw",
            created_by=lab["engineer"],
        )
        row = c.execute("SELECT object_key FROM anvil.artifacts WHERE id=%s", (aid,)).fetchone()
    path = Path(os.environ["ANVIL_BENCHMARK_VAULT_ROOT"]) / row["object_key"].removeprefix(
        "benchmark-vault/"
    )
    if tamper == "bytes":
        path.write_bytes(b"CORRUPTED")
    elif tamper == "world_read":
        path.chmod(0o644)
    elif tamper == "symlink":
        sibling = path.with_name("synthetic-sibling")
        path.rename(sibling)
        path.symlink_to(sibling)
    else:
        os.link(path, path.with_name("synthetic-extra-link"))
    with transaction(lab["project"], lab["engineer"]) as c:
        with pytest.raises(HTTPException) as exc:
            read_private(c, aid)
        assert exc.value.status_code == (403 if tamper == "symlink" else 409)


def test_project_private_retention_limit_cannot_be_bypassed_by_class(lab):
    stage_private_stream(lab["project"], io.BytesIO(b"A" * 50), "benchmark_raw", retained_limit=80)
    with pytest.raises(HTTPException) as exc:
        stage_private_stream(
            lab["project"], io.BytesIO(b"B" * 40), "benchmark_eval", retained_limit=80
        )
    assert exc.value.status_code == 429
    duplicate = stage_private_stream(
        lab["project"], io.BytesIO(b"A" * 50), "benchmark_raw", retained_limit=80
    )
    assert duplicate.byte_size == 50
