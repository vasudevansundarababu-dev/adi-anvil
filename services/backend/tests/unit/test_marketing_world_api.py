"""Real controller transforms with mocked SQL, not serving/native qualification."""

import json
from uuid import uuid4

import pytest
from test_marketing_world_registry import setup as registry_setup

from anvil import marketing_world_api as api
from anvil.marketing_paid_world import WorldCall
from anvil.marketing_world_definition import definition
from anvil.praxis_generic_contract import digest


class Connection:
    def __init__(self):
        self.calls = []
        self.answer = {"allowed": True}

    def execute(self, sql, parameters):
        self.calls.append((sql, parameters))
        return self

    def fetchone(self):
        return self.answer


def setup(monkeypatch):
    body, _, candidate, plan = registry_setup(monkeypatch)
    claim = WorldCall(
        **{
            key: str(uuid4())
            for key in ("project_id", "actor_id", "job_id", "lease_token", "plan_id")
        },
        operation="attach",
        value={},
    )
    plan.update(
        id=str(claim.plan_id), project_id=str(claim.project_id), created_by=str(claim.actor_id)
    )
    plan["config"]["trial"] = 1
    source = candidate["value"]["source"]
    qualification = candidate["value"]["qualification"] | {"id": str(uuid4())}
    return claim, plan, definition(body), source, qualification


def attached(monkeypatch):
    claim, plan, world, source, qualification = setup(monkeypatch)
    c = Connection()
    attachment = api.allocate(c, claim, plan, world, source, qualification)
    parameters = c.calls[-1][1]
    row = {
        "source_id": source["id"],
        "qualification_id": qualification["id"],
        "episode_id": attachment["episode_id"],
        "generation": 0,
        "world_binding_id": attachment["world_binding_id"],
        "world_binding_sha256": attachment["world_binding_sha256"],
        "attachment": attachment,
        "controller_state": json.loads(parameters[6]),
        "controller_state_sha256": parameters[7],
    }
    scope = {
        key: attachment[key]
        for key in ("world_binding_id", "world_binding_sha256", "episode_id", "generation")
    }
    role_claim = claim.model_copy(
        update={"operation": "role_attach", "value": scope | {"role": "intent"}}
    )
    return role_claim, plan, world, source, qualification, row


def test_attach_binds_frozen_repeat_and_keeps_private_state_out_of_reply(monkeypatch):
    claim, plan, world, source, qualification = setup(monkeypatch)
    c = Connection()
    reply = api.allocate(c, claim, plan, world, source, qualification)
    state = json.loads(c.calls[0][1][6])
    assert state["outcome"] == world.branch(plan["config"]["trial"] - 1)
    assert state["trial_id"] == reply["episode_id"]
    assert all(row["outcome_binding"] is None for rows in state["initial"].values() for row in rows)
    for token in [state["controller_token"], *state["role_tokens"].values(), world.branch_seed]:
        assert token not in str(reply)
    assert "controller_state" not in reply and "outcome" not in reply


@pytest.mark.parametrize("trial", [None, True, 0, 1001])
def test_attach_never_invents_missing_or_invalid_case_repetition(monkeypatch, trial):
    claim, plan, world, source, qualification = setup(monkeypatch)
    plan["config"]["trial"] = trial
    c = Connection()
    with pytest.raises(RuntimeError, match="repetition"):
        api.allocate(c, claim, plan, world, source, qualification)
    assert c.calls == []


def test_session_rejects_cross_world_identity_before_private_controller_use(monkeypatch):
    claim, _, world, source, qualification, row = attached(monkeypatch)
    c = Connection()
    c.answer = {"value": row}
    wrong = claim.model_copy(update={"value": claim.value | {"episode_id": str(uuid4())}})
    with pytest.raises(ValueError, match="world identity"):
        api.session(c, wrong, world, source, qualification)


def tool_setup(monkeypatch):
    claim, plan, world, source, qualification, row = attached(monkeypatch)
    c = Connection()
    c.answer = {"value": row}
    row, controller = api.session(c, claim, world, source, qualification)
    request_id = uuid4().hex
    tool_claim = claim.model_copy(
        update={
            "operation": "role_tool",
            "value": claim.value
            | {"request_id": request_id, "operation": "context.read", "arguments": {}},
        }
    )
    intent = {
        "role": "intent",
        "operation": "context.read",
        "arguments": {},
        "arguments_sha256": digest({}),
    }
    ctx = {"session": row, "intent": intent}

    class ToolConnection(Connection):
        commit_allowed = True

        def execute(self, sql, parameters):
            super().execute(sql, parameters)
            if "private_world_tool_context" in sql:
                self.answer = {"value": ctx}
            elif "commit_private_world_tool" in sql:
                self.answer = {"allowed": self.commit_allowed}
            else:
                pytest.fail("No direct controller SQL read/write is allowed")
            return self

    return tool_claim, row, controller, ToolConnection(), plan, ctx


def test_actual_controller_tool_transform_is_bound_to_intent_and_atomic_commit(monkeypatch):
    claim, row, controller, c, _, _ = tool_setup(monkeypatch)
    execution = registry_setup(monkeypatch)[0]["execution_sha256"]
    # Use the actual pinned fixture execution, not an asserted execution hash.
    from test_marketing_paid_world import fixture

    _, prepared, _ = fixture(monkeypatch)
    assert digest(prepared["execution"]) == execution
    reply = api.tool(c, claim, row, controller, prepared["execution"])
    assert reply["result"]["status"] == "completed"
    assert reply["result_sha256"] == digest(reply["result"])
    assert reply["state_sha256"] != row["controller_state_sha256"]
    assert len(c.calls) == 2
    assert "controller_state" not in reply and "role_tokens" not in str(reply)
    after = json.loads(c.calls[-1][1][5])
    assert after["transitions"] == 1


def test_mismatched_intent_stops_before_any_tool_transform_or_commit(monkeypatch):
    claim, row, controller, c, _, ctx = tool_setup(monkeypatch)
    ctx["intent"]["role"] = "policy"
    monkeypatch.setattr(api, "execute", lambda *args: pytest.fail("No tool effect permitted"))
    with pytest.raises(ValueError, match="before-effect intent"):
        api.tool(c, claim, row, controller, {})
    assert len(c.calls) == 1


def test_unconfirmed_commit_cannot_return_successful_tool_reply(monkeypatch):
    claim, row, controller, c, _, _ = tool_setup(monkeypatch)
    c.commit_allowed = False
    from test_marketing_paid_world import fixture

    _, prepared, _ = fixture(monkeypatch)
    with pytest.raises(RuntimeError, match="commit_unconfirmed"):
        api.tool(c, claim, row, controller, prepared["execution"])
    assert len(c.calls) == 2


def test_disabled_api_opens_no_transaction(monkeypatch):
    claim, _, _, _, _ = setup(monkeypatch)
    monkeypatch.delenv("ANVIL_MARKETING_WORLD_ENABLED", raising=False)
    monkeypatch.setattr(api, "transaction", lambda *args: pytest.fail("No database contact"))
    with pytest.raises(RuntimeError, match="disabled"):
        api.dispatch(claim)
