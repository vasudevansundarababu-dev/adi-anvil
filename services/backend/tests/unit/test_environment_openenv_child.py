"""Child configuration preserves cloud validation without inheriting credentials."""

import subprocess

import pytest

from anvil import config, environment_temp
from anvil.environment_openenv import InstalledEpisode


@pytest.mark.parametrize("cloud", [False, True])
def test_child_preserves_environment_and_drops_unrelated_secrets(monkeypatch, tmp_path, cloud):
    values = {
        "ANVIL_ENV": "cloud" if cloud else "local",
        "WEB_ORIGIN": "https://qa.example.invalid" if cloud else "http://127.0.0.1:3310",
        "WORKER_DATABASE_URL": "postgresql://synthetic-worker@localhost/qa",
        "OIDC_ISSUER": "https://identity.example.invalid/realms/qa",
        "ANVIL_SESSION_KEY": "synthetic-session-key-for-child-test-only",
    }
    monkeypatch.setattr(config, "CLOUD", cloud)
    monkeypatch.setattr(config, "setting", values.__getitem__)
    monkeypatch.setattr(environment_temp, "workspace", lambda _: tmp_path)
    monkeypatch.setenv("ANVIL_ENVIRONMENT_OPENENV_ENABLED", "true")
    monkeypatch.setenv("ANVIL_ENVIRONMENT_OPENENV_PYTHON", __file__)
    monkeypatch.setenv("ANVIL_LOCAL_WEB_PORT", "3310")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-forwarded")
    monkeypatch.setenv("DATABASE_URL", "must-not-be-forwarded")
    captured = {}

    def spawn(*args, **kwargs):
        captured.update(kwargs["env"])
        raise RuntimeError("stop before process creation")

    monkeypatch.setattr(subprocess, "Popen", spawn)
    with pytest.raises(RuntimeError, match="stop before"):
        InstalledEpisode("project", "user", "environment", "instance", "manifest", "pack")
    assert captured["ANVIL_ENV"] == values["ANVIL_ENV"]
    assert captured["WEB_ORIGIN"] == values["WEB_ORIGIN"]
    assert "OPENAI_API_KEY" not in captured and "DATABASE_URL" not in captured
    if cloud:
        assert captured["OIDC_ISSUER"] == values["OIDC_ISSUER"]
        assert captured["ANVIL_SESSION_KEY"] == values["ANVIL_SESSION_KEY"]
        assert "ANVIL_LOCAL_WEB_PORT" not in captured
    else:
        assert captured["ANVIL_LOCAL_WEB_PORT"] == "3310"
        assert "ANVIL_SESSION_KEY" not in captured
