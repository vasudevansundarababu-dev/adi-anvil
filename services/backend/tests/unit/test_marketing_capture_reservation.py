"""Original private reservation controls, with no credentials or dispatch."""

import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_marketing_capture_status import packet

from anvil import marketing_capture_evidence_store as store
from anvil import praxis_template_registry


@pytest.mark.parametrize("change", [None, "source", "lease", "project", "expired", "not_reserved", "no_slot"])
def test_only_current_original_reserved_slot_provides_a_pre_spend_deadline(monkeypatch, change):
    enrollment, status, _, now, _ = packet(now=datetime.now(timezone.utc))
    token = str(uuid4())
    scope = status["scope"].copy()
    scope["lease_sha256"] = hashlib.sha256(token.encode()).hexdigest()
    claim = SimpleNamespace(**{key: scope[key] for key in ("project_id", "job_id", "plan_id")}, lease_token=token)
    value = {"scope": scope, "status_transport": enrollment["status_transport"],
             "expires_at": status["descriptor"]["expires_at"], "manifest_id": status["manifest_id"],
             "content_state": "reserved_no_content"}
    if change == "source":
        value["status_transport"]["source_sha256"] = "2" * 64
    elif change == "lease":
        scope["lease_sha256"] = "f" * 64
    elif change == "project":
        scope["project_id"] = str(uuid4())
    elif change == "expired":
        value["expires_at"] = now.isoformat()
    elif change == "not_reserved":
        value["content_state"] = "materialization_unknown"
    elif change == "no_slot":
        value = None
    calls = []

    class Connection:
        def execute(self, sql, args):
            calls.append(sql)
            assert "capture_manifest_preflight" in sql
            return SimpleNamespace(fetchone=lambda: {"value": value})

    monkeypatch.setattr(praxis_template_registry, "source_hash", lambda: "1" * 64)
    if change is None:
        result = store.require_reserved_manifest(Connection(), claim)
        assert 0 < result["remaining_seconds"] <= 50
        assert result["capture_accepted"] is False
        assert result["manifest_id"] == value["manifest_id"]
    else:
        with pytest.raises((ValueError, RuntimeError)):
            store.require_reserved_manifest(Connection(), claim)
    assert len(calls) == 1
