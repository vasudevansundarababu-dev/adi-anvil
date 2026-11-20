"""Probe control flow with fake connections; NOT SQL qualification evidence."""

import asyncio
from datetime import datetime, timezone
from time import monotonic

import pytest

from anvil import marketing_capture_database_probe as probe
from anvil.marketing_capture_database import DatabaseUnknown
from anvil.praxis_generic_contract import digest


@pytest.mark.parametrize("acknowledged,restricted", [(True, True), (False, True), (True, False)])
def test_cancel_ack_terminal_observation_and_privileges_are_separate_required_checks(monkeypatch, acknowledged, restricted):
    calls, connections = [], []
    target = "a" * 64
    identity = {"source_sha256": "b" * 64}
    monkeypatch.setattr(probe, "configuration", lambda: ({"host": "/fixed/socket", "user": "capture", "dbname": "test"}, target))
    monkeypatch.setattr(probe, "runtime_identity", lambda: identity)

    class Cursor:
        def __init__(self, row):
            self.row = row

        async def fetchone(self):
            return self.row

    class Connection:
        closed = False
        capture_server_cancel_observed = False

        @property
        def pgconn(self):
            return self

        def finish(self):
            self.closed = True

        async def close(self):
            self.closed = True

        async def execute(self, query, parameters=None):
            calls.append((self, query, parameters))
            if query == "SELECT pg_sleep(300)":
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    self.capture_server_cancel_observed = acknowledged
                    self.finish()
                    raise DatabaseUnknown() from None
            if "FROM pg_roles" in query:
                return Cursor({"login": "capture", "active": "capture", "database": "test", "pid": 456,
                               "backend_start": datetime(2026, 11, 19, tzinfo=timezone.utc),
                               "address": None, "port": None, "ssl": False,
                               "read_only": "on", "restricted": restricted})
            return Cursor({"gone": True})

    async def connect(**_):
        connection = Connection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(probe._CaptureConnection, "connect", connect)
    if not acknowledged or not restricted:
        with pytest.raises(ValueError):
            asyncio.run(probe.probe(absolute_deadline=monotonic() + 2))
    else:
        result = asyncio.run(probe.probe(absolute_deadline=monotonic() + 2))
        assert result["observed_target_sha256"] == digest(result["target_observation"])
        assert result["role_profile_sha256"] == digest(result["role_profile"])
        assert all(check["evidence_sha256"] == digest(result["control_observations"][key])
                   for key, check in result["checks"].items())
        assert any("backend_start=%s" in query and parameters[0] == 456 for _, query, parameters in calls)
        assert result["spending_authority"] is False
    assert len(connections) == 2 and all(connection.closed for connection in connections)
    for connection in connections:
        assert next(query for source, query, _ in calls if source is connection) == "SET TRANSACTION READ ONLY"
    assert all(not query.startswith(("INSERT", "UPDATE", "DELETE", "ALTER", "GRANT")) for _, query, _ in calls)


def test_probe_rejects_unbounded_cutoff_before_configuration_or_connection(monkeypatch):
    monkeypatch.setattr(probe, "configuration", lambda: pytest.fail("No target for unbounded probe"))
    with pytest.raises(ValueError, match="300seconds"):
        asyncio.run(probe.probe(absolute_deadline=monotonic() + 301))
