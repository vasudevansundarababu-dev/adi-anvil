"""New same-epoch drain controls; manufactured completion/mocked SQL, not native."""

from contextlib import contextmanager
from copy import deepcopy

import pytest
from test_marketing_world_quiescence import manufactured_terminal, setup

from anvil import marketing_world_quiescence as stop
from anvil.db import digest as effect_digest
from anvil.marketing_task2_workflow_store import Journal
from anvil.praxis_generic_contract import digest


def draining(monkeypatch):
    claim, context, connection = setup(monkeypatch)
    context["pending"].update(sdk_dispatching=1, workflow_pending=1)
    fenced = stop.dispatch(connection, claim)
    assert fenced["state"] == "fenced_pending" and fenced["quiescence"] is None
    context["pending"].update(sdk_dispatching=0, workflow_pending=0)
    context["graph_ledger_sha256"] = "2" * 64
    manufactured_terminal(monkeypatch)
    return claim.model_copy(update={"operation": "drain"}), context, connection, fenced


def test_normal_inflight_completion_seals_final_ledger_without_rewriting_fence(monkeypatch):
    claim, context, connection, first = draining(monkeypatch)
    original = deepcopy(context["fence"])
    result = stop.dispatch(connection, claim)
    proof = result["quiescence"]
    assert result["state"] == "api_quiescent" and context["fence"] == original
    assert result["fence"] == first["fence"]
    assert proof["fenced_graph_ledger_sha256"] == "1" * 64
    assert proof["graph_ledger_sha256"] == "2" * 64
    assert proof["fenced_reconstruction_sha256"] == first["fence"]["reconstruction_sha256"]
    assert proof["reconstruction_sha256"] != proof["fenced_reconstruction_sha256"]
    assert proof["fence_epoch"] == result["fence"]["fence_epoch"] == 1
    assert proof["physical_stop_verified"] is False and proof["native_qualified"] is False


def test_unknown_inflight_call_cannot_be_drained_by_zeroing_other_counters(monkeypatch):
    claim, context, connection, _ = draining(monkeypatch)
    context["pending"]["sdk_unknown"] = 1
    result = stop.dispatch(connection, claim)
    assert result["state"] == "fenced_unknown" and result["quiescence"] is None
    assert not any("record_world_quiescence" in sql for sql, _ in connection.calls)


def test_foreign_epoch_cannot_reuse_same_final_ledger(monkeypatch):
    claim, _, connection, _ = draining(monkeypatch)
    result = stop.dispatch(connection, claim)
    proof = deepcopy(result["quiescence"])
    proof["fence_epoch"] = 2
    proof["receipt_sha256"] = digest(
        {key: value for key, value in proof.items() if key != "receipt_sha256"}
    )
    with pytest.raises(ValueError):
        stop.Status.model_validate(result | {"quiescence": proof})


def test_final_ledger_drift_retains_receipt_but_never_claims_current_quiescence(monkeypatch):
    claim, context, connection, _ = draining(monkeypatch)
    stop.dispatch(connection, claim)
    receipt = deepcopy(context["quiescence"])
    context["graph_ledger_sha256"] = "3" * 64
    with pytest.raises(RuntimeError, match="ledger_drift"):
        stop.dispatch(connection, claim.model_copy(update={"operation": "quiescence"}))
    assert context["quiescence"] == receipt


def test_already_claimed_journal_effect_can_complete_after_fence_without_new_admission(monkeypatch):
    claim, context, _ = setup(monkeypatch)
    statements, fenced = [], False

    class Connection:
        def execute(self, sql, parameters):
            statements.append(sql)
            if "paid_episode_completion_current" in sql:
                self.answer = {"allowed": True}
            elif "paid_episode_current" in sql:
                self.answer = {"allowed": not fenced}
            elif sql.startswith("SELECT * FROM marketing_runtime.workflow_effects"):
                self.answer = None
            return self

        def fetchone(self):
            return self.answer

    @contextmanager
    def connections():
        yield Connection()

    inputs = {"manufactured": True}

    def admitted_adapter(*args):
        nonlocal fenced
        fenced = True  # Existing call completes, no second SDK/tool/effect claim.
        return {"artifact": {}, "receipt": {"input_sha256": effect_digest(inputs)}}

    job = {
        "project_id": str(claim.project_id),
        "actor_id": str(claim.actor_id),
        "id": str(claim.job_id),
        "plan_id": str(claim.plan_id),
        "lease_token": str(claim.lease_token),
    }
    journal = Journal(
        connections,
        job["project_id"],
        job["actor_id"],
        context["session"]["episode_id"],
        0,
        context["execution"],
        admitted_adapter,
        paid_job=job,
    )
    node = next(
        n for n in journal.execution["workflow_graph"]["nodes"] if n["type"] == "agent_step"
    )
    journal(node, inputs, 12, 1)
    assert (
        sum(sql.startswith("INSERT INTO marketing_runtime.workflow_effects") for sql in statements)
        == 1
    )
    assert sum("paid_episode_completion_current" in sql for sql in statements) == 1
    assert sum("SET state='completed'" in sql for sql in statements) == 1
