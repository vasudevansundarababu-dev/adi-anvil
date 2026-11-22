"""Tampering/expiry controls for the technical-only method publication packet.

All review records and subjects here are manufactured unit fixtures. They do
not qualify QA, create owner decisions or run an external model.
"""

import hashlib
import importlib.util
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from anvil.db import digest
from anvil.governed_ai_catalogue import proof_valid
from infra.gcp import task_method_qualification as operator


@pytest.fixture
def packets(monkeypatch):
    from anvil.golden_kyc_source import source_hash

    assert callable(source_hash)
    monkeypatch.setattr("anvil.golden_kyc_source.source_hash", lambda: "a" * 64)
    path = Path(__file__).resolve().parents[2] / "runtime-checks/kyc_method_controls.py"
    spec = importlib.util.spec_from_file_location("method_fixture_controls", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    mechanics = module.observe()  # Actual normalizer and scoring arithmetic.
    mechanics["operator_sha256"] = operator.MECHANICS_OPERATOR
    now = datetime.now(timezone.utc)
    current = {"runtime_source_sha256": "a" * 64, "runtime_image_sha256": "b" * 64,
               "broker_source_sha256": "c" * 64, "release_sha256": "d" * 64,
               "method": mechanics["method"], "candidate_sha256": mechanics["method_sha256"],
               "component_receipt_sha256": "e" * 64,
               "component_expires_at": (now + timedelta(hours=2)).isoformat()}
    raw = json.dumps(mechanics, sort_keys=True).encode()
    mechanics_review = {"schema_version": "anvil.independent-kyc-method-mechanics-review.v1",
                        "origin": "independent_agent_read_only_review",
                        "status": "passed_software_observations_only",
                        "scope": "manufactured_method_and_diagnostic_mechanics_only",
                        "findings": [], "qualification_granted": False, "spending_authority": False,
                        "issued_at": (now - timedelta(minutes=1)).isoformat(),
                        "packet_files": {"positive.stdout": hashlib.sha256(raw).hexdigest()},
                        "cases": {name: {"terminal": True, "exit": code,
                                          "image": "manufactured/fixture@sha256:" + "b" * 64}
                                  for name, code in (("positive", 0), ("credential-negative", 1))}}
    measured = operator.reviewed_mechanics(raw, mechanics_review, current, now=now)
    project, group, resolved = (uuid4() for _ in range(3))
    task, revision = str(uuid4()), str(uuid4())
    public = {"id": str(group), "project_id": str(project), "source_sha256": "f" * 64,
              "tasks": [{"task_id": task, "task_version": revision, "payload_sha256": "1" * 64,
                         "workflow_steps": [{"index": 0, "action": "Manufactured public task", "tool": None,
                                             "failureBehaviour": None}], "workflow_declared": False}],
              "database_identity": {"database": "manufactured-unit-only", "database_oid": "1", "system_identifier": "2"}}
    witness = {"schema_version": "anvil.task-method-foreign-witness.v1",
               "origin": "independent_qa", "database_identity": public["database_identity"],
               "own_project_id": str(project), "own_group_id": str(group), "own_source_sha256": "f" * 64,
               "known_foreign_group_exists": True, "owner_observation_sha256": "2" * 64,
               "foreign_project_id": str(uuid4()), "foreign_group_id": str(uuid4()),
               "issued_at": (now - timedelta(minutes=1)).isoformat(),
               "expires_at": (now + timedelta(hours=1)).isoformat()}
    owner = {k: witness[k] for k in ("database_identity", "own_project_id", "own_group_id",
             "own_source_sha256", "foreign_project_id", "foreign_group_id", "known_foreign_group_exists")}
    owner |= {"schema_version": "anvil.task-method-owner-observation.v1",
              "origin": "actual_read_only_database_metadata", "foreign_source_sha256": "3" * 64,
              "observer": {"login": "manufactured-unit-owner", "database_owner": True, "superuser": False},
              "private_content_read": False, "qualification_granted": False, "provider_calls": 0,
              "observed_at": (now - timedelta(minutes=2)).isoformat()}
    owner_raw = operator.canonical(owner)
    witness["owner_observation_sha256"] = hashlib.sha256(owner_raw).hexdigest()
    bindings = [{"scope": {"project_id": str(project), "task_id": task, "revision_id": revision,
                            "source_sha256": "f" * 64, "resolved_input_id": str(resolved),
                            "runtime_source_sha256": "a" * 64, "runtime_image_sha256": "b" * 64},
                 "component_evidence_sha256": "e" * 64, "provider_calls": 0, "private_expectations_read": False}]
    controls = {"positive": {"actual_tasks": 1, "binding_observations_sha256": digest(bindings)},
                "negative": {"original_suite_rejected": True, "changed_source_rejected": True,
                             "origin": "actual_compatibility_and_copied_source_guard"},
                "missing": {"missing_group_id": str(uuid4()), "actual_query_returned_none": True},
                "project_isolation": {"known_foreign_group_hidden": True, "forged_context_rejected": True,
                                      "database_identity": public["database_identity"]}}
    observed = {"schema_version": "anvil.task-method-observation.v1", "status": "observed_not_qualified",
                "project_id": str(project), "task_group_id": str(group), "source_sha256": "f" * 64,
                "observed_at": (now - timedelta(seconds=10)).isoformat(), "identity": current,
                "public_group_sha256": digest(public), "mechanics": measured, "bindings": bindings,
                "resolved_input_id": str(resolved), "operator_source_sha256": hashlib.sha256(Path(operator.__file__).read_bytes()).hexdigest(),
                "foreign_witness_sha256": digest(witness), "controls": controls,
                "provider_calls": 0, "private_expectations_read": False, "human_review_approval": False,
                "spending_authority": False, "model_performance": False}
    review = {"schema_version": "anvil.independent-task-method-review.v1",
              "origin": "independent_agent_read_only_review", "scope": "task_method_technical_only",
              "status": "passed", "findings": [], "observation_sha256": digest(observed),
              "identity_sha256": digest(current), "control_sha256s": {k: digest(v) for k, v in controls.items()},
              "foreign_witness_sha256": digest(witness), "owner_observation_sha256": witness["owner_observation_sha256"],
              "human_review_approval": False, "spending_authority": False, "model_performance": False,
              "issued_at": now.isoformat(), "expires_at": (now + timedelta(minutes=30)).isoformat()}
    return raw, mechanics_review, current, public, measured, witness, observed, review, now, owner_raw


def build(packets):
    _, _, current, public, mechanics, witness, observed, review, now, owner_raw = packets
    return operator.receipt(observed, review, digest(review), current, public, mechanics, witness,
                            owner_raw, now=now, login="manufactured-unit-qualifier")


@pytest.mark.parametrize("field,value", [
    ("origin", "untrusted"), ("database_identity", {}), ("own_source_sha256", "0" * 64),
    ("known_foreign_group_exists", False), ("owner_observation_sha256", "missing"),
])
def test_publication_rechecks_witness_even_when_hashes_are_resubmitted(packets, field, value):
    changed = list(deepcopy(packets))
    changed[5][field] = value
    changed[6]["foreign_witness_sha256"] = digest(changed[5])
    changed[7]["foreign_witness_sha256"] = digest(changed[5])
    changed[7]["owner_observation_sha256"] = changed[5]["owner_observation_sha256"]
    changed[7]["observation_sha256"] = digest(changed[6])
    with pytest.raises(ValueError, match="witness"):
        build(changed)


def test_original_owner_bytes_cannot_be_replaced_by_a_matching_hash_claim(packets):
    changed = list(deepcopy(packets))
    changed[9] = b'{}'
    with pytest.raises(ValueError, match="Original owner observation bytes"):
        build(changed)


def test_original_arithmetic_retains_unscored_and_critical_boundaries(packets):
    raw, review, current, _, measured, *_ = packets
    result = operator.reviewed_mechanics(raw, review, current, now=packets[8])
    assert result == measured and len(result["case_result_sha256s"]) == 6
    assert result["scope"] == "synthetic_method_mechanics_not_human_expectation_review"


def test_method_packet_matches_actual_consumer_shape_without_owner_or_run_authority(packets, monkeypatch):
    body = build(packets)
    current = packets[2]
    row = {key: body[key] for key in ("target", "candidate_id", "candidate_sha256")}
    row |= {"evidence": body, "evidence_sha256": digest(body)}
    monkeypatch.setenv("ANVIL_RUNTIME_IMAGE_DIGEST", current["runtime_image_sha256"])
    assert proof_valid(row, {"content_sha256": body["source_sha256"]},
                       current["runtime_source_sha256"], current["broker_source_sha256"])
    assert body["spending_authority"] is False and body["human_review_approval"] is False
    assert body["model_performance"] is False


def test_forged_arithmetic_is_recomputed_even_if_all_submitted_hashes_are_updated(packets):
    raw, review, current, *_ = packets
    body, review = json.loads(raw), deepcopy(review)
    body["observations"][0]["result"]["rubric_score"]["earned_points"] = 100
    body["observations"][0]["result_sha256"] = digest(body["observations"][0]["result"])
    raw = json.dumps(body, sort_keys=True).encode()
    review["packet_files"]["positive.stdout"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="arithmetic"):
        operator.reviewed_mechanics(raw, review, current, now=packets[8])


@pytest.mark.parametrize("field,value", [
    ("runtime_source_sha256", "0" * 64), ("runtime_image_sha256", "0" * 64),
    ("broker_source_sha256", "0" * 64), ("release_sha256", "0" * 64),
])
def test_changed_installed_identity_does_not_inherit_method_evidence(packets, field, value):
    changed = list(deepcopy(packets))
    changed[2][field] = value
    with pytest.raises(ValueError):
        build(changed)


@pytest.mark.parametrize("field,value", [
    ("provider_calls", 1), ("provider_calls", False), ("human_review_approval", True),
    ("spending_authority", True), ("private_expectations_read", True),
    ("operator_source_sha256", "0" * 64), ("source_sha256", "0" * 64),
])
def test_untrusted_scope_or_authority_flags_are_rejected(packets, field, value):
    changed = list(deepcopy(packets))
    changed[6][field] = value
    with pytest.raises(ValueError):
        build(changed)


@pytest.mark.parametrize("field,value", [
    ("status", "pending"), ("observation_sha256", "0" * 64),
    ("identity_sha256", "0" * 64), ("control_sha256s", {}),
    ("human_review_approval", True), ("spending_authority", True),
])
def test_independent_review_is_exact_and_cannot_grant_other_authority(packets, field, value):
    changed = list(deepcopy(packets))
    changed[7][field] = value
    with pytest.raises(ValueError):
        build(changed)


def test_qualification_cannot_outlive_original_review_or_current_component(packets):
    changed = list(deepcopy(packets))
    changed[7]["expires_at"] = (packets[8] + timedelta(hours=3)).isoformat()
    with pytest.raises(ValueError, match="expiry"):
        build(changed)
    changed = list(deepcopy(packets))
    changed[8] = packets[8] + timedelta(hours=1)
    with pytest.raises(ValueError, match="expiry"):
        build(changed)


def test_foreign_or_missing_actual_task_binding_is_not_promoted(packets):
    changed = list(deepcopy(packets))
    changed[6]["bindings"][0]["scope"]["project_id"] = str(uuid4())
    with pytest.raises(ValueError, match="task/runtime"):
        build(changed)
    changed = list(deepcopy(packets))
    changed[6]["bindings"] = []
    with pytest.raises(ValueError, match="All actual"):
        build(changed)


def test_uploaded_or_mutable_control_files_are_not_original_operator_evidence(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="Fixed original"):
        operator.original(tmp_path / "uploaded.json", "a" * 64)
    monkeypatch.setattr(operator, "ARTIFACT_ROOT", tmp_path)
    value = tmp_path / "untrusted.json"
    value.write_text("{}")
    with pytest.raises(ValueError, match="Immutable"):
        operator.original(value, hashlib.sha256(value.read_bytes()).hexdigest())


@pytest.mark.parametrize("failure", ["revoked", "changed"])
def test_publication_rechecks_bindings_after_observation_before_any_insert(packets, monkeypatch, failure):
    from infra.gcp import kyc_binding_observation

    raw, mechanics_review, current, public, _, witness, observed, review, now, owner_raw = packets
    monkeypatch.setattr("anvil.kyc_policy_provision.enter", lambda *_: None)
    monkeypatch.setattr(operator, "identity", lambda: current)
    monkeypatch.setattr(operator, "public_group", lambda *_: public)
    inserted = []

    def query(c, statement, args=()):
        if "binding_fence" in statement:
            return {"locked": True}
        if "session_user" in statement:
            return {"login": "manufactured-unit-qualifier"}
        if "statement_timestamp" in statement:
            return {"now": now}
        inserted.append(statement)
        raise AssertionError("Publication must not insert stale qualification")

    def fresh(*_):
        if failure == "revoked":
            raise ValueError("Exact current unrevoked saved evaluator validation required")
        result = deepcopy(observed["bindings"][0])
        result["scope"]["runtime_source_sha256"] = "0" * 64
        return result

    monkeypatch.setattr(operator, "one", query)
    monkeypatch.setattr(kyc_binding_observation, "observe", fresh)
    with pytest.raises(ValueError, match="unrevoked|bindings changed"):
        operator.publish(object(), __import__("uuid").UUID(public["project_id"]),
                         __import__("uuid").UUID(public["id"]), observed, review, digest(review),
                         raw, mechanics_review, witness, owner_raw)
    assert inserted == []
