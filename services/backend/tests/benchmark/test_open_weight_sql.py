"""Fresh isolated SQL/API controls; synthetic tokens only, never external calls."""

import os
import secrets

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from anvil import open_weight_catalog, workspace_credentials, workspace_secrets
from anvil.api import app
from anvil.auth import hashed
from anvil.db import transaction, uid


def test_shared_hf_credential_project_isolation_rotation_and_immutable_revisions(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(workspace_secrets, "ROOT", tmp_path)
    monkeypatch.setattr(workspace_secrets, "CLOUD", False)
    dsn = os.environ["ANVIL_BENCHMARK_TEST_DATABASE_URL"]
    org, project, outsider, user = (uid() for _ in range(4))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        assert c.info.dbname.startswith("anvil_golden_kyc_")
        c.execute("INSERT INTO anvil.organizations VALUES(%s,'Open Weight synthetic test')", (org,))
        for p in (project, outsider):
            c.execute(
                "INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,'Synthetic test')",
                (p, org),
            )
        c.execute(
            "INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,'test',%s,'Synthetic test')",
            (user, org, user),
        )
        for p in (project, outsider):
            c.execute(
                "INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,'admin')",
                (p, user),
            )
        c.execute(
            "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
            (hashed(token), user, hashed(csrf)),
        )
    client = TestClient(app)
    client.cookies.set("anvil_session", token)
    client.headers.update({"Origin": "http://127.0.0.1:3202", "X-CSRF-Token": csrf})
    base = f"/api/v1/projects/{project}/workspace"

    def post(path, body, **headers):
        return client.post(path, json=body, headers={"Idempotency-Key": uid(), **headers})

    key_body = {
        "name": "Shared synthetic HF token",
        "provider": "huggingface",
        "secret": "test-only-not-a-real-hf-token",
    }
    result = post(base + "/credentials", key_body)
    assert result.status_code == 200, result.text
    assert key_body["secret"] not in result.text
    credential = result.json()["data"]
    body = {
        "name": "Synthetic open weight model",
        "provider": "huggingface",
        "model_id": "test-owner/test-model",
        "open_weight_catalog_id": "ow-r2-v1",
        "hub_revision": "a" * 40,
        "credential_id": credential["id"],
        "credential_version_id": credential["current_version_id"],
    }
    first = post(base + "/models", body)
    assert first.status_code == 200, first.text
    m1 = first.json()["data"]
    second = post(
        base + "/models", body | {"model_id": "test-owner/second-model", "hub_revision": "b" * 40}
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["credential_binding"] == m1["credential_binding"]
    assert m1["group"] == "open-weight-models" and m1["hub"]["revision"] == "a" * 40
    assert m1["launch_available"] is False
    foreign = post(f"/api/v1/projects/{outsider}/workspace/models", body)
    assert foreign.status_code == 404
    with transaction(outsider, user) as c:
        assert (
            c.execute(
                "SELECT id FROM anvil.workspace_credentials WHERE id=%s", (credential["id"],)
            ).fetchone()
            is None
        )
    rotated = post(
        base + "/credentials/" + credential["id"] + "/versions",
        {"secret": "test-only-successor-token"},
    )
    assert rotated.status_code == 200, rotated.text
    stale = post(base + "/models", body)
    assert stale.status_code == 409
    config = client.get(base + "/models/" + m1["id"] + "/configuration").json()["data"]
    assert config["credential_state"] == "rotated" and config["hub"] == m1["hub"]
    assert config["credential_binding"] == m1["credential_binding"]
    with transaction(project, user) as c:
        try:
            workspace_credentials.resolve(c, credential["id"], credential["current_version_id"])
            raise AssertionError("Rotated token resolved")
        except workspace_secrets.StoreUnavailable:
            pass
    catalog = client.get(base + "/models/catalog")
    assert catalog.status_code == 200 and len(catalog.json()["data"]["items"]) == 24
    assert not catalog.json()["data"]["live_available"]
    observed = open_weight_catalog.catalog()["items"][0]
    repo = observed["repositories"][0]
    registration = {
        "models": [
            {
                "catalog_id": observed["id"],
                "repository": repo["repository"],
                "revision": repo["revision"],
            }
        ],
        "credential_id": credential["id"],
        "credential_version_id": rotated.json()["data"]["current_version_id"],
    }
    register = post(base + "/models/catalog/register", registration)
    assert register.status_code == 200, register.text
    repeated = post(base + "/models/catalog/register", registration)
    assert (
        repeated.status_code == 200
        and repeated.json()["data"]["items"][0]["id"] == register.json()["data"]["items"][0]["id"]
    )
    foreign = post(f"/api/v1/projects/{outsider}/workspace/models/catalog/register", registration)
    assert foreign.status_code == 404
    stale_group = post(
        base + "/models/catalog/register",
        registration | {"credential_version_id": credential["current_version_id"]},
    )
    assert stale_group.status_code == 409
    all_models = [
        {"catalog_id": item["id"], "repository": r["repository"], "revision": r["revision"]}
        for item in open_weight_catalog.catalog()["items"]
        for r in item["repositories"]
    ]
    registered = post(base + "/models/catalog/register", registration | {"models": all_models})
    assert registered.status_code == 200, registered.text
    values = registered.json()["data"]["items"]
    assert len(values) == 32 and len({v["id"] for v in values}) == 32
    assert all(v["credential_binding"] == values[0]["credential_binding"] for v in values)
    assert all(not v["launch_available"] for v in values)
    revoked = post(base + "/credentials/" + credential["id"] + "/revoke", {})
    assert revoked.status_code == 200, revoked.text
    denied = post(base + "/models/catalog/register", registration)
    assert denied.status_code == 409
    original = client.get(base + "/models/" + m1["id"] + "/configuration").json()["data"]
    assert original["credential_state"] == "revoked" and original["hub"] == m1["hub"]
