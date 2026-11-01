"""Exact preparation-to-Harbor execution groups over the existing queue and spend ledger."""

import hashlib
import io
import stat
import zipfile
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import AwareDatetime, Field

from anvil import artifacts, auth, domain, providers, workspace_credentials
from anvil import harbor_agents as ha
from anvil.config import ROOT, harbor_live_enabled, private_file_owner
from anvil.db import Jsonb, audit, digest, one, project_fence, transaction, uid
from anvil.schemas import Strict
from anvil.task_parser import json_value
from anvil.workspace_preparation import PLAN_ROLES, model_snapshot
from anvil.workspace_preparation import readiness as planning_readiness


class Authority(Strict):
    reference: str = Field(pattern=r"^harbor:[A-Za-z0-9_.-]{5,100}$")
    project_id: UUID
    group_subject_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    total_cap_micro_usd: int = Field(gt=0, le=1000000000, strict=True)
    expires_at: AwareDatetime


class Create(Strict):
    preparation_id: UUID


class GroupReview(ha.POReview):
    pass


class Evidence(Strict):
    reference: str = Field(min_length=5, max_length=500, pattern=r".*\S.*")
    description: str = Field(min_length=10, max_length=2000)


class Revocation(Strict):
    rationale: str = Field(min_length=10, max_length=2000)


def authority():
    path = ROOT / ".local/workspace-authority.json"
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
        return value if value.expires_at > datetime.now(timezone.utc) else None
    except (ValueError, OSError):
        return None


def group(c, identifier, lock=False):
    row = one(
        c,
        "SELECT * FROM anvil.workspace_execution_groups WHERE id=%s"
        + (" FOR UPDATE" if lock else ""),
        (identifier,),
    )
    if not row:
        raise HTTPException(404, "Execution group not found in this project")
    return row


def children(c, gid):
    return c.execute(
        """SELECT p.*,m.ordinal,m.check_id child_check_id FROM anvil.workspace_execution_models m
        JOIN anvil.harbor_agent_plans p ON p.id=m.plan_id AND p.project_id=m.project_id
        WHERE m.group_id=%s ORDER BY m.ordinal""",
        (gid,),
    ).fetchall()


def required_cost(config):
    price = config.get("pricing")
    if not price:
        return None
    return (
        max(
            1,
            (
                (32768 + 1024) * price["input_micro_usd_per_million_tokens"]
                + config["max_output_tokens"] * price["output_micro_usd_per_million_tokens"]
                + 999999
            )
            // 1000000,
        )
        * config["max_calls"]
    )


def billed_usage(provider, usage):
    if provider == "gemini":
        inputs = usage.get("prompt_token_count")
        outputs = usage.get("candidates_token_count")
        thoughts = usage.get("thoughts_token_count")
        thoughts = 0 if thoughts is None else thoughts
        if any(type(value) is not int or value < 0 for value in (inputs, outputs, thoughts)):
            raise ValueError("missing_or_invalid_usage")
        outputs += thoughts
        if usage.get("total_token_count") != inputs + outputs:
            raise ValueError("unsupported_usage_components")
    else:
        inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
        if provider == "anthropic" and any(
            usage.get(key) for key in ("cache_creation_input_tokens", "cache_read_input_tokens")
        ):
            raise ValueError("unadmitted_cache_pricing")
    if any(type(value) is not int or value < 0 for value in (inputs, outputs)):
        raise ValueError("missing_or_invalid_usage")
    return inputs, outputs


_UNSET = object()


def readiness(c, row, policy=_UNSET):
    snapshot = row["snapshot"]
    prep = snapshot["preparation"]
    base = planning_readiness(c, prep)
    obsolete = {
        "execution_group_required",
        "workspace_dispatch_not_qualified",
        "reviewed_pricing_admission_not_bound",
        "exact_user_authority_not_bound",
        "processing_rights_not_bound",
        "required_run_decisions_not_bound",
        "shared_spending_admission_not_implemented",
    }
    missing = [reason for reason in base["missing"] if reason not in obsolete]
    if not harbor_live_enabled():
        missing.append("live_dispatch_disabled_in_runtime")
    if snapshot["adapter_sha256"] != ha.code_digest():
        missing.append("adapter_changed_create_new_execution_group")
    try:
        auth.require(auth.project_roles(c, row["project_id"], row["created_by"]), *PLAN_ROLES)
    except HTTPException:
        missing.append("initiator_access_revoked")
    if policy is _UNSET:
        policy = authority()
    if (
        not policy
        or str(policy.project_id) != str(row["project_id"])
        or policy.group_subject_hash != row["subject_hash"]
    ):
        missing.append("exact_group_user_authority_required")
        policy = None
    plans = children(c, row["id"])
    required = []
    states = []
    owners = domain.product_owners(c, row["project_id"])
    package = one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (prep["package"]["id"],))
    approved = one(
        c, "SELECT * FROM anvil.harbor_approvals WHERE package_id=%s", (prep["package"]["id"],)
    )
    if (
        not package
        or package["package_sha256"] != prep["package"]["package_sha256"]
        or not approved
        or str(approved["approved_by"]) not in owners
    ):
        missing.append("exact_package_software_check_approval")
    for child, state in zip(plans, base["models"], strict=True):
        config = child["config"]
        issues = [r for r in state["missing"] if r != "provider_task_adapter_not_qualified"]
        binding = config["workspace_model"]
        if binding["provider"] not in ("openai", "anthropic", "gemini"):
            issues.append("provider_task_adapter_not_supported")
        current = one(
            c, "SELECT config FROM anvil.connections WHERE id=%s", (child["connection_id"],)
        )
        if not current or current["config"].get("workspace_pricing") != config["pricing"]:
            issues.append("frozen_pricing_binding_changed")
        if not current or not (current["config"].get("workspace_terms") or {}).get("reference"):
            issues.append("processing_terms_reference_required")
        cost = required_cost(config)
        if cost is None:
            issues.append("reviewed_pricing_required")
        else:
            required.append(cost)
        review = one(
            c,
            """SELECT 1 FROM anvil.harbor_agent_reviews r
            JOIN anvil.users u ON u.id=r.approved_by
            WHERE r.plan_id=%s AND r.subject_hash=%s AND r.expires_at>now()
            AND u.active AND NOT u.is_synthetic
            AND NOT EXISTS(SELECT 1 FROM anvil.harbor_agent_review_revocations v WHERE v.review_id=r.id)
            AND EXISTS(SELECT 1 FROM anvil.memberships m WHERE m.user_id=r.approved_by AND m.project_id=r.project_id AND m.role='product-owner' AND m.active)
            AND EXISTS(SELECT 1 FROM anvil.project_assignments a WHERE a.user_id=r.approved_by AND a.project_id=r.project_id AND a.capability='rights_reviewer' AND a.active)
            AND EXISTS(SELECT 1 FROM anvil.artifacts a WHERE a.id=r.rights_evidence_id AND a.project_id=r.project_id AND a.scan_status='clean')""",
            (child["id"], child["subject_hash"]),
        )
        if not review:
            issues.append("real_product_owner_rights_and_run_review")
        for purpose, subject in [
            ("activation", config["connection_hash"]),
            ("paid_scope", child["subject_hash"]),
        ]:
            if not policy or ha.admin_count(c, child, purpose, subject, policy) < 2:
                issues.append("two_real_distinct_admin_" + purpose + "_approvals")
        states.append(
            {
                "plan_id": str(child["id"]),
                "model_profile_id": str(child["connection_id"]),
                "model": binding["model_id"],
                "provider": binding["provider"],
                "missing": issues,
                "required_micro_usd": cost,
            }
        )
    cost = sum(required) if len(required) == len(plans) else None
    cap = prep["aggregate_cap_micro_usd"]
    if (
        cost is not None
        and cap is not None
        and (cap < cost or policy and cap > policy.total_cap_micro_usd)
    ):
        missing.append("group_cap_below_conservative_cost_or_above_authority")
    if row["state"] == "launched":
        window = one(
            c, "SELECT * FROM anvil.evaluation_spend_windows WHERE id=%s", (row["window_id"],)
        )
        if (
            not window
            or window["status"] != "active"
            or window["end_at"] <= datetime.now(timezone.utc)
            or window["reserved_micro_usd"] < (cap or 0)
        ):
            missing.append("reserved_spend_window_inactive_or_insufficient")
    return {
        "ready": not missing and all(not s["missing"] for s in states),
        "missing": missing,
        "models": states,
        "conservative_cost_micro_usd": cost,
        "aggregate_cap_micro_usd": cap,
        "authority_reference": policy.reference if policy else None,
        "live_model_verified": False,
    }


def plan_readiness(c, record):
    row = group(c, record["config"]["workspace_execution_group"])
    ready = readiness(c, row)
    missing = ready["missing"] + [reason for m in ready["models"] for reason in m["missing"]]
    if record["state"] == "launched" and row["state"] != "launched":
        missing.append("execution_group_not_launched")
    return {
        "ready": not missing,
        "missing_gates": sorted(set(missing)),
        "subject_hash": record["subject_hash"],
        "config": record["config"],
        "required_conservative_run_micro_usd": required_cost(record["config"]),
    }


def public(c, row):
    members = []
    for child in children(c, row["id"]):
        check = (
            one(
                c,
                "SELECT id,state,error_code,cancel_requested FROM anvil.harbor_checks WHERE id=%s",
                (child["child_check_id"],),
            )
            if child["child_check_id"]
            else None
        )
        members.append(
            {
                "plan_id": str(child["id"]),
                "subject_hash": child["subject_hash"],
                "ordinal": child["ordinal"],
                "model": child["config"]["workspace_model"],
                "check": check,
            }
        )
    checks = [m["check"] for m in members if m["check"]]
    status = "draft"
    if row["state"] == "launched":
        states = {h["state"] for h in checks}
        status = (
            "execution_unknown"
            if "execution_unknown" in states
            else "running"
            if "running" in states
            else "blocked"
            if states.intersection({"failed", "cancelled"}) and "queued" in states
            else "queued"
            if "queued" in states
            else "cancelled"
            if "cancelled" in states
            else "failed"
            if "failed" in states
            else "succeeded"
        )
    return {
        **{k: row[k] for k in ("id", "preparation_id", "subject_hash", "state", "created_at")},
        "status": status,
        "models": members,
        "readiness": readiness(c, row),
        "snapshot": row["snapshot"],
        "reservation_retained": row["state"] == "launched",
    }


def decision(project, user, plan_id, stage_index, *, transport=None):
    from anvil import workspace_dispatch

    if type(stage_index) is not int or stage_index < 0:
        raise RuntimeError("unsupported_stage")
    if transport is not None and type(transport) is not httpx.MockTransport:
        raise ValueError("Only an explicit MockTransport test override is supported")
    dispatch_origin = "sdk_mock" if transport is not None else "provider"
    with transaction(project, user) as c:
        project_fence(c, project)
        initial = ha.plan(c, plan_id)
        group(c, initial["config"]["workspace_execution_group"], True)
        record = ha.plan(c, plan_id, True)
        check = one(
            c, "SELECT * FROM anvil.harbor_checks WHERE id=%s FOR UPDATE", (record["check_id"],)
        )
        if (
            not plan_readiness(c, record)["ready"]
            or not check
            or check["state"] != "running"
            or check["cancel_requested"]
            or stage_index >= record["config"]["max_calls"]
        ):
            raise RuntimeError("workspace_admission_revoked")
        if (
            record["state"] != "launched"
            or group(c, record["config"]["workspace_execution_group"])["state"] != "launched"
        ):
            raise RuntimeError("execution_group_not_launched")
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
        package = one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (record["package_id"],))
        with zipfile.ZipFile(
            io.BytesIO(artifacts.read(c, package["package_artifact_id"]))
        ) as archive:
            raw = archive.read("anvil-agent/admission.json")
        if (
            hashlib.sha256(raw).hexdigest()
            != package["manifest"]["files"]["anvil-agent/admission.json"]
        ):
            raise RuntimeError("admission_integrity_mismatch")
        prompt = ha.actor_prompt(
            json_value(raw), stage_index, [json_value(r["output_json"]["text"]) for r in old]
        )
        binding = record["config"]["workspace_model"]
        # Serialize current/disable/rotation changes through the durable dispatch-intent boundary.
        locked = one(
            c,
            """SELECT d.* FROM anvil.connections d JOIN anvil.workspace_model_profiles p ON p.current_connection_id=d.id
            WHERE d.id=%s AND p.disabled_at IS NULL FOR SHARE OF d,p""",
            (record["connection_id"],),
        )
        if not locked or locked["status"] == "revoked" or model_snapshot(locked) != binding:
            raise RuntimeError("model_binding_changed")
        cred = binding["credential"]
        one(c, "SELECT id FROM anvil.workspace_credentials WHERE id=%s FOR SHARE", (cred["id"],))
        secret = workspace_credentials.resolve(c, cred["id"], cred["version_id"])
        bound = required_cost(record["config"]) // record["config"]["max_calls"]
        if (
            sum(r["reserved_micro_usd"] for r in old) + bound
            > record["config"]["max_total_micro_usd"]
        ):
            raise RuntimeError("spend_ceiling")
        cid = uid()
        c.execute(
            "INSERT INTO anvil.harbor_agent_calls(id,project_id,plan_id,stage_index,request_sha256,reserved_micro_usd,status,usage) VALUES(%s,%s,%s,%s,%s,%s,'dispatching',%s)",
            (
                cid,
                project,
                plan_id,
                stage_index,
                hashlib.sha256(prompt.encode()).hexdigest(),
                bound,
                Jsonb({"dispatch_origin": dispatch_origin}),
            ),
        )
        audit(
            c,
            project,
            user,
            "workspace.dispatch_intent",
            cid,
            {"stage_index": stage_index, "reserved_micro_usd": bound},
        )
    request = providers.ActorRequest(
        model=binding["model_id"],
        actor_text=prompt,
        max_output_tokens=record["config"]["max_output_tokens"],
        timeout_seconds=record["config"]["request_timeout_seconds"],
    )
    result = None
    try:
        result = workspace_dispatch.execute(binding, secret, request, transport=transport)
        output = result.text or ""
        usage = result.usage or {}
        inputs, outputs = billed_usage(binding["provider"], usage)
        if (
            result.status not in ("completed", "refused", "truncated")
            or len(output.encode()) > 65536
            or type(inputs) is not int
            or type(outputs) is not int
            or min(inputs, outputs) < 0
            or inputs > 32768 + 1024
            or outputs > record["config"]["max_output_tokens"]
            or result.model_returned != binding["model_id"]
        ):
            raise ValueError()
        price = record["config"]["pricing"]
        actual = (
            inputs * price["input_micro_usd_per_million_tokens"]
            + outputs * price["output_micro_usd_per_million_tokens"]
            + 999999
        ) // 1000000
        if actual > bound:
            raise ValueError()
    except Exception:
        if result and (result.usage or {}).get("dispatch_origin") == "sdk_mock":
            dispatch_origin = "sdk_mock"
        safe_errors = {
            "ambiguous_dispatch",
            "unauthorized",
            "model_unavailable",
            "rate_limited",
            "provider_error_after_dispatch",
            "unsafe_response_suppressed",
            "dispatch_not_confirmed_no_retry",
            "broker_configuration_blocked",
            "broker_request_blocked",
        }
        error_code = (
            result.error_code
            if result and result.error_code in safe_errors
            else "response_model_or_usage_not_admitted"
        )
        with transaction(project, worker=True) as c:
            project_fence(c, project)
            c.execute(
                "UPDATE anvil.harbor_agent_calls SET status='execution_unknown',usage=%s,finished_at=now() WHERE id=%s",
                (Jsonb({"dispatch_origin": dispatch_origin, "error_code": error_code}), cid),
            )
            audit(
                c,
                project,
                user,
                "workspace.dispatch_unknown",
                cid,
                {"dispatch_origin": dispatch_origin, "check_id": str(record["check_id"])},
            )
        raise RuntimeError("provider_output_or_usage_unknown_no_retry") from None
    with transaction(project, worker=True) as c:
        project_fence(c, project)
        c.execute(
            "UPDATE anvil.harbor_agent_calls SET status='completed',output_json=%s,usage=%s,request_id=%s,actual_micro_usd=%s,finished_at=now() WHERE id=%s",
            (
                Jsonb({"text": output}),
                Jsonb(
                    {
                        **usage,
                        "billed_input_tokens": inputs,
                        "billed_output_tokens": outputs,
                        "normalized_status": result.status,
                        "finish_reason": result.finish_reason,
                        "returned_model": result.model_returned,
                    }
                ),
                result.request_id,
                actual,
                cid,
            ),
        )
        audit(c, project, user, "workspace.output_captured", cid, {"actual_micro_usd": actual})
    return output


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace")

    @router.post("/execution-groups")
    def create(project: UUID, body: Create, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *PLAN_ROLES)

            def act():
                prep = one(
                    c,
                    "SELECT * FROM anvil.workspace_run_preparations WHERE id=%s",
                    (body.preparation_id,),
                )
                if not prep:
                    raise HTTPException(404, "Preparation not found in this project")
                gid = uid()
                snapshot = {
                    "preparation": prep["snapshot"],
                    "preparation_hash": prep["subject_hash"],
                    "adapter_sha256": ha.code_digest(),
                    "pricing": [],
                    "processing_terms": [],
                    "execution_order": "sequential",
                    "group_cap_is_single_reservation": True,
                }
                for bound in prep["snapshot"]["models"]:
                    row = one(c, "SELECT config FROM anvil.connections WHERE id=%s", (bound["id"],))
                    snapshot["pricing"].append(
                        row["config"].get("workspace_pricing") if row else None
                    )
                    snapshot["processing_terms"].append(
                        row["config"].get("workspace_terms") if row else None
                    )
                subject = digest({"id": gid, "created_by": str(user), "snapshot": snapshot})
                c.execute(
                    "INSERT INTO anvil.workspace_execution_groups(id,project_id,preparation_id,created_by,snapshot,subject_hash) VALUES(%s,%s,%s,%s,%s,%s)",
                    (gid, project, body.preparation_id, user, Jsonb(snapshot), subject),
                )
                for index, bound in enumerate(prep["snapshot"]["models"]):
                    pid = uid()
                    config = {
                        "workspace_execution_group": gid,
                        "workspace_model": bound,
                        "model": bound["model_id"],
                        "connection_hash": bound["config_hash"],
                        "package_sha256": prep["snapshot"]["package"]["package_sha256"],
                        "max_calls": len(prep["snapshot"]["package"]["manifest"]["stage_order"]),
                        "max_output_tokens": prep["snapshot"]["max_output_tokens"],
                        "request_timeout_seconds": min(
                            90, prep["snapshot"]["episode_timeout_seconds"]
                        ),
                        "episode_timeout_seconds": prep["snapshot"]["episode_timeout_seconds"],
                        "pricing": snapshot["pricing"][index],
                        "adapter_sha256": snapshot["adapter_sha256"],
                    }
                    config["max_total_micro_usd"] = required_cost(config)
                    child_hash = digest({"id": pid, "created_by": str(user), "config": config})
                    c.execute(
                        "INSERT INTO anvil.harbor_agent_plans(id,project_id,package_id,connection_id,created_by,config,subject_hash) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                        (
                            pid,
                            project,
                            prep["package_id"],
                            bound["id"],
                            user,
                            Jsonb(config),
                            child_hash,
                        ),
                    )
                    c.execute(
                        "INSERT INTO anvil.workspace_execution_models(project_id,group_id,ordinal,plan_id) VALUES(%s,%s,%s,%s)",
                        (project, gid, index, pid),
                    )
                audit(
                    c,
                    project,
                    user,
                    "workspace.execution_group_created",
                    gid,
                    {"subject_hash": subject},
                )
                return public(c, group(c, gid))

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.get("/execution-groups")
    def listing(
        project: UUID,
        request: Request,
        preparation_id: UUID | None = None,
        limit: int = Query(30, ge=1, le=100),
        after: UUID | None = None,
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *PLAN_ROLES)
            rows = c.execute(
                "SELECT * FROM anvil.workspace_execution_groups WHERE (%s::uuid IS NULL OR preparation_id=%s) AND (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
                (preparation_id, preparation_id, after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": [public(c, row) for row in rows[:limit]],
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                },
                request,
            )

    @router.get("/execution-groups/{gid}")
    def inspect(project: UUID, gid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *PLAN_ROLES)
            return wrap(public(c, group(c, gid)), request)

    @router.post("/execution-groups/{gid}/review")
    def review(project: UUID, gid: UUID, body: GroupReview, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "product-owner")

            def act():
                row = group(c, gid, True)
                if (
                    row["state"] != "draft"
                    or row["subject_hash"] != body.subject_hash
                    or body.expires_at <= datetime.now(timezone.utc)
                ):
                    raise HTTPException(
                        409, "Review must bind an exact draft group and future expiry"
                    )
                if one(c, "SELECT is_synthetic FROM anvil.users WHERE id=%s", (user,))[
                    "is_synthetic"
                ]:
                    raise HTTPException(
                        403, "A real Product Owner must review paid processing rights"
                    )
                if not one(
                    c,
                    "SELECT 1 FROM anvil.project_assignments WHERE user_id=%s AND capability='rights_reviewer' AND active",
                    (user,),
                ):
                    raise HTTPException(403, "Assigned rights reviewer required")
                self_approved = str(user) == str(row["created_by"])
                if self_approved and len(domain.product_owners(c, project)) != 1:
                    raise HTTPException(409, "Another Product Owner must review your group")
                artifacts.read(c, body.rights_evidence_id)
                for child in children(c, gid):
                    if one(
                        c,
                        "SELECT 1 FROM anvil.harbor_agent_reviews WHERE plan_id=%s AND approved_by=%s",
                        (child["id"], user),
                    ):
                        raise HTTPException(
                            409, "Immutable review already exists; create a new group to renew"
                        )
                    c.execute(
                        "INSERT INTO anvil.harbor_agent_reviews(id,project_id,plan_id,approved_by,subject_hash,rationale,rights_evidence_id,self_approved,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            uid(),
                            project,
                            child["id"],
                            user,
                            child["subject_hash"],
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
                    "workspace.group_rights_and_run_reviewed",
                    gid,
                    {"self_approved": self_approved},
                )
                return public(c, group(c, gid))

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/execution-groups/{gid}/admin-approvals")
    def approve(project: UUID, gid: UUID, body: ha.AdminReview, request: Request):
        from anvil.marketing_authority import real_admin

        if (datetime.now(timezone.utc) - auth.identity(request)["issued_at"]).total_seconds() > 600:
            raise HTTPException(403, "Reauthentication required")
        with context(request, project) as (c, user, roles):
            real_admin(c, project, user)

            def act():
                row = group(c, gid, True)
                policy = authority()
                if (
                    row["state"] != "draft"
                    or body.subject_hash != row["subject_hash"]
                    or not policy
                    or policy.group_subject_hash != row["subject_hash"]
                    or str(policy.project_id) != str(project)
                    or body.authority_reference != policy.reference
                    or not datetime.now(timezone.utc) < body.expires_at <= policy.expires_at
                ):
                    raise HTTPException(
                        409, "Exact current group authority/hash and bounded expiry required"
                    )
                for child in children(c, gid):
                    subject = (
                        child["config"]["connection_hash"]
                        if body.purpose == "activation"
                        else child["subject_hash"]
                    )
                    c.execute(
                        "INSERT INTO anvil.provider_approvals(id,project_id,connection_id,approver_id,purpose,subject_hash,cap_micro_usd,authority_reference,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(connection_id,purpose,subject_hash,approver_id) DO NOTHING",
                        (
                            uid(),
                            project,
                            child["connection_id"],
                            user,
                            body.purpose,
                            subject,
                            policy.total_cap_micro_usd,
                            policy.reference,
                            body.expires_at,
                        ),
                    )
                audit(c, project, user, "workspace.group_admin_" + body.purpose, gid)
                return public(c, group(c, gid))

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/execution-groups/{gid}/rights-evidence")
    def evidence(project: UUID, gid: UUID, body: Evidence, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "product-owner")

            def act():
                row = group(c, gid)
                from anvil.harbor_package import encoded

                aid = artifacts.store(
                    c,
                    project,
                    encoded(
                        {
                            "group_subject_hash": row["subject_hash"],
                            "reference": body.reference,
                            "description": body.description,
                            "recorded_by": str(user),
                            "meaning": "Evidence reference only; no rights approval granted",
                        }
                    ),
                    "internal",
                    mime="application/json",
                )
                audit(
                    c,
                    project,
                    user,
                    "workspace.rights_evidence_recorded",
                    gid,
                    {"artifact_id": aid},
                )
                return {"artifact_id": aid}

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/execution-groups/{gid}/revoke-review")
    def revoke_review(project: UUID, gid: UUID, body: Revocation, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "product-owner")

            def act():
                row = group(c, gid, True)
                for child in children(c, gid):
                    for review in c.execute(
                        "SELECT id FROM anvil.harbor_agent_reviews WHERE plan_id=%s", (child["id"],)
                    ).fetchall():
                        c.execute(
                            "INSERT INTO anvil.harbor_agent_review_revocations(id,project_id,review_id,revoked_by,rationale) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(review_id) DO NOTHING",
                            (uid(), project, review["id"], user, body.rationale),
                        )
                audit(c, project, user, "workspace.group_review_revoked", gid)
                return public(c, row)

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/execution-groups/{gid}/launch")
    def launch(project: UUID, gid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *PLAN_ROLES)

            def act():
                row = group(c, gid, True)
                if row["state"] == "launched":
                    return public(c, row)
                policy = authority()
                ready = readiness(c, row, policy=policy)
                if not ready["ready"]:
                    raise HTTPException(
                        409, {"message": "Execution blocked; no model dispatched", **ready}
                    )
                c.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (policy.reference,)
                )
                window = one(
                    c,
                    "SELECT * FROM anvil.evaluation_spend_windows WHERE authority_reference=%s FOR UPDATE",
                    (policy.reference,),
                )
                current_policy = authority()
                if (
                    not current_policy
                    or current_policy != policy
                    or policy.expires_at <= datetime.now(timezone.utc)
                    or not readiness(c, row, policy=policy)["ready"]
                ):
                    raise HTTPException(
                        409, "Authorization or admission changed while reserving; refresh readiness"
                    )
                if not window:
                    wid = uid()
                    c.execute(
                        "INSERT INTO anvil.evaluation_spend_windows(id,project_id,cap_micro_usd,end_at,status,authority_reference) VALUES(%s,%s,%s,%s,'active',%s)",
                        (
                            wid,
                            project,
                            policy.total_cap_micro_usd,
                            policy.expires_at,
                            policy.reference,
                        ),
                    )
                    window = one(
                        c, "SELECT * FROM anvil.evaluation_spend_windows WHERE id=%s", (wid,)
                    )
                cap = row["snapshot"]["preparation"]["aggregate_cap_micro_usd"]
                if (
                    window["status"] != "active"
                    or window["end_at"] <= datetime.now(timezone.utc)
                    or window["cap_micro_usd"] != policy.total_cap_micro_usd
                    or window["reserved_micro_usd"] + window["settled_micro_usd"] + cap
                    > window["cap_micro_usd"]
                ):
                    raise HTTPException(
                        409, "Shared authorized spending ceiling exhausted or expired"
                    )
                c.execute(
                    "UPDATE anvil.evaluation_spend_windows SET reserved_micro_usd=reserved_micro_usd+%s WHERE id=%s",
                    (cap, window["id"]),
                )
                for child in children(c, gid):
                    hid = uid()
                    c.execute(
                        "INSERT INTO anvil.harbor_checks(id,project_id,package_id,created_by,candidate,agent_plan_id) VALUES(%s,%s,%s,%s,'agent',%s)",
                        (hid, project, child["package_id"], row["created_by"], child["id"]),
                    )
                    c.execute(
                        "UPDATE anvil.harbor_agent_plans SET state='launched',check_id=%s,window_id=%s WHERE id=%s",
                        (hid, window["id"], child["id"]),
                    )
                    c.execute(
                        "UPDATE anvil.workspace_execution_models SET check_id=%s WHERE plan_id=%s",
                        (hid, child["id"]),
                    )
                    c.execute(
                        "INSERT INTO anvil.jobs(id,project_id,kind,target_id,operation_key) VALUES(%s,%s,'harbor_check',%s,%s)",
                        (
                            uid(),
                            project,
                            hid,
                            "workspace:" + str(gid) + ":" + str(child["ordinal"]),
                        ),
                    )
                c.execute(
                    "UPDATE anvil.workspace_execution_groups SET state='launched',window_id=%s WHERE id=%s",
                    (window["id"], gid),
                )
                audit(
                    c,
                    project,
                    user,
                    "workspace.group_budget_reserved",
                    gid,
                    {"aggregate_cap_micro_usd": cap, "authority_reference": policy.reference},
                )
                return public(c, group(c, gid))

            return wrap(idempotent(c, project, user, request, {}, act), request)

    @router.post("/execution-groups/{gid}/cancel")
    def cancel(project: UUID, gid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *PLAN_ROLES)

            def act():
                row = group(c, gid, True)
                for child in children(c, gid):
                    if child["child_check_id"]:
                        c.execute(
                            "UPDATE anvil.harbor_checks SET cancel_requested=true,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,finished_at=CASE WHEN state='queued' THEN now() ELSE finished_at END WHERE id=%s AND state IN ('queued','running')",
                            (child["child_check_id"],),
                        )
                        c.execute(
                            "UPDATE anvil.jobs SET status='cancelled' WHERE target_id=%s AND status='queued'",
                            (child["child_check_id"],),
                        )
                audit(
                    c,
                    project,
                    user,
                    "workspace.group_cancel_requested",
                    gid,
                    {"reservation_retained": True},
                )
                return public(c, row)

            return wrap(idempotent(c, project, user, request, {}, act), request)

    return router
