"""Project-scoped modern workspace projections; no dispatch or approval side effects."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field

from anvil import artifacts, auth
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.providers import PROVIDERS, secret_presence
from anvil.schemas import Strict

READ_ROLES = ("admin", "researcher", "data-engineer", "product-owner", "advisor")


class ModelProfile(Strict):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    provider: Literal["openai", "anthropic", "gemini"]
    model_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/@-]*$")
    max_output_tokens: int = Field(default=4096, ge=1, le=8192)
    credential_id: UUID | None = None


class FrameworkProfile(Strict):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    framework: Literal["harbor", "langsmith", "semantic_kernel"]
    runtime_version: str | None = Field(
        default=None, max_length=64, pattern=r"^[0-9][A-Za-z0-9.+-]*$"
    )
    tracing_project: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")


def model_public(c, row):
    workspace_profile = row["config"].get("workspace_profile_version") == 1
    present = False
    if not workspace_profile:
        present, _ = secret_presence(row["provider_key"])
    credential_state = "server_configured" if present else "missing"
    binding = row["config"].get("workspace_credential")
    if binding:
        credential = one(
            c, "SELECT * FROM anvil.workspace_credentials WHERE id=%s", (binding["id"],)
        )
        credential_state = "missing"
        present = False
        if credential:
            credential_state = (
                "revoked"
                if credential["revoked_at"]
                else "rotated"
                if str(credential["current_version_id"]) != binding["version_id"]
                else "configured"
            )
            present = credential_state == "configured"
    return {
        "id": row["id"],
        "name": row["config"].get("profile_name") or row["model_id"] or row["provider_key"],
        "provider": row["provider_key"],
        "model_id": row["model_id"],
        "config_hash": row["config_hash"],
        "workspace_profile": workspace_profile,
        "created_at": row["created_at"],
        "credential_present": present,
        "credential_state": credential_state,
        "status": "revoked" if row["status"] == "revoked" else "planning_only",
        "max_output_tokens": row["config"].get("max_output_tokens"),
        "launch_available": False,
        "missing": ["exact_run_readiness_required", "profile_dispatch_binding_not_qualified"],
    }


RUN_SELECT = """SELECT h.*,p.package_sha256,p.manifest,s.task_id,s.task_version,
    s.source_sha256,s.actor_spec,s.revision_id source_revision_id
    FROM anvil.harbor_checks h JOIN anvil.harbor_packages p ON p.id=h.package_id
    JOIN anvil.praxis_sources s ON s.id=p.source_id"""


def metrics(row, calls):
    result = row.get("result") or {}
    diagnostic = result.get("diagnostics") or {}
    reward = diagnostic.get("reward") if row["state"] == "succeeded" else None
    scored = isinstance(reward, (int, float)) and not isinstance(reward, bool)
    unknown = row["state"] == "execution_unknown" or any(
        c["status"] in ("dispatching", "execution_unknown") for c in calls
    )
    paid = row["candidate"] == "agent"
    known = [c["actual_micro_usd"] for c in calls if c["actual_micro_usd"] is not None]
    complete_cost = not paid or (bool(calls) and len(known) == len(calls) and not unknown)
    return {
        "reward": reward if scored else None,
        "score": round(reward * 100, 4) if scored else None,
        "score_basis": "automated_reward_0_to_100; not human-reviewed capability",
        "scored": int(scored),
        "attempts": 1,
        "passed": int(scored and reward == 1),
        "task_failed": int(scored and reward < 1),
        "execution_errors": int(row["state"] == "failed"),
        "unknown": int(unknown),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "known_cost_micro_usd": sum(known) if known else (0 if not paid else None),
        "cost_complete": complete_cost,
        "reserved_micro_usd": sum(c["reserved_micro_usd"] for c in calls),
    }


def calls_for(c, row):
    if not row.get("agent_plan_id"):
        return []
    return c.execute(
        """SELECT stage_index,status,reserved_micro_usd,actual_micro_usd,usage,
        created_at,finished_at FROM anvil.harbor_agent_calls WHERE plan_id=%s
        ORDER BY stage_index""",
        (row["agent_plan_id"],),
    ).fetchall()


def public_run(c, row, detail=False):
    calls = calls_for(c, row)
    result = row.get("result") or {}
    synthetic = row["candidate"] != "agent"
    projection = {
        k: row[k]
        for k in (
            "id",
            "task_id",
            "task_version",
            "package_id",
            "package_sha256",
            "candidate",
            "state",
            "error_code",
            "created_at",
            "started_at",
            "finished_at",
        )
    }
    projection.update(
        title=row["actor_spec"].get("title", row["task_id"]),
        model=result.get("model"),
        origin="synthetic_software_verification" if synthetic else "live_model_unreviewed",
        metrics=metrics(row, calls),
        comparison_signature=digest(
            {
                "package": row["package_sha256"],
                "origin": "synthetic" if synthetic else "model",
                "reward_version": (result.get("diagnostics") or {}).get("reward_version"),
                "harbor": result.get("harbor_version"),
                "execution_overlay": result.get("execution_overlay"),
            }
        ),
    )
    if detail:
        projection.update(
            diagnostics=result.get("diagnostics"),
            actor_snapshot=row["actor_spec"],
            source_sha256=row["source_sha256"],
            source_revision_id=row["source_revision_id"],
            evidence=[
                {k: e[k] for k in ("artifact_id", "kind", "sha256")}
                for e in result.get("evidence", [])
                if e.get("kind") in {"output.json", "output.txt", "diagnostics.json"}
                and all(k in e for k in ("artifact_id", "kind", "sha256"))
            ],
            calls=calls,
            trajectory_limitations=result.get("trajectory") or "No retained trajectory available",
            evaluation_snapshot={
                "package_sha256": row["package_sha256"],
                "harbor_version": result.get("harbor_version"),
                "schema_version": row["manifest"].get("schema_version"),
                "stage_order": row["manifest"].get("stage_order", []),
                "reference_material": "Restricted; excluded from this projection",
                "rubric": "Executable grader is bound by the immutable package hash. Full rubric editor is pending.",
            },
        )
    return projection


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace")

    @router.get("/frameworks")
    def frameworks(
        project: UUID,
        request: Request,
        limit: int = Query(50, ge=1, le=100),
        after: UUID | None = None,
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            rows = c.execute(
                "SELECT id,name,framework,config,config_hash,created_at FROM anvil.workspace_framework_profiles WHERE (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
                (after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": rows[:limit],
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                },
                request,
            )

    @router.post("/frameworks")
    def create_framework(project: UUID, body: FrameworkProfile, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            if body.framework == "harbor" and body.runtime_version not in (None, "0.25.0"):
                raise HTTPException(422, "The existing Harbor adapter is pinned to 0.25.0")
            if body.tracing_project and body.framework != "langsmith":
                raise HTTPException(422, "Tracing project applies only to LangSmith")

            def save():
                fid = uid()
                config = {
                    "schema_version": "anvil.framework_profile.v1",
                    "runtime_version": "0.25.0"
                    if body.framework == "harbor"
                    else body.runtime_version,
                    "tracing_project": body.tracing_project,
                    "trace_export_enabled": False,
                    "dispatch_enabled": False,
                    "qualification": "existing_adapter_binding_pending"
                    if body.framework == "harbor"
                    else "adapter_not_implemented",
                }
                checksum = digest(
                    {"framework": body.framework, "name": body.name.strip(), "config": config}
                )
                c.execute(
                    "INSERT INTO anvil.workspace_framework_profiles(id,project_id,name,framework,config,config_hash,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (
                        fid,
                        project,
                        body.name.strip(),
                        body.framework,
                        Jsonb(config),
                        checksum,
                        user,
                    ),
                )
                audit(
                    c,
                    project,
                    user,
                    "workspace.framework_profile_created",
                    fid,
                    {"config_hash": checksum, "dispatch_enabled": False},
                )
                return {
                    "id": fid,
                    "name": body.name.strip(),
                    "framework": body.framework,
                    "config": config,
                    "config_hash": checksum,
                }

            return wrap(idempotent(c, project, user, request, body, save), request)

    @router.get("/models")
    def models(
        project: UUID,
        request: Request,
        limit: int = Query(50, ge=1, le=100),
        after: UUID | None = None,
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            rows = c.execute(
                "SELECT * FROM anvil.connections WHERE (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
                (after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": [model_public(c, r) for r in rows[:limit]],
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                },
                request,
            )

    @router.post("/models")
    def create_model(project: UUID, body: ModelProfile, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def save():
                cid = uid()
                config = {
                    "profile_name": body.name.strip(),
                    "max_output_tokens": body.max_output_tokens,
                    "workspace_profile_version": 1,
                    "pricing_revision": None,
                    "bound_micro_usd": None,
                    "processing_terms_reviewed": False,
                }
                if body.credential_id:
                    credential = one(
                        c,
                        "SELECT * FROM anvil.workspace_credentials WHERE id=%s FOR SHARE",
                        (body.credential_id,),
                    )
                    if not credential or credential["provider"] != body.provider:
                        raise HTTPException(
                            404, "Matching provider credential not found in this project"
                        )
                    if credential["revoked_at"] or not credential["current_version_id"]:
                        raise HTTPException(409, "Credential is revoked or has no saved version")
                    config["workspace_credential"] = {
                        "id": str(body.credential_id),
                        "version_id": str(credential["current_version_id"]),
                    }
                checksum = digest(
                    {
                        "provider": body.provider,
                        "model_id": body.model_id,
                        "config": config,
                        "adapter": "workspace-planning-v1",
                    }
                )
                c.execute(
                    """INSERT INTO anvil.connections(id,project_id,provider_key,model_id,destination,
                    secret_reference,config,config_hash,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        cid,
                        project,
                        body.provider,
                        body.model_id,
                        PROVIDERS[body.provider][2],
                        PROVIDERS[body.provider][1],
                        Jsonb(config),
                        checksum,
                        user,
                    ),
                )
                audit(
                    c,
                    project,
                    user,
                    "workspace.model_profile_created",
                    cid,
                    {"config_hash": checksum, "live_enabled": False},
                )
                return model_public(
                    c, one(c, "SELECT * FROM anvil.connections WHERE id=%s", (cid,))
                )

            return wrap(idempotent(c, project, user, request, body, save), request)

    @router.get("/tasks")
    def tasks(
        project: UUID,
        request: Request,
        limit: int = Query(50, ge=1, le=100),
        after: str | None = Query(None, max_length=200),
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            rows = c.execute(
                """SELECT DISTINCT ON (s.task_id) s.id,s.task_id,s.task_version,s.actor_spec->>'title' title,
                s.source_sha256,s.created_at,
                (SELECT count(*) FROM anvil.praxis_sources v WHERE v.task_id=s.task_id) versions,
                (SELECT count(*) FROM anvil.harbor_checks h JOIN anvil.harbor_packages p ON p.id=h.package_id
                 JOIN anvil.praxis_sources v ON v.id=p.source_id WHERE v.task_id=s.task_id) run_count
                FROM anvil.praxis_sources s WHERE (%s::text IS NULL OR s.task_id>%s)
                ORDER BY s.task_id,s.created_at DESC,s.id DESC LIMIT %s""",
                (after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": rows[:limit],
                    "next_cursor": rows[limit - 1]["task_id"] if len(rows) > limit else None,
                    "scope": "praxis_harbor",
                },
                request,
            )

    @router.get("/runs")
    def runs(
        project: UUID,
        request: Request,
        task_id: str | None = Query(None, max_length=200),
        limit: int = Query(50, ge=1, le=100),
        after: UUID | None = None,
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            cursor = None
            if after:
                cursor = one(
                    c, "SELECT id,created_at FROM anvil.harbor_checks WHERE id=%s", (after,)
                )
                if not cursor:
                    raise HTTPException(404, "Run cursor not found in this project")
            rows = c.execute(
                RUN_SELECT
                + """ WHERE (%s::text IS NULL OR s.task_id=%s)
                AND (%s::timestamptz IS NULL OR (h.created_at,h.id)<(%s,%s))
                ORDER BY h.created_at DESC,h.id DESC LIMIT %s""",
                (
                    task_id,
                    task_id,
                    cursor["created_at"] if cursor else None,
                    cursor["created_at"] if cursor else None,
                    after,
                    limit + 1,
                ),
            ).fetchall()
            return wrap(
                {
                    "items": [public_run(c, r) for r in rows[:limit]],
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                    "scope": "praxis_harbor",
                },
                request,
            )

    @router.get("/runs/{rid}")
    def detail(project: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            row = one(c, RUN_SELECT + " WHERE h.id=%s", (rid,))
            if not row:
                raise HTTPException(404, "Run not found in this project")
            return wrap(public_run(c, row, True), request)

    @router.get("/runs/{rid}/evidence/{aid}")
    def evidence(project: UUID, rid: UUID, aid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            row = one(c, RUN_SELECT + " WHERE h.id=%s", (rid,))
            if not row:
                raise HTTPException(404, "Run not found in this project")
            linked = next(
                (
                    e
                    for e in (row.get("result") or {}).get("evidence", [])
                    if e.get("artifact_id") == str(aid)
                    and e.get("kind") in {"output.json", "output.txt", "diagnostics.json"}
                ),
                None,
            )
            artifact = one(
                c, "SELECT classification,sha256,byte_size FROM anvil.artifacts WHERE id=%s", (aid,)
            )
            if not linked or not artifact or artifact["classification"] != "internal":
                raise HTTPException(404, "Permitted run evidence not found")
            if artifact["sha256"] != linked["sha256"] or artifact["byte_size"] > 65536:
                raise HTTPException(409, "Evidence integrity or size mismatch")
            value = artifacts.read(c, aid).decode("utf-8", errors="replace")
            audit(c, project, user, "workspace.evidence_read", aid, {"run_id": str(rid)})
            return wrap(
                {"kind": linked["kind"], "content": value, "sha256": artifact["sha256"]}, request
            )

    return router
