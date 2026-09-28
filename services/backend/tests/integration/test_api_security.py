"""Direct API negatives; real OIDC acquisition is separately covered by Playwright."""

import json
import secrets

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

from anvil import graph
from anvil.api import app
from anvil.artifacts import store
from anvil.auth import hashed
from anvil.cli import OUTSIDER_PROJECT, PROJECT
from anvil.config import ROOT
from anvil.db import transaction, uid

USERS = json.loads((ROOT / ".local/demo-identities.json").read_text())
BASE = f"/api/v1/projects/{PROJECT}"


@pytest.fixture
def client_factory():
    sessions = []

    def make(name="researcher"):
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with transaction() as c:
            c.execute(
                "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
                (hashed(token), USERS[name], hashed(csrf)),
            )
        sessions.append(hashed(token))
        client = TestClient(app)
        client.cookies.set("anvil_session", token)
        client.headers.update(
            {"Origin": "http://127.0.0.1:3202", "X-CSRF-Token": csrf, "Idempotency-Key": uid()}
        )
        return client, hashed(token)

    yield make
    with transaction() as c:
        for token_hash in sessions:
            c.execute(
                "UPDATE anvil.sessions SET revoked_at=now() WHERE token_hash=%s", (token_hash,)
            )


@pytest.mark.parametrize("state", ["expired", "idle", "revoked"])
def test_expired_idle_revoked_session(client_factory, state):
    client, token_hash = client_factory()
    statements = {
        "expired": "expires_at=now()-interval '1 second'",
        "idle": "last_seen_at=now()-interval '31 minutes'",
        "revoked": "revoked_at=now()",
    }
    with transaction() as c:
        c.execute(
            f"UPDATE anvil.sessions SET {statements[state]} WHERE token_hash=%s", (token_hash,)
        )
    assert client.get("/api/v1/me").status_code == 401


def test_logout_invalidates_captured_cookie(client_factory):
    client, _ = client_factory()
    token = client.cookies.get("anvil_session")
    assert client.post("/api/v1/auth/logout").status_code == 200
    client.cookies.set("anvil_session", token)
    assert client.get("/api/v1/me").status_code == 401


@pytest.mark.parametrize(
    "origin,csrf",
    [("https://evil.invalid", "keep"), ("", "keep"), ("http://127.0.0.1:3202", "wrong")],
)
def test_origin_and_csrf(client_factory, origin, csrf):
    client, _ = client_factory()
    headers = {"Origin": origin}
    if csrf != "keep":
        headers["X-CSRF-Token"] = csrf
    assert client.post(BASE + "/objectives", json={}, headers=headers).status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/objectives",
        "/objectives/{id}",
        "/artifacts/{id}/content",
        "/reviews/{id}",
        "/diagnostics",
        "/reports/{id}/download/evidence.zip",
        "/runs/{id}",
    ],
)
def test_cross_project_endpoint_substitution(client_factory, path):
    client, _ = client_factory()
    path = path.replace("{id}", uid())
    result = client.get(f"/api/v1/projects/{OUTSIDER_PROJECT}" + path)
    assert result.status_code == 404, result.text


@pytest.mark.parametrize("role", ["sales", "admin-1"])
def test_content_role_required(client_factory, role):
    client, _ = client_factory(role)
    for path in ("/rubrics", "/cases", "/artifacts/" + uid() + "/content"):
        assert client.get(BASE + path).status_code == 403
    assert client.post(BASE + "/objectives", json={}).status_code == 403


def objective_body():
    return {
        "title": "API security fixture",
        "origin": "adi_initiated",
        "entry_type": "capability",
        "hypothesis": "Known synthetic constraints remain satisfied.",
        "business_context": "Negative API verification, illustrative data only.",
        "measurement_plan": "Synthetic unit of work with independent scoped approval.",
        "researcher_id": USERS["researcher"],
        "advisor_id": USERS["advisor"],
        "product_owner_id": USERS["product-owner"],
    }


def test_idempotency_stale_etag_and_submitted_immutability(client_factory):
    client, _ = client_factory()
    body = objective_body()
    first = client.post(BASE + "/objectives", json=body)
    assert first.status_code == 201, first.text
    original = first.json()["data"]
    replay = client.post(BASE + "/objectives", json=body)
    assert replay.json()["data"]["id"] == original["id"]
    assert (
        client.post(BASE + "/objectives", json={**body, "title": "Changed payload"}).status_code
        == 409
    )
    path = BASE + "/objectives/" + original["id"]
    assert client.patch(path + "/draft", json=body, headers={"If-Match": "999"}).status_code == 412
    submit = client.post(
        path + "/submit", json={}, headers={"If-Match": str(original["row_version"])}
    )
    assert submit.status_code == 200, submit.text
    current = submit.json()["data"]
    assert (
        client.patch(
            path + "/draft", json=body, headers={"If-Match": str(current["row_version"])}
        ).status_code
        == 409
    )


def test_manifest_dryrun_atomic_commit_dedup_and_quarantine(client_factory):
    client, _ = client_factory("data-engineer")
    with transaction(PROJECT, USERS["data-engineer"]) as c:
        clean = store(
            c, PROJECT, b'{"synthetic_test":true}', "actor", origin="original_synthetic_fixture"
        )
        quarantine = store(c, PROJECT, b"untrusted test bytes", "internal", scan="quarantined")
        before = c.execute("SELECT count(*) n FROM anvil.resources WHERE kind='case'").fetchone()[
            "n"
        ]
    case = {
        "external_case_id": uid(),
        "source_version": "1",
        "title": "Synthetic import test",
        "subjects": ["Test"],
        "source_family_key": "test",
        "artifact_ids": [clean],
        "provenance": {"origin": "synthetic_fixture", "faculty_review_claim": None},
    }
    manifest = {
        "schema_version": "anvil.case_import.v1",
        "partner_key": "integration-fixture",
        "cases": [case],
    }

    def preview(value):
        response = client.post(
            BASE + "/imports/validate", json=value, headers={"Idempotency-Key": uid()}
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]

    def commit(batch):
        return client.post(
            BASE + "/imports/" + batch["id"] + "/commit",
            json={"manifest_hash": batch["manifest_hash"]},
            headers={"Idempotency-Key": uid()},
        )

    rejected = preview(
        {
            **manifest,
            "cases": [case, {**case, "external_case_id": uid(), "artifact_ids": [quarantine]}],
        }
    )
    assert rejected["status"] == "rejected" and rejected["errors"][0]["row"] == 1
    assert commit(rejected).status_code == 409
    batch = preview(manifest)
    assert batch["status"] == "validated"
    with transaction(PROJECT, USERS["data-engineer"]) as c:
        assert (
            c.execute("SELECT count(*) n FROM anvil.resources WHERE kind='case'").fetchone()["n"]
            == before
        )
    first = commit(batch)
    assert first.status_code == 200, first.text
    ids = first.json()["data"]["source_ids"]
    assert commit(batch).json()["data"]["source_ids"] == ids
    assert commit(preview(manifest)).json()["data"]["source_ids"] == ids
    source = client.get(BASE + "/cases/" + ids[0]).json()["data"]
    assert source["content"]["faculty_validation"] is None
    assert source["content"]["rights_status"] == "unknown"
    assert source["rights"] == []
    conflict = preview({**manifest, "cases": [{**case, "title": "Changed original"}]})
    assert conflict["status"] == "rejected"
    assert conflict["errors"][0]["code"] == "source_version_conflict"
    duplicate = preview({**manifest, "cases": [case, case]})
    assert any(e["code"] == "duplicate_external_id" for e in duplicate["errors"])
    with transaction(PROJECT, USERS["data-engineer"]) as c:
        assert (
            c.execute("SELECT count(*) n FROM anvil.resources WHERE kind='case'").fetchone()["n"]
            == before + 1
        )


def test_graph_rebuild_replay_and_unavailable_fallback(client_factory, monkeypatch):
    client, _ = client_factory()
    first = graph.project_graph(PROJECT)
    second = graph.project_graph(PROJECT)
    assert first == second
    result = client.get(BASE + "/diagnostics").json()["data"]
    assert result["projection_status"] == "current"
    assert result["nodes"] == first["nodes"]
    assert all(n["kind"] != "rubric" for n in result["nodes"])

    def unavailable():
        raise ServiceUnavailable("Controlled graph outage")

    monkeypatch.setattr(graph, "driver", unavailable)
    fallback = client.get(BASE + "/diagnostics").json()["data"]
    assert fallback["projection_status"] == "unavailable"
    assert fallback["nodes"] == result["nodes"] and fallback["edges"] == result["edges"]
    assert client.get(BASE + "/diagnostics?depth=4").status_code == 422


def test_invalid_and_reused_login_state(client_factory):
    client, _ = client_factory()
    assert client.get("/api/v1/auth/callback?state=bad&code=bad").status_code == 401
    state = secrets.token_urlsafe(32)
    with transaction() as c:
        c.execute(
            "INSERT INTO anvil.oidc_login_attempts(state_hash,nonce_hash,verifier_cipher,consumed_at) VALUES(%s,%s,%s,now())",
            (hashed(state), hashed("nonce"), "unused"),
        )
    client.cookies.set("anvil_login", state)
    assert (
        client.get("/api/v1/auth/callback", params={"state": state, "code": "unused"}).status_code
        == 401
    )
