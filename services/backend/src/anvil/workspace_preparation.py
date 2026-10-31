"""Immutable planning only; no dispatch, credentials resolution or spending side effects."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field

from anvil import auth
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.schemas import Strict
from anvil.workspace import READ_ROLES

PLAN_ROLES = ("admin", "researcher", "product-owner")


class Preset(Strict):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    runner_profile_id: UUID
    candidate_runtime: Literal["anvil-structured-json-v1", "semantic_kernel"]
    candidate_profile_id: UUID | None = None
    tracing_profile_id: UUID | None = None
    model_profile_ids: list[UUID] = Field(min_length=1, max_length=8)


class Preparation(Strict):
    preset_id: UUID
    package_id: UUID
    model_profile_ids: list[UUID] = Field(min_length=1, max_length=8)
    max_output_tokens: int = Field(ge=1, le=2048, strict=True)
    episode_timeout_seconds: int = Field(ge=1, le=600, strict=True)
    aggregate_cap_micro_usd: int | None = Field(default=None, gt=0, le=1000000000, strict=True)


def unique(ids):
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Select each model profile only once")


def record(c, table, identifier):
    if table not in ("workspace_execution_presets", "workspace_run_preparations"):
        raise ValueError("Unsupported planning record")
    row = one(c, f"SELECT * FROM anvil.{table} WHERE id=%s", (identifier,))
    if not row:
        raise HTTPException(404, "Planning record not found in this project")
    return row


def framework(c, identifier, kind):
    row = one(c, "SELECT * FROM anvil.workspace_framework_profiles WHERE id=%s", (identifier,))
    if not row or row["framework"] != kind:
        raise HTTPException(404, f"Matching {kind} profile not found in this project")
    if kind == "harbor" and row["config"].get("runtime_version") != "0.25.0":
        raise HTTPException(422, "This preparation supports the pinned Harbor 0.25.0 metadata")
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "framework": kind,
        "config_hash": row["config_hash"],
        "runtime_version": row["config"].get("runtime_version"),
    }


def model_snapshot(row):
    binding = row["config"].get("workspace_credential")
    return {
        "id": str(row["id"]),
        "name": row["config"].get("profile_name"),
        "provider": row["provider_key"],
        "model_id": row["model_id"],
        "destination": row["destination"],
        "config_hash": row["config_hash"],
        "max_output_tokens": row["config"].get("max_output_tokens"),
        "credential": {"id": binding["id"], "version_id": binding["version_id"]}
        if binding
        else None,
    }


def model(c, identifier):
    row = one(c, "SELECT * FROM anvil.connections WHERE id=%s FOR SHARE", (identifier,))
    if not row or row["config"].get("workspace_profile_version") != 1:
        raise HTTPException(404, "Workspace model profile not found in this project")
    if row["status"] == "revoked":
        raise HTTPException(409, "A selected model profile is revoked")
    return model_snapshot(row)


def package_snapshot(row):
    # Do not copy files, source review, grading admission or future observations.
    allowed = (
        "schema_version",
        "task_id",
        "task_version",
        "revision_id",
        "source_sha256",
        "binding",
        "compiler_version",
        "harbor_version",
        "stage_order",
    )
    return {
        "id": str(row["id"]),
        "source_id": str(row["source_id"]),
        "package_sha256": row["package_sha256"],
        "agent_admission_present": "anvil-agent/admission.json" in row["manifest"].get("files", {}),
        "manifest": {k: row["manifest"][k] for k in allowed if k in row["manifest"]},
    }


def readiness(c, snapshot):
    reasons = [
        "workspace_dispatch_not_qualified",
        "current_pricing_not_bound",
        "exact_user_authority_not_bound",
        "processing_rights_not_bound",
        "required_run_decisions_not_bound",
        "shared_spending_admission_not_implemented",
    ]
    if snapshot["aggregate_cap_micro_usd"] is None:
        reasons.append("aggregate_api_cap_missing")
    package = snapshot["package"]
    if package["manifest"].get("binding") not in ("structured-decision-v1", "staged-decision-v1"):
        reasons.append("task_binding_not_supported")
    if package["manifest"].get("harbor_version") != "0.25.0":
        reasons.append("package_runtime_not_supported")
    if not package["agent_admission_present"]:
        reasons.append("package_agent_admission_missing")
    preset = snapshot["preset"]
    if preset["candidate_runtime"] != "anvil-structured-json-v1":
        reasons.append("candidate_runtime_not_qualified")
    if preset["tracing"]:
        reasons.append("external_tracing_not_qualified_export_disabled")
    for field in ("runner", "candidate", "tracing"):
        bound_framework = preset[field]
        if bound_framework:
            current_framework = one(
                c,
                "SELECT config_hash FROM anvil.workspace_framework_profiles WHERE id=%s",
                (bound_framework["id"],),
            )
            if (
                not current_framework
                or current_framework["config_hash"] != bound_framework["config_hash"]
            ):
                reasons.append("framework_binding_changed_or_unavailable")
    model_states = []
    for bound in snapshot["models"]:
        missing = []
        current = one(c, "SELECT * FROM anvil.connections WHERE id=%s", (bound["id"],))
        if not current or current["status"] == "revoked":
            missing.append("model_revoked_or_unavailable")
        elif (
            current["config"].get("workspace_profile_version") != 1
            or model_snapshot(current) != bound
        ):
            missing.append("model_configuration_changed")
        if snapshot["max_output_tokens"] > bound["max_output_tokens"]:
            missing.append("selected_output_limit_exceeds_profile")
        credential = bound["credential"]
        if not credential:
            missing.append("credential_missing")
        else:
            stored = one(
                c,
                "SELECT provider,revoked_at,current_version_id FROM anvil.workspace_credentials WHERE id=%s",
                (credential["id"],),
            )
            if not stored or stored["provider"] != bound["provider"] or stored["revoked_at"]:
                missing.append("credential_revoked_or_unavailable")
            elif str(stored["current_version_id"]) != credential["version_id"]:
                missing.append("bound_credential_rotated")
        missing.append("provider_task_adapter_not_qualified")
        model_states.append({"model_profile_id": bound["id"], "missing": missing})
    return {
        "state": "planning_only",
        "launch_available": False,
        "missing": reasons,
        "models": model_states,
        "conservative_cost_micro_usd": None,
        "reservation_micro_usd": None,
        "trace_export_enabled": False,
    }


def public(c, row, preparation=False):
    result = {k: row[k] for k in ("id", "snapshot", "subject_hash", "created_at")}
    result["state"] = "planning_only"
    result["launch_available"] = False
    if preparation:
        result["readiness"] = readiness(c, row["snapshot"])
    return result


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace")

    @router.get("/packages")
    def packages(
        project: UUID,
        request: Request,
        limit: int = Query(30, ge=1, le=100),
        after: UUID | None = None,
        task_id: str | None = Query(None, max_length=100),
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            rows = c.execute(
                """SELECT p.*,s.actor_spec->>'title' title FROM anvil.harbor_packages p
                JOIN anvil.praxis_sources s ON s.id=p.source_id WHERE (%s::uuid IS NULL OR p.id>%s)
                AND (%s::text IS NULL OR s.task_id=%s) ORDER BY p.id LIMIT %s""",
                (after, after, task_id, task_id, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": [
                        {**package_snapshot(row), "title": row["title"]} for row in rows[:limit]
                    ],
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                },
                request,
            )

    @router.get("/presets")
    def presets(
        project: UUID,
        request: Request,
        limit: int = Query(30, ge=1, le=100),
        after: UUID | None = None,
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            rows = c.execute(
                "SELECT * FROM anvil.workspace_execution_presets WHERE (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
                (after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": [public(c, row) for row in rows[:limit]],
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                },
                request,
            )

    @router.post("/presets")
    def create_preset(project: UUID, body: Preset, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def save():
                unique(body.model_profile_ids)
                if (body.candidate_runtime == "semantic_kernel") != bool(body.candidate_profile_id):
                    raise HTTPException(
                        422,
                        "Semantic Kernel requires its own typed profile; built-in Anvil does not",
                    )
                snapshot = {
                    "name": body.name.strip(),
                    "runner": framework(c, body.runner_profile_id, "harbor"),
                    "candidate_runtime": body.candidate_runtime,
                    "candidate": framework(c, body.candidate_profile_id, "semantic_kernel")
                    if body.candidate_profile_id
                    else None,
                    "tracing": framework(c, body.tracing_profile_id, "langsmith")
                    if body.tracing_profile_id
                    else None,
                    "models": [model(c, identifier) for identifier in body.model_profile_ids],
                    "trace_export_enabled": False,
                }
                identifier, checksum = uid(), digest(snapshot)
                c.execute(
                    "INSERT INTO anvil.workspace_execution_presets(id,project_id,name,runner_profile_id,candidate_profile_id,tracing_profile_id,snapshot,subject_hash,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        identifier,
                        project,
                        snapshot["name"],
                        body.runner_profile_id,
                        body.candidate_profile_id,
                        body.tracing_profile_id,
                        Jsonb(snapshot),
                        checksum,
                        user,
                    ),
                )
                for mid in body.model_profile_ids:
                    c.execute(
                        "INSERT INTO anvil.workspace_preset_models VALUES(%s,%s,%s)",
                        (project, identifier, mid),
                    )
                audit(
                    c,
                    project,
                    user,
                    "workspace.execution_preset_created",
                    identifier,
                    {"subject_hash": checksum, "planning_only": True},
                )
                return public(c, record(c, "workspace_execution_presets", identifier))

            return wrap(idempotent(c, project, user, request, body, save), request)

    @router.get("/preparations")
    def preparations(
        project: UUID,
        request: Request,
        limit: int = Query(30, ge=1, le=100),
        after: UUID | None = None,
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            rows = c.execute(
                "SELECT * FROM anvil.workspace_run_preparations WHERE (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
                (after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": [public(c, row, True) for row in rows[:limit]],
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                },
                request,
            )

    @router.get("/preparations/{pid}")
    def preparation(project: UUID, pid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            return wrap(public(c, record(c, "workspace_run_preparations", pid), True), request)

    @router.post("/preparations")
    def create_preparation(project: UUID, body: Preparation, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *PLAN_ROLES)

            def save():
                unique(body.model_profile_ids)
                preset = record(c, "workspace_execution_presets", body.preset_id)
                allowed = {m["id"] for m in preset["snapshot"]["models"]}
                if any(str(mid) not in allowed for mid in body.model_profile_ids):
                    raise HTTPException(422, "Select models from this preset's exact allowlist")
                package = one(
                    c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (body.package_id,)
                )
                if not package:
                    raise HTTPException(404, "Package not found in this project")
                models = [model(c, mid) for mid in body.model_profile_ids]
                frozen = {m["id"]: m for m in preset["snapshot"]["models"]}
                if any(m != frozen[m["id"]] for m in models):
                    raise HTTPException(
                        409, "Model configuration differs from this preset; create a new preset"
                    )
                snapshot = {
                    "preset_id": str(preset["id"]),
                    "preset_hash": preset["subject_hash"],
                    "preset": preset["snapshot"],
                    "package": package_snapshot(package),
                    "models": models,
                    "max_output_tokens": body.max_output_tokens,
                    "episode_timeout_seconds": body.episode_timeout_seconds,
                    "aggregate_cap_micro_usd": body.aggregate_cap_micro_usd,
                    "execution_order": "sequential",
                    "trials_per_model": 1,
                }
                identifier, checksum = uid(), digest(snapshot)
                c.execute(
                    "INSERT INTO anvil.workspace_run_preparations(id,project_id,preset_id,package_id,snapshot,subject_hash,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (
                        identifier,
                        project,
                        body.preset_id,
                        body.package_id,
                        Jsonb(snapshot),
                        checksum,
                        user,
                    ),
                )
                for m in models:
                    credential = m["credential"] or {}
                    c.execute(
                        "INSERT INTO anvil.workspace_preparation_models VALUES(%s,%s,%s,%s,%s,%s)",
                        (
                            project,
                            identifier,
                            body.preset_id,
                            m["id"],
                            credential.get("id"),
                            credential.get("version_id"),
                        ),
                    )
                audit(
                    c,
                    project,
                    user,
                    "workspace.run_preparation_created",
                    identifier,
                    {"subject_hash": checksum, "planning_only": True},
                )
                return public(c, record(c, "workspace_run_preparations", identifier), True)

            return wrap(idempotent(c, project, user, request, body, save), request)

    return router
