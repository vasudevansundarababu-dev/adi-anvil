"""Direct API negatives; real OIDC acquisition is separately covered by Playwright."""

import json
import secrets
import time

import httpx
import pytest
from authlib.jose import JsonWebKey, JsonWebToken
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

from anvil import auth, graph
from anvil.api import app
from anvil.artifacts import store
from anvil.auth import hashed
from anvil.cli import OUTSIDER_PROJECT, PROJECT
from anvil.config import ROOT, setting
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
    root_id = result["edges"][0]["source"]
    neighborhood = client.get(BASE + "/graph", params={"root": root_id, "depth": 1}).json()["data"]
    expected = {root_id}
    expected.update(e["target"] for e in result["edges"] if e["source"] == root_id)
    expected.update(e["source"] for e in result["edges"] if e["target"] == root_id)
    assert {n["id"] for n in neighborhood["nodes"]} == expected
    assert client.get(BASE + "/graph", params={"root": uid()}).status_code == 404

    def unavailable():
        raise ServiceUnavailable("Controlled graph outage")

    monkeypatch.setattr(graph, "driver", unavailable)
    fallback = client.get(BASE + "/diagnostics").json()["data"]
    assert fallback["projection_status"] == "unavailable"
    assert fallback["nodes"] == result["nodes"] and fallback["edges"] == result["edges"]
    assert client.get(BASE + "/diagnostics?depth=4").status_code == 422


def test_successor_and_withdrawal_preserve_history(client_factory):
    client, _ = client_factory()
    body = objective_body()
    original = client.post(BASE + "/objectives", json=body).json()["data"]
    path = BASE + "/objectives/" + original["id"]
    submitted = client.post(
        path + "/submit", json={}, headers={"If-Match": str(original["row_version"])}
    ).json()["data"]
    successor = client.post(
        path + "/successor",
        json={**body, "title": "Revised synthetic question"},
        headers={"If-Match": str(submitted["row_version"])},
    ).json()["data"]
    assert successor["lifecycle"] == "draft"
    assert successor["current_revision_id"] != original["current_revision_id"]
    with transaction(PROJECT, USERS["researcher"]) as c:
        old = c.execute(
            "SELECT content FROM anvil.revisions WHERE id=%s", (original["current_revision_id"],)
        ).fetchone()
        assert old["content"]["title"] == body["title"]
    withdrawn = client.post(
        path + "/withdraw",
        json={"reason": "Synthetic correction requires withdrawal"},
        headers={"If-Match": str(successor["row_version"])},
    ).json()["data"]
    assert withdrawn["lifecycle"] == "withdrawn"
    graph_data = client.get(BASE + "/diagnostics").json()["data"]
    assert not any(n["resource_id"] == original["id"] for n in graph_data["nodes"])


@pytest.mark.parametrize(
    "invalid", ["issuer", "audience", "nonce", "expired", "signature", "none", "valid"]
)
def test_signed_oidc_claim_validation(client_factory, monkeypatch, invalid):
    client, _ = client_factory()
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with transaction() as c:
        c.execute(
            "INSERT INTO anvil.oidc_login_attempts(state_hash,nonce_hash,verifier_cipher) VALUES(%s,%s,%s)",
            (
                hashed(state),
                hashed(nonce),
                auth.cipher().encrypt(b"synthetic-test-verifier").decode(),
            ),
        )
    client.cookies.set("anvil_login", state)
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    claims = {
        "iss": setting("OIDC_ISSUER"),
        "aud": setting("OIDC_CLIENT_ID"),
        "sub": USERS["researcher"],
        "exp": int(time.time()) + 60,
        "nonce": nonce,
    }
    if invalid == "issuer":
        claims["iss"] = "https://untrusted.invalid"
    if invalid == "audience":
        claims["aud"] = "different-client"
    if invalid == "nonce":
        claims["nonce"] = "wrong-nonce"
    if invalid == "expired":
        claims["exp"] = int(time.time()) - 60
    signing_key = (
        JsonWebKey.generate_key("RSA", 2048, is_private=True) if invalid == "signature" else key
    )
    if invalid == "none":
        import base64

        def encoded(b):
            return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

        token = encoded(b'{"alg":"none"}') + "." + encoded(json.dumps(claims).encode()) + "."
    else:
        token = JsonWebToken(["RS256"]).encode({"alg": "RS256"}, claims, signing_key).decode()

    class MockOIDC:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            return httpx.Response(200, json={"id_token": token}, request=httpx.Request("POST", url))

        def get(self, url):
            return httpx.Response(
                200,
                json={"keys": [key.as_dict(is_private=False)]},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(auth.httpx, "Client", MockOIDC)
    response = client.get(
        "/api/v1/auth/callback", params={"state": state, "code": "test"}, follow_redirects=False
    )
    assert response.status_code == (307 if invalid == "valid" else 401), response.text
    assert (
        client.get(
            "/api/v1/auth/callback", params={"state": state, "code": "test"}, follow_redirects=False
        ).status_code
        == 401
    )
    if invalid == "valid":
        with transaction() as c:
            c.execute(
                "UPDATE anvil.sessions SET revoked_at=now() WHERE token_hash=%s",
                (hashed(response.cookies.get("anvil_session")),),
            )


def test_fixture_delivery_bound_approval_unknown_replay_and_suppression(
    client_factory, monkeypatch
):
    from anvil import delivery

    # Prevent background pickup so revocation can be exercised between queue and worker.
    monkeypatch.setattr(delivery, "enqueue", lambda *args: None)
    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    project = journey.get("project_id", PROJECT)
    base = f"/api/v1/projects/{project}"
    clients = {
        name: client_factory(name)[0]
        for name in [
            "researcher",
            "advisor",
            "reviewer-1",
            "product-owner",
            "sales",
            "admin-1",
            "admin-2",
        ]
    }

    def post(name, path, body, version=None, expected=200):
        headers = {"Idempotency-Key": uid()}
        if version:
            headers["If-Match"] = str(version)
        result = clients[name].post(base + path, json=body, headers=headers)
        assert result.status_code == expected, result.text
        return result.json().get("data")

    report = post(
        "researcher",
        "/reports",
        {
            "title": "Fixture delivery guard test",
            "run_id": journey["run_id"],
            "finding_revision_ids": [],
            "advisor_id": USERS["advisor"],
            "reviewer_id": USERS["reviewer-1"],
            "product_owner_id": USERS["product-owner"],
            "audience": "internal_fixture",
        },
        expected=201,
    )
    path = "/reports/" + report["id"]
    report = post("researcher", path + "/submit", {}, report["row_version"])
    for role, purpose in [
        ("advisor", "technical"),
        ("reviewer-1", "domain"),
        ("product-owner", "audience"),
        ("product-owner", "release"),
    ]:
        report = post(
            role,
            path + "/decisions",
            {
                "purpose": purpose,
                "decision": "approve",
                "rationale": "Independent synthetic delivery pipeline verification.",
            },
            report["row_version"],
        )
    kit = post("researcher", path + "/build", {}, report["row_version"])
    post(
        "sales",
        "/sales-contacts",
        {
            "name": "Synthetic recipient",
            "email": "real@example.com",
            "organization_label": "Fixture",
            "contact_basis": "Synthetic fixture only",
        },
        expected=422,
    )
    for scenario in ("accepted", "failed", "unknown", "suppressed"):
        contact = post(
            "sales",
            "/sales-contacts",
            {
                "name": "Synthetic recipient",
                "email": "test@fixture.invalid",
                "organization_label": "Fixture",
                "contact_basis": "Synthetic test, no real contact or sending authority.",
            },
        )
        contact = post(
            "product-owner",
            "/sales-contacts/" + contact["id"] + "/decision",
            {"status": "approved"},
            contact["row_version"],
        )
        sender = post(
            "admin-1",
            "/fixture-senders",
            {
                "name": "Network-free test sender",
                "scenario": "accepted" if scenario == "suppressed" else scenario,
            },
        )
        post(
            "admin-1",
            "/fixture-senders/" + sender["id"] + "/activate",
            {},
            sender["row_version"],
            expected=409,
        )
        sender = post(
            "admin-2", "/fixture-senders/" + sender["id"] + "/activate", {}, sender["row_version"]
        )
        approval_body = {
            "recipient_contact_id": contact["id"],
            "sender_connection_id": sender["id"],
        }
        approval = post(
            "product-owner", "/sales-kits/" + kit["id"] + "/delivery-approvals", approval_body
        )
        send_body = {
            "delivery_approval_id": approval["id"],
            "content_hash": approval["content_hash"],
        }
        record = post("sales", "/sales-kits/" + kit["id"] + "/simulate-send", send_body)
        if scenario == "suppressed":
            post(
                "product-owner",
                "/sales-contacts/" + contact["id"] + "/decision",
                {"status": "suppressed"},
                contact["row_version"],
            )
        job = {"target_id": record["id"], "project_id": project}
        with transaction(project, worker=True) as c:
            delivery.dispatch_fixture(c, job)
            delivery.dispatch_fixture(c, job)
        state = clients["sales"].get(base + "/sales-deliveries/" + record["id"]).json()["data"]
        assert state["status"] == ("blocked" if scenario == "suppressed" else "fixture_" + scenario)
        assert state["attempts"] == (0 if scenario == "suppressed" else 1)
        assert state["real_email_sent"] is False
        if scenario != "suppressed":
            new_approval = post(
                "product-owner", "/sales-kits/" + kit["id"] + "/delivery-approvals", approval_body
            )
            replay = post(
                "sales",
                "/sales-kits/" + kit["id"] + "/simulate-send",
                {
                    "delivery_approval_id": new_approval["id"],
                    "content_hash": new_approval["content_hash"],
                },
            )
            assert replay["id"] == record["id"]


@pytest.mark.parametrize(
    "filename,payload,mime",
    [
        ("../../escape.exe", b"MZ harmless non-executable test bytes", "application/pdf"),
        (
            "macro.docm",
            b"PK\\x03\\x04 harmless macro-container marker",
            "application/vnd.ms-word.document.macroEnabled.12",
        ),
        ("bomb.zip", b"PK\\x03\\x04 truncated archive; never decompressed", "application/zip"),
        ("mismatch.png", b"not an image", "image/png"),
    ],
)
def test_untrusted_uploads_stay_quarantined_without_parsing(
    client_factory, filename, payload, mime
):
    client, _ = client_factory("data-engineer")
    response = client.post(BASE + "/artifacts", files={"file": (filename, payload, mime)})
    assert response.status_code == 200, response.text
    artifact = response.json()["data"]
    assert artifact["scan_status"] == "quarantined"
    assert client.get(BASE + "/artifacts/" + artifact["id"] + "/content").status_code == 403
    with transaction(PROJECT, USERS["data-engineer"]) as c:
        row = c.execute(
            "SELECT object_key,scan_status FROM anvil.artifacts WHERE id=%s", (artifact["id"],)
        ).fetchone()
        assert ".." not in row["object_key"] and filename not in row["object_key"]


def test_oversized_upload_rejected_before_artifact_storage(client_factory):
    client, _ = client_factory("data-engineer")
    with transaction(PROJECT, USERS["data-engineer"]) as c:
        before = c.execute("SELECT count(*) n FROM anvil.artifacts").fetchone()["n"]
    response = client.post(
        BASE + "/artifacts",
        files={"file": ("oversized.txt", b"x" * (26 * 1024 * 1024), "text/plain")},
    )
    assert response.status_code == 413
    with transaction(PROJECT, USERS["data-engineer"]) as c:
        assert c.execute("SELECT count(*) n FROM anvil.artifacts").fetchone()["n"] == before


def test_task_missing_duplicate_cross_source_and_unsupported_inputs(client_factory):
    client, _ = client_factory()
    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    base = f"/api/v1/projects/{journey['project_id']}"
    tasks = [
        t
        for t in client.get(base + "/tasks?limit=100").json()["data"]
        if t["lifecycle"] == "published"
    ]
    source = tasks[0]["content"]
    for body in (
        {**source, "actor_artifact_ids": source["actor_artifact_ids"][:1]},
        {**source, "actor_artifact_ids": [source["actor_artifact_ids"][0]] * 2},
    ):
        assert (
            client.post(base + "/tasks", json=body, headers={"Idempotency-Key": uid()}).status_code
            == 422
        )
    for body in (
        {**source, "mode": "interactive"},
        {
            **source,
            "actor_artifact_ids": [
                tasks[1]["content"]["actor_artifact_ids"][0],
                source["actor_artifact_ids"][1],
            ],
        },
    ):
        response = client.post(base + "/tasks", json=body, headers={"Idempotency-Key": uid()})
        assert response.status_code == 201, response.text
        draft = response.json()["data"]
        rejected = client.post(
            base + "/tasks/" + draft["id"] + "/submit",
            json={},
            headers={"Idempotency-Key": uid(), "If-Match": str(draft["row_version"])},
        )
        assert rejected.status_code == 409, rejected.text


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
