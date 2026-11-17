"""Actual async raw helpers with manufactured SQL, never native acceptance."""

import asyncio
from datetime import datetime, timedelta, timezone
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_marketing_capture_store import retained_packet

from anvil import marketing_capture_api as api
from anvil import marketing_capture_intake_async as custody
from anvil.praxis_generic_contract import canonical


@pytest.mark.parametrize("allowed", [True, False])
def test_async_raw_retention_keeps_exact_wire_and_original_signed_header_once(allowed):
    context, value, attestation = retained_packet()
    context["intent_id"] = str(uuid4())
    raw, calls = canonical(value), []

    class Connection:
        async def execute(self, sql, args):
            calls.append((sql, args))

            async def fetchone():
                return {"allowed": allowed}

            return SimpleNamespace(fetchone=fetchone)

    async def run():
        return await custody.retain(Connection(), context, raw, transport_complete=True, attestation=attestation)

    if allowed:
        result = asyncio.run(run())
        assert result["accepted_capture_reference"] is None and result["native_qualified"] is False
    else:
        with pytest.raises(RuntimeError, match="unconfirmed_no_retry"):
            asyncio.run(run())
    assert len(calls) == 1 and calls[0][1][2] == raw and calls[0][1][6] == attestation.original_header


def test_wire_read_preserves_original_monotonic_deadline_and_partial_bytes():
    events = []

    async def stream():
        yield b"original partial bytes"
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            events.append("source_cancelled")
            raise
        events.append("late_bytes")
        yield b"must never arrive"

    request = SimpleNamespace(stream=stream)

    async def run():
        return await api.read_wire(request, (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(),
                                   1024, absolute_deadline=monotonic() + .02)

    assert asyncio.run(run()) == (b"original partial bytes", False)
    assert events == ["source_cancelled"]
