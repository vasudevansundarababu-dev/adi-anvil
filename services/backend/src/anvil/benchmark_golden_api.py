"""Project-scoped human golden curation; no reads or intents dispatch a model."""

import os
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from anvil import auth
from anvil import benchmark_golden as golden
from anvil import benchmark_pipeline as pipeline
from anvil.db import one
from anvil.schemas import Strict


class Archive(Strict):
    rationale: str = Field(min_length=10, max_length=2000)


def _authorize(roles):
    if os.environ.get("ANVIL_BENCHMARK_ENABLED") != "true":
        raise HTTPException(503, "Benchmark workbench is disabled")
    auth.require(roles, "admin", "rl-engineer")


def _policy(project, user, build_id):
    if build_id is not None:
        _, blockers = pipeline.policy_status(project, user, build_id)
        if blockers:
            raise HTTPException(409, "Current source rights, integrity and review are required")


def _historical(c, project, user, trace_id):
    if trace_id is None:
        return
    # The dashboard owns historical record validation; never accept arbitrary IDs.
    from anvil import benchmark_dashboard

    resolver = getattr(benchmark_dashboard, "resolve_anchor", None)
    if resolver is None:
        raise HTTPException(409, "Historical trace binding is unavailable")
    resolved = resolver(c, trace_id, project, user)
    if resolved.get("kind") != "historical_control":
        raise HTTPException(409, "Use the exact run and cell for comparison trace anchors")


def _matches(c, content, request, created_at=None):
    from anvil import benchmark_dashboard

    selected = getattr(request.state, "golden_dashboard_context", None)
    if selected is None:
        selected = benchmark_dashboard.query(request)
        request.state.golden_dashboard_context = selected
    return benchmark_dashboard.matches_case_context(c, content, selected, created_at=created_at)


def _permissions(c, user, row):
    blockers = []
    if row["created_by"] == user:
        blockers.append("distinct_human_verifier_required")
    if row["source_build_id"] is None:
        blockers.append("current_source_binding_required")
    if row["content"].get("source_trace_id") is not None:
        blockers.append("historical_control_not_current_source_authority")
    if row["verification"] is not None:
        blockers.append("immutable_decision_already_exists")
    if not one(
        c,
        "SELECT 1 FROM anvil.benchmark_private_assignments a WHERE user_id=%s AND scope='evaluation_review' AND artifact_id IS NULL AND expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r WHERE r.assignment_id=a.id)",
        (user,),
    ):
        blockers.append("current_individual_evaluation_duty_required")
    return row | {"permissions": {"can_verify": not blockers, "verification_blockers": blockers}}


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/benchmarks")

    def body_source(project, request, body):
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            _historical(c, project, user, body.source_trace_id)
            build_id, _ = golden.resolve_source(
                c, body.source_build_id, body.source_anchor, body.fictional_task_id
            )
        _policy(project, user, build_id)
        return build_id

    def checked_version(project, request, identifier, *, enforce_context=True):
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            row = _permissions(c, user, golden.version(c, identifier))
            _historical(c, project, user, row["content"].get("source_trace_id"))
            if enforce_context and not _matches(c, row["content"], request, row["created_at"]):
                raise HTTPException(404, "Golden case is outside the selected dashboard context")
        _policy(project, user, row["source_build_id"])
        return row

    @router.get("/golden-datasets")
    def datasets(project: UUID, request: Request, limit: int = 50, after: UUID | None = None):
        if not 1 <= limit <= 100:
            raise HTTPException(422, "Page size must be between1 and100")
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            rows = c.execute(
                "SELECT id FROM anvil.benchmark_golden_datasets WHERE (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
                (after, after, limit + 1),
            ).fetchall()
            items = [golden.dataset(c, row["id"]) for row in rows[:limit]]
            return wrap(
                {
                    "items": items,
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                },
                request,
            )

    @router.post("/golden-datasets", status_code=201)
    def create_dataset(project: UUID, body: golden.Dataset, request: Request):
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: golden.create_dataset(c, project, user, body),
                ),
                request,
            )

    @router.get("/golden-datasets/{dataset_id}")
    def dataset(project: UUID, dataset_id: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            return wrap(golden.dataset(c, dataset_id), request)

    @router.post("/golden-datasets/{dataset_id}/archive")
    def archive(project: UUID, dataset_id: UUID, body: Archive, request: Request):
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            row = golden.dataset(c, dataset_id)
            if row["created_by"] != user and "admin" not in roles:
                raise HTTPException(403, "Only the dataset author or Admin may archive it")
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: golden.archive(c, project, user, dataset_id, body.rationale),
                ),
                request,
            )

    @router.get("/golden-datasets/{dataset_id}/versions")
    def versions(
        project: UUID,
        dataset_id: UUID,
        request: Request,
        limit: int = 50,
        after: UUID | None = None,
    ):
        if not 1 <= limit <= 100:
            raise HTTPException(422, "Page size must be between1 and100")
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            golden.dataset(c, dataset_id)
            rows = c.execute(
                "SELECT id,content-'input_text'-'expected_output' content,created_at FROM anvil.benchmark_golden_versions WHERE dataset_id=%s AND (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT 501",
                (dataset_id, after, after),
            ).fetchall()
            if len(rows) > 500:
                raise HTTPException(
                    409, "Golden context scan exceeds500 versions; narrow the dataset or cursor"
                )
            rows = [row for row in rows if _matches(c, row["content"], request, row["created_at"])]
        items = [checked_version(project, request, row["id"]) for row in rows[:limit]]
        return wrap(
            {
                "items": items,
                "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                "visibility": "Only versions currently readable by this person and source rights are included.",
            },
            request,
        )

    @router.post("/golden-datasets/{dataset_id}/versions", status_code=201)
    def create_version(project: UUID, dataset_id: UUID, body: golden.CaseVersion, request: Request):
        build_id = body_source(project, request, body)
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            result = idempotent(
                c,
                project,
                user,
                request,
                body,
                lambda: golden.create_version(c, project, user, dataset_id, body),
            )
        _policy(project, user, build_id)
        return wrap(checked_version(project, request, result["id"], enforce_context=False), request)

    @router.get("/golden-versions/{version_id}")
    def version(project: UUID, version_id: UUID, request: Request):
        return wrap(checked_version(project, request, version_id), request)

    @router.post("/golden-versions/{version_id}/verification")
    def verification(project: UUID, version_id: UUID, body: golden.Verification, request: Request):
        row = checked_version(project, request, version_id, enforce_context=False)
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            idempotent(
                c,
                project,
                user,
                request,
                body,
                lambda: golden.verify(c, project, user, version_id, body),
            )
        _policy(project, user, row["source_build_id"])
        return wrap(checked_version(project, request, version_id, enforce_context=False), request)

    @router.get("/remediation")
    def proposals(project: UUID, request: Request, limit: int = 50, after: UUID | None = None):
        if not 1 <= limit <= 100:
            raise HTTPException(422, "Page size must be between1 and100")
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            rows = c.execute(
                "SELECT id,content-'proposed_prompt'-'rationale'-'title' content,created_at FROM anvil.benchmark_remediation_proposals WHERE (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT 501",
                (after, after),
            ).fetchall()
            if len(rows) > 500:
                raise HTTPException(
                    409, "Remediation context scan exceeds500 proposals; narrow the cursor"
                )
            rows = [row for row in rows if _matches(c, row["content"], request, row["created_at"])]
            items = [golden.proposal(c, row["id"]) for row in rows[:limit]]
            for row in items:
                _historical(c, project, user, row["content"].get("source_trace_id"))
        for row in items:
            _policy(project, user, row["source_build_id"])
        return wrap(
            {
                "items": items,
                "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
            },
            request,
        )

    @router.post("/remediation", status_code=201)
    def create_proposal(project: UUID, body: golden.Proposal, request: Request):
        build_id = body_source(project, request, body)
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            row = idempotent(
                c,
                project,
                user,
                request,
                body,
                lambda: golden.create_proposal(c, project, user, body),
            )
        _policy(project, user, build_id)
        return wrap(row, request)

    @router.get("/remediation/{proposal_id}")
    def proposal(project: UUID, proposal_id: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            row = golden.proposal(c, proposal_id)
            _historical(c, project, user, row["content"].get("source_trace_id"))
            if not _matches(c, row["content"], request, row["created_at"]):
                raise HTTPException(404, "Proposal is outside the selected dashboard context")
        _policy(project, user, row["source_build_id"])
        return wrap(row, request)

    @router.post("/remediation/{proposal_id}/run-intents", status_code=202)
    def intent(project: UUID, proposal_id: UUID, body: golden.RunIntent, request: Request):
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            row = golden.proposal(c, proposal_id)
        _policy(project, user, row["source_build_id"])
        with context(request, project) as (c, user, roles):
            _authorize(roles)
            _historical(c, project, user, row["content"].get("source_trace_id"))
            result = idempotent(
                c,
                project,
                user,
                request,
                body,
                lambda: golden.run_intent(c, project, user, proposal_id, body),
            )
        _policy(project, user, row["source_build_id"])
        return wrap(result, request)

    return router
