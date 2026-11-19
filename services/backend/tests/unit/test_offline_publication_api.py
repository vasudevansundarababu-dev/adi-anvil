"""HTTP/auth contract controls; no real publication attestation is performed."""

from contextlib import contextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from anvil import praxis_offline_publication_api as api


@pytest.fixture
def client(monkeypatch):
    calls, roles = [], {"admin"}

    @contextmanager
    def context(request, project):
        calls.append("context")
        yield object(), uuid4(), roles

    def action(*args):
        calls.append("stage")
        return {"publication_verified": False, "publication_accepted": False, "qualification_granted": False}

    monkeypatch.setattr(api.ledger, "stage", action)
    app = FastAPI()
    app.include_router(api.routes(context, lambda value, request: value,
        lambda c, p, u, r, body, fn: fn(), lambda: None), prefix="/projects/{project}")
    with TestClient(app) as http:
        yield http, calls, roles


@pytest.mark.parametrize("suffix", ["", "/00000000-0000-0000-0000-000000000001/attest",
                                    "/00000000-0000-0000-0000-000000000001/revoke"])
@pytest.mark.parametrize("raw", [b'{"record_utf8":"{}","record_utf8":"{}"}', b'{"x":NaN}', b'[]', b'\xff'])
def test_invalid_or_ambiguous_json_never_enters_database_context(client, suffix, raw):
    http, calls, _ = client
    response = http.post(f"/projects/{uuid4()}/templates/{uuid4()}/offline-publications{suffix}", content=raw)
    assert response.status_code == 422 and calls == []


def test_oversized_stream_stops_before_database_context(client):
    http, calls, _ = client
    response = http.post(f"/projects/{uuid4()}/templates/{uuid4()}/offline-publications", content=b" " * 1048577)
    assert response.status_code == 413 and calls == []


def test_upload_is_not_an_attestation_and_engineer_cannot_stage(client):
    http, calls, roles = client
    path = f"/projects/{uuid4()}/templates/{uuid4()}/offline-publications"
    response = http.post(path, json={"record_utf8": "{}"})
    assert response.status_code == 201
    assert response.json() == {"publication_verified": False, "publication_accepted": False, "qualification_granted": False}
    calls.clear()
    roles.clear()
    roles.add("rl-engineer")
    response = http.post(path, json={"record_utf8": "{}"})
    assert response.status_code == 403 and calls == ["context"]
