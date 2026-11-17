"""Private source-schema controls, not dataset/runtime qualification or import."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from test_marketing_world_descriptor_services import source

from anvil.marketing_world_definition import COLLECTIONS, definition
from anvil.marketing_world_service_sources import with_services
from anvil.praxis_generic_contract import digest


def candidate():
    files, pins, execution, _ = source()
    start = datetime(2027, 1, 4, tzinfo=timezone.utc)
    records = {name: [] for name in COLLECTIONS}
    for branch in ("positive", "null", "negative"):
        path = f"reviewer_only/us-pair/GT2-R01/reuse-test-{branch}/conditional_campaign_approval.json"
        records["work"].append({"source_path": path, "source_sha256": pins[path], "released_at": start.isoformat(),
                               "outcome_binding": branch, "public": {"id": "manufactured-branch-marker"}})
    context = {"case_id": "GT2-R01", "locale": "en-US", "campaign_ref": "manufactured-campaign",
               "task_id": "manufactured-task", "revision_id": "manufactured-revision",
               "dataset_id": "manufactured-dataset", "dataset_version": "1", "dataset_sha256": "a" * 64,
               "public_source_refs": [], "currency": "USD", "business_budget_minor": 20000000,
               "origin": "fictional_campaign_environment"}
    original = {"schema_version": "anvil.marketing-private-world-definition.v1", "case_id": "GT2-R01",
                "case_snapshot_sha256": "a" * 64, "execution_sha256": digest(execution),
                "fixture_manifest_sha256": "b" * 64, "source_manifest_sha256": "b" * 64,
                "rights_receipt_sha256": "c" * 64, "campaign_context": context, "start": start.isoformat(),
                "branch_seed": "d" * 64, "branch_cycle": ["positive", "null", "negative"], "source_hashes": pins,
                "records": records, "public_columns": {name: ["id"] for name in COLLECTIONS},
                "windows": [{"week": i + 1, "instant": (start + timedelta(days=7 * i)).isoformat(),
                             "window_ref": f"manufactured-window-{i+1}", "source_paths": ["cases/GT2-R01/case.json"]}
                            for i in range(12)]}
    return original, with_services(original, files, execution)


def test_explicit_service_v2_preserves_v1_and_source_derived_public_context():
    original, successor = candidate()
    before = digest(deepcopy(original))
    old = definition(original)
    new = definition(successor)
    assert old.schema_version == "anvil.marketing-private-world-definition.v1"
    assert "service_contract" not in old.model_dump()
    assert new.service_contract["qualification_granted"] is False
    assert digest(original) == before
    assert any(row.public.get("id") == "GT2-R01_commute_reuse_test" for row in new.records["documents"])
    assert all(row.outcome_binding is not None for row in new.records["work"])


def test_changed_normalized_values_cannot_be_certified_with_a_new_self_hash():
    _, successor = candidate()
    successor["service_contract"]["case"]["approved_creative_catalogue"][0]["descriptor_sha256"] = "f" * 64
    successor["service_contract_sha256"] = digest(successor["service_contract"])
    with pytest.raises(ValueError, match="actual pinned source bytes"):
        definition(successor)


def test_wrong_public_projection_cannot_hide_behind_correct_source_file_hash():
    _, successor = candidate()
    successor["records"]["content"][0]["public"]["descriptor_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="approved baseline source"):
        definition(successor)
