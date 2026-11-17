"""Permanent pilot profiles use manufactured keys and exact mocked secret transport."""

import json
import os
from uuid import uuid4

import pytest
from pydantic import SecretStr

from anvil import cloud_secrets, pilot_environment, providers, workspace_dispatch


def configure(monkeypatch, environment="qa"):
    profile, prefix, origin, issuer, *_ = pilot_environment.TARGETS[environment]
    for key, value in {
        "ANVIL_ENV": "cloud",
        "ANVIL_PILOT_ENVIRONMENT": environment,
        "ANVIL_CREDENTIAL_STORE_PROFILE": profile,
        "WEB_ORIGIN": origin,
        "OIDC_ISSUER": issuer,
        "ANVIL_PILOT_GCP_PROJECT_NUMBER": "123456",
        "ANVIL_PILOT_SECRET_RESOURCE": f"projects/123456/secrets/{prefix}-model-credentials",
        "ANVIL_WORKER_BROKER_ROLE": "api",
    }.items():
        monkeypatch.setenv(key, value)
    for key in [
        "ANVIL_GENERATION_SECRET_RESOURCE",
        "ANVIL_QA_SECRET_RESOURCE",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY_FILE",
    ]:
        monkeypatch.delenv(key, raising=False)
    return f"projects/123456/secrets/{prefix}-model-credentials"


def test_api_metadata_literal_and_secret_paths_cannot_be_caller_redirects(monkeypatch):
    import httpx

    resource = configure(monkeypatch)
    seen = []
    original = httpx.Client

    def serve(request):
        seen.append(request)
        if request.url.host == "169.254.169.254":
            assert request.headers["metadata-flavor"] == "Google"
            return httpx.Response(200, json={"access_token": "manufactured-workload-token"})
        assert (
            str(request.url)
            == "https://secretmanager.googleapis.com/v1/" + resource + "/versions/1:access"
        )
        return httpx.Response(200, json={"bounded": "manufactured"})

    monkeypatch.setattr(
        cloud_secrets.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(serve), **kwargs),
    )
    assert cloud_secrets.request("GET", resource + "/versions/1:access") == {
        "bounded": "manufactured"
    }
    assert len(seen) == 2
    for path in [
        "http://169.254.169.254/computeMetadata/v1/",
        "https://attacker.invalid/",
        resource + "/versions/1:access?redirect=metadata",
        resource + "/../foreign/versions/1:access",
    ]:
        with pytest.raises(ValueError, match="outside exact resource"):
            cloud_secrets.request("GET", path)
    assert len(seen) == 2


@pytest.mark.parametrize("environment", ["qa", "staging"])
def test_project_version_provider_custody_and_locator_isolation(monkeypatch, tmp_path, environment):
    resource = configure(monkeypatch, environment)
    os.chmod(tmp_path, 0o700)
    monkeypatch.setenv("ANVIL_CLOUD_SECRET_INDEX", str(tmp_path))
    calls = []
    payload = {}

    def request(method, path, body=None):
        calls.append((method, path))
        if method == "POST":
            payload.update(body)
            return {"name": resource + "/versions/1"}
        return {"name": resource + "/versions/1", **payload}

    monkeypatch.setattr(cloud_secrets, "request", request)
    binding = {k: str(uuid4()) for k in ["project_id", "credential_id", "version_id"]}
    binding["provider"] = "openai"
    identifier = cloud_secrets.save("manufactured-pilot-key", binding)
    assert cloud_secrets.load(identifier, binding) == "manufactured-pilot-key"
    assert "manufactured-pilot-key" not in (tmp_path / identifier).read_text()
    before = len(calls)
    with pytest.raises(ValueError, match="binding mismatch"):
        cloud_secrets.load(identifier, {**binding, "version_id": str(uuid4())})
    assert len(calls) == before + 1
    (tmp_path / identifier).write_text(
        json.dumps({"version": "projects/123456/secrets/anvil-import-generation/versions/1"})
    )
    before = len(calls)
    with pytest.raises(ValueError, match="locator"):
        cloud_secrets.load(identifier, binding)
    assert len(calls) == before


@pytest.mark.parametrize(
    "key,value",
    [
        ("ANVIL_CREDENTIAL_STORE_PROFILE", "qa"),
        ("ANVIL_CREDENTIAL_STORE_PROFILE", "legacy"),
        (
            "ANVIL_PILOT_SECRET_RESOURCE",
            "projects/123456/secrets/anvil-staging-v1-model-credentials",
        ),
        ("ANVIL_PILOT_SECRET_RESOURCE", "projects/123456/secrets/anvil-qa-model-credentials"),
        ("ANVIL_PILOT_SECRET_RESOURCE", "projects/654321/secrets/anvil-qa-v1-model-credentials"),
        ("ANVIL_GENERATION_SECRET_RESOURCE", "projects/123456/secrets/anvil-import-generation"),
        ("ANVIL_QA_SECRET_RESOURCE", "projects/123456/secrets/anvil-qa-model-credentials"),
        ("OPENAI_API_KEY", "manufactured"),
        ("OPENAI_API_KEY_FILE", "/tmp/foreign"),
        ("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/foreign.json"),
        ("OIDC_ISSUER", "https://anvil-staging-auth.adi-labs.ai/realms/anvil-staging"),
    ],
)
def test_no_wrong_namespace_ambient_or_legacy_fallback(monkeypatch, key, value):
    configure(monkeypatch)
    monkeypatch.setenv(key, value)
    assert not cloud_secrets.available()


def test_scope_generation_and_origin_omission_do_not_bypass(monkeypatch):
    configure(monkeypatch)
    with pytest.raises(ValueError, match="project binding"):
        cloud_secrets.save(
            "manufactured",
            {
                "scope": "installation_import_generation",
                "settings_id": "test",
                "provider": "openai",
            },
        )
    monkeypatch.delenv("ANVIL_PILOT_ENVIRONMENT")
    with pytest.raises(ValueError):
        pilot_environment.current()
    assert not cloud_secrets.available()


def test_unbudgeted_paths_stay_disabled_and_broker_requires_effect_ticket(monkeypatch):
    configure(monkeypatch)
    for flag in [
        "ANVIL_IMPORT_GENERATION_ENABLED",
        "ANVIL_BENCHMARK_EVALUATION_ENABLED",
        "LANGSMITH_TRACING",
    ]:
        monkeypatch.setenv(flag, "true")
        with pytest.raises(ValueError):
            pilot_environment.check_flags()
        monkeypatch.setenv(flag, "false")
    result = workspace_dispatch.execute(
        {"provider": "openai", "model_id": "gpt-6.1-sol"},
        SecretStr("manufactured"),
        providers.ActorRequest(
            model="gpt-6.1-sol", actor_text="Test actor input", max_output_tokens=10
        ),
    )
    assert result.error_code == "pilot_dispatch_admission_blocked"
