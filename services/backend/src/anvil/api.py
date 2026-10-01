import logging
from contextlib import contextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from psycopg import IntegrityError
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from anvil import artifacts, auth, domain, fixtures
from anvil.db import audit, digest, one, transaction, uid
from anvil.delivery import routes as delivery_routes
from anvil.evaluation import routes as evaluation_routes
from anvil.external_results import routes as external_routes
from anvil.factory import routes as factory_routes
from anvil.graph import routes as graph_routes
from anvil.intake import routes as intake_routes
from anvil.plans import routes as plan_routes
from anvil.provider_api import routes as provider_routes
from anvil.readiness import routes as readiness_routes
from anvil.reports import prepare_report
from anvil.reports import routes as report_routes
from anvil.request_limits import RequestLimits
from anvil.schemas import Decision, FixtureImport, Rights, Withdrawal
from anvil.support import routes as support_routes
from anvil.task_imports import routes as task_import_routes

app = FastAPI(title="ADI Anvil", version="0.1.0")
app.add_middleware(RequestLimits)
app.include_router(auth.router)


@app.middleware("http")
async def security_headers(request, call_next):
    request.state.request_id = uid()
    try:
        response = await call_next(request)
    except Exception as exc:
        logging.getLogger("anvil.api").error(
            "request=%s code=%s", request.state.request_id, type(exc).__name__
        )
        response = JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "Unexpected server error; retain the request ID for diagnosis",
                    "retryable": False,
                    "request_id": request.state.request_id,
                }
            },
            status_code=500,
        )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse(
        {
            "error": {
                "code": f"http_{exc.status_code}",
                "message": exc.detail,
                "retryable": False,
                "request_id": request.state.request_id,
            }
        },
        status_code=exc.status_code,
    )


@app.exception_handler(ValidationError)
@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(
        {
            "error": {
                "code": "validation",
                "message": "Invalid input",
                "field_errors": errors,
                "retryable": False,
                "request_id": request.state.request_id,
            }
        },
        status_code=422,
    )


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(
        {
            "error": {
                "code": "conflict",
                "message": "Conflicting or invalid scoped record",
                "retryable": False,
                "request_id": request.state.request_id,
            }
        },
        status_code=409,
    )


def wrap(data, request):
    return {"data": data, "meta": {"request_id": request.state.request_id}}


@contextmanager
def context(request, project):
    user = auth.identity(request)
    with transaction(project, user["id"]) as c:
        roles = auth.project_roles(c, project, user["id"])
        yield c, user["id"], roles


def idempotent(c, project, user, request, body, fn):
    key = request.headers.get("idempotency-key")
    if not key or len(key) > 200:
        raise HTTPException(428, "Idempotency-Key required (maximum 200 characters)")
    scope = request.url.path
    # Project serialization prevents duplicate commands from racing before ledger insert.
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    h = digest(jsonable_encoder(body))
    old = one(
        c,
        "SELECT * FROM anvil.idempotency WHERE project_id=%s AND user_id=%s AND route=%s AND key=%s",
        (project, user, scope, key),
    )
    if old:
        if old["body_hash"] != h:
            raise HTTPException(409, "Idempotency key reused with changed body")
        return old["response"]
    result = jsonable_encoder(fn())
    c.execute(
        "INSERT INTO anvil.idempotency VALUES(%s,%s,%s,%s,%s,%s)",
        (project, user, scope, key, h, Jsonb(result)),
    )
    return result


app.include_router(evaluation_routes(context, wrap, idempotent))
app.include_router(graph_routes(context, wrap))
app.include_router(report_routes(context, wrap, idempotent))
app.include_router(provider_routes(context, wrap, idempotent))
app.include_router(intake_routes(context, wrap, idempotent))
app.include_router(external_routes(context, wrap, idempotent))
app.include_router(delivery_routes(context, wrap, idempotent))
app.include_router(readiness_routes(context, wrap, idempotent))
app.include_router(task_import_routes(context, wrap, idempotent))
app.include_router(factory_routes(context, wrap, idempotent))
app.include_router(plan_routes(context, wrap, idempotent))
app.include_router(support_routes(context, wrap, idempotent))

from anvil.marketing_api import routes as marketing_routes  # noqa: E402

app.include_router(marketing_routes(context, wrap, idempotent))

KINDS = {
    "objectives": "objective",
    "cases": "case",
    "tasks": "task",
    "rubrics": "rubric",
    "suites": "suite",
    "protocols": "protocol",
    "findings": "finding",
    "reports": "report",
}


def visibility(roles, kind):
    if kind == "objective":
        auth.require(roles, *domain.CONTENT_ROLES, "sales")
    else:
        auth.require(roles, *domain.CONTENT_ROLES)


@app.get("/api/v1/health")
def health():
    with transaction() as c:
        c.execute("SELECT 1")
    return {"data": {"api": "ready", "database": "ready", "live_inference": "disabled"}}


@app.get("/api/v1/projects/{project}/members")
def members(project: UUID, request: Request):
    with context(request, project) as (c, user, roles):
        auth.require(roles, *domain.CONTENT_ROLES, "admin")
        return wrap(
            c.execute(
                "SELECT u.id,u.name,m.role FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id WHERE m.project_id=%s AND m.active AND u.active ORDER BY u.name",
                (project,),
            ).fetchall(),
            request,
        )


@app.post("/api/v1/projects/{project}/fixtures/import")
def import_fixtures(project: UUID, body: FixtureImport, request: Request):
    with context(request, project) as (c, user, roles):
        auth.require(roles, "data-engineer")
        result = idempotent(
            c, project, user, request, body, lambda: fixtures.load(c, project, user, body)
        )
        return wrap(result, request)


@app.post("/api/v1/projects/{project}/artifacts")
async def upload(project: UUID, request: Request, file: UploadFile, purpose: str | None = None):
    with context(request, project) as (c, user, roles):
        if purpose not in (None, "task_import"):
            raise HTTPException(422, "Unknown upload purpose")
        auth.require(roles, *(["data-engineer", "researcher"] if purpose else ["data-engineer"]))
        filename = (file.filename or "").replace("\\", "/").split("/")[-1][:255]
        extension = filename.rsplit(".", 1)[-1].lower()
        if purpose and extension not in ("csv", "jsonl"):
            raise HTTPException(422, "Task imports accept .csv or .jsonl files only")
        data = await file.read(25 * 1024 * 1024 + 1)
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(413, "File exceeds 25 MiB")
        aid = artifacts.store(
            c,
            project,
            data,
            "hidden_reference" if purpose else "internal",
            ("text/csv" if extension == "csv" else "application/x-ndjson")
            if purpose
            else "application/octet-stream",
            "user_upload",
            "quarantined",
        )
        c.execute(
            "UPDATE anvil.artifacts SET original_filename=%s,upload_purpose=%s,uploaded_by=%s WHERE id=%s",
            (filename, purpose, user, aid),
        )
        audit(c, project, user, "artifact.quarantined", aid)
        return wrap(
            {"id": aid, "scan_status": "quarantined", "reason": "Qualified scanner unavailable"},
            request,
        )


@app.get("/api/v1/projects/{project}/artifacts/{aid}/content")
def artifact_content(project: UUID, aid: UUID, request: Request):
    with context(request, project) as (c, user, roles):
        auth.require(roles, *domain.CONTENT_ROLES)
        a = one(c, "SELECT * FROM anvil.artifacts WHERE id=%s", (aid,))
        if not a:
            raise HTTPException(404, "Artifact not found")
        if a["classification"] == "hidden_reference":
            auth.require(roles, "data-engineer", "reviewer", "advisor", "adjudicator")
            if not roles.intersection({"data-engineer"}):
                linked = c.execute(
                    "SELECT v.content FROM anvil.artifact_links l JOIN anvil.revisions v ON v.id=l.revision_id WHERE l.artifact_id=%s",
                    (aid,),
                ).fetchall()
                if not any(
                    str(user) in (x["content"].get("reviewer_id"), x["content"].get("advisor_id"))
                    for x in linked
                ):
                    raise HTTPException(403, "Reference access requires an assigned review")
        data = artifacts.read(c, aid)
        audit(c, project, user, "artifact.read", aid)
        return Response(
            data,
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{aid}.txt"'},
        )


@app.post("/api/v1/projects/{project}/cases/{rid}/rights")
def case_rights(project: UUID, rid: UUID, body: Rights, request: Request):
    with context(request, project) as (c, user, roles):
        auth.require(roles, "product-owner")
        if not one(
            c,
            "SELECT 1 FROM anvil.project_assignments WHERE user_id=%s AND capability='rights_reviewer' AND active",
            (user,),
        ):
            raise HTTPException(403, "Designated rights reviewer required")

        def change():
            r = domain.get_resource(c, rid, True)
            if r["kind"] != "case":
                raise HTTPException(404, "Case not found")
            domain.etag(r, request.headers.get("if-match"))
            if str(r["created_by"]) == str(user):
                raise HTTPException(409, "Independent rights review required")
            c.execute(
                """INSERT INTO anvil.rights_grants(id,project_id,source_revision_id,operation,destination,status,reviewed_by,evidence,expires_at)
                         VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(source_revision_id,operation,destination)
                         DO UPDATE SET status=excluded.status,reviewed_by=excluded.reviewed_by,evidence=excluded.evidence,expires_at=excluded.expires_at,row_version=anvil.rights_grants.row_version+1""",
                (
                    uid(),
                    project,
                    r["current_revision_id"],
                    body.operation,
                    body.destination,
                    body.status,
                    user,
                    body.evidence,
                    body.expires_at,
                ),
            )
            audit(
                c,
                project,
                user,
                "rights." + body.status,
                rid,
                {
                    "operation": body.operation,
                    "destination": body.destination,
                    "source_revision_id": str(r["current_revision_id"]),
                    "expires_at": body.expires_at.isoformat() if body.expires_at else None,
                },
            )
            return {
                "status": body.status,
                "source_revision_id": str(r["current_revision_id"]),
                "expires_at": body.expires_at.isoformat() if body.expires_at else None,
            }

        return wrap(idempotent(c, project, user, request, body, change), request)


@app.get("/api/v1/projects/{project}/{collection}")
def list_resources(
    project: UUID,
    collection: str,
    request: Request,
    limit: int = 25,
    after: UUID | None = None,
    q: str = Query(default="", max_length=200),
):
    if collection not in KINDS:
        raise HTTPException(404, "Collection not found")
    if not 1 <= limit <= 100:
        raise HTTPException(422, "Limit must be 1..100")
    with context(request, project) as (c, user, roles):
        kind = KINDS[collection]
        visibility(roles, kind)
        rows = c.execute(
            """SELECT r.*,v.content,v.content_hash,v.revision FROM anvil.resources r
                          JOIN anvil.revisions v ON v.id=r.current_revision_id
                          WHERE kind=%s AND (%s::uuid IS NULL OR r.id>%s)
                          AND strpos(lower(concat_ws(' ',v.content->>'title',v.content->>'external_case_id',r.lifecycle)),lower(%s))>0
                          ORDER BY r.id LIMIT %s""",
            (kind, after, after, q, limit + 1),
        ).fetchall()
        counts = one(
            c,
            """SELECT count(*) AS inventory_total,
            count(*) FILTER(WHERE strpos(lower(concat_ws(' ',v.content->>'title',v.content->>'external_case_id',r.lifecycle)),lower(%s))>0) AS matching_total
            FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE kind=%s""",
            (q, kind),
        )
        result = wrap(rows[:limit], request)
        result["meta"].update(
            {**counts, "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None}
        )
        if kind == "case":
            result["meta"].update(
                one(
                    c,
                    """SELECT count(*) source_versions FROM anvil.revisions v
                JOIN anvil.resources r ON r.id=v.resource_id WHERE r.kind='case'""",
                )
            )
            result["meta"]["source_families"] = one(
                c,
                """SELECT count(DISTINCT coalesce(v.content->>'source_family_key',v.content->>'family_id')) n
                FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE r.kind='case'""",
            )["n"]
            result["meta"]["qualified_sources"] = one(
                c,
                """SELECT count(*) n FROM anvil.resources source WHERE source.kind='case'
                AND EXISTS(SELECT 1 FROM anvil.resources task JOIN anvil.revisions v ON v.id=task.current_revision_id
                    WHERE task.kind='task' AND task.lifecycle='published' AND v.content->>'source_revision_id'=source.current_revision_id::text)""",
            )["n"]
        return result


@app.get("/api/v1/projects/{project}/{collection}/{rid}")
def detail(project: UUID, collection: str, rid: UUID, request: Request):
    if collection not in KINDS:
        raise HTTPException(404, "Collection not found")
    with context(request, project) as (c, user, roles):
        visibility(roles, KINDS[collection])
        r = domain.get_resource(c, rid)
        if r["kind"] != KINDS[collection]:
            raise HTTPException(404, "Resource not found")
        r["reviews"] = c.execute(
            "SELECT purpose,decision,rationale,reviewer_id FROM anvil.review_decisions WHERE revision_id=%s",
            (r["current_revision_id"],),
        ).fetchall()
        if r["kind"] == "case":
            r["rights"] = c.execute(
                "SELECT operation,destination,status,evidence FROM anvil.rights_grants WHERE source_revision_id=%s",
                (r["current_revision_id"],),
            ).fetchall()
        return wrap(r, request)


@app.post("/api/v1/projects/{project}/{collection}", status_code=201)
def create_resource(project: UUID, collection: str, body: dict, request: Request):
    if collection not in KINDS:
        raise HTTPException(404, "Collection not found")
    with context(request, project) as (c, user, roles):
        auth.require(roles, "researcher")
        kind = KINDS[collection]

        def act():
            content = domain.validate_content(c, project, kind, body)
            if kind == "report":
                content = prepare_report(c, content)
            r = domain.create(c, project, user, kind, content)
            if kind in ("suite", "protocol", "finding"):
                domain.qualify(c, r)
            return r

        return wrap(idempotent(c, project, user, request, body, act), request)


@app.patch("/api/v1/projects/{project}/{collection}/{rid}/draft")
def edit_resource(project: UUID, collection: str, rid: UUID, body: dict, request: Request):
    with context(request, project) as (c, user, roles):
        auth.require(roles, "researcher", "data-engineer")

        def act():
            r = domain.get_resource(c, rid, True)
            if KINDS.get(collection) != r["kind"]:
                raise HTTPException(404, "Resource not found")
            domain.etag(r, request.headers.get("if-match"))
            if r["lifecycle"] not in ("draft", "changes_requested"):
                raise HTTPException(409, "Submitted content is immutable; create a successor")
            if r["created_by"] != user:
                raise HTTPException(403, "Only author can edit this draft")
            content = domain.validate_content(c, project, r["kind"], body)
            if r["kind"] == "report":
                content = prepare_report(c, content)
            return domain.revise(c, r, user, content)

        return wrap(idempotent(c, project, user, request, body, act), request)


@app.post("/api/v1/projects/{project}/{collection}/{rid}/successor")
def successor(project: UUID, collection: str, rid: UUID, body: dict, request: Request):
    with context(request, project) as (c, user, roles):
        auth.require(roles, "researcher", "data-engineer")

        def act():
            r = domain.get_resource(c, rid, True)
            if KINDS.get(collection) != r["kind"]:
                raise HTTPException(404, "Resource not found")
            domain.etag(r, request.headers.get("if-match"))
            if r["created_by"] != user:
                raise HTTPException(403, "Only author can create a successor")
            if r["lifecycle"] in ("draft", "changes_requested"):
                raise HTTPException(409, "Edit the existing draft instead")
            content = domain.validate_content(c, project, r["kind"], body)
            if r["kind"] == "report":
                content = prepare_report(c, content)
            return domain.revise(c, r, user, content)

        return wrap(idempotent(c, project, user, request, body, act), request)


@app.post("/api/v1/projects/{project}/{collection}/{rid}/withdraw")
def withdraw(project: UUID, collection: str, rid: UUID, body: Withdrawal, request: Request):
    with context(request, project) as (c, user, roles):
        auth.require(roles, "researcher", "data-engineer", "product-owner")

        def act():
            r = domain.get_resource(c, rid, True)
            if KINDS.get(collection) != r["kind"]:
                raise HTTPException(404, "Resource not found")
            domain.etag(r, request.headers.get("if-match"))
            if r["created_by"] != user and "product-owner" not in roles:
                raise HTTPException(403, "Author or Product Owner required for withdrawal")
            audit(c, project, user, "withdrawal.reason", rid, {"reason": body.reason})
            return domain.move(c, r, user, "withdrawn")

        return wrap(idempotent(c, project, user, request, body, act), request)


@app.post("/api/v1/projects/{project}/{collection}/{rid}/decisions")
def decision(project: UUID, collection: str, rid: UUID, body: Decision, request: Request):
    with context(request, project) as (c, user, roles):

        def act():
            r = domain.get_resource(c, rid, True)
            if KINDS.get(collection) != r["kind"]:
                raise HTTPException(404, "Resource not found")
            domain.etag(r, request.headers.get("if-match"))
            result = domain.decide(c, r, user, roles, body)
            if result["kind"] == "report" and result["lifecycle"] == "approved":
                from anvil.evaluation import enqueue

                enqueue(
                    c,
                    project,
                    "sales_kit_render",
                    result["id"],
                    "approved-kit:" + str(result["current_revision_id"]),
                )
            return result

        return wrap(idempotent(c, project, user, request, body, act), request)


@app.post("/api/v1/projects/{project}/{collection}/{rid}/{action}")
def transition(project: UUID, collection: str, rid: UUID, action: str, request: Request):
    with context(request, project) as (c, user, roles):

        def act():
            r = domain.get_resource(c, rid, True)
            if KINDS.get(collection) != r["kind"]:
                raise HTTPException(404, "Resource not found")
            domain.etag(r, request.headers.get("if-match"))
            if action == "submit":
                auth.require(roles, "researcher", "data-engineer")
                if r["lifecycle"] != "draft":
                    raise HTTPException(409, "Only drafts may be submitted")
                domain.qualify(c, r)
                submitted = domain.move(c, r, user, "submitted")
                if r["kind"] == "finding":
                    # D-SIMPLE: findings are covered by the report's Product Owner approval.
                    return domain.move(c, submitted, user, "approved")
                return submitted
            if action == "publish" and r["kind"] == "task":
                auth.require(roles, "data-engineer")
                if r["lifecycle"] != "qualified":
                    raise HTTPException(409, "Qualification reviews required")
                domain.qualify(c, r)
                return domain.move(c, r, user, "published")
            if action == "freeze" and r["kind"] == "suite":
                auth.require(roles, "researcher")
                if r["lifecycle"] != "approved":
                    raise HTTPException(409, "Independent suite review required")
                domain.qualify(c, r)
                return domain.move(c, r, user, "frozen")
            raise HTTPException(422, "Unsupported transition")

        return wrap(idempotent(c, project, user, request, {}, act), request)
