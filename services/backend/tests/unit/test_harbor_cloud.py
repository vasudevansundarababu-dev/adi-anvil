"""Disabled cloud wiring and private file admission; only synthetic keys/mock transport."""

import json
import runpy
import stat
import sys

import httpx
import pytest

from anvil import config, harbor_agents, providers


def policy():
    return {
        "reference": "harbor:synthetic-cloud-test",
        "project_id": "a0000000-0000-4000-8000-000000000002",
        "provider": "openai",
        "model": "synthetic-cloud-model",
        "total_cap_micro_usd": 1000000,
        "input_micro_usd_per_million_tokens": 2000000,
        "output_micro_usd_per_million_tokens": 8000000,
        "pricing_revision": "synthetic-pricing-only",
        "expires_at": "2099-01-01T00:00:00Z",
        "pricing_expires_at": "2099-01-01T00:00:00Z",
    }


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CLOUD", True)
    monkeypatch.setattr(providers, "CLOUD", True)
    monkeypatch.setattr(providers, "ROOT", tmp_path)
    monkeypatch.setattr(harbor_agents, "ROOT", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", ".secrets/openai_api_key")
    monkeypatch.setenv("ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", "false")
    (tmp_path / ".secrets").mkdir(mode=0o700)
    (tmp_path / ".local").mkdir(mode=0o700)
    return tmp_path


def test_disabled_missing_private_inputs_never_calls_sdk(cloud):
    assert not config.harbor_live_enabled()
    assert harbor_agents.authority() is None
    assert providers.secret_presence("openai") == (False, "secret_missing")
    with pytest.raises(RuntimeError, match="secret_missing"):
        harbor_agents.execute_provider(
            "synthetic-cloud-model",
            "actor",
            httpx.MockTransport(lambda r: pytest.fail("SDK called")),
        )


@pytest.mark.parametrize("field", ["expires_at", "pricing_expires_at"])
def test_expired_authority_blocks_admission(cloud, field):
    value = policy()
    value[field] = "2000-01-01T00:00:00Z"
    path = cloud / ".local/harbor-authority.json"
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    assert harbor_agents.authority() is None


def test_private_inputs_reject_public_files_symlinks_and_env_keys(cloud, monkeypatch):
    key = cloud / ".secrets/openai_api_key"
    key.write_text("synthetic-not-real-key")
    key.chmod(0o644)
    assert providers.secret_presence("openai") == (False, "secret_file_permissions")
    key.unlink()
    other = cloud / "other"
    other.write_text("synthetic-not-real-key")
    other.chmod(0o600)
    key.symlink_to(other)
    assert providers.secret_presence("openai") == (False, "secret_path_not_allowlisted")
    monkeypatch.delenv("OPENAI_API_KEY_FILE")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-real-key")
    assert providers.secret_presence("openai") == (False, "cloud_secret_requires_private_file")
    authority = cloud / ".local/harbor-authority.json"
    authority.write_text(json.dumps(policy()))
    authority.chmod(0o644)
    assert harbor_agents.authority() is None


def test_allowed_private_mount_path_uses_network_free_stub(cloud, monkeypatch):
    key = cloud / ".secrets/openai_api_key"
    key.write_text("synthetic-not-real-key")
    key.chmod(0o600)
    authority = cloud / ".local/harbor-authority.json"
    authority.write_text(json.dumps(policy()))
    authority.chmod(0o600)
    monkeypatch.setenv("ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", "true")
    monkeypatch.setenv("ANVIL_LIVE_PROVIDERS_ENABLED", "false")
    assert config.harbor_live_enabled()
    assert harbor_agents.authority() is not None
    calls = []

    def respond(request):
        calls.append(request)
        assert json.loads(request.content)["model"] == "synthetic-cloud-model"
        return httpx.Response(
            200,
            json={
                "id": "stub",
                "model": "synthetic-cloud-model",
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    result = harbor_agents.execute_provider(
        "synthetic-cloud-model", "actor only", httpx.MockTransport(respond)
    )
    assert result.status == "completed" and len(calls) == 1


def test_renderer_forces_disabled_and_creates_no_key_or_authority(tmp_path, monkeypatch):
    module = runpy.run_path(str(config.ROOT / "infra/gcp/render_config.py"))
    for name in module["SECRETS"]:
        monkeypatch.setenv(name, "synthetic-render-only")
    monkeypatch.setenv("ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", "true")
    monkeypatch.setattr(
        sys, "argv", ["render", str(tmp_path), "anvil.example.test", "auth.example.test"]
    )
    module["main"]()
    assert "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED=false\n" in (tmp_path / "harbor.env").read_text()
    assert "ANVIL_LIVE_PROVIDERS_ENABLED=false\n" in (tmp_path / "app.env").read_text()
    assert stat.S_IMODE((tmp_path / "harbor.env").stat().st_mode) == 0o600
    assert not (tmp_path / ".secrets").exists()
    assert not (tmp_path / ".local").exists()
    assert "OPENAI_API_KEY=" not in (tmp_path / "harbor.env").read_text()
