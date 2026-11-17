"""Real async custody/compiler composed with manufactured private SQL only."""

import asyncio
from contextlib import asynccontextmanager
from time import monotonic

import pytest
from test_marketing_capture_evidence_store import setup

from anvil import marketing_capture_evidence_async as custody
from anvil import marketing_capture_evidence_store as software_store


def adapter(monkeypatch, **options):
    claim, state, events, snapshots = setup(monkeypatch, **options)
    hard = monotonic() + 5

    class Cursor:
        def __init__(self, original):
            self.original = original

        async def __aenter__(self):
            self.original.__enter__()
            return self

        async def __aexit__(self, *args):
            self.original.__exit__(*args)

        async def execute(self, sql, args):
            self.original.execute(sql, args)

        async def fetchone(self):
            return self.original.fetchone()

    class Connection:
        capture_deadline = hard

        def __init__(self, original):
            self.original = original

        async def execute(self, sql, args):
            # Only this fixture delegates to manufactured synchronous SQL.
            # The production adapter contains no synchronous fallback.
            value = self.original.execute(sql, args)

            async def fetchone():
                return value.fetchone()

            return type("Result", (), {"fetchone": staticmethod(fetchone)})()

        def cursor(self, *, name):
            return Cursor(self.original.cursor(name=name))

    @asynccontextmanager
    async def transaction(project, user, *, absolute_deadline):
        assert 0 < absolute_deadline - monotonic() <= hard - monotonic() + .001
        with software_store.transaction(project, user) as original:
            yield Connection(original)

    monkeypatch.setattr(custody, "transaction", transaction)
    return claim, state, events, snapshots, hard


def test_async_intent_commits_before_bulk_then_actual_compiler_and_private_readback(monkeypatch):
    claim, state, events, snapshots, hard = adapter(monkeypatch)

    async def run():
        scheduled = await custody.schedule(claim, absolute_deadline=hard)
        assert state["intent"] and "enumerate_after_committed_intent" not in events
        result = await custody.materialize(claim, scheduled)
        assert result["state"] == "ready" and result["descriptor"] == state["descriptor"]
        assert result["capture_accepted"] is False and result["native_qualified"] is False
        before = len(events)
        with pytest.raises(RuntimeError, match="already consumed"):
            await custody.materialize(claim, scheduled)
        assert len(events) == before

    asyncio.run(run())
    assert len(snapshots) == 2
    assert events.index("intent_committed") < events.index("enumerate_after_committed_intent")


@pytest.mark.parametrize("boundary", ["snapshot", "manifest", "lost_callback", "expired_callback"])
def test_async_failure_never_reclaims_slot_or_creates_native_acceptance(monkeypatch, boundary):
    claim, state, events, _, hard = adapter(monkeypatch, allow_snapshot=boundary != "snapshot", allow_manifest=boundary != "manifest")

    async def run():
        scheduled = await custody.schedule(claim, absolute_deadline=hard)
        if boundary == "expired_callback":
            scheduled.absolute_deadline = monotonic() - 1
        if boundary != "lost_callback":
            with pytest.raises((RuntimeError, TimeoutError)):
                await custody.materialize(claim, scheduled)
        with pytest.raises(RuntimeError, match="consumed_unknown"):
            await custody.schedule(claim, absolute_deadline=hard)

    asyncio.run(run())
    assert state["descriptor"] is None
    assert len([event for event in events if "begin_capture_evidence" in event]) == 1
    if boundary in {"lost_callback", "expired_callback"}:
        assert "enumerate_after_committed_intent" not in events
