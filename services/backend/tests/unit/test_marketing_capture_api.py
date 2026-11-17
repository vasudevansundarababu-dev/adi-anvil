"""In-process ASGI controls: real test signatures, mocked private SQL only.

No operational key, kernel identity or accepted capture is produced.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI
from test_marketing_capture_attestation import header, signing_packet

from anvil import marketing_capture_api as api
from anvil import marketing_capture_database as capture_database
from anvil import marketing_capture_intake_async as custody
from anvil.marketing_capture_submission import WIRE_CAP
from anvil.request_limits import RequestLimits


def configure(monkeypatch, *, key_available=True, enrolled=True, expired=False):
    monkeypatch.setenv("ANVIL_MARKETING_NATIVE_CAPTURE_ENABLED", "true")
    monkeypatch.setenv("ANVIL_WORKER_BROKER_ROLE", "api")
    monkeypatch.setattr(api.pilot_environment, "current", lambda: "qa")
    enrollment, _, raw, claims, private, now = signing_packet(now=datetime.now(timezone.utc))
    if expired:
        enrollment["expires_at"] = (now - timedelta(seconds=1)).isoformat()
        claims["expires_at"] = (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    enrollment.update(project_id="manufactured-project", actor_id="manufactured-actor",
                      intent_id="11111111-1111-4111-8111-111111111111")
    signed = header(claims, private)
    events, retained = [], []

    @asynccontextmanager
    async def transaction(*_, absolute_deadline):
        yield None
        events.append("intent_committed" if events[-1:] == ["intent"] else "transaction_closed")

    async def key(*_):
        events.append("public_key")
        return enrollment if key_available else None

    async def scope(*_):
        events.append("scope")
        return {"project_id": "manufactured-project", "actor_id": "manufactured-actor"} if enrolled else None

    async def begin(*_):
        events.append("intent")
        return enrollment

    async def retain(_connection, _context, body, *, transport_complete, attestation):
        assert attestation.original_header == signed
        assert attestation.enrollment_id == enrollment["enrollment_id"]
        events.append("retain")
        retained.append((body, transport_complete))
        return {"private_intake_id": "must-never-leak", "accepted_capture_reference": None}

    monkeypatch.setattr(custody, "key", key)
    monkeypatch.setattr(capture_database, "transaction", transaction)
    monkeypatch.setattr(custody, "scope", scope)
    monkeypatch.setattr(custody, "begin", begin)
    monkeypatch.setattr(custody, "retain", retain)
    app = FastAPI()
    app.include_router(api.routes())
    return RequestLimits(app), enrollment, raw, signed, events, retained


def send(app, enrollment, signed, events, chunks, *, extra_headers=None, duplicate=False, bearer=False):
    async def body():
        for chunk in chunks:
            events.append("body_read")
            yield chunk

    async def run():
        headers = [("X-Anvil-Capture-Attestation", signed), ("X-Anvil-Capture-Enrollment", enrollment["enrollment_id"]),
                   ("Content-Type", "application/json")]
        if extra_headers:
            headers += list(extra_headers.items())
        if duplicate:
            headers.append(("X-Anvil-Capture-Attestation", signed))
        if bearer:
            headers.append(("Authorization", "Bearer manufactured-no-real-token"))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test.invalid") as client:
            return await client.post(api.PATH, content=body(), headers=headers)

    return asyncio.run(run())


def test_disabled_route_does_not_query_key_or_read_body(monkeypatch):
    app, enrollment, raw, signed, events, retained = configure(monkeypatch)
    monkeypatch.setenv("ANVIL_MARKETING_NATIVE_CAPTURE_ENABLED", "false")
    assert send(app, enrollment, signed, events, [raw]).status_code == 503
    assert events == retained == []


def test_no_oidc_fallback_or_http_kernel_identity_assertion(monkeypatch):
    app, enrollment, raw, signed, events, retained = configure(monkeypatch)
    response = send(app, enrollment, signed, events, [raw], bearer=True, extra_headers={"X-Producer-Identity": "linux_peer"})
    assert response.status_code == 401 and events == retained == []


def test_unknown_enrollment_denies_before_intent_and_body(monkeypatch):
    app, enrollment, raw, signed, events, retained = configure(monkeypatch, enrolled=False)
    assert send(app, enrollment, signed, events, [raw]).status_code == 409
    assert "intent" not in events and "body_read" not in events and not retained


def test_real_test_signature_then_exclusive_mock_intent_precede_wire_without_issuing_success_ref(monkeypatch):
    app, enrollment, raw, signed, events, retained = configure(monkeypatch)
    response = send(app, enrollment, signed, events, [raw])
    assert events.index("intent_committed") < events.index("body_read") < events.index("retain")
    assert retained == [(raw, True)]
    assert response.status_code == 409 and "no_success_reference" in response.text
    assert "must-never-leak" not in response.text


def test_duplicate_signature_headers_deny_without_key_lookup_or_read(monkeypatch):
    app, enrollment, raw, signed, events, retained = configure(monkeypatch)
    assert send(app, enrollment, signed, events, [raw], duplicate=True).status_code == 401
    assert events == retained == []


def test_extra_body_after_signed_length_is_unknown_not_silently_truncated_success(monkeypatch):
    app, enrollment, raw, signed, events, retained = configure(monkeypatch)
    response = send(app, enrollment, signed, events, [raw, b"extra"])
    assert response.status_code == 409 and retained == [(raw, False)]
    assert events.count("retain") == 1


def test_oversized_declared_length_keeps_existing_one_mib_middleware_limit(monkeypatch):
    app, enrollment, raw, signed, events, retained = configure(monkeypatch)
    response = send(app, enrollment, signed, events, [raw], extra_headers={"Content-Length": str(WIRE_CAP + 1)})
    assert response.status_code == 413 and events == retained == []


def test_expired_signature_cannot_read_body_or_consume_intent(monkeypatch):
    app, enrollment, raw, signed, events, retained = configure(monkeypatch, expired=True)
    assert send(app, enrollment, signed, events, [raw]).status_code == 401
    assert "intent" not in events and "body_read" not in events and retained == []


def test_signed_length_with_wrong_body_digest_is_retained_only_as_unknown(monkeypatch):
    app, enrollment, raw, signed, events, retained = configure(monkeypatch)
    changed = b"x" + raw[1:]
    assert send(app, enrollment, signed, events, [changed]).status_code == 409
    assert retained == [(changed, False)]


def test_missing_independently_enrolled_public_key_cannot_authenticate(monkeypatch):
    app, enrollment, raw, signed, events, retained = configure(monkeypatch, key_available=False)
    assert send(app, enrollment, signed, events, [raw]).status_code == 401
    assert "intent" not in events and "body_read" not in events and retained == []
