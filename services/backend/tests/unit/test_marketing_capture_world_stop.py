"""Async cleanup with manufactured private SQL; physical/native proof absent."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from test_marketing_world_quiescence import manufactured_terminal, setup

from anvil import marketing_capture_world_stop as coordinator
from anvil import marketing_world_quiescence as stop


@pytest.mark.parametrize("boundary", ["ready", "pending", "capture_denied", "readonly", "expired", "foreign"])
def test_original_async_cleanup_commits_before_capture_and_never_replays_or_extends(monkeypatch, boundary, caplog):
    claim, context, original = setup(monkeypatch)
    manufactured_terminal(monkeypatch)
    now = datetime.now(timezone.utc)
    scope = {key: context["session"][key] for key in (
        "project_id", "job_id", "plan_id", "world_binding_id", "world_binding_sha256",
        "episode_id", "generation", "lease_sha256",
    )}
    scope.update(execution_sha256=context["session"]["attachment"]["execution_sha256"],
                 source_qualification_sha256=context["source_qualification_sha256"])
    timing = {"scope": scope, "expires_at": (now + timedelta(seconds=120)).isoformat(),
              "materialize_before": (now + timedelta(seconds=90)).isoformat()}
    if boundary == "expired":
        timing.update(expires_at=(now - timedelta(seconds=1)).isoformat(),
                      materialize_before=(now - timedelta(seconds=31)).isoformat())
    elif boundary == "foreign":
        timing["scope"]["lease_sha256"] = "f" * 64
    elif boundary == "pending":
        context["pending"]["sdk_unknown"] = 1
    elif boundary == "readonly":
        stop.dispatch(original, claim)
        original.calls.clear()
        claim = claim.model_copy(update={"operation": "quiescence"})
    events, transactions = [], []

    class Connection:
        async def execute(self, sql, args):
            if "capture_stop_deadline" in sql:
                value = {"value": timing}
            elif "SELECT id FROM anvil.projects" in sql:
                value = {"id": str(claim.project_id)}
            else:
                value = original.execute(sql, args).fetchone()

            async def fetchone():
                return value

            return SimpleNamespace(fetchone=fetchone)

    @asynccontextmanager
    async def transaction(project, user, *, absolute_deadline):
        assert str(project) == str(claim.project_id) and str(user) == str(claim.actor_id)
        index = len(transactions)
        transactions.append(absolute_deadline)
        events.append("begin" + str(index))
        yield Connection()
        events.append("commit" + str(index))

    async def schedule(original_claim, *, absolute_deadline):
        assert events[-1] == "commit1" and absolute_deadline == transactions[1]
        events.append("intent")
        if boundary == "capture_denied":
            raise RuntimeError("PRIVATE_PROOF_OR_CREDENTIAL_DO_NOT_LOG")
        return object()

    monkeypatch.setattr(coordinator, "transaction", transaction)
    monkeypatch.setattr(coordinator, "schedule", schedule)
    if boundary in {"expired", "foreign"}:
        with pytest.raises((ValueError, TimeoutError)):
            asyncio.run(coordinator.dispatch(claim))
        assert len(transactions) == 1 and not original.calls
    else:
        result, handle = asyncio.run(coordinator.dispatch(claim))
        assert result["native_qualified"] is False and result["physical_stop_verified"] is False
        assert len(transactions) == 2
        assert (handle is not None) == (boundary == "ready")
        if boundary == "capture_denied":
            assert result["quiescence"] is not None and context["quiescence"] is not None
            assert "PRIVATE_PROOF_OR_CREDENTIAL_DO_NOT_LOG" not in caplog.text
        if boundary == "readonly":
            assert "intent" not in events
            assert all("world_stop_context" in sql or "private_world_service_records" in sql for sql, _ in original.calls)
        if boundary == "pending":
            assert result["quiescence"] is None and "intent" not in events
