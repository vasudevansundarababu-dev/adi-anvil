import base64
import json
import os

import pytest

from anvil import cloud_secrets


def test_managed_generation_secret_roundtrip_and_binding_fence(tmp_path, monkeypatch):
    os.chmod(tmp_path, 0o700)
    monkeypatch.setenv("ANVIL_CLOUD_SECRET_INDEX", str(tmp_path))
    resource = "projects/123456/secrets/anvil-import-generation"
    monkeypatch.setenv("ANVIL_GENERATION_SECRET_RESOURCE", resource)
    calls = []
    payload = {}

    def request(method, path, body=None):
        calls.append((method, path))
        if method == "POST":
            payload.update(body)
            return {"name": resource + "/versions/1"}
        return {"name": resource + "/versions/1", **payload}

    monkeypatch.setattr(cloud_secrets, "request", request)
    binding = {
        "scope": "installation_import_generation",
        "settings_id": "test",
        "provider": "openai",
    }
    identifier = cloud_secrets.save("fake-key-not-real", binding)
    assert "fake-key" not in (tmp_path / identifier).read_text()
    assert cloud_secrets.load(identifier, binding) == "fake-key-not-real"
    with pytest.raises(ValueError, match="binding"):
        cloud_secrets.load(identifier, {**binding, "settings_id": "different"})
    with pytest.raises(ValueError, match="evaluation"):
        cloud_secrets.save("fake", {"scope": "evaluation"})
    assert len([c for c in calls if c[0] == "POST"]) == 1
    decoded = json.loads(base64.b64decode(payload["payload"]["data"]))
    assert decoded["binding"] == binding


def test_managed_secret_locator_cannot_select_another_secret(tmp_path, monkeypatch):
    os.chmod(tmp_path, 0o700)
    monkeypatch.setenv("ANVIL_CLOUD_SECRET_INDEX", str(tmp_path))
    monkeypatch.setenv(
        "ANVIL_GENERATION_SECRET_RESOURCE", "projects/123/secrets/anvil-import-generation"
    )
    name = "10000000-0000-4000-8000-000000000001"
    path = tmp_path / name
    path.write_text(json.dumps({"version": "projects/123/secrets/unrelated/versions/1"}))
    os.chmod(path, 0o600)
    with pytest.raises(ValueError, match="locator"):
        cloud_secrets.load(
            name,
            {
                "scope": "installation_import_generation",
                "settings_id": "test",
                "provider": "openai",
            },
        )


def test_project_cloud_credentials_are_bound_and_never_written_to_index(tmp_path, monkeypatch):
    from uuid import uuid4

    os.chmod(tmp_path, 0o700)
    monkeypatch.setenv("ANVIL_CLOUD_SECRET_INDEX", str(tmp_path))
    resource = "projects/123456/secrets/anvil-import-generation"
    monkeypatch.setenv("ANVIL_GENERATION_SECRET_RESOURCE", resource)
    payload = {}

    def request(method, path, body=None):
        if method == "POST":
            payload.update(body)
        return {"name": resource + "/versions/1", **payload}

    monkeypatch.setattr(cloud_secrets, "request", request)
    binding = {key: str(uuid4()) for key in ("project_id", "credential_id", "version_id")}
    binding["provider"] = "anthropic"
    identifier = cloud_secrets.save("fake-project-key", binding)
    assert cloud_secrets.available()
    assert "fake-project-key" not in (tmp_path / identifier).read_text()
    assert cloud_secrets.load(identifier, binding) == "fake-project-key"
    for key in ("project_id", "credential_id", "version_id", "provider"):
        changed = "openai" if key == "provider" else str(uuid4())
        with pytest.raises(ValueError, match="binding"):
            cloud_secrets.load(identifier, {**binding, key: changed})
    with pytest.raises(ValueError, match="binding"):
        cloud_secrets.load(
            identifier,
            {
                "scope": "installation_import_generation",
                "settings_id": "test",
                "provider": "openai",
            },
        )
    with pytest.raises(ValueError):
        cloud_secrets.save("fake", {**binding, "project_id": "not-a-uuid"})
    monkeypatch.delenv("ANVIL_GENERATION_SECRET_RESOURCE")
    assert not cloud_secrets.available()
