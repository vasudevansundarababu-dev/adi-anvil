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
