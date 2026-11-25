"""Suite routes (ARCHITECTURE 9.6 Suites)."""

from fastapi import APIRouter, Body, Request

from anvil.rlgym.common import idempotent, require, scope
from anvil.rlgym.routes import W, ok
from anvil.rlgym.suites import service


def routes():
    r = APIRouter()

    def write(ws, request, body, fn, status=200):
        with scope(request, ws) as ctx:
            ctx.actor.require_person()
            return ok(idempotent(ctx, request, body, lambda: fn(ctx)), request, status)

    @r.get(W + "/projects/{pid}/suites")
    def suites(ws: str, pid: str, request: Request):
        with scope(request, ws) as ctx:
            return ok({"items": service.list_suites(ctx.c, ctx.ws, pid)}, request)

    @r.post(W + "/projects/{pid}/suites", status_code=201)
    def create(ws: str, pid: str, request: Request, body: dict = Body(default_factory=dict)):
        def run(ctx):
            sv_id = service.create_suite(
                ctx.c, ctx.ws, ctx.actor, pid, (body.get("name") or "").strip()
            )
            return service.view(ctx.c, ctx.ws, sv_id)

        return write(ws, request, body, run, 201)

    @r.post(W + "/suites/{suite_id}/drafts", status_code=201)
    def draft(ws: str, suite_id: str, request: Request, body: dict = Body(default_factory=dict)):
        require(
            body.get("project_id"),
            "VALIDATION_FAILED",
            "project_id is required",
            field="project_id",
        )
        return write(
            ws,
            request,
            body,
            lambda ctx: service.view(
                ctx.c,
                ctx.ws,
                service.new_draft(ctx.c, ctx.ws, ctx.actor, body["project_id"], suite_id),
            ),
            201,
        )

    @r.get(W + "/suite-versions/{sv}")
    def get(ws: str, sv: str, request: Request):
        with scope(request, ws) as ctx:
            return ok(service.view(ctx.c, ctx.ws, sv), request)

    # E-005 §3.1: the plan's exact case set, browse all cases, and one case with its read-only expected outcome.
    @r.get(W + "/suite-versions/{sv}/case-set")
    def case_set(ws: str, sv: str, request: Request):
        from anvil.rlgym.suites import cases

        with scope(request, ws) as ctx:
            return ok(cases.case_set(ctx.c, ctx.ws, sv), request)

    @r.get(W + "/suite-versions/{sv}/cases")
    def browse_cases(
        ws: str,
        sv: str,
        request: Request,
        application_type: str | None = None,
        completeness: str | None = None,
        edge_case: str | None = None,
        family: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ):
        from anvil.rlgym.suites import cases

        filters = {
            "application_type": application_type,
            "completeness": completeness,
            "edge_case": edge_case,
            "family": family,
        }
        with scope(request, ws) as ctx:
            return ok(cases.browse(ctx.c, ctx.ws, sv, filters, offset, limit), request)

    @r.get(W + "/suite-versions/{sv}/cases/{case_id}")
    def case_detail(ws: str, sv: str, case_id: str, request: Request):
        from anvil.rlgym.suites import cases

        with scope(request, ws) as ctx:
            return ok(cases.case_detail(ctx, sv, case_id), request)

    # E-005 §3.2: edge-case families from Studio, and "Request variant" (RL Engineer or Admin; Studio checks it).
    @r.get(W + "/suite-versions/{sv}/edge-catalog")
    def edge_catalog(ws: str, sv: str, request: Request):
        from anvil.rlgym.suites import cases

        with scope(request, ws) as ctx:
            return ok(cases.edge_catalog(ctx.c, ctx.ws, sv), request)

    @r.post(W + "/suite-versions/{sv}/edge-variants", status_code=201)
    def edge_variant(ws: str, sv: str, request: Request, body: dict = Body(default_factory=dict)):
        import uuid as _uuid

        from anvil.rlgym.suites import cases

        key = request.headers.get("Idempotency-Key") or f"rlgym-{_uuid.uuid4()}"
        with scope(request, ws) as ctx:
            return ok(cases.request_variant(ctx, sv, body, key), request, 201)

    # E-005 §2.3: environment versions this suite can use without re-authoring (others greyed, with the reason).
    @r.get(W + "/suite-versions/{sv}/environment-options")
    def environment_options(ws: str, sv: str, request: Request):
        from anvil.rlgym.suites import environment

        with scope(request, ws) as ctx:
            return ok(environment.options(ctx.c, ctx.ws, sv), request)

    # E-006 §3: the Trust & Safety category table (applies here? can be graded? prompts and where they're delivered).
    @r.get(W + "/suite-versions/{sv}/ts-categories")
    def ts_categories(ws: str, sv: str, request: Request):
        from anvil.rlgym.suites import safety_table

        with scope(request, ws) as ctx:
            return ok(safety_table.table(ctx.c, ctx.ws, sv), request)

    # E-007 §7.2: the reference agent (V-04 reference-solvable, V-01 replay) and the confirmation of each task's approach.
    @r.get(W + "/suite-versions/{sv}/reference")
    def reference_get(ws: str, sv: str, request: Request):
        from anvil.rlgym.verification import reference, reference_run

        with scope(request, ws) as ctx:
            tasks = ctx.c.execute(
                """SELECT t.id, t.task_id, t.revision, t.package_sha256, a.content actor FROM suites.suite_tasks s
                   JOIN projects.task_imports t ON t.id=s.task_import_id
                   LEFT JOIN projects.task_payloads a ON a.workspace_id=t.workspace_id AND a.package_sha256=t.package_sha256 AND a.part='actor'
                   WHERE s.suite_version_id=%s ORDER BY t.task_id""",
                (sv,),
            ).fetchall()
            out = []
            for t in tasks:
                summ = reference.summary(t["actor"])
                conf = ctx.c.execute(
                    """SELECT verdict, note, decided_by, decided_at FROM verification.reference_confirmations
                       WHERE workspace_id=%s AND package_sha256=%s AND summary_sha256=%s ORDER BY decided_at DESC LIMIT 1""",
                    (ctx.ws, t["package_sha256"], summ["sha256"]),
                ).fetchone()
                out.append(
                    {
                        "task_import_id": str(t["id"]),
                        "task_id": t["task_id"],
                        "revision": t["revision"],
                        "summary": summ,
                        "confirmation": conf,
                    }
                )
            return ok(
                {"tasks": out, "latest_run": reference_run.latest(ctx.c, ctx.ws, sv)}, request
            )

    @r.post(W + "/suite-versions/{sv}/reference-run", status_code=201)
    def reference_run_now(
        ws: str, sv: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        from anvil.rlgym.verification import reference_run

        with scope(request, ws) as ctx:
            ctx.actor.require_person()
            return ok(
                reference_run.run(
                    ctx.c,
                    ctx.ws,
                    sv,
                    str(ctx.actor.id),
                    replay=body.get("replay", True) is not False,
                    max_cases_per_task=min(int(body.get("cases_per_task") or 3), 10),
                ),
                request,
                201,
            )

    @r.post(W + "/suite-versions/{sv}/lookup-run", status_code=201)
    def lookup_run_now(ws: str, sv: str, request: Request, body: dict = Body(default_factory=dict)):
        """G4: the no-AI lookup baseline on the suite's case set (local instance; no model; no spend)."""
        from anvil.rlgym.verification import lookup

        with scope(request, ws) as ctx:
            ctx.actor.require_person()
            return ok(lookup.run(ctx.c, ctx.ws, sv, str(ctx.actor.id), body), request, 201)

    @r.get(W + "/suite-versions/{sv}/lookup-run")
    def lookup_latest(ws: str, sv: str, request: Request):
        from anvil.rlgym.verification import lookup

        with scope(request, ws) as ctx:
            return ok(
                {
                    "latest_run": lookup.latest(ctx.c, ctx.ws, sv),
                    "default_threshold_percent": lookup.DEFAULT_THRESHOLD,
                },
                request,
            )

    @r.post(W + "/task-imports/{tid}/reference-confirmation", status_code=201)
    def reference_confirm(
        ws: str, tid: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        from anvil.rlgym.verification import reference_run

        with scope(request, ws) as ctx:
            return ok(
                reference_run.confirm(ctx, tid, body.get("verdict"), body.get("note")), request, 201
            )

    @r.post(W + "/suite-versions/{sv}/edge-variants/{tag}/recipe")
    def edge_recipe(
        ws: str, sv: str, tag: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        import uuid as _uuid

        from anvil.rlgym.suites import cases

        key = request.headers.get("Idempotency-Key") or f"rlgym-{_uuid.uuid4()}"
        with scope(request, ws) as ctx:
            return ok(cases.write_recipe(ctx, sv, tag, body, key), request)

    @r.get(W + "/suite-versions/{sv}/coverage")
    def coverage(ws: str, sv: str, request: Request):
        with scope(request, ws) as ctx:
            v = service.view(ctx.c, ctx.ws, sv)
            return ok(
                {"tasks": v["tasks"], "cells": v["cells"], "criteria": len(v["criteria"])}, request
            )

    @r.patch(W + "/suite-versions/{sv}")
    def patch(ws: str, sv: str, request: Request, body: dict = Body(default_factory=dict)):
        return write(
            ws, request, body, lambda ctx: service.patch(ctx.c, ctx.ws, ctx.actor, sv, body)
        )

    @r.post(W + "/suite-versions/{sv}/save")
    def save(ws: str, sv: str, request: Request, body: dict = Body(default_factory=dict)):
        return write(ws, request, body, lambda ctx: service.save(ctx.c, ctx.ws, ctx.actor, sv))

    @r.delete(W + "/suite-versions/{sv}")
    def discard(ws: str, sv: str, request: Request):
        with scope(request, ws) as ctx:
            ctx.actor.require_person()
            return ok(service.discard(ctx.c, ctx.ws, ctx.actor, sv), request)

    @r.post(W + "/suite-versions/{sv}/suggestions/{kind}")
    def suggest(ws: str, sv: str, kind: str, request: Request):
        fn = {
            "bindings": service.suggest_bindings,
            "data-mix": service.suggest_mix,
            "ts": service.suggest_ts,
        }.get(kind)
        require(fn, "NOT_FOUND", "Unknown suggestion")
        with scope(request, ws) as ctx:
            return ok(fn(ctx.c, ctx.ws, sv), request)

    @r.post(W + "/suite-versions/{sv}/ts/generate")
    def ts_generate(ws: str, sv: str, request: Request, body: dict = Body(default_factory=dict)):
        return write(
            ws, request, body, lambda ctx: service.ts_generate(ctx.c, ctx.ws, ctx.actor, sv, body)
        )

    @r.post(W + "/suite-versions/{sv}/ts/review")
    def ts_review(ws: str, sv: str, request: Request, body: dict = Body(default_factory=dict)):
        return write(
            ws, request, body, lambda ctx: service.ts_review(ctx.c, ctx.ws, ctx.actor, sv, body)
        )

    @r.post(W + "/suite-versions/{sv}/ts/approve")
    def ts_approve(ws: str, sv: str, request: Request, body: dict = Body(default_factory=dict)):
        return write(
            ws, request, body, lambda ctx: service.ts_approve(ctx.c, ctx.ws, ctx.actor, sv)
        )

    @r.post(W + "/suite-versions/{sv}/more-data", status_code=201)
    def more_data(ws: str, sv: str, request: Request, body: dict = Body(default_factory=dict)):
        return write(
            ws,
            request,
            body,
            lambda ctx: service.send_more_data(ctx.c, ctx.ws, ctx.actor, sv, body),
            201,
        )

    return r
