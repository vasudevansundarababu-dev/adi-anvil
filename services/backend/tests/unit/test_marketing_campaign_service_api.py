"""New API-handler controls using a fake SQL connection, not SQL qualification."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_marketing_activation_definition import proposal
from test_marketing_world_readiness import setup

from anvil.marketing_task2_persistence import freeze
from anvil.marketing_world_definition import definition
from anvil.marketing_world_service_api import effect
from anvil.praxis_generic_contract import canonical, digest


@pytest.fixture(scope="module")
def world():
    _, value = proposal()
    return definition(value)


class Connection:
    def __init__(self, context, allowed):
        self.context, self.allowed, self.calls = context, allowed, []

    def execute(self, sql, args):
        self.calls.append((sql, args))
        if "private_world_campaign_context" in sql:
            return SimpleNamespace(fetchone=lambda: {"value": self.context})
        assert "commit_private_world_campaign" in sql
        return SimpleNamespace(fetchone=lambda: {"allowed": self.allowed})


def request(world, *, allowed=True, recommendation="ready"):
    controller, execution, node, inputs, *_ = setup(recommendation=recommendation)
    controller._initial = world.controller(0)._initial
    state, fingerprint = freeze(controller)
    # Real PostgreSQL JSONB returns arrays, not Python's in-memory tuples.
    state = json.loads(canonical(state))
    source_id, qualification_id, binding = (str(uuid4()) for _ in range(3))
    row = {"source_id": source_id, "qualification_id": qualification_id, "world_binding_id": binding,
           "world_binding_sha256": "a" * 64, "episode_id": controller.trial_id, "generation": controller.generation,
           "controller_state": state, "controller_state_sha256": fingerprint}
    intent = {"id": str(uuid4()), "node_sha256": digest(node), "input_sha256": digest(inputs)}
    claim = SimpleNamespace(job_id=uuid4(), lease_token=uuid4(), plan_id=uuid4(),
                            value={"node_id": node["id"], "inputs": inputs, "week": 6, "visit": 1,
                                   **{key: row[key] for key in ("world_binding_id", "world_binding_sha256", "episode_id", "generation")}})
    connection = Connection({"session": row, "effect": intent}, allowed)
    return connection, claim, execution, {"id": source_id}, {"id": qualification_id}, state


def test_confirmed_mock_commit_receives_complete_atomic_state_and_returns_bound_receipt(world):
    connection, claim, execution, source, qualification, before = request(world)
    result = effect(connection, claim, world, source, qualification, execution)
    assert result["port"] == "responded" and result["artifact"]["decision"] == "approved"
    assert len(connection.calls) == 2
    arguments = connection.calls[1][1]
    assert json.loads(arguments[7]) == before
    after = json.loads(arguments[8])
    assert result["receipt"]["post_state_sha256"] == arguments[9] == digest(after)
    assert after["settled"] == 11535890 and after["committed"] == 154762
    assert after["reservations"][0]["value"] == 200000
    assert any(r["outcome_binding"] is not None for r in after["initial"]["reports"])
    assert any(r["public"]["provenance"] == "CURRENT_SOURCE_RECONCILED_SIMULATED_CONTROLLER_ACCOUNTING"
               for r in after["initial"]["budget-snapshots"])


def test_unconfirmed_commit_never_returns_approved_effect_and_does_not_retry(world):
    connection, claim, execution, source, qualification, before = request(world, allowed=False)
    with pytest.raises(RuntimeError, match="unconfirmed; no retry"):
        effect(connection, claim, world, source, qualification, execution)
    assert len(connection.calls) == 2
    assert connection.context["session"]["controller_state"] == before


def test_nonready_actual_request_commits_only_timeout_and_unchanged_state(world):
    connection, claim, execution, source, qualification, before = request(world, recommendation="hold")
    result = effect(connection, claim, world, source, qualification, execution)
    assert result["port"] == "timeout" and result["artifact"]["campaign_authority_issued"] is False
    arguments = connection.calls[1][1]
    assert json.loads(arguments[7]) == json.loads(arguments[8]) == before


def test_wrong_committed_input_denies_before_transition_or_commit(world):
    connection, claim, execution, source, qualification, _ = request(world)
    connection.context["effect"]["input_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="committed request-effect scope"):
        effect(connection, claim, world, source, qualification, execution)
    assert len(connection.calls) == 1
