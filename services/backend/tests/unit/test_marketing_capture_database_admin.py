"""Admin projection only: no connection probe, credential output or admission."""

import json

from anvil import marketing_capture_database_target as target
from anvil import runtime_admin


def test_inventory_separates_configuration_from_qualification_without_connection_or_private_details(monkeypatch):
    monkeypatch.setattr(runtime_admin, "ROLES", ())
    monkeypatch.delenv(target.PIN, raising=False)
    monkeypatch.setattr(target, "setting", lambda _: "host=original-db.example hostaddr=192.0.2.1 port=5432 dbname=PRIVATE_DB user=PRIVATE_ROLE password=PRIVATE_PASSWORD sslmode=verify-full gssencmode=disable")
    _, pin = target.inspect_target()
    monkeypatch.setenv(target.PIN, pin)

    class NoProbe:
        def execute(self, *_):
            raise AssertionError("Capture readiness must not add a connection probe")

    result = runtime_admin.listing(NoProbe(), "manufactured-project")
    status = result["capture_database"]
    assert status["configuration_ready"] is True and status["ready"] is status["runtime_qualified"] is False
    assert status["owner"] == "anvil_provisioning" and not status["connection_probe_performed"]
    assert result["paid_dispatch_authorized"] is result["deployment_available"] is False
    raw = json.dumps(result)
    assert all(value not in raw for value in ("PRIVATE_DB", "PRIVATE_ROLE", "PRIVATE_PASSWORD", "original-db.example", "192.0.2.1"))
