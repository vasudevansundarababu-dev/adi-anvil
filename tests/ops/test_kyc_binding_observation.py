"""No-provider controls for exact saved binding observation validation."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from anvil.db import digest
from anvil.golden_kyc_evaluators import CRITERIA
from anvil.golden_kyc_native_program import controls, program
from infra.gcp.kyc_binding_observation import check_pins


@pytest.fixture
def artifacts():
    project = uuid4()
    rows, refs = {}, []
    for criterion in CRITERIA:
        identifier, validation = str(uuid4()), str(uuid4())
        native = program(criterion).model_dump(mode="json")
        config = {"adapter": "builtin", "adapter_version": "1", "configuration": {"native_kyc": native}}
        evidence = controls(native)
        row = config | {"id": identifier, "project_id": project, "status": "ready",
                        "configuration_sha256": digest(config),
                        "validation": {"id": validation, "evidence": evidence, "evidence_sha256": digest(evidence)}}
        rows[identifier] = row
        refs.append({"configuration_id": identifier, "configuration_sha256": row["configuration_sha256"],
                     "validation_id": validation, "validation_sha256": digest(evidence),
                     "kind": "rubric", "requirement": criterion})
    env = {"runtime": "golden-kyc-postgres-v1", "openenv": "0.12.0", "harbor": "0.25.0",
           "reset": "before_every_application_model_repetition", "tools": ["assigned_banking_api_v1"],
           "source_sha256": "a" * 64, "implementation_sha256": "a" * 64,
           "paid_calls": False, "model_performance": False}
    environment = {"manifest": env, "manifest_sha256": digest(env)}
    manifest = {"source_sha256": "a" * 64, "environment_manifest_sha256": digest(env), "evaluators": refs}
    imported = {"project_id": project, "manifest": manifest, "manifest_sha256": digest(manifest)}
    scope = SimpleNamespace(project_id=project, runtime_source_sha256="a" * 64,
                            environment_binding_sha256=digest(env), evaluator_bindings_sha256=digest(refs))
    return scope, imported, environment, rows


def test_exact_actual_native_programs_and_real_scoring_receipts_pass(artifacts):
    result = check_pins(*artifacts)
    assert result["configuration_count"] == result["sealed_rubric_count"] == 20
    assert "not_substantive" in result["other_configurations"]


@pytest.mark.parametrize("field", ["project_id", "runtime_source_sha256", "environment_binding_sha256", "evaluator_bindings_sha256"])
def test_changed_scope_rejects(artifacts, field):
    scope, imported, env, rows = artifacts
    setattr(scope, field, uuid4() if field == "project_id" else "0" * 64)
    with pytest.raises(ValueError):
        check_pins(scope, imported, env, rows)


@pytest.mark.parametrize("mutation", ["missing", "revoked", "stale", "generic", "foreign", "changed_receipt"])
def test_missing_revoked_stale_generic_foreign_or_different_validation_rejects(artifacts, mutation):
    scope, imported, env, rows = artifacts
    row = next(iter(rows.values()))
    if mutation == "missing":
        row["validation"] = None
    elif mutation == "revoked":
        row["status"] = "revoked"
    elif mutation == "stale":
        row["configuration"]["native_kyc"]["normalizer_source_sha256"] = "0" * 64
    elif mutation == "generic":
        row["configuration"] = {"rule": {"kind": "equals", "field": "supported", "value": True}}
    elif mutation == "foreign":
        row["project_id"] = uuid4()
    else:
        row["validation"]["id"] = str(uuid4())
    with pytest.raises(ValueError):
        check_pins(scope, imported, env, rows)


def test_self_consistent_hashes_cannot_admit_unsupported_reset_contract(artifacts):
    scope, imported, env, rows = deepcopy(artifacts)
    env["manifest"]["reset"] = "never"
    env["manifest_sha256"] = digest(env["manifest"])
    imported["manifest"]["environment_manifest_sha256"] = env["manifest_sha256"]
    imported["manifest_sha256"] = digest(imported["manifest"])
    scope.environment_binding_sha256 = env["manifest_sha256"]
    with pytest.raises(ValueError, match="environment/tool/reset"):
        check_pins(scope, imported, env, rows)


@pytest.mark.parametrize("mutation", ["stale", "generic"])
def test_rehashing_cannot_promote_stale_or_generic_program_to_native_scoring(artifacts, mutation):
    scope, imported, env, rows = artifacts
    ref = imported["manifest"]["evaluators"][0]
    row = rows[ref["configuration_id"]]
    if mutation == "stale":
        row["configuration"]["native_kyc"]["normalizer_source_sha256"] = "0" * 64
    else:
        row["configuration"] = {"rule": {"kind": "equals", "field": "supported", "value": True}}
    row["configuration_sha256"] = digest({key: row[key] for key in ("adapter", "adapter_version", "configuration")})
    ref["configuration_sha256"] = row["configuration_sha256"]
    imported["manifest_sha256"] = digest(imported["manifest"])
    scope.evaluator_bindings_sha256 = digest(imported["manifest"]["evaluators"])
    with pytest.raises(ValueError):
        check_pins(scope, imported, env, rows)


def test_incomplete_rubric_manifest_is_not_complete_qualification(artifacts):
    scope, imported, env, rows = artifacts
    imported["manifest"]["evaluators"].pop()
    imported["manifest_sha256"] = digest(imported["manifest"])
    scope.evaluator_bindings_sha256 = digest(imported["manifest"]["evaluators"])
    with pytest.raises(ValueError, match="All exact"):
        check_pins(scope, imported, env, rows)
