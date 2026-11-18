from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, ValidationError

from anvil import auth
from anvil.kyc_policy_reviews import Decision, DomainSubject, decide, revoke, stage
from anvil.praxis_generic_contract import canonical, load
from anvil.schemas import Strict


class Revocation(Strict):
    reason: str = Field(min_length=10, max_length=2000)


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/policy-reviews")

    @router.get("/subjects")
    def subjects(project: UUID, request: Request):
        with context(request, project) as (c, _, roles):
            auth.require(roles, "admin", "rl-engineer")
            rows = c.execute("SELECT id,content_sha256,created_at,created_by FROM anvil.kyc_policy_review_subjects "
                             "WHERE project_id=%s ORDER BY created_at DESC,id LIMIT 100", (project,)).fetchall()
            return wrap(rows, request)

    @router.get("/subjects/{subject_id}")
    def subject_detail(project: UUID, subject_id: UUID, request: Request):
        with context(request, project) as (c, _, roles):
            auth.require(roles, "admin", "rl-engineer")
            row = c.execute("SELECT id,content_sha256,body_canonical,created_by FROM anvil.kyc_policy_review_subjects "
                            "WHERE project_id=%s AND id=%s", (project, subject_id)).fetchone()
            if not row:
                raise HTTPException(404, "Policy subject not found")
            return wrap({"id": row["id"], "sha256": row["content_sha256"],
                         "subject": load(row["body_canonical"].encode()), "created_by": row["created_by"]}, request)

    async def parse(request, model):
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 131072:
                raise HTTPException(413, "Policy review payload exceeds bound")
            raw.extend(chunk)
        try:
            return model.model_validate_json(canonical(load(bytes(raw))))
        except (ValueError, ValidationError):
            raise HTTPException(422, "Invalid policy review contract") from None

    @router.post("/subjects", status_code=201)
    async def create_subject(project: UUID, request: Request):
        body = await parse(request, DomainSubject)
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            return wrap(idempotent(c, project, user, request, body,
                                  lambda: stage(c, project, user, body)), request)

    @router.post("/subjects/{subject_id}/decisions", status_code=201)
    async def decision(project: UUID, subject_id: UUID, request: Request):
        body = await parse(request, Decision)
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            return wrap(idempotent(c, project, user, request,
                                  {"subject_id": str(subject_id), **body.model_dump(mode="json")},
                                  lambda: decide(c, project, user, subject_id, body)), request)

    @router.get("")
    def records(project: UUID, request: Request):
        with context(request, project) as (c, _, roles):
            auth.require(roles, "admin", "rl-engineer")
            rows = c.execute("SELECT r.id,r.kind,r.subject_id,r.content_sha256,r.expires_at,"
                             "r.body_canonical::jsonb->>'decision' AS decision,"
                             "EXISTS(SELECT 1 FROM anvil.kyc_policy_review_revocations v "
                             "WHERE v.project_id=r.project_id AND v.receipt_id=r.id) AS revoked "
                             "FROM anvil.kyc_policy_review_receipts r WHERE r.project_id=%s "
                             "ORDER BY r.created_at DESC,r.id LIMIT 100", (project,)).fetchall()
            return wrap({"records": rows, "qualification_granted": False}, request)

    @router.post("/{receipt_id}/revoke")
    async def revocation(project: UUID, receipt_id: UUID, request: Request):
        body = await parse(request, Revocation)
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            return wrap(idempotent(c, project, user, request,
                                  {"receipt_id": str(receipt_id), **body.model_dump()},
                                  lambda: revoke(c, project, user, receipt_id, body.reason)), request)

    return router
