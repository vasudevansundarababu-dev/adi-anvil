from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from anvil import auth
from anvil import evaluator_configurations as configurations
from anvil.db import audit, uid


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/evaluators")

    def authorize(roles):
        auth.require(roles, "admin", "rl-engineer")

    @router.get("")
    def listing(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            rows = c.execute(
                "SELECT id FROM anvil.evaluator_configurations ORDER BY created_at DESC,id DESC LIMIT 100"
            ).fetchall()
            return wrap(
                {
                    "items": [configurations.get(c, row["id"]) for row in rows],
                    "live_calls_enabled": False,
                },
                request,
            )

    @router.post("", status_code=201)
    def create(project: UUID, body: configurations.Configure, request: Request):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            if body.secret:
                recent = c.execute(
                    "SELECT 1 FROM anvil.sessions WHERE user_id=%s AND token_hash=%s AND issued_at>now()-interval '10 minutes' AND revoked_at IS NULL AND expires_at>now()",
                    (user, auth.hashed(request.cookies.get("anvil_session", ""))),
                ).fetchone()
                if not recent:
                    raise HTTPException(403, "Sign in again before saving an evaluator key")
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body.model_dump(exclude={"secret"})
                    | {
                        "secret_digest": auth.hashed(body.secret.get_secret_value())
                        if body.secret
                        else None
                    },
                    lambda: configurations.create(c, project, user, body),
                ),
                request,
            )

    @router.post("/{identifier}/test")
    def test(project: UUID, identifier: UUID, body: configurations.TestCases, request: Request):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: configurations.test(c, project, user, identifier, body),
                ),
                request,
            )

    @router.post("/{identifier}/revoke")
    def revoke(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            configurations.get(c, identifier)
            c.execute(
                "INSERT INTO anvil.evaluator_revocations(id,project_id,configuration_id,created_by) VALUES(%s,%s,%s,%s) ON CONFLICT(project_id,configuration_id) DO NOTHING",
                (uid(), project, identifier, user),
            )
            audit(c, project, user, "evaluator.revoked", identifier)
            return wrap(configurations.get(c, identifier), request)

    return router
