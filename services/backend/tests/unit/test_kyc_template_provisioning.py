"""Missing project provisioning must fail closed with an actionable diagnosis."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from anvil import praxis_golden_kyc as adapter
from anvil.golden_kyc_data import VERSION
from anvil.praxis_generic_contract import digest


def supported(monkeypatch):
    checks = {key: {"status": "passed", "evidence_sha256": "a" * 64} for key in (
        "kyc_product_routing", "all_original_rows_conserved",
        "per_application_policy_registry", "shared_task_evaluator_binding")}
    monkeypatch.setattr(adapter, "installed", lambda: {"ready": True, "evidence": {"checks": checks}})
    monkeypatch.setattr("anvil.golden_kyc_v7_export.product_template", lambda spec: True)
    monkeypatch.setattr(adapter, "source_hash", lambda: "b" * 64)
    execution = SimpleNamespace(
        catalogue_version="1.2.0", environment=SimpleNamespace(version="2"),
        graph_node_types=[],
        evaluators=[SimpleNamespace(criterion_id=key, capability=SimpleNamespace(
            id="golden-kyc-rubric-v1", version="1"), evidence_source="run_evidence")
            for key in adapter.CRITERIA],
        tools=[SimpleNamespace(id=value["id"], model_dump=lambda value=value: value)
               for value in adapter.tools()],
        rules=[SimpleNamespace(id=key, version=VERSION, content_sha256=digest(value))
               for key, value in adapter.RULES.items()],
    )
    return SimpleNamespace(execution=execution, model_dump=lambda: {})


def test_missing_product_import_is_explicit_and_does_not_provision(monkeypatch):
    spec = supported(monkeypatch)
    reader = Mock(return_value=None)
    monkeypatch.setattr(adapter, "one", reader)
    connection = Mock()
    result = adapter.conformance(connection, "project", spec)
    assert result["passed"] is False
    assert result["origin"] == "golden_project_runtime_import_required"
    assert result["requirements"] == ["AV_KYC_PROJECT_RUNTIME_IMPORT_REQUIRED"]
    assert result["required_task_mode"] == "reusable_application_workflow"
    assert reader.call_args.args[2] == ("project", "b" * 64, "reusable_application_workflow")
    connection.execute.assert_not_called()
    assert result["case_grading_performed"] is False


def test_changed_tool_contract_is_still_rejected_before_import_lookup(monkeypatch):
    spec = supported(monkeypatch)
    spec.execution.tools = spec.execution.tools[:-1]
    reader = Mock()
    monkeypatch.setattr(adapter, "one", reader)
    with pytest.raises(ValueError, match="Exact single-agent Golden tool"):
        adapter.conformance(Mock(), "project", spec)
    reader.assert_not_called()


def test_missing_installed_qualification_still_blocks_before_project_lookup(monkeypatch):
    spec = supported(monkeypatch)
    monkeypatch.setattr(adapter, "installed", lambda: {"ready": False, "missing": ["expired"]})
    reader = Mock()
    monkeypatch.setattr(adapter, "one", reader)
    result = adapter.conformance(Mock(), "project", spec)
    assert result["passed"] is False
    assert result["origin"] == "installed_golden_qualification_missing"
    reader.assert_not_called()
