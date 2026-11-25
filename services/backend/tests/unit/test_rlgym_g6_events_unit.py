"""G6 (KYC Judgment v1 C3): scenario events in the sealed evidence. The runtime appends each fired record to the
episode state (collection `scenario_events`, pending Studio's name: RL Gym review); RL Gym keeps them, and the notices
the agent actually read through notices.read, in the bundle. Episodes without events keep today's bundle shape."""

import inspect

from anvil.rlgym.runs import events, worker

FIRED = {
    "scenario_id": "kj-1.scenario",
    "event_id": "gb-03-v2",
    "case_id": "kj-1",
    "trigger_sequence": 7,
    "published_at_sequence": 7,
    "rule_id": "GB-03",
    "from_version": 1,
    "to_version": 2,
    "from_text_sha256": "a" * 64,
    "to_text_sha256": "b" * 64,
    "notice_id": "bulletin-0001",
}


def test_fired_records_and_notices_read_are_kept():
    snaps = {"start": {"scenario_events": []}, "end": {"scenario_events": [FIRED]}}
    transcript = [
        {"step": 1, "tool": "screening.check", "observation": {"ok": True, "sequence": 7}},
        {
            "step": 2,
            "tool": "notices.read",
            "observation": {
                "ok": True,
                "sequence": 8,
                "output": {
                    "records": [
                        {
                            "notice_id": "bulletin-0001",
                            "source": "policy_service",
                            "title": "GB-03 v2",
                            "published_at_sequence": 7,
                        }
                    ]
                },
            },
        },
    ]
    out = events.scenario_events(snaps, transcript)
    assert out["fired"] == [FIRED]
    assert out["notices_read"] == [
        {"notice_id": "bulletin-0001", "read_at_sequence": 8, "source": "policy_service"}
    ]
    assert out["unread"] == []


def test_a_fired_notice_the_agent_never_read_is_listed():
    out = events.scenario_events({"end": {"scenario_events": [FIRED]}}, [])
    assert out["unread"] == ["bulletin-0001"]


def test_no_events_means_nothing_added():
    assert (
        events.scenario_events(
            {"start": {}, "end": {}}, [{"step": 1, "tool": "x", "observation": {"ok": True}}]
        )
        is None
    )
    assert events.scenario_events(None, []) is None


def test_the_worker_adds_them_only_when_present():
    src = inspect.getsource(worker.execute)
    assert "scenario_log.scenario_events(snapshots, transcript)" in src
    assert '{"scenario_events": scenario}' in src
