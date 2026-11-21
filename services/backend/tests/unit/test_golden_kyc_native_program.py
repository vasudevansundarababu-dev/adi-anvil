from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from anvil import evaluator_configurations as configurations
from anvil import golden_kyc_native_program as native
from anvil.db import digest
from anvil.golden_kyc_evaluators import CRITERIA, evaluate


@pytest.mark.parametrize("criterion", CRITERIA)
def test_real_scoring_controls_bind_all_criteria_and_preserve_reviews(criterion):
    program = native.program(criterion).model_dump(mode="json")
    evidence = native.controls(program)
    assert [case["actual"] for case in evidence["cases"][:5]] == [5, 2, 0, None, None]
    assert evidence["cases"][-1]["actual"] == (None if criterion.startswith("state_") else 5)
    assert evidence["provider_calls"] == 0
    assert evidence["case_review_granted"] is evidence["legal_review_granted"] is False
    assert native.qualified(program, {"evidence": evidence, "evidence_sha256": digest(evidence)})
    wrong = deepcopy(evidence)
    wrong["normalizer_source_sha256"] = "a" * 64
    assert not native.qualified(program, {"evidence": wrong, "evidence_sha256": digest(wrong)})


def test_program_rejects_actor_facts_unsupported_criteria_and_stale_source():
    value = native.program("profile").model_dump(mode="json")
    with pytest.raises(ValidationError):
        native.Program.model_validate(value | {"supported": True})
    with pytest.raises(ValidationError):
        native.Program.model_validate(value | {"criterion": "invented"})
    with pytest.raises(ValueError, match="Current sealed"):
        native.checked(value | {"normalizer_source_sha256": "a" * 64})
    for adapter, rule in (("zen", None), ("builtin", {"kind": "equals", "field": "supported", "value": True})):
        with pytest.raises(ValidationError):
            configurations.Configure(name="KYC", adapter=adapter, rule=rule, native_kyc=value)
    configured = configurations.Configure(name="KYC", adapter="builtin", native_kyc=value)
    assert configured.native_kyc.criterion == "profile"


def test_boolean_examples_cannot_qualify_sealed_grading(monkeypatch):
    monkeypatch.setattr(configurations, "get", lambda *a, **kw: {
        "configuration": {"native_kyc": native.program("profile").model_dump(mode="json")}})
    with pytest.raises(HTTPException) as error:
        configurations.test(None, uuid4(), uuid4(), uuid4(), None)
    assert error.value.status_code == 409


def test_missing_private_intended_decision_stays_unknown():
    result = evaluate({"final": {}}, {"independent_expectation_review": "approved"}, {})
    assert result["decision_correctness"] is None
    assert result["overall_result"] == "not_evaluated"
    assert result["rubric_score"] == {"earned_points": 0, "maximum_points": 100, "unscored_points": 100}


def sealed_trace():
    from anvil.golden_kyc_data import VERSION

    parties = [{"id": f"synthetic-p{n}", "role": "adult_owner", "birth_date": "1990-01-01"}
               for n in (1, 2)]
    snapshot = {"id": "synthetic-case", "parties": parties, "product": "adult_joint",
                "requested_product": "adult_joint", "assessment_date": "2026-11-12"}
    documents = [{"id": f"agreement-{n}", "party_id": p["id"], "kind": "agreement"}
                 for n, p in enumerate(parties)]
    operations = {}
    for p in parties:
        for kind in ("identity", "screening", "authority"):
            identifier = f"op-{len(operations) + 1}"
            operations[identifier] = {"id": identifier, "kind": kind,
                "result": {"party_id": p["id"], "input_revision": 1,
                           "verification_status": "corroborated"}}
    reads = [snapshot["id"], VERSION, *operations, *(d["id"] for d in documents)]
    final = {"decision": "ready_for_approval", "assessed_revision": 1, "account_type": "adult_joint",
             "reason": "Synthetic supported outcome", "outstanding_actions": [], "evidence_ids": reads[:],
             "party_assessments": [{"party_id": p["id"], "role": p["role"], "status": "verified",
                 "verification_evidence_ids": [op["id"] for op in operations.values()
                    if op["kind"] == "identity" and op["result"]["party_id"] == p["id"]]} for p in parties]}
    state = {"application": snapshot | {"documents": documents}, "revision": 1,
             "operations": operations, "reads": reads, "final": final,
             "requests": {}, "specialists": {}, "findings": {}, "idempotency": dict.fromkeys(operations)}
    return snapshot, state


def test_actual_sealed_normalizer_scores_supported_evidence_but_leaves_state_unknown():
    from anvil.golden_kyc_grader import normalize

    snapshot, state = sealed_trace()
    checks, trace, critical = normalize(state, snapshot, [])
    assert not critical and trace["identity_established"] and trace["screening_established"]
    assert all(checks[k] is True for k in CRITERIA if not k.startswith("state_"))
    expectation = {"independent_expectation_review": "approved", "legal_qualification": "pending",
                   "intended_decision": "ready_for_approval"}
    result = evaluate(state, expectation, checks, critical)
    assert result["rubric_score"] == {"earned_points": 80, "maximum_points": 100, "unscored_points": 20}
    assert result["overall_result"] == "not_evaluated"
    state["final"]["evidence_ids"].remove(snapshot["id"])
    checks, _, critical = normalize(state, snapshot, [])
    assert evaluate(state, expectation, checks, critical)["checks"]["profile"] == 2


@pytest.mark.parametrize("mutation", ["wrong_party", "stale", "missing", "unread"])
def test_actual_normalizer_rejects_unsupported_clearance(mutation):
    from anvil.golden_kyc_grader import normalize

    snapshot, state = sealed_trace()
    if mutation == "wrong_party":
        state["operations"]["op-1"]["result"]["party_id"] = "foreign-person"
    elif mutation == "stale":
        state["operations"]["op-1"]["result"]["input_revision"] = 0
    elif mutation == "missing":
        del state["operations"]["op-1"]
    else:
        state["reads"].remove("op-1")
    checks, _, critical = normalize(state, snapshot, [])
    assert checks["identification_verification"] is False
    assert checks["mandatory_conditions"] is False
    assert "unsupported_mandatory_clearance" in critical
    result = evaluate(state, {"independent_expectation_review": "pending"}, checks, critical)
    assert result["overall_result"] == "critical_fail"
    assert result["rubric_score"]["unscored_points"] == 100


def selection_fixture(monkeypatch):
    project, group, binding, resolved = [uuid4() for _ in range(4)]
    identity = {"task_id": "task", "task_version": "revision", "payload_sha256": "b" * 64}
    configs, refs = {}, []
    for criterion in CRITERIA:
        identifier = str(uuid4())
        configuration = {"native_kyc": native.program(criterion).model_dump(mode="json")}
        sha = digest({"adapter": "builtin", "adapter_version": configurations.ADAPTER_VERSION,
                      "configuration": configuration})
        configs[identifier] = {"id": identifier, "project_id": project, "status": "ready",
            "adapter": "builtin", "adapter_version": configurations.ADAPTER_VERSION,
            "configuration": configuration, "configuration_sha256": sha,
            "validation": {"id": uuid4(), "evidence_sha256": "c" * 64}}
        refs.append({"kind": "evaluator", "id": identifier, "sha256": sha,
                     "target": "criterion:" + digest(identity | {"criterion_id": criterion})})
    snapshot = {"rubric": refs}
    sha = digest(snapshot)
    frozen = {"id": binding, "task_group_id": group, "snapshot_sha256": sha}
    def one(c, sql, args):
        if "workspace_execution_groups" in sql:
            return {"snapshot": {"preparation": {"project_binding": frozen}}}
        if "project_binding_versions" in sql:
            assert args == (project, binding, group)
            return {"snapshot": snapshot, "snapshot_sha256": sha}
        if "praxis_resolved_tasks" in sql:
            return {"task_key": "task", "revision": "revision", "private_reference_sha256": "b" * 64}
        raise AssertionError(sql)
    monkeypatch.setattr(native, "one", one)
    monkeypatch.setattr(configurations, "get", lambda c, identifier: configs[identifier])
    return project, {"group_id": group, "resolved_task_id": resolved}, configs, refs


def test_exact_saved_configurations_produce_private_provenance(monkeypatch):
    project, paid, configs, refs = selection_fixture(monkeypatch)
    selected = native.selected(None, project, paid)
    assert len(selected) == 20
    result = {"checks": dict.fromkeys(CRITERIA, None)}
    records = native.receipts(selected, result, {"snapshot": 1}, {"state": 2}, [])
    assert len(records) == 20 and all(r["status"] == "unscored" for r in records)
    assert all(r["configuration_sha256"] in {v["sha256"] for v in refs} for r in records)
    assert all("expectation" not in str(r) for r in records)


@pytest.mark.parametrize("change", ["foreign_project", "wrong_criterion", "revoked", "generic", "hash", "missing", "duplicate"])
def test_selection_rejects_changed_or_generic_configuration(monkeypatch, change):
    project, paid, configs, refs = selection_fixture(monkeypatch)
    row = configs[refs[0]["id"]]
    if change == "foreign_project":
        row["project_id"] = uuid4()
    if change == "wrong_criterion":
        row["configuration"]["native_kyc"]["criterion"] = "profile"
    if change == "revoked":
        row["status"] = "revoked"
    if change == "generic":
        row["configuration"] = {"rule": {"kind": "equals", "field": "supported", "value": True}}
    if change == "hash":
        refs[0]["sha256"] = "d" * 64
    if change == "missing":
        refs.pop(0)
    if change == "duplicate":
        refs.append(deepcopy(refs[0]))
    with pytest.raises(ValueError):
        native.selected(None, project, paid)
