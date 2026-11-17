"""Reviewed fictional evaluator registry and queue; never dispatches code or a paid judge."""

import json
from datetime import datetime, timezone

from fastapi import HTTPException

from anvil.benchmark_compiler import FIXTURE_IMAGE
from anvil.benchmark_evaluator_program import (
    PROFILE,
    calibration,
    canonical,
    evaluate,
    policy_checked,
    seal,
    seal_checked,
    sha,
    validate_report,
)
from anvil.benchmark_storage import read_private_record
from anvil.config import ROOT
from anvil.db import audit, one, transaction, uid

PROGRAM = ROOT / "services/backend/src/anvil/benchmark_evaluator_program.py"


def implementation_sha256():
    return sha(PROGRAM.read_bytes())


def metadata(c, artifact_id, classification):
    row = one(c, "SELECT * FROM anvil.artifacts WHERE id=%s", (artifact_id,))
    if row is None:
        raise HTTPException(404, "Evaluator artifact not found")
    if row["classification"] != classification:
        raise HTTPException(409, "Invalid evaluator artifact class")
    return row


def prepare_review(project, user, policy_id, evidence_id):
    with transaction(project, user) as c:
        policy = metadata(c, policy_id, "benchmark_eval")
        evidence = metadata(c, evidence_id, "benchmark_eval")
    raw = read_private_record(policy)
    if len(raw) > 262144:
        raise HTTPException(409, "Evaluator policy exceeds limit")
    parsed = json.loads(raw)
    policy_checked(parsed)
    if canonical(parsed) != raw:
        raise HTTPException(409, "Evaluator policy must be canonical")
    read_private_record(evidence)
    checks = calibration()
    if checks["status"] != "passed":
        raise HTTPException(409, "Local evaluator calibration failed")
    return policy, evidence, parsed, sha(canonical(checks)), implementation_sha256()


def register(c, project, user, prepared, expires_at):
    policy, evidence, parsed, calibration_hash, implementation = prepared
    metadata(c, policy["id"], "benchmark_eval")
    metadata(c, evidence["id"], "benchmark_eval")
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(409, "Evaluator review already expired")
    binding = one(
        c,
        "SELECT id FROM anvil.benchmark_evaluator_bindings WHERE project_id=%s AND registry_id=%s AND version=%s AND implementation_sha256=%s AND policy_sha256=%s",
        (project, PROFILE, "1.0.0", implementation, policy["sha256"]),
    )
    if binding is None:
        binding = {"id": uid()}
        c.execute(
            "INSERT INTO anvil.benchmark_evaluator_bindings(id,project_id,registry_id,version,implementation_sha256,image_digest,policy_sha256,reviewed_by,review_evidence_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                binding["id"],
                project,
                PROFILE,
                "1.0.0",
                implementation,
                FIXTURE_IMAGE.split("@")[1],
                policy["sha256"],
                user,
                evidence["sha256"],
            ),
        )
    registry = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_evaluator_registrations(id,project_id,binding_id,policy_artifact_id,evidence_artifact_id,policy_sha256,implementation_sha256,calibration_sha256,reviewed_by,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            registry,
            project,
            binding["id"],
            policy["id"],
            evidence["id"],
            policy["sha256"],
            implementation,
            calibration_hash,
            user,
            expires_at,
        ),
    )
    audit(
        c,
        project,
        user,
        "benchmark.evaluator_reviewed",
        registry,
        {"scope": "fictional_local_software_only"},
    )
    return {
        "registry_id": registry,
        "scope": "fictional_local_software_only",
        "external_judge": "blocked",
    }


def prepare_evaluation(project, user, registry_id, output_id):
    with transaction(project, user) as c:
        registry = one(
            c, "SELECT * FROM anvil.benchmark_evaluator_registrations WHERE id=%s", (registry_id,)
        )
        if registry is None:
            raise HTTPException(404, "Evaluator registry not found")
        policy = metadata(c, registry["policy_artifact_id"], "benchmark_eval")
        output = metadata(c, output_id, "benchmark_sealed")
    parsed = json.loads(read_private_record(policy))
    sealed = json.loads(read_private_record(output))
    policy_checked(parsed)
    seal_checked(sealed)
    evaluate(parsed, sealed)
    if registry["implementation_sha256"] != implementation_sha256() or registry[
        "calibration_sha256"
    ] != sha(canonical(calibration())):
        raise HTTPException(409, "Evaluator source or calibration changed")
    return registry, output, sealed


def enqueue(c, project, user, prepared, key):
    registry, output, sealed = prepared
    subject = sha(
        canonical(
            {
                "registry": str(registry["id"]),
                "output": output["sha256"],
                "sealed": sealed["sealed_sha256"],
            }
        )
    )
    old = one(
        c,
        "SELECT job_id,subject_sha256 FROM anvil.benchmark_evaluation_requests WHERE project_id=%s AND idempotency_key=%s",
        (project, key),
    )
    if old:
        if old["subject_sha256"] != subject:
            raise HTTPException(409, "Immutable evaluation request conflict")
        return projection(c, old["job_id"])
    if not one(
        c, "SELECT anvil.evaluation_review_live(%s,%s,%s) ok", (project, registry["id"], user)
    )["ok"]:
        raise HTTPException(409, "Current review and individual evaluation assignment required")
    metadata(c, output["id"], "benchmark_sealed")
    metadata(c, registry["policy_artifact_id"], "benchmark_eval")
    job = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_evaluator_jobs(id,project_id,binding_id,sealed_output_artifact_id,created_by,state) VALUES(%s,%s,%s,%s,%s,'queued')",
        (job, project, registry["binding_id"], output["id"], user),
    )
    c.execute(
        "INSERT INTO anvil.benchmark_evaluation_requests(project_id,job_id,registry_id,task_id,sealed_sha256,output_sha256,idempotency_key,subject_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            project,
            job,
            registry["id"],
            sealed["task_id"],
            sealed["sealed_sha256"],
            output["sha256"],
            key,
            subject,
        ),
    )
    for artifact in (output, metadata(c, registry["policy_artifact_id"], "benchmark_eval")):
        c.execute(
            "INSERT INTO anvil.benchmark_evaluator_job_inputs(project_id,job_id,artifact_id,artifact_sha256) VALUES(%s,%s,%s,%s)",
            (project, job, artifact["id"], artifact["sha256"]),
        )
    audit(c, project, user, "benchmark.evaluation_queued", job)
    return projection(c, job)


def projection(c, job):
    row = one(
        c,
        "SELECT j.id,j.state,j.lease_until,r.status,r.safe_code FROM anvil.benchmark_evaluator_jobs j JOIN anvil.benchmark_evaluation_requests q ON q.project_id=j.project_id AND q.job_id=j.id LEFT JOIN anvil.benchmark_evaluation_results r ON r.project_id=j.project_id AND r.job_id=j.id WHERE j.id=%s",
        (job,),
    )
    if row is None:
        raise HTTPException(404, "Evaluation job not found")
    expired = row["state"] == "leased" and row["lease_until"] <= datetime.now(timezone.utc)
    return {
        "job_id": str(row["id"]),
        "state": row["state"],
        "evaluation_state": "review_required" if expired else row["status"] or "pending",
        "safe_code": "lease_expired_no_retry" if expired else row["safe_code"],
        "scope": "fictional_local_software_only",
        "external_judge": "blocked",
    }


__all__ = ["calibration", "evaluate", "seal", "validate_report"]
