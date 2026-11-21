"""Authenticated project-scoped configuration, Run and exact-scope export endpoints."""

from datetime import timedelta
from typing import Literal
from uuid import UUID
from zipfile import BadZipFile

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from anvil import auth
from anvil import benchmark_business_fixture as fixture
from anvil import benchmark_project_import as imports
from anvil import benchmark_report_policy as review_policy
from anvil import benchmark_run_views as views
from anvil import benchmark_runs as runs
from anvil.db import audit, uid
from anvil.request_limits import RequestBodyTooLarge


class ReferenceStorageConsent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmation: Literal['allow_my_protected_reference_import_for_8_hours']


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/benchmark")

    def permit(roles):
        auth.require(roles, "admin", "rl-engineer")

    @router.get('/reference-storage-access')
    def reference_storage_access(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, 'admin')
            allowed = c.execute(
                "SELECT anvil.benchmark_private_access(%s,'benchmark_eval',NULL::uuid) AS allowed",
                (project,),
            ).fetchone()['allowed']
            own = c.execute(
                "SELECT id,expires_at FROM anvil.benchmark_private_assignments a "
                "WHERE a.project_id=%s AND a.user_id=%s AND a.granted_by=%s "
                "AND a.scope='source_review' AND a.artifact_id IS NULL AND a.expires_at>now() "
                "AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r "
                "WHERE r.project_id=a.project_id AND r.assignment_id=a.id) "
                "ORDER BY a.created_at DESC,a.id DESC LIMIT 1", (project, user, user),
            ).fetchone()
            return wrap({'allowed': allowed, 'scope': 'source_review',
                         'assignment_id': own['id'] if own else None,
                         'expires_at': own['expires_at'] if own else None,
                         'paid_calls': False, 'review_approval': False}, request)

    @router.post('/reference-storage-access')
    def grant_reference_storage(project: UUID, body: ReferenceStorageConsent, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, 'admin')

            def grant():
                # The real authenticated Admin can grant only their own existing
                # source-review duty. No recipient, role, scope or expiry is accepted.
                c.execute('SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE', (project,))
                old = c.execute(
                    "SELECT id,expires_at FROM anvil.benchmark_private_assignments a "
                    "WHERE a.project_id=%s AND a.user_id=%s AND a.granted_by=%s "
                    "AND a.scope='source_review' AND a.artifact_id IS NULL AND a.expires_at>now() "
                    "AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r "
                    "WHERE r.project_id=a.project_id AND r.assignment_id=a.id) "
                    "ORDER BY a.created_at DESC,a.id DESC LIMIT 1", (project, user, user),
                ).fetchone()
                if old is None:
                    old = c.execute(
                        "INSERT INTO anvil.benchmark_private_assignments"
                        "(id,project_id,user_id,scope,artifact_id,granted_by,expires_at) "
                        "VALUES(%s,%s,%s,'source_review',NULL,%s,now()+%s) RETURNING id,expires_at",
                        (uid(), project, user, user, timedelta(hours=8)),
                    ).fetchone()
                    audit(c, project, user, 'benchmark.reference_storage_access_granted', old['id'],
                          {'scope': 'source_review', 'recipient': str(user),
                           'expires_at': old['expires_at'].isoformat(),
                           'purpose': 'approved_task_reference_import', 'review_approval': False,
                           'paid_calls': False})
                return {'assignment_id': old['id'], 'expires_at': old['expires_at'],
                        'scope': 'source_review', 'allowed': True,
                        'review_approval': False, 'paid_calls': False}

            receipt = idempotent(c, project, user, request, body.model_dump(), grant)
            # A replay is a historical grant receipt, not evidence of current access.
            allowed = c.execute(
                "SELECT anvil.benchmark_private_access(%s,'benchmark_eval',NULL::uuid) AS allowed",
                (project,),
            ).fetchone()['allowed']
            return wrap(receipt | {'allowed': allowed}, request)

    @router.post('/reference-storage-access/{assignment}/revoke')
    def revoke_reference_storage(project: UUID, assignment: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, 'admin')

            def revoke():
                row = c.execute(
                    "SELECT id FROM anvil.benchmark_private_assignments WHERE project_id=%s "
                    "AND id=%s AND user_id=%s AND granted_by=%s AND scope='source_review' "
                    "AND artifact_id IS NULL", (project, assignment, user, user),
                ).fetchone()
                if row is None:
                    raise HTTPException(404, 'Own source-review assignment not found')
                c.execute(
                    "INSERT INTO anvil.benchmark_private_revocations"
                    "(project_id,assignment_id,revoked_by,rationale) VALUES(%s,%s,%s,%s) "
                    "ON CONFLICT(assignment_id) DO NOTHING",
                    (project, assignment, user, 'Admin ended their temporary reference-import access'),
                )
                audit(c, project, user, 'benchmark.reference_storage_access_revoked', assignment)
                return {'assignment_id': assignment, 'revoked': True, 'paid_calls': False}

            return wrap(idempotent(c, project, user, request, {'assignment': str(assignment)}, revoke), request)

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
            if "sme-reviewer" in roles and not {"admin", "rl-engineer"} & roles:
                from anvil.expert_reviews import navigation

                return wrap(navigation(c, project), request)
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
            from anvil.environment_execution import source_hash as environment_source_hash
            from anvil.golden_kyc_anvil import SCHEMA as GOLDEN_SCHEMA
            from anvil.golden_kyc_anvil import source_hash as golden_source_hash

            return wrap(
                {
                    "groups": [imports.public_group(g) for g in groups],
                    "plans": [
                        p
                        | {
                            "runnable": p["snapshot"]["source_sha256"]
                            == (
                                golden_source_hash()
                                if p["snapshot"].get("schema_version") == GOLDEN_SCHEMA
                                else environment_source_hash()
                                if p["snapshot"].get("schema_version")
                                == "anvil.environment-execution-plan.v1"
                                else current_source
                            )
                        }
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
        # The same Import action accepts the existing authored-task export wire;
        # it is not converted into legacy output-field grading or new authored tasks.
        try:
            files = imports.archive_files(bytes(raw))
        except (ValueError, KeyError, TypeError, BadZipFile) as exc:
            raise HTTPException(422, "Invalid bounded Project ZIP") from exc
        if "praxis-export.json" in files:
            import os

            from anvil import praxis_template_registry as templates
            from anvil.benchmark_storage import describe_private, stage_private
            from anvil.praxis_case_registry import lookup as dataset_lookup
            from anvil.praxis_generic_export import validate as validate_authored
            from anvil.praxis_project_intake import store as store_authored
            from anvil.praxis_validation_report import binding_assessment, report

            with context(request, project) as (c, user, roles):
                auth.require(roles, "admin")
                if os.environ.get("ANVIL_PRAXIS_GENERIC_EXPORT_ENABLED") != "true":
                    raise HTTPException(
                        503,
                        "Anvil authored-export import is disabled; operator provisioning required",
                    )
                if len(raw) > 1048576:
                    raise HTTPException(
                        413, "Authored export exceeds the existing1MiB contract limit"
                    )
                validation, parsed = validate_authored(
                    bytes(raw),
                    lambda ref: templates.lookup(c, project, ref),
                    lambda ref: dataset_lookup(c, project, ref),
                )
                if validation["valid"] is not True:
                    raise HTTPException(
                        422 if validation["valid"] is False else 409,
                        report(validation, request.state.request_id),
                    )
                if not c.execute(
                    "SELECT anvil.benchmark_private_access(%s,'benchmark_eval',NULL::uuid) AS allowed",
                    (project,),
                ).fetchone()["allowed"]:
                    raise HTTPException(
                        409, report(validation | {
                            'code': 'AV_PRIVATE_STORAGE_ASSIGNMENT_REQUIRED', 'owner': 'anvil',
                            'anvil_requirements': validation['anvil_requirements'] + [{
                                'code': 'AV_PRIVATE_STORAGE_ASSIGNMENT_REQUIRED',
                                'owner': 'anvil', 'status': 'blocked',
                            }],
                        }, request.state.request_id, {
                            'status': 'blocked', 'owner': 'anvil',
                            'reason': 'protected_reference_import_access_required',
                            'execution_setup_ready': False, 'paid_dispatch_authorized': False,
                        })
                    )
                prepared = describe_private(project, raw, "benchmark_eval", "application/zip")

                def save_authored():
                    resolution = None
                    if not validation["anvil_requirements"]:
                        from anvil.praxis_generic_resolution import resolve

                        resolution = resolve(c, project, user, validation, parsed, prepared)
                    stored = store_authored(c, project, user, validation, parsed, prepared)
                    return stored | {
                        "validation": validation,
                        "resolution": resolution,
                        "execution_ready": False,
                    }

                result = idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"package_sha256": validation["package_sha256"]},
                    save_authored,
                )
                response = wrap(result | {
                    'validation': report(result['validation'], request.state.request_id,
                                         binding_assessment(c, project, result['validation'])),
                }, request)
                # SQL changes remain uncommitted. Publish only after validation,
                # intake, idempotency and response construction all succeeded.
                stage_private(project, raw, "benchmark_eval", "application/zip")
                return response
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
            if "sme-reviewer" in roles and not {"admin", "rl-engineer"} & roles:
                from anvil.expert_reviews import projection

                return wrap(projection(c, project, identifier, roles), request)
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
