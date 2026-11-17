"""Prepared identity ordering with mocked authority/SQL; no native admission."""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from test_marketing_paid_world import fixture
from test_marketing_world_api import Connection, attached

from anvil import marketing_paid_execution as preparation
from anvil import marketing_paid_world as facade
from anvil import marketing_world_api as api
from anvil import marketing_world_registry as registry
from anvil.praxis_generic_contract import digest


def test_later_attach_reads_same_preallocated_bytes_without_reset_or_allocation(monkeypatch):
    claim, _, world, source, qualification, row = attached(monkeypatch)
    claim = claim.model_copy(update={"operation": "attach", "value": {}})
    c = Connection()
    c.answer = {"value": row}
    monkeypatch.setattr(
        api, "allocate", lambda *args: pytest.fail("Native attach must never allocate")
    )
    assert api.attach(c, claim, world, source, qualification) == row["attachment"]
    assert api.attach(c, claim, world, source, qualification) == row["attachment"]
    assert len(c.calls) == 2
    assert all("private_world_session" in call[0] for call in c.calls)


def test_missing_prepared_world_is_not_silently_recreated(monkeypatch):
    claim, _, world, source, qualification, _ = attached(monkeypatch)
    c = Connection()
    c.answer = {"value": None}
    monkeypatch.setattr(api, "allocate", lambda *args: pytest.fail("No reset/recreation"))
    with pytest.raises(RuntimeError, match="prepared_world"):
        api.attach(
            c,
            claim.model_copy(update={"operation": "attach", "value": {}}),
            world,
            source,
            qualification,
        )


def test_facade_requires_exact_frozen_prepared_attachment_hash(monkeypatch):
    job, prepared, attachment = fixture(monkeypatch)
    prepared["world_attachment_sha256"] = "0" * 64
    monkeypatch.setattr(
        facade, "_rpc", lambda *args: pytest.fail("Construction opens no transport")
    )
    with pytest.raises(ValueError, match="server-owned prepared"):
        facade.QualifiedWorld(job, prepared, attachment, absolute_deadline=200.0)


def test_prepare_allocates_once_before_returning_public_identity_to_prestart(monkeypatch):
    claim, plan, _, _, qualification, row = attached(monkeypatch)
    _, prepared, _ = fixture(monkeypatch)
    events = []
    plan["check_id"] = str(uuid4())
    plan["config"].update(
        workspace_execution_group=str(uuid4()),
        max_calls=10,
        episode_timeout_seconds=600,
        request_timeout_seconds=60,
        workspace_model={"model_id": "manufactured-sdk-mock"},
    )
    context = {
        "native_binding": {"workflow_graph_sha256": prepared["execution"]["workflow_graph_sha256"]},
        "actor": {"task": "manufactured"},
        "execution": prepared["execution"],
    }

    class FakeConnection:
        started = False

        def execute(self, sql, parameters):
            assert "UPDATE anvil.harbor_checks" in sql
            self.started = True
            events.append("mark_running")

    c = FakeConnection()

    @contextmanager
    def transaction(*args):
        yield c
        events.append("commit")

    def allocate(*args):
        assert c.started is True
        events.append("allocate_world")
        return row["attachment"]

    monkeypatch.setenv("ANVIL_MARKETING_WORLD_ENABLED", "true")
    monkeypatch.setattr(preparation, "transaction", transaction)
    monkeypatch.setattr(preparation, "admitted", lambda *args, **kwargs: (plan, context))
    monkeypatch.setattr(
        preparation,
        "one",
        lambda connection, sql, parameters: (
            {"invocation_count": 0, "id": plan["check_id"]}
            if "FROM anvil.harbor_checks" in sql
            else None
        ),
    )
    monkeypatch.setattr(registry, "load", lambda *args: (object(), {}, qualification))
    monkeypatch.setattr(api, "allocate", allocate)
    monkeypatch.setattr(preparation, "audit", lambda *args: events.append("audit"))
    result = preparation.prepare(claim)
    assert events == ["mark_running", "allocate_world", "audit", "commit"]
    assert result["world_attachment"] == row["attachment"]
    assert result["world_attachment_sha256"] == digest(row["attachment"])


def test_disabled_world_preparation_opens_no_database(monkeypatch):
    monkeypatch.delenv("ANVIL_MARKETING_WORLD_ENABLED", raising=False)
    monkeypatch.setattr(preparation, "transaction", lambda *args: pytest.fail("No database"))
    with pytest.raises(RuntimeError, match="preparation_disabled"):
        preparation.prepare(object())
