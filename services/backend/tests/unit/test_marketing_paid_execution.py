"""Disabled API boundary, no SQL or live admission claim."""

from types import SimpleNamespace

import pytest

from anvil import marketing_paid_execution as execution


def test_worker_claim_cannot_certify_success_before_durable_finish_qualification():
    with pytest.raises(RuntimeError, match="durable_native_finish_qualification_required"):
        execution.finish(SimpleNamespace(native={"success": True}))


def test_disabled_marketing_api_denies_before_project_or_worker_access(monkeypatch):
    monkeypatch.setenv("ANVIL_MARKETING_PAID_ENABLED", "false")
    monkeypatch.setattr(execution.pilot_environment, "current", lambda: "qa")
    monkeypatch.setattr(execution, "project_fence", lambda *args: pytest.fail("No DB access"))
    with pytest.raises(RuntimeError, match="admission_disabled"):
        execution.admitted(None, SimpleNamespace())
