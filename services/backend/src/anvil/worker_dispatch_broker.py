"""Lease-bound worker RPC; only the API resolves keys or invokes provider SDKs.

The lease is a short-lived capability kept in the trusted coordinator, never in
actor requests, environments or logs. No caller prompt/model/key is accepted.
"""

import math
import os
from time import monotonic
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import Field

from anvil import pilot_environment
from anvil.db import one, transaction
from anvil.marketing_native_worker_flags import trusted_worker_live_enabled
from anvil.schemas import Strict


class DispatchRequest(Strict):
    project_id: UUID
    actor_id: UUID
    job_id: UUID
    lease_token: UUID
    plan_id: UUID
    stage_index: int = Field(ge=0, le=999, strict=True)
    remaining_seconds: int = Field(ge=1, le=600, strict=True)
    effect_key: str | None = Field(default=None, min_length=1, max_length=180)


class NativeFinish(DispatchRequest):
    native: dict


def harbor_live_enabled():
    """Keep the public alias; only trusted worker callers use the pure read."""
    if os.environ.get('ANVIL_WORKER_BROKER_ROLE') == 'worker':
        return trusted_worker_live_enabled()
    from anvil.config import harbor_live_enabled as validated_api_flag

    return validated_api_flag()


def api_enabled():
    return (
        pilot_environment.current() is not None
        and os.environ.get("ANVIL_WORKER_BROKER_ROLE") == "api"
        and os.environ.get("ANVIL_WORKER_BROKER_ENABLED", "false") == "true"
    )


def authorize(c, claim, *, preparing=False, allow_cancel=False):
    """No lock inversion with worker heartbeat; dispatch intent locks its plan.

    Harbor does not reclaim an invoked uncertain trial. Lease expiry/token change
    fails this check; a timed-out RPC never sends a new inference request.
    """
    row = one(
        c,
        "SELECT j.id FROM anvil.jobs j JOIN anvil.harbor_checks h ON h.id=j.target_id AND h.project_id=j.project_id JOIN anvil.harbor_agent_plans p ON p.id=h.agent_plan_id AND p.project_id=h.project_id WHERE j.id=%s AND j.project_id=%s AND (j.kind='harbor_check' AND coalesce(p.config->>'golden_kyc_paid','false')<>'true' AND coalesce(p.config->>'marketing_paid','false')<>'true' OR j.kind='benchmark_golden_paid' AND p.config->>'golden_kyc_paid'='true' AND coalesce(p.config->>'marketing_paid','false')<>'true' OR j.kind='benchmark_marketing_paid' AND p.config->>'marketing_paid'='true' AND coalesce(p.config->>'golden_kyc_paid','false')<>'true') AND j.status='leased' AND j.lease_token=%s AND j.lease_until>now() AND h.created_by=%s AND p.created_by=%s AND p.id=%s AND h.state=%s AND (NOT h.cancel_requested OR %s) AND p.state='launched'",
        (
            claim.job_id,
            claim.project_id,
            claim.lease_token,
            claim.actor_id,
            claim.actor_id,
            claim.plan_id,
            "queued" if preparing else "running",
            allow_cancel,
        ),
    )
    if not row:
        raise RuntimeError("worker_dispatch_claim_invalid")


def forward(
    job,
    actor,
    plan,
    stage,
    *,
    remaining_seconds=120,
    operation="dispatch",
    transport=None,
    native=None,
    effect_key=None,
    absolute_deadline=None,
):
    if pilot_environment.current() is None:
        raise RuntimeError("pilot_worker_broker_required")
    if os.environ.get("ANVIL_WORKER_BROKER_ROLE") != "worker":
        raise RuntimeError("worker_broker_role_required")
    if (
        os.environ.get("ANVIL_WORKER_BROKER_ENABLED", "false") != "true"
        or not harbor_live_enabled()
    ):
        raise RuntimeError("worker_dispatch_disabled")
    # One exact private service endpoint; never follow redirects/proxy variables
    # or send lease capability to a caller-supplied host/path.
    if os.environ.get("ANVIL_WORKER_BROKER_URL") != "http://api:8200/internal/v1/worker-dispatch":
        raise RuntimeError("worker_broker_endpoint_invalid")
    if operation not in {"dispatch", "readiness", "prepare", "capture", "finish", "wave"}:
        raise ValueError("worker_broker_operation_invalid")
    if transport is not None and type(transport) is not httpx.MockTransport:
        raise ValueError("Only explicit MockTransport is supported")
    if absolute_deadline is not None:
        if (operation not in {"dispatch", "readiness"} or transport is not None
                or type(absolute_deadline) not in (int, float)
                or not math.isfinite(absolute_deadline)):
            raise ValueError("Exact fixed phased broker transport required")
        left = absolute_deadline - monotonic()
        if not 1 <= left <= 600:
            raise TimeoutError("Worker graph phase expired or extended")
        if type(remaining_seconds) is not int or not 1 <= remaining_seconds <= 600:
            raise ValueError("Exact current request budget required")
        remaining_seconds = min(remaining_seconds, int(left))
    body = DispatchRequest(
        project_id=job["project_id"],
        actor_id=actor,
        job_id=job["id"],
        lease_token=job["lease_token"],
        plan_id=plan,
        stage_index=stage,
        remaining_seconds=remaining_seconds,
        effect_key=effect_key,
    )
    payload = body.model_dump(mode="json", exclude_none=True)
    if operation == "finish":
        payload = NativeFinish(**body.model_dump(), native=native).model_dump(
            mode="json", exclude_none=True
        )
    elif native is not None:
        raise ValueError("unexpected_native_receipt")
    try:
        if absolute_deadline is not None:
            from anvil.dataset_export_contract import json_object
            from anvil.marketing_paid_dispatch_transport import execute

            raw = execute(operation, payload, absolute_deadline=absolute_deadline,
                          request_seconds=remaining_seconds)
            value = json_object(raw)
            if monotonic() >= absolute_deadline:
                raise TimeoutError("Worker graph phase elapsed during response")
            return _forward_value(value, operation)
        with httpx.Client(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=remaining_seconds + 20,
        ) as client:
            response = client.post(
                os.environ["ANVIL_WORKER_BROKER_URL"] + "/" + operation,
                json=payload,
            )
            response.raise_for_status()
            if len(response.content) > 131072:
                raise ValueError("worker_broker_response_limit")
            value = response.json()
            return _forward_value(value, operation)
    except Exception:
        # Deliberately omit endpoint body, lease, secret and provider exceptions.
        # No retry. Server ledger determines whether any dispatch occurred.
        raise RuntimeError("worker_broker_unavailable_or_outcome_unknown_no_retry") from None


def _forward_value(value, operation):
    if operation in {"prepare", "capture", "finish", "wave"}:
        if not isinstance(value, dict):
            raise ValueError("worker_broker_response_invalid")
        return value
    if operation == "readiness":
        if type(value) is not dict or set(value) != {"ready"} or value["ready"] is not True:
            raise ValueError("worker_readiness_revoked")
        return True
    if (type(value) is not dict or set(value) != {"output"}
            or not isinstance(value["output"], str)
            or len(value["output"].encode()) > 65536):
        raise ValueError("worker_broker_output_invalid")
    return value["output"]


def routes():
    # Creating HTTP routes still requires the ORIGINAL full API configuration,
    # including its session/auth settings. Importing a worker client does not.
    from anvil.config import environment

    environment()
    router = APIRouter(prefix="/internal/v1/worker-dispatch")

    def gate(*, world_stop=False):
        try:
            enabled = api_enabled()
        except ValueError:
            enabled = False
        stop_enabled = (
            world_stop
            and pilot_environment.current() == "qa"
            and os.environ.get("ANVIL_MARKETING_WORLD_STOP_ENABLED") == "true"
        )
        if not enabled or not (stop_enabled or harbor_live_enabled()):
            raise HTTPException(404, "Worker dispatch unavailable")

    from anvil.campaign_semantic_contract import Claim as SemanticClaim
    from anvil.marketing_paid_world import WorldCall

    @router.post("/world")
    def world(body: WorldCall, background_tasks: BackgroundTasks):
        gate(world_stop=body.operation in {"fence", "drain", "quiescence"})
        from anvil.marketing_world_api import dispatch as private_world

        try:
            return private_world(body, after_response=lambda callback: background_tasks.add_task(callback))
        except Exception:
            raise HTTPException(
                409, "Private world denied or outcome unknown; do not retry"
            ) from None

    @router.post("/judge")
    def judge(body: SemanticClaim):
        gate()
        from anvil.campaign_semantic_runtime import dispatch as private_judge
        from anvil.pilot_concurrency import slot

        try:
            with slot(body.project_id, body.actor_id):
                return private_judge(body)
        except Exception:
            raise HTTPException(
                409, "Private evaluator dispatch denied or outcome unknown; do not retry"
            ) from None

    @router.post("/prepare")
    def prepare(body: DispatchRequest):
        gate()
        from anvil.pilot_native_api import prepare as prepare_native

        try:
            return prepare_native(body)
        except Exception:
            raise HTTPException(409, "Native preparation denied") from None

    @router.post("/wave")
    def wave(body: DispatchRequest):
        gate()
        from anvil.workflow_native_execution import wave as next_wave

        try:
            return next_wave(body)
        except Exception:
            raise HTTPException(
                409, "Workflow admission denied or outcome unknown; do not retry"
            ) from None

    @router.post("/capture")
    def capture(body: DispatchRequest):
        gate()
        from anvil.pilot_native_api import capture_receipt

        try:
            with transaction(body.project_id, body.actor_id) as c:
                authorize(c, body)
                return capture_receipt(c, body)
        except Exception:
            raise HTTPException(409, "Native capture unavailable") from None

    @router.post("/finish")
    def finish(body: NativeFinish):
        gate()
        from anvil.pilot_native_api import finish as finish_native

        try:
            return finish_native(body)
        except Exception:
            raise HTTPException(
                409, "Native capture denied or outcome unknown; do not retry"
            ) from None

    @router.post("/readiness")
    def readiness(body: DispatchRequest):
        gate()
        from anvil import harbor_agents, workspace_execution

        try:
            with transaction(body.project_id, body.actor_id) as c:
                authorize(c, body)
                if not workspace_execution.plan_readiness(c, harbor_agents.plan(c, body.plan_id))[
                    "ready"
                ]:
                    raise RuntimeError("worker_readiness_revoked")
        except Exception:
            raise HTTPException(409, "Worker dispatch admission denied") from None
        return {"ready": True}

    @router.post("/dispatch")
    def dispatch(body: DispatchRequest, request: Request):
        gate()
        from anvil.workspace_execution import decision

        try:
            from anvil.pilot_concurrency import slot

            with slot(body.project_id, body.actor_id):
                text = decision(
                    body.project_id,
                    body.actor_id,
                    body.plan_id,
                    body.stage_index,
                    remaining_seconds=body.remaining_seconds,
                    broker_claim=body,
                )
        except Exception:
            raise HTTPException(
                409, "Worker dispatch denied or outcome unknown; do not retry"
            ) from None
        return {"output": text}

    from anvil.golden_kyc_deadline_api import routes as kyc_routes

    router.include_router(kyc_routes(gate))
    return router
