from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Jsonb
from pydantic import Field

from anvil import auth
from anvil.db import audit, digest, one, uid
from anvil.providers import PROVIDERS, secret_presence
from anvil.schemas import Strict

router = APIRouter(prefix="/api/v1/projects/{project}")


class ProviderConfig(Strict):
    model_id: str | None = Field(default=None, max_length=200)
    max_output_tokens: int = Field(default=4096, ge=1, le=8192)
    pricing_revision: str | None = None
    bound_micro_usd: int | None = Field(default=None, ge=1)
    processing_terms_reviewed: bool = False


class PaidApproval(Strict):
    purpose: Literal["activation", "paid_scope"]
    subject_hash: str = Field(min_length=64, max_length=64)
    cap_micro_usd: int = Field(gt=0)
    authority_reference: str = Field(min_length=10)
    expires_at: datetime


def readiness(c, provider, connection=None):
    present, secret_error = secret_presence(provider)
    missing = [
        "explicit_user_live_authority",
        "real_distinct_admin_activation",
        "real_distinct_admin_paid_scope",
        "reviewed_actor_processing_rights",
        "frozen_live_protocol",
        "live_dispatch_qualification",
    ]
    marketing = provider == "openai" and connection and connection["model_id"] == "gpt-6-sol"
    if marketing:
        missing = ["check_exact_marketing_run_readiness_in_run_console"]
    if not present:
        missing.append(secret_error or "secret_missing")
    if not connection or not connection["model_id"]:
        missing.append("exact_model_missing")
    if not connection or not connection["config"].get("pricing_revision"):
        missing.append("pricing_missing")
    if not connection or not connection["config"].get("bound_micro_usd"):
        missing.append("conservative_cost_bound_missing")
    return {
        "id": str(connection["id"]) if connection else provider,
        "kind": "provider",
        "lifecycle": "blocked",
        "row_version": connection["row_version"] if connection else 0,
        "content": {
            "title": PROVIDERS[provider][0],
            "provider_key": provider,
            "specified": True,
            "implemented": True,
            "contract_tested": True,
            "live_verified": False,
            "secret_present": present,
            "model_id": connection["model_id"] if connection else None,
            "destination": PROVIDERS[provider][2],
            "missing_gates": missing,
            "inference_requests": None if marketing else 0,
            "integration_scope": (
                "13-response marketing harness; mocked transport and durable local workflow. Paid launch requires exact run readiness and real approvals. Live verification not performed."
                if marketing
                else "Official SDK mocked transport; live dispatch unavailable pending qualification and authority"
            ),
        },
        "content_hash": connection["config_hash"] if connection else None,
    }


def routes(context, wrap, idempotent):
    @router.get("/providers")
    def providers(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "admin")
            return wrap(
                [
                    readiness(
                        c,
                        key,
                        one(
                            c,
                            "SELECT * FROM anvil.connections WHERE provider_key=%s AND NOT(config ? 'workspace_profile_version') ORDER BY created_at DESC LIMIT 1",
                            (key,),
                        ),
                    )
                    for key in PROVIDERS
                ],
                request,
            )

    @router.post("/providers/{provider}/config")
    def configure(project: UUID, provider: str, body: ProviderConfig, request: Request):
        if provider not in PROVIDERS:
            raise HTTPException(404, "Provider not found")
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def save():
                config = body.model_dump(mode="json")
                cid = uid()
                binding = {
                    **config,
                    "provider": provider,
                    "destination": PROVIDERS[provider][2],
                    "adapter_version": "static-v1",
                }
                c.execute(
                    "INSERT INTO anvil.connections(id,project_id,provider_key,model_id,destination,secret_reference,config,config_hash,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        cid,
                        project,
                        provider,
                        body.model_id,
                        PROVIDERS[provider][2],
                        PROVIDERS[provider][1],
                        Jsonb(config),
                        digest(binding),
                        user,
                    ),
                )
                audit(
                    c,
                    project,
                    user,
                    "provider.configured",
                    cid,
                    {"provider": provider, "config_hash": digest(binding)},
                )
                return readiness(
                    c, provider, one(c, "SELECT * FROM anvil.connections WHERE id=%s", (cid,))
                )

            return wrap(idempotent(c, project, user, request, body, save), request)

    @router.post("/connections/{cid}/approvals")
    def approve(project: UUID, cid: UUID, body: PaidApproval, request: Request):
        identity = auth.identity(request)
        if (datetime.now(timezone.utc) - identity["issued_at"]).total_seconds() > 600:
            raise HTTPException(403, "Reauthentication required")
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            record = one(c, "SELECT * FROM anvil.connections WHERE id=%s", (cid,))
            if not record:
                raise HTTPException(404, "Connection not found")
            if (
                record["config_hash"] != body.subject_hash
                or body.expires_at.tzinfo is None
                or body.expires_at <= datetime.now(timezone.utc)
            ):
                raise HTTPException(409, "Approval hash or expiry invalid")
            from anvil.marketing_authority import CAP, PRICE_EXPIRES, active_admin, config_valid

            active_admin(c, project, user)
            if body.purpose != "activation":
                raise HTTPException(409, "Paid scope must be approved on the exact configured run")
            if (
                not config_valid(record)
                or body.cap_micro_usd != CAP
                or body.expires_at > PRICE_EXPIRES
            ):
                raise HTTPException(
                    409, "Use the reviewed marketing configuration, $100 ceiling and pricing expiry"
                )

            def save():
                aid = uid()
                c.execute(
                    "INSERT INTO anvil.provider_approvals(id,project_id,connection_id,approver_id,purpose,subject_hash,cap_micro_usd,authority_reference,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        aid,
                        project,
                        cid,
                        user,
                        body.purpose,
                        body.subject_hash,
                        body.cap_micro_usd,
                        body.authority_reference,
                        body.expires_at,
                    ),
                )
                audit(c, project, user, "provider.activation_approved", cid)
                return {"id": aid, "approved": True}

            return wrap(idempotent(c, project, user, request, body, save), request)

    @router.post("/providers/dry-run")
    def dry_run(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "admin")
            return wrap(
                {
                    "status": "blocked",
                    "inference_requests": 0,
                    "providers": [readiness(c, k)["content"] for k in PROVIDERS],
                },
                request,
            )

    return router
