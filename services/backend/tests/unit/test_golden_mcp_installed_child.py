"""Real local stdio control with a synthetic in-memory episode; no SQL/model."""
import sys
from contextlib import AsyncExitStack
from types import SimpleNamespace

import pytest

pytest.importorskip("mcp", reason="Pinned MCP SDK is installed in the dedicated OpenEnv runtime")

from anvil import golden_mcp_client as client


class SyntheticEpisode:
    def __init__(self):
        self.credentials = {"generation": 0}
        self.calls = []

    def step(self, action):
        self.calls.append(action)
        return SimpleNamespace(result={"status": "completed", "synthetic": True}, done=False)


def test_child_launch_is_installed_isolated_and_secret_free(monkeypatch):
    captured = []

    def observe(parameters, **kwargs):
        captured.append(parameters)
        raise RuntimeError("stop_before_launch")

    monkeypatch.setattr(client, "stdio_client", observe)
    monkeypatch.setattr(client, "NativeGateway", lambda *a, **kw: SimpleNamespace(
        path="/synthetic/gateway", token="synthetic-token", close=lambda: None))
    monkeypatch.setenv("PYTHONPATH", "/untrusted/source")
    monkeypatch.setenv("DATABASE_URL", "synthetic-secret-never-in-child")
    monkeypatch.setenv("PROVIDER_API_KEY", "synthetic-secret-never-in-child")
    episode = client.McpEpisode(SyntheticEpisode(), {"generation": 0}, lambda: True)

    async def attempt():
        async with AsyncExitStack() as stack:
            await episode._open_session(stack)

    try:
        with pytest.raises(RuntimeError, match="stop_before_launch"):
            client.anyio.run(attempt)
        parameters = captured[0]
        assert parameters.command == sys.executable
        assert parameters.args == ["-I", "-B", "-m", "anvil.golden_mcp_server"]
        assert set(parameters.env) == {"PATH", "HOME", "ANVIL_MCP_CONFIG_FILE"}
        assert parameters.env["HOME"] == str(episode.home)
    finally:
        episode.stderr.close()
        episode.gateway.close()


def test_actual_installed_stdio_schema_auth_and_reset_fences():
    synthetic = SyntheticEpisode()
    action = SimpleNamespace(operation="policy.read", arguments={}, expected_generation=0)
    try:
        mediator = client.McpEpisode(synthetic, {"generation": 0}, lambda: True,
                                    action_factory=lambda **kwargs: SimpleNamespace(**kwargs))
    except PermissionError:
        pytest.skip("Local sandbox forbids AF_UNIX bind; actual MCP control not run")
    with mediator as episode:
        assert episode.step(action).result == {"status": "completed", "synthetic": True}
        assert len(synthetic.calls) == 1

        async def unauthorized():
            return await episode.session.call_tool("policy.read", {}, meta={"anvil_session": "wrong", "scope_sha256": episode.scope_hash})

        assert episode.portal.call(unauthorized).isError

        async def bad_schema():
            return await episode.session.call_tool("policy.read", {"unexpected": True}, meta=episode.meta)

        assert episode.portal.call(bad_schema).isError
        assert len(synthetic.calls) == 1
        synthetic.credentials = {"generation": 1}
        with pytest.raises(ValueError, match="generation"):
            episode.step(action)
        assert len(synthetic.calls) == 1
        assert episode.public_receipt()["provider_credentials_to_server"] is False
        assert episode.public_receipt()["database_credentials_to_server"] is False


def test_missing_installed_child_fails_closed_without_episode_effect(monkeypatch):
    closed = []
    monkeypatch.setattr(client, "NativeGateway", lambda *a, **kw: SimpleNamespace(
        path="/synthetic/gateway", token="synthetic-token", close=lambda: closed.append(True)))

    async def unavailable(self, stack):
        raise ModuleNotFoundError("synthetic missing installed module")

    monkeypatch.setattr(client.McpEpisode, "_open_session", unavailable)
    synthetic = SyntheticEpisode()
    with pytest.raises(RuntimeError, match="MCP handshake failed") as failure:
        with client.McpEpisode(synthetic, {"generation": 0}, lambda: True):
            pytest.fail("Unavailable installed child must not enter a session")
    assert isinstance(failure.value.__cause__, ModuleNotFoundError)
    assert synthetic.calls == [] and closed == [True]
