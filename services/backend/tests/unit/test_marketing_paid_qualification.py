"""Manufactured independent-proof shapes only; no installed source qualification."""

from copy import deepcopy

import pytest

from anvil import marketing_paid_qualification as qualification
from anvil.marketing_paid_budget import claim
from anvil.marketing_paid_session import require_frozen


def proof():
    return {
        "schema_version": "anvil.marketing-runtime-component-qualification.v1",
        "origin": "independent_qa",
        "scope": "technical_marketing_runtime_only",
        "spending_authority": False,
        "workflow_graph_sha256": "a" * 64,
        "role_profiles_sha256": "b" * 64,
        "checks": {
            name: {"status": "passed", "evidence_sha256": "c" * 64} for name in qualification.CHECKS
        },
    }


def test_generic_or_uninstalled_component_proof_does_not_admit_marketing(monkeypatch):
    monkeypatch.setattr(
        qualification, "components", lambda: {"ready": False, "missing": ["actual_component_gap"]}
    )
    result = qualification.installed("a" * 64)
    assert not result["ready"] and "actual_component_gap" in result["missing"]
    monkeypatch.setattr(qualification, "components", lambda: {"ready": True, "evidence": {}})
    assert not qualification.installed("a" * 64)["ready"]


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "graph",
        "profiles",
        "origin",
        "spending",
        "scope",
        "missing_control",
        "invalid_digest",
    ],
)
def test_exact_marketing_proof_scope_and_controls_are_required(monkeypatch, fault):
    value = deepcopy(proof())
    if fault == "graph":
        value["workflow_graph_sha256"] = "d" * 64
    elif fault == "profiles":
        value["role_profiles_sha256"] = "d" * 64
    elif fault == "origin":
        value["origin"] = "candidate_claim"
    elif fault == "spending":
        value["spending_authority"] = True
    elif fault == "scope":
        value["scope"] = "generic_component_only"
    elif fault == "missing_control":
        value["checks"].pop("unknown_no_replay")
    elif fault == "invalid_digest":
        value["checks"]["role_openenv_mcp"]["evidence_sha256"] = "placeholder"
    monkeypatch.setenv("ANVIL_RUNTIME_ROLE_PROFILES_SHA256", "b" * 64)
    monkeypatch.setattr(
        qualification,
        "components",
        lambda: {"ready": True, "evidence": {"marketing_runtime": value}},
    )
    result = qualification.installed("a" * 64)
    assert result["ready"] is (fault == "none")
    if fault == "none":
        assert result["spending_authority"] is False


def test_unmarked_plan_and_missing_case_cannot_claim_sql_or_substitute_context(monkeypatch):
    monkeypatch.setattr(
        "anvil.marketing_paid_budget.one", lambda *args: pytest.fail("No paid SQL claim allowed")
    )
    assert claim(None, {}, {"config": {}}, {}, {}, None) is False
    with pytest.raises(RuntimeError, match="assignment_required"):
        require_frozen(None, "project", {}, case_id=None)
