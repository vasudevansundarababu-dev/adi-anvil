"""HTTP contract controls only: no approvals, database, or model dispatch."""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from anvil import kyc_policy_review_api as api


@pytest.fixture
def client(monkeypatch):
    calls = []

    @contextmanager
    def context(request, project):
        calls.append(("context", str(project)))
        yield object(), uuid4(), {"admin"}

    def idempotent(c, project, user, request, body, action):
        calls.append(("idempotent", body))
        return action()

    monkeypatch.setattr(api, "revoke", lambda *args: {"revoked": True, "qualification_granted": False})
    app = FastAPI()
    app.include_router(api.routes(context, lambda value, request: value, idempotent),
                       prefix="/projects/{project}")
    with TestClient(app) as http:
        yield http, calls


@pytest.mark.parametrize("suffix", ["subjects", "subjects/00000000-0000-0000-0000-000000000001/decisions",
                                    "00000000-0000-0000-0000-000000000001/revoke"])
@pytest.mark.parametrize("raw", [b'{"reason":"valid long reason","reason":"another long reason"}',
                                  b'{"reason":NaN}', b'[]', b'{', b'\xff'])
def test_ambiguous_or_invalid_json_never_enters_database_context(client, suffix, raw):
    http, calls = client
    response = http.post(f"/projects/{uuid4()}/policy-reviews/{suffix}", content=raw)
    assert response.status_code == 422
    assert calls == []


@pytest.mark.parametrize("suffix", ["subjects", "00000000-0000-0000-0000-000000000001/revoke"])
def test_oversized_stream_is_refused_before_database_context(client, suffix):
    http, calls = client
    response = http.post(f"/projects/{uuid4()}/policy-reviews/{suffix}", content=b" " * 131073)
    assert response.status_code == 413
    assert calls == []


def test_revocation_exact_json_uses_idempotent_scope_and_never_qualifies(client):
    http, calls = client
    receipt = uuid4()
    response = http.post(f"/projects/{uuid4()}/policy-reviews/{receipt}/revoke",
                         json={"reason": "Withdraw synthetic test review."})
    assert response.status_code == 200
    assert response.json() == {"revoked": True, "qualification_granted": False}
    assert calls[1][1] == {"receipt_id": str(receipt), "reason": "Withdraw synthetic test review."}
