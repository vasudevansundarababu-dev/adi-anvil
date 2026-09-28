from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from anvil import auth, marketing_env
from anvil.db import audit, one, uid
from anvil.evaluation import get_run
from anvil.marketing_authority import CAP, PRICE_EXPIRES, binding, readiness, real_admin, scope
from anvil.provider_api import PaidApproval

router = APIRouter(prefix="/api/v1/projects/{project}")


def routes(context, wrap, idempotent):
    @router.get("/runs/{rid}/marketing")
    def detail(project: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "admin", "advisor", "data-engineer", "product-owner")
            run = get_run(c, rid)
            try:
                ready = readiness(c, run)
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
                ready = {"ready": False, "missing_gates": [exc.detail]}
            episode = one(
                c,
                "SELECT e.id,e.state,s.step,s.state environment_state FROM anvil.episodes e JOIN anvil.interactive_sessions s ON s.episode_id=e.id WHERE e.run_id=%s",
                (rid,),
            )
            calls = []
            if episode:
                calls = c.execute(
                    "SELECT step,status,started_at,finished_at,error_code,result->'usage' usage,result->>'model_returned' model_returned FROM anvil.interactive_calls WHERE episode_id=%s ORDER BY step",
                    (episode["id"],),
                ).fetchall()
                episode["observation"] = marketing_env.observe(episode.pop("environment_state"))
            ledger = one(
                c,
                "SELECT cap_micro_usd,reserved_micro_usd,settled_micro_usd FROM anvil.run_budgets WHERE run_id=%s",
                (rid,),
            )
            return wrap(
                {
                    "readiness": ready,
                    "episode": episode,
                    "calls": calls,
                    "budget": ledger,
                    "billing_status": "Usage is provider-reported; full reservations retained until separate reconciliation. No automatic inference retries.",
                },
                request,
            )

    @router.post("/runs/{rid}/paid-approvals")
    def approve(project: UUID, rid: UUID, body: PaidApproval, request: Request):
        identity = auth.identity(request)
        if (datetime.now(timezone.utc) - identity["issued_at"]).total_seconds() > 600:
            raise HTTPException(403, "Reauthentication required")
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            real_admin(c, project, user)

            def save():
                run = get_run(c, rid, True)
                protocol, _, connection = binding(c, run)
                if (
                    run["state"] != "draft"
                    or body.purpose != "paid_scope"
                    or body.subject_hash != scope(run, protocol, connection)
                    or body.cap_micro_usd != CAP
                    or body.expires_at.tzinfo is None
                    or not datetime.now(timezone.utc) < body.expires_at <= PRICE_EXPIRES
                ):
                    raise HTTPException(
                        409,
                        "Approval must bind the draft run, exact scope, $100 ceiling and current pricing expiry",
                    )
                aid = uid()
                c.execute(
                    "INSERT INTO anvil.provider_approvals(id,project_id,connection_id,approver_id,purpose,subject_hash,cap_micro_usd,authority_reference,expires_at) VALUES(%s,%s,%s,%s,'paid_scope',%s,%s,%s,%s)",
                    (
                        aid,
                        project,
                        connection["id"],
                        user,
                        body.subject_hash,
                        CAP,
                        body.authority_reference,
                        body.expires_at,
                    ),
                )
                audit(
                    c,
                    project,
                    user,
                    "marketing.paid_scope_approved",
                    rid,
                    {"subject_hash": body.subject_hash},
                )
                return {"id": aid, "approved": True}

            return wrap(idempotent(c, project, user, request, body, save), request)

    return router
