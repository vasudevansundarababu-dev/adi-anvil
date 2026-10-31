import os

import pytest

from anvil import workspace_secrets as store
from anvil.workspace_credentials import SecretValue

BINDING = {
    "project_id": "project-one",
    "credential_id": "credential-one",
    "version_id": "version-one",
    "provider": "openai",
}


def test_local_ciphertext_is_private_bound_and_cloud_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "CLOUD", False)
    secret = "test-only-credential-marker-" + "x" * 64
    reference = store.save(secret, BINDING)
    path = store.directory() / reference
    assert secret.encode() not in path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600
    assert store.directory().stat().st_mode & 0o777 == 0o700
    assert store.load(reference, BINDING) == secret
    with pytest.raises(store.StoreUnavailable):
        store.load(reference, {**BINDING, "project_id": "another-project"})
    with pytest.raises(store.StoreUnavailable):
        store.load("../wrapping-key.v1", BINDING)
    os.chmod(path, 0o644)
    with pytest.raises(store.StoreUnavailable):
        store.load(reference, BINDING)
    monkeypatch.setattr(store, "CLOUD", True)
    with pytest.raises(store.StoreUnavailable):
        store.save("never-stored", BINDING)


@pytest.mark.parametrize("character", ["x", '"', "\\"])
def test_maximum_credential_round_trips_and_unicode_is_rejected(tmp_path, monkeypatch, character):
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "CLOUD", False)
    secret = character * 8192
    assert SecretValue(secret=secret)
    reference = store.save(secret, BINDING)
    assert store.load(reference, BINDING) == secret
    with pytest.raises(ValueError):
        SecretValue(secret="😀" * 8192)
    with pytest.raises(ValueError):
        SecretValue(secret="line\nbreak")


def test_symlink_store_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "CLOUD", False)
    (tmp_path / ".local").mkdir()
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / ".local/workspace-secrets").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(store.StoreUnavailable):
        store.save("test-only-secret", BINDING)


def test_missing_wrap_key_requires_recovery_and_does_not_replace_it(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "CLOUD", False)
    store.save("first-test-only-secret", BINDING)
    key = store.directory() / "wrapping-key.v1"
    key.unlink()
    with pytest.raises(store.StoreUnavailable):
        store.save("second-test-only-secret", BINDING)
    assert not key.exists()
