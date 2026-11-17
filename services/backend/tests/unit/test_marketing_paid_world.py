"""Public world facade controls; no actual world/source/native qualification."""

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from anvil import marketing_paid_world as world
from anvil.db import digest
from anvil.praxis_generic_contract import digest as wire_digest


def fixture(monkeypatch):
    monkeypatch.setattr(world, "monotonic", lambda: 100.0)
    execution = json.loads(
        (Path(__file__).parents[1] / "fixtures/veyra-template-execution-v3.json").read_text()
    )
    job = {key: str(uuid4()) for key in ("project_id", "actor_id", "id", "plan_id", "lease_token")}
    dataset = {"id": "manufactured-dataset", "version": "1", "sha256": "d" * 64}
    native = {
        "case_assignment": {"case_id": "GT2-R01", "snapshot_sha256": "c" * 64},
        "execution_sha256": wire_digest(execution),
        "fixture_manifest_sha256": "f" * 64,
        "dataset_qualification": {"receipt_sha256": "e" * 64},
        "task_id": "manufactured-task",
        "revision_id": "1",
        "case_context": {"caseDataset": dataset},
    }
    prepared = {
        "mode": "marketing-native",
        "native_binding": native,
        "execution": execution,
        "request_timeout_seconds": 60,
    }
    attachment = {
        "schema_version": "anvil.marketing-world-attachment.v1",
        "project_id": job["project_id"],
        "actor_id": job["actor_id"],
        "job_id": job["id"],
        "plan_id": job["plan_id"],
        "world_binding_id": str(uuid4()),
        "episode_id": str(uuid4()),
        "generation": 0,
        "world_binding_sha256": "b" * 64,
        "case_id": "GT2-R01",
        "case_snapshot_sha256": "c" * 64,
        "execution_sha256": native["execution_sha256"],
        "native_binding_sha256": wire_digest(native),
        "source_manifest_sha256": "f" * 64,
        "dataset_qualification_sha256": "e" * 64,
        "rights_receipt_sha256": "a" * 64,
        "campaign_context": {
            "case_id": "GT2-R01",
            "locale": "en-US",
            "campaign_ref": "manufactured-public-campaign",
            "task_id": native["task_id"],
            "revision_id": native["revision_id"],
            "dataset_id": dataset["id"],
            "dataset_version": dataset["version"],
            "dataset_sha256": dataset["sha256"],
            "public_source_refs": ["public-source:1"],
            "currency": "USD",
            "business_budget_minor": 20000000,
            "origin": "fictional_campaign_environment",
        },
    }
    prepared["world_attachment"] = attachment
    prepared["world_attachment_sha256"] = wire_digest(attachment)
    return job, prepared, attachment


def test_construction_is_pure_and_context_cannot_inject_private_world_rules(monkeypatch):
    job, prepared, attached = fixture(monkeypatch)
    monkeypatch.setattr(world, "_rpc", lambda *args: pytest.fail("Construction must not call API"))
    instance = world.QualifiedWorld(job, prepared, attached, absolute_deadline=200.0)
    context = instance.campaign_context
    context["public_source_refs"].append("changed")
    assert instance.campaign_context["public_source_refs"] == ["public-source:1"]
    for key in ("outcome", "controller_token", "future_windows"):
        changed = deepcopy(attached)
        changed["campaign_context"][key] = "PRIVATE-NEVER-PUBLIC"
        with pytest.raises(ValueError):
            world.QualifiedWorld(job, prepared, changed, absolute_deadline=200.0)


@pytest.mark.parametrize(
    "field",
    [
        "case_id",
        "case_snapshot_sha256",
        "execution_sha256",
        "dataset_qualification_sha256",
        "native_binding_sha256",
    ],
)
def test_attachment_cannot_change_case_source_or_configuration(monkeypatch, field):
    job, prepared, attached = fixture(monkeypatch)
    attached[field] = "GT2-R02" if field == "case_id" else "0" * 64
    with pytest.raises(ValueError, match="server-owned"):
        world.QualifiedWorld(job, prepared, attached, absolute_deadline=200.0)


def test_release_is_exact_window_scoped_and_contains_only_public_refs(monkeypatch):
    job, prepared, attached = fixture(monkeypatch)
    seen = []
    response = {
        "schema_version": "anvil.marketing-world-release.v1",
        **{
            key: attached[key]
            for key in (
                "world_binding_id",
                "world_binding_sha256",
                "episode_id",
                "generation",
                "case_id",
                "case_snapshot_sha256",
            )
        },
        "week": 1,
        "released_at": "2027-01-01T00:00:00Z",
        "window_ref": "public-window:1",
        "evidence_refs": ["public-record:1"],
        "receipt_id": str(uuid4()),
        "receipt_sha256": "a" * 64,
    }
    monkeypatch.setattr(world, "_rpc", lambda *args: seen.append(args) or response)
    instance = world.QualifiedWorld(job, prepared, attached, absolute_deadline=200.0)
    released = instance.release(1)
    assert released["week"] == 1 and released["evidence_refs"] == ["public-record:1"]
    assert set(released) == {
        "week",
        "released_at",
        "window_ref",
        "evidence_refs",
        "world_receipt_ref",
    }
    assert seen[0][2] == "release" and seen[0][3]["episode_id"] == attached["episode_id"]
    response["case_id"] = "GT2-R02"
    with pytest.raises(ValueError, match="another actual case"):
        instance.release(1)


def test_only_exact_nonagent_effect_can_cross_fixed_world_interface(monkeypatch):
    job, prepared, attached = fixture(monkeypatch)
    node = next(
        item for item in prepared["execution"]["workflow_graph"]["nodes"] if item["id"] == "task3"
    )
    inputs, artifact = (
        {"production_request": {"id": "actual-request", "version": 1}},
        {"id": "fixture-delivery", "version": 1},
    )
    response = {
        "artifact": artifact,
        "receipt": {
            "input_sha256": digest(inputs),
            "artifact_sha256": wire_digest(artifact),
            "post_state_sha256": "a" * 64,
            "world_binding_sha256": attached["world_binding_sha256"],
            "world_effect_id": str(uuid4()),
            "world_receipt_sha256": "b" * 64,
            "episode_id": attached["episode_id"],
            "generation": 0,
            "node_id": "task3",
            "week": 1,
            "visit": 1,
            "origin": "persisted_environment_effect",
            "simulated_environment": True,
        },
    }
    seen = []
    monkeypatch.setattr(world, "_rpc", lambda *args: seen.append(args) or response)
    instance = world.QualifiedWorld(job, prepared, attached, absolute_deadline=200.0)
    assert instance.effect(node, inputs, 1, 1)["artifact"] == artifact
    assert len(seen) == 1
    with pytest.raises(ValueError):
        instance.effect(node, inputs | {"foreign": {}}, 1, 1)
    agent = next(
        item
        for item in prepared["execution"]["workflow_graph"]["nodes"]
        if item["type"] == "agent_step"
    )
    with pytest.raises(ValueError):
        instance.effect(agent, {}, 1, 1)
    assert len(seen) == 1
    response["receipt"]["generation"] = 1
    with pytest.raises(ValueError, match="exact claimed graph"):
        instance.effect(node, inputs, 1, 1)


def test_deadline_cannot_be_restarted_and_attach_sends_no_caller_world_recipe(monkeypatch):
    job, prepared, attached = fixture(monkeypatch)
    seen = []
    monkeypatch.setattr(world, "_rpc", lambda *args: seen.append(args) or attached)
    instance = world.QualifiedWorld.attach(job, prepared, absolute_deadline=200.0)
    assert seen[0][2:4] == ("attach", {})
    monkeypatch.setattr(world, "monotonic", lambda: 200.0)
    with pytest.raises(TimeoutError):
        instance.release(1)
    assert len(seen) == 1


def test_world_call_rejects_extra_attach_values_and_boolean_window(monkeypatch):
    job, _, attached = fixture(monkeypatch)
    base = {
        "project_id": job["project_id"],
        "actor_id": job["actor_id"],
        "job_id": job["id"],
        "lease_token": job["lease_token"],
        "plan_id": job["plan_id"],
    }
    with pytest.raises(ValueError):
        world.WorldCall(**base, operation="attach", value={"world_factory": "caller_choice"})
    value = {
        key: attached[key]
        for key in ("world_binding_id", "world_binding_sha256", "episode_id", "generation")
    }
    with pytest.raises(ValueError):
        world.WorldCall(**base, operation="release", value=value | {"week": True})


def test_native_wire_hash_and_readonly_binding_projection_keep_producer_domains_exact(monkeypatch):
    job, prepared, attached = fixture(monkeypatch)
    native = prepared["native_binding"]
    native["manufactured_numeric_metadata"] = 1.0
    assert digest(native) != wire_digest(native)
    attached["native_binding_sha256"] = wire_digest(native)
    prepared["world_attachment_sha256"] = wire_digest(attached)
    instance = world.QualifiedWorld(job, prepared, attached, absolute_deadline=200.0)
    raw = instance.binding_projection
    assert type(raw) is bytes
    projection = json.loads(raw)
    assert projection["native_binding_sha256"] == wire_digest(native)
    assert (
        projection["rights_ref"]
        == "anvil-rights-receipt:sha256:" + attached["rights_receipt_sha256"]
    )
    assert "campaign_context" not in projection and "lease_token" not in projection
    projection["rights_ref"] = "changed"
    assert instance.binding_projection == raw
    attached["native_binding_sha256"] = digest(native)
    prepared["world_attachment_sha256"] = wire_digest(attached)
    with pytest.raises(ValueError, match="server-owned"):
        world.QualifiedWorld(job, prepared, attached, absolute_deadline=200.0)
