"""Generic contract endpoints beside the unchanged frozen Golden path."""

import os
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from anvil import auth
from anvil import praxis_template_registry as templates
from anvil.benchmark_storage import stage_private
from anvil.praxis_capabilities import catalogue
from anvil.praxis_generic_contract import (
    EXPORT,
    EXPORT_V2,
    CampaignExport,
    Export,
    ReusableExport,
    RevocationEvent,
    TemplateProposal,
    TemplateSpec,
    digest,
    load,
)
from anvil.praxis_generic_export import validate
from anvil.praxis_generic_resolution import resolve


def routes(access, context, wrap, idempotent):
    router = APIRouter(prefix="/generic")

    def enabled():
        if os.environ.get("ANVIL_PRAXIS_GENERIC_EXPORT_ENABLED") != "true":
            raise HTTPException(
                503, "Generic Praxis contract API is disabled; Anvil operator action required"
            )

    @router.get("/contracts")
    def contracts(project: UUID, request: Request):
        with access(request, project) as (c, _, roles):
            auth.require(roles, "admin", "rl-engineer")
            from anvil.golden_kyc_v7_candidate import CandidateExport
            from anvil.golden_kyc_v7_export import qualified_variants
            from anvil.praxis_case_registry import discover as case_datasets

            products = qualified_variants(c,project)
            v1_schema = TypeAdapter(Export | CandidateExport).json_schema() if products else Export.model_json_schema()

            return wrap(
                {
                    "contract": EXPORT,
                    "contracts": [EXPORT, EXPORT_V2],
                    "enabled": os.environ.get("ANVIL_PRAXIS_GENERIC_EXPORT_ENABLED") == "true",
                    "manifest_schema": v1_schema,
                    "qualified_product_variants": products,
                    "manifest_schemas": {
                        EXPORT: v1_schema,
                        EXPORT_V2: {
                            "oneOf": [
                                ReusableExport.model_json_schema(),
                                CampaignExport.model_json_schema(),
                            ]
                        },
                    },
                    "template_spec_schema": TemplateSpec.model_json_schema(),
                    "revocation_event_schema": RevocationEvent.model_json_schema(),
                    "capability_catalogue": catalogue(),
                    "case_datasets": case_datasets(c, project),
                    "supported_catalogue_versions": ["1.0.0", "1.1.0", "1.2.0", "1.3.0"],
                    "capability_catalogues": [
                        catalogue(v) for v in ("1.0.0", "1.1.0", "1.2.0", "1.3.0")
                    ],
                    "canonical_json": "RFC8785",
                    "authoring_schema_source": "/api/v1/integrations/anvil/templates/contracts (Praxis service)",
                    "hash": "sha256",
                    "limits": {
                        "compressed_bytes": 1048576,
                        "expanded_bytes": 30 * 1048576,
                        "file_bytes": 10 * 1048576,
                        "files": 1200,
                        "tasks_per_package": 200,
                    },
                    "valid_may_be_unknown": True,
                    "run_authority": "not_granted",
                    "paid_calls": False,
                },
                request,
            )

    async def process(project, request, resolving=False):
        with access(request, project, resolving) as (c, user, roles):
            auth.require(roles, *(("admin",) if resolving else ("admin", "rl-engineer")))
            enabled()
            if request.headers.get("content-type", "").split(";")[0].strip() != "application/zip":
                raise HTTPException(415, "Use raw application/zip bytes")
            raw = await request.body()
            if len(raw) > 1048576:
                raise HTTPException(413, "Generic export exceeds1MiB")
            from anvil.praxis_case_registry import lookup as dataset_lookup

            result, parsed = validate(
                raw,
                lambda ref: templates.lookup(c, project, ref),
                lambda ref: dataset_lookup(c, project, ref),
            )
            if resolving and result["valid"] is True:
                if result["anvil_requirements"]:
                    result["status"] = "anvil_blocked"
                else:
                    private_access = c.execute(
                        "SELECT anvil.benchmark_private_access(%s,'benchmark_eval',NULL::uuid) AS allowed",
                        (project,),
                    ).fetchone()["allowed"]
                    if not private_access:
                        result["status"] = "anvil_blocked"
                        result["anvil_requirements"] = [
                            {
                                "code": "AV_PRIVATE_STORAGE_ASSIGNMENT_REQUIRED",
                                "owner": "anvil",
                                "status": "blocked",
                            }
                        ]
                        return JSONResponse(wrap(result, request), status_code=409)
                    key = request.headers.get("Idempotency-Key", "")
                    if not key or len(key) > 200:
                        raise HTTPException(428, "Bounded Idempotency-Key required")
                    try:
                        prepared = stage_private(project, raw, "benchmark_eval", "application/zip")
                    except (OSError, RuntimeError):
                        result["status"] = "anvil_blocked"
                        result["anvil_requirements"] = [
                            {
                                "code": "AV_PRIVATE_STORAGE_UNAVAILABLE",
                                "owner": "anvil",
                                "status": "blocked",
                            }
                        ]
                    else:
                        # Hash/stage before project locks; preserve uncertain outcomes.
                        idempotent(
                            c,
                            project,
                            user,
                            request,
                            {"package_sha256": result["package_sha256"]},
                            lambda: {"accepted": True},
                        )
                        result = resolve(
                            c,
                            project,
                            user,
                            result,
                            parsed,
                            prepared,
                            client_id=getattr(request.state, "export_client_id", None),
                            auth_kind=getattr(request.state, "export_auth_kind", None),
                        )
                        if result.get("status") == "import_resolved":
                            from anvil.praxis_project_intake import store as store_project

                            result["imported_project"] = store_project(
                                c, project, user, result, parsed, prepared
                            )
            status = (
                422
                if result["valid"] is False
                else 409
                if result["valid"] is None or result["status"] == "anvil_blocked"
                else 200
            )
            return JSONResponse(wrap(result, request), status_code=status)

    @router.post(
        "/validate",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
            }
        },
    )
    async def validation(project: UUID, request: Request):
        return await process(project, request)

    @router.post(
        "/resolve",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
            }
        },
    )
    async def resolution(project: UUID, request: Request):
        return await process(project, request, True)

    @router.post("/templates")
    async def register(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            enabled()
            try:
                body = load(await request.body())
                TemplateSpec.model_validate(body)
            except (ValueError, ValidationError):
                raise HTTPException(
                    422, "Invalid bounded joint template spec; consult published schema"
                ) from None
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: templates.register(c, project, user, body),
                ),
                request,
            )

    def remote_error(exc):
        from anvil.praxis_template_client import PraxisCallError

        if not isinstance(exc, PraxisCallError):
            raise exc
        raise HTTPException(
            409,
            {
                "owner": "anvil",
                "code": exc.code,
                "outcome_unknown": exc.ambiguous,
                "upstream_code": exc.remote_code,
                "upstream_request_id": exc.request_id,
                "fix": "Praxis Admin must inspect the existing workflow draft and publish or retire it through the normal review flow."
                if exc.remote_code == "DRAFT_EXISTS"
                else "Anvil operator must reconcile the upstream response; do not alter task data or retry automatically.",
                "automatic_retry": False,
                "paid_calls": False,
            },
        ) from None

    @router.get("/praxis/contracts")
    def praxis_contracts(project: UUID, request: Request):
        from anvil.praxis_template_client import PraxisCallError, runtime_client

        with context(request, project) as (_, _, roles):
            auth.require(roles, "admin")
            enabled()
            try:
                result = runtime_client(project).contracts()
            except PraxisCallError as exc:
                remote_error(exc)
            return wrap(result, request)

    @router.post("/praxis/proposals")
    async def propose(project: UUID, request: Request):
        from anvil.praxis_template_client import PraxisCallError, runtime_client

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            enabled()
            try:
                raw = await request.body()
                if len(raw) > 1048576:
                    raise HTTPException(413, "Template proposal exceeds1MiB")
                body = load(raw)
                TemplateProposal.model_validate(body)
            except (ValueError, ValidationError):
                raise HTTPException(
                    422, "Use the six-field joint proposal; Praxis assigns identity/version"
                ) from None

            def submit():
                try:
                    # Stable content-derived remote identity survives a lost
                    # HTTP response/local rollback without creating another draft.
                    return runtime_client(project).propose(
                        body, idempotency_key="anvil-proposal-" + digest(body)
                    )
                except PraxisCallError as exc:
                    remote_error(exc)

            return wrap(idempotent(c, project, user, request, body, submit), request)

    @router.post("/praxis/proposals/{proposal}/accept-publication")
    def accept_praxis_publication(project: UUID, proposal: UUID, request: Request):
        from anvil.praxis_template_client import PraxisCallError, accept_publication, runtime_client

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            enabled()

            def accept():
                try:
                    return accept_publication(
                        c, project, user, runtime_client(project), str(proposal)
                    )
                except PraxisCallError as exc:
                    remote_error(exc)

            return wrap(
                idempotent(c, project, user, request, {"proposal_id": str(proposal)}, accept),
                request,
            )

    @router.post("/praxis/events/upgrade-qualifications")
    async def upgrade_qualification_events(project: UUID, request: Request):
        from anvil.praxis_template_delivery import upgrade_pending_qualifications

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            enabled()
            try:
                body = load(await request.body())
                if set(body) - {"after_event_id", "limit"}:
                    raise ValueError("Unknown upgrade argument")
                limit = body.get("limit", 100)
                cursor = body.get("after_event_id")
                if cursor is not None and not isinstance(cursor, str):
                    raise ValueError("UUID cursor required")
                after = UUID(cursor) if cursor is not None else None
                if type(limit) is not int or not 1 <= limit <= 1000:
                    raise ValueError("Bounded batch required")
            except (ValueError, TypeError):
                raise HTTPException(
                    422, "Use a bounded limit and optional event UUID cursor"
                ) from None
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: upgrade_pending_qualifications(
                        c, project, user, limit=limit, after=after
                    ),
                ),
                request,
            )

    @router.get("/praxis/events")
    def template_events(project: UUID, request: Request):
        from anvil.praxis_template_delivery import pending

        with context(request, project) as (c, _, roles):
            auth.require(roles, "admin")
            enabled()
            return wrap(
                {
                    "items": [
                        {
                            "id": str(e["id"]),
                            "kind": e["kind"],
                            "body_sha256": e["body_sha256"],
                            "event_key": e["event_key"],
                        }
                        for e in pending(c, project)
                    ]
                },
                request,
            )

    @router.post("/praxis/events/{event}/deliver")
    async def deliver_template_event(project: UUID, event: UUID, request: Request):
        from anvil.praxis_template_client import PraxisCallError, runtime_client
        from anvil.praxis_template_delivery import deliver

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            enabled()
            if not c.execute(
                "SELECT 1 FROM anvil.praxis_template_events WHERE project_id=%s AND id=%s",
                (project, event),
            ).fetchone():
                raise HTTPException(404, "Template event not found in this project")
            try:
                body = load(await request.body())
                if (
                    set(body) - {"reconciliation_confirmed"}
                    or type(body.get("reconciliation_confirmed", False)) is not bool
                ):
                    raise ValueError("Explicit reconciliation flag required")
            except ValueError:
                raise HTTPException(
                    422,
                    "Use reconciliation_confirmed:true only after reconciling a prior uncertain send",
                ) from None
            # Serialize the uncertainty check with deliver() and other event
            # attempts; a concurrent ambiguous result cannot slip between them.
            c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
            if c.execute(
                "SELECT 1 FROM anvil.praxis_template_delivery_attempts WHERE project_id=%s AND event_id=%s AND status='ambiguous'",
                (project, event),
            ).fetchone() and not body.get("reconciliation_confirmed"):
                raise HTTPException(
                    409,
                    "Anvil operator must reconcile the previous uncertain event delivery before an explicit retry",
                )

            def send():
                try:
                    return deliver(c, project, user, event, runtime_client(project))
                except PraxisCallError as exc:
                    remote_error(exc)

            return wrap(
                idempotent(c, project, user, request, {"event_id": str(event), **body}, send),
                request,
            )

    @router.get("/templates")
    def listing(project: UUID, request: Request):
        with context(request, project) as (c, _, roles):
            auth.require(roles, "admin", "rl-engineer")
            enabled()
            rows = c.execute(
                "SELECT * FROM anvil.praxis_template_versions WHERE project_id=%s ORDER BY created_at DESC,id DESC LIMIT 100",
                (project,),
            ).fetchall()
            return wrap([templates.public(row) for row in rows], request)

    @router.post("/templates/{template}/qualify")
    def qualify(project: UUID, template: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            enabled()
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"template_id": str(template)},
                    lambda: templates.qualify(c, project, user, template),
                ),
                request,
            )

    @router.post("/qualifications/{qualification}/revoke")
    async def revoke(project: UUID, qualification: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            enabled()
            body = load(await request.body())
            if (
                set(body) != {"reason"}
                or not isinstance(body["reason"], str)
                or not 1 <= len(body["reason"]) <= 1000
            ):
                raise HTTPException(422, "Bounded nonsecret revocation reason required")
            return wrap(
                jsonable_encoder(
                    idempotent(
                        c,
                        project,
                        user,
                        request,
                        body,
                        lambda: templates.revoke(c, project, user, qualification, body["reason"]),
                    )
                ),
                request,
            )

    @router.get("/notification-deliveries")
    def notifications(project: UUID, request: Request):
        from anvil.praxis_template_delivery import pending

        with context(request, project) as (c, _, roles):
            auth.require(roles, "admin")
            enabled()
            return wrap(
                [
                    {
                        "event_id": str(row["id"]),
                        "kind": row["kind"],
                        "body_sha256": row["body_sha256"],
                        "status": "pending",
                    }
                    for row in pending(c, project)
                ],
                request,
            )

    return router
