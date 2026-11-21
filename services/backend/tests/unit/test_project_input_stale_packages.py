"""A historical frozen package stays blocked without breaking Project listing."""

import pytest
from fastapi import HTTPException

from anvil import golden_kyc_paid_package, project_inputs
from anvil.golden_kyc_resolved_store import StaleProductBinding


@pytest.fixture
def selection(monkeypatch):
    monkeypatch.setenv("ANVIL_PROJECT_INPUTS_ENABLED", "true")
    imported = {"content": {"tasks": [{"task_id": "public-task"}]}}
    monkeypatch.setattr(project_inputs, "frozen", lambda *args: {"input_id": None})
    monkeypatch.setattr(project_inputs, "execution_overlay", lambda *args: {
        "family": "kyc", "cases": [{"id": "synthetic-case", "snapshot_sha256": "a" * 64}],
    })
    monkeypatch.setattr(project_inputs, "one", lambda *args: {
        "package_sha256": "b" * 64,
        "manifest": {"task_id": "public-task", "native_binding": {"task_mode": "reusable_application_workflow"}},
    })
    return lambda: project_inputs.selection_gaps(None, "synthetic-project", imported, {}, [
        {"kind": "package", "id": "synthetic-package", "sha256": "b" * 64},
    ])


def test_stale_input_or_runtime_blocks_instead_of_crashing(selection, monkeypatch):
    def stale(*args):
        raise StaleProductBinding("Exact product task/runtime input changed")
    monkeypatch.setattr(golden_kyc_paid_package, "task_set_assignments", stale)
    assert selection() == [{"section": "data", "code": "AV_INPUT_EXECUTION_BINDING_STALE", "owner": "anvil"}]


def test_current_exact_assignment_still_required(selection, monkeypatch):
    monkeypatch.setattr(golden_kyc_paid_package, "task_set_assignments", lambda *args: [
        {"application_id": "synthetic-case", "application_sha256": "c" * 64},
    ])
    assert selection()[0]["code"] == "AV_INPUT_CASE_ASSIGNMENT_MISMATCH"


def test_access_denial_is_not_downgraded_to_readiness_gap(selection, monkeypatch):
    def denied(*args):
        raise HTTPException(403, "Denied")
    monkeypatch.setattr(golden_kyc_paid_package, "task_set_assignments", denied)
    with pytest.raises(HTTPException) as result:
        selection()
    assert result.value.status_code == 403


def test_database_or_operator_failure_is_not_hidden(selection, monkeypatch):
    def unavailable(*args):
        raise RuntimeError("Database unavailable")
    monkeypatch.setattr(golden_kyc_paid_package, "task_set_assignments", unavailable)
    with pytest.raises(RuntimeError, match="Database unavailable"):
        selection()


def test_unclassified_integrity_failure_is_not_hidden(selection, monkeypatch):
    def corrupted(*args):
        raise ValueError("Stored original input binding integrity changed")
    monkeypatch.setattr(golden_kyc_paid_package, "task_set_assignments", corrupted)
    with pytest.raises(ValueError, match="integrity changed"):
        selection()


def test_original_policy_scope_still_rejects_stale_template(monkeypatch):
    from uuid import uuid4

    from anvil import golden_kyc_resolved_store as store
    from anvil.praxis_generic_contract import canonical, digest

    project, input_id, binding_id = uuid4(), uuid4(), uuid4()
    snapshot = {"source_sha256": "c" * 64}
    body = {
        "scope": {"project_id": str(project), "project_binding_id": str(binding_id),
                  "project_binding_sha256": digest(snapshot)},
        "tasks": [{"task_id": "task", "revision_id": "revision",
                   "template": {"id": str(uuid4()), "version": 8, "sha256": "d" * 64},
                   "template_qualification_receipt_sha256": "e" * 64}],
    }
    raw = canonical(body)
    import hashlib
    record = {"body_canonical": raw.decode(), "content_sha256": hashlib.sha256(raw).hexdigest(),
              "snapshot": snapshot, "snapshot_sha256": digest(snapshot), "binding_id": binding_id}

    class Connection:
        def execute(self, *args):
            return self
        def fetchone(self):
            return record

    monkeypatch.setattr(store, "lookup", lambda *args: None)
    with pytest.raises(StaleProductBinding, match="current exact template"):
        store.policy_scope(Connection(), project, input_id, "task", "revision")


@pytest.mark.parametrize("drift", ["runtime_source", "runtime_image", "qualification", "payload", "product", "task_mode"])
def test_actual_product_context_distinguishes_refresh_from_identity_failure(monkeypatch, drift):
    import hashlib
    from types import SimpleNamespace
    from uuid import uuid4

    from anvil import golden_component_qualification, golden_kyc_anvil
    from anvil import golden_kyc_product_context as context
    from anvil import golden_kyc_resolved_store as store
    from anvil.praxis_generic_contract import canonical

    project, input_id, resolution_id = uuid4(), uuid4(), uuid4()
    raw = canonical({"schema_version": "anvil.private-kyc-resolved-input.v1"})
    fingerprint = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(context, "one", lambda *args: {
        "content_sha256": fingerprint, "resolution_id": resolution_id, "body_canonical": raw.decode(),
    })
    scope = SimpleNamespace(payload_sha256="a" * 64, runtime_source_sha256="b" * 64,
                            runtime_image_sha256="c" * 64, workflow_product="individual")
    if drift == "runtime_source":
        scope.runtime_source_sha256 = "d" * 64
    if drift == "runtime_image":
        scope.runtime_image_sha256 = "d" * 64
    if drift == "payload":
        scope.payload_sha256 = "d" * 64
    if drift == "product":
        scope.workflow_product = "custodial"
    monkeypatch.setattr(store, "policy_scope", lambda *args: scope)
    monkeypatch.setattr(golden_kyc_anvil, "source_hash", lambda: "b" * 64)
    monkeypatch.setattr(golden_component_qualification, "installed", lambda: {
        "ready": drift != "qualification", "evidence": {"runtime_image_sha256": "c" * 64},
    })
    resolved = {"resolution_id": resolution_id, "task_key": "task", "revision": "revision",
                "private_reference_sha256": "a" * 64,
                "binding": {"case_selector": {"value": "individual"},
                            "task_mode": "wrong-mode" if drift == "task_mode" else "reusable_application_workflow"}}
    with pytest.raises(ValueError) as failure:
        context.load(None, project, resolved, {"id": str(input_id), "sha256": fingerprint})
    assert isinstance(failure.value, StaleProductBinding) == (drift in {"runtime_source", "runtime_image", "qualification"})
