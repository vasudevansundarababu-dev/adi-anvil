"""Actual single-request SDK broker for qualified, bounded AI assistance.

Only the API resolves the saved provider credential. The existing scheduler sends
a one-use SQL lease, never a prompt/model/key. No retries after uncertain effects.
"""

import hashlib
import json
import os
from uuid import UUID

import httpx
import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field

from anvil import (
    auth,
    pilot_environment,
    workspace_costs,
    workspace_credentials,
    workspace_dispatch,
)
from anvil.db import Jsonb, audit, digest, one, transaction, uid
from anvil.evaluation import enqueue
from anvil.governed_ai_catalogue import (
    PURPOSES,
    catalogue,
    prompt,
    validate_output,
)
from anvil.governed_ai_catalogue import context as task_context
from anvil.project_bindings import group
from anvil.providers import ActorRequest
from anvil.schemas import Strict
from anvil.shared_execution_budget import get as budget_get
from anvil.task_parser import json_value
from anvil.task_safety_sources import SourceReference
from anvil.workspace_preparation import model


class Create(Strict):
    budget_id: UUID
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_profile_id: UUID
    purpose: PURPOSES
    target: str | None = Field(default=None, max_length=200)
    safety_categories: list[str] | None = Field(default=None, min_length=5, max_length=10)
    safety_source: SourceReference | None = None
    max_output_tokens: int = Field(default=1024, ge=256, le=8192, strict=True)


class Claim(Strict):
    project_id: UUID
    actor_id: UUID
    job_id: UUID
    lease_token: UUID
    call_id: UUID


class Reconcile(Strict):
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rationale: str = Field(min_length=10, max_length=1000)


def enabled():
    return os.environ.get("ANVIL_GOVERNED_AI_ENABLED", "false") == "true"


def component_ready():
    from anvil.golden_component_qualification import installed

    return installed()["ready"]


def api_enabled():
    from anvil.config import harbor_live_enabled

    return (
        enabled()
        and pilot_environment.current() == "qa"
        and os.environ.get("ANVIL_WORKER_BROKER_ROLE") == "api"
        and os.environ.get("ANVIL_WORKER_BROKER_ENABLED") == "true"
        and harbor_live_enabled()
    )


def bound_cost(binding, text, output_tokens):
    price = workspace_costs.managed(binding["provider"], binding["model_id"])
    if not workspace_costs.current(price):
        raise HTTPException(
            409, {"code": "governed_ai_current_managed_price_required", "owner": "anvil"}
        )
    inputs = len(text.encode()) + 1024  # Token bound, including native envelope.
    amount = max(
        1,
        (
            inputs * workspace_costs.input_bound(price)
            + output_tokens * price["output_micro_usd_per_million_tokens"]
            + 999999
        )
        // 1000000,
    )
    return amount, price


def prepare(c, project, task_group_id, body):
    if not enabled() or not component_ready():
        raise HTTPException(
            409, {"code": "governed_ai_runtime_not_qualified_or_enabled", "owner": "anvil"}
        )
    imported, budget = group(c, project, task_group_id), budget_get(c, body.budget_id)
    if (
        str(budget["task_group_id"]) != str(task_group_id)
        or body.source_sha256 != imported["content_sha256"]
        or budget["source_sha256"] != body.source_sha256
    ):
        raise HTTPException(409, {"code": "governed_ai_source_binding_changed", "owner": "anvil"})
    if not one(c, "SELECT anvil.shared_execution_budget_active(%s) AS allowed", (body.budget_id,))[
        "allowed"
    ]:
        raise HTTPException(409, {"code": "shared_budget_expired_or_revoked", "owner": "anvil"})
    binding = model(c, body.model_profile_id)
    credential = binding.get("credential")
    if not credential or not one(
        c,
        "SELECT 1 FROM anvil.workspace_credentials WHERE id=%s AND current_version_id=%s AND revoked_at IS NULL",
        (credential["id"], credential["version_id"]),
    ):
        raise HTTPException(
            409, {"code": "governed_ai_current_saved_credential_required", "owner": "anvil"}
        )
    if binding not in budget["models"]:
        raise HTTPException(409, {"code": "shared_budget_model_changed", "owner": "anvil"})
    if body.max_output_tokens > binding["max_output_tokens"]:
        raise HTTPException(422, "Requested output bound exceeds this saved model version")
    catalog = catalogue(c, imported)
    clean = task_context(
        imported, catalog, body.purpose, target=body.target, categories=body.safety_categories
    )
    text = prompt(clean)
    framework = None
    if body.safety_source is not None:
        if body.purpose != "safety_generation":
            raise HTTPException(422, "Safety framework source applies only to safety generation")
        from anvil.task_safety_promptfoo import prepare as framework_prepare
        from anvil.task_safety_sources import qualification, reference

        ref = body.safety_source.model_dump(mode="json")
        proof = qualification(c, imported, ref) if ref == reference() else None
        if not proof:
            raise HTTPException(
                409, {"code": "safety_source_qualification_required", "owner": "anvil"}
            )
        purpose = framework_purpose(clean)
        categories = [candidate["id"] for candidate in clean["candidates"]]
        try:
            prepared = framework_prepare(purpose, categories)
        except (ValueError, OSError, KeyError):
            raise HTTPException(
                409, {"code": "safety_source_runtime_unavailable", "owner": "anvil"}
            ) from None
        text = prepared["prompt"]
        framework = {
            "source_ref": ref,
            "qualification": proof,
            "framework_api": prepared["framework_api"],
            "prompt_sha256": prepared["prompt_sha256"],
        }
    amount, price = bound_cost(binding, text, body.max_output_tokens)
    request = {
        "schema_version": "anvil.governed-ai-request.v1",
        "task_group_id": str(task_group_id),
        "source_sha256": body.source_sha256,
        "purpose": body.purpose,
        "selection": {"target": body.target, "categories": body.safety_categories},
        "context_sha256": digest(clean),
        "catalogue_sha256": digest(clean["candidates"]),
        "runtime_source_sha256": catalog["runtime_source_sha256"],
        "broker_source_sha256": catalog["broker_source_sha256"],
        "release_sha256": catalog["release_sha256"],
        "qualifications": [
            q
            for q in catalog["qualifications"]
            if any(
                (q["kind"], q["target"], q["candidate_id"], q["candidate_sha256"])
                == (candidate["kind"], candidate["target"], candidate["id"], candidate["sha256"])
                for candidate in clean["candidates"]
            )
        ],
        "prompt": text,
        "prompt_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "max_output_tokens": body.max_output_tokens,
        "timeout_seconds": 120,
        "price": price,
        "bound_micro_usd": amount,
    }
    if framework:
        request["safety_framework"] = framework
    if len(json.dumps(request).encode()) > 120000:
        raise HTTPException(
            422,
            {
                "code": "governed_ai_intent_limit",
                "owner": "anvil",
                "message": "Exact context and proofs exceed the durable intent bound; no coverage was silently dropped",
            },
        )
    return request, binding


def framework_purpose(clean):
    """Only the same allowlisted, cost-invariant public context enters upstream."""
    return json.dumps(clean, sort_keys=True, ensure_ascii=False, allow_nan=False)


def parse_generation(request, clean, text):
    """Framework parsing never initiates a provider request or SDK retry."""
    framework = request.get("safety_framework")
    if not framework:
        return validate_output(clean, json_value(text)), None
    from anvil.task_safety_promptfoo import parse_recorded

    parsed = parse_recorded(
        framework_purpose(clean),
        [candidate["id"] for candidate in clean["candidates"]],
        request["prompt"],
        text,
    )
    output = {
        "schema_version": "anvil.generated-safety-prompts.v1",
        "categories": [
            {"id": category["id"], "prompts": category["prompts"]}
            for category in parsed["categories"]
        ],
    }
    return validate_output(clean, output), parsed


def current_context(c, row):
    """Fresh source/model/credential/eligibility check at every effect boundary."""
    request = row["request"]
    if digest(request) != row["request_sha256"]:
        raise RuntimeError("governed_ai_request_custody_changed")
    body = Create(
        budget_id=row["budget_id"],
        source_sha256=request["source_sha256"],
        model_profile_id=row["model_binding"]["id"],
        purpose=row["purpose"],
        target=request["selection"]["target"],
        safety_categories=request["selection"]["categories"],
        safety_source=(request.get("safety_framework") or {}).get("source_ref"),
        max_output_tokens=request["max_output_tokens"],
    )
    fresh, binding = prepare(c, row["project_id"], UUID(request["task_group_id"]), body)
    if fresh != request or binding != row["model_binding"]:
        raise RuntimeError("governed_ai_source_eligibility_or_price_changed")
    imported = group(c, row["project_id"], UUID(request["task_group_id"]))
    catalog = catalogue(c, imported)
    return task_context(
        imported, catalog, row["purpose"], target=body.target, categories=body.safety_categories
    )


def semantic_context(c, row):
    """Current meaning/qualification of a saved suggestion, independent of money.

    Expired budgets, changed prices and rotated credentials block new dispatch;
    they do not change an already captured recommendation's task relevance.
    """
    request = row["request"]
    if digest(request) != row["request_sha256"]:
        raise RuntimeError("governed_ai_request_custody_changed")
    imported = group(c, row["project_id"], UUID(request["task_group_id"]))
    if imported["content_sha256"] != request["source_sha256"] or not component_ready():
        raise RuntimeError("governed_ai_source_or_runtime_changed")
    catalog = catalogue(c, imported)
    clean = task_context(
        imported,
        catalog,
        row["purpose"],
        target=request["selection"]["target"],
        categories=request["selection"]["categories"],
    )
    if digest(clean) != request["context_sha256"] or any(
        catalog[key] != request[key]
        for key in ("runtime_source_sha256", "broker_source_sha256", "release_sha256")
    ):
        raise RuntimeError("governed_ai_semantic_eligibility_changed")
    if request.get("safety_framework"):
        from anvil.task_safety_sources import qualification, reference

        framework = request["safety_framework"]
        if (
            framework["source_ref"] != reference()
            or qualification(c, imported, framework["source_ref"]) != framework["qualification"]
        ):
            raise RuntimeError("safety_framework_qualification_changed")
    return clean


def public(row):
    result = row["result"]
    if result is not None and digest(result) != row["result_sha256"]:
        raise HTTPException(409, "Governed AI receipt integrity failed")
    return {
        key: row[key]
        for key in (
            "id",
            "budget_id",
            "purpose",
            "state",
            "request_sha256",
            "bound_micro_usd",
            "actual_micro_usd",
            "created_at",
            "finished_at",
            "result",
            "result_sha256",
        )
    } | {
        "model": {k: row["model_binding"][k] for k in ("provider", "model_id", "config_hash")},
        "binding_automatically_changed": False,
        "paid_benchmark_started": False,
        "needs_operator_review": row["state"] == "execution_unknown",
    }


def recommendation_status(c, imported):
    """Historical suggestions are never substituted with rule-based rankings."""
    rows = []
    catalog = catalogue(c, imported)
    for purpose in ("evaluator_recommendation", "method_recommendation"):
        try:
            clean = task_context(imported, catalog, purpose)
        except (ValueError, HTTPException):
            continue
        rows.extend(
            c.execute(
                "SELECT a.* FROM anvil.governed_ai_calls a JOIN anvil.shared_execution_budgets b ON b.id=a.budget_id AND b.project_id=a.project_id WHERE b.task_group_id=%s AND b.source_sha256=%s AND a.purpose=%s AND a.state='completed' AND a.result->>'origin'='actual_provider_sdk' AND a.request->>'context_sha256'=%s AND a.request->>'runtime_source_sha256'=%s AND a.request->>'broker_source_sha256'=%s AND a.request->>'release_sha256'=%s ORDER BY a.created_at DESC,a.id DESC LIMIT 10",
                (
                    imported["id"],
                    imported["content_sha256"],
                    purpose,
                    digest(clean),
                    catalog["runtime_source_sha256"],
                    catalog["broker_source_sha256"],
                    catalog["release_sha256"],
                ),
            ).fetchall()
        )
    controls = one(
        c,
        "SELECT count(*) AS value FROM anvil.governed_ai_calls a JOIN anvil.shared_execution_budgets b ON b.id=a.budget_id AND b.project_id=a.project_id WHERE b.task_group_id=%s AND b.source_sha256=%s AND a.purpose IN('evaluator_recommendation','method_recommendation') AND a.state='completed' AND a.result->>'origin'='native_sdk_mock'",
        (imported["id"], imported["content_sha256"]),
    )["value"]
    actual, per_purpose = [], {}
    for row in rows:
        public(row)  # Verify immutable result custody before using its origin.
        result = row["result"]
        if per_purpose.get(row["purpose"], 0) >= 10:
            continue
        try:
            semantic_context(c, row)
            eligible = True
        except (ValueError, HTTPException, RuntimeError):
            eligible = False
        # Apply the display limit after origin and semantic eligibility. Each
        # purpose has its own quota; newer controls or stale rows cannot hide it.
        if not eligible:
            continue
        per_purpose[row["purpose"]] = per_purpose.get(row["purpose"], 0) + 1
        actual.append(
            {
                "call_id": str(row["id"]),
                "purpose": row["purpose"],
                "source_sha256": row["request"]["source_sha256"],
                "context_sha256": result["context_sha256"],
                "result_sha256": row["result_sha256"],
                "current_eligibility": eligible,
                "output": result["output"],
            }
        )
    return {
        "status": "actual_suggestions_available"
        if any(item["current_eligibility"] for item in actual)
        else "not_qualified"
        if not component_ready()
        else "not_run_or_not_current",
        "items": actual,
        "software_control_count": controls,
        "reason": "Only captured actual provider suggestions are shown as AI; qualified catalogue metadata and software controls are separate.",
        "requests_path": f"/api/v1/projects/{imported['project_id']}/imported-projects/{imported['id']}/ai/requests",
    }


def authorize(c, claim):
    allowed = one(
        c,
        "SELECT 1 FROM anvil.jobs j JOIN anvil.governed_ai_calls a ON a.id=j.target_id AND a.project_id=j.project_id WHERE j.id=%s AND j.project_id=%s AND j.target_id=%s AND j.kind='benchmark_governed_ai' AND j.status='leased' AND j.lease_token=%s AND j.lease_until>clock_timestamp() AND a.created_by=%s",
        (claim.job_id, claim.project_id, claim.call_id, claim.lease_token, claim.actor_id),
    )
    if not allowed:
        raise RuntimeError("governed_ai_worker_lease_invalid")


def claim_allowed(binding, ticket, request):
    fields = {"purpose", "project", "actor", "job", "lease", "call", "dispatch"}
    if (
        not isinstance(ticket, dict)
        or set(ticket) != fields
        or ticket["purpose"] != "governed_ai"
        or not enabled()
        or not component_ready()
    ):
        return False
    try:
        for key in fields - {"purpose"}:
            if str(UUID(ticket[key])) != ticket[key]:
                return False
        with transaction(ticket["project"], ticket["actor"]) as c:
            row = one(c, "SELECT * FROM anvil.governed_ai_calls WHERE id=%s", (ticket["call"],))
            if (
                not row
                or row["model_binding"] != binding
                or row["request"]["prompt"] != request.actor_text
                or row["request"]["max_output_tokens"] != request.max_output_tokens
                or row["request"]["timeout_seconds"] != request.timeout_seconds
            ):
                return False
            current_context(c, row)
            return bool(
                one(
                    c,
                    "SELECT anvil.claim_governed_ai_sdk(%s,%s,%s,%s,%s,%s) AS allowed",
                    (
                        ticket["job"],
                        ticket["lease"],
                        ticket["call"],
                        ticket["dispatch"],
                        hashlib.sha256(request.actor_text.encode()).hexdigest(),
                        Jsonb(binding),
                    ),
                )["allowed"]
            )
    except (ValueError, TypeError, HTTPException, RuntimeError, psycopg.Error):
        return False


def execute_claim(claim, *, transport=None):
    """Internal API boundary only. Explicit SDK mocks never count as live AI."""
    if transport is not None and type(transport) is not httpx.MockTransport:
        raise ValueError("Only explicit MockTransport is supported for software controls")
    if transport is None and not api_enabled():
        raise RuntimeError("governed_ai_qa_api_dispatch_disabled")
    with transaction(str(claim.project_id), str(claim.actor_id)) as c:
        authorize(c, claim)
        if (
            transport is None
            and one(c, "SELECT is_synthetic FROM anvil.users WHERE id=%s", (claim.actor_id,))[
                "is_synthetic"
            ]
        ):
            raise RuntimeError("governed_ai_live_non_synthetic_Admin_required")
        row = one(c, "SELECT * FROM anvil.governed_ai_calls WHERE id=%s", (claim.call_id,))
        clean = current_context(c, row)
        binding = row["model_binding"]
        credential = binding["credential"]
        from anvil.workspace_secrets import StoreUnavailable

        try:
            secret = workspace_credentials.resolve(c, credential["id"], credential["version_id"])
        except StoreUnavailable:
            raise RuntimeError("governed_ai_saved_credential_unavailable") from None
        token = one(
            c,
            "SELECT anvil.start_governed_ai_call(%s,%s,%s) AS token",
            (claim.job_id, claim.lease_token, claim.call_id),
        )["token"]
        if not token:
            raise RuntimeError("governed_ai_intent_consumed_or_revoked_no_retry")
    # Durable dispatch intent is committed before entering the native SDK.
    request = ActorRequest(
        model=binding["model_id"],
        actor_text=row["request"]["prompt"],
        max_output_tokens=row["request"]["max_output_tokens"],
        timeout_seconds=row["request"]["timeout_seconds"],
    )
    ticket = {
        "purpose": "governed_ai",
        "project": str(claim.project_id),
        "actor": str(claim.actor_id),
        "job": str(claim.job_id),
        "lease": str(claim.lease_token),
        "call": str(claim.call_id),
        "dispatch": str(token),
    }
    from anvil.pilot_concurrency import slot

    cost, parsed, issue, result, framework_receipt = None, None, None, None, None
    try:
        with slot(str(claim.project_id), str(claim.actor_id)):
            result = workspace_dispatch.execute(
                binding, secret, request, generation=True, pilot_ticket=ticket, transport=transport
            )
        if result.status != "completed":
            raise RuntimeError(result.error_code or "governed_ai_sdk_not_completed")
        from anvil.workspace_execution import billed_usage

        inputs, outputs = billed_usage(binding["provider"], result.usage)
        if inputs > len(request.actor_text.encode()) + 1024 or outputs > request.max_output_tokens:
            raise ValueError("governed_ai_usage_exceeds_bound")
        cost = workspace_costs.billed_cost(row["request"]["price"], result.usage, inputs, outputs)
        if cost > row["bound_micro_usd"]:
            raise ValueError("governed_ai_cost_exceeds_bound")
        parsed, framework_receipt = parse_generation(row["request"], clean, result.text)
    except (ValueError, TypeError, SyntaxError, RuntimeError, HTTPException, psycopg.Error) as exc:
        # Raw SDK/code/schema exception strings can contain submitted data.
        issue = type(exc).__name__
    finally:
        del secret
    with transaction(str(claim.project_id), str(claim.actor_id)) as c:
        try:
            if not one(
                c,
                "SELECT anvil.lock_governed_ai_completion(%s,%s) AS allowed",
                (claim.call_id, token),
            )["allowed"]:
                raise RuntimeError("completion_authority_revoked")
            current_context(c, row)
            if not one(
                c, "SELECT anvil.shared_execution_budget_active(%s) AS allowed", (row["budget_id"],)
            )["allowed"]:
                raise RuntimeError("authority_revoked")
        except (ValueError, RuntimeError, HTTPException):
            issue, parsed = "authority_or_eligibility_changed", None
        origin = "native_sdk_mock" if transport is not None else "actual_provider_sdk"
        observed = one(
            c, "SELECT broker_claimed FROM anvil.governed_ai_calls WHERE id=%s", (claim.call_id,)
        )
        admitted = observed["broker_claimed"] if observed else True
        state = (
            "completed"
            if parsed is not None and issue is None
            else "execution_unknown"
            if result is None or result.status == "execution_unknown" or cost is None
            else "error"
        )
        if not admitted:
            state, cost = "error", 0
        charged = cost if transport is None else 0
        receipt = {
            "schema_version": "anvil.governed-ai-result.v1",
            "origin": origin,
            "source_sha256": row["request"]["source_sha256"],
            "context_sha256": row["request"]["context_sha256"],
            "request_sha256": row["request_sha256"],
            "purpose": row["purpose"],
            "output": parsed if not issue else None,
            "error_code": issue,
            "provider_request_id": result.request_id if result else None,
            "model_returned": result.model_returned if result else None,
            "usage": result.usage if result else None,
            "actual_micro_usd": charged,
            "simulated_usage_micro_usd": cost if transport is not None else None,
            "model_performance": False,
            "binding_automatically_changed": False,
        }
        if row["request"].get("safety_framework"):
            receipt["safety_framework"] = framework_receipt if not issue else None
            receipt["generation_framework"] = "promptfoo-custom"
            receipt["raw_response_sha256"] = (
                hashlib.sha256(result.text.encode()).hexdigest()
                if result and isinstance(result.text, str)
                else None
            )
        if not one(
            c,
            "SELECT anvil.finish_governed_ai_call(%s,%s,%s,%s,%s,%s) AS allowed",
            (claim.call_id, token, state, Jsonb(receipt), digest(receipt), charged),
        )["allowed"]:
            raise RuntimeError("governed_ai_completion_unconfirmed_no_retry")
        visible = one(c, "SELECT * FROM anvil.governed_ai_calls WHERE id=%s", (claim.call_id,))
        return (
            public(visible)
            if visible
            else {
                "id": str(claim.call_id),
                "state": state,
                "result_sha256": digest(receipt),
                "result": None,
                "access_revoked": True,
                "binding_automatically_changed": False,
            }
        )


def worker_once(connections, *, transport=None):
    """Same dedicated scheduler, no key access or additional worker process."""
    if not enabled():
        raise RuntimeError("governed_ai_worker_disabled")
    if transport is not None and type(transport) is not httpx.MockTransport:
        raise ValueError("Explicit mock transport only")
    if transport is None and (
        pilot_environment.current() != "qa"
        or os.environ.get("ANVIL_WORKER_BROKER_ROLE") != "worker"
    ):
        raise RuntimeError("governed_ai_qa_scheduler_required")
    with connections() as c:
        claim = one(c, "SELECT anvil.claim_governed_ai_job() AS claim")["claim"]
    if not claim:
        return None
    # A failed/ambiguous RPC is not sent again. Its lease/intent remains retained.
    with httpx.Client(
        transport=transport, trust_env=False, follow_redirects=False, timeout=150
    ) as http:
        response = http.post("http://api:8200/internal/v1/governed-ai/dispatch", json=claim)
        if len(response.content) > 262144:
            raise RuntimeError("governed_ai_rpc_response_bound")
        response.raise_for_status()
        return response.json()


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/imported-projects/{task_group_id}/ai")

    @router.get("/options")
    def options(project: UUID, task_group_id: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            catalog = catalogue(c, group(c, project, task_group_id))
            return wrap(
                {
                    "candidates": catalog["candidates"],
                    "source_sha256": catalog["source_sha256"],
                    "origin": "independently_qualified_catalogue_not_AI_ranking",
                    "enabled": enabled(),
                    "component_qualified": component_ready(),
                },
                request,
            )

    @router.post("/estimate")
    def estimate(project: UUID, task_group_id: UUID, body: Create, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            prepared, binding = prepare(c, project, task_group_id, body)
            return wrap(
                {
                    "bound_micro_usd": prepared["bound_micro_usd"],
                    "prompt_sha256": prepared["prompt_sha256"],
                    "context_sha256": prepared["context_sha256"],
                    "model": {k: binding[k] for k in ("provider", "model_id")},
                    "no_model_call": True,
                },
                request,
            )

    @router.post("/requests")
    def create(project: UUID, task_group_id: UUID, body: Create, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            if not api_enabled():
                raise HTTPException(
                    409, {"code": "governed_ai_paid_dispatch_not_activated", "owner": "anvil"}
                )

            def save():
                prepared, binding = prepare(c, project, task_group_id, body)
                identifier = one(
                    c,
                    "SELECT anvil.reserve_governed_ai_call(%s,%s,%s,%s,%s,%s,%s,%s) AS id",
                    (
                        body.budget_id,
                        uid(),
                        body.purpose,
                        request.headers["Idempotency-Key"],
                        Jsonb(prepared),
                        digest(prepared),
                        Jsonb(binding),
                        prepared["bound_micro_usd"],
                    ),
                )["id"]
                enqueue(
                    c,
                    project,
                    "benchmark_governed_ai",
                    identifier,
                    "governed-ai:" + str(identifier),
                )
                audit(
                    c,
                    project,
                    user,
                    "governed_ai.queued",
                    identifier,
                    {
                        "purpose": body.purpose,
                        "bound_micro_usd": prepared["bound_micro_usd"],
                        "source_sha256": body.source_sha256,
                    },
                )
                return public(
                    one(c, "SELECT * FROM anvil.governed_ai_calls WHERE id=%s", (identifier,))
                )

            return wrap(
                idempotent(c, project, user, request, body.model_dump(mode="json"), save), request
            )

    @router.get("/requests")
    def listing(
        project: UUID, task_group_id: UUID, request: Request, limit: int = Query(20, ge=1, le=100)
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            rows = c.execute(
                "SELECT a.* FROM anvil.governed_ai_calls a JOIN anvil.shared_execution_budgets b ON b.id=a.budget_id WHERE b.task_group_id=%s ORDER BY a.created_at DESC,a.id DESC LIMIT %s",
                (task_group_id, limit),
            ).fetchall()
            return wrap({"items": [public(row) for row in rows]}, request)

    def source_call(c, task_group_id, identifier):
        row = one(
            c,
            "SELECT a.* FROM anvil.governed_ai_calls a JOIN anvil.shared_execution_budgets b ON b.id=a.budget_id AND b.project_id=a.project_id WHERE a.id=%s AND b.task_group_id=%s",
            (identifier, task_group_id),
        )
        if not row:
            raise HTTPException(404, "Governed AI request not found in this Project")
        return row

    @router.get("/requests/{identifier}")
    def retrieve(project: UUID, task_group_id: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            row = source_call(c, task_group_id, identifier)
            return wrap(public(row), request)

    @router.post("/requests/{identifier}/reconcile")
    def reconcile(
        project: UUID, task_group_id: UUID, identifier: UUID, body: Reconcile, request: Request
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            row = source_call(c, task_group_id, identifier)
            if row["request_sha256"] != body.request_sha256:
                raise HTTPException(409, "Governed AI request fingerprint changed")
            status = one(
                c,
                "SELECT anvil.reconcile_governed_ai_call(%s,%s) AS value",
                (identifier, body.request_sha256),
            )["value"]
            if not status:
                raise HTTPException(
                    409,
                    "Only an expired claimed worker lease can be reconciled; no retry or provider request was made",
                )
            if not status.get("already_terminal"):
                receipt = status["receipt"]
                if not one(
                    c,
                    "SELECT anvil.finish_ai_reconciliation(%s,%s,%s,%s) AS allowed",
                    (identifier, body.request_sha256, Jsonb(receipt), digest(receipt)),
                )["allowed"]:
                    raise HTTPException(
                        409, "Reconciliation completion unconfirmed; no provider retry"
                    )
                audit(
                    c,
                    project,
                    user,
                    "governed_ai.reconciled",
                    identifier,
                    {"rationale": body.rationale, "physical_request_replayed": False},
                )
            return wrap(public(source_call(c, task_group_id, identifier)), request)

    return router


def internal_routes():
    router = APIRouter()

    @router.post("/internal/v1/governed-ai/dispatch")
    def dispatch(claim: Claim):
        if not api_enabled():
            raise HTTPException(404, "Governed API broker disabled")
        try:
            return execute_claim(claim)
        except (ValueError, RuntimeError, HTTPException):
            raise HTTPException(
                409, "Governed dispatch denied or completion unconfirmed; do not retry"
            ) from None

    return router
