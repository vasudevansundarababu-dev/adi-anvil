"""Additive authenticated environment library; no paid/cloud dispatch route."""

import json
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import Field, StrictInt, model_validator

from anvil import auth
from anvil import environment_bindings as bindings
from anvil import environment_builds as builds
from anvil import environment_data as data_packs
from anvil import environment_runtime as runtime
from anvil import environment_seeds as seeds
from anvil import environment_validation as validation
from anvil.db import one
from anvil.schemas import Strict


class Assessment(Strict):
    binding_id: UUID
    evidence_receipt_id: UUID


class ApprovalDecision(Strict):
    decision: Literal["approved", "rejected"]
    rationale: str = Field(min_length=10, max_length=2000)


class Generate(Strict):
    template: str = Field(max_length=30)
    scenario: str = Field(max_length=60)
    seed: StrictInt = Field(default=1, ge=0, le=2147483647)


class ImportCSV(Generate):
    base_pack_id: UUID | None = None
    collection: str = Field(min_length=1, max_length=80)
    csv_text: str = Field(min_length=1, max_length=262144)
    field_mapping: dict[str, str] = Field(min_length=1, max_length=100)
    source_name: str = Field(min_length=1, max_length=120)
    usage_basis: str = Field(min_length=10, max_length=2000)


class Build(Generate):
    name: str = Field(min_length=1, max_length=120, pattern=r".*\S.*")
    runtime_profile: str = Field(default="local-reference-v1", max_length=120)
    defer: bool = Field(default=False, strict=True)


class Version(Strict):
    pack_id: UUID
    name: str = Field(min_length=1, max_length=120, pattern=r".*\S.*")


class Generation(Strict):
    expected_generation: StrictInt = Field(ge=0)


class Revision(Strict):
    expected_revision: StrictInt = Field(ge=0)


class BuildJob(Strict):
    environment_id: UUID
    runtime_profile_id:UUID|None=None


class Operation(Generation):
    operation: str = Field(min_length=1, max_length=60)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded(self):
        if len(json.dumps(self.arguments, allow_nan=False).encode()) > 16384:
            raise ValueError("Operation arguments exceed 16 KiB")
        for key, value in self.arguments.items():
            if (
                not key.isascii()
                or not key.replace("_", "").isalnum()
                or len(key) > 80
                or "\x00" in key
            ):
                raise ValueError("Invalid tool argument name")
            values = value if isinstance(value, list) else [value]
            if len(values) > 100 or any(
                not isinstance(v, str) or len(v) > 5000 or "\x00" in v for v in values
            ):
                raise ValueError("Tool arguments must be bounded text or text arrays")
        return self


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/environments")

    def permit(roles):
        auth.require(roles, "admin", "rl-engineer")

    @router.get("/runtime-profiles")
    def profiles(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            rows = c.execute(
                "SELECT * FROM anvil.environment_runtime_profiles ORDER BY created_at DESC,id DESC LIMIT 100"
            ).fetchall()
            return wrap(
                [
                    r | {"status": "configured_not_cloud_qualified", "cloud_enabled": False}
                    for r in rows
                ],
                request,
            )

    @router.post("/runtime-profiles")
    def configure_profile(project: UUID, body: dict, request: Request):
        from pydantic import ValidationError

        from anvil.db import Jsonb, digest, uid
        from anvil.environment_cloud_build import BuildProfile

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            if (
                set(body) != {"name", "configuration"}
                or not isinstance(body["name"], str)
                or not 1 <= len(body["name"].strip()) <= 120
            ):
                raise HTTPException(422, "Name and exact runtime configuration required")
            try:
                profile = BuildProfile.model_validate(body["configuration"]).model_dump()
            except ValidationError as exc:
                raise HTTPException(
                    422, "Invalid bounded GCP runtime profile; no credentials are accepted"
                ) from exc

            def store():
                return one(
                    c,
                    "INSERT INTO anvil.environment_runtime_profiles(id,project_id,name,configuration,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
                    (uid(), project, body["name"].strip(), Jsonb(profile), digest(profile), user),
                ) | {"status": "configured_not_cloud_qualified", "cloud_enabled": False}

            return wrap(idempotent(c, project, user, request, body, store), request)

    @router.get("/execution-capabilities")
    def execution_capabilities(project: UUID, request: Request):
        import os

        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                {
                    "local_components": True,
                    "openenv_local_protocol": True,
                    "installed_openenv_qualified": False,
                    "installed_openenv_available": os.environ.get(
                        "ANVIL_ENVIRONMENT_OPENENV_ENABLED"
                    )
                    == "true",
                    "harbor_host_mediated": os.environ.get("ANVIL_ENVIRONMENT_NATIVE_ENABLED")
                    == "true",
                    "paid_models": False,
                    "cloud_provisioning": False,
                },
                request,
            )

    @router.get("/build-jobs")
    def build_jobs(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                c.execute(
                    "SELECT * FROM anvil.environment_build_jobs ORDER BY created_at DESC,id DESC LIMIT 100"
                ).fetchall(),
                request,
            )

    @router.post("/build-jobs")
    def new_build_job(project: UUID, body: BuildJob, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: builds.create(c, project, user, body.environment_id,body.runtime_profile_id),
                ),
                request,
            )

    @router.get("/build-jobs/{identifier}")
    def build_job(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(builds.get(c, identifier), request)

    @router.post("/build-jobs/{identifier}/{action}")
    def step_build(
        project: UUID,
        identifier: UUID,
        action: Literal["resume", "cancel"],
        body: Revision,
        request: Request,
    ):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body.model_dump() | {"action": action},
                    lambda: builds.advance(
                        c, user, identifier, body.expected_revision, cancel=action == "cancel"
                    ),
                ),
                request,
            )

    @router.post("/execution-plans")
    def new_execution_plan(project: UUID, request: Request, body: dict):
        from pydantic import ValidationError

        from anvil.environment_execution import Plan, create_plan

        try:
            parsed = Plan.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid bounded environment execution plan") from exc
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c, project, user, request, parsed, lambda: create_plan(c, project, user, parsed)
                ),
                request,
            )

    @router.post("/runs/{identifier}/cancel")
    def cancel_run(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            changed = c.execute(
                "UPDATE anvil.environment_run_controls SET cancel_requested=true WHERE run_id=%s RETURNING run_id",
                (identifier,),
            ).fetchone()
            if not changed:
                raise HTTPException(404, "Environment Run not found")
            return wrap(
                {"run_id": identifier, "cancel_requested": True, "provider_calls": 0}, request
            )

    @router.get("/runs/{identifier}/attempts")
    def attempts(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            if not one(
                c,
                "SELECT run_id FROM anvil.environment_run_controls WHERE run_id=%s",
                (identifier,),
            ):
                raise HTTPException(404, "Environment Run not found")
            return wrap(
                c.execute(
                    "SELECT id,environment_id,model_key,repetition,parent_attempt_id,state,instance_id,evidence_receipt_id,evaluation_id,error_code,created_at FROM anvil.environment_attempts WHERE run_id=%s ORDER BY created_at,id",
                    (identifier,),
                ).fetchall(),
                request,
            )

    @router.post("/runs/{identifier}/retry")
    def retry(project: UUID, identifier: UUID, request: Request):
        from anvil import benchmark_runs as runs

        with context(request, project) as (c, user, roles):
            permit(roles)
            parent = one(c, "SELECT * FROM anvil.benchmark_runs WHERE id=%s", (identifier,))
            if (
                not parent
                or parent["snapshot"].get("schema_version") != "anvil.environment-execution-plan.v1"
            ):
                raise HTTPException(404, "Environment Run not found")
            if parent["state"] not in ("completed", "failed", "blocked"):
                raise HTTPException(409, "Wait for the current Run to terminate before retrying")

            def start_retry():
                child = runs.start(
                    c,
                    project,
                    user,
                    runs.Start(
                        plan_id=parent["plan_id"], expected_plan_sha256=parent["snapshot_sha256"]
                    ),
                )
                c.execute(
                    "INSERT INTO anvil.environment_run_lineage(run_id,project_id,parent_run_id,created_by) VALUES(%s,%s,%s,%s)",
                    (child["id"], project, identifier, user),
                )
                return child | {"parent_run_id": str(identifier)}

            return wrap(
                idempotent(
                    c, project, user, request, {"parent_run_id": str(identifier)}, start_retry
                ),
                request,
            )

    @router.get("/receipts/{identifier}")
    def retained_receipt(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            receipt = one(
                c,
                "SELECT * FROM anvil.environment_receipts WHERE id=%s AND kind='evidence'",
                (identifier,),
            )
            if not receipt:
                raise HTTPException(404, "Evidence receipt not found")
            return wrap(receipt, request)

    @router.get("")
    def listing(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                {
                    "templates": seeds.catalog(),
                    "packs": c.execute(
                        "SELECT id,template_id,scenario_id,content_sha256,validation,created_at FROM anvil.environment_packs ORDER BY created_at DESC,id DESC LIMIT 100"
                    ).fetchall(),
                    "environments": [
                        v | {"readiness": runtime.readiness(c, v)}
                        for v in c.execute(
                            "SELECT * FROM anvil.environment_versions ORDER BY created_at DESC,id DESC LIMIT 100"
                        ).fetchall()
                    ],
                    "instances": c.execute(
                        "SELECT * FROM anvil.environment_instances WHERE state='active' ORDER BY created_at DESC LIMIT 100"
                    ).fetchall(),
                    "provider_calls": 0,
                    "cloud_provisioning": "requires_separate_authority",
                    "runtime": "postgres-local-components-v1",
                },
                request,
            )

    @router.post("/packs/generate")
    def generate(project: UUID, body: Generate, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            try:
                pack = seeds.generate(body.template, body.scenario, body.seed)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: runtime.pack_store(c, project, user, pack),
                ),
                request,
            )

    @router.post("/builds")
    def build(project: UUID, body: Build, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            if body.runtime_profile != "local-reference-v1":
                raise HTTPException(
                    409,
                    "Cloud provisioning is not enabled or authorized; no resources were created",
                )
            try:
                pack = seeds.generate(body.template, body.scenario, body.seed)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

            def run():
                stored = runtime.pack_store(c, project, user, pack)
                version = runtime.create_version(c, project, user, stored["id"], body.name.strip())
                job = builds.create(c, project, user, version["id"])
                if body.defer:
                    return {
                        "environment": version,
                        "job": job,
                        "state": "queued_local",
                        "provider_calls": 0,
                        "cloud_provisioned": False,
                    }
                for revision in range(4):
                    job = builds.advance(c, user, job["id"], revision)
                step = next(s for s in job["steps"] if s["phase"] == "validate")
                receipt = one(
                    c,
                    "SELECT * FROM anvil.environment_receipts WHERE id=%s",
                    (step["content"]["receipt_id"],),
                )
                return {
                    "environment": version,
                    "validation": receipt,
                    "state": "validated_local" if receipt["content"]["passed"] else "failed_local",
                    "registration": "explicit_action_required",
                    "job": job,
                    "cloud_provisioned": False,
                    "provider_calls": 0,
                }

            return wrap(idempotent(c, project, user, request, body, run), request)

    @router.post("/packs/import-csv")
    def import_csv(project: UUID, body: ImportCSV, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            try:
                pack = data_packs.import_csv(
                    body.template,
                    body.scenario,
                    body.seed,
                    body.collection,
                    body.csv_text,
                    body.field_mapping,
                    body.source_name,
                    body.usage_basis,
                    runtime.get(c, "environment_packs", body.base_pack_id)["content"]
                    if body.base_pack_id
                    else None,
                )
            except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
                raise HTTPException(422, str(exc)) from exc
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: runtime.pack_store(c, project, user, pack),
                ),
                request,
            )

    @router.post("/versions")
    def create(project: UUID, body: Version, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: runtime.create_version(
                        c, project, user, body.pack_id, body.name.strip()
                    ),
                ),
                request,
            )

    @router.get("/versions/{environment}")
    def detail(project: UUID, environment: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            version = runtime.get(c, "environment_versions", environment)
            return wrap(
                {
                    "environment": version,
                    "pack": runtime.get(c, "environment_packs", version["pack_id"]),
                    "receipts": c.execute(
                        "SELECT * FROM anvil.environment_receipts WHERE environment_id=%s ORDER BY created_at DESC,id DESC LIMIT 100",
                        (environment,),
                    ).fetchall(),
                },
                request,
            )

    @router.post("/versions/{environment}/validate")
    def validate(project: UUID, environment: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"environment": str(environment)},
                    lambda: validation.validate(c, project, user, environment),
                ),
                request,
            )

    @router.post("/versions/{environment}/register")
    def register(project: UUID, environment: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"environment": str(environment)},
                    lambda: validation.register(c, project, user, environment),
                ),
                request,
            )

    @router.post("/versions/{environment}/instances")
    def instance(project: UUID, environment: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"environment": str(environment)},
                    lambda: runtime.create_instance(c, project, user, environment),
                ),
                request,
            )

    @router.get("/instances/{instance}")
    def inspect(project: UUID, instance: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            row = runtime.get(c, "environment_instances", instance)
            return wrap(
                {
                    "instance": row,
                    "state": runtime.state(c, instance),
                    "events": c.execute(
                        "SELECT * FROM anvil.environment_events WHERE instance_id=%s ORDER BY sequence DESC LIMIT 100",
                        (instance,),
                    ).fetchall(),
                },
                request,
            )

    @router.post("/instances/{instance}/tools")
    def tools(project: UUID, instance: UUID, body: Operation, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: runtime.execute(
                        c, user, instance, body.operation, body.arguments, body.expected_generation
                    ),
                ),
                request,
            )

    @router.get("/instances/{instance}/files")
    def download(project: UUID, instance: UUID, path: str, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            runtime.get(c, "environment_instances", instance)
            row = one(
                c,
                "SELECT media_type,content FROM anvil.environment_files WHERE instance_id=%s AND path=%s",
                (instance, path),
            )
            if not row:
                raise HTTPException(404, "File not present")
            return Response(
                bytes(row["content"]),
                media_type=row["media_type"],
                headers={
                    "Content-Disposition": 'attachment; filename="environment-artifact"',
                    "X-Content-Type-Options": "nosniff",
                },
            )

    @router.post("/instances/{instance}/reset")
    def reset(project: UUID, instance: UUID, body: Generation, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: runtime.reset(c, user, instance, body.expected_generation),
                ),
                request,
            )

    @router.post("/instances/{instance}/evidence")
    def evidence(project: UUID, instance: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"instance": str(instance)},
                    lambda: runtime.export_evidence(c, user, instance),
                ),
                request,
            )

    @router.post("/instances/{instance}/close")
    def close(project: UUID, instance: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"instance": str(instance)},
                    lambda: runtime.close(c, user, instance),
                ),
                request,
            )

    @router.post("/instances/{instance}/approvals/{approval_id}")
    def decide_approval(
        project: UUID, instance: UUID, approval_id: UUID, body: ApprovalDecision, request: Request
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: runtime.decide_approval(
                        c, user, instance, approval_id, body.decision, body.rationale
                    ),
                ),
                request,
            )

    @router.get("/bindings")
    def binding_list(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            rows = c.execute(
                "SELECT * FROM anvil.environment_task_bindings ORDER BY created_at DESC,id DESC LIMIT 100"
            ).fetchall()
            return wrap(
                {
                    "bindings": [bindings.public(r) for r in rows],
                    "evaluations": c.execute(
                        "SELECT * FROM anvil.environment_evaluations ORDER BY created_at DESC,id DESC LIMIT 100"
                    ).fetchall(),
                },
                request,
            )

    @router.get("/versions/{environment}/binding-options")
    def binding_options(project: UUID, environment: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap({"tasks": bindings.options(c, environment)}, request)

    @router.post("/bindings")
    def binding_create(project: UUID, body: bindings.Create, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c, project, user, request, body, lambda: bindings.create(c, project, user, body)
                ),
                request,
            )

    @router.post("/assessments")
    def assess(project: UUID, body: Assessment, request: Request):
        with context(request, project) as (c, user, roles):
            permit(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: bindings.assess(
                        c, project, user, body.binding_id, body.evidence_receipt_id
                    ),
                ),
                request,
            )

    return router
