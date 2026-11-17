"""Fail-closed pilot admission. Full reservations are never automatically released."""

import os

from fastapi import HTTPException

from anvil import pilot_environment
from anvil.db import one, transaction


def issues(c, row):
    try:
        env = pilot_environment.current()
    except ValueError:
        return ["pilot_namespace_binding_invalid"]
    if env is None:
        return []
    if not one(c, "SELECT to_regclass('anvil.pilot_budget_policies') AS table")["table"]:
        return ["pilot_budget_migration_required"]
    policy = one(
        c,
        "SELECT *,start_at<=now() AND end_at>now() AS current FROM anvil.pilot_budget_policies WHERE environment=%s",
        (env,),
    )
    if not policy or not policy["current"] or policy["status"] != "active":
        return ["pilot_budget_policy_absent_expired_or_closed"]
    snapshot = row["snapshot"]["preparation"]
    from anvil.shared_execution_budget import issues as shared_issues

    shared = shared_issues(c, snapshot, row["id"])
    if shared:
        return shared
    cap = snapshot.get("aggregate_cap_micro_usd")
    if type(cap) is not int or not 0 < cap <= policy["run_micro_usd"]:
        return ["pilot_per_run_cap_exceeded"]
    if not snapshot.get("models") or any(
        (m.get("provider"), m.get("model_id")) not in pilot_environment.MODELS[env]
        for m in snapshot["models"]
    ):
        return ["pilot_model_not_approved"]
    reservation = one(
        c, "SELECT * FROM anvil.pilot_budget_reservations WHERE group_id=%s", (row["id"],)
    )
    if reservation:
        if (
            reservation["environment"] != env
            or str(reservation["project_id"]) != str(row["project_id"])
            or reservation["subject_hash"] != row["subject_hash"]
            or reservation["amount_micro_usd"] != cap
        ):
            return ["pilot_reservation_binding_changed"]
    elif row["state"] == "launched":
        return ["pilot_reservation_required"]
    elif (
        not snapshot.get("execution_budget_id")
        and policy["committed_micro_usd"] + cap > policy["total_micro_usd"]
    ):
        return ["pilot_total_cap_exhausted"]
    return []


def reserve(c, row):
    env = pilot_environment.current()
    if env is None:
        return
    missing = issues(c, row)
    if missing:
        raise HTTPException(409, {"message": "Pilot budget blocked", "missing": missing})
    try:
        with c.transaction():
            c.execute("SELECT anvil.reserve_pilot_budget(%s,%s)", (env, row["id"]))
    except Exception as error:
        import psycopg

        if not isinstance(error, psycopg.Error):
            raise
        raise HTTPException(409, "Pilot shared budget reservation blocked") from None


def ticket(row, plan, call):
    if pilot_environment.current() is None:
        return None
    return {
        "project": str(row["project_id"]),
        "actor": str(row["created_by"]),
        "group": str(row["id"]),
        "plan": str(plan),
        "call": str(call),
    }


def dispatch_allowed(binding, ticket, generation, request):
    if not generation and isinstance(ticket, dict) and ticket.get("purpose") == "campaign_semantic":
        from anvil.campaign_semantic_runtime import claim_allowed

        return claim_allowed(binding, ticket, request)
    if generation and isinstance(ticket, dict) and ticket.get("purpose") == "governed_ai":
        from anvil.governed_ai_runtime import claim_allowed

        return claim_allowed(binding, ticket, request)
    try:
        env = pilot_environment.current()
    except ValueError:
        return False
    if env is None:
        return True
    from anvil.worker_dispatch_broker import api_enabled

    if not api_enabled():
        return False
    if (
        generation
        or not isinstance(ticket, dict)
        or set(ticket) != {"project", "actor", "group", "plan", "call"}
    ):
        return False
    if (binding.get("provider"), binding.get("model_id")) not in pilot_environment.MODELS[env]:
        return False
    from uuid import UUID

    try:
        if any(str(UUID(ticket[k])) != ticket[k] for k in ticket):
            return False
    except (ValueError, TypeError, AttributeError):
        return False
    with transaction(ticket["project"], ticket["actor"]) as c:
        row = one(
            c,
            "SELECT * FROM anvil.workspace_execution_groups WHERE id=%s FOR UPDATE",
            (ticket["group"],),
        )
        if (
            not row
            or str(row["project_id"]) != ticket["project"]
            or str(row["created_by"]) != ticket["actor"]
            or row["state"] != "launched"
            or issues(c, row)
        ):
            return False
        plan = one(c, "SELECT * FROM anvil.harbor_agent_plans WHERE id=%s", (ticket["plan"],))
        if (
            not plan
            or str(plan["config"].get("workspace_execution_group")) != ticket["group"]
            or plan["config"]["workspace_model"] != binding
        ):
            return False
        if plan["config"].get("golden_kyc_paid") and plan["config"].get("marketing_paid"):
            return False
        if (
            (
                os.environ.get("ANVIL_GOLDEN_KYC_PAID_ENABLED") == "true"
                or os.environ.get("ANVIL_MARKETING_PAID_ENABLED") == "true"
            )
            and plan["config"].get("golden_kyc_paid") is not True
            and plan["config"].get("marketing_paid") is not True
        ):
            # The bounded final QA exception cannot open unrelated workspace runs.
            return False
        from anvil.workspace_execution import plan_readiness

        if not plan_readiness(c, plan)["ready"]:
            return False
        check = one(c, "SELECT * FROM anvil.harbor_checks WHERE id=%s", (plan["check_id"],))
        if not check or check["state"] != "running" or check["cancel_requested"]:
            return False
        call = one(
            c,
            "SELECT * FROM anvil.harbor_agent_calls WHERE id=%s AND plan_id=%s FOR UPDATE",
            (ticket["call"], ticket["plan"]),
        )
        import hashlib

        if (
            not call
            or call["status"] != "dispatching"
            or not isinstance(call["usage"], dict)
            or call["usage"].get("pilot_broker_claimed")
            or call["request_sha256"] != hashlib.sha256(request.actor_text.encode()).hexdigest()
        ):
            return False
        if not isinstance(call["usage"].get("worker_broker_job"), str):
            return False
        job = one(
            c,
            "SELECT *,lease_until>now() AS current FROM anvil.jobs WHERE id=%s AND project_id=%s",
            (call["usage"].get("worker_broker_job"), ticket["project"]),
        )
        if (
            not job
            or job["kind"]
            != (
                "benchmark_golden_paid"
                if plan["config"].get("golden_kyc_paid")
                else "benchmark_marketing_paid"
                if plan["config"].get("marketing_paid")
                else "harbor_check"
            )
            or job["status"] != "leased"
            or not job["current"]
            or str(job["target_id"]) != str(plan["check_id"])
            or hashlib.sha256(str(job["lease_token"]).encode()).hexdigest()
            != call["usage"].get("worker_broker_lease_sha256")
        ):
            return False
        if not one(c, "SELECT anvil.pilot_dispatch_capacity() ok")["ok"]:
            return False
        if plan["config"].get("golden_kyc_paid") or plan["config"].get(
            "golden_paid_manifest_sha256"
        ):
            from anvil.golden_kyc_paid_budget import claim

            if not claim(c, row, plan, call, binding, request):
                return False
        if plan["config"].get("marketing_paid"):
            from anvil.marketing_paid_budget import claim as claim_marketing

            if plan["config"].get("golden_kyc_paid") or not claim_marketing(
                c, row, plan, call, binding, request
            ):
                return False
        c.execute(
            "UPDATE anvil.harbor_agent_calls SET usage=usage||'{\"pilot_broker_claimed\":true}'::jsonb WHERE id=%s",
            (ticket["call"],),
        )
        return True
