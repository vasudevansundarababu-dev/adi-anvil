"""Actual compiler/adapter with manufactured SQL and commits, never service QA."""

import hashlib
import json
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_marketing_capture_evidence import packet

from anvil import marketing_capture_evidence_store as store
from anvil.praxis_generic_contract import digest


def setup(monkeypatch, *, uncertain_intent=False, allow_snapshot=True, allow_manifest=True):
    context, rows, _ = packet()
    claim = SimpleNamespace(**{key: context["scope"][key] for key in ("project_id", "job_id", "plan_id")},
                            actor_id=str(uuid4()), lease_token=str(uuid4()))
    context["scope"]["lease_sha256"] = hashlib.sha256(claim.lease_token.encode()).hexdigest()
    context["quiescence"].update(context["scope"])
    context["quiescence"].pop("receipt_sha256")
    context["quiescence"]["receipt_sha256"] = digest(context["quiescence"])
    now = datetime.now(timezone.utc)
    context.update(expires_at=(now + timedelta(seconds=120)).isoformat(),
                   materialize_before=(now + timedelta(seconds=90)).isoformat())
    events, snapshots = [], []
    state = {"intent": None, "descriptor": None}

    def status():
        return {"schema_version": "anvil.marketing-api-evidence-status.v1", "scope": context["scope"],
                **{key: context[key] for key in ("manifest_id", "enrollment_id", "request_sha256", "operation_nonce")},
                "state": "ready" if state["descriptor"] is not None else "materialization_unknown" if state["intent"] else "reserved_no_content",
                "descriptor": deepcopy(state["descriptor"]), "capture_accepted": False, "native_qualified": False}

    class Cursor:
        itersize = None

        def __enter__(self):
            return self

        def __exit__(self, *_):
            events.append("cursor_closed")

        def execute(self, sql, args):
            assert "intent_committed" in events and args[-1] == state["intent"]
            events.append("enumerate_after_committed_intent")
            self.iterator = iter(rows)

        def fetchone(self):
            row = next(self.iterator, None)
            return {"value": row} if row else None

    class Connection:
        def execute(self, sql, args):
            events.append(sql)
            if "set_config('statement_timeout'" in sql:
                assert "intent_committed" in events
                assert args[0].endswith("ms") and 0 < int(args[0][:-2]) <= 90000
                return None
            if "capture_evidence_status(" in sql:
                return SimpleNamespace(fetchone=lambda: {"value": status()})
            if "begin_capture_evidence" in sql:
                state["intent"] = args[-1]
                return SimpleNamespace(fetchone=lambda: {"value": deepcopy(context) | {"intent_id": str(args[-1])}})
            if "retain_capture_evidence_snapshot" in sql:
                snapshots.append(args)
                return SimpleNamespace(fetchone=lambda: {"allowed": allow_snapshot})
            if "commit_capture_evidence" in sql:
                assert "cursor_closed" in events
                assert hashlib.sha256(args[5].encode()).hexdigest() == args[6]
                if allow_manifest:
                    state["descriptor"] = json.loads(args[7])
                return SimpleNamespace(fetchone=lambda: {"allowed": allow_manifest})
            pytest.fail("No other SQL, SDK or service request allowed")

        def cursor(self, *, name):
            assert name.startswith("anvil_evidence_")
            return Cursor()

    @contextmanager
    def transaction(*_):
        yield Connection()
        if state["intent"] and "intent_committed" not in events:
            events.append("intent_committed")
            if uncertain_intent:
                raise RuntimeError("manufactured_commit_unknown")

    monkeypatch.setattr(store, "transaction", transaction)
    return claim, state, events, snapshots


def test_actual_adapter_commits_one_intent_then_streams_snapshots_and_reads_back_original_content(monkeypatch):
    claim, state, events, snapshots = setup(monkeypatch)
    result = store.materialize(claim)
    assert result["state"] == "ready" and result["descriptor"] == state["descriptor"]
    assert result["capture_accepted"] is False and result["native_qualified"] is False
    assert len(snapshots) == 2
    assert events.index("intent_committed") < events.index("enumerate_after_committed_intent")
    writes = [event for event in events if "begin_capture_evidence" in event or "commit_capture_evidence" in event]
    assert len(writes) == 2
    assert store.materialize(claim) == result
    assert len([event for event in events if "begin_capture_evidence" in event]) == 1


def test_expired_sql_cutoff_never_issues_another_statement():
    connection = Connection()
    with pytest.raises(RuntimeError, match="cutoff reached_no_retry"):
        store._statement_cutoff(connection, {"materialize_before": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()})
    assert not connection.calls


def test_callback_lost_after_scheduling_leaves_consumed_intent_without_bulk_or_reclaim(monkeypatch):
    claim, state, events, snapshots = setup(monkeypatch)
    scheduled = store.schedule_materialization(claim)
    assert type(scheduled) is store.ScheduledMaterialization
    assert state["intent"] and "intent_committed" in events
    assert "enumerate_after_committed_intent" not in events and not snapshots
    with pytest.raises(RuntimeError, match="already consumed_unknown_no_retry"):
        store.schedule_materialization(claim)
    assert len([event for event in events if "begin_capture_evidence" in event]) == 1


def test_same_process_callback_can_execute_only_once_and_never_repair_a_failed_attempt(monkeypatch):
    claim, _, events, _ = setup(monkeypatch, allow_manifest=False)
    scheduled = store.schedule_materialization(claim)
    with pytest.raises(RuntimeError, match="unconfirmed"):
        store._materialize_scheduled(claim, scheduled)
    before = len(events)
    with pytest.raises(RuntimeError, match="callback already consumed_unknown_no_retry"):
        store._materialize_scheduled(claim, scheduled)
    assert len(events) == before


def test_lost_intent_commit_never_enumerates_or_reclaims_even_when_slot_still_exists(monkeypatch):
    claim, _, events, snapshots = setup(monkeypatch, uncertain_intent=True)
    with pytest.raises(RuntimeError, match="manufactured_commit_unknown"):
        store.materialize(claim)
    assert not snapshots and "enumerate_after_committed_intent" not in events
    with pytest.raises(RuntimeError, match="already consumed_unknown"):
        store.materialize(claim)
    assert len([event for event in events if "begin_capture_evidence" in event]) == 1


@pytest.mark.parametrize("boundary", ["snapshot", "manifest"])
def test_unconfirmed_retention_never_yields_ready_or_retries(boundary, monkeypatch):
    claim, state, events, _ = setup(monkeypatch, allow_snapshot=boundary != "snapshot", allow_manifest=boundary != "manifest")
    with pytest.raises(RuntimeError, match="unconfirmed"):
        store.materialize(claim)
    assert state["descriptor"] is None
    with pytest.raises(RuntimeError, match="already consumed_unknown"):
        store.materialize(claim)
    assert len([event for event in events if "begin_capture_evidence" in event]) == 1


class Connection:
    def __init__(self, value=None, allowed=True):
        self.value, self.allowed, self.calls = value, allowed, []

    def execute(self, sql, args):
        self.calls.append((sql, args))
        return SimpleNamespace(fetchone=lambda: {"value": self.value, "allowed": self.allowed})


def test_rendered_prompt_original_utf8_is_retained_with_exact_stage_before_any_sdk():
    plan = {"id": str(uuid4()), "project_id": str(uuid4())}
    intent = {"plan_id": plan["id"], "project_id": plan["project_id"], "stage_index": 0}
    text = 'Original résumé 🦉 "quoted"\nexact bytes'
    connection = Connection()
    store.retain_prompt(connection, plan, intent, text)
    assert connection.calls[0][1] == (plan["id"], 0, text, hashlib.sha256(text.encode()).hexdigest())
    with pytest.raises(RuntimeError, match="before_sdk_no_retry"):
        store.retain_prompt(Connection(allowed=False), plan, intent, text)


@pytest.mark.parametrize("changed", ["prompt_utf8", "prompt_sha256", "request_sha256", "call_id", "stage_index"])
def test_actual_dispatch_request_must_match_original_prompt_and_call_identity(changed):
    plan, call = str(uuid4()), str(uuid4())
    text = "original exact actor input"
    value = {"plan_id": plan, "call_id": call, "stage_index": 0, "prompt_utf8": text,
             "prompt_sha256": hashlib.sha256(text.encode()).hexdigest(), "request_sha256": hashlib.sha256(text.encode()).hexdigest(),
             "dispatch_before_utc": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()}
    value[changed] = 1 if changed == "stage_index" else "changed"
    with pytest.raises(RuntimeError, match="differs from retained original"):
        store.require_dispatch_prompt(Connection(value), plan, 0, call, text)


def test_actual_prompt_check_returns_only_original_cleanup_bounded_deadline():
    plan, call = str(uuid4()), str(uuid4())
    text = "original"
    value = {"plan_id": plan, "call_id": call, "stage_index": 0, "prompt_utf8": text,
             "prompt_sha256": hashlib.sha256(text.encode()).hexdigest(), "request_sha256": hashlib.sha256(text.encode()).hexdigest(),
             "dispatch_before_utc": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()}
    result = store.require_dispatch_prompt(Connection(value), plan, 0, call, text)
    assert 0 < result["remaining_seconds"] <= 60 and result["capture_accepted"] is False
    value["dispatch_before_utc"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with pytest.raises(RuntimeError, match="cleanup reserve"):
        store.require_dispatch_prompt(Connection(value), plan, 0, call, text)
