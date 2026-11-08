"""SME archive receipts only; import is not qualification or execution authority."""

import os
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, Field, StrictBool
from starlette.concurrency import run_in_threadpool

from anvil import auth
from anvil import benchmark_evaluation as evaluation
from anvil import benchmark_pipeline as pipeline
from anvil.benchmark_archive import ArchiveError
from anvil.benchmark_ingest import inspect_original, intake_file, prepare_original, spool
from anvil.benchmark_storage import bind_private, read_private_record
from anvil.db import audit, digest, one, uid
from anvil.schemas import Strict


class SourceReview(Strict):
    expected_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_artifact_id: UUID
    rights_confirmed: StrictBool
    expires_at: AwareDatetime


class Build(Strict):
    expected_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_id: UUID


class Qualify(Strict):
    expected_subject_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Revoke(Strict):
    rationale: str = Field(min_length=10, max_length=2000)
    target: Literal["review", "evaluator"]


class EvaluatorReview(Strict):
    policy_artifact_id: UUID
    evidence_artifact_id: UUID
    expires_at: AwareDatetime


class Evaluate(Strict):
    registry_id: UUID
    sealed_output_artifact_id: UUID


def _enabled():
    if os.environ.get("ANVIL_BENCHMARK_ENABLED") != "true":
        raise HTTPException(503, "Benchmark intake is disabled for this installation")


def _authorize(c, project, user, roles, *, upload=False):
    auth.require(roles, "rl-engineer", "admin")
    if upload:
        allowed = one(
            c,
            "SELECT anvil.benchmark_private_access(%s,'benchmark_raw',%s) AS allowed",
            (project, uid()),
        )
        if not allowed["allowed"]:
            raise HTTPException(403, "A current individual source-review assignment is required")


def _projection(c, receipt_id):
    row = one(
        c,
        "SELECT r.id,r.exporter,r.bank_id,r.bank_version,r.archive_sha256,r.manifest_sha256,s.task_count,s.payload_count,s.source_classification,s.scoring_profile "
        "FROM anvil.benchmark_bundle_receipts r JOIN anvil.benchmark_import_summaries s ON s.project_id=r.project_id AND s.receipt_id=r.id WHERE r.id=%s",
        (receipt_id,),
    )
    if row is None:
        raise HTTPException(404, "Benchmark receipt not found")
    event = one(
        c,
        "SELECT id,source_state,signature_status,safe_code FROM anvil.benchmark_receipt_events WHERE receipt_id=%s ORDER BY event_seq DESC LIMIT 1",
        (receipt_id,),
    )
    if event is None:
        raise HTTPException(409, "Benchmark receipt validation is incomplete")
    return {
        "receipt_id": str(row["id"]),
        "exporter": row["exporter"],
        "bank_id": row["bank_id"],
        "bank_version": row["bank_version"],
        "archive_sha256": row["archive_sha256"],
        "manifest_sha256": row["manifest_sha256"],
        "source_state": event["source_state"],
        "signature_status": event["signature_status"],
        "task_count": row["task_count"],
        "payload_count": row["payload_count"],
        "source_classification": row["source_classification"],
        "scoring_profile": row["scoring_profile"],
        "validation_event_id": str(event["id"]),
    }


def _record(c, project, user, prepared, result, raw_manifest, canonical):
    manifest = result.parsed.manifest
    previous = one(
        c,
        "SELECT id,archive_sha256 FROM anvil.benchmark_bundle_receipts WHERE project_id=%s AND exporter=%s AND bank_id=%s AND bank_version=%s",
        (project, manifest.exporter.identity, manifest.bank.id, manifest.bank.version),
    )
    if previous:
        if previous["archive_sha256"] != prepared.sha256:
            raise HTTPException(
                409,
                "Immutable bank version has different original bytes; upload a successor version",
            )
        return _projection(c, previous["id"])
    archive_id = bind_private(c, prepared, created_by=user)
    raw_id = bind_private(c, raw_manifest, created_by=user)
    canonical_id = bind_private(c, canonical, created_by=user)
    receipt, event = uid(), uid()
    c.execute(
        "INSERT INTO anvil.benchmark_bundle_receipts(id,project_id,exporter,bank_id,bank_version,archive_artifact_id,archive_sha256,manifest_sha256,raw_manifest_artifact_id,canonical_manifest_artifact_id,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            receipt,
            project,
            manifest.exporter.identity,
            manifest.bank.id,
            manifest.bank.version,
            archive_id,
            prepared.sha256,
            result.parsed.canonical_sha256,
            raw_id,
            canonical_id,
            user,
        ),
    )
    c.execute(
        "INSERT INTO anvil.benchmark_import_summaries(project_id,receipt_id,task_count,payload_count,source_classification,schema_version,scoring_profile) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (
            project,
            receipt,
            len(manifest.tasks),
            len(manifest.files),
            manifest.source.classification,
            manifest.schema_version,
            manifest.scoring.profile,
        ),
    )
    signature = result.signature.status.removeprefix("quarantined_")
    state = "accepted" if signature == "verified" else "quarantined"
    code = "source_verified" if signature == "verified" else "source_" + signature
    c.execute(
        "INSERT INTO anvil.benchmark_receipt_events(id,project_id,receipt_id,source_state,signature_status,safe_code,subject_sha256,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (event, project, receipt, state, signature, code, result.parsed.canonical_sha256, user),
    )
    audit(
        c,
        project,
        user,
        "benchmark.import.recorded",
        receipt,
        {"archive_sha256": prepared.sha256, "source_state": state, "signature_status": signature},
    )
    return _projection(c, receipt)


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/benchmarks")

    def reject_original(project, request, prepared, code):
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles, upload=True)
            c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
            artifact = bind_private(c, prepared, created_by=user)
            audit(
                c,
                project,
                user,
                "benchmark.import.rejected",
                artifact,
                {"code": code, "archive_sha256": prepared.sha256},
            )

    @router.post(
        "/imports",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/gzip": {"schema": {"type": "string", "format": "binary"}},
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
                },
            }
        },
    )
    async def ingest(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles, upload=True)
        _enabled()
        key = request.headers.get("idempotency-key")
        if not key or len(key) > 200:
            raise HTTPException(428, "Idempotency-Key required (maximum 200 characters)")
        if request.headers.get("content-type", "").split(";", 1)[0] not in {
            "application/gzip",
            "application/octet-stream",
        }:
            raise HTTPException(422, "Benchmark intake requires a raw gzip archive")
        try:
            with intake_file(project) as temporary:
                await spool(request, temporary)
                prepared = await run_in_threadpool(prepare_original, project, temporary)
                with context(request, project) as (c, user, roles):
                    _authorize(c, project, user, roles, upload=True)
                    old = one(
                        c,
                        "SELECT body_hash FROM anvil.idempotency WHERE project_id=%s AND user_id=%s AND route=%s AND key=%s",
                        (project, user, request.url.path, key),
                    )
                body = {"archive_sha256": prepared.sha256}
                if old and old["body_hash"] != digest(body):
                    reject_original(project, request, prepared, "idempotency_conflict")
                    raise HTTPException(409, "Idempotency key reused with changed original bytes")
                try:
                    result, raw, canonical = await run_in_threadpool(
                        inspect_original,
                        project,
                        temporary,
                        now=datetime.now(timezone.utc),
                        expected_sha256=prepared.sha256,
                    )
                except ArchiveError as exc:
                    reject_original(project, request, prepared, exc.code)
                    raise HTTPException(
                        exc.status, "Benchmark archive rejected: " + exc.code
                    ) from exc
                try:
                    with context(request, project) as (c, user, roles):
                        _authorize(c, project, user, roles, upload=True)
                        response = idempotent(
                            c,
                            project,
                            user,
                            request,
                            body,
                            lambda: _record(c, project, user, prepared, result, raw, canonical),
                        )
                except HTTPException as exc:
                    if exc.status_code == 409:
                        reject_original(project, request, prepared, "immutable_version_conflict")
                    raise
                return wrap(response, request)
        except RuntimeError as exc:
            raise HTTPException(
                503, "Benchmark private intake configuration is unavailable"
            ) from exc

    @router.get("/imports/{receipt_id}")
    def receipt(project: UUID, receipt_id: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            return wrap(_projection(c, receipt_id), request)

    @router.get("/imports/{receipt_id}/errors")
    def errors(project: UUID, receipt_id: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            result = _projection(c, receipt_id)
            rows = c.execute(
                "SELECT safe_code FROM anvil.benchmark_receipt_events WHERE receipt_id=%s AND source_state='quarantined' ORDER BY event_seq DESC LIMIT 50",
                (receipt_id,),
            ).fetchall()
            return wrap(
                {
                    "receipt_id": result["receipt_id"],
                    "errors": [
                        {
                            "code": row["safe_code"],
                            "layer": "source",
                            "fixer": "admin",
                            "action": "Review source signature and upload a properly signed successor if required",
                        }
                        for row in rows
                    ],
                },
                request,
            )

    def preflight(project, request, *, admin=False):
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            if admin:
                auth.require(roles, "admin")
        _enabled()
        key = request.headers.get("idempotency-key")
        if not key or len(key) > 200:
            raise HTTPException(428, "Idempotency-Key required (maximum 200 characters)")
        return user

    @router.post("/imports/{receipt_id}/reviews")
    def review_source(project: UUID, receipt_id: UUID, body: SourceReview, request: Request):
        user = preflight(project, request, admin=True)
        if not body.rights_confirmed:
            raise HTTPException(422, "Explicit local fictional rights confirmation is required")
        _, _, parsed, _ = pipeline.source_snapshot(project, user, receipt_id)
        with context(request, project) as (c, user, roles):
            evidence = pipeline.private_metadata(c, body.evidence_artifact_id)
        read_private_record(evidence)
        with context(request, project) as (c, user, roles):
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: pipeline.create_review(
                        c, project, user, receipt_id, parsed, evidence, body
                    ),
                ),
                request,
            )

    @router.post("/reviews/{review_id}/revoke")
    def revoke_review(project: UUID, review_id: UUID, body: Revoke, request: Request):
        preflight(project, request, admin=True)
        with context(request, project) as (c, user, roles):

            def act():
                pipeline.record(c, "benchmark_source_reviews", review_id)
                c.execute(
                    "INSERT INTO anvil.benchmark_review_revocations(id,project_id,review_id,target,actor_id,rationale) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(project_id,review_id,target) DO NOTHING",
                    (uid(), project, review_id, body.target, user, body.rationale),
                )
                audit(
                    c, project, user, "benchmark.review_revoked", review_id, {"target": body.target}
                )
                return {"review_id": str(review_id), "target": body.target, "revoked": True}

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/imports/{receipt_id}/build")
    def build(project: UUID, receipt_id: UUID, body: Build, request: Request):
        user = preflight(project, request)
        try:
            prepared = pipeline.prepare_build(project, user, receipt_id, body)
        except (RuntimeError, OSError, ValueError) as exc:
            raise HTTPException(
                409, "Benchmark build prerequisites are unavailable or changed"
            ) from exc
        with context(request, project) as (c, user, roles):
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: pipeline.bind_build(c, project, user, prepared),
                ),
                request,
            )

    @router.get("/builds/{build_id}/readiness")
    def build_readiness(project: UUID, build_id: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            pipeline.record(c, "benchmark_builds", build_id)
        return wrap(pipeline.readiness(project, user, build_id), request)

    @router.post("/builds/{build_id}/qualify", status_code=202)
    def qualify(project: UUID, build_id: UUID, body: Qualify, request: Request):
        user = preflight(project, request, admin=True)
        _, blockers = pipeline.policy_status(project, user, build_id)
        if blockers:
            raise HTTPException(
                409, "Current source, review, assignment and build inputs are required"
            )
        with context(request, project) as (c, user, roles):
            if not one(
                c,
                "SELECT anvil.benchmark_private_access(%s,'benchmark_trace',%s) AS allowed",
                (project, uid()),
            )["allowed"]:
                raise HTTPException(
                    403, "A current individual evaluation-review assignment is required"
                )
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: pipeline.enqueue(
                        c, project, user, build_id, body.expected_subject_sha256
                    ),
                ),
                request,
            )

    @router.get("/qualification-operations/{operation_id}")
    def qualification_status(project: UUID, operation_id: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            return wrap(pipeline.operation_public(c, operation_id), request)

    @router.post("/qualification-operations/{operation_id}/cancel")
    def cancel_qualification(project: UUID, operation_id: UUID, request: Request):
        preflight(project, request, admin=True)
        with context(request, project) as (c, user, roles):

            def act():
                operation = pipeline.record(c, "benchmark_qualification_operations", operation_id)
                if operation["state"] in {"queued", "running"}:
                    c.execute(
                        "UPDATE anvil.benchmark_qualification_operations SET state=CASE WHEN state='queued' THEN 'cancelled' ELSE 'execution_unknown' END,finished_at=now(),safe_code='qualification_cancelled_no_retry' WHERE id=%s",
                        (operation_id,),
                    )
                    audit(c, project, user, "benchmark.qualification_cancelled", operation_id)
                return pipeline.operation_public(c, operation_id)

            return wrap(idempotent(c, project, user, request, {}, act), request)

    def evaluator_enabled():
        _enabled()
        if os.environ.get("ANVIL_BENCHMARK_EVALUATION_ENABLED") != "true":
            raise HTTPException(503, "Separate benchmark evaluation is disabled")

    @router.post("/evaluators/reviews")
    def evaluator_review(project: UUID, body: EvaluatorReview, request: Request):
        user = preflight(project, request, admin=True)
        evaluator_enabled()
        try:
            prepared = evaluation.prepare_review(
                project, user, body.policy_artifact_id, body.evidence_artifact_id
            )
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(409, "Evaluator review inputs unavailable or invalid") from exc
        with context(request, project) as (c, user, roles):
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: evaluation.register(c, project, user, prepared, body.expires_at),
                ),
                request,
            )

    @router.post("/evaluators/reviews/{registry_id}/revoke")
    def revoke_evaluator(project: UUID, registry_id: UUID, body: Revoke, request: Request):
        preflight(project, request, admin=True)
        with context(request, project) as (c, user, roles):

            def act():
                if not one(
                    c,
                    "SELECT id FROM anvil.benchmark_evaluator_registrations WHERE id=%s",
                    (registry_id,),
                ):
                    raise HTTPException(404, "Evaluator registry not found")
                c.execute(
                    "INSERT INTO anvil.benchmark_evaluator_registry_revocations(project_id,registry_id,revoked_by,rationale) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (project, registry_id, user, body.rationale),
                )
                audit(c, project, user, "benchmark.evaluator_revoked", registry_id)
                return {"registry_id": str(registry_id), "revoked": True}

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/evaluations", status_code=202)
    def evaluate_output(project: UUID, body: Evaluate, request: Request):
        user = preflight(project, request)
        evaluator_enabled()
        try:
            prepared = evaluation.prepare_evaluation(
                project, user, body.registry_id, body.sealed_output_artifact_id
            )
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(409, "Sealed evaluation inputs unavailable or invalid") from exc
        with context(request, project) as (c, user, roles):
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: evaluation.enqueue(
                        c, project, user, prepared, request.headers["idempotency-key"]
                    ),
                ),
                request,
            )

    @router.get("/evaluations/{job_id}")
    def evaluation_status(project: UUID, job_id: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            return wrap(evaluation.projection(c, job_id), request)

    @router.post("/evaluations/{job_id}/cancel")
    def cancel_evaluation(project: UUID, job_id: UUID, request: Request):
        preflight(project, request, admin=True)
        with context(request, project) as (c, user, roles):

            def act():
                evaluation.projection(c, job_id)
                c.execute("SELECT anvil.cancel_benchmark_evaluation(%s,%s)", (project, job_id))
                audit(c, project, user, "benchmark.evaluation_cancelled", job_id)
                return evaluation.projection(c, job_id)

            return wrap(idempotent(c, project, user, request, {}, act), request)

    return router
