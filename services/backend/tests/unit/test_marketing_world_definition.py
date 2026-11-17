"""Manufactured private source records; no rights/branch/runtime qualification."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from test_marketing_paid_world import fixture

from anvil.marketing_task2_contract import WIRE_ROLES
from anvil.marketing_world_definition import COLLECTIONS, definition


def source(monkeypatch):
    _, _, attachment = fixture(monkeypatch)
    start = datetime(2026, 11, 14, tzinfo=timezone.utc)
    path = "cases/GT2-R01/manufactured-records.json"
    body = {
        "schema_version": "anvil.marketing-private-world-definition.v1",
        "case_id": "GT2-R01",
        "case_snapshot_sha256": "c" * 64,
        "execution_sha256": attachment["execution_sha256"],
        "fixture_manifest_sha256": "f" * 64,
        "source_manifest_sha256": "f" * 64,
        "rights_receipt_sha256": "a" * 64,
        "campaign_context": attachment["campaign_context"],
        "start": start.isoformat(),
        "branch_seed": "7" * 64,
        "branch_cycle": ["positive", "null", "negative"],
        "source_hashes": {path: "d" * 64},
        "public_columns": {name: ["id", "text"] for name in COLLECTIONS},
        "records": {name: [] for name in COLLECTIONS},
        "windows": [
            {
                "week": week,
                "instant": (start + timedelta(days=7 * (week - 1))).isoformat(),
                "window_ref": "manufactured-window:" + str(week),
                "source_paths": [path],
            }
            for week in range(1, 13)
        ],
    }
    for index, branch in enumerate(body["branch_cycle"]):
        for future in (False, True):
            body["records"]["reports"].append(
                {
                    "source_path": path,
                    "source_sha256": "d" * 64,
                    "released_at": (start + timedelta(days=7 if future else 0)).isoformat(),
                    "outcome_binding": branch,
                    "public": {
                        "id": ("future-" if future else "current-") + str(index),
                        "text": "manufactured visible evidence",
                    },
                }
            )
    for future in (False, True):
        body["records"]["reports"].append(
            {
                "source_path": path,
                "source_sha256": "d" * 64,
                "released_at": (start + timedelta(days=7 if future else 0)).isoformat(),
                "outcome_binding": None,
                "public": {
                    "id": "future-shared" if future else "current-shared",
                    "text": "manufactured baseline evidence",
                },
            }
        )
    return body


def test_case_repetition_selects_all_branches_without_candidate_model_input(monkeypatch):
    world = definition(source(monkeypatch))
    assert {world.branch(index) for index in range(3)} == {"positive", "null", "negative"}
    assert [world.branch(index) for index in range(9)] == [
        world.branch(index) for index in range(3)
    ] * 3
    for invalid in (None, True, -1, 1000, "0"):
        with pytest.raises(ValueError, match="repetition"):
            world.branch(invalid)


def test_only_selected_branch_and_released_public_projection_reach_role(monkeypatch):
    world = definition(source(monkeypatch))
    controller = world.controller(0)
    token = controller.credential(WIRE_ROLES["intent"])
    response = controller.call(token, 0, "evidence", {"collection": "reports"})
    assert len(response["records"]) == 1
    assert response["records"][0]["id"].startswith("current-")
    assert set(response["records"][0]) == {"id", "text"}
    controller.advance(world.windows[1].instant.isoformat())
    assert len(controller.call(token, 0, "evidence", {"collection": "reports"})["records"]) == 2


def test_missing_collection_or_private_extra_column_is_rejected(monkeypatch):
    body = source(monkeypatch)
    changed = deepcopy(body)
    del changed["records"]["offers"]
    with pytest.raises(ValueError, match="collection"):
        definition(changed)
    body["records"]["reports"][0]["public"]["private_expected_award"] = 4
    with pytest.raises(ValueError, match="projected source"):
        definition(body)


def test_source_mismatch_or_missing_branch_cannot_be_qualified_by_shape(monkeypatch):
    body = source(monkeypatch)
    body["records"]["reports"][0]["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="pinned projected"):
        definition(body)
    body = source(monkeypatch)
    body["records"]["reports"] = [
        row for row in body["records"]["reports"] if row["outcome_binding"] != "negative"
    ]
    with pytest.raises(ValueError, match="three private branch"):
        definition(body)


def test_ambiguous_shared_and_branch_record_identity_is_rejected(monkeypatch):
    body = source(monkeypatch)
    shared = deepcopy(body["records"]["reports"][0])
    shared["outcome_binding"] = None
    body["records"]["reports"].append(shared)
    with pytest.raises(ValueError, match="pinned projected"):
        definition(body)


def test_time_alone_does_not_activate_private_experiment_results(monkeypatch):
    world = definition(source(monkeypatch))
    controller = world.controller(0)
    controller.advance(world.windows[-1].instant.isoformat())
    result = controller.call(
        controller.credential(WIRE_ROLES["intent"]), 0, "evidence", {"collection": "reports"}
    )
    assert {row["id"] for row in result["records"]} == {"current-shared", "future-shared"}
    assert all(row["outcome_binding"] is None for row in controller._initial["reports"])


def test_branch_blinding_seed_is_private_and_low_entropy_integer_is_rejected(monkeypatch):
    body = source(monkeypatch)
    world = definition(body)
    controller = world.controller(0)
    assert world.branch_seed not in str(controller.capture())
    assert world.branch_seed not in str(controller._initial)
    body["branch_seed"] = 17
    with pytest.raises(ValueError):
        definition(body)
