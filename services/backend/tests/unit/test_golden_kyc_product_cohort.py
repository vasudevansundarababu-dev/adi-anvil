"""A single authored product remains a bounded cohort, never all-product coverage."""

import pytest
from fastapi import HTTPException

from anvil import golden_kyc_paid_package as packages


def package(identifier, product):
    return {
        "id": identifier,
        "manifest": {
            "native_binding": {
                "task_mode": "reusable_application_workflow",
                "case_selector": {"field": "product", "value": product},
                "resolved_input": {"id": "input", "sha256": "a" * 64},
                "preparation_binding_id": "binding",
                "preparation_binding_sha256": "b" * 64,
                "import_id": "import",
                "import_sha256": "c" * 64,
                "runtime_sha256": "d" * 64,
                "evaluator_sha256": "e" * 64,
                "template_sha256": "f" * 64,
                "pack_id": "pack",
            }
        },
    }


def test_single_product_preserves_exact_original_assignment_and_rejects_other_cases(monkeypatch):
    originals = [{"application_id": "original-individual-1", "application_sha256": "a" * 64}]
    monkeypatch.setattr(packages, "assignments", lambda *args: originals)
    selected = package("task1", "individual")
    result = packages.task_set_assignments(None, "project", [selected])
    assert result == [originals[0] | {"package_id": "task1"}]
    with pytest.raises(HTTPException) as failed:
        packages.task_set_assignments(None, "project", [selected], ["foreign-product-1"])
    assert failed.value.status_code == 422


def test_mixed_input_and_duplicate_products_never_merge(monkeypatch):
    monkeypatch.setattr(packages, "assignments", lambda *args: [])
    for other in [package("task2", "individual"), package("task2", "adult_joint")]:
        if other["manifest"]["native_binding"]["case_selector"]["value"] == "adult_joint":
            other["manifest"]["native_binding"]["resolved_input"] = {
                "id": "other",
                "sha256": "0" * 64,
            }
        with pytest.raises(HTTPException) as failed:
            packages.task_set_assignments(None, "project", [package("task1", "individual"), other])
        assert failed.value.status_code == 409


def test_single_product_ancestry_adds_only_exact_package(monkeypatch):
    from copy import deepcopy

    from anvil import db
    from anvil.golden_kyc_binding_ancestry import verify_packages

    old = {"workflow": [], "data": [{"kind": "input", "id": "original-input"}]}
    parent = {"snapshot": old, "snapshot_sha256": db.digest(old), "task_group_id": "group"}
    item = package("task1", "individual")
    item["package_sha256"] = "1" * 64
    item["manifest"]["native_binding"]["preparation_binding_sha256"] = parent["snapshot_sha256"]
    ref = {"kind": "package", "id": "task1", "sha256": item["package_sha256"], "target": "task"}
    new = deepcopy(old)
    new["workflow"] = [ref]
    current = {"snapshot": new, "snapshot_sha256": db.digest(new), "task_group_id": "group"}
    monkeypatch.setattr(db, "one", lambda *a: parent)
    assert (
        verify_packages(None, "project", current, [item])["package_reference_additions_only"]
        is True
    )
    new["data"][0]["id"] = "replacement-input"
    current["snapshot_sha256"] = db.digest(new)
    with pytest.raises(ValueError, match="binding changed"):
        verify_packages(None, "project", current, [item])


@pytest.mark.parametrize("count", [1, 2, 3, 4])
def test_each_selected_product_keeps_its_original_assignment(count, monkeypatch):
    products = ["individual", "adult_joint", "teen_joint", "custodial"][:count]
    monkeypatch.setattr(
        packages,
        "assignments",
        lambda c, p, b: [
            {"application_id": b["case_selector"]["value"], "application_sha256": "a" * 64}
        ],
    )
    items = [package(str(index), product) for index, product in enumerate(products)]
    rows = packages.task_set_assignments(None, "project", items)
    assert {row["application_id"] for row in rows} == set(products)
    assert len(rows) == count and len({row["package_id"] for row in rows}) == count


def test_original_unassigned_foreign_rows_are_not_filtered_out():
    from anvil.golden_kyc_product_context import _members

    original = {
        "application_id": "individual-original",
        "status": "assigned_pending_policy_and_runtime_qualification",
        "task_id": "task",
        "revision_id": "revision",
        "product": "individual",
    }
    body = {"input_count": 1, "rows": [original]}
    assert _members(body, "task", "revision", "individual") == [original]
    body["rows"].append(
        {
            "application_id": "foreign-original",
            "status": "workflow_missing",
            "task_id": None,
            "revision_id": None,
            "product": "adult_joint",
        }
    )
    body["input_count"] = 2
    with pytest.raises(ValueError, match="original application population"):
        _members(body, "task", "revision", "individual")
    assert len(body["rows"]) == 2
