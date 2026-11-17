"""Authenticated assigned human requests; neither graph launch nor spending approval."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from anvil import auth
from anvil.db import audit, one
from anvil.praxis_contract import Model
from anvil.workflow_journal import submit_answer


class HumanAnswer(Model):
    request_key: str = Field(min_length=1, max_length=180)
    response: dict = Field(max_length=50)
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    outcome: Literal["next", "error"] = "next"


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/workflows")

    from anvil.workflow_native import Definition

    @router.get("/responders")
    def responders(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            return wrap(
                {
                    "items": c.execute(
                        "SELECT DISTINCT u.id,u.name FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id WHERE m.project_id=%s AND m.active AND m.role IN ('admin','rl-engineer') AND u.active AND NOT u.is_synthetic ORDER BY u.name,u.id LIMIT 100",
                        (project,),
                    ).fetchall()
                },
                request,
            )

    @router.post("/definitions")
    def register_definition(project: UUID, body: Definition, request: Request):
        from anvil import workflow_registry
        from anvil.workspace_execution import recent_admin_signin

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            recent_admin_signin(request)

            def save():
                try:
                    return workflow_registry.register(c, project, user, body)
                except ValueError:
                    raise HTTPException(
                        409, "Exact graph testing definition, review, rights and bounds required"
                    ) from None

            return wrap(
                idempotent(c, project, user, request, body.model_dump(mode="json"), save), request
            )

    @router.get("/definitions")
    def definitions(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            if not one(c, "SELECT to_regclass('anvil.workflow_definitions') t")["t"]:
                return wrap({"items": []}, request)
            return wrap(
                {
                    "items": c.execute(
                        "SELECT id,package_id,subject_hash,revoked_at,definition FROM anvil.workflow_definitions WHERE project_id=%s ORDER BY created_at DESC LIMIT 100",
                        (project,),
                    ).fetchall()
                },
                request,
            )

    @router.post("/definitions/{definition}/revoke")
    def revoke_definition(project: UUID, definition: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def revoke():
                row = one(
                    c,
                    "UPDATE anvil.workflow_definitions SET revoked_at=now() WHERE id=%s AND project_id=%s AND revoked_at IS NULL RETURNING id",
                    (definition, project),
                )
                if not row:
                    raise HTTPException(409, "Definition unavailable or already revoked")
                audit(c, project, user, "workflow.testing_definition_revoked", definition)
                return {"revoked": True}

            return wrap(idempotent(c, project, user, request, {}, revoke), request)

    @router.post("/{execution}/cancel")
    def cancel(project: UUID, execution: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")

            def stop():
                row = one(
                    c,
                    "UPDATE anvil.workflow_executions SET cancel_requested=true WHERE id=%s AND project_id=%s RETURNING id",
                    (execution, project),
                )
                if not row:
                    raise HTTPException(404, "Workflow unavailable")
                audit(c, project, user, "workflow.cancel_requested", execution)
                return {"cancel_requested": True}

            return wrap(idempotent(c, project, user, request, {}, stop), request)

    @router.get("/human-requests")
    def requests(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            if not one(c, "SELECT to_regclass('anvil.workflow_executions') t")["t"]:
                return wrap({"available": False, "items": []}, request)
            rows = c.execute(
                "SELECT r.execution_id,r.request_key,r.request_sha256,r.deadline,e.binding_sha256,e.state->'humans'->r.request_key->'request' AS request FROM anvil.workflow_human_requests r JOIN anvil.workflow_executions e ON e.id=r.execution_id WHERE r.project_id=%s AND r.assigned_to=%s AND NOT e.cancel_requested AND e.expires_at>now() AND r.deadline>now() AND e.state->>'status'='waiting_human' AND NOT EXISTS(SELECT 1 FROM anvil.workflow_human_answers a WHERE a.execution_id=r.execution_id AND a.request_key=r.request_key) ORDER BY r.deadline,r.execution_id,r.request_key LIMIT 100",
                (project, user),
            ).fetchall()
            return wrap({"available": True, "items": rows}, request)

    @router.post("/{execution}/human-answers")
    def respond(project: UUID, execution: UUID, body: HumanAnswer, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")

            def save():
                # Exact displayed request, not a signature over a mutable graph.
                pending = one(
                    c,
                    "SELECT request_sha256 FROM anvil.workflow_human_requests WHERE execution_id=%s AND request_key=%s AND assigned_to=%s AND project_id=%s",
                    (execution, body.request_key, user, project),
                )
                if not pending or pending["request_sha256"] != body.request_sha256:
                    raise HTTPException(409, "Human request changed or unavailable")
                try:
                    submit_answer(
                        c, project, user, execution, body.request_key, body.response, body.outcome
                    )
                except ValueError:
                    raise HTTPException(409, "Human request closed, expired or invalid") from None
                audit(
                    c,
                    project,
                    user,
                    "workflow.human_answer",
                    execution,
                    {
                        "request_key": body.request_key,
                        "request_sha256": body.request_sha256,
                        "spending_authority": False,
                    },
                )
                return {"status": "recorded", "spending_authority": False}

            return wrap(idempotent(c, project, user, request, body.model_dump(), save), request)

    return router
