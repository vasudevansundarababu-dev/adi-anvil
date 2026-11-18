"""Scoped planning/trace endpoints. Neither registration nor reporting dispatches."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, ValidationError

from anvil import auth
from anvil.db import one
from anvil.golden_kyc_paid_budget import register
from anvil.golden_kyc_paid_contract import PaidKYCManifest
from anvil.golden_kyc_policy_registry import ReceiptReference
from anvil.praxis_generic_contract import load
from anvil.schemas import Strict


class NativePackage(Strict):
    resolved_task_id: UUID
    max_model_calls: int = Field(ge=1, le=100, strict=True)
    resolved_input: ReceiptReference | None = None


class NativeTaskSet(Strict):
    resolved_task_ids: list[UUID] = Field(min_length=1, max_length=5)
    max_model_calls: int = Field(ge=1, le=100, strict=True)
    resolved_input: ReceiptReference | None = None


def report(c, project, group_id):
    saved = one(
        c,
        "SELECT * FROM anvil.golden_paid_manifests WHERE project_id=%s AND group_id=%s",
        (project, group_id),
    )
    if not saved:
        raise HTTPException(404, "Golden paid group not found in project")
    calls = c.execute(
        "SELECT a.id,a.stage_index,a.status,a.request_sha256,a.reserved_micro_usd,a.actual_micro_usd,a.request_id,a.usage,a.finished_at,p.id AS plan_id,p.config FROM anvil.harbor_agent_calls a JOIN anvil.harbor_agent_plans p ON p.id=a.plan_id AND p.project_id=a.project_id WHERE a.project_id=%s AND p.config->>'workspace_execution_group'=%s ORDER BY p.created_at,p.id,a.stage_index",
        (project, str(group_id)),
    ).fetchall()
    physical = []
    for call in calls:
        usage = call["usage"] or {}
        physical.append(
            {
                "call_id": str(call["id"]),
                "plan_id": str(call["plan_id"]),
                "stage_index": call["stage_index"],
                "status": call["status"],
                "request_sha256": call["request_sha256"],
                "provider_request_id": call["request_id"],
                "origin": usage.get("dispatch_origin"),
                "usage": usage,
                "model": call["config"]["workspace_model"],
                "parameters": {
                    k: call["config"][k] for k in ("max_output_tokens", "request_timeout_seconds")
                },
                "reserved_micro_usd": call["reserved_micro_usd"],
                "actual_micro_usd": call["actual_micro_usd"],
            }
        )
    provider = [r for r in physical if r["origin"] == "provider"]
    unknown = [r["call_id"] for r in provider if r["actual_micro_usd"] is None]
    reservation = one(
        c,
        "SELECT environment,amount_micro_usd FROM anvil.pilot_budget_reservations WHERE group_id=%s AND project_id=%s",
        (group_id, project),
    )
    evaluations = c.execute(
        "SELECT b.plan_id,b.application_id,b.trial_id,b.generation,s.summary FROM banking.paid_agent_bindings b LEFT JOIN banking.evaluation_summaries s ON s.project_id=b.project_id AND s.trial_id=b.trial_id AND s.generation=b.generation WHERE b.project_id=%s AND b.group_id=%s ORDER BY b.created_at,b.plan_id",
        (project, group_id),
    ).fetchall()
    graded = bool(evaluations) and all(row["summary"] is not None for row in evaluations)
    return {
        "schema_version": "anvil.golden-paid-trace-report.v1",
        "group_id": str(group_id),
        "manifest_sha256": saved["manifest_sha256"],
        "source_manifest": saved["manifest"],
        "physical_requests": physical,
        "actual_provider_request_count": len(provider),
        "actual_run": bool(provider),
        "benchmark_scope": {
            "planned_application_ids": sorted(
                {item["case_id"] for item in saved["manifest"]["requests"]}
            ),
            "captured_application_ids": sorted({row["application_id"] for row in evaluations}),
            "full_200_case_benchmark_completed": False,
            "population_performance_claim": False,
        },
        "known_actual_micro_usd": sum(
            r["actual_micro_usd"] for r in provider if r["actual_micro_usd"] is not None
        ),
        "unknown_cost_call_ids": unknown,
        "shared071_reservation": reservation,
        "automatic_refund": False,
        "model_performance_validated": False,
        "independent_review": "Dash verification required",
        "scores": evaluations if graded else None,
        "grading_status": "sealed_state_evaluated_human_legal_review_separate"
        if graded
        else "separate sealed-state evaluator and review gates required",
    }


def routes(context, wrap, idempotent):
    router = APIRouter()

    @router.get("/paid-tasks")
    def native_tasks(project: UUID, request: Request):
        from anvil.golden_kyc_paid_session import task_context
        from anvil.praxis_case_dataset import CaseDataset, StateTaskContext
        from anvil.praxis_case_registry import lookup

        with context(request, project) as (c, _, roles):
            auth.require(roles, "admin", "rl-engineer")
            rows = c.execute(
                "SELECT r.id,r.task_key,r.revision,r.actor,r.binding FROM anvil.praxis_resolved_tasks r WHERE r.project_id=%s AND r.binding ? 'case_context' ORDER BY r.created_at DESC,r.id LIMIT 100",
                (project,),
            ).fetchall()
            items = []
            for row in rows:
                ready, reasons = False, []
                try:
                    ctx = StateTaskContext.model_validate(row["binding"]["case_context"])
                    dataset = lookup(c, project, ctx.caseDataset)
                    if not dataset or not dataset["qualified"]:
                        reasons.append("Current qualified dataset and environment required")
                    else:
                        members = CaseDataset.model_validate(dataset["manifest"]).select(
                            ctx.caseDataset, ctx.caseSelector
                        )
                        task_context(c, project, row["id"], members[0].id)
                        ready = True
                    public = {
                        "state": ctx.caseSelector.value,
                        "case_count": ctx.caseSelector.case_count,
                        "case_dataset": ctx.caseDataset.model_dump(),
                    }
                except (ValueError, RuntimeError, HTTPException):
                    public = {}
                    reasons.append(
                        "Published task, policy and runtime bindings need Anvil qualification"
                    )
                items.append(
                    {
                        "resolved_task_id": str(row["id"]),
                        "task_id": row["task_key"],
                        "revision": row["revision"],
                        "title": row["actor"].get("title", row["task_key"]),
                        **public,
                        "ready_for_package": ready,
                        "anvil_requirements": reasons,
                    }
                )
            return wrap(items, request)

    @router.post("/paid-task-packages")
    def prepare_state_tasks(project: UUID, body: NativeTaskSet, request: Request):
        from anvil.golden_kyc_paid_package import prepare

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            if len(set(body.resolved_task_ids)) != len(body.resolved_task_ids):
                raise HTTPException(422, "Select each reusable state task once")

            def create():
                if body.resolved_input is not None:
                    if not 1 <= len(body.resolved_task_ids) <= 4:
                        raise HTTPException(422, "Select one to four reusable application product tasks")
                    products, packages = set(), []
                    reference = body.resolved_input.model_dump(mode="json")
                    for identifier in body.resolved_task_ids:
                        row = one(c, "SELECT binding FROM anvil.praxis_resolved_tasks WHERE project_id=%s AND id=%s", (project, identifier))
                        selector = row["binding"].get("case_selector", {}) if row else {}
                        product = selector.get("value")
                        if (not row or row["binding"].get("task_mode") != "reusable_application_workflow"
                                or selector.get("field") != "product" or product in products
                                or product not in {"individual", "adult_joint", "teen_joint", "custodial"}):
                            raise HTTPException(409, "Distinct current product tasks required")
                        products.add(product)
                        packages.append(prepare(c, project, user, identifier, body.max_model_calls, resolved_input=reference))
                    return {"packages": packages, "task_count": len(packages), "resolved_input": reference,
                            "run_authority": "not_granted", "paid_calls": False}
                packages, states, shared = [], set(), None
                for identifier in body.resolved_task_ids:
                    row = one(
                        c,
                        "SELECT binding FROM anvil.praxis_resolved_tasks WHERE project_id=%s AND id=%s",
                        (project, identifier),
                    )
                    context_binding = row["binding"].get("case_context") if row else None
                    if not context_binding:
                        raise HTTPException(
                            409, "Only corrected reusable state tasks may enter this task set"
                        )
                    state = context_binding["caseSelector"]["value"]
                    if state in states:
                        raise HTTPException(422, "Select one task per governing state")
                    states.add(state)
                    descriptor = context_binding["caseDataset"]
                    if shared is not None and descriptor != shared:
                        raise HTTPException(
                            409, "State tasks must reference the same dataset version"
                        )
                    shared = descriptor
                    packages.append(prepare(c, project, user, identifier, body.max_model_calls))
                return {
                    "packages": packages,
                    "task_count": len(packages),
                    "run_authority": "not_granted",
                    "paid_calls": False,
                }

            return wrap(
                idempotent(c, project, user, request, body.model_dump(mode="json"), create), request
            )

    @router.post("/paid-packages")
    def prepare_native(project: UUID, body: NativePackage, request: Request):
        from anvil.golden_kyc_paid_package import prepare

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            try:
                value = idempotent(
                    c,
                    project,
                    user,
                    request,
                    body.model_dump(mode="json"),
                    lambda: prepare(c, project, user, body.resolved_task_id, body.max_model_calls,
                                    resolved_input=body.resolved_input.model_dump(mode="json") if body.resolved_input else None),
                )
            except RuntimeError:
                raise HTTPException(
                    409,
                    "Current published task, native runtime and exact qualification bindings required",
                ) from None
            return wrap(value, request)

    @router.post("/paid-manifests")
    async def create(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            try:
                raw = load(await request.body())
                manifest = PaidKYCManifest.model_validate(raw)
            except (ValueError, ValidationError):
                raise HTTPException(422, "Invalid bounded physical-request manifest") from None
            if manifest.project_id != str(project):
                raise HTTPException(404, "Group not found in project")
            group = one(
                c,
                "SELECT * FROM anvil.workspace_execution_groups WHERE id=%s AND project_id=%s FOR UPDATE",
                (manifest.group_id, project),
            )
            if not group:
                raise HTTPException(404, "Group not found in project")
            try:
                row = idempotent(
                    c,
                    project,
                    user,
                    request,
                    raw,
                    lambda: {
                        "manifest_sha256": register(c, group, user, raw)["manifest_sha256"],
                        "group_id": manifest.group_id,
                        "dispatch_authorized": False,
                    },
                )
            except ValueError:
                raise HTTPException(
                    409, "Exact qualified Golden import, draft group and current bounds required"
                ) from None
            return wrap(row, request)

    @router.get("/paid-groups/{group_id}/report")
    def inspect(project: UUID, group_id: UUID, request: Request):
        with context(request, project) as (c, _, roles):
            auth.require(roles, "admin", "rl-engineer")
            return wrap(report(c, project, group_id), request)

    @router.post("/paid-groups/{group_id}/reconcile")
    def reconcile_expired(project: UUID, group_id: UUID, request: Request):
        from anvil.golden_kyc_paid_execution import reconcile

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"group_id": str(group_id)},
                    lambda: reconcile(c, project, user, group_id),
                ),
                request,
            )

    return router
