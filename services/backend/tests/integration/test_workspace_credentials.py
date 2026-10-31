from test_api_security import USERS
from test_praxis_harbor import BASE

from anvil import workspace_credentials, workspace_secrets
from anvil.cli import OUTSIDER_PROJECT, PROJECT
from anvil.db import one, transaction, uid


def test_write_only_local_credentials_rotation_revocation_and_profile_binding(
    client_factory, tmp_path, monkeypatch
):
    monkeypatch.setattr(workspace_secrets, "ROOT", tmp_path)
    monkeypatch.setattr(workspace_secrets, "CLOUD", False)
    admin, _ = client_factory("admin-1")
    researcher, _ = client_factory("researcher")
    path = BASE + "/workspace/credentials"
    secret = "test-only-never-a-provider-key-" + uid()
    body = {"name": "Test-only credential lifecycle", "provider": "openai", "secret": secret}
    assert researcher.post(path, json=body).status_code == 403
    assert researcher.get(path).status_code == 403
    key = uid()
    first = admin.post(path, json=body, headers={"Idempotency-Key": key})
    assert first.status_code == 200, first.text
    assert secret not in first.text and "secret_reference" not in first.text
    record = first.json()["data"]
    cid, original_version = record["id"], record["current_version_id"]
    try:
        replay = admin.post(path, json=body, headers={"Idempotency-Key": key})
        assert replay.json()["data"] == record
        listed = admin.get(path)
        assert secret not in listed.text
        with transaction(PROJECT, USERS["admin-1"]) as c:
            assert (
                workspace_credentials.resolve(c, cid, original_version).get_secret_value() == secret
            )
            ref = one(
                c,
                "SELECT secret_reference FROM anvil.workspace_credential_versions WHERE id=%s",
                (original_version,),
            )["secret_reference"]
            assert secret.encode() not in (workspace_secrets.directory() / str(ref)).read_bytes()
            audit = c.execute(
                "SELECT metadata FROM anvil.audit_events WHERE target_id=%s", (cid,)
            ).fetchall()
            assert secret not in str(audit)
        with transaction(OUTSIDER_PROJECT, USERS["outsider"]) as c:
            try:
                workspace_credentials.resolve(c, cid, original_version)
                raise AssertionError("Foreign credential resolved")
            except workspace_secrets.StoreUnavailable:
                pass
        model = admin.post(
            BASE + "/workspace/models",
            json={
                "name": "Test-only bound profile",
                "provider": "openai",
                "model_id": "test-model",
                "credential_id": cid,
            },
            headers={"Idempotency-Key": uid()},
        )
        assert model.status_code == 200 and model.json()["data"]["credential_state"] == "configured"
        mismatch = admin.post(
            BASE + "/workspace/models",
            json={
                "name": "Wrong provider",
                "provider": "gemini",
                "model_id": "test-model",
                "credential_id": cid,
            },
            headers={"Idempotency-Key": uid()},
        )
        assert mismatch.status_code == 404
        second = admin.post(
            path + f"/{cid}/versions",
            json={"secret": "rotated-test-only-" + uid()},
            headers={"Idempotency-Key": uid()},
        )
        assert (
            second.status_code == 200
            and second.json()["data"]["current_version_id"] != original_version
        )
        with transaction(PROJECT, USERS["admin-1"]) as c:
            try:
                workspace_credentials.resolve(c, cid, original_version)
                raise AssertionError("Rotated version resolved for new dispatch")
            except workspace_secrets.StoreUnavailable:
                pass
        admin.headers.pop("X-CSRF-Token")
        assert admin.post(path, json=body).status_code == 403
    finally:
        fresh, _ = client_factory("admin-1")
        revoked = fresh.post(path + f"/{cid}/revoke", headers={"Idempotency-Key": uid()})
        assert revoked.status_code == 200 and revoked.json()["data"]["revoked_at"]
        assert (
            fresh.post(
                path + f"/{cid}/versions",
                json={"secret": "not-active"},
                headers={"Idempotency-Key": uid()},
            ).status_code
            == 409
        )


def test_cloud_credential_writes_fail_closed(client_factory, monkeypatch):
    monkeypatch.setattr(workspace_credentials, "CLOUD", True)
    admin, _ = client_factory("admin-1")
    result = admin.post(
        BASE + "/workspace/credentials",
        json={
            "name": "Must not be saved",
            "provider": "openai",
            "secret": "cloud-test-only-secret",
        },
    )
    assert result.status_code == 409 and "cloud-test-only-secret" not in result.text
