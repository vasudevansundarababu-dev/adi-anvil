"""Immutable planning only; no dispatch, credentials resolution or spending side effects."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field

from anvil import auth, workspace_costs
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.project_bindings import FrozenBinding
from anvil.schemas import Strict
from anvil.workspace import READ_ROLES
from anvil.workspace_models import selection_issues

PLAN_ROLES = ("admin", "rl-engineer")


class Preset(Strict):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    runner_profile_id: UUID
    candidate_runtime: Literal[
        "anvil-structured-json-v1",
        "semantic_kernel",
        "golden-kyc-openenv-tool-agent-v1",
        "marketing-task2-five-role-v1",
    ]
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
    trials_per_model: int = Field(default=1, ge=1, le=10, strict=True)
    environment: Literal["package-docker", "golden-kyc-openenv-v2", "marketing-task2-us-v1"] = (
        "package-docker"
    )
    max_agent_steps: int | None = Field(default=None, ge=1, le=1000, strict=True)
    workflow_definition_id: UUID | None = None
    human_assignments: dict[str, UUID] = Field(default_factory=dict, max_length=30)
    case_ids: list[str] | None = Field(default=None, min_length=1, max_length=10000)
    task_package_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=5)
    project_binding: FrozenBinding | None = None
    execution_budget_id: UUID | None = None


def unique(ids):
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Select each model profile only once")


def turn_bound(package, requested):
    """Explicit physical bounds never silently truncate a native campaign."""
    marketing = package["manifest"].get("binding") == "marketing-task2-five-role-v1"
    available = len(package["manifest"]["stage_order"])
    ceiling = 1000 if marketing else 100
    selected = requested if requested is not None else min(ceiling, available)
    if not 1 <= selected <= min(ceiling, available):
        raise HTTPException(422, "Selected model turn bound exceeds the package/runtime ceiling")
    return selected


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
    issues = selection_issues(c, identifier)
    if issues:
        raise HTTPException(409, "Select an enabled current model version: " + ", ".join(issues))
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
        "base_image",
        "native_binding",
    )
    return {
        "id": str(row["id"]),
        "source_id": str(row["source_id"]),
        "package_sha256": row["package_sha256"],
        "agent_admission_present": "anvil-agent/admission.json" in row["manifest"].get("files", {}),
        "manifest": {k: row["manifest"][k] for k in allowed if k in row["manifest"]},
    }


def readiness(c, snapshot):
    reasons = ["execution_group_required"]
    if snapshot["aggregate_cap_micro_usd"] is None:
        reasons.append("aggregate_api_cap_missing")
    package = snapshot["package"]
    for bound in snapshot.get("task_packages", []):
        current_package = one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (bound["id"],))
        if not current_package or package_snapshot(current_package) != bound:
            reasons.append("state_task_package_binding_changed")
    if package["manifest"].get("binding") not in (
        "structured-decision-v1",
        "staged-decision-v1",
        "mcp-tool-agent-v1",
        "golden-kyc-openenv-tool-agent-v1",
        "marketing-task2-five-role-v1",
    ):
        reasons.append("task_binding_not_supported")
    from anvil.harbor_package import structured_profile_current

    if package["manifest"].get("harbor_version") != "0.25.0" or (
        package["manifest"].get("binding") in {"structured-decision-v1", "staged-decision-v1"}
        and not structured_profile_current(package["manifest"])
    ):
        reasons.append("package_runtime_not_supported")
    if not package["agent_admission_present"]:
        reasons.append("package_agent_admission_missing")
    preset = snapshot["preset"]
    native = package["manifest"].get("binding") == "golden-kyc-openenv-tool-agent-v1"
    marketing = package["manifest"].get("binding") == "marketing-task2-five-role-v1"
    expected_runtime = (
        package["manifest"]["binding"] if native or marketing else "anvil-structured-json-v1"
    )
    if preset["candidate_runtime"] != expected_runtime:
        reasons.append("candidate_runtime_not_qualified")
    if native or marketing or snapshot.get("project_binding"):
        from anvil.project_bindings import execution_issues

        source_package = one(
            c, "SELECT project_id FROM anvil.harbor_packages WHERE id=%s", (package["id"],)
        )
        if not source_package:
            reasons.append("project_binding_package_unavailable")
        else:
            reasons.extend(
                execution_issues(
                    c,
                    source_package["project_id"],
                    snapshot.get("project_binding"),
                    snapshot.get("task_packages", [package]),
                )
            )
    if native:
        if snapshot.get("environment", {}).get("id") != "golden-kyc-openenv-v2" or not package[
            "manifest"
        ].get("native_binding"):
            reasons.append("golden_native_environment_binding_required")
        from anvil.golden_kyc_paid_qualification import installed

        reasons.extend(installed()["missing"])
    elif marketing:
        from anvil.marketing_paid_qualification import installed
        from anvil.marketing_paid_session import task_context

        binding = package["manifest"].get("native_binding") or {}
        if snapshot.get("environment", {}).get("id") != "marketing-task2-us-v1":
            reasons.append("marketing_native_environment_binding_required")
        reasons.extend(installed(binding.get("workflow_graph_sha256"))["missing"])
        try:
            current_context = task_context(
                c,
                source_package["project_id"],
                binding["resolved_task_id"],
                binding["task_group_id"],
                execution_data=binding.get("execution_data"),
            )
            if current_context["native_binding"] != binding:
                reasons.append("marketing_current_source_binding_changed")
        except (ValueError, RuntimeError, KeyError, TypeError):
            reasons.append("marketing_current_source_qualification_required")
    elif snapshot.get("environment", {}).get("id") in (
        "golden-kyc-openenv-v2",
        "marketing-task2-us-v1",
    ):
        reasons.append("golden_native_package_required")
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
        missing = selection_issues(c, bound["id"])
        current = one(c, "SELECT * FROM anvil.connections WHERE id=%s", (bound["id"],))
        if not current or current["status"] == "revoked":
            missing.append("model_revoked_or_unavailable")
        elif (
            current["config"].get("workspace_profile_version") != 1
            or model_snapshot(current) != bound
        ):
            missing.append("model_configuration_changed")
        if current:
            price = workspace_costs.for_model(current)
            if not price:
                missing.append("model_cost_support_unavailable")
            elif not workspace_costs.current(price):
                missing.append("model_cost_support_expired")
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
        if bound["provider"] not in ("openai", "anthropic", "gemini"):
            missing.append("provider_task_adapter_not_supported")
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
        source_id: UUID | None = None,
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            rows = c.execute(
                """SELECT p.*,s.actor_spec->>'title' title FROM anvil.harbor_packages p
                JOIN anvil.praxis_sources s ON s.id=p.source_id WHERE (%s::uuid IS NULL OR p.id>%s)
                AND (%s::text IS NULL OR s.task_id=%s)
                AND (%s::uuid IS NULL OR s.id=%s) ORDER BY p.id LIMIT %s""",
                (after, after, task_id, task_id, source_id, source_id, limit + 1),
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
                    "trials_per_model": body.trials_per_model,
                    "max_agent_steps": turn_bound(package, body.max_agent_steps),
                    "environment": {
                        "id": body.environment,
                        "name": "Golden KYC OpenEnv"
                        if body.environment == "golden-kyc-openenv-v2"
                        else "Marketing five-role OpenEnv"
                        if body.environment == "marketing-task2-us-v1"
                        else "Harbor isolated Docker",
                        "base_image": package["manifest"].get("base_image"),
                        "package_sha256": package["package_sha256"],
                    },
                }
                if body.project_binding is not None:
                    snapshot["project_binding"] = body.project_binding.model_dump(mode="json")
                    from anvil.project_bindings import current as current_binding

                    selected = current_binding(c, project, body.project_binding.task_group_id)
                    if (
                        not selected
                        or str(selected["id"]) != str(body.project_binding.id)
                        or selected["snapshot_sha256"] != body.project_binding.snapshot_sha256
                    ):
                        raise HTTPException(
                            409, "Project binding changed before method preparation"
                        )
                    snapshot["method_binding"] = selected["snapshot"].get("method_binding")
                    snapshot["skill_mapping_bindings"] = selected["snapshot"].get(
                        "skill_mapping_bindings", []
                    )
                    if selected["snapshot"].get("semantic_judge_batches"):
                        from anvil.campaign_semantic_contract import parse_template

                        snapshot["semantic_judge_templates"] = [
                            parse_template(item).model_dump(mode="json")
                            for item in selected["snapshot"]["semantic_judge_batches"]
                        ]
                        snapshot["semantic_judge_model_support"] = selected["snapshot"].get(
                            "semantic_judge_model_support", {}
                        )
                    from anvil.native_semantic import prepare_fixed_models

                    snapshot.update(
                        prepare_fixed_models(
                            c, selected["snapshot"].get("semantic_judge_models", {})
                        )
                    )
                    if selected["snapshot"].get("semantic_judge_gaps"):
                        snapshot["semantic_judge_gaps"] = selected["snapshot"][
                            "semantic_judge_gaps"
                        ]
                if body.execution_budget_id is not None:
                    snapshot["execution_budget_id"] = str(body.execution_budget_id)
                native_binding = package["manifest"].get("native_binding") or {}
                if native_binding.get("task_mode") in {"reusable_state_workflow", "reusable_application_workflow"}:
                    from anvil.golden_kyc_paid_package import task_set_assignments

                    identifiers = body.task_package_ids or [body.package_id]
                    if body.package_id not in identifiers or len(set(identifiers)) != len(
                        identifiers
                    ):
                        raise HTTPException(
                            422, "Include the primary package once in the unique state task set"
                        )
                    packages = [
                        one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (identifier,))
                        for identifier in identifiers
                    ]
                    if any(p is None for p in packages):
                        raise HTTPException(404, "State task package not found in this project")
                    if any(
                        p["manifest"].get("stage_order") != package["manifest"].get("stage_order")
                        for p in packages
                    ):
                        raise HTTPException(
                            422,
                            "State tasks in one comparison must use the same bounded turn configuration",
                        )
                    snapshot["task_packages"] = [package_snapshot(p) for p in packages]
                    snapshot["case_assignments"] = task_set_assignments(
                        c, project, packages, body.case_ids
                    )
                    snapshot["case_count"] = len(snapshot["case_assignments"])
                elif native_binding.get("task_mode") == "reusable_campaign_workflow":
                    from anvil.marketing_paid_package import assignments

                    if (
                        body.task_package_ids is not None
                        or body.workflow_definition_id is not None
                        or body.human_assignments
                    ):
                        raise HTTPException(
                            422, "Marketing uses its published five-role graph and one package"
                        )
                    try:
                        snapshot["case_assignments"] = assignments(package, case_ids=body.case_ids)
                    except ValueError as exc:
                        raise HTTPException(422, str(exc)) from None
                    snapshot["case_count"] = len(snapshot["case_assignments"])
                elif body.case_ids is not None or body.task_package_ids is not None:
                    raise HTTPException(
                        422, "Case selection requires a reusable state-task package"
                    )
                if body.project_binding is not None:
                    from anvil.campaign_reference_bindings import (
                        freeze as freeze_campaign_references,
                    )
                    from anvil.golden_targets import family

                    imported_source = one(
                        c,
                        "SELECT content FROM anvil.benchmark_task_groups WHERE project_id=%s AND id=%s",
                        (project, body.project_binding.task_group_id),
                    )
                    source_tasks = (
                        imported_source["content"].get("tasks", []) if imported_source else []
                    )
                    if source_tasks and all(family(task) == "marketing" for task in source_tasks):
                        if not snapshot.get("case_assignments"):
                            raise HTTPException(
                                409, {"code": "campaign_case_assignment_required", "owner": "anvil"}
                            )
                        snapshot.update(
                            freeze_campaign_references(
                                c, body.project_binding.task_group_id, snapshot["case_assignments"]
                            )
                        )
                if body.workflow_definition_id:
                    from anvil import workflow_registry

                    try:
                        workflow = workflow_registry.preparation(
                            c, body.workflow_definition_id, body.package_id, body.human_assignments
                        )
                    except ValueError:
                        raise HTTPException(
                            409,
                            "Current exact graph testing definition and human assignments required",
                        ) from None
                    if body.max_agent_steps not in (None, workflow["bounds"]["calls"]):
                        raise HTTPException(
                            422, "Graph call ceiling is fixed by the registered definition"
                        )
                    snapshot["workflow"] = workflow
                    snapshot["max_agent_steps"] = workflow["bounds"]["calls"]
                elif body.human_assignments:
                    raise HTTPException(422, "Human assignments require a registered workflow")
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
