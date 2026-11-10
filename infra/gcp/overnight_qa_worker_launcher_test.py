import pytest
from overnight_qa_worker_launcher import environment


def test_scoped_worker_environment_drops_unrelated_authority():
    values = {
        "WORKER_DATABASE_URL": "postgresql://anvil_worker:synthetic@postgres:5432/anvil",
        "ANVIL_SESSION_KEY": "s" * 32,
        "OPENAI_API_KEY": "synthetic",
        "MIGRATION_DATABASE_URL": "owner",
        "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "true",
    }
    result = environment(values, "a" * 64)
    assert (
        result["WORKER_DATABASE_URL"] == "postgresql://anvil_worker:synthetic@127.0.0.1:55432/anvil"
    )
    assert "OPENAI_API_KEY" not in result and "MIGRATION_DATABASE_URL" not in result
    assert result["ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED"] == "false"
    assert values["ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED"] == "true"


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://anvil_migration:synthetic@postgres:5432/anvil",
        "postgresql://anvil_worker:synthetic@other:5432/anvil",
        "postgresql://anvil_worker:synthetic@postgres:5432/production",
    ],
)
def test_worker_refuses_wrong_identity_or_target(dsn):
    with pytest.raises(ValueError):
        environment({"WORKER_DATABASE_URL": dsn, "ANVIL_SESSION_KEY": "s" * 32}, "a" * 64)
