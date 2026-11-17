"""One retained QA envelope for AI assistance and its resulting benchmark.

Creating a budget is an explicit existing-Admin spending/rights authorization,
not runtime qualification. This module never resolves a key or invokes a model.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, StrictBool

from anvil import auth, pilot_environment
from anvil.db import Jsonb, audit, one, uid
from anvil.schemas import Strict


class Create(Strict):
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_profile_ids: list[UUID] = Field(min_length=1, max_length=8)
    aggregate_cap_micro_usd: int = Field(gt=0, le=2_000_000, strict=True)
    rights_confirmed: StrictBool


class Revoke(Strict):
    reason: str = Field(min_length=10, max_length=1000)


def get(c, identifier):
    row = one(c, "SELECT * FROM anvil.shared_execution_budgets WHERE id=%s", (identifier,))
    if not row:
        raise HTTPException(404, "Shared execution budget not found in this project")
    return row


def public(c, row):
    used = one(
        c,
        "SELECT coalesce(sum(bound_micro_usd),0) AS held,coalesce(sum(actual_micro_usd),0) AS known_actual,count(*) FILTER(WHERE state IN('dispatching','execution_unknown')) AS unknown FROM anvil.governed_ai_calls WHERE budget_id=%s",
        (row["id"],),
    )
    groups = one(
        c,
        "SELECT coalesce(sum(amount_micro_usd),0) AS held FROM anvil.shared_execution_group_allocations WHERE budget_id=%s",
        (row["id"],),
    )
    reserved = one(
        c,
        "SELECT amount_micro_usd FROM anvil.shared_execution_budget_reservations WHERE budget_id=%s",
        (row["id"],),
    )
    active = one(c, "SELECT anvil.shared_execution_budget_active(%s) AS value", (row["id"],))[
        "value"
    ]
    return {
        key: row[key]
        for key in (
            "id",
            "task_group_id",
            "source_sha256",
            "models",
            "cap_micro_usd",
            "created_at",
            "expires_at",
        )
    } | {
        "active": active,
        "pilot_reserved_micro_usd": reserved["amount_micro_usd"] if reserved else 0,
        "ai_held_micro_usd": used["held"],
        "benchmark_held_micro_usd": groups["held"],
        "available_micro_usd": max(0, row["cap_micro_usd"] - used["held"] - groups["held"]),
        "ai_known_actual_micro_usd": used["known_actual"],
        "ai_unknown_calls": used["unknown"],
        "reservation_policy": "Retain all bounds, including unknown/error outcomes; no automatic refund",
        "paid_dispatch_authorized": False,
    }


def issues(c, preparation, group_id=None):
    golden_runtimes = {"golden-kyc-openenv-tool-agent-v1", "marketing-task2-five-role-v1"}
    golden = (
        preparation.get("candidate_runtime") in golden_runtimes
        or preparation.get("preset", {}).get("candidate_runtime") in golden_runtimes
        or preparation.get("package", {}).get("manifest", {}).get("binding") in golden_runtimes
    )
    frozen = preparation.get("project_binding")
    if not frozen:
        return (
            ["shared_budget_source_binding_required"]
            if preparation.get("execution_budget_id") or golden
            else []
        )
    bound = one(c, "SELECT * FROM anvil.project_binding_versions WHERE id=%s", (frozen.get("id"),))
    if not bound:
        return ["shared_budget_source_binding_required"]
    budget = one(
        c,
        "SELECT * FROM anvil.shared_execution_budgets WHERE task_group_id=%s",
        (bound["task_group_id"],),
    )
    if not budget:
        return (
            ["shared_budget_not_found"] if preparation.get("execution_budget_id") or golden else []
        )
    if str(budget["id"]) != preparation.get("execution_budget_id"):
        return ["shared_budget_required_no_separate_allowance"]
    missing = []
    if not one(c, "SELECT anvil.shared_execution_budget_active(%s) AS value", (budget["id"],))[
        "value"
    ]:
        missing.append("shared_budget_expired_or_revoked")
    if bound["snapshot"].get("source_sha256") != budget["source_sha256"]:
        missing.append("shared_budget_source_changed")
    if any(model not in budget["models"] for model in preparation.get("models", [])):
        missing.append("shared_budget_model_changed")
    cap = preparation.get("aggregate_cap_micro_usd")
    allocated = (
        one(
            c,
            "SELECT amount_micro_usd FROM anvil.shared_execution_group_allocations WHERE budget_id=%s AND group_id=%s",
            (budget["id"], group_id),
        )
        if group_id
        else None
    )
    # An existing allocation is checked by071 against the exact group identity;
    # this planning projection must not treat another group's hold as new money.
    if type(cap) is not int or cap <= 0 or cap > budget["cap_micro_usd"]:
        missing.append("shared_budget_run_cap_invalid")
    elif not allocated and cap > public(c, budget)["available_micro_usd"]:
        missing.append("shared_budget_remaining_insufficient")
    return missing


def routes(context, wrap, idempotent):
    router = APIRouter(
        prefix="/api/v1/projects/{project}/imported-projects/{task_group_id}/execution-budget"
    )

    @router.get("")
    def retrieve(project: UUID, task_group_id: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            row = one(
                c,
                "SELECT * FROM anvil.shared_execution_budgets WHERE task_group_id=%s",
                (task_group_id,),
            )
            return wrap(public(c, row) if row else None, request)

    @router.post("")
    def create(project: UUID, task_group_id: UUID, body: Create, request: Request):
        from anvil.workspace_preparation import model, unique

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def save():
                c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
                source = one(
                    c,
                    "SELECT content_sha256 FROM anvil.benchmark_task_groups WHERE id=%s",
                    (task_group_id,),
                )
                if not source:
                    raise HTTPException(404, "Imported Project not found")
                if body.source_sha256 != source["content_sha256"] or not body.rights_confirmed:
                    raise HTTPException(
                        422, "Confirm the exact source, processing rights and one aggregate budget"
                    )
                unique(body.model_profile_ids)
                models = [model(c, identifier) for identifier in body.model_profile_ids]
                if any(
                    (m["provider"], m["model_id"]) not in pilot_environment.MODELS["qa"]
                    for m in models
                ):
                    raise HTTPException(422, "Shared QA budget requires an approved exact model")
                old = one(
                    c,
                    "SELECT * FROM anvil.shared_execution_budgets WHERE task_group_id=%s",
                    (task_group_id,),
                )
                if old:
                    if (
                        old["source_sha256"] != body.source_sha256
                        or old["models"] != models
                        or old["cap_micro_usd"] != body.aggregate_cap_micro_usd
                    ):
                        raise HTTPException(
                            409,
                            "This source already has an immutable shared budget; it cannot acquire another spending allowance",
                        )
                    return public(c, old)
                policy = one(
                    c,
                    "SELECT end_at FROM anvil.pilot_budget_policies WHERE environment='qa' AND status='active' AND start_at<=clock_timestamp() AND end_at>clock_timestamp()",
                )
                if not policy:
                    raise HTTPException(409, {"code": "qa_pilot_policy_required", "owner": "anvil"})
                identifier = uid()
                c.execute(
                    "INSERT INTO anvil.shared_execution_budgets(id,project_id,task_group_id,source_sha256,models,cap_micro_usd,created_by,rights_confirmed,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,true,%s)",
                    (
                        identifier,
                        project,
                        task_group_id,
                        body.source_sha256,
                        Jsonb(models),
                        body.aggregate_cap_micro_usd,
                        user,
                        policy["end_at"],
                    ),
                )
                audit(
                    c,
                    project,
                    user,
                    "shared_budget.authorized",
                    identifier,
                    {
                        "source_sha256": body.source_sha256,
                        "cap_micro_usd": body.aggregate_cap_micro_usd,
                        "purposes": "governed_ai_and_benchmark",
                        "no_paid_dispatch": True,
                    },
                )
                return public(c, get(c, identifier))

            return wrap(
                idempotent(c, project, user, request, body.model_dump(mode="json"), save), request
            )

    @router.post("/revoke")
    def revoke(project: UUID, task_group_id: UUID, body: Revoke, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            row = one(
                c,
                "SELECT * FROM anvil.shared_execution_budgets WHERE task_group_id=%s",
                (task_group_id,),
            )
            if not row:
                raise HTTPException(404, "Shared execution budget not found")
            c.execute(
                "INSERT INTO anvil.shared_execution_budget_revocations(id,project_id,budget_id,created_by,reason) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(budget_id) DO NOTHING",
                (uid(), project, row["id"], user, body.reason),
            )
            audit(c, project, user, "shared_budget.revoked", row["id"])
            return wrap(public(c, row), request)

    return router
