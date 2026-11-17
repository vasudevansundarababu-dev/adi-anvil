"""New API contract/readonly reconstruction with mocked SQL, never native proof."""

import hashlib
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from test_marketing_paid_world import fixture

from anvil import marketing_world_quiescence as stop
from anvil.marketing_paid_world import WorldCall
from anvil.praxis_generic_contract import digest


def setup(monkeypatch):
    job, prepared, attachment = fixture(monkeypatch)
    scope = {
        key: attachment[key]
        for key in ("world_binding_id", "world_binding_sha256", "episode_id", "generation")
    }
    claim = WorldCall(
        project_id=job["project_id"],
        actor_id=job["actor_id"],
        job_id=job["id"],
        plan_id=job["plan_id"],
        lease_token=job["lease_token"],
        operation="fence",
        value=scope,
    )
    context = {
        "session": {
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
                )
            },
            "lease_sha256": hashlib.sha256(job["lease_token"].encode()).hexdigest(),
            "attachment": attachment,
        },
        "execution": prepared["execution"],
        "source_qualification_sha256": "e" * 64,
        "observed_at": "2026-11-14T12:00:00Z",
        "graph_ledger_sha256": "1" * 64,
        "graph_records": {"attachment": attachment, "effects": [], "releases": [], "turns": []},
        "pending": {name: 0 for name in stop.Pending.model_fields},
        "fence": None,
        "quiescence": None,
    }

    class Connection:
        allow = True

        def __init__(self):
            self.calls = []

        def execute(self, sql, parameters):
            self.calls.append((sql, parameters))
            if "world_stop_context" in sql:
                self.answer = {"value": deepcopy(context)}
            elif "private_world_service_records" in sql:
                self.answer = {"value": {"records": [], "source_contract_sha256": "a" * 64}}
            elif "record_world_fence" in sql:
                self.answer = {"allowed": self.allow}
                if self.allow:
                    context["fence"] = {
                        "terminal": json.loads(parameters[4]),
                        "receipt": json.loads(parameters[5]),
                        "body_sha256": parameters[6],
                    }
            elif "record_world_quiescence" in sql:
                self.answer = {"allowed": self.allow}
                if self.allow:
                    context["quiescence"] = {
                        "receipt": json.loads(parameters[5]),
                        "body_sha256": parameters[6],
                    }
            else:
                pytest.fail("No inference/tool/other SQL allowed")
            return self

        def fetchone(self):
            return self.answer

    return claim, context, Connection()


def manufactured_terminal(monkeypatch, terminal="done"):
    from anvil import marketing_world_release

    body = {
        "state": {"terminal": terminal},
        "workflow_status": "closed" if terminal == "done" else "hold_requires_qualification",
        "partial_reason": None,
    }
    graph = body | {"reconstruction_sha256": digest(body)}
    monkeypatch.setattr(marketing_world_release, "recorded_records", lambda *args: (graph, {}))


def test_zero_counters_without_recorded_terminal_cannot_claim_quiescence(monkeypatch):
    claim, _, c = setup(monkeypatch)
    result = stop.dispatch(c, claim)
    assert result["state"] == "fenced_unknown" and result["quiescence"] is None
    assert result["physical_stop_verified"] is False and result["native_qualified"] is False
    assert not any("record_world_quiescence" in sql for sql, _ in c.calls)


def test_terminal_plus_zero_ledger_has_two_distinct_immutable_receipts(monkeypatch):
    claim, context, c = setup(monkeypatch)
    manufactured_terminal(monkeypatch)
    result = stop.dispatch(c, claim)
    assert result["state"] == "api_quiescent"
    proof = result["quiescence"]
    assert proof["fence_receipt_sha256"] == result["fence"]["receipt_sha256"]
    assert proof["receipt_sha256"] != result["fence"]["receipt_sha256"]
    assert proof["physical_stop_verified"] is False and proof["native_qualified"] is False
    before = deepcopy(context)
    calls = len(c.calls)
    repeated = stop.dispatch(c, claim.model_copy(update={"operation": "quiescence"}))
    assert repeated == result and context == before
    assert all("world_stop_context" in sql or "private_world_service_records" in sql for sql, _ in c.calls[calls:])


def test_recorded_hold_still_requires_separate_qualification(monkeypatch):
    claim, _, c = setup(monkeypatch)
    manufactured_terminal(monkeypatch, "awaiting_authority")
    result = stop.dispatch(c, claim)
    assert result["quiescence"]["terminal_status"] == "recorded_hold_requires_qualification"
    assert result["native_qualified"] is False


def test_unknown_sdk_never_disappears_behind_terminal_graph(monkeypatch):
    claim, context, c = setup(monkeypatch)
    manufactured_terminal(monkeypatch)
    context["pending"]["sdk_unknown"] = 1
    result = stop.dispatch(c, claim)
    assert result["state"] == "fenced_unknown" and result["quiescence"] is None


def test_unconfirmed_fence_commit_returns_no_positive_receipt(monkeypatch):
    claim, _, c = setup(monkeypatch)
    c.allow = False
    with pytest.raises(RuntimeError, match="commit_unconfirmed"):
        stop.dispatch(c, claim)


def test_cross_world_scope_denied_before_receipt_write(monkeypatch):
    claim, _, c = setup(monkeypatch)
    claim.value["episode_id"] = str(uuid4())
    with pytest.raises(ValueError, match="scope"):
        stop.dispatch(c, claim)
    assert all("world_stop_context" in sql for sql, _ in c.calls)


def test_foreign_quiescence_receipt_cannot_attach_to_same_fence(monkeypatch):
    claim, _, c = setup(monkeypatch)
    manufactured_terminal(monkeypatch)
    result = stop.dispatch(c, claim)
    foreign = deepcopy(result["quiescence"])
    foreign["plan_id"] = str(uuid4())
    foreign["receipt_sha256"] = digest({k: v for k, v in foreign.items() if k != "receipt_sha256"})
    with pytest.raises(ValueError, match="same fenced"):
        stop.Status.model_validate(result | {"quiescence": foreign})


def test_number_zero_cannot_masquerade_as_false_receipt_flag(monkeypatch):
    claim, _, c = setup(monkeypatch)
    result = stop.dispatch(c, claim)
    with pytest.raises(ValueError, match="Boolean"):
        stop.Status.model_validate(result | {"native_qualified": 0})
