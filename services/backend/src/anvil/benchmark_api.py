"""SME archive receipts only; import is not qualification or execution authority."""

import io
import json
import os
import zipfile
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, Field, StrictBool
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from anvil import auth
from anvil import benchmark_evaluation as evaluation
from anvil import benchmark_execution as execution
from anvil import benchmark_pipeline as pipeline
from anvil import benchmark_reconciliation as reconciliation
from anvil import benchmark_results as results
from anvil import benchmark_scheduler as scheduler
from anvil.benchmark_archive import ArchiveError
from anvil.benchmark_ingest import inspect_original, intake_file, prepare_original, spool
from anvil.benchmark_protocol import ReviewPolicy
from anvil.benchmark_storage import bind_private, read_private_record, stage_private
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


class Freeze(Strict):
    expected_subject_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ProtocolSlot(Strict):
    connection_id: UUID
    transport: Literal["offline_contract"]
    configuration_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class FreezeProtocol(Strict):
    benchmark_revision_id: UUID
    expected_benchmark_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    slots: tuple[ProtocolSlot, ProtocolSlot, ProtocolSlot]
    expires_at: AwareDatetime
    review_policy: ReviewPolicy | None = None


class ExactSubject(Strict):
    expected_subject_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class CancelComparison(ExactSubject):
    rationale: str = Field(min_length=10, max_length=2000)


class ScoreReview(Strict):
    score_revision_id: UUID
    expected_projection_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    assignment_id: UUID
    decision: Literal["approved", "disputed", "changes_required", "adjudicated"]
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rationale: str = Field(min_length=10, max_length=2000)


class CriterionCorrection(Strict):
    cell_id: UUID
    criterion_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
    earned_points: str = Field(pattern=r"^(?:0|[1-9][0-9]{0,6})(?:\.[0-9]{1,8})?$")
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class CorrectScore(Strict):
    score_revision_id: UUID
    expected_projection_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    assignment_id: UUID
    corrections: list[CriterionCorrection] = Field(min_length=1, max_length=486)
    rationale: str = Field(min_length=10, max_length=2000)


class ResumeComparison(ExactSubject):
    expected_event_seq: int = Field(strict=True, ge=0)


class OperatorEvidence(Strict):
    evidence_text: str = Field(min_length=10, max_length=65536)


class ReconcileStopped(ResumeComparison):
    cell_id: UUID
    evidence_artifact_id: UUID
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    owned_actors_stopped_confirmed: StrictBool


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
        "SELECT r.id,r.exporter,r.bank_id,r.bank_version,r.archive_sha256,r.manifest_sha256,s.task_count,s.payload_count,s.source_classification,s.scoring_profile,s.source_owner,s.bank_title "
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
        "bank_title": row["bank_title"],
        "source_owner": row["source_owner"],
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
        "INSERT INTO anvil.benchmark_import_summaries(project_id,receipt_id,task_count,payload_count,source_classification,schema_version,scoring_profile,source_owner,bank_title) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            project,
            receipt,
            len(manifest.tasks),
            len(manifest.files),
            manifest.source.classification,
            manifest.schema_version,
            manifest.scoring.profile,
            manifest.source.owner,
            manifest.bank.title,
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

    @router.get("/library")
    def library(
        project: UUID,
        request: Request,
        cursor: UUID | None = None,
        limit: int = 50,
        after: UUID | None = None,
        q: str = "",
        classification: Literal[
            "original_synthetic_fixture", "partner_restricted", "public_licensed"
        ]
        | None = None,
    ):
        if not 1 <= limit <= 100:
            raise HTTPException(422, "Page size must be between 1 and 100")
        if len(q) > 100:
            raise HTTPException(422, "Search text exceeds 100 characters")
        _enabled()
        if cursor is not None and after is not None and cursor != after:
            raise HTTPException(422, "Use one consistent page cursor")
        cursor = cursor or after
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            pattern = "%" + q.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            receipts = c.execute(
                "SELECT id FROM anvil.benchmark_bundle_receipts WHERE (%s::uuid IS NULL OR id>%s::uuid) AND (%s='' OR bank_id ILIKE %s ESCAPE '!' OR exporter ILIKE %s ESCAPE '!') AND (%s::text IS NULL OR id IN (SELECT receipt_id FROM anvil.benchmark_import_summaries WHERE source_classification=%s)) ORDER BY id LIMIT %s",
                (cursor, cursor, q, pattern, pattern, classification, classification, limit + 1),
            ).fetchall()
            items = []
            for receipt in receipts[:limit]:
                item = _projection(c, receipt["id"])
                build = one(
                    c,
                    "SELECT id,subject_sha256 FROM anvil.benchmark_builds WHERE receipt_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
                    (receipt["id"],),
                )
                item["latest_build"] = (
                    {
                        "build_id": str(build["id"]),
                        "subject_sha256": build["subject_sha256"],
                        "state": "built",
                    }
                    if build
                    else None
                )
                items.append(item)
            return wrap(
                {
                    "items": items,
                    "next_cursor": str(receipts[limit - 1]["id"])
                    if len(receipts) > limit
                    else None,
                },
                request,
            )

    @router.get("/review-assignments")
    def review_assignments(project: UUID, request: Request):
        _enabled()
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            assignments = c.execute(
                "SELECT DISTINCT a.id,a.user_id,u.name user_name,a.expires_at FROM anvil.benchmark_private_assignments a JOIN anvil.memberships m ON m.project_id=a.project_id AND m.user_id=a.user_id AND m.active AND m.role IN ('admin','rl-engineer') JOIN anvil.users u ON u.id=m.user_id AND u.active WHERE a.scope='evaluation_review' AND a.artifact_id IS NULL AND a.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r WHERE r.assignment_id=a.id) ORDER BY a.id LIMIT 100"
            ).fetchall()
            return wrap(
                {
                    "items": [
                        {
                            "assignment_id": str(a["id"]),
                            "user_id": str(a["user_id"]),
                            "user_name": a["user_name"],
                            "expires_at": a["expires_at"].isoformat(),
                        }
                        for a in assignments
                    ]
                },
                request,
            )

    @router.get("/versions/{benchmark_revision_id}")
    def version(project: UUID, benchmark_revision_id: UUID, request: Request):
        _enabled()
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            return wrap(execution.version(c, benchmark_revision_id), request)

    @router.post("/builds/{build_id}/freeze")
    def freeze(project: UUID, build_id: UUID, body: Freeze, request: Request):
        preflight(project, request)
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            build = pipeline.record(c, "benchmark_builds", build_id)
        current = pipeline.readiness(project, user, build_id)
        if not current["software_qualified"]:
            raise HTTPException(409, "Current native qualification is required before freeze")
        try:
            _, _, parsed, _ = pipeline.source_snapshot(project, user, build["receipt_id"])
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(409, "Frozen source is unavailable or changed") from exc
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: execution.publish(
                        c,
                        project,
                        user,
                        build_id,
                        body.expected_subject_sha256,
                        parsed.parsed.manifest,
                    ),
                ),
                request,
            )

    @router.post("/protocols")
    def freeze_protocol(project: UUID, body: FreezeProtocol, request: Request):
        preflight(project, request)
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            try:
                result = idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: execution.freeze_protocol(c, project, user, body),
                )
            except ValueError as exc:
                raise HTTPException(
                    422, "Frozen benchmark protocol has inconsistent bindings"
                ) from exc
            return wrap(result, request)

    @router.get("/protocols/{protocol_revision_id}")
    def protocol(project: UUID, protocol_revision_id: UUID, request: Request):
        _enabled()
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            return wrap(execution.protocol(c, protocol_revision_id), request)

    @router.get("/protocols/{protocol_revision_id}/readiness")
    def protocol_readiness(project: UUID, protocol_revision_id: UUID, request: Request):
        _enabled()
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            projection, reasons = execution.protocol_gates(c, protocol_revision_id)
            current = execution.version(c, projection["protocol"]["benchmark_revision_id"])
        build_readiness = pipeline.readiness(project, user, current["build_id"])
        if not build_readiness["software_qualified"]:
            reasons.append("qualification_stale")
        if os.environ.get("ANVIL_BENCHMARK_OFFLINE_ENABLED") != "true":
            reasons.append("offline_operator_not_activated")
        return wrap(
            {
                "ready": not reasons,
                "subject_sha256": projection["subject_sha256"],
                "planned_cells": 18,
                "blockers": [
                    {
                        "code": code,
                        "layer": "execution",
                        "fixer": "admin",
                        "action": "Review exact execution prerequisites",
                    }
                    for code in sorted(set(reasons))
                ],
            },
            request,
        )

    @router.post("/protocols/{protocol_revision_id}/launch")
    def launch_comparison(
        project: UUID, protocol_revision_id: UUID, body: ExactSubject, request: Request
    ):
        preflight(project, request, admin=True)
        if os.environ.get("ANVIL_BENCHMARK_OFFLINE_ENABLED") != "true":
            raise HTTPException(409, "Offline native operator is not activated")
        with context(request, project) as (c, user, roles):
            projection, reasons = execution.protocol_gates(c, protocol_revision_id)
            current = execution.version(c, projection["protocol"]["benchmark_revision_id"])
        build_readiness = pipeline.readiness(project, user, current["build_id"])
        if reasons or not build_readiness["software_qualified"]:
            raise HTTPException(
                409, "Current source, model and native qualification gates are required"
            )
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            auth.require(roles, "admin")
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: execution.admit_offline(
                        c, project, user, protocol_revision_id, body.expected_subject_sha256
                    ),
                ),
                request,
            )

    @router.get("/comparisons/{run_id}")
    def comparison(project: UUID, run_id: UUID, request: Request):
        _enabled()
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            return wrap(execution.comparison(c, run_id), request)

    @router.get("/comparisons")
    def comparison_history(
        project: UUID, request: Request, after: UUID | None = None, limit: int = 25
    ):
        _enabled()
        if not 1 <= limit <= 100:
            raise HTTPException(422, "Page size must be between 1 and 100")
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            rows = c.execute(
                "SELECT b.run_id,b.protocol_revision_id,b.planned_cells,b.created_at FROM anvil.benchmark_comparisons b WHERE (%s::uuid IS NULL OR b.run_id>%s::uuid) ORDER BY b.run_id LIMIT %s",
                (after, after, limit + 1),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                status = execution.comparison(c, row["run_id"])
                items.append(
                    {
                        "run_id": str(row["run_id"]),
                        "protocol_revision_id": str(row["protocol_revision_id"]),
                        "state": status["state"],
                        "origin": status["origin"],
                        "planned_cells": row["planned_cells"],
                        "created_at": row["created_at"].isoformat(),
                    }
                )
            return wrap(
                {
                    "items": items,
                    "next_cursor": str(rows[limit - 1]["run_id"]) if len(rows) > limit else None,
                },
                request,
            )

    @router.get("/comparisons/{run_id}/events")
    def comparison_events(
        project: UUID, run_id: UUID, request: Request, after_event_seq: int = 0, limit: int = 50
    ):
        _enabled()
        if after_event_seq < 0 or not 1 <= limit <= 100:
            raise HTTPException(422, "Invalid event cursor or page size")
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            execution.comparison(c, run_id)
            events = c.execute(
                "SELECT e.event_seq,e.state,e.validity,e.reason_code,e.created_at,cell.id cell_id FROM anvil.benchmark_attempt_events e JOIN anvil.benchmark_cell_attempts a ON a.project_id=e.project_id AND a.id=e.attempt_id JOIN anvil.benchmark_cells cell ON cell.project_id=a.project_id AND cell.id=a.cell_id WHERE cell.run_id=%s AND e.event_seq>%s ORDER BY e.event_seq LIMIT %s",
                (run_id, after_event_seq, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": [
                        {
                            **event,
                            "cell_id": str(event["cell_id"]),
                            "created_at": event["created_at"].isoformat(),
                        }
                        for event in events[:limit]
                    ],
                    "next_event_seq": events[limit - 1]["event_seq"]
                    if len(events) > limit
                    else None,
                },
                request,
            )

    @router.post("/comparisons/{run_id}/cancel")
    def cancel_comparison(project: UUID, run_id: UUID, body: CancelComparison, request: Request):
        preflight(project, request)
        with context(request, project) as (c, user, roles):
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: execution.cancel(
                        c, project, user, run_id, body.expected_subject_sha256, body.rationale
                    ),
                ),
                request,
            )

    @router.post("/comparisons/{run_id}/reconcile-expired")
    def reconcile_expired(project: UUID, run_id: UUID, body: ExactSubject, request: Request):
        preflight(project, request, admin=True)
        with context(request, project) as (c, user, roles):

            def act():
                if (
                    execution.comparison(c, run_id)["subject_sha256"]
                    != body.expected_subject_sha256
                ):
                    raise HTTPException(409, "Exact comparison subject changed")
                return {
                    "expired": scheduler.expire(c, project, run_id),
                    "comparison": execution.comparison(c, run_id),
                }

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/comparisons/{run_id}/resume")
    def resume_comparison(project: UUID, run_id: UUID, body: ResumeComparison, request: Request):
        preflight(project, request, admin=True)
        if os.environ.get("ANVIL_BENCHMARK_OFFLINE_ENABLED") != "true":
            raise HTTPException(409, "Offline native operator is not activated")
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            auth.require(roles, "admin")
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: reconciliation.resume(c, project, user, run_id, body),
                ),
                request,
            )

    @router.post("/comparisons/{run_id}/operator-evidence")
    def operator_evidence(project: UUID, run_id: UUID, body: OperatorEvidence, request: Request):
        preflight(project, request, admin=True)
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            auth.require(roles, "admin")
            execution.comparison(c, run_id)
            if not one(
                c,
                "SELECT anvil.benchmark_private_access(%s,'benchmark_trace',%s) ok",
                (project, uid()),
            )["ok"]:
                raise HTTPException(403, "Current individual evaluation duty is required")
        data = json.dumps(
            {
                "profile": "offline-operator-evidence-v1",
                "run_id": str(run_id),
                "operator_id": str(user),
                "evidence_text": body.evidence_text,
            },
            sort_keys=True,
        ).encode()
        prepared = stage_private(project, data, "benchmark_trace", "application/json")
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            auth.require(roles, "admin")

            def act():
                execution.comparison(c, run_id)
                artifact = bind_private(c, prepared, created_by=user)
                return {
                    "evidence_artifact_id": str(artifact),
                    "evidence_sha256": prepared.sha256,
                    "kind": "human_operator_evidence_not_automatic_native_proof",
                }

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/comparisons/{run_id}/reconciliations")
    def reconcile_stopped(project: UUID, run_id: UUID, body: ReconcileStopped, request: Request):
        preflight(project, request, admin=True)
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            auth.require(roles, "admin")
            execution.comparison(c, run_id)
            evidence = pipeline.private_metadata(c, body.evidence_artifact_id)
            if (
                evidence["classification"] != "benchmark_trace"
                or evidence["sha256"] != body.evidence_sha256
                or evidence["byte_size"] > 300000
            ):
                raise HTTPException(403, "Exact scoped operator inspection evidence is required")
        try:
            proof = json.loads(read_private_record(evidence))
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(409, "Operator evidence is unavailable or changed") from exc
        if (
            not isinstance(proof, dict)
            or proof.get("profile") != "offline-operator-evidence-v1"
            or proof.get("run_id") != str(run_id)
            or proof.get("operator_id") != str(user)
        ):
            raise HTTPException(
                409, "Operator evidence must bind this exact run and inspecting person"
            )
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            auth.require(roles, "admin")
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: reconciliation.attest_stopped(c, project, user, run_id, body),
                ),
                request,
            )

    @router.get("/comparisons/{run_id}/results")
    def score_results(project: UUID, run_id: UUID, request: Request):
        _enabled()
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            return wrap(results.latest(c, run_id), request)

    @router.get("/comparisons/{run_id}/cells/{cell_id}/evidence")
    def cell_evidence(project: UUID, run_id: UUID, cell_id: UUID, request: Request):
        _enabled()
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            execution.comparison(c, run_id)
            execution.export_rights(c, run_id)
            cell = one(
                c,
                "SELECT a.id attempt_id,rt.output_artifact_id FROM anvil.benchmark_cells cell JOIN anvil.benchmark_cell_attempts a ON a.project_id=cell.project_id AND a.cell_id=cell.id AND a.attempt_no=1 JOIN anvil.benchmark_offline_runtime rt ON rt.project_id=a.project_id AND rt.attempt_id=a.id WHERE cell.run_id=%s AND cell.id=%s",
                (run_id, cell_id),
            )
            if cell is None or cell["output_artifact_id"] is None:
                raise HTTPException(409, "This cell has no captured output evidence")
            metadata = pipeline.private_metadata(c, cell["output_artifact_id"])
            if metadata["classification"] != "benchmark_sealed":
                raise HTTPException(409, "Invalid sealed output binding")
            criteria = c.execute(
                "SELECT cr.criterion_id,cr.earned_points,cr.possible_points,cr.output_sha256,cr.absence_event_id,cr.evidence_start,cr.evidence_end FROM anvil.benchmark_criterion_results cr JOIN anvil.benchmark_evaluator_calls ec ON ec.project_id=cr.project_id AND ec.id=cr.evaluator_call_id WHERE ec.attempt_id=%s AND ec.evaluation_revision=1 AND ec.purpose='deterministic' ORDER BY cr.criterion_id",
                (cell["attempt_id"],),
            ).fetchall()
        sealed = json.loads(read_private_record(metadata))
        evaluation.seal_checked(sealed)
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            execution.export_rights(c, run_id)
            pipeline.private_metadata(c, cell["output_artifact_id"])
            return wrap(
                {
                    "cell_id": str(cell_id),
                    "origin": "original_synthetic_fixture",
                    "criteria": [
                        {k: str(v) if v is not None else None for k, v in criterion.items()}
                        for criterion in criteria
                    ],
                    "outputs": sealed["files"],
                    "missing": sealed["missing"],
                },
                request,
            )

    @router.post("/comparisons/{run_id}/reviews")
    def review_score(project: UUID, run_id: UUID, body: ScoreReview, request: Request):
        preflight(project, request)
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            execution.export_rights(c, run_id)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: results.review(c, project, user, run_id, body),
                ),
                request,
            )

    @router.post("/comparisons/{run_id}/corrections")
    def correct_score(project: UUID, run_id: UUID, body: CorrectScore, request: Request):
        preflight(project, request)
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            execution.export_rights(c, run_id)
            try:
                result = idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: results.correct(c, project, user, run_id, body),
                )
            except ValueError as exc:
                raise HTTPException(422, "Correction points must be finite exact decimals") from exc
            return wrap(result, request)

    @router.get("/comparisons/{run_id}/exports/{format_}")
    def export_score(
        project: UUID,
        run_id: UUID,
        format_: str,
        request: Request,
        score_revision_id: UUID | None = None,
    ):
        _enabled()
        if format_ == "atif":
            with context(request, project) as (c, user, roles):
                _authorize(c, project, user, roles)
                execution.export_rights(c, run_id)
                stored = results.latest(c, run_id, score_revision_id)
                allowed = {
                    (item["task_revision_id"], model["slot"], item["repetition"])
                    for model in stored["projection"]["models"]
                    for item in model["diagnostic"]["included"]
                }
                reports = c.execute(
                    "SELECT cell.id cell_id,cell.task_revision_id,cell.slot,cell.repetition,rt.report_artifact_id FROM anvil.benchmark_cells cell JOIN anvil.benchmark_cell_attempts a ON a.project_id=cell.project_id AND a.cell_id=cell.id AND a.attempt_no=1 JOIN anvil.benchmark_offline_runtime rt ON rt.project_id=a.project_id AND rt.attempt_id=a.id WHERE cell.run_id=%s AND rt.report_artifact_id IS NOT NULL ORDER BY cell.id",
                    (run_id,),
                ).fetchall()
                reports = [
                    row
                    for row in reports
                    if (str(row["task_revision_id"]), row["slot"], row["repetition"]) in allowed
                ]
                metadata = [
                    (row, pipeline.private_metadata(c, row["report_artifact_id"]))
                    for row in reports
                ]
            if not metadata:
                raise HTTPException(409, "No captured validated trajectory is available")
            output = io.BytesIO()
            manifest = {
                "run_id": str(run_id),
                "score_revision_id": stored["score_revision_id"],
                "projection_sha256": stored["projection_sha256"],
                "origin": "original_synthetic_fixture",
                "cells": [],
            }
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for row, artifact in metadata:
                    report = json.loads(read_private_record(artifact))
                    if report.get("atif_validator") != "harbor-0.25.0" or "atif" not in report:
                        raise HTTPException(
                            409, "A captured trajectory lacks pinned Harbor validation"
                        )
                    data = json.dumps(
                        report["atif"],
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    ).encode()
                    name = str(row["cell_id"]) + ".json"
                    archive.writestr(name, data)
                    manifest["cells"].append(
                        {
                            "cell_id": str(row["cell_id"]),
                            "path": name,
                            "trajectory_sha256": digest(report["atif"]),
                        }
                    )
                archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
            with context(request, project) as (c, user, roles):
                _authorize(c, project, user, roles)
                execution.export_rights(c, run_id)
                for row, _ in metadata:
                    pipeline.private_metadata(c, row["report_artifact_id"])
                audit(
                    c,
                    project,
                    user,
                    "benchmark.score_exported",
                    run_id,
                    {"format": "atif", "score_revision_id": stored["score_revision_id"]},
                )
            return Response(
                output.getvalue(),
                media_type="application/zip",
                headers={
                    "Content-Disposition": 'attachment; filename="benchmark-trajectories.zip"',
                    "Cache-Control": "no-store",
                },
            )
        with context(request, project) as (c, user, roles):
            _authorize(c, project, user, roles)
            execution.export_rights(c, run_id)
            content, mime = results.export(c, run_id, format_, score_revision_id)
            audit(c, project, user, "benchmark.score_exported", run_id, {"format": format_})
        extension = "csv" if format_ == "csv" else "txt" if format_ == "report" else "json"
        return Response(
            content,
            media_type=mime,
            headers={
                "Content-Disposition": 'attachment; filename="benchmark-results.' + extension + '"',
                "Cache-Control": "no-store",
            },
        )

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
                c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
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
                c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
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
