"""Complete public delivery coverage; manufactured sources are not legal review."""

from copy import deepcopy
import hashlib

from anvil.golden_kyc_policy_chunks import build, CHUNK_SCHEMA
from anvil.golden_kyc_policy_observations import delivered_state_rules


def delivered():
    text = "Synthetic public state source. 😀" * 500
    source = {"id": "synthetic-state", "version": "test-only", "text": text,
              "public_text_sha256": hashlib.sha256(text.encode()).hexdigest()}
    root, documents = build({"schema_version": "anvil.bound-application-policy.v2",
                             "application_id": "synthetic-application", "bound_common_rules": [],
                             "bound_state_rules": [source]})
    events = [{"action": "policy.read", "record": {"status": "completed", "result": root}}]
    events += [{"action": "document.read", "record": {"status": "completed", "result": doc}}
               for doc in documents.values()]
    return source, events


def test_only_complete_actually_delivered_sources_count_as_read():
    source, events = delivered()
    assert delivered_state_rules(events) == [source]
    assert delivered_state_rules(events, application_id="foreign-application") == []
    assert delivered_state_rules(events[:1]) == []
    for position in range(1, len(events)):
        assert delivered_state_rules(events[:position] + events[position + 1:]) == []


def test_mutated_chunk_or_different_binding_never_counts_as_original_delivery():
    _, events = delivered()
    wrong = deepcopy(events)
    chunk = next(event["record"]["result"] for event in wrong
                 if event["record"]["result"].get("schema_version") == CHUNK_SCHEMA)
    chunk["text"] = "changed synthetic text"
    assert delivered_state_rules(wrong) == []
    wrong = deepcopy(events)
    wrong[0]["record"]["result"]["application_id"] = "foreign-application"
    assert delivered_state_rules(wrong) == []


def test_denied_events_and_conflicting_duplicate_observations_do_not_count():
    _, events = delivered()
    wrong = deepcopy(events)
    wrong[-1]["record"]["status"] = "denied"
    assert delivered_state_rules(wrong) == []
    conflict = deepcopy(events[-1])
    conflict["record"]["result"]["application_id"] = "foreign"
    assert delivered_state_rules([*events, conflict]) == []
