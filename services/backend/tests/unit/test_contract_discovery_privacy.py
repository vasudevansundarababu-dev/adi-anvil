"""Authoring discovery must not reveal Gym benchmark population identities."""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from anvil.praxis_generic_api import routes


@pytest.mark.parametrize("auth_kind", ["project_export_client", "workload_identity", None])
def test_discovery_does_not_query_private_inventory_for_export_clients(monkeypatch, auth_kind):
    sentinel = {"id": "private-holdout", "sha256": "private-fingerprint", "count": 50}
    calls = []

    def discover(connection, project):
        calls.append(project)
        return [sentinel]

    @contextmanager
    def access(request, project, *args):
        if auth_kind:
            request.state.export_client_id = uuid4()
            request.state.export_auth_kind = auth_kind
        yield object(), uuid4(), ["admin"]

    monkeypatch.setattr("anvil.golden_kyc_v7_export.qualified_variants", lambda *args: [])
    monkeypatch.setattr("anvil.praxis_case_registry.discover", discover)
    app = FastAPI()
    app.include_router(routes(access, None, lambda value, request: value, None))
    project = uuid4()
    response = TestClient(app).get(f"/generic/contracts?project={project}")
    assert response.status_code == 200
    body = response.json()
    assert body["paid_calls"] is False
    assert body["run_authority"] == "not_granted"
    if auth_kind:
        assert calls == []
        assert body["case_datasets"] == []
        assert "private-holdout" not in response.text
        assert "private-fingerprint" not in response.text
    else:
        assert calls == [project]
        assert body["case_datasets"] == [sentinel]
