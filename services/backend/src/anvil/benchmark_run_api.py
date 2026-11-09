"""Authenticated project-scoped configuration, Run and exact-scope export endpoints."""

from uuid import UUID
from zipfile import BadZipFile

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response

from anvil import auth
from anvil import benchmark_business_fixture as fixture
from anvil import benchmark_project_import as imports
from anvil import benchmark_report_policy as review_policy
from anvil import benchmark_run_views as views
from anvil import benchmark_runs as runs
from anvil.request_limits import RequestBodyTooLarge


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/benchmark")

    def permit(roles):
        auth.require(roles, "admin", "rl-engineer")

    def scope(request):
        q = request.query_params
        return dict(
            models=q.getlist("model"),
            environments=q.getlist("environment"),
            task=q.get("task", "all"),
            period=q.get("period", "all"),
            method=q.get("method", "all"),
            cell_id=q.get("cell"),
        )

    @router.get("")
    def listing(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            groups = c.execute(
                "SELECT * FROM anvil.benchmark_task_groups ORDER BY created_at DESC,id DESC LIMIT 100"
            ).fetchall()
            plans = c.execute(
                "SELECT * FROM anvil.benchmark_execution_plans ORDER BY created_at DESC,id DESC LIMIT 100"
            ).fetchall()
            rows = c.execute(
                "SELECT id FROM anvil.benchmark_runs ORDER BY created_at DESC,id DESC LIMIT 100"
            ).fetchall()
            current_source = runs.source_hash()
            return wrap(
                {
                    "groups": [imports.public_group(g) for g in groups],
                    "plans": [
                        p | {"runnable": p["snapshot"]["source_sha256"] == current_source}
                        for p in plans
                    ],
                    "runs": [runs.get(c, r["id"]) for r in rows],
                    "methods": runs.method_profiles(c),
                    "models": fixture.MODELS,
                    "provider_calls": 0,
                    "report_policy": review_policy.current(c, project),
                },
                request,
            )

    @router.get("/sample.zip")
    def sample(project: UUID, request: Request):
        with context(request, project) as (_, user, roles):
            permit(roles)
            return Response(
                fixture.bundle(),
                media_type="application/zip",
                headers={
                    "Content-Disposition": 'attachment; filename="fictional-praxis-project.zip"'
                },
            )

    @router.post("/sample")
    def sample_import(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            runs.enabled()
            content, policies = imports.parse(fixture.bundle())
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"fixture": "fictional-banking-v1"},
                    lambda: imports.store(c, project, user, content, policies),
                ),
                request,
            )

    @router.post("/import")
    async def importing(project: UUID, request: Request):
        # Authenticate before accepting bytes. Legacy body-buffer limits remain unchanged.
        with context(request, project) as (_, user, roles):
            permit(roles)
        raw = bytearray()
        try:
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 26 * 1024 * 1024:
                    raise HTTPException(413, "Project ZIP exceeds 26 MiB")
        except RequestBodyTooLarge as exc:
            raise HTTPException(413, "Project ZIP exceeds 26 MiB") from exc
        try:
            content, policies = imports.parse(bytes(raw))
        except (ValueError, KeyError, TypeError, BadZipFile) as exc:
            raise HTTPException(
                422,
                "Invalid Project package; verify the versioned manifest, Task hashes and policy sources",
            ) from exc
        with context(request, project) as (c, user, roles):
            permit(roles)
            import hashlib

            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"archive_sha256": hashlib.sha256(raw).hexdigest()},
                    lambda: imports.store(c, project, user, content, policies),
                ),
                request,
            )

    @router.get("/groups/{identifier}/policies")
    def policies(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            imports.get(c, identifier)
            return wrap(runs.policies(c, identifier), request)

    @router.post("/groups/{identifier}/sample-verifiers")
    def preset(project: UUID, identifier: UUID, request: Request, adapter: str = "builtin"):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"group": str(identifier), "adapter": adapter},
                    lambda: runs.configure_sample(c, project, user, identifier, adapter),
                ),
                request,
            )

    @router.get("/groups/{identifier}/policies/sources/{source_id}")
    def policy_source(project: UUID, identifier: UUID, source_id: str, request: Request):
        import base64

        with context(request, project) as (c, user, roles):
            permit(roles)
            imports.get(c, identifier)
            source = next(
                (s for s in runs.policies(c, identifier)["sources"] if s["id"] == source_id), None
            )
            if not source:
                raise HTTPException(404, "Policy source not found")
            return Response(
                base64.b64decode(source["original_base64"], validate=True),
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": 'attachment; filename="'
                    + source["path"].rsplit("/", 1)[-1]
                    + '"',
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    @router.post("/mappings")
    def mapping(project: UUID, body: runs.Mapping, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: runs.save_mapping(c, project, user, body),
                ),
                request,
            )

    @router.post("/methods")
    def method(project: UUID, body: runs.MethodConfigure, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: runs.configure_method(c, project, user, body),
                ),
                request,
            )

    @router.post("/report-policy")
    def report_policy(project: UUID, body: review_policy.Configure, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: review_policy.configure(c, project, user, body),
                ),
                request,
            )

    @router.post("/plans")
    def plan(project: UUID, body: runs.Plan, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: runs.create_plan(c, project, user, body),
                ),
                request,
            )

    @router.post("/runs")
    def start(project: UUID, body: runs.Start, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c, project, user, request, body, lambda: runs.start(c, project, user, body)
                ),
                request,
            )

    @router.get("/runs/{identifier}")
    def result(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(views.view(c, identifier, **scope(request)), request)

    @router.post("/runs/{identifier}/review")
    def review(project: UUID, identifier: UUID, body: runs.ReportDecision, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: runs.decide(c, project, user, identifier, body),
                ),
                request,
            )

    @router.post("/runs/{identifier}/remediation")
    def remediation(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    scope(request),
                    lambda: views.save_pack(c, project, user, identifier, scope(request)),
                ),
                request,
            )

    @router.get("/runs/{identifier}/export")
    def export(
        project: UUID,
        identifier: UUID,
        request: Request,
        format: str = "pdf",
        expected_view_sha256: str = "",
    ):
        with context(request, project) as (c, user, roles):
            permit(roles)
            data = views.view(c, identifier, **scope(request))
            if not data["run"]["report_review"]["ready"]:
                raise HTTPException(409, "Report review is pending for this exact result")
            if expected_view_sha256 != data["view_sha256"]:
                raise HTTPException(409, "Report scope changed; refresh before exporting")
            import json

            if format == "json":
                body, mime, suffix = (
                    json.dumps(jsonable_encoder(data), indent=2).encode(),
                    "application/json",
                    "json",
                )
            elif format == "pdf":
                from anvil.benchmark_run_pdf import render

                body, mime, suffix = render(data), "application/pdf", "pdf"
            elif format == "jsonl":
                body, mime, suffix = (
                    (
                        "\n".join(
                            json.dumps(jsonable_encoder(r["sample"])) for r in data["remediation"]
                        )
                        + "\n"
                    ).encode(),
                    "application/x-ndjson",
                    "jsonl",
                )
            else:
                raise HTTPException(422, "Unknown export format")
            return Response(
                body,
                media_type=mime,
                headers={
                    "Content-Disposition": f'attachment; filename="anvil-benchmark-{identifier}.{suffix}"',
                    "Cache-Control": "no-store",
                    "X-Anvil-View-SHA256": data["view_sha256"],
                },
            )

    return router
