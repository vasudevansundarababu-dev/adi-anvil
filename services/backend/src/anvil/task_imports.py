"""Task dataset intake using existing scoped artifacts, audit and command ledger."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field

from anvil import artifacts, auth, domain, ingestion
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.schemas import Strict
from anvil.task_parser import parse


class Import(Strict):
    artifact_id: UUID
    dataset_id: UUID | None = None
    mapping: dict[str, str] = Field(default_factory=dict, max_length=12)


class Mapping(Strict):
    mapping: dict[str, str] = Field(max_length=12)
    revision: int = Field(ge=1)


class Publish(Strict):
    revision: int = Field(ge=1)
    normalized_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Attach(Strict):
    version_id: UUID


def approved_objective(c, objective):
    resource = domain.get_resource(c, objective)
    if resource["kind"] != "objective" or resource["lifecycle"] != "approved":
        raise HTTPException(409, "An approved Research Objective is required")
    return resource


def version(c, vid, objective=None):
    result = one(
        c, "SELECT * FROM anvil.dataset_versions WHERE id=%s AND status='published'", (vid,)
    )
    if not result:
        raise HTTPException(409, "Published DatasetVersion not found in this project")
    if objective is not None and str(result["objective_id"]) != str(objective):
        raise HTTPException(409, "Dataset and suite must belong to the same objective")
    return result


def public_version(item):
    return {**item, "version_id": item["id"], "counts": item["validation"]["counts"]}


def batch(c, iid):
    row = one(c, "SELECT * FROM anvil.task_imports WHERE id=%s", (iid,))
    if not row:
        raise HTTPException(404, "Task import not found")
    return row


def preview(c, item):
    source = one(
        c,
        "SELECT original_filename,sha256,byte_size,mime_type FROM anvil.artifacts WHERE id=%s",
        (item["source_artifact_id"],),
    )
    job = one(
        c,
        "SELECT *,EXTRACT(EPOCH FROM coalesce(finished_at,now())-started_at)::int AS elapsed_seconds FROM anvil.ingestion_jobs WHERE import_id=%s AND import_revision=%s",
        (item["id"], item["revision"]),
    )
    return {
        k: item[k]
        for k in (
            "id",
            "dataset_id",
            "status",
            "revision",
            "mapping",
            "normalized_sha256",
            "published_version_id",
        )
    } | {
        "source": source,
        **item["validation"],
        "job": job,
        "status": job["state"]
        if job and job["state"] in ("failed", "cancelled")
        else item["status"],
        "preview": [
            {
                "row": r["row"],
                "spec": {k: v for k, v in r["spec"].items() if k != "reference"},
                "has_reference": "reference" in r["spec"],
            }
            for r in item["normalized"][:20]
        ],
    }


def validate_source(c, aid, mapping):
    source = one(
        c, "SELECT * FROM anvil.artifacts WHERE id=%s AND upload_purpose='task_import'", (aid,)
    )
    if not source:
        raise HTTPException(404, "Upload a CSV or JSONL artifact for task import first")
    try:
        result = parse(
            artifacts.read(c, aid, structured_import=True), source["original_filename"], mapping
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return source, result


def run_snapshot(c, vid, protocol):
    objective = domain.get_revision(c, protocol["objective_revision_id"], "objective", ["approved"])
    item = version(c, vid, objective["resource_id"])
    domain.get_revision(c, protocol["suite_revision_id"], "suite", ["frozen"])
    if not one(
        c,
        "SELECT 1 FROM anvil.suite_datasets WHERE suite_revision_id=%s AND version_id=%s",
        (protocol["suite_revision_id"], vid),
    ):
        raise HTTPException(
            409, "Attach this exact DatasetVersion to the protocol's suite revision first"
        )
    return {
        "version_id": str(item["id"]),
        "dataset_id": str(item["dataset_id"]),
        "version_number": item["version_number"],
        "task_schema_version": item["schema_version"],
        "normalized_sha256": item["normalized_sha256"],
        "source_sha256": item["source"]["sha256"],
        "task_count": item["validation"]["counts"]["valid"],
        "objective_id": str(item["objective_id"]),
        "objective_revision_id": str(protocol["objective_revision_id"]),
        "suite_revision_id": str(protocol["suite_revision_id"]),
        "execution_readiness": "blocked_pending_task_qualification_and_supported_adapter",
    }


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}")

    @router.post("/objectives/{oid}/task-imports")
    def create(project: UUID, oid: UUID, body: Import, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "data-engineer")

            def act():
                objective = approved_objective(c, oid)
                source = one(
                    c, "SELECT uploaded_by FROM anvil.artifacts WHERE id=%s", (body.artifact_id,)
                )
                if not source or (
                    str(source["uploaded_by"]) != str(user) and "data-engineer" not in roles
                ):
                    raise HTTPException(403, "Use your own upload or ask a project Data Engineer")
                source = one(
                    c,
                    "SELECT * FROM anvil.artifacts WHERE id=%s AND upload_purpose='task_import'",
                    (body.artifact_id,),
                )
                if not source:
                    raise HTTPException(404, "Upload a CSV or JSONL task source first")
                result = {
                    "columns": [],
                    "errors": [],
                    "counts": {"received": 0, "valid": 0, "invalid": 0, "duplicates": 0},
                }
                did = str(body.dataset_id) if body.dataset_id else uid()
                if body.dataset_id:
                    dataset = one(c, "SELECT * FROM anvil.task_datasets WHERE id=%s", (did,))
                    if not dataset or str(dataset["objective_id"]) != str(oid):
                        raise HTTPException(
                            409, "Dataset must belong to this objective and project"
                        )
                else:
                    c.execute(
                        "INSERT INTO anvil.task_datasets(id,project_id,objective_id,created_by) VALUES(%s,%s,%s,%s)",
                        (did, project, oid, user),
                    )
                iid = uid()
                normalized = []
                checksum = digest([])
                c.execute(
                    """INSERT INTO anvil.task_imports(id,project_id,dataset_id,objective_revision_id,
                    source_artifact_id,created_by,mapping,validation,normalized,normalized_sha256,status)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        iid,
                        project,
                        did,
                        objective["current_revision_id"],
                        body.artifact_id,
                        user,
                        Jsonb(body.mapping),
                        Jsonb(result),
                        Jsonb(normalized),
                        checksum,
                        "queued",
                    ),
                )
                ingestion.enqueue(c, project, user, iid, 1)
                audit(
                    c,
                    project,
                    user,
                    "task_import.created",
                    iid,
                    {
                        "source_sha256": one(
                            c, "SELECT sha256 FROM anvil.artifacts WHERE id=%s", (body.artifact_id,)
                        )["sha256"]
                    },
                )
                return preview(c, batch(c, iid))

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.get("/objectives/{oid}/task-imports")
    def imports(project: UUID, oid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "data-engineer")
            domain.get_resource(c, oid)
            return wrap(
                c.execute(
                    """SELECT i.id,i.dataset_id,i.status,i.revision,i.published_version_id,i.created_at
                FROM anvil.task_imports i JOIN anvil.task_datasets d ON d.id=i.dataset_id
                WHERE d.objective_id=%s ORDER BY i.created_at DESC LIMIT 100""",
                    (oid,),
                ).fetchall(),
                request,
            )

    @router.get("/task-imports/{iid}")
    def get(project: UUID, iid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "data-engineer")
            return wrap(preview(c, batch(c, iid)), request)

    @router.post("/task-imports/{iid}/validate")
    def revalidate(project: UUID, iid: UUID, body: Mapping, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "data-engineer")

            def act():
                item = batch(c, iid)
                if (
                    item["status"] not in ("ready", "invalid", "failed", "cancelled")
                    or item["revision"] != body.revision
                ):
                    raise HTTPException(
                        409, "Published or stale import; reload or upload a new file"
                    )
                result = {
                    "columns": item["validation"].get("columns", []),
                    "errors": [],
                    "counts": {"received": 0, "valid": 0, "invalid": 0, "duplicates": 0},
                }
                normalized, checksum = [], digest([])
                c.execute(
                    """UPDATE anvil.task_imports SET mapping=%s,validation=%s,normalized=%s,
                    normalized_sha256=%s,status=%s,revision=revision+1 WHERE id=%s""",
                    (
                        Jsonb(body.mapping),
                        Jsonb(result),
                        Jsonb(normalized),
                        checksum,
                        "queued",
                        iid,
                    ),
                )
                ingestion.enqueue(c, project, user, iid, body.revision + 1)
                return preview(c, batch(c, iid))

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/task-imports/{iid}/publish")
    def publish(project: UUID, iid: UUID, body: Publish, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "data-engineer")

            def act():
                item = batch(c, iid)
                if (
                    item["revision"] != body.revision
                    or item["normalized_sha256"] != body.normalized_sha256
                ):
                    raise HTTPException(409, "Validation changed; reload before publishing")
                if item["published_version_id"]:
                    return public_version(version(c, item["published_version_id"]))
                if item["status"] != "ready":
                    raise HTTPException(
                        409, "Wait for completed, valid ingestion before publishing"
                    )
                dataset = one(
                    c, "SELECT * FROM anvil.task_datasets WHERE id=%s", (item["dataset_id"],)
                )
                objective = approved_objective(c, dataset["objective_id"])
                if str(objective["current_revision_id"]) != str(item["objective_revision_id"]):
                    raise HTTPException(
                        409, "Objective changed; create a new import against its approved revision"
                    )
                source, checked = validate_source(c, item["source_artifact_id"], item["mapping"])
                if checked["errors"] or checked["normalized_sha256"] != item["normalized_sha256"]:
                    raise HTTPException(409, "Fix all validation errors before publishing")
                vid = uid()
                number = one(
                    c,
                    "SELECT coalesce(max(version_number),0)+1 n FROM anvil.dataset_versions WHERE dataset_id=%s",
                    (item["dataset_id"],),
                )["n"]
                source_info = {
                    "filename": source["original_filename"],
                    "media_type": source["mime_type"],
                    "byte_size": source["byte_size"],
                    "sha256": source["sha256"],
                    "artifact_id": str(source["id"]),
                }
                c.execute(
                    """INSERT INTO anvil.dataset_versions(id,project_id,dataset_id,version_number,import_id,
                    objective_id,objective_revision_id,schema_version,status,source,mapping,validation,
                    normalized_sha256,created_by,created_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,'1.0','published',%s,%s,%s,%s,%s,%s)""",
                    (
                        vid,
                        project,
                        item["dataset_id"],
                        number,
                        iid,
                        dataset["objective_id"],
                        item["objective_revision_id"],
                        Jsonb(source_info),
                        Jsonb(item["mapping"]),
                        Jsonb(item["validation"]),
                        item["normalized_sha256"],
                        user,
                        item["created_at"],
                    ),
                )
                for row in item["normalized"]:
                    tid = uid()
                    spec = row["spec"]
                    actor = {k: v for k, v in spec.items() if k != "reference"}
                    c.execute(
                        "INSERT INTO anvil.dataset_tasks(id,project_id,version_id,row_number,external_id,actor_spec) VALUES(%s,%s,%s,%s,%s,%s)",
                        (tid, project, vid, row["row"], spec["external_id"], Jsonb(actor)),
                    )
                    if "reference" in spec:
                        c.execute(
                            "INSERT INTO anvil.dataset_references VALUES(%s,%s,%s)",
                            (tid, project, Jsonb(spec["reference"])),
                        )
                c.execute(
                    "UPDATE anvil.task_imports SET status='published',published_version_id=%s WHERE id=%s",
                    (vid, iid),
                )
                audit(
                    c,
                    project,
                    user,
                    "task_import.published",
                    vid,
                    {"task_count": len(item["normalized"]), "version_number": number},
                )
                return public_version(version(c, vid))

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/task-imports/{iid}/{command}")
    def job_command(project: UUID, iid: UUID, command: str, request: Request):
        if command not in ("cancel", "retry"):
            raise HTTPException(404, "Unknown import command")
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "data-engineer")

            def act():
                item = batch(c, iid)
                info = one(
                    c,
                    "SELECT * FROM anvil.ingestion_jobs WHERE import_id=%s AND import_revision=%s",
                    (iid, item["revision"]),
                )
                job = one(
                    c,
                    "SELECT * FROM anvil.jobs WHERE target_id=%s AND kind='task_ingestion' FOR UPDATE",
                    (info["id"],),
                )
                info = one(
                    c, "SELECT * FROM anvil.ingestion_jobs WHERE id=%s FOR UPDATE", (info["id"],)
                )
                if command == "cancel":
                    if info["state"] not in ("queued", "extracting", "validating", "failed"):
                        raise HTTPException(409, "Only an unfinished import can be cancelled")
                    state = "cancelled"
                else:
                    expired = one(
                        c,
                        "SELECT 1 FROM anvil.jobs WHERE id=%s AND status='leased' AND lease_until<now()",
                        (job["id"],),
                    )
                    if info["state"] not in ("failed", "cancelled") and not expired:
                        raise HTTPException(
                            409, "Retry requires a failed, cancelled or expired import"
                        )
                    if info["retries"] >= 3:
                        raise HTTPException(409, "Retry ceiling reached; upload a corrected source")
                    state = "queued"
                c.execute(
                    "UPDATE anvil.jobs SET status=%s,attempts=0,lease_token=NULL,lease_until=NULL WHERE id=%s",
                    (state, job["id"]),
                )
                c.execute(
                    "UPDATE anvil.ingestion_jobs SET state=%s,error_code=NULL,finished_at=NULL,retries=retries+%s WHERE id=%s",
                    (state, int(command == "retry"), info["id"]),
                )
                c.execute("UPDATE anvil.task_imports SET status=%s WHERE id=%s", (state, iid))
                audit(
                    c,
                    project,
                    user,
                    "ingestion." + ("cancelled" if command == "cancel" else "retried"),
                    info["id"],
                    {"checkpoint": info["checkpoint"]},
                )
                return preview(c, batch(c, iid))

            return wrap(idempotent(c, project, user, request, {}, act), request)

    @router.get("/dataset-versions/{vid}")
    def get_version(project: UUID, vid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *domain.CONTENT_ROLES)
            return wrap(public_version(version(c, vid)), request)

    @router.get("/dataset-versions/{vid}/tasks")
    def tasks(
        project: UUID,
        vid: UUID,
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *domain.CONTENT_ROLES)
            version(c, vid)
            return wrap(
                c.execute(
                    "SELECT id,row_number,external_id,actor_spec FROM anvil.dataset_tasks WHERE version_id=%s ORDER BY row_number LIMIT %s OFFSET %s",
                    (vid, limit, offset),
                ).fetchall(),
                request,
            )

    @router.put("/suites/{sid}/dataset-version")
    def attach(project: UUID, sid: UUID, body: Attach, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher")

            def act():
                suite = domain.get_resource(c, sid, True)
                if suite["kind"] != "suite":
                    raise HTTPException(404, "Suite not found")
                domain.etag(suite, request.headers.get("if-match"))
                objective = domain.get_revision(
                    c, suite["content"]["objective_revision_id"], "objective", ["approved"]
                )
                item = version(c, body.version_id, objective["resource_id"])
                if str(item["objective_revision_id"]) != str(objective["id"]):
                    raise HTTPException(
                        409, "Dataset and suite must bind the same approved objective revision"
                    )
                c.execute(
                    "INSERT INTO anvil.suite_datasets VALUES(%s,%s,%s,%s,now()) ON CONFLICT DO NOTHING",
                    (project, suite["current_revision_id"], body.version_id, user),
                )
                audit(
                    c,
                    project,
                    user,
                    "suite.dataset_attached",
                    sid,
                    {
                        "version_id": str(body.version_id),
                        "suite_revision_id": str(suite["current_revision_id"]),
                    },
                )
                return {
                    "suite_id": str(sid),
                    "suite_revision_id": str(suite["current_revision_id"]),
                    "objective_id": str(objective["resource_id"]),
                    "version_id": str(body.version_id),
                }

            return wrap(idempotent(c, project, user, request, body, act), request)

    return router
