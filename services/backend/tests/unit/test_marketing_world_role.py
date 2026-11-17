"""Actual local OpenEnv objects with mocked RPC, not API/native qualification."""

from copy import deepcopy
from uuid import uuid4

import pytest
from test_marketing_paid_world import fixture

from anvil import marketing_paid_world as world
from anvil import marketing_task2_workflow_store as workflow_store
from anvil.marketing_task2_openenv import MarketingNativeAction
from anvil.praxis_generic_contract import digest


def setup(monkeypatch):
    job, prepared, attached = fixture(monkeypatch)
    instance = world.QualifiedWorld(job, prepared, attached, absolute_deadline=200.0)
    calls = []

    def rpc(job, plan, operation, value, remaining, deadline):
        world.WorldCall(
            project_id=job["project_id"],
            actor_id=job["actor_id"],
            job_id=job["id"],
            lease_token=job["lease_token"],
            plan_id=plan,
            operation=operation,
            value=value,
        )
        calls.append((operation, deepcopy(value), remaining, deadline))
        reply = {
            key: attached[key]
            for key in (
                "world_binding_id",
                "world_binding_sha256",
                "episode_id",
                "generation",
                "execution_sha256",
            )
        }
        reply.update(
            role=value["role"],
            snapshot_sha256=attached["case_snapshot_sha256"],
            state_sha256="a" * 64,
        )
        if operation == "role_tool":
            result = {"status": "completed", "result": {"manufactured": True}, "evidence_refs": []}
            reply.update(
                request_id=value["request_id"],
                operation=value["operation"],
                result=result,
                result_sha256=digest(result),
            )
        return reply

    monkeypatch.setattr(world, "_rpc", rpc)
    return instance, calls, rpc


def action():
    return MarketingNativeAction(
        operation="context.read", arguments={}, expected_generation=0, request_id=uuid4().hex
    )


def test_real_openenv_session_uses_fixed_private_api_without_sql_state_access(monkeypatch):
    instance, calls, _ = setup(monkeypatch)
    env = instance.role_environment("intent")
    assert calls == []
    env.reset()
    result = env.step(action(), timeout_s=2)
    assert [call[0] for call in calls] == ["role_attach", "role_tool"]
    assert calls[-1][2:] == (2, 200.0)
    assert result.reward is None and result.done is False
    assert env.credentials == {"generation": 0, "role": "intent"}
    assert not hasattr(env, "connections")
    assert not hasattr(env, "controller")
    with pytest.raises(ValueError, match="Attach once"):
        env.reset()


def test_changed_role_reply_closes_session_without_retry(monkeypatch):
    instance, calls, rpc = setup(monkeypatch)

    def wrong(*args):
        return rpc(*args) | {"role": "policy"}

    monkeypatch.setattr(world, "_rpc", wrong)
    env = instance.role_environment("intent")
    with pytest.raises(ValueError, match="role scope"):
        env.reset()
    with pytest.raises(ValueError, match="Attach once"):
        env.reset()
    assert len(calls) == 1 and env.closed is True


def test_ambiguous_tool_response_closes_session_and_prevents_replay(monkeypatch):
    instance, calls, _ = setup(monkeypatch)
    env = instance.role_environment("intent")
    env.reset()

    def unknown(*args):
        calls.append(("unknown",))
        raise TimeoutError("manufactured unknown remote outcome")

    monkeypatch.setattr(world, "_rpc", unknown)
    attempted = action()
    with pytest.raises(TimeoutError):
        env.step(attempted)
    with pytest.raises(ValueError, match="Current correlated"):
        env.step(attempted)
    assert len(calls) == 2 and env.closed is True


@pytest.mark.parametrize("field", ["request_id", "result_sha256"])
def test_uncorrelated_or_changed_result_never_becomes_tool_observation(monkeypatch, field):
    instance, calls, rpc = setup(monkeypatch)
    env = instance.role_environment("intent")
    env.reset()

    def changed(*args):
        return rpc(*args) | {field: str(uuid4()) if field == "request_id" else "0" * 64}

    monkeypatch.setattr(world, "_rpc", changed)
    with pytest.raises(ValueError, match="custody"):
        env.step(action())
    assert len(calls) == 2 and env.closed is True


def test_paid_journal_guard_reads_only_current_episode_metadata(monkeypatch):
    instance, _, _ = setup(monkeypatch)
    monkeypatch.setattr(
        workflow_store, "locked", lambda *args: pytest.fail("No private controller deserialization")
    )
    statements = []

    class Connection:
        def execute(self, sql, arguments):
            statements.append((sql, arguments))
            return self

        def fetchone(self):
            return {"allowed": True}

    journal = workflow_store.Journal(
        None,
        instance._job["project_id"],
        instance._job["actor_id"],
        instance.episode_id,
        instance.generation,
        instance._execution,
        None,
        paid_job=instance._job,
    )
    journal.guard(Connection())
    assert len(statements) == 1
    assert "paid_episode_current" in statements[0][0]
    assert statements[0][1][-1] == instance._bound.execution_sha256
