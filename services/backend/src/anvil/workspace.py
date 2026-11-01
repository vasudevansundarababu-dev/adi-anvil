"""Project-scoped modern workspace projections; no dispatch or approval side effects."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field

from anvil import artifacts, auth
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.schemas import Strict
from anvil.workspace_models import ModelProfile, model_public, save_model

READ_ROLES = ("admin", "rl-engineer")


class FrameworkProfile(Strict):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    framework: Literal["harbor", "langsmith", "semantic_kernel"]
    runtime_version: str | None = Field(
        default=None, max_length=64, pattern=r"^[0-9][A-Za-z0-9.+-]*$"
    )
    tracing_project: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")


RUN_SELECT = """SELECT h.*,p.package_sha256,p.manifest,s.task_id,s.task_version,
    s.source_sha256,s.actor_spec,s.revision_id source_revision_id,s.source_artifact_id
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
        """SELECT stage_index,status,reserved_micro_usd,actual_micro_usd,usage,request_id,request_sha256,
        created_at,finished_at FROM anvil.harbor_agent_calls WHERE plan_id=%s
        ORDER BY stage_index""",
        (row["agent_plan_id"],),
    ).fetchall()


def public_run(c, row, detail=False):
    calls = calls_for(c, row)
    result = row.get("result") or {}
    mock_execution = bool(
        result.get("mock_execution")
        or any((call.get("usage") or {}).get("dispatch_origin") == "sdk_mock" for call in calls)
    )
    synthetic = row["candidate"] != "agent" or mock_execution
    plan = (
        one(c, "SELECT config FROM anvil.harbor_agent_plans WHERE id=%s", (row["agent_plan_id"],))
        if row.get("agent_plan_id")
        else None
    )
    config = plan["config"] if plan else {}
    selected_model = config.get("workspace_model")
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
        model=result.get("model")
        or (selected_model["model_id"] if selected_model else config.get("model")),
        provider=selected_model["provider"] if selected_model else ("openai" if plan else None),
        execution_group_id=config.get("workspace_execution_group"),
        trial=config.get("trial", 1),
        origin="native_sdk_mock_verification"
        if mock_execution
        else "synthetic_software_verification"
        if synthetic
        else "live_model_unreviewed",
        metrics=metrics(row, calls),
        comparison_signature=digest(
            {
                "package": row["package_sha256"],
                "origin": "sdk_mock" if mock_execution else "synthetic" if synthetic else "model",
                "reward_version": (result.get("diagnostics") or {}).get("reward_version"),
                "harbor": result.get("harbor_version"),
                "execution_overlay": result.get("execution_overlay"),
                "output_tokens": config.get("max_output_tokens"),
                "timeout_seconds": config.get("episode_timeout_seconds"),
                "adapter_sha256": config.get("adapter_sha256"),
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
            calls=observed_calls(c, row, calls),
            trajectory_limitations=result.get("trajectory") or "No retained trajectory available",
            evaluation_snapshot={
                "package_sha256": row["package_sha256"],
                "harbor_version": result.get("harbor_version"),
                "schema_version": row["manifest"].get("schema_version"),
                "stage_order": row["manifest"].get("stage_order", []),
                "reference_material": "Restricted; excluded from this projection",
                "rubric": safe_rubric(c, row),
                "execution_settings": {
                    k: config.get(k)
                    for k in (
                        "model",
                        "max_calls",
                        "max_output_tokens",
                        "episode_timeout_seconds",
                        "request_timeout_seconds",
                        "adapter_sha256",
                    )
                },
                "selected_model": selected_model,
            },
        )
    return projection


def safe_rubric(c, row):
    from anvil.praxis_contract import PraxisTask
    from anvil.praxis_export import parse_export
    from anvil.praxis_staged import PraxisTaskV2
    from anvil.task_parser import json_value

    raw, _ = parse_export(artifacts.read(c, row["source_artifact_id"]))
    value = json_value(raw)
    task = (
        PraxisTaskV2 if value.get("schema_version") == "praxis.anvil.task.v2" else PraxisTask
    ).model_validate(value)

    def criteria(rubric):
        return [
            {"id": item.id, "description": item.description, "weight_bps": item.weight_bps}
            for item in rubric.criteria
        ]

    return {
        "criteria": criteria(task.rubric),
        "stages": [{"id": stage.id, "criteria": criteria(stage.rubric)} for stage in task.stages]
        if task.schema_version == "praxis.anvil.task.v2"
        else [],
        "private_bindings": "Excluded; exact executable grading remains bound to the package hash",
    }


def observed_calls(c, row, calls):
    """Reconstruct only an actually recorded intent's actor context, verified by its hash.

    Grading bindings/admission bytes never leave this function. Captured output is
    exposed only after the execution is terminal, including failed/unknown executions.
    """
    if not calls:
        return []
    import hashlib
    import io
    import zipfile

    from anvil import harbor_agents
    from anvil.task_parser import json_value

    package = one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (row["package_id"],))
    with zipfile.ZipFile(io.BytesIO(artifacts.read(c, package["package_artifact_id"]))) as archive:
        raw = archive.read("anvil-agent/admission.json")
    if (
        hashlib.sha256(raw).hexdigest()
        != package["manifest"]["files"]["anvil-agent/admission.json"]
    ):
        raise HTTPException(409, "Actor admission integrity mismatch")
    admission = json_value(raw)
    outputs = c.execute(
        "SELECT stage_index,output_json FROM anvil.harbor_agent_calls WHERE plan_id=%s ORDER BY stage_index",
        (row["agent_plan_id"],),
    ).fetchall()
    texts = {entry["stage_index"]: (entry["output_json"] or {}).get("text") for entry in outputs}
    result = []
    for call in calls:
        context = None
        try:
            previous = [json_value(texts[index]) for index in range(call["stage_index"])]
            prompt = harbor_agents.actor_prompt(admission, call["stage_index"], previous)
            if hashlib.sha256(prompt.encode()).hexdigest() == call["request_sha256"]:
                context = prompt
        except (ValueError, TypeError, KeyError, RuntimeError):
            pass
        result.append(
            {
                **call,
                "actor_context": context,
                "output_text": texts.get(call["stage_index"])
                if row["state"] not in ("queued", "running")
                else None,
            }
        )
    return result


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
        current_only: bool = False,
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            rows = c.execute(
                """SELECT c.*,CASE WHEN %s THEN COALESCE(p.id,c.id) ELSE c.id END page_cursor FROM anvil.connections c LEFT JOIN anvil.workspace_model_versions v ON v.connection_id=c.id
                LEFT JOIN anvil.workspace_model_profiles p ON p.id=v.profile_id
                WHERE (%s::uuid IS NULL OR (CASE WHEN %s THEN COALESCE(p.id,c.id) ELSE c.id END)>%s)
                AND (NOT %s OR p.id IS NULL OR p.current_connection_id=c.id)
                ORDER BY page_cursor LIMIT %s""",
                (current_only, after, current_only, after, current_only, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": [model_public(c, r) for r in rows[:limit]],
                    "next_cursor": str(rows[limit - 1]["page_cursor"])
                    if len(rows) > limit
                    else None,
                },
                request,
            )

    @router.post("/models")
    def create_model(project: UUID, body: ModelProfile, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def save():
                return save_model(c, project, user, body)

            return wrap(idempotent(c, project, user, request, body, save), request)

    @router.get("/tasks")
    def tasks(
        project: UUID,
        request: Request,
        limit: int = Query(50, ge=1, le=100),
        after: str | None = Query(None, max_length=200),
        search: str = Query("", max_length=200),
        status: Literal["all", "ready", "draft"] = "all",
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            rows = c.execute(
                """SELECT DISTINCT ON (s.task_id) s.id,s.task_id,s.task_version,s.actor_spec->>'title' title,
                s.source_sha256,s.created_at,
                (SELECT count(*) FROM anvil.praxis_sources v WHERE v.task_id=s.task_id) versions,
                (SELECT count(*) FROM anvil.harbor_checks h JOIN anvil.harbor_packages p ON p.id=h.package_id
                 JOIN anvil.praxis_sources v ON v.id=p.source_id WHERE v.task_id=s.task_id) run_count,
                (SELECT max(h.created_at) FROM anvil.harbor_checks h JOIN anvil.harbor_packages p ON p.id=h.package_id
                 JOIN anvil.praxis_sources v ON v.id=p.source_id WHERE v.task_id=s.task_id) last_run_at,
                EXISTS(SELECT 1 FROM anvil.harbor_packages p WHERE p.source_id=s.id) package_built
                FROM (SELECT DISTINCT ON(task_id) * FROM anvil.praxis_sources
                      ORDER BY task_id,created_at DESC,id DESC) s
                WHERE (%s::text IS NULL OR s.task_id>%s)
                AND (strpos(lower(s.task_id),lower(%s))>0 OR strpos(lower(s.actor_spec->>'title'),lower(%s))>0)
                AND (%s='all' OR (%s='ready')=EXISTS(SELECT 1 FROM anvil.harbor_packages p WHERE p.source_id=s.id))
                ORDER BY s.task_id,s.created_at DESC,s.id DESC LIMIT %s""",
                (after, after, search, search, status, status, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": rows[:limit],
                    "next_cursor": rows[limit - 1]["task_id"] if len(rows) > limit else None,
                    "scope": "praxis_harbor",
                },
                request,
            )

    @router.get("/tasks/{sid}")
    def task_detail(project: UUID, sid: UUID, request: Request):
        from anvil.workspace_environments import listing as environments

        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            row = one(c, "SELECT * FROM anvil.praxis_sources WHERE id=%s", (sid,))
            if not row:
                raise HTTPException(404, "Task version not found in this project")
            versions = c.execute(
                "SELECT id,task_version,created_at FROM anvil.praxis_sources WHERE task_id=%s ORDER BY created_at DESC,id DESC LIMIT 100",
                (row["task_id"],),
            ).fetchall()
            if all(version["id"] != row["id"] for version in versions):
                versions.append(
                    {
                        "id": row["id"],
                        "task_version": row["task_version"],
                        "created_at": row["created_at"],
                    }
                )
            packages = c.execute(
                "SELECT id,package_sha256,manifest,created_at FROM anvil.harbor_packages WHERE source_id=%s ORDER BY created_at DESC,id DESC",
                (sid,),
            ).fetchall()
            return wrap(
                {
                    "id": row["id"],
                    "task_id": row["task_id"],
                    "task_version": row["task_version"],
                    "title": row["actor_spec"].get("title", row["task_id"]),
                    "created_at": row["created_at"],
                    "source_sha256": row["source_sha256"],
                    "actor": row["actor_spec"],
                    "rubric": safe_rubric(c, row),
                    "versions": versions,
                    "versions_limit": 100,
                    "environments": environments(c, sid),
                    "packages": [
                        {
                            "id": p["id"],
                            "package_sha256": p["package_sha256"],
                            "base_image": p["manifest"].get("base_image"),
                            "binding": p["manifest"].get("binding"),
                            "stage_count": len(p["manifest"].get("stage_order", [])),
                            "created_at": p["created_at"],
                        }
                        for p in packages
                    ],
                    "run_count": one(
                        c,
                        "SELECT count(*) n FROM anvil.harbor_checks h JOIN anvil.harbor_packages p ON p.id=h.package_id JOIN anvil.praxis_sources s ON s.id=p.source_id WHERE s.task_id=%s",
                        (row["task_id"],),
                    )["n"],
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
