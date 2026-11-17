"""Coordinator boundary controls; manufactured worlds are not native qualification."""

import json
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

import pytest

from anvil.marketing_paid_graph import GraphRunner
from anvil.praxis_generic_contract import digest


def runner(*, database_allowed=True, readiness=True, checkpoint=None):
    execution = json.loads(
        (Path(__file__).parents[1] / "fixtures/veyra-template-execution-v3.json").read_text()
    )
    prepared = {
        "mode": "marketing-native",
        "native_binding": {
            "case_assignment": {"case_id": "GT2-R01"},
            "execution_sha256": digest(execution),
        },
        "execution": execution,
        "episode_timeout_seconds": 600,
        "request_timeout_seconds": 60,
    }
    calls = []

    class Connection:
        def execute(self, sql, params):
            calls.append((sql, params))
            return SimpleNamespace(fetchone=lambda: {"allowed": database_allowed})

    @contextmanager
    def connections():
        yield Connection()

    def dispatch(*args, **kwargs):
        calls.append(("broker", kwargs))
        return readiness if kwargs.get("operation") == "readiness" else "completed response"

    job = {key: str(uuid4()) for key in ("project_id", "id", "actor_id", "plan_id", "lease_token")}
    deadline = monotonic() + 590
    world = SimpleNamespace(
        case_id="GT2-R01", episode_id=str(uuid4()), generation=1, _deadline=deadline
    )
    saver = SimpleNamespace(get_tuple=lambda config: checkpoint)
    instance = GraphRunner(
        connections,
        job,
        prepared,
        world,
        absolute_deadline=deadline,
        dispatch=dispatch,
        checkpointer=saver,
    )
    return instance, calls


def test_no_native_guard_means_no_database_or_broker_work():
    instance, calls = runner()
    with pytest.raises(RuntimeError, match="liveness"):
        instance.guard()
    assert calls == []


@pytest.mark.parametrize("guard", [lambda: None, lambda: 1, lambda: False])
def test_native_guard_must_explicitly_confirm_liveness(guard):
    instance, calls = runner()
    with pytest.raises(RuntimeError, match="liveness"):
        instance.run(guard)
    assert calls == []


def test_expired_database_authority_blocks_before_broker_dispatch():
    instance, calls = runner(database_allowed=False)
    with pytest.raises(RuntimeError, match="current_attempt"):
        instance.run(lambda: True)
    assert len(calls) == 1
    assert "heartbeat_paid_agent_job" in calls[0][0]


def test_revoked_api_readiness_blocks_before_graph_effects():
    instance, calls = runner(readiness=False)
    with pytest.raises(RuntimeError, match="budget_authority"):
        instance.run(lambda: True)
    assert len(calls) == 2
    kind, arguments = calls[-1]
    assert kind == "broker"
    assert set(arguments) == {"operation", "remaining_seconds", "absolute_deadline"}
    assert arguments["operation"] == "readiness"
    assert arguments["absolute_deadline"] == instance._deadline
    assert 0 < arguments["remaining_seconds"] <= instance.prepared["request_timeout_seconds"]


def test_existing_durable_checkpoint_is_never_replayed():
    instance, calls = runner(checkpoint={"checkpoint": "already-started"})
    with pytest.raises(RuntimeError, match="no_replay"):
        instance.run(lambda: True)
    assert len(calls) == 2


def test_changed_case_or_execution_cannot_attach_to_other_world():
    instance, _ = runner()
    with pytest.raises(ValueError, match="campaign case"):
        GraphRunner(
            instance.connections,
            instance.job,
            instance.prepared,
            SimpleNamespace(case_id="GT2-R02"),
        )
    changed = instance.prepared | {"execution": instance.execution | {"unbound": True}}
    with pytest.raises(ValueError, match="published campaign execution"):
        GraphRunner(instance.connections, instance.job, changed, instance.world)


def test_entire_campaign_deadline_applies_before_each_effect():
    instance, calls = runner()
    instance.native_guard = lambda: True
    instance.roles.deadline = instance.roles.clock() - 1
    with pytest.raises(TimeoutError, match="elapsed_limit"):
        instance._effect({"type": "external_system"}, {}, 1, 1)
    assert calls == []
