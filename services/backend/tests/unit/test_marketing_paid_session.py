"""Manufactured rows/qualification stubs; actual published execution structure."""

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from anvil.db import digest
from anvil.marketing_paid_package import assignments
from anvil.marketing_paid_session import require_frozen, task_context
from anvil.praxis_marketing_contract import CampaignDataset


def fixture(monkeypatch):
    execution = json.loads(
        (Path(__file__).parents[1] / "fixtures/veyra-template-execution-v3.json").read_text()
    )
    actor = {"sections": {"S1": {"campaign": "Manufactured public task"}}}
    spec = {"execution": execution}
    dataset = CampaignDataset(
        schema_version="anvil.campaign-case-dataset.v1",
        id="software-US-pair",
        version="1",
        case_count=2,
        cases=[
            {"id": key, "snapshot_sha256": digest(key), "locale": "en-US"}
            for key in ("GT2-R01", "GT2-R02")
        ],
    )
    template_q = {"id": str(uuid4()), "receipt_sha256": "a" * 64}
    dataset_q = {"id": str(uuid4()), "receipt_sha256": "b" * 64}
    context = {
        "schema_version": "anvil.campaign-context.v1",
        "task_id": "software-campaign",
        "revision_id": "1",
        "caseDataset": dataset.reference().model_dump(),
        "caseSelector": {"field": "dataset", "value": "all", "case_count": 2},
        "environment": execution["environment"],
        "workflow_graph_sha256": execution["workflow_graph_sha256"],
        "evaluator_bindings_sha256": digest(execution["evaluators"]),
    }
    dataset_import = {
        "id": str(uuid4()),
        "manifest_sha256": dataset.reference().sha256,
        "fixture_manifest_sha256": "c" * 64,
    }
    binding = {
        "task_mode": "reusable_campaign_workflow",
        "source_sha256": "d" * 64,
        "actor_sha256": digest(actor),
        "template_sha256": digest(spec),
        "qualification_id": template_q["id"],
        "qualification_sha256": template_q["receipt_sha256"],
        "case_context": context,
        "case_context_sha256": digest(context),
        "case_import_id": dataset_import["id"],
        "case_import_sha256": dataset_import["manifest_sha256"],
        "execution_sha256": digest(execution),
        "environment": execution["environment"],
        "evaluator_bindings": execution["evaluators"],
    }
    resolved = {
        "actor": actor,
        "actor_sha256": digest(actor),
        "binding": binding,
        "binding_sha256": digest(binding),
        "spec": spec,
        "spec_sha256": digest(spec),
        "template_key": "software-template",
        "template_version": 1,
        "task_key": "software-campaign",
        "revision": "1",
        "private_reference_sha256": "e" * 64,
    }
    task = {
        "task_id": "software-campaign",
        "revision_id": "1",
        "payload_sha256": "e" * 64,
        "source": {"template": {"profile_id": "veyra-hush-one-launch-v1", "sha256": digest(spec)}},
    }
    content = {
        "tasks": [task],
        "source_origin": {"kind": "praxis_authored_batch"},
        "case_dataset": dataset.reference().model_dump(),
    }
    imported = {"id": str(uuid4()), "content": content, "content_sha256": digest(content)}
    template = {"qualified": True, "qualification": template_q}
    campaign = {
        "qualified": True,
        "qualification": dataset_q,
        "manifest": dataset.model_dump(),
        "import": dataset_import,
    }
    monkeypatch.setattr("anvil.marketing_paid_session.one", lambda *args: resolved)
    monkeypatch.setattr("anvil.project_bindings.group", lambda *args: imported)
    monkeypatch.setattr("anvil.praxis_template_registry.source_hash", lambda: "d" * 64)
    monkeypatch.setattr("anvil.golden_kyc_anvil.source_hash", lambda: "f" * 64)
    monkeypatch.setattr("anvil.harbor_agents.code_digest", lambda: "0" * 64)
    monkeypatch.setattr("anvil.praxis_template_registry.lookup", lambda *args: template)
    monkeypatch.setattr("anvil.praxis_campaign_registry.lookup", lambda *args: campaign)
    return {"resolved": resolved, "imported": imported, "template": template, "campaign": campaign}


def test_exact_binding_checks_return_only_actor_and_frozen_source_references(monkeypatch):
    data = fixture(monkeypatch)
    result = task_context(None, "project", "resolved", data["imported"]["id"], case_id="GT2-R01")
    native = result["native_binding"]
    assert result["actor"] == data["resolved"]["actor"]
    assert native["task_mode"] == "reusable_campaign_workflow" and len(native["cases"]) == 2
    assert "private_reference" not in result["actor"] and "fixture_manifest" not in native
    assert result["run_authority"] == "not_granted" and not result["private_reference_to_actor"]
    assert require_frozen(None, "project", native, case_id="GT2-R01") == result
    assigned = native | {
        "case_assignment": {
            "case_id": "GT2-R01",
            "snapshot_sha256": digest("GT2-R01"),
            "locale": "en-US",
        }
    }
    assert require_frozen(None, "project", assigned, case_id="GT2-R01") == result
    assigned["case_assignment"]["snapshot_sha256"] = "9" * 64
    with pytest.raises(RuntimeError, match="assignment"):
        require_frozen(None, "project", assigned, case_id="GT2-R01")


@pytest.mark.parametrize(
    "fault",
    [
        "actor",
        "binding",
        "spec",
        "task_revision",
        "import_sha",
        "template_revoked",
        "dataset_revoked",
        "dataset_import",
        "case_membership",
    ],
)
def test_source_and_qualification_drift_never_substitutes_a_new_context(monkeypatch, fault):
    data = fixture(monkeypatch)
    row = data["resolved"]
    if fault in {"actor", "binding", "spec"}:
        row[fault]["unrelated_change"] = "invalid source mutation"
    elif fault == "task_revision":
        data["imported"]["content"]["tasks"][0]["revision_id"] = "2"
        data["imported"]["content_sha256"] = digest(data["imported"]["content"])
    elif fault == "import_sha":
        data["imported"]["content_sha256"] = "9" * 64
    elif fault == "template_revoked":
        data["template"]["qualified"] = False
    elif fault == "dataset_revoked":
        data["campaign"]["qualified"] = False
    elif fault == "dataset_import":
        data["campaign"]["import"]["manifest_sha256"] = "9" * 64
    else:
        with pytest.raises(RuntimeError, match="outside"):
            task_context(
                None, "project", "resolved", data["imported"]["id"], case_id="foreign-case"
            )
        return
    with pytest.raises(RuntimeError):
        task_context(None, "project", "resolved", data["imported"]["id"], case_id="GT2-R01")


def test_receipt_or_runtime_change_requires_new_native_package(monkeypatch):
    data = fixture(monkeypatch)
    native = task_context(None, "project", "resolved", data["imported"]["id"])["native_binding"]
    data["campaign"]["qualification"]["receipt_sha256"] = "9" * 64
    with pytest.raises(RuntimeError, match="frozen"):
        require_frozen(None, "project", native, case_id="GT2-R01")
    with pytest.raises(RuntimeError, match="INPUT_ADAPTER"):
        task_context(
            None,
            "project",
            "resolved",
            data["imported"]["id"],
            execution_data={"id": "not-default"},
        )


def test_campaign_assignment_always_preserves_whole_dataset(monkeypatch):
    data = fixture(monkeypatch)
    native = task_context(None, "project", "resolved", data["imported"]["id"])["native_binding"]
    package = {
        "id": "package",
        "manifest": {"binding": "marketing-task2-five-role-v1", "native_binding": native},
    }
    assert len(assignments(package)) == 2
    with pytest.raises(ValueError, match="complete"):
        assignments(package, case_ids=["GT2-R01"])
    changed = deepcopy(package)
    changed["manifest"]["native_binding"]["cases"].append(native["cases"][0])
    with pytest.raises(ValueError, match="complete"):
        assignments(changed)
