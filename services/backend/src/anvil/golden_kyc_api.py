"""Authenticated Golden KYC command gateway; never imports private controls."""

import os
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Jsonb
from pydantic import Field

from anvil import auth
from anvil.db import digest, uid
from anvil.schemas import Strict


class Trial(Strict):
    pack_id: UUID
    application_id: str = Field(pattern=r"^GB-[0-9]{3}$")
    model_label: str = Field(min_length=1, max_length=100)
    repetition: int = Field(ge=1, le=10, strict=True)


class Step(Strict):
    generation: int = Field(ge=0, strict=True)
    trial_token: str = Field(min_length=32, max_length=128)
    action: str = Field(min_length=1, max_length=60)
    arguments: dict = Field(default_factory=dict)


class Run(Strict):
    pack_id: UUID
    repetitions: int = Field(default=1, ge=1, le=10, strict=True)


class AnvilImport(Strict):
    pack_id: UUID
    task_mode: Literal["reusable_state_workflow", "reusable_application_workflow"] = "reusable_state_workflow"


class AnvilRun(Strict):
    import_id: UUID
    repetitions: int = Field(default=1, ge=1, le=10, strict=True)


class ApplicationInputBinding(Strict):
    resolution_id: UUID
    case_import_id: UUID
    preparation_binding_id: UUID


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/golden-banking/v1")
    from anvil.golden_kyc_paid_api import routes as paid_routes

    router.include_router(paid_routes(context, wrap, idempotent))
    from anvil.kyc_policy_review_api import routes as policy_review_routes

    router.include_router(policy_review_routes(context, wrap, idempotent))

    def authorize(roles, admin=False):
        if os.environ.get("ANVIL_GOLDEN_KYC_ENABLED") != "true":
            raise HTTPException(503, "Golden KYC is disabled")
        auth.require(roles, *(("admin",) if admin else ("admin", "rl-engineer")))

    def enqueue(c, project, user, request, kind, args):
        key = request.headers.get("idempotency-key")
        if not key or len(key) > 128:
            raise HTTPException(428, "Bounded Idempotency-Key required")
        from fastapi.encoders import jsonable_encoder

        args = jsonable_encoder(args)
        if len(str(args)) > 20000:
            raise HTTPException(413, "Command exceeds bound")
        fingerprint = digest({"kind": kind, "args": args})
        c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
        old = c.execute(
            "SELECT id,body_sha256 FROM banking.commands WHERE project_id=%s AND requested_by=%s AND idempotency_key=%s",
            (project, user, key),
        ).fetchone()
        if old:
            if old["body_sha256"] != fingerprint:
                raise HTTPException(409, "Idempotency key reused with changed command")
            return {"command_id": old["id"], "accepted": True}
        identifier = uid()
        c.execute(
            "INSERT INTO banking.commands(id,project_id,requested_by,kind,arguments,idempotency_key,body_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (identifier, project, user, kind, Jsonb(args), key, fingerprint),
        )
        return {"command_id": identifier, "accepted": True}

    @router.get("/packs")
    def packs(project: UUID, request: Request):
        with context(request, project) as (c, _, roles):
            authorize(roles)
            rows = c.execute(
                "SELECT id,manifest,created_at FROM banking.packs WHERE project_id=%s ORDER BY created_at DESC LIMIT 20",
                (project,),
            ).fetchall()
            return wrap(rows, request)

    @router.post("/anvil/import")
    def import_anvil(project: UUID, request: Request, body: AnvilImport):
        from anvil.golden_kyc_anvil import register

        with context(request, project) as (c, user, roles):
            authorize(roles, True)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: register(c, project, user, body.pack_id,
                                     reusable=body.task_mode == "reusable_state_workflow",
                                     application_types=body.task_mode == "reusable_application_workflow"),
                ),
                request,
            )

    @router.get("/anvil/imports")
    def imports_anvil(project: UUID, request: Request):
        from anvil.golden_kyc_anvil import public

        with context(request, project) as (c, _, roles):
            authorize(roles)
            rows = c.execute(
                "SELECT * FROM banking.anvil_imports WHERE project_id=%s ORDER BY created_at DESC LIMIT 20",
                (project,),
            ).fetchall()
            return wrap([public(row) for row in rows], request)

    @router.post("/anvil/application-inputs")
    def bind_application_inputs(project: UUID, request: Request, body: ApplicationInputBinding):
        from anvil.golden_kyc_input_binding import bind

        with context(request, project) as (c, user, roles):
            authorize(roles, True)
            return wrap(idempotent(c, project, user, request, body,
                                  lambda: bind(c, project, user, resolution_id=body.resolution_id,
                                               case_import_id=body.case_import_id,
                                               preparation_binding_id=body.preparation_binding_id)), request)

    @router.post("/anvil/runs", status_code=202)
    def run_anvil(project: UUID, request: Request, body: AnvilRun):
        from anvil.golden_kyc_anvil import start

        with context(request, project) as (c, user, roles):
            authorize(roles, True)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: start(c, project, user, body.import_id, body.repetitions),
                ),
                request,
            )

    @router.get("/anvil/runs")
    def anvil_runs(project: UUID, request: Request):
        from anvil.benchmark_runs import get

        with context(request, project) as (c, _, roles):
            authorize(roles)
            rows = c.execute(
                "SELECT r.run_id FROM banking.anvil_runs r WHERE r.project_id=%s UNION SELECT j.run_id FROM banking.execution_jobs j WHERE j.project_id=%s",
                (project, project),
            ).fetchall()
            return wrap([get(c, row["run_id"]) for row in rows], request)

    @router.post("/seed", status_code=202)
    def seed(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            authorize(roles, True)
            return wrap(enqueue(c, project, user, request, "seed", {}), request)

    @router.get("/packs/{pack}/applications")
    def applications(project: UUID, pack: UUID, request: Request):
        with context(request, project) as (c, _, roles):
            authorize(roles)
            # Curator inventory excludes private scenarios/expectations.
            rows = c.execute(
                "SELECT id,snapshot->>'product' AS product,snapshot->>'governing_state' AS state,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id LIMIT 200",
                (project, pack),
            ).fetchall()
            return wrap(rows, request)

    @router.post("/trials", status_code=202)
    def trial(project: UUID, request: Request, body: Trial):
        with context(request, project) as (c, user, roles):
            authorize(roles, True)
            return wrap(enqueue(c, project, user, request, "trial", body.model_dump()), request)

    @router.post("/runs", status_code=202)
    def run(project: UUID, request: Request, body: Run):
        with context(request, project) as (c, user, roles):
            authorize(roles, True)
            return wrap(enqueue(c, project, user, request, "run", body.model_dump()), request)

    @router.get("/runs")
    def runs(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            rows = c.execute(
                "SELECT id,profile,profile_sha256,created_at FROM banking.runs WHERE project_id=%s AND created_by=%s ORDER BY created_at DESC LIMIT 20",
                (project, user),
            ).fetchall()
            return wrap(rows, request)

    @router.post("/trials/{trial}/actions", status_code=202)
    def step(project: UUID, trial: UUID, request: Request, body: Step):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            if not c.execute(
                "SELECT 1 FROM banking.trials WHERE project_id=%s AND id=%s AND assigned_user=%s",
                (project, trial, user),
            ).fetchone():
                raise HTTPException(404, "Resource not found")
            return wrap(
                enqueue(
                    c, project, user, request, "step", body.model_dump() | {"trial_id": str(trial)}
                ),
                request,
            )

    @router.get("/commands/{command}")
    def command(project: UUID, command: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            row = c.execute(
                "SELECT id,status,result,created_at FROM banking.commands WHERE id=%s AND project_id=%s AND requested_by=%s",
                (command, project, user),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Resource not found")
            return wrap(row, request)

    @router.get("/trials")
    def trials(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            rows = c.execute(
                "SELECT id,application_id,model_label,repetition,generation,closed,created_at FROM banking.trials WHERE project_id=%s AND assigned_user=%s ORDER BY created_at DESC LIMIT 200",
                (project, user),
            ).fetchall()
            return wrap(rows, request)

    @router.get("/trials/{trial}/export")
    def export(project: UUID, trial: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            row = c.execute(
                "SELECT id,application_id,model_label,repetition,generation,closed FROM banking.trials WHERE id=%s AND project_id=%s AND assigned_user=%s",
                (trial, project, user),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Resource not found")
            recommendations = c.execute(
                "SELECT generation,content,created_at FROM banking.recommendations WHERE trial_id=%s ORDER BY generation",
                (trial,),
            ).fetchall()
            evaluations = c.execute(
                "SELECT generation,summary,created_at FROM banking.evaluation_summaries WHERE trial_id=%s ORDER BY generation",
                (trial,),
            ).fetchall()
            return wrap(
                {
                    "trial": row,
                    "recommendations": recommendations,
                    "paid_calls": False,
                    "model_performance": False,
                    "evaluations": evaluations,
                    "evaluation": "available" if evaluations else "pending_separate_evaluator",
                },
                request,
            )

    return router
