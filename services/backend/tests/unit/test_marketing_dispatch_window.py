"""Offline dispatch-boundary controls; no SQL, provider or native qualification."""

from datetime import datetime, timedelta, timezone

import pytest

from anvil import marketing_capture_evidence_store as custody
from anvil import providers
from anvil import workspace_execution as execution

NOW = datetime(2026, 11, 14, 20, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(execution, "datetime", Clock)


def budget(seconds=40):
    return {
        "remaining_seconds": seconds,
        "dispatch_before_utc": (NOW + timedelta(seconds=seconds)).isoformat(),
        "capture_accepted": False,
    }


def request():
    return providers.ActorRequest(
        model="offline-test-model", actor_text='Exact résumé 🦉\n"source"',
        max_output_tokens=200, timeout_seconds=90,
    )


def test_actual_request_text_and_committed_call_are_checked_and_timeout_preserves_reserve(monkeypatch):
    seen = []
    original = request()
    connection = object()

    def check(*args):
        seen.append(args)
        return budget(40)

    monkeypatch.setattr(custody, "require_dispatch_prompt", check)
    checked = execution._marketing_dispatch_request(
        connection, "plan", 7, "committed-call", original, NOW + timedelta(seconds=17)
    )
    assert seen == [(connection, "plan", 7, "committed-call", original.actor_text)]
    assert checked.timeout_seconds == 17
    assert checked.actor_text.encode("utf-8") == original.actor_text.encode("utf-8")
    assert checked.model == original.model and checked.max_output_tokens == 200
    assert original.timeout_seconds == 90


def test_fresh_private_deadline_can_shorten_but_cannot_extend_original_budget(monkeypatch):
    monkeypatch.setattr(custody, "require_dispatch_prompt", lambda *args: budget(8))
    checked = execution._marketing_dispatch_request(
        None, "plan", 0, "call", request(), NOW + timedelta(seconds=17)
    )
    assert checked.timeout_seconds == 8


def test_prompt_custody_denial_propagates_without_reconstructing_or_retrying(monkeypatch):
    calls = []

    def deny(*args):
        calls.append(args)
        raise RuntimeError("prompt mismatch_no_retry")

    monkeypatch.setattr(custody, "require_dispatch_prompt", deny)
    with pytest.raises(RuntimeError, match="prompt mismatch_no_retry"):
        execution._marketing_dispatch_request(
            None, "plan", 0, "call", request(), NOW + timedelta(seconds=17)
        )
    assert len(calls) == 1


def test_preparation_time_cannot_reset_original_elapsed_deadline(monkeypatch):
    monkeypatch.setattr(custody, "require_dispatch_prompt", lambda *args: budget(40))
    with pytest.raises(RuntimeError, match="cleanup_reserve_elapsed_no_retry"):
        execution._marketing_dispatch_request(
            None, "plan", 0, "call", request(), NOW - timedelta(seconds=1)
        )


@pytest.mark.parametrize("seconds", [True, 0, -1, 40.0, "40"])
def test_unknown_or_coerced_remaining_time_cannot_admit_dispatch(seconds):
    with pytest.raises(RuntimeError, match="original_dispatch_budget_required"):
        execution._marketing_dispatch_deadline(budget(seconds=40) | {"remaining_seconds": seconds})


def test_capture_acceptance_flag_cannot_be_used_as_dispatch_authority():
    with pytest.raises(RuntimeError, match="original_dispatch_budget_required"):
        execution._marketing_dispatch_deadline(budget() | {"capture_accepted": True})


def test_naive_deadline_is_not_server_time_authority():
    with pytest.raises(RuntimeError, match="original_dispatch_deadline_required"):
        execution._marketing_dispatch_deadline(budget() | {"dispatch_before_utc": "2026-11-14T20:01:00"})


def test_longer_capture_reservation_never_increases_existing_request_timeout(monkeypatch):
    monkeypatch.setattr(custody, "require_dispatch_prompt", lambda *args: budget(1000))
    checked = execution._marketing_dispatch_request(
        None, "plan", 0, "call", request(), NOW + timedelta(seconds=1000)
    )
    assert checked.timeout_seconds == 90
