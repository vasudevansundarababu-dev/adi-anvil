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

    @r.get(W + "/runs/{run_id}/skill-compare")
    def skill_compare(ws: str, run_id: str, request: Request, other: str):
        """G5: two runs (e.g. golden KYC v8 and KYC Judgment v1, same models) compared skill by skill. Read-only."""
        from anvil.rlgym.results import skills

        with scope(request, ws) as ctx:
            return ok(skills.compare_runs(ctx.c, ctx.ws, run_id, other), request)

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


def sme_routes():
    """Episode viewer and SME review (SCREENS 3.38-3.39)."""
    from anvil.rlgym.results import episodes, sme

    r = APIRouter()

    @r.get(W + "/episodes/{episode_id}")
    def episode(ws: str, episode_id: str, request: Request):
        with scope(request, ws, services=("studio",)) as ctx:
            return ok(episodes.view(ctx.c, ctx.ws, ctx.actor, episode_id), request)

    @r.get(W + "/episodes/{episode_id}/compare")
    def compare(ws: str, episode_id: str, request: Request, other: str):
        with scope(request, ws) as ctx:
            return ok(episodes.compare(ctx.c, ctx.ws, ctx.actor, episode_id, other), request)

    @r.put(W + "/episodes/{episode_id}/suspected-cause")
    def cause(ws: str, episode_id: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: episodes.set_cause(ctx.c, ctx.ws, ctx.actor, episode_id, body),
                ),
                request,
            )

    @r.get(W + "/runs/{run_id}/sme-review")
    def run_sme(ws: str, run_id: str, request: Request):
        with scope(request, ws) as ctx:
            return ok(sme.run_view(ctx.c, ctx.ws, run_id), request)

    @r.post(W + "/runs/{run_id}/sme-review-batches", status_code=201)
    def create_batch(
        ws: str, run_id: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: sme.create_batch(ctx.c, ctx.ws, ctx.actor, run_id, body),
                ),
                request,
                201,
            )

    @r.get(W + "/sme-review-batches/{batch_id}")
    def batch(ws: str, batch_id: str, request: Request):
        with scope(request, ws, services=("adi-forge",)) as ctx:
            return ok(sme.batch_view(ctx.c, ctx.ws, batch_id), request)

    @r.post(W + "/sme-review-batches/{batch_id}/decisions")
    def decisions(
        ws: str, batch_id: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        # Only ADI Forge sends SME decisions; SMEs have no RL Gym account.
        with scope(request, ws, services=("adi-forge",), people=False) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: sme.receive_decisions(ctx.c, ctx.ws, ctx.actor, batch_id, body),
                ),
                request,
            )

    @r.post(W + "/sme-review-items/{item_id}/grader-fix", status_code=201)
    def grader_fix(
        ws: str, item_id: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: sme.grader_fix(ctx.c, ctx.ws, ctx.actor, item_id, body),
                ),
                request,
                201,
            )

    @r.post(W + "/sme-review-items/{item_id}/validation-run", status_code=201)
    def validation(
        ws: str, item_id: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: sme.validation_run(ctx.c, ctx.ws, ctx.actor, item_id),
                ),
                request,
                201,
            )

    return r
