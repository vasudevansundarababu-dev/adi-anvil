"""Server-mediated bounded JSON agent. Provider credentials never enter Harbor.

The operator's exact user authorization is required independently of app approvals.
Entire run ceilings remain reserved in the shared spend window, including unknown calls.
No implicit retry, budget release or inference from old marketing-only authority.
"""

import hashlib
import hmac
import io
import os
import secrets
import socket
import stat
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, Field

from anvil import artifacts, auth, domain, providers
from anvil.config import ROOT, harbor_live_enabled, private_file_owner
from anvil.db import Jsonb, audit, digest, one, project_fence, transaction, uid
from anvil.harbor_package import encoded
from anvil.praxis_contract import Binding, matches
from anvil.schemas import Strict
from anvil.task_parser import json_value

AGENT = "anvil-structured-json-v1"
AGENT_IMPORT = "anvil_harbor.agent:StructuredAgent"
MAX_PROMPT_BYTES = 32768
MAX_OUTPUT_TOKENS = 2048


def code_digest():
    paths = [
        ROOT / "services/backend/src/anvil" / name
        for name in (
            "harbor_agents.py",
            "harbor_worker.py",
            "harbor_package.py",
            "praxis_contract.py",
            "praxis_staged.py",
            "providers.py",
            "db.py",
            "auth.py",
            "config.py",
            "domain.py",
            "artifacts.py",
            "marketing_authority.py",
            "workspace_execution.py",
            "workspace_dispatch.py",
            "workspace_adapter_contracts.py",
            "workspace_preparation.py",
            "workspace_models.py",
            "workspace_credentials.py",
            "workspace_secrets.py",
        )
    ]
    paths.append(ROOT / "services/harbor/src/anvil_harbor/agent.py")
    return digest(
        {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    )


class Authority(Strict):
    reference: str = Field(pattern=r"^harbor:[A-Za-z0-9_.-]{5,100}$")
    project_id: UUID
    provider: Literal["openai"]
    model: str = Field(min_length=1, max_length=200)
    total_cap_micro_usd: int = Field(gt=0, strict=True)
    input_micro_usd_per_million_tokens: int = Field(gt=0, strict=True)
    output_micro_usd_per_million_tokens: int = Field(gt=0, strict=True)
    pricing_revision: str = Field(min_length=5)
    expires_at: AwareDatetime
    pricing_expires_at: AwareDatetime


def authority():
    path = ROOT / ".local/harbor-authority.json"
    try:
        if path.is_symlink() or not path.is_file():
            return None
        info = path.stat()
        if (
            stat.S_IMODE(info.st_mode) & 0o077
            or not private_file_owner(info.st_uid)
            or not 0 < info.st_size <= 16384
        ):
            return None
        value = Authority.model_validate_json(path.read_bytes())
    except (ValueError, OSError):
        return None
    now = datetime.now(timezone.utc)
    return value if value.expires_at > now and value.pricing_expires_at > now else None


def call_bound(policy):
    # Text-only UTF-8 input: one token per byte plus a conservative envelope margin.
    return (
        (MAX_PROMPT_BYTES + 1024) * policy.input_micro_usd_per_million_tokens
        + MAX_OUTPUT_TOKENS * policy.output_micro_usd_per_million_tokens
        + 999999
    ) // 1000000


class Plan(Strict):
    connection_id: UUID
    agent: Literal["anvil-structured-json-v1"]
    model: str = Field(min_length=1, max_length=200)
    max_total_micro_usd: int = Field(gt=0, le=1000000000, strict=True)
    trials: Literal[1]


class POReview(Strict):
    subject_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    rights_evidence_id: UUID
    rationale: str = Field(min_length=10, max_length=2000)
    expires_at: AwareDatetime


class AdminReview(Strict):
    purpose: Literal["activation", "paid_scope"]
    subject_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    authority_reference: str = Field(min_length=5)
    expires_at: AwareDatetime


def plan(c, pid, lock=False):
    result = one(
        c,
        "SELECT * FROM anvil.harbor_agent_plans WHERE id=%s" + (" FOR UPDATE" if lock else ""),
        (pid,),
    )
    if not result:
        raise HTTPException(404, "Agent plan not found in this project")
    return result


def admin_count(c, record, purpose, subject, policy):
    return one(
        c,
        """SELECT count(DISTINCT a.approver_id) n FROM anvil.provider_approvals a
        JOIN anvil.users u ON u.id=a.approver_id JOIN anvil.memberships m ON m.user_id=u.id AND m.project_id=a.project_id
        WHERE a.connection_id=%s AND a.purpose=%s AND a.subject_hash=%s AND a.authority_reference=%s
        AND a.cap_micro_usd=%s AND a.expires_at>now() AND u.active AND NOT u.is_synthetic AND m.active AND m.role='admin'""",
        (record["connection_id"], purpose, subject, policy.reference, policy.total_cap_micro_usd),
    )["n"]


def readiness(c, record):
    if record["config"].get("workspace_execution_group"):
        from anvil.workspace_execution import plan_readiness

        return plan_readiness(c, record)
    connection = one(c, "SELECT * FROM anvil.connections WHERE id=%s", (record["connection_id"],))
    package = one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (record["package_id"],))
    missing = []
    if connection and connection["config"].get("workspace_profile_version"):
        missing.append("workspace_profile_dispatch_binding_not_qualified")
    policy = authority()
    if not harbor_live_enabled():
        missing.append("live_dispatch_disabled_in_runtime")
    if (
        not policy
        or str(policy.project_id) != str(record["project_id"])
        or policy.model != record["config"]["model"]
    ):
        missing.append("exact_user_provider_model_budget_and_current_pricing_authority")
        policy = None
    elif record["config"].get("authority_sha256") != digest(policy.model_dump(mode="json")):
        missing.append("recreate_plan_to_bind_exact_current_authority_and_pricing")
    if record["config"].get("adapter_sha256") != code_digest():
        missing.append("adapter_changed_rebuild_and_review_plan")
    if (
        not connection
        or connection["provider_key"] != "openai"
        or connection["model_id"] != record["config"]["model"]
        or connection["destination"] != providers.PROVIDERS["openai"][2]
        or connection["status"] == "revoked"
    ):
        missing.append("reviewed_exact_openai_connection")
    elif policy and (
        connection["config_hash"] != record["config"]["connection_hash"]
        or connection["config"].get("pricing_revision") != policy.pricing_revision
        or not connection["config"].get("processing_terms_reviewed")
    ):
        missing.append("connection_binding_or_processing_terms_or_pricing")
    present, error = providers.secret_presence("openai")
    if not present:
        missing.append(error or "provider_secret_missing")
    reviews = c.execute(
        "SELECT * FROM anvil.harbor_agent_reviews r WHERE plan_id=%s AND subject_hash=%s AND expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.harbor_agent_review_revocations v WHERE v.review_id=r.id) AND EXISTS(SELECT 1 FROM anvil.project_assignments a WHERE a.user_id=r.approved_by AND a.capability='rights_reviewer' AND a.active) AND EXISTS(SELECT 1 FROM anvil.artifacts a WHERE a.id=r.rights_evidence_id AND a.scan_status='clean')",
        (record["id"], record["subject_hash"]),
    ).fetchall()
    owners = domain.product_owners(c, record["project_id"])
    if not any(str(r["approved_by"]) in owners for r in reviews):
        missing.append("product_owner_exact_run_and_external_processing_rights_review")
    if record["state"] == "launched":
        window = one(
            c, "SELECT * FROM anvil.evaluation_spend_windows WHERE id=%s", (record["window_id"],)
        )
        if (
            not window
            or window["status"] != "active"
            or window["end_at"] <= datetime.now(timezone.utc)
            or window["reserved_micro_usd"] < record["config"]["max_total_micro_usd"]
        ):
            missing.append("reserved_spend_window_inactive_or_insufficient")
    if policy:
        for purpose, subject in (
            ("activation", record["config"]["connection_hash"]),
            ("paid_scope", record["subject_hash"]),
        ):
            if admin_count(c, record, purpose, subject, policy) < 2:
                missing.append("two_real_distinct_admin_" + purpose + "_approvals")
        required = call_bound(policy) * record["config"]["max_calls"]
        if (
            record["config"]["max_total_micro_usd"] < required
            or record["config"]["max_total_micro_usd"] > policy.total_cap_micro_usd
        ):
            missing.append("run_ceiling_below_conservative_bound_or_above_authority")
    else:
        required = None
        missing.extend(
            [
                "two_real_distinct_admin_activation_approvals",
                "two_real_distinct_admin_paid_scope_approvals",
            ]
        )
    if not package or not one(
        c, "SELECT 1 FROM anvil.harbor_approvals WHERE package_id=%s", (record["package_id"],)
    ):
        missing.append("exact_package_software_check_approval")
    return {
        "ready": not missing,
        "missing_gates": missing,
        "subject_hash": record["subject_hash"],
        "config": record["config"],
        "required_conservative_run_micro_usd": required,
        "provider_secret_present": present,
        "authority_reference": policy.reference if policy else None,
        "mechanism": "one server-mediated OpenAI JSON response per stage; full run ceiling reserved before launch; no retries; no provider credentials in Harbor",
    }


def actor_prompt(admission, stage_index, previous):
    if (
        type(stage_index) is not int
        or not 0 <= stage_index < len(admission["stages"])
        or len(previous) != stage_index
    ):
        raise RuntimeError("unsupported_stage")
    state = dict(admission["initial_state"])
    for i, output in enumerate(previous):
        stage = admission["stages"][i]
        grading = stage["grading"]
        if not grading or any(
            not matches(Binding.model_validate(r["binding"]), output)
            for r in [
                *grading["criteria"],
                *[r for r in grading["constraints"] if r["hard_failure"]],
            ]
        ):
            raise RuntimeError("previous_stage_did_not_pass")
        state.update({u["key"]: output[u["from_field"]] for u in stage["state_updates"]})
        state["completed_stage"] = stage["id"]
    body = dict(admission["stages"][stage_index]["actor"])
    if admission["source_schema_version"] == "praxis.anvil.task.v2":
        body["state"] = state
    prompt = (
        "Return one JSON object for output.json. Do not include Markdown or execute code.\n"
        + encoded(body).decode()
    )
    if len(prompt.encode()) > MAX_PROMPT_BYTES:
        raise RuntimeError("actor_prompt_limit")
    return prompt


def execute_provider(model, prompt, transport=None):
    """Only the trusted mediator calls this, after durable intent and reservation commit."""
    import httpx
    from openai import OpenAI

    if transport is not None and not isinstance(transport, httpx.MockTransport):
        raise ValueError("Only an explicit network-free mock transport may override HTTP")
    if not isinstance(prompt, str) or len(prompt.encode()) > MAX_PROMPT_BYTES:
        raise ValueError("Actor prompt exceeds admitted bound")

    name = providers.PROVIDERS["openai"][1]
    present, error = providers.secret_presence("openai")
    if not present:
        raise RuntimeError(error or "provider_secret_missing")
    key = os.environ.get(name)
    if not key:
        key = (ROOT / os.environ[name + "_FILE"]).read_text().strip()
    try:
        with httpx.Client(
            timeout=90, follow_redirects=False, trust_env=False, transport=transport
        ) as http:
            sdk = OpenAI(
                api_key=key,
                base_url=providers.PROVIDERS["openai"][2],
                http_client=http,
                max_retries=0,
            )
            response = sdk.responses.create(
                model=model,
                input=[{"role": "user", "content": prompt}],
                max_output_tokens=MAX_OUTPUT_TOKENS,
                store=False,
                service_tier="default",
                text={"format": {"type": "json_object"}},
            )
            return providers.normalized("openai", response.model_dump(mode="json", warnings=False))
    except Exception:
        return providers.Result("execution_unknown", error_code="provider_dispatch_uncertain")


def decision(project, user, plan_id, stage_index, transport=execute_provider):
    with transaction(project, user) as c:
        workspace = plan(c, plan_id)["config"].get("workspace_execution_group")
    if workspace:
        from anvil.workspace_execution import decision as workspace_decision

        return workspace_decision(project, user, plan_id, stage_index)
    if type(stage_index) is not int or stage_index < 0:
        raise RuntimeError("unsupported_stage")
    with transaction(project, user) as c:
        project_fence(c, project)
        record = plan(c, plan_id, True)
        check = one(c, "SELECT * FROM anvil.harbor_checks WHERE id=%s", (record["check_id"],))
        ready = readiness(c, record)
        if (
            not ready["ready"]
            or not check
            or check["cancel_requested"]
            or check["state"] != "running"
            or stage_index >= record["config"]["max_calls"]
        ):
            raise RuntimeError("live_authority_or_stage_blocked")
        package = one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (record["package_id"],))
        archive = artifacts.read(c, package["package_artifact_id"])
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            admitted = z.read("anvil-agent/admission.json")
        if (
            hashlib.sha256(admitted).hexdigest()
            != package["manifest"]["files"]["anvil-agent/admission.json"]
        ):
            raise RuntimeError("admission_integrity_mismatch")
        admission = json_value(admitted)
        old = c.execute(
            "SELECT * FROM anvil.harbor_agent_calls WHERE plan_id=%s ORDER BY stage_index",
            (plan_id,),
        ).fetchall()
        current = next((r for r in old if r["stage_index"] == stage_index), None)
        if current:
            if current["status"] == "completed":
                return current["output_json"]["text"]
            raise RuntimeError("dispatch_outcome_unknown_no_retry")
        if len(old) != stage_index or any(r["status"] != "completed" for r in old):
            raise RuntimeError("stage_sequence_mismatch")
        previous = [json_value(r["output_json"]["text"]) for r in old]
        if any(not isinstance(output, dict) for output in previous):
            raise RuntimeError("previous_stage_did_not_pass")
        prompt = actor_prompt(admission, stage_index, previous)
        policy = authority()
        bound = call_bound(policy)
        if (
            sum(r["reserved_micro_usd"] for r in old) + bound
            > record["config"]["max_total_micro_usd"]
        ):
            raise RuntimeError("spend_ceiling")
        cid = uid()
        c.execute(
            "INSERT INTO anvil.harbor_agent_calls(id,project_id,plan_id,stage_index,request_sha256,reserved_micro_usd,status) VALUES(%s,%s,%s,%s,%s,%s,'dispatching')",
            (
                cid,
                project,
                plan_id,
                stage_index,
                hashlib.sha256(prompt.encode()).hexdigest(),
                bound,
            ),
        )
        audit(
            c,
            project,
            user,
            "harbor.agent_dispatch_intent",
            cid,
            {"bound_micro_usd": bound, "stage_index": stage_index},
        )
    # No database transaction or locks span network dispatch. Intent is durable beforehand.
    try:
        result = transport(record["config"]["model"], prompt)
    except Exception:
        result = providers.Result("execution_unknown", error_code="provider_dispatch_uncertain")
    try:
        output = result.text or ""
        if (
            result.status not in ("completed", "refused", "truncated")
            or len(output.encode()) > 65536
        ):
            raise ValueError()
        usage = result.usage or {}
        input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
        if (
            type(input_tokens) is not int
            or type(output_tokens) is not int
            or min(input_tokens, output_tokens) < 0
        ):
            raise ValueError()
        actual = (
            input_tokens * policy.input_micro_usd_per_million_tokens
            + output_tokens * policy.output_micro_usd_per_million_tokens
            + 999999
        ) // 1000000
        if actual > bound or result.model_returned != record["config"]["model"]:
            raise ValueError()
    except (ValueError, TypeError, RecursionError):
        with transaction(project, worker=True) as c:
            project_fence(c, project)
            c.execute(
                "UPDATE anvil.harbor_agent_calls SET status='execution_unknown',finished_at=now() WHERE id=%s",
                (cid,),
            )
            audit(c, project, user, "harbor.agent_dispatch_unknown", cid)
        raise RuntimeError("provider_output_or_usage_unknown_no_retry") from None
    with transaction(project, worker=True) as c:
        project_fence(c, project)
        c.execute(
            "UPDATE anvil.harbor_agent_calls SET status='completed',output_json=%s,usage=%s,request_id=%s,actual_micro_usd=%s,finished_at=now() WHERE id=%s",
            (
                Jsonb({"text": output}),
                Jsonb(
                    {
                        **result.usage,
                        "normalized_status": result.status,
                        "finish_reason": result.finish_reason,
                    }
                ),
                result.request_id,
                actual,
                cid,
            ),
        )
        audit(c, project, user, "harbor.agent_output_captured", cid, {"actual_micro_usd": actual})
    return output


class UnixHTTPServer(ThreadingMixIn, HTTPServer):
    address_family = socket.AF_UNIX
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass


class Gateway:
    def __init__(self, project, user, plan_id):
        self.folder = tempfile.TemporaryDirectory(prefix="anvil-gw-")
        self.path = str(Path(self.folder.name) / "gateway.sock")
        self.token = secrets.token_urlsafe(32)
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                try:
                    if self.path != "/decision" or not hmac.compare_digest(
                        self.headers.get("Authorization", ""), "Bearer " + gateway.token
                    ):
                        raise ValueError()
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 256:
                        raise ValueError()
                    body = json_value(self.rfile.read(size))
                    if set(body) != {"stage_index"}:
                        raise ValueError()
                    output = decision(project, user, plan_id, body["stage_index"])
                    data = encoded({"output": output})
                    self.send_response(200)
                except Exception:
                    data = b'{"error":"agent_gateway_blocked_or_unknown_no_retry"}'
                    self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = UnixHTTPServer(self.path, Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.folder.cleanup()


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}")

    @router.get("/harbor-agent-connections")
    def connections(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "product-owner")
            return wrap(
                c.execute(
                    "SELECT id,provider_key,model_id,config_hash FROM anvil.connections WHERE provider_key='openai' AND status<>'revoked' AND NOT(config ? 'workspace_profile_version') ORDER BY created_at DESC LIMIT 100"
                ).fetchall(),
                request,
            )

    @router.post("/harbor-packages/{package_id}/agent-plans")
    def create(project: UUID, package_id: UUID, body: Plan, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "product-owner")

            def act():
                package = one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (package_id,))
                connection = one(
                    c, "SELECT * FROM anvil.connections WHERE id=%s", (body.connection_id,)
                )
                if not package or not connection:
                    raise HTTPException(
                        404, "Package or provider connection not found in this project"
                    )
                if "anvil-agent/admission.json" not in package["manifest"]["files"]:
                    raise HTTPException(
                        409,
                        "Rebuild this source with the current agent-admission compiler before planning an agent run",
                    )
                if connection["provider_key"] != "openai" or connection["model_id"] != body.model:
                    raise HTTPException(
                        422, "Select the exact model on a project OpenAI connection"
                    )
                if connection["config"].get("workspace_profile_version"):
                    raise HTTPException(
                        409,
                        "Workspace model profiles await qualified credential/dispatch binding; the legacy global key is never substituted",
                    )
                policy = authority()
                config = body.model_dump(mode="json") | {
                    "connection_hash": connection["config_hash"],
                    "package_sha256": package["package_sha256"],
                    "max_calls": len(package["manifest"]["stage_order"]),
                    "max_output_tokens": MAX_OUTPUT_TOKENS,
                    "max_prompt_bytes": MAX_PROMPT_BYTES,
                    "adapter_version": AGENT,
                    "adapter_sha256": code_digest(),
                    "authority_sha256": digest(policy.model_dump(mode="json")) if policy else None,
                }
                pid = uid()
                subject = digest({"plan_id": pid, "created_by": str(user), "config": config})
                c.execute(
                    "INSERT INTO anvil.harbor_agent_plans(id,project_id,package_id,connection_id,created_by,config,subject_hash) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (pid, project, package_id, body.connection_id, user, Jsonb(config), subject),
                )
                audit(c, project, user, "harbor.agent_plan_created", pid, {"subject_hash": subject})
                return {"id": pid, **readiness(c, plan(c, pid))}

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.get("/harbor-agent-plans/{pid}")
    def inspect(project: UUID, pid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "product-owner")
            record = plan(c, pid)
            calls = c.execute(
                "SELECT stage_index,status,reserved_micro_usd,actual_micro_usd,usage,request_id FROM anvil.harbor_agent_calls WHERE plan_id=%s ORDER BY stage_index",
                (pid,),
            ).fetchall()
            return wrap(
                {
                    "id": pid,
                    "state": record["state"],
                    "check_id": record["check_id"],
                    "calls": calls,
                    **readiness(c, record),
                },
                request,
            )

    @router.post("/harbor-agent-plans/{pid}/revoke-review")
    def revoke_review(project: UUID, pid: UUID, body: dict, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "product-owner")

            def act():
                record = plan(c, pid)
                if record["config"].get("workspace_execution_group"):
                    raise HTTPException(409, "Use the execution-group review controls")
                rationale = body.get("rationale")
                if (
                    set(body) != {"rationale"}
                    or not isinstance(rationale, str)
                    or not 10 <= len(rationale) <= 2000
                ):
                    raise HTTPException(
                        422, "Provide a review-revocation rationale (10–2000 characters)"
                    )
                for review in c.execute(
                    "SELECT id FROM anvil.harbor_agent_reviews WHERE plan_id=%s", (pid,)
                ).fetchall():
                    c.execute(
                        "INSERT INTO anvil.harbor_agent_review_revocations(id,project_id,review_id,revoked_by,rationale) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(review_id) DO NOTHING",
                        (uid(), project, review["id"], user, rationale),
                    )
                audit(c, project, user, "harbor.agent_rights_review_revoked", pid)
                return readiness(c, record)

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/harbor-agent-plans/{pid}/review")
    def review(project: UUID, pid: UUID, body: POReview, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "product-owner")

            def act():
                record = plan(c, pid, True)
                if record["config"].get("workspace_execution_group"):
                    raise HTTPException(409, "Use the execution-group review controls")
                if body.subject_hash != record["subject_hash"]:
                    raise HTTPException(409, "Review must bind exact plan")
                if one(
                    c,
                    "SELECT 1 FROM anvil.harbor_agent_reviews WHERE plan_id=%s AND approved_by=%s",
                    (pid, user),
                ):
                    raise HTTPException(
                        409,
                        "This Product Owner already reviewed the plan. Create a new plan to renew or replace an immutable review.",
                    )
                self_approved = str(record["created_by"]) == str(user)
                if self_approved and len(domain.product_owners(c, project)) != 1:
                    raise HTTPException(409, "Another Product Owner must review your plan")
                if body.expires_at <= datetime.now(timezone.utc):
                    raise HTTPException(422, "Rights review expiry must be in the future")
                if not one(
                    c,
                    "SELECT 1 FROM anvil.project_assignments WHERE user_id=%s AND capability='rights_reviewer' AND active",
                    (user,),
                ):
                    raise HTTPException(
                        403, "An assigned Product Owner rights reviewer is required"
                    )
                artifacts.read(c, body.rights_evidence_id)
                if one(c, "SELECT is_synthetic FROM anvil.users WHERE id=%s", (user,))[
                    "is_synthetic"
                ]:
                    raise HTTPException(403, "A real Product Owner must review paid-run rights")
                c.execute(
                    "INSERT INTO anvil.harbor_agent_reviews(id,project_id,plan_id,approved_by,subject_hash,rationale,rights_evidence_id,self_approved,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(plan_id,approved_by) DO NOTHING",
                    (
                        uid(),
                        project,
                        pid,
                        user,
                        body.subject_hash,
                        body.rationale,
                        body.rights_evidence_id,
                        self_approved,
                        body.expires_at,
                    ),
                )
                audit(
                    c,
                    project,
                    user,
                    "harbor.agent_rights_and_run_approved",
                    pid,
                    {"self_approved": self_approved, "subject_hash": body.subject_hash},
                )
                return readiness(c, record)

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/harbor-agent-plans/{pid}/admin-approvals")
    def admin_review(project: UUID, pid: UUID, body: AdminReview, request: Request):
        identity = auth.identity(request)
        if (datetime.now(timezone.utc) - identity["issued_at"]).total_seconds() > 600:
            raise HTTPException(403, "Reauthentication required")
        with context(request, project) as (c, user, roles):
            from anvil.marketing_authority import real_admin

            real_admin(c, project, user)

            def act():
                record = plan(c, pid)
                if record["config"].get("workspace_execution_group"):
                    raise HTTPException(409, "Use the execution-group Admin controls")
                policy = authority()
                expected = (
                    record["config"]["connection_hash"]
                    if body.purpose == "activation"
                    else record["subject_hash"]
                )
                if (
                    not policy
                    or str(policy.project_id) != str(project)
                    or body.authority_reference != policy.reference
                    or body.subject_hash != expected
                    or not datetime.now(timezone.utc)
                    < body.expires_at
                    <= min(policy.expires_at, policy.pricing_expires_at)
                ):
                    raise HTTPException(
                        409, "Exact current user authority, scope hash and expiry required"
                    )
                c.execute(
                    "INSERT INTO anvil.provider_approvals(id,project_id,connection_id,approver_id,purpose,subject_hash,cap_micro_usd,authority_reference,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(connection_id,purpose,subject_hash,approver_id) DO NOTHING",
                    (
                        uid(),
                        project,
                        record["connection_id"],
                        user,
                        body.purpose,
                        body.subject_hash,
                        policy.total_cap_micro_usd,
                        policy.reference,
                        body.expires_at,
                    ),
                )
                audit(c, project, user, "harbor.agent_admin_" + body.purpose, pid)
                return readiness(c, record)

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/harbor-agent-plans/{pid}/launch")
    def launch(project: UUID, pid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "product-owner")

            def act():
                record = plan(c, pid, True)
                if record["config"].get("workspace_execution_group"):
                    raise HTTPException(
                        409, "Launch this workspace plan through its execution group"
                    )
                if record["check_id"]:
                    return {"check_id": record["check_id"]}
                ready = readiness(c, record)
                if not ready["ready"]:
                    raise HTTPException(
                        409, {"message": "Agent run blocked; no inference dispatched", **ready}
                    )
                policy = authority()
                c.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (policy.reference,)
                )
                window = one(
                    c,
                    "SELECT * FROM anvil.evaluation_spend_windows WHERE authority_reference=%s FOR UPDATE",
                    (policy.reference,),
                )
                if not window:
                    wid = uid()
                    c.execute(
                        "INSERT INTO anvil.evaluation_spend_windows(id,project_id,cap_micro_usd,end_at,status,authority_reference) VALUES(%s,%s,%s,%s,'active',%s)",
                        (
                            wid,
                            project,
                            policy.total_cap_micro_usd,
                            min(policy.expires_at, policy.pricing_expires_at),
                            policy.reference,
                        ),
                    )
                    window = one(
                        c, "SELECT * FROM anvil.evaluation_spend_windows WHERE id=%s", (wid,)
                    )
                ceiling = record["config"]["max_total_micro_usd"]
                if (
                    window["status"] != "active"
                    or window["end_at"] <= datetime.now(timezone.utc)
                    or window["cap_micro_usd"] != policy.total_cap_micro_usd
                    or window["reserved_micro_usd"] + window["settled_micro_usd"] + ceiling
                    > window["cap_micro_usd"]
                ):
                    raise HTTPException(
                        409, "Shared authorized spending ceiling exhausted or expired"
                    )
                if one(
                    c,
                    "SELECT 1 FROM anvil.harbor_checks WHERE state IN ('queued','running') LIMIT 1",
                ):
                    raise HTTPException(409, "Finish or cancel active check first")
                hid = uid()
                c.execute(
                    "UPDATE anvil.evaluation_spend_windows SET reserved_micro_usd=reserved_micro_usd+%s WHERE id=%s",
                    (ceiling, window["id"]),
                )
                c.execute(
                    "INSERT INTO anvil.harbor_checks(id,project_id,package_id,created_by,candidate,agent_plan_id) VALUES(%s,%s,%s,%s,'agent',%s)",
                    (hid, project, record["package_id"], user, pid),
                )
                c.execute(
                    "UPDATE anvil.harbor_agent_plans SET state='launched',check_id=%s,window_id=%s WHERE id=%s",
                    (hid, window["id"], pid),
                )
                c.execute(
                    "INSERT INTO anvil.jobs(id,project_id,kind,target_id,operation_key) VALUES(%s,%s,'harbor_check',%s,%s)",
                    (uid(), project, hid, "harbor-agent:" + str(pid)),
                )
                audit(
                    c,
                    project,
                    user,
                    "harbor.agent_run_reserved",
                    hid,
                    {"ceiling_micro_usd": ceiling, "authority_reference": policy.reference},
                )
                return {"check_id": hid, "reserved_micro_usd": ceiling}

            return wrap(idempotent(c, project, user, request, {}, act), request)

    return router
