"""Actual controller/reconstruction with manufactured records and mocked SQL."""

import json
from copy import deepcopy

import pytest
from test_marketing_world_api import Connection, attached

from anvil import marketing_world_api as api
from anvil.marketing_paid_world import WorldCall
from anvil.marketing_world_release import inventory_refs, release
from anvil.praxis_generic_contract import digest


def setup(monkeypatch):
    claim, plan, world, source, qualification, row = attached(monkeypatch)
    c = Connection()
    c.answer = {"value": row}
    row, controller = api.session(c, claim, world, source, qualification)
    row["last_week"] = 0
    data = {"attachment": row["attachment"], "releases": [], "effects": [], "turns": []}

    class RecordedConnection(Connection):
        commit_allowed = True

        def execute(self, sql, parameters):
            super().execute(sql, parameters)
            if "private_world_graph_records" in sql:
                self.answer = {"value": data}
            elif "private_world_service_records" in sql:
                self.answer = {"value": {"records": [], "source_contract_sha256": "a" * 64}}
            elif "commit_private_world_release" in sql:
                self.answer = {"allowed": self.commit_allowed}
            else:
                pytest.fail("No other SQL or effect path permitted")
            return self

    from test_marketing_paid_world import fixture

    _, prepared, _ = fixture(monkeypatch)
    value = {
        key: claim.value[key]
        for key in ("world_binding_id", "world_binding_sha256", "episode_id", "generation")
    } | {"week": 1}
    claim = WorldCall.model_validate(
        claim.model_dump(mode="json") | {"operation": "release", "value": value}
    )
    return claim, row, controller, world, prepared["execution"], RecordedConnection(), data


def test_initial_baseline_release_has_immutable_complete_collection_indexes(monkeypatch):
    claim, row, controller, world, execution, c, _ = setup(monkeypatch)
    reply = release(c, claim, row, controller, world, execution)
    assert reply["week"] == 1
    assert reply["receipt_sha256"] == digest(
        {key: value for key, value in reply.items() if key != "receipt_sha256"}
    )
    args = c.calls[-1][1]
    indexes = json.loads(args[9])
    assert len(reply["evidence_refs"]) == len(controller._initial)
    assert sum(index["record_count"] for index in indexes) == 1
    assert reply["evidence_refs"] == inventory_refs(reply["receipt_id"], indexes)
    assert "current-shared" not in str(reply)
    assert all(
        record["outcome_binding"] is None
        for records in controller._initial.values()
        for record in records
    )


def test_skipping_window_denied_before_clock_or_database_change(monkeypatch):
    claim, row, controller, world, execution, c, _ = setup(monkeypatch)
    before = controller.capture()
    claim.value["week"] = 2
    with pytest.raises(ValueError, match="next unreleased"):
        release(c, claim, row, controller, world, execution)
    assert controller.capture() == before and c.calls == []


def test_next_window_needs_actual_completed_prior_graph_not_worker_boolean(monkeypatch):
    claim, row, controller, world, execution, c, data = setup(monkeypatch)
    reply = release(c, claim, row, controller, world, execution)
    args = c.calls[-1][1]
    data["releases"] = [
        {"reply": reply, "reply_sha256": digest(reply), "inventory": json.loads(args[9])}
    ]
    row.update(last_week=1, controller_state_sha256=args[6])
    claim.value["week"] = 2
    before = controller.capture()
    with pytest.raises(ValueError, match="completed prior weekly"):
        release(c, claim, row, controller, world, execution)
    assert controller.capture() == before


def test_failed_atomic_release_commit_returns_no_successful_receipt(monkeypatch):
    claim, row, controller, world, execution, c, _ = setup(monkeypatch)
    c.commit_allowed = False
    with pytest.raises(RuntimeError, match="commit_unconfirmed"):
        release(c, claim, row, controller, world, execution)


def test_release_reference_count_does_not_truncate_large_released_collection(monkeypatch):
    claim, row, controller, world, execution, c, _ = setup(monkeypatch)
    original = controller._initial["reports"][0]
    # More than500 released rows are fully hashed under one collection index.
    controller._initial["reports"] = [
        deepcopy(original)
        | {"public": {"id": "manufactured-" + str(index), "text": "released baseline"}}
        for index in range(1200)
    ]
    reply = release(c, claim, row, controller, world, execution)
    indexes = json.loads(c.calls[-1][1][9])
    reports = next(value for value in indexes if value["collection"] == "reports")
    assert reports["record_count"] == 1200
    assert len(reply["evidence_refs"]) == len(controller._initial)
