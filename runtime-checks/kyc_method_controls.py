"""KYC method and diagnostic mechanics over manufactured traces; no qualification.

Run inside the exact candidate image with no network, database, Docker socket or
credentials. These examples do not represent reviewed application expectations,
policy applicability, task-specific binding, model behavior or project isolation.
An independent publisher must separately verify those identities and evidence.
"""

import hashlib
import json
import os
import sys
from copy import deepcopy
from pathlib import Path


def require(condition):
    if not condition:
        raise ValueError("KYC method mechanics control failed")


def manufactured_trace():
    from anvil.golden_kyc_data import VERSION

    parties = [{"id": f"control-party-{index}", "role": "adult_owner", "birth_date": "1990-01-01"}
               for index in (1, 2)]
    snapshot = {"id": "manufactured-method-control", "parties": parties, "product": "adult_joint",
                "requested_product": "adult_joint", "assessment_date": "2026-11-12"}
    documents = [{"id": f"agreement-{index}", "party_id": party["id"], "kind": "agreement"}
                 for index, party in enumerate(parties)]
    operations = {}
    for party in parties:
        for kind in ("identity", "screening", "authority"):
            identifier = f"operation-{len(operations) + 1}"
            operations[identifier] = {"id": identifier, "kind": kind,
                "result": {"party_id": party["id"], "input_revision": 1,
                           "verification_status": "corroborated"}}
    reads = [snapshot["id"], VERSION, *operations, *(document["id"] for document in documents)]
    final = {"decision": "ready_for_approval", "assessed_revision": 1, "account_type": "adult_joint",
             "reason": "Manufactured software control only", "outstanding_actions": [], "evidence_ids": reads[:],
             "party_assessments": [{"party_id": party["id"], "role": party["role"], "status": "verified",
                 "verification_evidence_ids": [operation["id"] for operation in operations.values()
                    if operation["kind"] == "identity" and operation["result"]["party_id"] == party["id"]]}
                 for party in parties]}
    state = {"application": snapshot | {"documents": documents}, "revision": 1,
             "operations": operations, "reads": reads, "final": final,
             "requests": {}, "specialists": {}, "findings": {}, "idempotency": dict.fromkeys(operations)}
    return snapshot, state


def observe():
    from anvil.benchmark_runs import METHODS
    from anvil.db import digest
    from anvil.golden_kyc_evaluators import CRITERIA, evaluate, score
    from anvil.golden_kyc_grader import normalize
    from anvil.golden_kyc_source import source_hash

    before = source_hash()
    method = next(item for item in METHODS if item["id"] == "task-rubric-v1")
    require(method["status"] == "ready" and method["kind"] == "deterministic")
    snapshot, original = manufactured_trace()
    expectation = {"independent_expectation_review": "approved", "legal_qualification": "pending",
                   "intended_decision": "ready_for_approval"}
    observations = []

    def run(name, state, expected):
        checks, _, critical = normalize(state, snapshot, [])
        result = evaluate(state, expected, checks, critical)
        observations.append({"case": name, "input_sha256": digest({"snapshot": snapshot, "state": state,
                             "manufactured_expectation": expected}), "result": result,
                             "result_sha256": digest(result)})
        return checks, result

    checks, positive = run("supported_nonstate_legal_pending", deepcopy(original), expectation)
    require(all(checks[key] is True for key in CRITERIA if not key.startswith("state_")))
    require(positive["rubric_score"] == {"earned_points": 80, "maximum_points": 100, "unscored_points": 20})
    require(positive["overall_result"] == "not_evaluated")
    require(all(positive["checks"][key] is None for key in CRITERIA if key.startswith("state_")))

    partial = deepcopy(original)
    partial["final"]["evidence_ids"].remove(snapshot["id"])
    _, result = run("missing_citation_partial", partial, expectation)
    require(result["checks"]["profile"] == 2 and result["rubric_score"]["maximum_points"] == 100)

    wrong_party = deepcopy(original)
    wrong_party["operations"]["operation-1"]["result"]["party_id"] = "wrong-control-party"
    checks, result = run("unsupported_clearance_critical_veto", wrong_party, expectation)
    require(checks["identification_verification"] is False)
    require(result["checks"]["identification_verification"] == 0)
    require(result["overall_result"] == "critical_fail" and "unsupported_mandatory_clearance" in result["critical_failures"])

    _, result = run("pending_expectation_review", deepcopy(original), expectation | {"independent_expectation_review": "pending"})
    require(result["rubric_score"] == {"earned_points": 0, "maximum_points": 100, "unscored_points": 100})
    require(result["overall_result"] == "not_evaluated")

    missing = expectation.copy()
    missing.pop("intended_decision")
    _, result = run("missing_intended_decision", deepcopy(original), missing)
    require(result["decision_correctness"] is None and result["checks"]["decision"] is None)
    require(result["overall_result"] == "not_evaluated")

    # Exercise the real aggregate boundary independently of manufactured state
    # references. A critical veto cannot be averaged away by 100 point anchors.
    all_points = dict.fromkeys(CRITERIA, 5)
    veto = score(all_points, correct_decision=True, mandatory=True, critical_failures=["manufactured-veto"])
    require(veto["rubric_score"]["earned_points"] == 100 and veto["overall_result"] == "critical_fail")
    observations.append({"case": "aggregate_critical_veto", "result": veto, "result_sha256": digest(veto)})
    require(source_hash() == before)
    return {"schema_version": "anvil.kyc-method-mechanics-observation.v1", "status": "observed_not_qualified",
            "origin": "manufactured_no_model_software_controls", "method": method, "method_sha256": digest(method),
            "runtime_source_sha256": before, "observations": observations, "provider_calls": 0,
            "private_expectations_read": False, "project_isolation": "not_observed",
            "task_specific_binding": "not_observed", "policy_review_granted": False,
            "case_review_granted": False, "spending_authority": False, "model_performance": False}


def credential_names(environment):
    suffixes = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_DSN", "_DATABASE_URL", "_CREDENTIALS")
    exact = {"DATABASE_URL", "MIGRATION_DATABASE_URL", "GOOGLE_APPLICATION_CREDENTIALS",
             "AWS_PROFILE", "AWS_SHARED_CREDENTIALS_FILE", "AZURE_CONFIG_DIR", "CLOUDSDK_CONFIG"}
    return sorted(key for key, value in environment.items()
                  if value and (key.upper() in exact or key.upper().endswith(suffixes)))


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode and os.geteuid() == 10001)
    require(not credential_names(os.environ))
    require(all(os.environ.get(key, "false") == "false" for key in (
        "ANVIL_LIVE_PROVIDERS_ENABLED", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", "ANVIL_REAL_EMAIL_ENABLED")))
    result = observe()
    from anvil.diagnostic_measures import TARGETS
    from anvil.native_diagnostic import validate

    diagnostic = validate({"schema_version": "anvil.native-diagnostic-program.v1",
                           "method": "anvil.diagnostic-measure.v1", "target_ids": sorted(TARGETS)})
    require(diagnostic["passed"] is True and diagnostic["provider_calls"] == 0
            and diagnostic["human_calibration_established"] is False
            and diagnostic["model_performance_validated"] is False)
    result["diagnostic_software_observation"] = diagnostic
    result["operator_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
