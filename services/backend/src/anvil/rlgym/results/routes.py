"""Report, drill-down, PDF, diagnosis and package routes (ARCHITECTURE 9.6 Results; SCREENS 3.22-3.36)."""

from fastapi import APIRouter, Body, Request
from fastapi.responses import Response

from anvil.rlgym.common import idempotent, scope
from anvil.rlgym.results import report, service
from anvil.rlgym.routes import W, ok


def routes():
    r = APIRouter()

    @r.get(W + "/runs/{run_id}/report")
    def report_tab(ws: str, run_id: str, request: Request, tab: str = "overview"):
        with scope(request, ws) as ctx:
            out = report.tab(ctx.c, ctx.ws, run_id, tab)
            out["renders"] = service.renders(ctx.c, run_id)
            return ok(out, request)

    @r.get(W + "/runs/{run_id}/report/drill")
    def drill(ws: str, run_id: str, request: Request, kind: str, key: str = ""):
        with scope(request, ws) as ctx:
            return ok(report.drill(ctx.c, ctx.ws, run_id, kind, key, ctx.actor), request)

    @r.post(W + "/runs/{run_id}/report/pdf", status_code=201)
    def render(ws: str, run_id: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx, request, body, lambda: service.render_pdf(ctx.c, ctx.ws, ctx.actor, run_id)
                ),
                request,
                201,
            )

    @r.get(W + "/runs/{run_id}/report/pdf/{revision}")
    def download(ws: str, run_id: str, revision: int, request: Request, inline: bool = False):
        with scope(request, ws) as ctx:
            data, name = service.pdf_bytes(ctx.c, ctx.ws, ctx.actor, run_id, revision)
        return Response(
            data,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{name}"',
                "Cache-Control": "no-store",
            },
        )

    @r.put(W + "/episodes/{episode_id}/diagnosis")
    def diagnosis(
        ws: str, episode_id: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: service.save_diagnosis(ctx.c, ctx.ws, ctx.actor, episode_id, body),
                ),
                request,
            )

    @r.post(W + "/episodes/{episode_id}/inbox-items", status_code=201)
    def inbox_item(
        ws: str, episode_id: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: service.send_inbox(ctx.c, ctx.ws, ctx.actor, episode_id, body),
                ),
                request,
                201,
            )

    @r.post(W + "/packages", status_code=201)
    def package(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: service.create_package(ctx.c, ctx.ws, ctx.actor, body),
                ),
                request,
                201,
            )

    @r.get(W + "/packages")
    def packages(ws: str, request: Request):
        with scope(request, ws) as ctx:
            return ok({"items": service.list_packages(ctx.c, ctx.ws)}, request)

    @r.get(W + "/packages/{package_id}/download")
    def package_download(ws: str, package_id: str, request: Request):
        with scope(request, ws) as ctx:
            data, name = service.package_bytes(ctx.c, ctx.ws, ctx.actor, package_id)
        return Response(
            data,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "Cache-Control": "no-store",
            },
        )

    return r
