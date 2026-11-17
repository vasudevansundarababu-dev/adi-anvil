"""Mocked SQL/broker custody only; no model, native runtime or SQL qualification."""

from contextlib import contextmanager

import pytest

from anvil import marketing_paid_roles as roles
from anvil import marketing_paid_turn as turns
from anvil import marketing_response_diagnostics as diagnostics


def setup(monkeypatch, *, protocol="invalid", allowed=True):
    statements = []
    finding = {"protocol_status": protocol, "observed_failure": "invalid_json"}
    monkeypatch.setattr(diagnostics, "inspect", lambda *args: finding)

    class Cursor:
        def fetchone(self):
            return {"allowed": allowed}

    class Connection:
        def execute(self, sql, parameters):
            statements.append((sql, parameters))
            return Cursor()

    @contextmanager
    def connections():
        yield Connection()

    job = {"id": "job", "lease_token": "lease", "plan_id": "plan"}
    completed = {"id": "actual-completed-call", "text": "completed-response"}
    return connections, job, completed, statements, finding


def test_invalid_response_requires_committed_custody_before_typed_rejection(monkeypatch):
    connections, job, completed, statements, finding = setup(monkeypatch)
    with pytest.raises(turns.CandidateProtocolRejected):
        turns.validate_response_protocol(connections, job, 7, completed, {}, "intent")
    assert len(statements) == 1
    assert statements[0][1][:5] == ("job", "lease", "plan", 7, "actual-completed-call")
    assert statements[0][1][5].obj == finding


def test_unconfirmed_custody_is_not_reported_as_confirmed_candidate_rejection(monkeypatch):
    connections, job, completed, statements, _ = setup(monkeypatch, allowed=False)
    with pytest.raises(RuntimeError, match="custody_unconfirmed") as failure:
        turns.validate_response_protocol(connections, job, 7, completed, {}, "intent")
    assert not isinstance(failure.value, turns.CandidateProtocolRejected)
    assert len(statements) == 1


def test_invalid_completed_response_stops_before_client_or_tool_acquisition(monkeypatch):
    connections, job, completed, statements, _ = setup(monkeypatch)
    dispatched = []
    monkeypatch.setattr(roles, "claim_turn", lambda *args: (0, {"role": "intent"}))
    monkeypatch.setattr(roles, "response", lambda *args: completed)

    def dispatch(*args):
        dispatched.append(True)
        return completed["text"]

    def forbidden(*args):
        pytest.fail("Rejected response must not acquire client, apply effects or complete turn")

    monkeypatch.setattr(roles, "apply_turn", forbidden)
    monkeypatch.setattr(roles, "record_turn", forbidden)
    adapter = roles.RoleAdapter(connections, job, "episode", 0, {}, dispatch, forbidden)
    with pytest.raises(turns.CandidateProtocolRejected):
        adapter({"id": "intent", "type": "agent_step"}, {}, 1, 1)
    assert dispatched == [True]
    assert len(statements) == 1


def test_valid_turn_transport_failure_is_not_candidate_protocol_finding(monkeypatch):
    connections, job, completed, statements, _ = setup(monkeypatch, protocol="valid")
    monkeypatch.setattr(roles, "claim_turn", lambda *args: (0, {"role": "intent"}))
    monkeypatch.setattr(roles, "response", lambda *args: completed)

    @contextmanager
    def client(*args):
        yield object()

    def transport(*args):
        raise OSError("manufactured MCP transport failure")

    monkeypatch.setattr(roles, "apply_turn", transport)
    monkeypatch.setattr(roles, "record_turn", lambda *args: pytest.fail("No completed turn"))
    adapter = roles.RoleAdapter(connections, job, "episode", 0, {}, lambda *args: completed["text"], client)
    with pytest.raises(OSError, match="transport"):
        adapter({"id": "intent", "type": "agent_step"}, {}, 1, 1)
    assert statements == []


def test_host_contract_failure_does_not_create_candidate_finding(monkeypatch):
    connections, job, completed, statements, _ = setup(monkeypatch)

    def invalid_host(*args):
        raise ValueError("manufactured host contract mismatch")

    monkeypatch.setattr(diagnostics, "inspect", invalid_host)
    with pytest.raises(ValueError, match="host contract"):
        turns.validate_response_protocol(connections, job, 0, completed, {}, "intent")
    assert statements == []
