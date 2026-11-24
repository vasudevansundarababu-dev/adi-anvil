"""Run routes (ARCHITECTURE 9.6 Runs; SCREENS 3.17-3.21). Studio's Human Review preview reads runs through the same
read endpoints with its client key; it can never start, cancel or re-score."""

from fastapi import APIRouter, Body, Request

from anvil.rlgym.common import GymError, idempotent, scope
from anvil.rlgym.routes import W, ok
from anvil.rlgym.runs import service

READERS = ("studio",)


def routes():
    r = APIRouter()

    @r.post(W + "/runs/admission-check")
    def admission_check(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        # A read: it changes nothing (no probe, no build), so it needs no Idempotency-Key.
        with scope(request, ws) as ctx:
            ctx.actor.require_person()
            return ok(service.public_check(service.admission_check(ctx, body)), request)

    @r.post(W + "/runs", status_code=201)
    def start(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            ctx.actor.require_person()
            result = idempotent(ctx, request, body, lambda: service.start(ctx, body))
        # The refused run is committed above with its reasons; the caller still gets ADMISSION_REFUSED.
        if result["refused"]:
            raise GymError(
                "ADMISSION_REFUSED",
                "Admission refused; every failing item is listed",
                {
                    "run_id": result["run"]["id"],
                    "items": [i for i in result["check"]["items"] if not i["ok"]],
                },
            )
        return ok(result, request, 201)

    @r.get(W + "/runs")
    def runs(
        ws: str,
        request: Request,
        state: str | None = None,
        q: str | None = None,
        project: str | None = None,
    ):
        with scope(request, ws, services=READERS) as ctx:
            return ok({"items": service.list_runs(ctx, state, q, project)}, request)

    @r.get(W + "/runs/{run_id}")
    def run(ws: str, run_id: str, request: Request):
        with scope(request, ws, services=READERS) as ctx:
            return ok(service.get_run(ctx, run_id), request)

    # E-007 phase 1 (shadow): the run's verification report (reports only; blocks nothing).
    @r.get(W + "/runs/{run_id}/verification")
    def verification_get(ws: str, run_id: str, request: Request):
        from anvil.rlgym.verification import service as verification

        with scope(request, ws, services=READERS) as ctx:
            service._run(ctx, run_id)  # the same access check as the run page
            return ok({"report": verification.latest(ctx.c, ctx.ws, run_id)}, request)

    @r.post(W + "/runs/{run_id}/verification")
    def verification_build(ws: str, run_id: str, request: Request):
        from anvil.rlgym.verification import service as verification

        with scope(request, ws) as ctx:
            ctx.actor.require_person()
            service._run(ctx, run_id)
            return ok(
                {"report": verification.build(ctx.c, ctx.ws, run_id, requested_by=ctx.actor.id)},
                request,
            )

    @r.get(W + "/runs/{run_id}/episodes")
    def episodes(
        ws: str,
        run_id: str,
        request: Request,
        system: str | None = None,
        state: str | None = None,
        kind: str | None = None,
        verdict: str | None = None,
        stratum: str | None = None,
        q: str | None = None,
        page: int = 1,
        size: int = 50,
    ):
        with scope(request, ws, services=READERS) as ctx:
            return ok(
                service.episodes(ctx, run_id, system, state, kind, verdict, stratum, q, page, size),
                request,
            )

    @r.post(W + "/runs/{run_id}/cancel")
    def cancel(ws: str, run_id: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: service.cancel(ctx, run_id, body)), request
            )

    @r.post(W + "/runs/{run_id}/rescore")
    def rescore(ws: str, run_id: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: service.rescore(ctx, run_id, body)), request
            )

    @r.get(W + "/comparisons")
    def compare(ws: str, request: Request, baseline: str = "", compared: str = ""):
        with scope(request, ws) as ctx:
            return ok(service.compare(ctx, baseline, compared), request)

    @r.post(W + "/comparisons", status_code=201)
    def save_comparison(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: service.save_comparison(ctx, body)),
                request,
                201,
            )

    return r
