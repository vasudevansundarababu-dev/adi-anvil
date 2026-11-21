"""Read-only installed binding observations; never a qualification or approval.

Run under an enrolled disjoint qualifier LOGIN. The output must be independently
reviewed before a new technical receipt may reference it. No private answers,
domain decisions, fixture approvals or provider calls are used here.
"""

import argparse
import os
import signal
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from anvil.db import digest, one
from anvil.golden_kyc_native_program import checked, controls, qualified
from anvil.kyc_policy_reviews import runtime_subject
from anvil.praxis_generic_contract import canonical

READ_TABLES = ("banking.anvil_imports", "banking.packs", "banking.applications",
               "anvil.environment_versions", "anvil.environment_task_bindings", "anvil.evaluator_configurations",
               "anvil.evaluator_validation_receipts", "anvil.evaluator_revocations")


def read_capability(c, project):
    if not one(c, "SELECT anvil.kyc_policy_operator_scope(%s) AS allowed", (project,))["allowed"]:
        raise ValueError("Actual enrolled operator scope required")
    observations = []
    for table in READ_TABLES:
        schema, name = table.split(".")
        security = one(c, "SELECT x.relrowsecurity AS enabled,x.relforcerowsecurity AS forced FROM pg_class x JOIN pg_namespace n ON n.oid=x.relnamespace WHERE n.nspname=%s AND x.relname=%s", (schema, name))
        if not security or not security["enabled"] or not security["forced"]:
            raise ValueError("Forced binding row security required")
        rows = c.execute("SELECT policyname,permissive,roles,cmd,qual FROM pg_policies WHERE schemaname=%s AND tablename=%s AND policyname IN('kyc_operator_binding_read','kyc_operator_binding_enrollment') ORDER BY policyname", (schema, name)).fetchall()
        expected = {"kyc_operator_binding_read": "PERMISSIVE", "kyc_operator_binding_enrollment": "RESTRICTIVE"}
        if (len(rows) != 2 or {r["policyname"] for r in rows} != set(expected)
                or any(r["permissive"] != expected[r["policyname"]] or r["roles"] != ["anvil_kyc_qualifier"]
                       or r["cmd"] != "SELECT" or r["qual"] != "anvil.kyc_policy_operator_scope(project_id)" for r in rows)):
            raise ValueError("Exact separately deployed operator enrollment policies required")
        privileges = one(c, "SELECT has_table_privilege(current_user,%s,'SELECT') AS readable,"
                         "has_table_privilege(current_user,%s,'INSERT,UPDATE,DELETE,TRUNCATE') AS writable",
                         (table, table))
        if not privileges["readable"] or privileges["writable"]:
            raise ValueError("Read-only public binding metadata capability required")
        observations.append({"table": table, "policies": rows, "readable": True, "writable": False})
    for table in ("banking_private.expectations", "banking_private.expectation_versions",
                  "banking_private.scenarios", "banking_private.results", "banking.seals"):
        schema, name = table.split(".")
        privilege = one(c, "SELECT has_table_privilege(current_user,x.oid,'SELECT') AS readable FROM pg_class x JOIN pg_namespace n ON n.oid=x.relnamespace WHERE n.nspname=%s AND x.relname=%s", (schema, name))
        if not privilege or privilege["readable"]:
            raise ValueError("Binding observer must have no private grading access")
    return {"schema_version": "anvil.kyc-operator-read-capability.v1", "tables": observations,
            "private_grading_reads": False, "evidence_sha256": digest(observations)}


def check_pins(scope, imported, environment, configurations, *, proof=None):
    from anvil.golden_kyc_evaluators import CRITERIA

    manifest = imported["manifest"]
    if (str(imported["project_id"]) != str(scope.project_id)
            or digest(manifest) != imported["manifest_sha256"]
            or manifest["source_sha256"] != scope.runtime_source_sha256
            or manifest["environment_manifest_sha256"] != scope.environment_binding_sha256
            or digest(manifest["evaluators"]) != scope.evaluator_bindings_sha256
            or digest(environment["manifest"]) != environment["manifest_sha256"]
            or environment["manifest_sha256"] != scope.environment_binding_sha256):
        raise ValueError("Exact project/source/environment/evaluator identities required")
    env = environment["manifest"]
    expected = {"runtime": "golden-kyc-postgres-v1", "openenv": "0.12.0", "harbor": "0.25.0",
                "reset": "before_every_application_model_repetition", "tools": ["assigned_banking_api_v1"],
                "source_sha256": scope.runtime_source_sha256, "implementation_sha256": scope.runtime_source_sha256,
                "paid_calls": False, "model_performance": False}
    if any(type(env.get(k)) is not type(v) or env[k] != v for k, v in expected.items()):
        raise ValueError("Supported installed environment/tool/reset contract required")
    selected = []
    seen = set()
    for ref in manifest["evaluators"]:
        key = str(ref["configuration_id"])
        if key in seen:
            raise ValueError("Unique evaluator configuration bindings required")
        seen.add(key)
        row = configurations.get(key)
        if (not row or str(row["project_id"]) != str(scope.project_id) or row.get("status") != "ready"
                or digest({"adapter": row["adapter"], "adapter_version": row["adapter_version"],
                           "configuration": row["configuration"]}) != ref["configuration_sha256"]
                or row["configuration_sha256"] != ref["configuration_sha256"]
                or not row.get("validation")
                or str(row["validation"]["id"]) != str(ref["validation_id"])
                or row["validation"]["evidence_sha256"] != ref["validation_sha256"]):
            raise ValueError("Exact current unrevoked saved evaluator validation required")
        if ref["kind"] == "rubric":
            if set(row["configuration"]) != {"native_kyc"} or row["adapter"] != "builtin":
                raise ValueError("Substantive sealed-trace rubric program required")
            program = row["configuration"]["native_kyc"]
            selected_program = checked(program, _resource_proof=proof)
            if (selected_program.criterion != ref["requirement"]
                    or not qualified(program, row["validation"], _resource_proof=proof)):
                raise ValueError("Current exact native scoring controls required")
            selected.append(selected_program.criterion)
    if len(selected) != len(CRITERIA) or set(selected) != set(CRITERIA):
        raise ValueError("All exact supported sealed KYC rubric criteria required")
    return {"configuration_count": len(seen), "sealed_rubric_count": len(selected),
            "other_configurations": "software_integrity_only_not_substantive_criterion_qualification"}


def observe(c, project, input_id, task, revision):
    from anvil import evaluator_configurations
    from anvil.golden_component_qualification import installed
    from anvil.golden_kyc_anvil import _validate
    from anvil.golden_kyc_resolved_store import policy_scope
    from anvil.golden_kyc_source import source_hash
    from anvil.software_resource_proof import software_resources

    capability = read_capability(c, project)
    scope = policy_scope(c, project, input_id, task, revision)
    component = installed()
    if (not component["ready"] or scope.runtime_source_sha256 != source_hash()
            or scope.runtime_image_sha256 != component["evidence"]["runtime_image_sha256"]):
        raise ValueError("Exact currently qualified installed component required")
    imported = one(c, "SELECT i.* FROM anvil.kyc_resolved_input_versions v JOIN banking.anvil_imports i "
                   "ON i.project_id=v.project_id AND i.id=v.case_import_id WHERE v.project_id=%s AND v.id=%s",
                   (project, input_id))
    if not imported:
        raise ValueError("Actual registered input import required")
    environment = one(c, "SELECT manifest,manifest_sha256 FROM anvil.environment_versions WHERE project_id=%s AND id=%s",
                      (project, imported["environment_id"]))
    observations = {"actual_operator_read_capability": capability}
    # Same bounded proof pattern as validate_software: all source/dependency
    # checks remain enabled, once per actual transaction, never cached globally.
    with software_resources(c) as proof:
        _validate(c, imported, _resource_proof=proof)
        rows = {str(ref["configuration_id"]): evaluator_configurations.get(c, ref["configuration_id"], _resource_proof=proof)
                for ref in imported["manifest"]["evaluators"]}
        positive = check_pins(scope, imported, environment, rows, proof=proof)
        observations["actual_binding"] = {"accepted": True, "identities": positive}
        scores = {}
        for ref in imported["manifest"]["evaluators"]:
            if ref["kind"] == "rubric":
                program = rows[str(ref["configuration_id"])]["configuration"]["native_kyc"]
                scores[ref["requirement"]] = controls(program, _resource_proof=proof)
        observations["actual_saved_native_scoring_controls"] = scores
        for name, field in (("changed_environment", "environment_binding_sha256"),
                            ("changed_evaluator_manifest", "evaluator_bindings_sha256"),
                            ("changed_runtime_source", "runtime_source_sha256"),
                            ("foreign_project", "project_id")):
            value = uuid4() if field == "project_id" else ("0" if getattr(scope, field) != "0" * 64 else "1") * 64
            try:
                check_pins(scope.model_copy(update={field: value}), imported, environment, rows, proof=proof)
            except ValueError:
                observations[name] = {"rejected": True, "origin": "copied_input_negative_control"}
            else:
                raise ValueError("Binding identity negative control accepted")
        key = next(str(ref["configuration_id"]) for ref in imported["manifest"]["evaluators"] if ref["kind"] == "rubric")
        for name in ("missing_validation", "revoked_configuration", "stale_normalizer"):
            changed = deepcopy(rows)
            if name == "missing_validation":
                changed[key]["validation"] = None
            elif name == "revoked_configuration":
                changed[key]["status"] = "revoked"
            else:
                changed[key]["configuration"]["native_kyc"]["normalizer_source_sha256"] = "0" * 64
            try:
                check_pins(scope, imported, environment, changed, proof=proof)
            except ValueError:
                observations[name] = {"rejected": True, "origin": "copied_input_negative_control"}
            else:
                raise ValueError("Evaluator integrity negative control accepted")
    hidden = one(c, "SELECT count(*) AS n FROM banking.anvil_imports WHERE project_id<>%s", (project,))
    if hidden["n"] != 0:
        raise ValueError("Qualifier project isolation failed")
    observations["actual_project_isolation"] = {"foreign_rows_visible": 0}
    now = one(c, "SELECT statement_timestamp() AS now")["now"]
    return {"schema_version": "anvil.installed-kyc-binding-observation.v1", "status": "observed_not_qualified",
            "subject": runtime_subject(scope).model_dump(mode="json"), "scope": scope.model_dump(mode="json"),
            "observed_at": now.isoformat(), "component_evidence_sha256": digest(component["evidence"]),
            "component_expires_at": component["evidence"]["expires_at"],
            "import_id": str(imported["id"]), "import_manifest_sha256": imported["manifest_sha256"],
            "observations": observations, "provider_calls": 0, "private_expectations_read": False,
            "policy_review_granted": False, "case_review_granted": False, "spending_authority": False,
            "model_performance": False}


def main():
    def timeout(*_):
        raise TimeoutError("Five-minute observation deadline exceeded")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(300)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=UUID, required=True)
    parser.add_argument("--input", type=UUID, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (not args.output.is_absolute() or args.output.parent.resolve() != args.output.parent
            or args.output.parent.stat().st_mode & 0o022):
        raise ValueError("Owner-controlled absolute output directory required")
    import psycopg
    from psycopg.rows import dict_row

    from anvil.kyc_policy_provision import enter

    with psycopg.connect(os.environ["ANVIL_KYC_QUALIFIER_DATABASE_URL"], row_factory=dict_row,
                          connect_timeout=2, options="-c default_transaction_read_only=on -c statement_timeout=300000 -c lock_timeout=1000") as c:
        enter(c, args.project)
        report = observe(c, args.project, args.input, args.task, args.revision)
    raw = canonical(report)
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    print(canonical({"status": report["status"], "sha256": digest(report), "provider_calls": 0,
                     "finished_at": datetime.now(timezone.utc).isoformat()}).decode())
    signal.alarm(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("installed_binding_observation_blocked_no_qualification_or_run_authority_granted\n")
        raise SystemExit(1) from None
