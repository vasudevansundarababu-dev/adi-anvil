"""New real-controller/mock-SQL existing-request handoff; no tool invocation."""

from uuid import UUID, uuid4

import pytest
from test_marketing_world_api import Connection, attached

from anvil import marketing_world_api as api
from anvil.marketing_paid_world import WorldCall


def claim_for_tool(claim):
    return WorldCall.model_validate(
        claim.model_dump(mode="json")
        | {
            "operation": "role_tool",
            "value": claim.value
            | {"request_id": uuid4().hex, "operation": "search", "arguments": {}},
        }
    )


def test_only_exact_correlated_request_uses_existing_tool_session(monkeypatch):
    claim, _, world, source, qualification, row = attached(monkeypatch)
    claim = claim_for_tool(claim)
    connection = Connection()
    connection.answer = {"value": row}
    actual, controller = api.session(connection, claim, world, source, qualification)
    assert actual == row and controller.trial_id == row["episode_id"]
    sql, parameters = connection.calls[0]
    assert "private_world_session_for_existing_tool" in sql
    assert parameters == (
        claim.job_id,
        claim.lease_token,
        claim.plan_id,
        UUID(claim.value["request_id"]),
    )


def test_missing_or_unadmitted_request_cannot_restore_private_controller(monkeypatch):
    claim, _, world, source, qualification, _ = attached(monkeypatch)
    connection = Connection()
    connection.answer = {"value": None}
    monkeypatch.setattr(
        api, "restore", lambda *args: pytest.fail("No controller before existing-request admission")
    )
    with pytest.raises(RuntimeError, match="current_private_world_session"):
        api.session(connection, claim_for_tool(claim), world, source, qualification)
