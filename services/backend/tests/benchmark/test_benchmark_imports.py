import asyncio
import base64
import gzip
import hashlib
import io
import json
import os
import tarfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from test_private_storage import assign, connection
from test_private_storage import lab as storage_lab

from anvil.api import app
from anvil.benchmark_archive import ArchiveError
from anvil.benchmark_ingest import inspect_original, intake_file, prepare_original
from anvil.config import ROOT

lab = storage_lab


def archive(signature=None):
    fixture = ROOT / "fixtures/benchmark-bundle/fictional-points-v1"
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as stream:
        for path in sorted(fixture.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                header = tarfile.TarInfo(str(path.relative_to(fixture)))
                header.size = len(data)
                stream.addfile(header, io.BytesIO(data))
        if signature is not None:
            header = tarfile.TarInfo("signature.json")
            header.size = len(signature)
            stream.addfile(header, io.BytesIO(signature))
    return gzip.compress(raw.getvalue(), mtime=0)


@pytest.fixture
def client(lab):
    token, csrf = uuid4().hex, uuid4().hex
    with connection() as c:
        c.execute(
            "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                lab["engineer"],
                hashlib.sha256(csrf.encode()).hexdigest(),
            ),
        )
    with TestClient(app) as current:
        current.cookies.set("anvil_session", token)
        current.headers.update(
            {
                "origin": os.environ["WEB_ORIGIN"],
                "x-csrf-token": csrf,
                "content-type": "application/gzip",
                "idempotency-key": uuid4().hex,
            }
        )
        yield current


def route(lab):
    return f"/api/v1/projects/{lab['project']}/workspace/benchmarks/imports"


def test_unsigned_archive_stays_quarantined_and_private_with_exact_originals(client, lab):
    assign(lab, "engineer")
    raw = archive()
    response = client.post(route(lab), content=raw)
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["source_state"] == "quarantined"
    assert result["signature_status"] == "unsigned"
    assert result["archive_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["task_count"] == 3
    assert "object_key" not in response.text and "eval_pack" not in response.text
    with connection() as c:
        row = c.execute(
            "SELECT archive_artifact_id,raw_manifest_artifact_id,canonical_manifest_artifact_id FROM anvil.benchmark_bundle_receipts WHERE id=%s",
            (result["receipt_id"],),
        ).fetchone()
        assert all(row.values())
    for artifact_id in row.values():
        content = client.get(f"/api/v1/projects/{lab['project']}/artifacts/{artifact_id}/content")
        assert content.status_code == 403
    assert client.get(route(lab) + "/" + result["receipt_id"]).json()["data"] == result
    errors = client.get(route(lab) + "/" + result["receipt_id"] + "/errors").json()["data"]
    assert errors["errors"][0]["code"] == "source_unsigned"


def test_exact_duplicate_returns_receipt_but_repacked_same_version_conflicts(client, lab):
    assign(lab, "engineer")
    raw = archive()
    first = client.post(route(lab), content=raw)
    assert first.status_code == 200
    client.headers["idempotency-key"] = uuid4().hex
    second = client.post(route(lab), content=raw)
    assert second.status_code == 200
    assert first.json()["data"] == second.json()["data"]
    repacked = gzip.compress(gzip.decompress(raw), mtime=1)
    client.headers["idempotency-key"] = uuid4().hex
    conflict = client.post(route(lab), content=repacked)
    assert conflict.status_code == 409
    assert "eval_pack" not in conflict.text


def test_changed_bytes_with_same_idempotency_key_conflicts_without_new_receipt(client, lab):
    assign(lab, "engineer")
    assert client.post(route(lab), content=archive()).status_code == 200
    conflict = client.post(route(lab), content=b"different body")
    assert conflict.status_code == 409
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_bundle_receipts WHERE project_id=%s",
                (lab["project"],),
            ).fetchone()["n"]
            == 1
        )


@pytest.mark.parametrize(
    "case,status",
    [("missing_key", 428), ("csrf", 403), ("assignment", 403), ("cross_project", 404)],
)
def test_command_controls_fail_before_receipt_creation(client, lab, case, status):
    if case != "assignment":
        assign(lab, "engineer")
    path = route(lab)
    if case == "missing_key":
        del client.headers["idempotency-key"]
    elif case == "csrf":
        del client.headers["x-csrf-token"]
    elif case == "cross_project":
        path = path.replace(lab["project"], lab["other_project"])
    response = client.post(path, content=archive())
    assert response.status_code == status
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_bundle_receipts WHERE project_id=%s",
                (lab["project"],),
            ).fetchone()["n"]
            == 0
        )


def test_rejected_original_retained_privately_without_accepted_receipt(client, lab):
    assign(lab, "engineer")
    raw = b"not a gzip archive; original fictional malformed bytes"
    response = client.post(route(lab), content=raw)
    assert response.status_code == 422
    assert raw.decode() not in response.text
    with connection() as c:
        artifact = c.execute(
            "SELECT id,classification FROM anvil.artifacts WHERE project_id=%s AND sha256=%s",
            (lab["project"], hashlib.sha256(raw).hexdigest()),
        ).fetchone()
        assert artifact and artifact["classification"] == "benchmark_raw"
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_bundle_receipts WHERE project_id=%s",
                (lab["project"],),
            ).fetchone()["n"]
            == 0
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.audit_events WHERE project_id=%s AND action='benchmark.import.rejected'",
                (lab["project"],),
            ).fetchone()["n"]
            == 1
        )


def test_cross_project_receipt_and_errors_return_uniform_not_found(client, lab):
    assign(lab, "engineer")
    imported = client.post(route(lab), content=archive())
    assert imported.status_code == 200
    rid = imported.json()["data"]["receipt_id"]
    for suffix in ["", "/errors"]:
        response = client.get(
            route(lab).replace(lab["project"], lab["other_project"]) + "/" + rid + suffix
        )
        assert response.status_code == 404


@contextmanager
def setting(name, value):
    previous = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def test_known_public_policy_accepts_signature_but_does_not_create_runs(client, lab, tmp_path):
    assign(lab, "engineer")
    private = Ed25519PrivateKey.generate()
    manifest = json.loads(
        (ROOT / "fixtures/benchmark-bundle/fictional-points-v1/manifest.json").read_bytes()
    )
    signature = json.dumps(
        {
            "profile": "ed25519-jcs-v1",
            "algorithm": "Ed25519",
            "key_id": "original-test-root",
            "signature_base64": base64.b64encode(private.sign(rfc8785.dumps(manifest))).decode(),
        }
    ).encode()
    policy = {
        "schema_version": "anvil.benchmark.trust.v1",
        "keys": [
            {
                "key_id": "original-test-root",
                "public_key_base64": base64.b64encode(
                    private.public_key().public_bytes_raw()
                ).decode(),
                "not_before": "2026-01-01T00:00:00Z",
                "not_after": "2027-01-01T00:00:00Z",
                "revoked": False,
            }
        ],
    }
    public_policy = tmp_path / "benchmark-trust-policy.json"
    public_policy.write_text(json.dumps(policy))
    public_policy.chmod(0o600)
    with setting("ANVIL_BENCHMARK_TRUST_POLICY", str(public_policy)):
        response = client.post(route(lab), content=archive(signature))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["signature_status"] == "verified"
    assert response.json()["data"]["source_state"] == "accepted"
    with connection() as c:
        for table in ["runs", "jobs", "budget_reservations", "benchmark_qualifications"]:
            assert (
                c.execute(
                    "SELECT count(*) AS n FROM anvil." + table + " WHERE project_id=%s",
                    (lab["project"],),
                ).fetchone()["n"]
                == 0
            )


def test_import_feature_defaults_disabled_and_does_not_accept(client, lab):
    assign(lab, "engineer")
    with setting("ANVIL_BENCHMARK_ENABLED", None):
        assert client.post(route(lab), content=archive()).status_code == 503
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_bundle_receipts WHERE project_id=%s",
                (lab["project"],),
            ).fetchone()["n"]
            == 0
        )


def test_actual_project_intake_permits_enforce_limit_and_release_owned_staging(client, lab):
    assign(lab, "engineer")
    with intake_file(lab["project"]):
        with intake_file(lab["project"]):
            assert client.post(route(lab), content=archive()).status_code == 429
    assert client.post(route(lab), content=archive()).status_code == 200
    folder = ROOT / ".local/benchmark-vault/.intake" / lab["project"]
    assert list(folder.glob(".upload-*")) == []


def test_two_actual_concurrent_imports_share_one_receipt(client, lab):
    assign(lab, "engineer")
    raw = archive()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(route(lab), content=raw), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json()["data"] == responses[1].json()["data"]
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_bundle_receipts WHERE project_id=%s",
                (lab["project"],),
            ).fetchone()["n"]
            == 1
        )


def test_real_asgi_disconnect_leaves_no_receipt_and_removes_only_owned_partial(client, lab):
    assign(lab, "engineer")
    path = route(lab)
    headers = [(k.encode(), v.encode()) for k, v in client.headers.items()]
    cookie = "; ".join(k + "=" + v for k, v in client.cookies.items())
    headers.append((b"cookie", cookie.encode()))
    messages = iter(
        [
            {"type": "http.request", "body": archive()[:50], "more_body": True},
            {"type": "http.disconnect"},
        ]
    )
    sent = []

    async def receive():
        return next(messages, {"type": "http.disconnect"})

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 20000),
        "root_path": "",
    }
    asyncio.run(asyncio.wait_for(app(scope, receive, send), timeout=10))
    assert not any(m.get("status") == 200 for m in sent)
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_bundle_receipts WHERE project_id=%s",
                (lab["project"],),
            ).fetchone()["n"]
            == 0
        )
    folder = ROOT / ".local/benchmark-vault/.intake" / lab["project"]
    assert list(folder.glob(".upload-*")) == []


def test_changed_staging_bytes_cannot_bind_old_original_hash(lab):
    raw = archive()
    with intake_file(lab["project"]) as stream:
        stream.write(raw)
        stream.flush()
        stream.seek(0)
        prepared = prepare_original(lab["project"], stream)
        stream.seek(0)
        stream.write(gzip.compress(gzip.decompress(raw), mtime=1))
        stream.truncate()
        stream.flush()
        stream.seek(0)
        with pytest.raises(ArchiveError) as exc:
            inspect_original(
                lab["project"],
                stream,
                now=datetime.now(timezone.utc),
                expected_sha256=prepared.sha256,
            )
        assert exc.value.code == "staged_original_changed"
