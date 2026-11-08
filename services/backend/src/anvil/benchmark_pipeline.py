"""Durable fictional SME builds and qualification admission; never model execution."""

import hashlib
import io
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import rfc8785
from fastapi import HTTPException

from anvil import auth
from anvil.benchmark_archive import validate_archive
from anvil.benchmark_bundle import actor_view, parse_manifest
from anvil.benchmark_compiler import COMPILER_VERSION, FIXTURE_IMAGE, compile_task, fixture_binding
from anvil.benchmark_storage import (
    bind_private,
    read_private_record,
    stage_private,
    stage_private_stream,
    vault_root,
)
from anvil.benchmark_trust import load_trust_policy
from anvil.config import ROOT
from anvil.db import Jsonb, audit, one, transaction, uid

PROFILE = "local_fictional_qualification_only"
SOURCE_FILES = (
    "services/backend/src/anvil/benchmark_pipeline.py",
    "services/backend/src/anvil/benchmark_pipeline_worker.py",
    "services/backend/src/anvil/benchmark_compiler.py",
    "services/backend/src/anvil/benchmark_qualification.py",
    "services/backend/src/anvil/benchmark_archive.py",
    "services/backend/src/anvil/benchmark_bundle.py",
    "services/backend/src/anvil/benchmark_trust.py",
    "services/backend/src/anvil/benchmark_storage.py",
    "services/backend/src/anvil/import_sandbox.py",
    "services/backend/src/anvil/harbor_worker.py",
    "services/harbor/src/anvil_harbor/sme.py",
    "services/harbor/requirements.lock",
    "services/backend/uv.lock",
    "services/backend/src/anvil/benchmark_api.py",
    "services/backend/migrations/039_benchmark_private_foundation.sql",
    "services/backend/migrations/040_benchmark_private_guards.sql",
    "services/backend/migrations/041_benchmark_canonical_bindings.sql",
    "services/backend/migrations/042_benchmark_window_ownership.sql",
    "services/backend/migrations/043_benchmark_import_summaries.sql",
    "services/backend/migrations/044_benchmark_qualification_pipeline.sql",
    "services/backend/migrations/045_benchmark_qualification_capture_guards.sql",
    "services/backend/migrations/046_benchmark_capture_inputs.sql",
)


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def current_dependencies(signers, *, root=ROOT):
    root = Path(root)
    fixture = root / "fixtures/benchmark-bundle/fictional-points-v1"
    raw = (fixture / "manifest.json").read_bytes()
    manifest = parse_manifest(raw)
    if manifest.canonical_sha256 != fixture_binding().manifest_sha256:
        raise ValueError("Fictional fixture manifest changed")
    fixture_files = {"manifest.json": checksum(raw)}
    for member in manifest.manifest.files:
        path = fixture / member.path
        if not path.resolve().is_relative_to(fixture.resolve()) or path.is_symlink():
            raise ValueError("Fictional fixture member escaped source scope")
        data = path.read_bytes()
        if len(data) != member.byte_size or checksum(data) != member.sha256:
            raise ValueError("Fictional fixture payload changed")
        fixture_files[member.path] = member.sha256
    return {
        "profile": PROFILE,
        "compiler_version": COMPILER_VERSION,
        "image": FIXTURE_IMAGE,
        "harbor_version": "0.25.0",
        "sources": {path: checksum((root / path).read_bytes()) for path in SOURCE_FILES},
        "fixture_files": fixture_files,
        "trust_sha256": checksum(
            rfc8785.dumps(
                {
                    key: {
                        "public_key": signer.public_key.hex(),
                        "not_before": signer.not_before.isoformat(),
                        "not_after": signer.not_after.isoformat(),
                        "revoked": signer.revoked,
                    }
                    for key, signer in signers.items()
                }
            )
        ),
    }


def record(c, table, identifier):
    if table not in {
        "benchmark_bundle_receipts",
        "benchmark_source_reviews",
        "benchmark_builds",
        "benchmark_qualification_operations",
    }:
        raise ValueError("Unsupported benchmark record")
    row = one(c, f"SELECT * FROM anvil.{table} WHERE id=%s", (identifier,))
    if row is None:
        raise HTTPException(404, "Benchmark record not found")
    return row


def assigned(c, artifact):
    if not one(
        c,
        "SELECT anvil.benchmark_private_access(%s,'benchmark_raw',%s) AS allowed",
        (artifact["project_id"], artifact["id"]),
    )["allowed"]:
        raise HTTPException(403, "A current individual source-review assignment is required")


def private_metadata(c, identifier):
    row = one(c, "SELECT * FROM anvil.artifacts WHERE id=%s", (identifier,))
    if row is None:
        raise HTTPException(403, "A current individual private-source assignment is required")
    return row


def source_snapshot(project, user, receipt_id):
    with transaction(project, user) as c:
        auth.require(auth.project_roles(c, project, user), "rl-engineer", "admin")
        receipt = record(c, "benchmark_bundle_receipts", receipt_id)
        artifact = private_metadata(c, receipt["archive_artifact_id"])
        assigned(c, artifact)
    raw = read_private_record(artifact)
    signers = load_trust_policy()
    parsed = validate_archive(io.BytesIO(raw), signers=signers, now=datetime.now(timezone.utc))
    if (
        parsed.archive_sha256 != receipt["archive_sha256"]
        or parsed.parsed.canonical_sha256 != receipt["manifest_sha256"]
    ):
        raise ValueError("Source integrity changed")
    return receipt, raw, parsed, signers


def review_status(c, review, receipt_id):
    reasons = []
    if str(review["receipt_id"]) != str(receipt_id):
        raise HTTPException(409, "Review belongs to another source receipt")
    member = one(
        c,
        "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active AND m.role='admin'",
        (review["project_id"], review["reviewed_by"]),
    )
    if not member or review["expires_at"] <= datetime.now(timezone.utc):
        reasons.append("source_review_expired_or_inactive")
    for revoked in c.execute(
        "SELECT target FROM anvil.benchmark_review_revocations WHERE review_id=%s OR (target='evaluator' AND review_id IN (SELECT id FROM anvil.benchmark_source_reviews WHERE evaluator_binding_id=%s))",
        (review["id"], review["evaluator_binding_id"]),
    ).fetchall():
        reasons.append(
            "source_review_revoked"
            if revoked["target"] == "review"
            else "evaluator_binding_revoked"
        )
    binding = one(
        c,
        "SELECT * FROM anvil.benchmark_evaluator_bindings WHERE id=%s",
        (review["evaluator_binding_id"],),
    )
    expected = asdict(fixture_binding())
    if binding is None or any(
        binding[key] != expected[key]
        for key in (
            "registry_id",
            "version",
            "implementation_sha256",
            "image_digest",
            "policy_sha256",
        )
    ):
        reasons.append("evaluator_binding_changed")
    return reasons


def create_review(c, project, user, receipt_id, receipt, evidence, body):
    auth.require(auth.project_roles(c, project, user), "admin")
    if (
        receipt.signature.status != "verified"
        or receipt.parsed.canonical_sha256 != body.expected_manifest_sha256
    ):
        raise HTTPException(409, "A current verified exact source is required")
    binding = fixture_binding()
    if (
        receipt.parsed.canonical_sha256 != binding.manifest_sha256
        or body.expires_at <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            409, "Only the reviewed fictional source and current local rights scope are supported"
        )
    row = one(
        c,
        "SELECT id FROM anvil.benchmark_evaluator_bindings WHERE project_id=%s AND registry_id=%s AND version=%s AND implementation_sha256=%s AND image_digest=%s AND policy_sha256=%s",
        (
            project,
            binding.registry_id,
            binding.version,
            binding.implementation_sha256,
            binding.image_digest,
            binding.policy_sha256,
        ),
    )
    eid = str(row["id"]) if row else uid()
    if row is None:
        c.execute(
            "INSERT INTO anvil.benchmark_evaluator_bindings(id,project_id,registry_id,version,implementation_sha256,image_digest,policy_sha256,reviewed_by,review_evidence_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                eid,
                project,
                binding.registry_id,
                binding.version,
                binding.implementation_sha256,
                binding.image_digest,
                binding.policy_sha256,
                user,
                evidence["sha256"],
            ),
        )
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_source_reviews(id,project_id,receipt_id,evaluator_binding_id,manifest_sha256,evidence_artifact_id,reviewed_by,rights_confirmed,scope,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,true,%s,%s)",
        (
            identifier,
            project,
            receipt_id,
            eid,
            body.expected_manifest_sha256,
            evidence["id"],
            user,
            PROFILE,
            body.expires_at,
        ),
    )
    audit(
        c,
        project,
        user,
        "benchmark.source_reviewed",
        identifier,
        {"manifest_sha256": body.expected_manifest_sha256, "scope": PROFILE},
    )
    return {
        "review_id": identifier,
        "evaluator_binding_id": eid,
        "scope": PROFILE,
        "execution_authority": False,
    }


def prepare_build(project, user, receipt_id, body):
    receipt, raw, parsed, signers = source_snapshot(project, user, receipt_id)
    with transaction(project, user) as c:
        review = record(c, "benchmark_source_reviews", body.review_id)
        blockers = review_status(c, review, receipt_id)
    if (
        parsed.signature.status != "verified"
        or blockers
        or body.expected_manifest_sha256 != receipt["manifest_sha256"]
    ):
        raise HTTPException(409, "Current source trust, review and local rights are required")
    dependencies = current_dependencies(signers)
    subject = checksum(
        rfc8785.dumps(
            {
                "receipt_id": str(receipt_id),
                "review_id": str(body.review_id),
                "manifest_sha256": receipt["manifest_sha256"],
                "dependencies": dependencies,
            }
        )
    )
    with transaction(project, user) as c:
        old = one(
            c,
            "SELECT id FROM anvil.benchmark_builds WHERE receipt_id=%s AND subject_sha256=%s",
            (receipt_id, subject),
        )
        if old:
            return {"existing": str(old["id"])}
    prepared = []
    with tempfile.TemporaryDirectory(prefix=".compile-", dir=vault_root()) as directory:
        for task in parsed.parsed.manifest.tasks:
            path = Path(directory) / (task.id + ".zip")
            compiled = compile_task(
                io.BytesIO(raw),
                parsed,
                task.id,
                fixture_binding(),
                path,
                signers=signers,
                now=datetime.now(timezone.utc),
            )
            with path.open("rb") as stream:
                package = stage_private_stream(project, stream, "benchmark_eval", "application/zip")
            bindings = stage_private(
                project, rfc8785.dumps(compiled.bindings), "benchmark_eval", "application/json"
            )
            prepared.append((task, compiled, package, bindings))
    return {
        "receipt": receipt,
        "receipt_manifest": parsed.parsed.manifest,
        "review": review,
        "dependencies": dependencies,
        "subject": subject,
        "tasks": prepared,
    }


def bind_build(c, project, user, prepared):
    if "existing" in prepared:
        return build_public(c, prepared["existing"])
    receipt, review = prepared["receipt"], prepared["review"]
    if review_status(c, review, receipt["id"]):
        raise HTTPException(409, "Review changed while preparing the build")
    old = one(
        c,
        "SELECT id FROM anvil.benchmark_builds WHERE receipt_id=%s AND subject_sha256=%s",
        (receipt["id"], prepared["subject"]),
    )
    if old:
        return build_public(c, old["id"])
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_builds(id,project_id,receipt_id,review_id,subject_sha256,dependencies,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            receipt["id"],
            review["id"],
            prepared["subject"],
            Jsonb(prepared["dependencies"]),
            user,
        ),
    )
    for task, compiled, package, bindings in prepared["tasks"]:
        member = one(
            c,
            "SELECT source_id FROM anvil.benchmark_receipt_tasks WHERE receipt_id=%s AND task_id=%s",
            (receipt["id"], task.id),
        )
        sid = str(member["source_id"]) if member else uid()
        if member is None:
            actor = actor_view(prepared["receipt_manifest"], task.id)
            c.execute(
                "INSERT INTO anvil.praxis_sources(id,project_id,task_id,task_version,revision_id,source_sha256,source_artifact_id,actor_spec,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    sid,
                    project,
                    "sme:" + str(receipt["id"]) + ":" + task.id,
                    task.version,
                    task.revision,
                    receipt["manifest_sha256"],
                    receipt["archive_artifact_id"],
                    Jsonb(actor),
                    user,
                ),
            )
            c.execute(
                "INSERT INTO anvil.benchmark_receipt_tasks(project_id,receipt_id,task_id,task_version,source_id) VALUES(%s,%s,%s,%s,%s)",
                (project, receipt["id"], task.id, task.version, sid),
            )
        aid = bind_private(c, package, created_by=user)
        bid = bind_private(c, bindings, created_by=user)
        pid = uid()
        old_package = one(
            c,
            "SELECT id FROM anvil.harbor_packages WHERE source_id=%s AND package_sha256=%s",
            (sid, compiled.archive_sha256),
        )
        if old_package:
            pid = str(old_package["id"])
        else:
            c.execute(
                "INSERT INTO anvil.harbor_packages(id,project_id,source_id,package_sha256,package_artifact_id,manifest,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    pid,
                    project,
                    sid,
                    compiled.archive_sha256,
                    aid,
                    Jsonb(
                        {
                            "binding": "sme-artifact-v1",
                            "compiler_version": COMPILER_VERSION,
                            "harbor_version": "0.25.0",
                            "task_id": task.id,
                            "scope": PROFILE,
                        }
                    ),
                    user,
                ),
            )
        c.execute(
            "INSERT INTO anvil.benchmark_build_tasks(project_id,build_id,receipt_id,task_id,source_id,package_id,binding_sha256,bindings_artifact_id,environment_digest,tool_schema_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                project,
                identifier,
                receipt["id"],
                task.id,
                sid,
                pid,
                compiled.binding_sha256,
                bid,
                compiled.bindings["environment"]["oci_manifest_digest"],
                checksum(rfc8785.dumps(compiled.bindings["tools"])),
            ),
        )
    audit(
        c,
        project,
        user,
        "benchmark.build_recorded",
        identifier,
        {"subject_sha256": prepared["subject"], "scope": PROFILE},
    )
    return build_public(c, identifier)


def build_public(c, identifier):
    build = record(c, "benchmark_builds", identifier)
    review = record(c, "benchmark_source_reviews", build["review_id"])
    packages = c.execute(
        "SELECT t.task_id,t.package_id,p.package_sha256,t.binding_sha256 FROM anvil.benchmark_build_tasks t JOIN anvil.harbor_packages p ON p.project_id=t.project_id AND p.id=t.package_id WHERE t.build_id=%s ORDER BY t.task_id",
        (identifier,),
    ).fetchall()
    return {
        "build_id": str(build["id"]),
        "receipt_id": str(build["receipt_id"]),
        "review_id": str(build["review_id"]),
        "evaluator_binding_id": str(review["evaluator_binding_id"]),
        "subject_sha256": build["subject_sha256"],
        "state": "built",
        "packages": [{key: str(value) for key, value in p.items()} for p in packages],
        "scope": PROFILE,
        "execution_ready": False,
    }


def policy_status(project, user, build_id):
    with transaction(project, user) as c:
        build = record(c, "benchmark_builds", build_id)
        review = record(c, "benchmark_source_reviews", build["review_id"])
        reasons = review_status(c, review, build["receipt_id"])
        if not one(
            c,
            "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active",
            (project, build["created_by"]),
        ):
            reasons.append("build_author_inactive")
    if os.environ.get("ANVIL_BENCHMARK_ENABLED") != "true":
        reasons.append("benchmark_disabled")
    try:
        _, _, parsed, signers = source_snapshot(project, user, build["receipt_id"])
        if parsed.signature.status != "verified":
            reasons.append("source_trust_not_current")
        if current_dependencies(signers) != build["dependencies"]:
            reasons.append("qualification_inputs_changed")
    except (ValueError, RuntimeError, OSError, HTTPException):
        reasons.append("source_access_or_integrity_unavailable")
    return build, sorted(set(reasons))


def readiness(project, user, build_id):
    build, reasons = policy_status(project, user, build_id)
    with transaction(project, user) as c:
        latest = one(
            c,
            "SELECT * FROM anvil.benchmark_qualification_operations WHERE build_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
            (build_id,),
        )
        count = one(
            c,
            "SELECT count(*) AS n FROM anvil.benchmark_operation_results r JOIN anvil.benchmark_qualifications q ON q.project_id=r.project_id AND q.id=r.qualification_id WHERE r.operation_id=%s AND q.outcome='passed' AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_qualification_events e WHERE e.qualification_id=q.id)",
            (latest["id"] if latest else None,),
        )["n"]
        expected = one(
            c,
            "SELECT count(*) AS n FROM anvil.benchmark_build_tasks WHERE build_id=%s",
            (build_id,),
        )["n"]
    qualified = not reasons and bool(
        latest and latest["state"] == "passed" and count == expected and expected > 0
    )
    state = (
        "stale"
        if reasons and latest and latest["state"] == "passed"
        else "blocked"
        if reasons
        else "qualified"
        if qualified
        else latest["state"]
        if latest
        else "built"
    )
    blockers = reasons + ([] if qualified else ["qualification_missing"])
    blockers.append("protocol_required")
    return {
        "build_id": str(build_id),
        "subject_sha256": build["subject_sha256"],
        "state": state,
        "software_qualified": qualified,
        "ready": False,
        "execution_admission": "separate_frozen_protocol",
        "scope": PROFILE,
        "blockers": [
            {
                "code": code,
                "layer": "qualification",
                "fixer": "admin",
                "action": "Review current source, local rights and qualification inputs",
            }
            for code in blockers
        ],
    }


def operation_public(c, identifier):
    op = record(c, "benchmark_qualification_operations", identifier)
    refs = c.execute(
        "SELECT task_id,qualification_id FROM anvil.benchmark_operation_results WHERE operation_id=%s ORDER BY task_id",
        (identifier,),
    ).fetchall()
    return {
        "operation_id": str(op["id"]),
        "build_id": str(op["build_id"]),
        "state": op["state"],
        "code": op["safe_code"],
        "qualifications": [
            {"task_id": r["task_id"], "qualification_id": str(r["qualification_id"])} for r in refs
        ],
        "scope": PROFILE,
        "model_performance": False,
    }


def enqueue(c, project, user, build_id, subject):
    build = record(c, "benchmark_builds", build_id)
    if build["subject_sha256"] != subject:
        raise HTTPException(409, "Qualification must bind the exact current subject")
    review = record(c, "benchmark_source_reviews", build["review_id"])
    if review_status(c, review, build["receipt_id"]):
        raise HTTPException(409, "Review is no longer current")
    active = one(
        c,
        "SELECT id FROM anvil.benchmark_qualification_operations WHERE build_id=%s AND state IN ('queued','running','execution_unknown')",
        (build_id,),
    )
    if active:
        raise HTTPException(409, "An active or unknown qualification already owns this build")
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_qualification_operations(id,project_id,build_id,created_by,state) VALUES(%s,%s,%s,%s,'queued')",
        (identifier, project, build_id, user),
    )
    audit(
        c,
        project,
        user,
        "benchmark.qualification_queued",
        identifier,
        {"subject_sha256": subject, "scope": PROFILE},
    )
    return operation_public(c, identifier)


def claim(project, operation_id, user, *, lease_seconds=1800):
    if type(lease_seconds) is not int or not 1 <= lease_seconds <= 1800:
        raise ValueError("Qualification lease must be 1–1800 seconds")
    with transaction(project, user) as c:
        auth.require(auth.project_roles(c, project, user), "admin")
        op = record(c, "benchmark_qualification_operations", operation_id)
        if str(op["created_by"]) != str(user):
            raise HTTPException(403, "Qualification operator must match the initiating Admin")
    _, blockers = policy_status(project, op["created_by"], op["build_id"])
    if blockers:
        with transaction(project, op["created_by"]) as c:
            c.execute(
                "UPDATE anvil.benchmark_qualification_operations SET state='blocked',finished_at=now(),safe_code='qualification_policy_blocked' WHERE id=%s AND state='queued'",
                (operation_id,),
            )
        return None
    with transaction(project, op["created_by"]) as c:
        c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
        return one(
            c,
            "UPDATE anvil.benchmark_qualification_operations SET state='running',fence=gen_random_uuid(),lease_until=now()+(%s*interval '1 second'),safe_code='qualification_running' WHERE id=%s AND state='queued' RETURNING *",
            (lease_seconds, operation_id),
        )


def expire_claim(project, operation_id, user):
    with transaction(project, user) as c:
        row = one(
            c,
            "UPDATE anvil.benchmark_qualification_operations SET state='execution_unknown',finished_at=now(),safe_code='qualification_lease_expired_no_retry' WHERE id=%s AND state='running' AND lease_until<=now() RETURNING id",
            (operation_id,),
        )
        return row is not None


def process_operation(project, operation_id, user):
    # Keep the Docker-host entrypoint out of API initialization and break worker imports.
    from anvil.benchmark_pipeline_worker import process_operation as process

    return process(project, operation_id, user)
