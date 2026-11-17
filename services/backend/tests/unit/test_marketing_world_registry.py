"""Mocked private SQL selection; manufactured receipts are not qualification."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_marketing_world_definition import source

from anvil import golden_kyc_anvil, praxis_template_registry
from anvil.marketing_world_registry import CONTROLS, candidate, load, persist
from anvil.praxis_generic_contract import digest


class Connection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, arguments=None):
        self.sql, self.arguments = sql, arguments
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return {"allowed": False}


def setup(monkeypatch):
    monkeypatch.setattr(praxis_template_registry, "source_hash", lambda: "a" * 64)
    monkeypatch.setattr(golden_kyc_anvil, "source_hash", lambda: "b" * 64)
    monkeypatch.setenv("ANVIL_RUNTIME_IMAGE_DIGEST", "sha256:" + "c" * 64)
    body = source(monkeypatch)
    dataset = {
        "id": str(uuid4()),
        "manifest": {
            "cases": [{"id": body["case_id"], "snapshot_sha256": body["case_snapshot_sha256"]}]
        },
        "fixture_manifest_sha256": "f" * 64,
        "fixture_manifest": {"source_hashes": body["source_hashes"]},
    }
    receipt = {
        "schema_version": "anvil.marketing-private-world-qualification.v1",
        "origin": "independent_qa",
        "scope": "fictional_controlled_sources_and_simulated_world_only",
        "definition_sha256": digest(body),
        "source_sha256": "a" * 64,
        "runtime_sha256": "b" * 64,
        "runtime_image_sha256": "sha256:" + "c" * 64,
        "dataset_qualification_sha256": "e" * 64,
        "rights_receipt_sha256": body["rights_receipt_sha256"],
        "controls": {name: {"status": "passed", "evidence_sha256": "1" * 64} for name in CONTROLS},
    }
    row = {
        "value": {
            "source": {
                "id": str(uuid4()),
                "definition": body,
                "definition_sha256": digest(body),
                "source_sha256": "a" * 64,
            },
            "qualification": {"receipt": receipt, "receipt_sha256": digest(receipt)},
        }
    }
    native = {
        "runtime_sha256": "b" * 64,
        "dataset_qualification": {"receipt_sha256": "e" * 64},
        "case_assignment": {
            "case_id": body["case_id"],
            "snapshot_sha256": body["case_snapshot_sha256"],
        },
        "execution_sha256": body["execution_sha256"],
        "fixture_manifest_sha256": "f" * 64,
        "task_id": body["campaign_context"]["task_id"],
        "revision_id": body["campaign_context"]["revision_id"],
    }
    return body, dataset, row, {"config": {"marketing_native_binding": native}}


def test_candidate_does_not_create_qualification_and_pins_actual_source_inventory(monkeypatch):
    body, dataset, _, _ = setup(monkeypatch)
    prepared = candidate(body, dataset)
    assert prepared["definition_sha256"] == digest(prepared["definition"])
    assert "qualification" not in prepared
    changed = deepcopy(dataset)
    changed["fixture_manifest"]["source_hashes"] = {"other.json": "0" * 64}
    with pytest.raises(ValueError, match="complete source inventory"):
        candidate(body, changed)


def test_application_or_worker_cannot_import_world_source_without_operator_privilege():
    c = Connection([])
    with pytest.raises(PermissionError, match="privileged"):
        persist(c, "project", {})
    assert "has_table_privilege" in c.sql


def test_missing_independent_world_receipt_blocks_source_selection(monkeypatch):
    _, _, _, plan = setup(monkeypatch)
    with pytest.raises(RuntimeError, match="independently_qualified"):
        load(
            Connection([]), SimpleNamespace(job_id="job", lease_token="lease", plan_id="plan"), plan
        )


def test_exact_manufactured_receipt_selects_source_without_granting_run_or_approval(monkeypatch):
    body, _, row, plan = setup(monkeypatch)
    c = Connection([row])
    world, selected, _ = load(
        c, SimpleNamespace(job_id="job", lease_token="lease", plan_id="plan"), plan
    )
    assert world.case_id == body["case_id"]
    assert selected["definition_sha256"] == digest(body)
    assert c.arguments == ("job", "lease", "plan")
    assert not hasattr(world, "qualification_granted")


@pytest.mark.parametrize(
    "field", ["rights_receipt_sha256", "runtime_sha256", "runtime_image_sha256"]
)
def test_mismatched_rights_runtime_or_image_never_falls_back_to_candidate(monkeypatch, field):
    _, _, row, plan = setup(monkeypatch)
    receipt = row["value"]["qualification"]["receipt"]
    receipt[field] = ("sha256:" if field == "runtime_image_sha256" else "") + "0" * 64
    row["value"]["qualification"]["receipt_sha256"] = digest(receipt)
    with pytest.raises(RuntimeError, match="independently_qualified"):
        load(
            Connection([row]),
            SimpleNamespace(job_id="job", lease_token="lease", plan_id="plan"),
            plan,
        )


def test_missing_actual_control_cannot_be_replaced_with_shape_only_receipt(monkeypatch):
    _, _, row, plan = setup(monkeypatch)
    receipt = row["value"]["qualification"]["receipt"]
    del receipt["controls"]["conditional_approval_activation"]
    row["value"]["qualification"]["receipt_sha256"] = digest(receipt)
    with pytest.raises(ValueError, match="independently exercised"):
        load(
            Connection([row]),
            SimpleNamespace(job_id="job", lease_token="lease", plan_id="plan"),
            plan,
        )
