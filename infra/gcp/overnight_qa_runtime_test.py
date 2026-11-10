import json

import pytest
from overnight_qa_runtime import render, run_worker_unit
from staging_compose import render_demo


def images():
    return {
        name: name + "@sha256:" + "a" * 64
        for name in ("backend", "web", "postgres", "neo4j", "keycloak", "caddy")
    }


def test_private_additive_profile_does_not_change_legacy():
    before = render_demo(images())
    result = render(images(), "b" * 64)
    assert render_demo(images()) == before
    assert result["services"]["caddy"]["ports"] == ["127.0.0.1:8080:80"]
    assert result["services"]["postgres"]["ports"] == ["127.0.0.1:55432:5432"]
    wire = json.dumps(result)
    assert "docker.sock" not in wire and "/opt/anvil/" not in wire
    assert "anvil-staging-demo" not in wire
    assert result["services"]["api"]["environment"]["ANVIL_LIVE_PROVIDERS_ENABLED"] == "false"


def test_run_worker_uses_allowlisted_environment_without_migration_or_provider_keys():
    unit = run_worker_unit("b" * 64)
    assert "env -i" in unit and "-m anvil.benchmark_run_worker" in unit
    assert "WORKER_DATABASE_URL=${WORKER_DATABASE_URL}" in unit
    assert "API_KEY" not in unit and "MIGRATION_DATABASE" not in unit
    assert "Restart=no" in unit and "KillMode=control-group" in unit
    assert "ANVIL_ENVIRONMENT_QA_SOURCE_SHA256=" + "b" * 64 in unit
    assert "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED=false" in unit


@pytest.mark.parametrize("value", ["", "a" * 63, "x" * 64, "a\n" * 32])
def test_source_binding_rejects_malformed_values(value):
    with pytest.raises(ValueError):
        render(images(), value)
    with pytest.raises(ValueError):
        run_worker_unit(value)
