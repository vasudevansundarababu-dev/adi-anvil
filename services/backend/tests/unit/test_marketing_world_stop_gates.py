"""New stop-only gate controls with mocked SQL/transport; no live actions."""

import hashlib
from contextlib import contextmanager
from uuid import uuid4

import pytest
from test_marketing_paid_world import fixture
from test_marketing_world_quiescence import setup

from anvil import marketing_paid_world as world
from anvil import marketing_world_api as api
from anvil import pilot_environment
from anvil.praxis_generic_contract import canonical, digest


def test_disabled_stop_gate_rejects_before_any_storage(monkeypatch):
    claim, _, _ = setup(monkeypatch)
    monkeypatch.setattr(pilot_environment, "current", lambda: "qa")
    monkeypatch.setenv("ANVIL_MARKETING_WORLD_STOP_ENABLED", "false")
    monkeypatch.setattr(
        api, "transaction", lambda *args: pytest.fail("No storage before stop admission")
    )
    with pytest.raises(RuntimeError, match="stop_qa_api_disabled"):
        api.dispatch(claim)


def test_stop_gate_cannot_dispatch_paid_work_and_survives_paid_disable(monkeypatch):
    claim, _, connection = setup(monkeypatch)
    monkeypatch.setattr(pilot_environment, "current", lambda: "qa")
    monkeypatch.setenv("ANVIL_MARKETING_WORLD_STOP_ENABLED", "true")
    monkeypatch.setenv("ANVIL_MARKETING_WORLD_ENABLED", "false")
    monkeypatch.setenv("ANVIL_MARKETING_PAID_ENABLED", "false")
    monkeypatch.setattr(
        api, "admitted", lambda *args: pytest.fail("Cleanup cannot use or grant paid admission")
    )
    monkeypatch.setattr(api, "project_fence", lambda *args: None)

    @contextmanager
    def transaction(*args):
        yield connection

    monkeypatch.setattr(api, "transaction", transaction)
    result = api.dispatch(claim)
    assert result["state"] == "fenced_unknown" and result["native_qualified"] is False


def test_fixed_worker_stop_transport_never_requires_provider_activation(monkeypatch):
    from anvil import config, marketing_paid_world_transport
    from anvil.marketing_world_quiescence import dispatch

    claim, _, connection = setup(monkeypatch)
    result = dispatch(connection, claim)
    monkeypatch.setattr(pilot_environment, "current", lambda: "qa")
    monkeypatch.setattr(
        config,
        "harbor_live_enabled",
        lambda: pytest.fail("Stop cannot enable/check provider dispatch"),
    )
    for key, value in {
        "ANVIL_WORKER_BROKER_ROLE": "worker",
        "ANVIL_WORKER_BROKER_ENABLED": "true",
        "ANVIL_WORKER_BROKER_URL": "http://api:8200/internal/v1/worker-dispatch",
        "ANVIL_MARKETING_WORLD_STOP_ENABLED": "true",
        "ANVIL_MARKETING_WORLD_ENABLED": "false",
    }.items():
        monkeypatch.setenv(key, value)
    calls = []
    monkeypatch.setattr(
        marketing_paid_world_transport,
        "execute",
        lambda raw, **kwargs: calls.append(raw) or canonical(result),
    )
    job = {
        "project_id": str(claim.project_id),
        "actor_id": str(claim.actor_id),
        "id": str(claim.job_id),
        "lease_token": str(claim.lease_token),
    }
    response = world._rpc(job, claim.plan_id, "fence", claim.value, 10, 200.0)
    assert response == result and len(calls) == 1


def test_facade_rejects_validly_hashed_foreign_stop_scope(monkeypatch):
    from anvil.marketing_world_quiescence import Pending, Status

    job, prepared, attachment = fixture(monkeypatch)
    instance = world.QualifiedWorld(job, prepared, attachment, absolute_deadline=200.0)
    body = {
        **{
            key: attachment[key]
            for key in (
                "project_id",
                "job_id",
                "plan_id",
                "world_binding_id",
                "world_binding_sha256",
                "episode_id",
                "generation",
                "execution_sha256",
            )
        },
        "plan_id": str(uuid4()),
        "schema_version": "anvil.marketing-world-fence.v1",
        "lease_sha256": hashlib.sha256(job["lease_token"].encode()).hexdigest(),
        "source_qualification_sha256": "e" * 64,
        "fence_id": str(uuid4()),
        "fence_epoch": 1,
        "fenced_at": "2026-11-14T12:00:00Z",
        "graph_ledger_sha256": "1" * 64,
        "reconstruction_sha256": None,
        "new_work_permitted": False,
    }
    response = Status.model_validate(
        {
            "schema_version": "anvil.marketing-world-quiescence-status.v2",
            "fence": body | {"receipt_sha256": digest(body)},
            "state": "fenced_unknown",
            "pending": {name: 0 for name in Pending.model_fields},
            "quiescence": None,
            "physical_stop_verified": False,
            "native_qualified": False,
        }
    ).model_dump(mode="json")
    monkeypatch.setattr(world, "_rpc", lambda *args: response)
    with pytest.raises(ValueError, match="same actual world"):
        instance.fence()
