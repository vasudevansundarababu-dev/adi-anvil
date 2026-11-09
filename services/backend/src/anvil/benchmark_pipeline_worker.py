"""Explicit local Docker-host qualification of reviewed fictional SME builds."""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

import rfc8785
from fastapi import HTTPException

from anvil.benchmark_compiler import CompiledTask
from anvil.benchmark_pipeline import (
    PROFILE,
    checksum,
    claim,
    current_dependencies,
    policy_status,
    private_metadata,
    record,
    review_status,
    source_snapshot,
)
from anvil.benchmark_qualification import native_trial, resource_probe
from anvil.benchmark_storage import bind_private, read_private_record, stage_private, vault_root
from anvil.config import ROOT
from anvil.db import audit, one, transaction, uid


def _live_claim(c, operation):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (operation["project_id"],))
    current = one(
        c,
        "SELECT * FROM anvil.benchmark_qualification_operations WHERE id=%s FOR UPDATE",
        (operation["id"],),
    )
    if (
        current["state"] != "running"
        or current["fence"] != operation["fence"]
        or current["lease_until"] <= datetime.now(timezone.utc)
    ):
        raise HTTPException(409, "Qualification lease is no longer current; no retry")
    return current


def _assert_policy(operation):
    _, blockers = policy_status(
        operation["project_id"], operation["created_by"], operation["build_id"]
    )
    with transaction(operation["project_id"], operation["created_by"]) as c:
        if not one(
            c,
            "SELECT anvil.benchmark_private_access(%s,'benchmark_trace',%s) AS allowed",
            (operation["project_id"], uid()),
        )["allowed"]:
            blockers.append("evaluation_assignment_missing")
        current = record(c, "benchmark_qualification_operations", operation["id"])
        if (
            current["state"] != "running"
            or current["fence"] != operation["fence"]
            or current["lease_until"] <= datetime.now(timezone.utc)
        ):
            blockers.append("qualification_lease_stale")
    if blockers:
        raise HTTPException(409, "Qualification policy no longer admits local work")


def _task_inputs(operation):
    project, user = operation["project_id"], operation["created_by"]
    with transaction(project, user) as c:
        build = record(c, "benchmark_builds", operation["build_id"])
        review = record(c, "benchmark_source_reviews", build["review_id"])
        rows = c.execute(
            "SELECT t.*,p.package_sha256,p.package_artifact_id FROM anvil.benchmark_build_tasks t JOIN anvil.harbor_packages p ON p.project_id=t.project_id AND p.id=t.package_id WHERE t.build_id=%s ORDER BY t.task_id",
            (build["id"],),
        ).fetchall()
        metadata = [
            (
                row,
                private_metadata(c, row["package_artifact_id"]),
                private_metadata(c, row["bindings_artifact_id"]),
            )
            for row in rows
        ]
    _, _, parsed, _ = source_snapshot(project, user, build["receipt_id"])
    if {r[0]["task_id"] for r in metadata} != {t.id for t in parsed.parsed.manifest.tasks}:
        raise ValueError("Build task membership changed")
    return build, review, parsed, metadata


def _validate_native(compiled, task, results, dependencies=None):
    if (
        not isinstance(results, list)
        or len(results) != 3
        or any(not isinstance(r, dict) for r in results)
        or {r.get("mode") for r in results} != {"positive", "empty", "guardrail"}
    ):
        raise ValueError("Incomplete native qualification matrix")
    if checksum(rfc8785.dumps(compiled.bindings)) != compiled.binding_sha256:
        raise ValueError("Compiled binding changed")
    sources = (dependencies if dependencies is not None else current_dependencies({}))["sources"]
    possible = sum(criterion.possible_points for criterion in task.criteria)
    common = {
        "origin": "original_synthetic_software_conformance",
        "harbor_version": "0.25.0",
        "source_authenticity": "isolated_test_signer_not_product_authority",
        "binding_sha256": compiled.binding_sha256,
        "compiled_archive_sha256": compiled.archive_sha256,
        "manifest_sha256": compiled.bindings["manifest_sha256"],
        "private_file_bindings": compiled.bindings["private_files"],
        "qualification_sha256": sources["services/backend/src/anvil/benchmark_qualification.py"],
        "compiler_source_sha256": sources["services/backend/src/anvil/benchmark_compiler.py"],
        "adapter_sha256": sources["services/harbor/src/anvil_harbor/sme.py"],
        "task_id": task.id,
        "possible_points": possible,
        "provider_calls": 0,
        "candidate_stopped_before_evaluation": True,
        "candidate_mounts_private": False,
        "evaluator_mounts_actor": False,
        "forbidden_access_attempts_denied": 4,
        "control_checks": {"non_root_readonly_no_egress_cgroups": True, "fresh_actor": True},
    }
    containers = set()
    for result in results:
        mode = result["mode"]
        expected = {
            **common,
            "mode": mode,
            "points": possible if mode == "positive" else 0,
            "tool_calls": possible if mode == "positive" else 0,
            "denied_tool_calls": 1 if mode == "guardrail" else 0,
        }
        receipt_fields = set(expected) | {
            "seal_sha256",
            "candidate_container",
            "evaluator_container",
            "native_receipt_sha256",
        }
        if set(result) not in (receipt_fields, receipt_fields | {"public_capture"}):
            raise ValueError("Native result fields are incomplete or unsupported")
        from anvil.benchmark_qualification_evidence import public_projection

        public_projection(result.get("public_capture"))
        if any(
            type(result[key]) is not type(value)
            or json.dumps(result[key], sort_keys=True, allow_nan=False)
            != json.dumps(value, sort_keys=True, allow_nan=False)
            for key, value in expected.items()
        ):
            raise ValueError("Native result does not bind expected task, controls and inputs")
        for key in (
            "seal_sha256",
            "candidate_container",
            "evaluator_container",
            "native_receipt_sha256",
        ):
            if not isinstance(result[key], str) or not re.fullmatch(r"[a-f0-9]{64}", result[key]):
                raise ValueError("Native receipt digest or container identity is invalid")
        for key in ("candidate_container", "evaluator_container"):
            if result[key] in containers:
                raise ValueError("Native qualification requires fresh separate containers")
            containers.add(result[key])
        raw = json.dumps(
            {k: v for k, v in result.items() if k != "native_receipt_sha256"},
            sort_keys=True,
            allow_nan=False,
        ).encode()
        if checksum(raw) != result["native_receipt_sha256"]:
            raise ValueError("Native receipt bytes changed")


def _validate_resources(results):
    controls = {
        "memory_pids": {"pids_denied": True, "memory_oom_observed": True},
        "tree_timeout": {"owned_timeout_tree_stopped": True},
        "stdio_overflow": {"stdio_overflow_denied": True},
        "stdio_timeout": {"stdio_timeout_denied": True},
    }
    if (
        not isinstance(results, list)
        or len(results) != len(controls)
        or any(not isinstance(r, dict) for r in results)
        or {r.get("mode") for r in results} != set(controls)
    ):
        raise ValueError("Incomplete resource qualification matrix")
    containers = set()
    for result in results:
        expected = {"retained": True, **controls[result["mode"]]}
        fields = set(expected) | {"mode", "container"}
        if result["mode"] == "memory_pids":
            fields.add("children_started")
            count = result.get("children_started")
            if type(count) is not int or not 1 <= count < 16:
                raise ValueError("PID exhaustion was not observed")
        if set(result) != fields or any(
            result[key] is not value for key, value in expected.items()
        ):
            raise ValueError("Resource qualification controls did not pass")
        container = result["container"]
        if (
            not isinstance(container, str)
            or not re.fullmatch(r"[a-f0-9]{64}", container)
            or container in containers
        ):
            raise ValueError("Resource qualification requires fresh retained containers")
        containers.add(container)


def _finish(operation, report, task_reports, state):
    project, user = operation["project_id"], operation["created_by"]
    if state == "passed":
        _assert_policy(operation)
    with transaction(project, user) as c:
        _live_claim(c, operation)
        build = record(c, "benchmark_builds", operation["build_id"])
        review = record(c, "benchmark_source_reviews", build["review_id"])
        if state == "passed" and review_status(c, review, build["receipt_id"]):
            raise HTTPException(409, "Source review changed before qualification capture")
        report_id = bind_private(c, report, created_by=user)
        for row, compiled, prepared in task_reports:
            artifact = bind_private(c, prepared, created_by=user)
            identifier = uid()
            c.execute(
                "INSERT INTO anvil.benchmark_qualifications(id,project_id,source_id,package_id,evaluator_binding_id,package_sha256,environment_digest,compiler_sha256,tool_schema_sha256,harbor_version,outcome,report_artifact_id,reviewed_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'0.25.0',%s,%s,%s)",
                (
                    identifier,
                    project,
                    row["source_id"],
                    row["package_id"],
                    review["evaluator_binding_id"],
                    compiled.archive_sha256,
                    compiled.bindings["environment"]["oci_manifest_digest"],
                    build["dependencies"]["sources"][
                        "services/backend/src/anvil/benchmark_compiler.py"
                    ],
                    checksum(rfc8785.dumps(compiled.bindings["tools"])),
                    state,
                    artifact,
                    user,
                ),
            )
            c.execute(
                "INSERT INTO anvil.benchmark_operation_results(project_id,operation_id,build_id,task_id,source_id,package_id,qualification_id) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    project,
                    operation["id"],
                    build["id"],
                    row["task_id"],
                    row["source_id"],
                    row["package_id"],
                    identifier,
                ),
            )
        c.execute(
            "UPDATE anvil.benchmark_qualification_operations SET state=%s,report_artifact_id=%s,finished_at=now(),safe_code=%s WHERE id=%s",
            (state, report_id, "qualification_" + state, operation["id"]),
        )
        audit(
            c,
            project,
            user,
            "benchmark.qualification_" + state,
            operation["id"],
            {
                "subject_sha256": build["subject_sha256"],
                "report_sha256": report.sha256,
                "scope": PROFILE,
            },
        )
    return state


def process_operation(project, operation_id, user):
    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        raise RuntimeError("Explicit isolated fictional native opt-in required")
    operation = claim(project, operation_id, user)
    if operation is None:
        return "not_claimed"
    task_reports = []
    try:
        _assert_policy(operation)
        build, review, parsed, metadata = _task_inputs(operation)
        folder = vault_root() / (".q-" + uuid4().hex[:20])
        folder.mkdir(mode=0o700)
        limits = []
        for mode in ("memory_pids", "tree_timeout", "stdio_overflow", "stdio_timeout"):
            _assert_policy(operation)
            limits.append(resource_probe(mode, folder / mode))
        _validate_resources(limits)
        for row, package_metadata, binding_metadata in metadata:
            _assert_policy(operation)
            task = next(task for task in parsed.parsed.manifest.tasks if task.id == row["task_id"])
            package = read_private_record(package_metadata)
            bindings = read_private_record(binding_metadata)
            if (
                checksum(package) != row["package_sha256"]
                or checksum(bindings) != row["binding_sha256"]
            ):
                raise ValueError("Stored package or binding changed")
            compiled = CompiledTask(
                row["package_sha256"], len(package), row["binding_sha256"], json.loads(bindings)
            )
            path = folder / (task.id + ".zip")
            with path.open("xb") as stream:
                stream.write(package)
            path.chmod(0o600)
            results = []
            for mode in ("positive", "empty", "guardrail"):
                _assert_policy(operation)
                trial = folder / (task.id + "-" + mode)
                trial.mkdir(mode=0o700)
                private = ROOT / "fixtures/benchmark-bundle/fictional-points-v1/eval_pack" / task.id
                results.append(native_trial(path, compiled, task, private, trial, mode=mode))
            _validate_native(compiled, task, results, build["dependencies"])
            document = {
                "origin": "original_synthetic_software_conformance",
                "scope": PROFILE,
                "subject_sha256": build["subject_sha256"],
                "binding_sha256": compiled.binding_sha256,
                "gates": {gate: "passed" for gate in ("G1", "G2", "G3", "G4", "G5")},
                "limits": limits,
                "native_trials": results,
            }
            prepared = stage_private(
                project, rfc8785.dumps(document), "benchmark_trace", "application/json"
            )
            task_reports.append((row, compiled, prepared))
        report = stage_private(
            project,
            rfc8785.dumps(
                {
                    "scope": PROFILE,
                    "subject_sha256": build["subject_sha256"],
                    "task_reports": [p.sha256 for _, _, p in task_reports],
                    "dependencies": build["dependencies"],
                    "model_performance": False,
                }
            ),
            "benchmark_trace",
            "application/json",
        )
        return _finish(operation, report, task_reports, "passed")
    except Exception:
        # A failed/ambiguous native attempt is terminal; never reclaim it as a new dispatch.
        with transaction(project, user) as c:
            current = record(c, "benchmark_qualification_operations", operation_id)
        if current["state"] != "running" or current["fence"] != operation["fence"]:
            return "not_captured"
        _, blockers = policy_status(project, user, operation["build_id"])
        state = "blocked" if blockers else "failed"
        report = stage_private(
            project,
            rfc8785.dumps(
                {
                    "scope": PROFILE,
                    "safe_code": "qualification_" + state,
                    "model_performance": False,
                }
            ),
            "benchmark_trace",
            "application/json",
        )
        return _finish(operation, report, [], state)


def main():
    parser = argparse.ArgumentParser(
        description="Explicit isolated fictional benchmark qualification; no providers"
    )
    parser.add_argument("--project", type=UUID, required=True)
    parser.add_argument("--operation", type=UUID, required=True)
    parser.add_argument("--admin", type=UUID, required=True)
    args = parser.parse_args()
    print(process_operation(args.project, args.operation, args.admin))


if __name__ == "__main__":
    main()
