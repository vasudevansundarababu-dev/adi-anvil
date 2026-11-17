"""Signed GET over in-process ASGI only; private SQL/status are manufactured."""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from test_marketing_capture_status import packet, sign

from anvil import marketing_capture_api as api
from anvil import marketing_capture_database as capture_database
from anvil import marketing_capture_intake_async as custody
from anvil import praxis_template_registry
from anvil.marketing_capture_status import PATH
from anvil.request_limits import RequestLimits


def setup(monkeypatch, *, key_available=True, enrolled=True):
    enrollment, value, private, _, upload = packet(now=datetime.now(timezone.utc))
    monkeypatch.setenv("ANVIL_MARKETING_NATIVE_CAPTURE_ENABLED", "true")
    monkeypatch.setenv("ANVIL_WORKER_BROKER_ROLE", "api")
    monkeypatch.setattr(api.pilot_environment, "current", lambda: "qa")
    monkeypatch.setattr(praxis_template_registry, "source_hash", lambda: "1" * 64)
    events = []

    class Connection:
        def execute(self, sql, args):
            assert "capture_evidence_enrollment_status" in sql
            assert str(args[0]) == enrollment["enrollment_id"]
            events.append("readonly_status")
            return SimpleNamespace(fetchone=lambda: {"value": deepcopy(value)})

    def key(*_):
        events.append("original_key_lookup")
        return enrollment if key_available else None

    def scope(*_):
        events.append("scope")
        return {"project_id": enrollment["scope"]["project_id"], "actor_id": str(uuid4())} if enrolled else None

    class AsyncConnection:
        async def execute(self, sql, args):
            if "capture_attestation_key" in sql:
                value = key()
            elif "capture_enrollment_scope" in sql:
                value = scope()
            else:
                value = Connection().execute(sql, args).fetchone()["value"]

            async def fetchone():
                return {"value": value}

            return SimpleNamespace(fetchone=fetchone)

    @asynccontextmanager
    async def capture_transaction(*_, absolute_deadline):
        from time import monotonic

        assert 0 < absolute_deadline - monotonic() <= 5
        yield AsyncConnection()
        events.append("readonly_transaction_closed")

    monkeypatch.setattr(capture_database, "transaction", capture_transaction)
    monkeypatch.setattr(custody, "begin", lambda *_: pytest.fail("GET must not consume upload intent"))
    monkeypatch.setattr(custody, "retain", lambda *_args, **_kwargs: pytest.fail("GET must not retain/mutate upload"))
    app = FastAPI()
    app.include_router(api.routes())
    return RequestLimits(app), enrollment, value, private, events, upload


def get(app, enrollment, key, *, header=None, path=PATH, extras=(), body=b"", stream=False, events=None):
    async def chunks():
        if events is not None:
            events.append("body_read")
        yield body

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test.invalid") as client:
            headers = [("X-Anvil-Capture-Attestation", header or sign(enrollment, key)),
                       ("X-Anvil-Capture-Enrollment", enrollment["enrollment_id"]), *extras]
            request = client.build_request("GET", path, headers=headers, content=chunks() if stream else body)
            if stream:
                # Manufacture a body without length/TE to prove actual ASGI body
                # is rejected after signature but before status disclosure.
                request.headers.pop("transfer-encoding", None)
            return await client.send(request)

    return asyncio.run(run())


def test_disabled_route_reveals_no_descriptor_and_queries_no_original_scope(monkeypatch):
    app, enrollment, _, key, events, _ = setup(monkeypatch)
    monkeypatch.setenv("ANVIL_MARKETING_NATIVE_CAPTURE_ENABLED", "false")
    response = get(app, enrollment, key)
    assert response.status_code == 503 and not events and "manifest_id" not in response.text


def test_authenticated_get_is_canonical_repeatable_and_never_consumes_upload(monkeypatch):
    app, enrollment, value, key, events, _ = setup(monkeypatch)
    first = get(app, enrollment, key)
    second = get(app, enrollment, key)
    from anvil.praxis_generic_contract import canonical

    assert first.status_code == second.status_code == 200
    assert first.content == second.content == canonical(value)
    assert first.headers["cache-control"] == "no-store"
    assert events.count("readonly_status") == 2
    assert events.index("original_key_lookup") < events.index("scope") < events.index("readonly_status")


@pytest.mark.parametrize("change", ["bearer", "duplicate", "query", "body"])
def test_wrong_get_envelope_rejects_before_any_key_or_status_lookup(change, monkeypatch):
    app, enrollment, _, key, events, _ = setup(monkeypatch)
    extras, path, body = (), PATH, b""
    if change == "bearer":
        extras = (("Authorization", "Bearer manufactured-no-real-key"),)
    elif change == "duplicate":
        extras = (("X-Anvil-Capture-Attestation", sign(enrollment, key)),)
    elif change == "query":
        path += "?nonce=caller-selected"
    else:
        body = b"body"
    assert get(app, enrollment, key, path=path, extras=extras, body=body).status_code == 401
    assert not events


@pytest.mark.parametrize("boundary", ["unknown_key", "revoked_scope", "missing_transport", "wrong_source"])
def test_original_key_live_scope_and_independent_transport_are_required(boundary, monkeypatch):
    app, enrollment, _, key, events, _ = setup(monkeypatch, key_available=boundary != "unknown_key", enrolled=boundary != "revoked_scope")
    signed = sign(enrollment, key)
    if boundary == "missing_transport":
        enrollment.pop("status_transport")
    if boundary == "wrong_source":
        monkeypatch.setattr(praxis_template_registry, "source_hash", lambda: "2" * 64)
    response = get(app, enrollment, key, header=signed)
    assert response.status_code == 401 and "readonly_status" not in events and "manifest_id" not in response.text


def test_upload_signature_cannot_fetch_status_and_get_signature_does_not_change_private_post(monkeypatch):
    app, enrollment, _, key, events, upload = setup(monkeypatch)
    from test_marketing_capture_attestation import header

    response = get(app, enrollment, key, header=header(upload, key))
    assert response.status_code == 401 and "scope" not in events and "readonly_status" not in events


def test_actual_undeclared_body_is_denied_after_authentication_before_scope_disclosure(monkeypatch):
    app, enrollment, _, key, events, _ = setup(monkeypatch)
    response = get(app, enrollment, key, stream=True, body=b"unexpected", events=events)
    assert response.status_code == 401
    assert events.index("original_key_lookup") < events.index("body_read")
    assert "scope" not in events and "readonly_status" not in events
