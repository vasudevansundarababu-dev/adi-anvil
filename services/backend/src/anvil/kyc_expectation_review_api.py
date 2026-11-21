"""Real Admin reviews salted metadata; never receives private expected answers."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field, ValidationError

from anvil import auth
from anvil.kyc_expectation_reviews import Decision, current, decide, parse_subject, revoke
from anvil.praxis_generic_contract import canonical, load
from anvil.schemas import Strict


class Revoke(Strict):
    reason: str = Field(min_length=10, max_length=2000)


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/expectation-reviews")

    @router.get("/attempts/{key}")
    def attempt(project: UUID, key: UUID, target_id: UUID, operation: Literal["decision", "revoke"],
                request: Request, body_sha256: str = Query(pattern=r"^[a-f0-9]{64}$")):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            prefix = f"/api/v1/projects/{project}/golden-banking/v1/expectation-reviews"
            route = prefix + (f"/subjects/{target_id}/decisions" if operation == "decision" else f"/{target_id}/revoke")
            row = c.execute("SELECT body_hash,response FROM anvil.idempotency WHERE project_id=%s AND user_id=%s AND route=%s AND key=%s",
                            (project, user, route, str(key))).fetchone()
            if not row:
                return wrap({"committed": False, "status": "not_observed_keep_reconciliation_hold"}, request)
            if str(row["body_hash"]).strip() != body_sha256:
                raise HTTPException(409, "Committed review attempt has a different request hash")
            return wrap({"committed": True, "body_sha256": body_sha256, "response": row["response"]}, request)

    async def parse(request, model):
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 16384:
                raise HTTPException(413, "Expectation review metadata exceeds bound")
            raw.extend(chunk)
        try:
            return model.model_validate_json(canonical(load(bytes(raw))))
        except (ValueError, ValidationError):
            raise HTTPException(422, "Invalid expectation review metadata; no private answers accepted") from None

    @router.get("/subjects")
    def subjects(project: UUID, request: Request):
        with context(request, project) as (c, _, roles):
            auth.require(roles, "admin", "rl-engineer")
            rows = c.execute("SELECT id,pack_id,content_sha256,created_at FROM anvil.kyc_expectation_subjects WHERE project_id=%s ORDER BY created_at DESC,id DESC LIMIT 50", (project,)).fetchall()
            return wrap({"subjects": rows, "private_answers_included": False, "run_authority": "not_granted"}, request)

    @router.get("/subjects/{identifier}")
    def detail(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, _, roles):
            auth.require(roles, "admin", "rl-engineer")
            row = c.execute("SELECT * FROM anvil.kyc_expectation_subjects WHERE project_id=%s AND id=%s", (project, identifier)).fetchone()
            if not row:
                raise HTTPException(404, "Expectation review subject not found")
            subject = parse_subject(row)
            return wrap({"id": row["id"], "sha256": row["content_sha256"],
                         "subject": subject.model_dump(mode="json"), "current_review": current(c, project, subject.pack_id),
                         "private_answers_included": False}, request)

    @router.post("/subjects/{identifier}/decisions", status_code=201)
    async def decision(project: UUID, identifier: UUID, request: Request):
        body = await parse(request, Decision)
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            return wrap(idempotent(c, project, user, request,
                                  {"subject_id": str(identifier), **body.model_dump(mode="json")},
                                  lambda: decide(c, project, user, identifier, body)), request)

    @router.post("/{identifier}/revoke")
    async def revocation(project: UUID, identifier: UUID, request: Request):
        body = await parse(request, Revoke)
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            return wrap(idempotent(c, project, user, request,
                                  {"receipt_id": str(identifier), **body.model_dump()},
                                  lambda: revoke(c, project, user, identifier, body.reason)), request)

    return router
