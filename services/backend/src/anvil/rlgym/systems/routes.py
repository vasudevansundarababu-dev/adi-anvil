"""Systems routes (ARCHITECTURE 9.6, Admin: models and keys)."""

from fastapi import APIRouter, Body, Request

from anvil.rlgym.common import idempotent, scope
from anvil.rlgym.routes import W, ok
from anvil.rlgym.systems import service


def routes():
    r = APIRouter()

    @r.get(W + "/systems")
    def systems(
        ws: str,
        request: Request,
        q: str | None = None,
        kind: str | None = None,
        status: str | None = None,
    ):
        with scope(request, ws) as ctx:
            return ok(
                {
                    "items": service.list_systems(ctx, q, kind, status),
                    "live_enabled": service.live_enabled(),
                },
                request,
            )

    @r.post(W + "/systems", status_code=201)
    def create(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: service.create_system(ctx, body)),
                request,
                201,
            )

    @r.get(W + "/live/approvals")
    def live_approvals(ws: str, request: Request):
        """Live approvals with spend so far (people only). No key or secret is ever part of this."""
        from anvil.rlgym.live import approvals

        with scope(request, ws, services=(), people=True) as ctx:
            return ok(
                {
                    "items": approvals.list_all(ctx.c, ctx.ws),
                    "live_enabled": service.live_enabled(),
                },
                request,
            )

    @r.post(W + "/live/approvals", status_code=201)
    def live_approve(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        from anvil.rlgym.live import approvals

        with scope(request, ws, services=(), people=True) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: approvals.create(ctx, body)), request, 201
            )

    @r.post(W + "/live/approvals/{aid}/revoke")
    def live_revoke(ws: str, aid: str, request: Request, body: dict = Body(default_factory=dict)):
        from anvil.rlgym.live import approvals

        with scope(request, ws, services=(), people=True) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: approvals.revoke(ctx, aid, body)), request
            )

    @r.get(W + "/systems/{sid}")
    def get(ws: str, sid: str, request: Request):
        with scope(request, ws) as ctx:
            return ok(service.get_system(ctx, sid), request)

    @r.post(W + "/systems/{sid}/versions", status_code=201)
    def version(ws: str, sid: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: service.new_version(ctx, sid, body)),
                request,
                201,
            )

    @r.post(W + "/systems/{sid}/versions/{v}/probe")
    def probe(ws: str, sid: str, v: int, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: service.probe_system(ctx, sid, v)), request
            )

    @r.post(W + "/systems/{sid}/disable")
    def disable(ws: str, sid: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: service.set_enabled(ctx, sid, False, body.get("reason")),
                ),
                request,
            )

    @r.post(W + "/systems/{sid}/enable")
    def enable(ws: str, sid: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: service.set_enabled(ctx, sid, True)), request
            )

    @r.get(W + "/hf/models/{repo:path}/revisions/latest")
    def hf_latest(ws: str, repo: str, request: Request):
        with scope(request, ws) as ctx:
            return ok(service.hf_latest(ctx, repo), request)

    @r.get(W + "/model-sets")
    def model_sets(ws: str, request: Request):
        with scope(request, ws) as ctx:
            return ok({"items": service.list_model_sets(ctx)}, request)

    @r.post(W + "/model-sets", status_code=201)
    def save_set(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: service.save_model_set(ctx, body)),
                request,
                201,
            )

    @r.get(W + "/keys")
    def keys(ws: str, request: Request, provider: str | None = None):
        with scope(request, ws) as ctx:
            return ok(
                {"items": service.list_keys(ctx, provider), "live_enabled": service.live_enabled()},
                request,
            )

    @r.post(W + "/keys", status_code=201)
    def add_key(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            # The idempotency record never hashes or stores the secret, only the public response.
            public = {k: v for k, v in body.items() if k != "secret"}
            return ok(
                idempotent(ctx, request, public, lambda: service.add_key(ctx, body)), request, 201
            )

    @r.post(W + "/keys/{kid}/rotate")
    def rotate(ws: str, kid: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            public = {k: v for k, v in body.items() if k != "secret"}
            return ok(
                idempotent(ctx, request, public, lambda: service.rotate_key(ctx, kid, body)),
                request,
            )

    @r.post(W + "/keys/{kid}/test")
    def test(ws: str, kid: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(idempotent(ctx, request, body, lambda: service.test_key(ctx, kid)), request)

    @r.post(W + "/keys/{kid}/revoke")
    def revoke(ws: str, kid: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: service.revoke_key(ctx, kid, body)), request
            )

    return r
