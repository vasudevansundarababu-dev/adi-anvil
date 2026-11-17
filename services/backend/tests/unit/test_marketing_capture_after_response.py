"""Manufactured transactions prove scheduling order, not native supervision."""

import asyncio
from contextlib import contextmanager
from uuid import uuid4

import pytest

from anvil import marketing_capture_evidence_async as async_store
from anvil import marketing_capture_evidence_store as store
from anvil import marketing_capture_world_stop as capture_stop
from anvil import marketing_world_api as api
from anvil import marketing_world_quiescence as stop
from anvil import pilot_environment


@pytest.mark.parametrize("operation,capture,has_quiescence,scheduled", [
    ("fence", True, True, True),
    ("drain", True, True, True),
    ("quiescence", True, True, False),
    ("drain", False, True, False),
    ("drain", True, False, False),
])
def test_custody_is_scheduled_only_after_committed_stop_response(
    monkeypatch, operation, capture, has_quiescence, scheduled,
):
    events, callbacks = [], []
    claim = {key: str(uuid4()) for key in (
        "project_id", "actor_id", "job_id", "plan_id", "lease_token",
    )}
    claim.update(operation=operation, value={
        "world_binding_id": str(uuid4()), "world_binding_sha256": "a" * 64,
        "episode_id": str(uuid4()), "generation": 0,
    })
    reply = {"quiescence": {"manufactured": True} if has_quiescence else None}

    @contextmanager
    def transaction(*_):
        events.append("begin")
        yield object()
        events.append("commit")

    def register(callback):
        assert events[-1] == "intent_committed"
        callbacks.append(callback)
        events.append("scheduled")

    monkeypatch.setenv("ANVIL_MARKETING_WORLD_STOP_ENABLED", "true")
    monkeypatch.setenv("ANVIL_MARKETING_NATIVE_CAPTURE_ENABLED", str(capture).lower())
    monkeypatch.setattr(pilot_environment, "current", lambda: "qa")
    monkeypatch.setattr(api, "transaction", transaction)
    monkeypatch.setattr(api, "project_fence", lambda *_: None)
    monkeypatch.setattr(stop, "dispatch", lambda *_: reply)
    async def schedule(original, *, absolute_deadline):
        assert events[-1] == "commit"
        events.append("intent_committed")
        return object()

    async def collect(original, scheduled):
        events.append("materialize")

    async def capture_dispatch(original):
        with transaction():
            result = stop.dispatch(None, original)
        handle = await schedule(original, absolute_deadline=0) if scheduled else None
        return result, handle

    monkeypatch.setattr(capture_stop, "dispatch", capture_dispatch)
    monkeypatch.setattr(async_store, "schedule", schedule)
    monkeypatch.setattr(async_store, "after_response", collect)
    assert api.dispatch(claim, after_response=register) is reply
    assert len(callbacks) == int(scheduled)
    assert "materialize" not in events
    if scheduled:
        asyncio.run(callbacks[0]())
        assert events == ["begin", "commit", "intent_committed", "scheduled", "materialize"]


def test_background_failure_is_not_retried_and_never_logs_private_exception(monkeypatch, caplog):
    from types import SimpleNamespace

    claim = SimpleNamespace(job_id=uuid4(), plan_id=uuid4())
    calls = []

    def fail(original, scheduled):
        calls.append(original)
        raise RuntimeError("PRIVATE_PROMPT_KEY_PROOF_MUST_NOT_APPEAR")

    monkeypatch.setattr(store, "_materialize_scheduled", fail)
    assert store.materialize_after_response(claim, object()) is None
    assert calls == [claim]
    assert "PRIVATE_PROMPT_KEY_PROOF_MUST_NOT_APPEAR" not in caplog.text
    assert "RuntimeError" in caplog.text
