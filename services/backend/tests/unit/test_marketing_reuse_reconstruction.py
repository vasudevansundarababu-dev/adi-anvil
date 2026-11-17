"""Manufactured record controls for released baseline reconstruction, not SQL proof."""

from copy import deepcopy
from uuid import uuid4

import pytest
from test_marketing_reuse_baseline import attachment, release, released_sources
from test_marketing_world_readiness import setup

from anvil.marketing_paid_reconstruction import reconstruct
from anvil.praxis_generic_contract import digest


def records():
    controller, execution, _, _, sources, *_ = setup()
    released_sources(controller, sources)
    bound = attachment(controller)
    bound.update(schema_version="anvil.marketing-world-attachment.v1", project_id=str(uuid4()),
                 actor_id=str(uuid4()), job_id=str(uuid4()), plan_id=str(uuid4()),
                 case_snapshot_sha256="a" * 64, execution_sha256=digest(execution),
                 native_binding_sha256="c" * 64, source_manifest_sha256="d" * 64,
                 dataset_qualification_sha256="e" * 64, rights_receipt_sha256="f" * 64,
                 campaign_context={"case_id": controller.case_id, "locale": "en-US",
                     "campaign_ref": "manufactured-campaign", "task_id": "manufactured-task",
                     "revision_id": "manufactured-revision", "dataset_id": "manufactured-dataset",
                     "dataset_version": "1", "dataset_sha256": "a" * 64, "public_source_refs": [],
                     "currency": "USD", "business_budget_minor": 20000000,
                     "origin": "fictional_campaign_environment"})
    manifest = release(controller, sources, bound)["baseline_delivery_manifest"]
    row = {"schema_version": "anvil.marketing-world-release.v2",
           **{k: bound[k] for k in ("world_binding_id", "world_binding_sha256", "episode_id", "generation", "case_id", "case_snapshot_sha256")},
           "week": 1, "released_at": controller._clock, "window_ref": "manufactured-window",
           "evidence_refs": [], "receipt_id": str(uuid4()), "baseline_delivery_manifest": manifest}
    row["receipt_sha256"] = digest(row)
    return execution, bound, row


def test_v2_reconstruction_preserves_baseline_without_claiming_unrecorded_work():
    execution, bound, row = records()
    value = reconstruct(execution, bound, [row], [], [])
    assert value["workflow_status"] == "partial"
    manifest = value["state"]["artifacts"]["delivery_manifest"]
    assert manifest["provenance"] == "PREEXISTING_STANDALONE_DESCRIPTOR_FIXTURES"
    assert manifest["new_task3_effect"] is False
    assert value["model_performance_validated"] is False


def test_v2_reconstruction_rejects_foreign_baseline_generation():
    execution, bound, row = records()
    foreign = deepcopy(row)
    foreign["baseline_delivery_manifest"]["generation"] += 1
    with pytest.raises(ValueError, match="another actual released window"):
        reconstruct(execution, bound, [foreign], [], [])
