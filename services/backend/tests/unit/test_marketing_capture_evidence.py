"""New complete-custody compiler controls over manufactured private API rows.

No manifest/slot is issued in a service, SQL is mocked out, no native proof.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from anvil.marketing_capture_evidence import (
    CATEGORIES,
    READY_DESCRIPTOR_CAP,
    SNAPSHOTS,
    prepare,
    verify_content,
)
from anvil.marketing_world_quiescence import Pending
from anvil.praxis_generic_contract import canonical, digest


def packet():
    now = datetime(2026, 11, 14, 18, tzinfo=timezone.utc)
    scope = {key: str(uuid4()) for key in ("project_id", "job_id", "plan_id", "world_binding_id", "episode_id")}
    scope.update({key: "a" * 64 for key in ("world_binding_sha256", "lease_sha256", "source_qualification_sha256", "execution_sha256")}, generation=0)
    quiescence = {"schema_version": "anvil.marketing-world-quiescence.v2", **scope, "fence_id": str(uuid4()), "fence_epoch": 1,
                  "fence_receipt_sha256": "b" * 64, "quiescence_id": str(uuid4()), "observed_at": "2026-11-14T18:00:00Z",
                  "graph_ledger_sha256": "c" * 64, "reconstruction_sha256": "d" * 64,
                  "fenced_graph_ledger_sha256": "c" * 64, "fenced_reconstruction_sha256": "d" * 64,
                  "terminal_status": "recorded_done", "pending": {key: 0 for key in Pending.model_fields},
                  "new_work_permitted": False, "api_quiescent": True, "physical_stop_verified": False, "native_qualified": False}
    quiescence["receipt_sha256"] = digest(quiescence)
    context = {"manifest_id": str(uuid4()), "enrollment_id": str(uuid4()), "intent_id": str(uuid4()),
               "request_sha256": "e" * 64, "operation_nonce": "f" * 64, "scope": scope,
               "expires_at": "2026-11-14T18:01:00Z", "materialize_before": "2026-11-14T18:00:30Z", "quiescence": quiescence,
               "category_counts": {category: 1 for category in CATEGORIES}}
    rows = [{"category": category, "source_id": str(uuid4()),
             "body": {"project_id": scope["project_id"], "plan_id": scope["plan_id"], "manufactured": category,
                      "exact_text": 'Private résumé 🦉 "quoted"\noriginal'}} for category in sorted(CATEGORIES)]
    return context, rows, now


def loader(rows, snapshots):
    originals = {(row["category"], row["source_id"]): canonical(row["body"]) for row in rows}
    original = originals.copy()
    for category, identifier, raw in snapshots:
        original[(category, identifier)] = raw
    return lambda category, identifier: original.get((category, identifier))


def test_complete_api_content_joins_all_categories_and_retains_actual_mutable_snapshots():
    context, rows, now = packet()
    result = prepare(context, iter(rows), now=now)
    assert len(canonical(result.descriptor)) <= READY_DESCRIPTOR_CAP
    assert "Private" not in repr(result)
    assert len(result.snapshots) == len(SNAPSHOTS)
    assert verify_content(result.manifest, result.descriptor, loader(rows, result.snapshots), now=now) == {
        "content_verified": True, "capture_accepted": False, "native_qualified": False}
    rows[0]["body"]["exact_text"] = "changed live mutable row"
    assert result.descriptor["capture_accepted"] is False


def test_actual_mutable_row_changes_cannot_substitute_for_original_private_snapshot():
    context, rows, now = packet()
    result = prepare(context, rows, now=now)
    row = next(row for row in rows if row["category"] == "sdk_calls")
    row["body"]["exact_text"] = "later mutation"
    with pytest.raises(ValueError, match="changed actual API"):
        verify_content(result.manifest, result.descriptor, loader(rows, ()), now=now)
    assert verify_content(result.manifest, result.descriptor, loader(rows, result.snapshots), now=now)["content_verified"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown", "foreign"])
def test_original_slot_and_hashes_do_not_make_partial_or_foreign_evidence_complete(change):
    context, rows, now = packet()
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif change == "unknown":
        rows[0]["category"] = "actor_selected_path"
    else:
        rows[0]["body"]["project_id"] = str(uuid4())
    with pytest.raises(ValueError):
        prepare(context, rows, now=now)


@pytest.mark.parametrize("category", ["sdk_prompts", "turn_observations", "tool_states", "world_source"])
def test_every_empty_or_missing_expected_category_needs_actual_join_closure(category):
    context, rows, now = packet()
    context["category_counts"][category] = 0
    with pytest.raises(ValueError, match="category counts"):
        prepare(context, rows, now=now)


def test_streamed_snapshot_custody_does_not_copy_bulk_into_the_control_descriptor():
    context, rows, now = packet()
    saved = []
    result = prepare(context, rows, now=now, retain_snapshot=lambda *row: saved.append(row))
    assert not result.snapshots and len(saved) == len(SNAPSHOTS)
    assert all(row[2].endswith(b'}') for row in saved)
    assert "exact_text" not in str(result.descriptor)
    assert verify_content(result.manifest, result.descriptor, loader(rows, saved), now=now)["capture_accepted"] is False


def test_descriptor_and_manifest_cannot_be_replaced_by_another_enrollment_or_extended_deadline():
    context, rows, now = packet()
    result = prepare(context, rows, now=now)
    with pytest.raises(ValueError, match="issued API content"):
        verify_content(result.manifest, result.descriptor | {"enrollment_id": str(uuid4())}, loader(rows, result.snapshots), now=now)
    with pytest.raises(ValueError, match="expiry"):
        verify_content(result.manifest, result.descriptor, loader(rows, result.snapshots), now=now + timedelta(seconds=60))
    context["expires_at"] = "2026-12-12T00:00:00Z"
    with pytest.raises(ValueError, match="expiry"):
        prepare(context, rows, now=now)


@pytest.mark.parametrize("seconds", [30, 60])
def test_original_materialization_cutoff_preserves_cleanup_reserve(seconds):
    context, rows, now = packet()
    saved = []
    with pytest.raises(ValueError, match="expiry"):
        prepare(context, rows, now=now + timedelta(seconds=seconds),
                retain_snapshot=lambda *row: saved.append(row))
    assert saved == []


@pytest.mark.parametrize("expires_during", ["enumeration", "snapshot"])
def test_elapsed_work_cannot_reset_materialization_cutoff(monkeypatch, expires_during):
    import anvil.marketing_capture_evidence as compiler

    context, rows, now = packet()
    clock = [now]
    saved = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    def source():
        for row in rows:
            if expires_during == "enumeration":
                clock[0] = now + timedelta(seconds=30)
            yield row

    def retain(*row):
        saved.append(row)
        clock[0] = now + timedelta(seconds=30)

    monkeypatch.setattr(compiler, "datetime", Clock)
    with pytest.raises(ValueError, match="expiry"):
        prepare(context, source(), retain_snapshot=retain)
    assert bool(saved) == (expires_during == "snapshot")


def test_complete_manifest_fits_existing_sdk_tool_effect_population_without_truncation():
    context, _, now = packet()
    counts = {category: 1 if category in {
        "world_source", "world_qualification", "dataset", "runtime_allowlist", "channel_qualification",
        "capture_enrollment", "agent_binding", "world_attachment", "final_world_state", "fence", "quiescence",
    } else 0 for category in CATEGORIES}
    counts.update(world_releases=13, workflow_effects=400, service_effects=400, campaign_states=400,
                  turn_intents=1000, turn_observations=1000, sdk_calls=1000, sdk_prompts=1000,
                  tool_intents=8000, tool_receipts=8000, tool_states=8000)
    context["category_counts"] = counts
    rows = ({"category": category, "source_id": str(index), "body": {"manufactured_index": index}}
            for category in sorted(CATEGORIES) for index in range(counts[category]))
    result = prepare(context, rows, now=now, retain_snapshot=lambda *_: None)
    assert result.descriptor["entry_count"] == sum(counts.values()) == 29224
    assert result.descriptor["category_counts"] == counts
    assert len(result.manifest) <= 16777216
    assert result.descriptor["capture_accepted"] is False
