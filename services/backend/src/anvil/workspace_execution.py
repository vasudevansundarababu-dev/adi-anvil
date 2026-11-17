"""Exact preparation-to-Harbor execution groups over the existing queue and spend ledger."""

import hashlib
import io
import os
import zipfile
from datetime import datetime, timedelta, timezone
from time import monotonic
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import AwareDatetime, Field

from anvil import artifacts, auth, pilot_budget, providers, workspace_costs, workspace_credentials
from anvil import harbor_agents as ha
from anvil.config import harbor_live_enabled
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


class AdminRun(Strict):
    subject_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    aggregate_cap_micro_usd: int = Field(gt=0, le=1000000000, strict=True)
    rights_confirmed: bool


def authority(c, row):
    record = one(
        c,
        """SELECT a.* FROM anvil.workspace_admin_run_authorizations a
        JOIN anvil.users u ON u.id=a.admin_id AND u.active
        JOIN anvil.memberships m ON m.user_id=a.admin_id AND m.project_id=a.project_id AND m.active AND m.role='admin'
        WHERE a.group_id=%s AND a.expires_at>now()
        AND NOT EXISTS(SELECT 1 FROM anvil.workspace_admin_run_revocations r WHERE r.authorization_id=a.id)""",
        (row["id"],),
    )
    if (
        not record
        or record["subject_hash"] != row["subject_hash"]
        or record["pricing_hash"] != digest(row["snapshot"]["pricing"])
        or record["terms_hash"] != digest(row["snapshot"]["processing_terms"])
        or record["cap_micro_usd"] != row["snapshot"]["preparation"]["aggregate_cap_micro_usd"]
    ):
        return None
    return Authority(
        reference=record["authority_reference"],
        project_id=row["project_id"],
        group_subject_hash=record["subject_hash"],
        total_cap_micro_usd=record["cap_micro_usd"],
        expires_at=record["expires_at"],
    )


def authorize_admin(c, row, user, body):
    from anvil.marketing_authority import active_admin

    active_admin(c, row["project_id"], user)
    cap = row["snapshot"]["preparation"]["aggregate_cap_micro_usd"]
    if (
        body.subject_hash != row["subject_hash"]
        or body.aggregate_cap_micro_usd != cap
        or not body.rights_confirmed
    ):
        raise HTTPException(409, "Confirm the exact run, processing rights and saved budget")
    existing = one(
        c, "SELECT id FROM anvil.workspace_admin_run_authorizations WHERE group_id=%s", (row["id"],)
    )
    if existing:
        if not authority(c, row):
            raise HTTPException(
                409, "Authorization expired or revoked; create a new execution group"
            )
        return
    c.execute(
        """INSERT INTO anvil.workspace_admin_run_authorizations
        (id,project_id,group_id,admin_id,subject_hash,cap_micro_usd,rights_confirmed,pricing_hash,terms_hash,authority_reference,expires_at)
        VALUES(%s,%s,%s,%s,%s,%s,true,%s,%s,%s,%s)""",
        (
            uid(),
            row["project_id"],
            row["id"],
            user,
            row["subject_hash"],
            cap,
            digest(row["snapshot"]["pricing"]),
            digest(row["snapshot"]["processing_terms"]),
            "harbor:admin-run-" + str(row["id"]),
            datetime.now(timezone.utc) + timedelta(hours=8),
        ),
    )
    audit(
        c,
        row["project_id"],
        user,
        "workspace.admin_run_authorized",
        row["id"],
        {
            "subject_hash": row["subject_hash"],
            "aggregate_cap_micro_usd": cap,
            "rights_confirmed": True,
            "self_authorized": str(user) == str(row["created_by"]),
            "authorization_policy": "active-project-admin-v2",
            "actor_seeded_origin": one(
                c, "SELECT is_synthetic FROM anvil.users WHERE id=%s", (user,)
            )["is_synthetic"],
        },
    )


def recent_admin_signin(request):
    if (datetime.now(timezone.utc) - auth.identity(request)["issued_at"]).total_seconds() > 600:
        raise HTTPException(403, "Please sign in again to authorize this run budget")


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
                (32768 + 1024) * workspace_costs.input_bound(price)
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


def provider_evidence(result):
    """Retain reconciliation metadata, never response text, prompts or raw errors."""
    if result is None:
        return {}

    def identifier(value):
        return (
            value
            if isinstance(value, str)
            and 0 < len(value) <= 200
            and all(c.isascii() and (c.isalnum() or c in "-_.:/") for c in value)
            else None
        )

    usage = result.usage if isinstance(result.usage, dict) else {}
    counters = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_token_count",
        "candidates_token_count",
        "thoughts_token_count",
        "total_token_count",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        if type(usage.get(key)) is int and 0 <= usage[key] <= 1000000000:
            counters[key] = usage[key]
    for key, allowed in (
        ("input_tokens_details", ("cached_tokens", "cache_write_tokens")),
        ("output_tokens_details", ("reasoning_tokens",)),
    ):
        detail = usage.get(key)
        if isinstance(detail, dict):
            counters[key] = {
                k: detail[k]
                for k in allowed
                if type(detail.get(k)) is int and 0 <= detail[k] <= 1000000000
            }
            if key == "input_tokens_details" and isinstance(
                detail.get("cache_write_tokens_details"), dict
            ):
                parts = detail["cache_write_tokens_details"]
                counters[key]["cache_write_tokens_details"] = {
                    k: parts[k]
                    for k in ("ttl_30m_tokens", "ttl_12h_tokens")
                    if type(parts.get(k)) is int and 0 <= parts[k] <= 1000000000
                }
    evidence = {
        "model_returned": identifier(result.model_returned),
        "request_id": identifier(result.request_id),
        "status": identifier(result.status),
        "token_usage": counters,
    }
    http_status = usage.get("provider_http_status")
    if type(http_status) is int and 500 <= http_status <= 599:
        evidence["provider_http_status"] = http_status
    if usage.get("provider_status") in (
        "INTERNAL",
        "UNAVAILABLE",
        "DEADLINE_EXCEEDED",
        "UNKNOWN",
    ):
        evidence["provider_status"] = usage["provider_status"]
    return evidence


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
    missing.extend(pilot_budget.issues(c, row))
    workflow = prep.get("workflow")
    if workflow:
        from anvil import workflow_registry

        try:
            registered, definition = workflow_registry.current(
                c, workflow["id"], prep["package"]["id"]
            )
            if registered["subject_hash"] != workflow["subject_hash"]:
                raise ValueError("workflow_snapshot_changed")
        except ValueError:
            missing.append("workflow_definition_unavailable_or_changed")
        if os.environ.get("ANVIL_HARBOR_WORKFLOW_ENABLED") != "true":
            missing.append("native_workflow_disabled")
    if not harbor_live_enabled():
        missing.append("live_dispatch_disabled_in_runtime")
    if snapshot["adapter_sha256"] != ha.code_digest():
        missing.append("adapter_changed_create_new_execution_group")
    try:
        auth.require(auth.project_roles(c, row["project_id"], row["created_by"]), *PLAN_ROLES)
    except HTTPException:
        missing.append("initiator_access_revoked")
    if policy is _UNSET:
        policy = authority(c, row)
    if (
        not policy
        or str(policy.project_id) != str(row["project_id"])
        or policy.group_subject_hash != row["subject_hash"]
    ):
        missing.append("admin_run_authorization_required")
        policy = None
    plans = children(c, row["id"])
    required = []
    states = []
    package = one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (prep["package"]["id"],))
    if not package or package["package_sha256"] != prep["package"]["package_sha256"]:
        missing.append("exact_package_binding_changed")
    model_states = {state["model_profile_id"]: state for state in base["models"]}
    for child in plans:
        config = child["config"]
        state = model_states[config["workspace_model"]["id"]]
        issues = [r for r in state["missing"] if r != "provider_task_adapter_not_qualified"]
        if config.get("golden_kyc_paid"):
            from anvil.golden_kyc_paid_budget import issues as golden_paid_issues

            issues.extend(golden_paid_issues(c, child))
        if config.get("marketing_paid"):
            from anvil.marketing_paid_budget import issues as marketing_paid_issues

            issues.extend(marketing_paid_issues(c, child))
        binding = config["workspace_model"]
        if binding["provider"] not in ("openai", "anthropic", "gemini"):
            issues.append("provider_task_adapter_not_supported")
        current = one(c, "SELECT * FROM anvil.connections WHERE id=%s", (child["connection_id"],))
        price = workspace_costs.for_model(current)
        if not price:
            issues.append("model_cost_support_unavailable")
        elif not workspace_costs.current(price):
            issues.append("model_cost_support_expired")
        elif price != config["pricing"]:
            issues.append("execution_cost_snapshot_changed")
        cost = required_cost(config)
        if workflow and (
            cost is None
            or cost > workflow["bounds"]["cost_micro_usd"]
            or config["max_calls"] * (33792 + config["max_output_tokens"])
            > workflow["bounds"]["tokens"]
        ):
            issues.append("workflow_global_token_or_cost_bound_insufficient")
        if cost is None:
            issues.append("execution_cost_snapshot_changed")
        else:
            required.append(cost)
        states.append(
            {
                "plan_id": str(child["id"]),
                "model_profile_id": str(child["connection_id"]),
                "model": binding["model_id"],
                "provider": binding["provider"],
                "missing": list(dict.fromkeys(issues)),
                "required_micro_usd": cost,
            }
        )
    cost = sum(required) if len(required) == len(plans) else None
    if (
        prep.get("semantic_judge_templates")
        or prep.get("semantic_judge_gaps")
        or row["snapshot"].get("shared_call_quote")
    ):
        from anvil.campaign_semantic_budget import issues as semantic_quote_issues

        missing.extend(semantic_quote_issues(c, row, plans))
        quote = row["snapshot"].get("shared_call_quote")
        cost = quote["required_micro_usd"] if quote and cost is not None else None
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
    if record["config"].get("golden_kyc_paid"):
        from anvil.golden_kyc_paid_budget import issues as golden_paid_issues

        missing.extend(golden_paid_issues(c, record))
    if record["config"].get("marketing_paid"):
        from anvil.marketing_paid_budget import issues as marketing_paid_issues

        missing.extend(marketing_paid_issues(c, record))
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
        workflow = None
        if child["config"].get("workflow"):
            execution = one(
                c,
                "SELECT e.id,e.state,e.cancel_requested,e.expires_at FROM anvil.workflow_native_links l JOIN anvil.workflow_executions e ON e.id=l.execution_id WHERE l.plan_id=%s",
                (child["id"],),
            )
            if execution:
                state = execution["state"]
                workflow = {
                    "execution_id": str(execution["id"]),
                    "status": state["status"],
                    "nodes": state["nodes"],
                    "cancel_requested": execution["cancel_requested"],
                    "expires_at": execution["expires_at"],
                    "timeline": [
                        {k: event[k] for k in ("index", "node", "outcome") if k in event}
                        for event in state["trace"][-100:]
                    ],
                }
        members.append(
            {
                "plan_id": str(child["id"]),
                "subject_hash": child["subject_hash"],
                "ordinal": child["ordinal"],
                "trial": child["config"].get("trial", 1),
                "model": child["config"]["workspace_model"],
                "check": check,
                "workflow": workflow,
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


def request_timeout_seconds(binding, episode_seconds):
    """New-plan latency policy; never mutates frozen plans or increases token/spend caps."""
    ceiling = (
        180 if binding["provider"] == "gemini" and binding["model_id"] == "gemini-3.8-flash" else 90
    )
    return min(ceiling, episode_seconds)


def _marketing_dispatch_deadline(budget):
    """Keep the original capture cleanup reserve inside the provider timeout."""
    if (
        type(budget) is not dict
        or type(budget.get("remaining_seconds")) is not int
        or budget["remaining_seconds"] < 1
        or budget.get("capture_accepted") is not False
        or type(budget.get("dispatch_before_utc")) is not str
    ):
        raise RuntimeError("marketing_original_dispatch_budget_required")
    before = datetime.fromisoformat(budget["dispatch_before_utc"].replace("Z", "+00:00"))
    if before.tzinfo is None:
        raise RuntimeError("marketing_original_dispatch_deadline_required")
    return min(
        before,
        datetime.now(timezone.utc) + timedelta(seconds=min(600, budget["remaining_seconds"])),
    )


def _marketing_dispatch_request(c, plan_id, stage_index, call_id, request, deadline):
    from anvil.marketing_capture_evidence_store import require_dispatch_prompt

    current = require_dispatch_prompt(c, plan_id, stage_index, call_id, request.actor_text)
    before = min(deadline, _marketing_dispatch_deadline(current))
    remaining = int((before - datetime.now(timezone.utc)).total_seconds())
    if remaining < 1:
        raise RuntimeError("marketing_original_cleanup_reserve_elapsed_no_retry")
    return providers.ActorRequest(
        model=request.model,
        actor_text=request.actor_text,
        max_output_tokens=request.max_output_tokens,
        timeout_seconds=min(request.timeout_seconds, remaining),
    )


def decision(
    project,
    user,
    plan_id,
    stage_index,
    *,
    transport=None,
    remaining_seconds=None,
    broker_claim=None,
):
    from anvil import pilot_environment, worker_dispatch_broker, workspace_dispatch

    if pilot_environment.current():
        if not worker_dispatch_broker.api_enabled() or broker_claim is None:
            raise RuntimeError("pilot_dispatch_requires_api_broker")
        if (
            str(broker_claim.project_id),
            str(broker_claim.actor_id),
            str(broker_claim.plan_id),
            broker_claim.stage_index,
        ) != (str(project), str(user), str(plan_id), stage_index):
            raise RuntimeError("pilot_broker_binding_changed")

    if type(stage_index) is not int or stage_index < 0:
        raise RuntimeError("unsupported_stage")
    if remaining_seconds is not None and (
        type(remaining_seconds) is not int or not 1 <= remaining_seconds <= 600
    ):
        raise RuntimeError("agent_timeout")
    if transport is not None and type(transport) is not httpx.MockTransport:
        raise ValueError("Only an explicit MockTransport test override is supported")
    dispatch_origin = "sdk_mock" if transport is not None else "provider"
    kyc_policy_deadline = monotonic() + remaining_seconds if remaining_seconds is not None else None
    from anvil.golden_kyc_dispatch_scope import current as current_kyc_scope

    active_kyc_scope=current_kyc_scope()
    if active_kyc_scope is not None:
        kyc_policy_deadline=min(kyc_policy_deadline,active_kyc_scope.absolute_deadline) if kyc_policy_deadline is not None else active_kyc_scope.absolute_deadline
    marketing_deadline = None
    with transaction(project, user) as c:
        project_fence(c, project)
        if broker_claim is not None:
            worker_dispatch_broker.authorize(c, broker_claim)
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
        graph_prompt = None
        if record["config"].get("workflow"):
            if broker_claim is None or not broker_claim.effect_key:
                raise RuntimeError("workflow_effect_claim_required")
            from anvil.workflow_native_execution import prompt as workflow_prompt

            graph_prompt, graph_remaining = workflow_prompt(c, record, broker_claim)
            remaining_seconds = min(remaining_seconds or 600, graph_remaining)
        elif record["config"].get("golden_kyc_paid"):
            if pilot_environment.current() != "qa":
                raise RuntimeError("golden_paid_scope_is_qa_only")
            # plan_readiness above verifies the append-only manifest against
            # the immutable group subject. Its hash cannot be required in the
            # plan created before that manifest exists.
            from anvil.golden_kyc_paid_session import actor_prompt as golden_actor_prompt

            graph_prompt = golden_actor_prompt(c, record, stage_index, absolute_deadline=kyc_policy_deadline)
        elif record["config"].get("marketing_paid"):
            if pilot_environment.current() != "qa":
                raise RuntimeError("marketing_paid_scope_is_qa_only")
            from anvil.marketing_paid_session import actor_prompt as marketing_actor_prompt
            from anvil.marketing_world_registry import require_sdk as require_marketing_world_sdk

            capture_budget = require_marketing_world_sdk(c, broker_claim, record)
            marketing_deadline = _marketing_dispatch_deadline(capture_budget)
            if (
                type(capture_budget.get("manifest_id")) is not str
                or str(UUID(capture_budget["manifest_id"])) != capture_budget["manifest_id"]
            ):
                raise RuntimeError("marketing_original_capture_manifest_required")

            if not check["started_at"]:
                raise RuntimeError("marketing_campaign_start_required")
            server_remaining = int(
                (
                    check["started_at"]
                    + timedelta(seconds=record["config"]["episode_timeout_seconds"])
                    - datetime.now(timezone.utc)
                ).total_seconds()
            )
            if server_remaining < 1:
                raise RuntimeError("marketing_campaign_elapsed_limit")
            remaining_seconds = min(
                remaining_seconds or 600, server_remaining, capture_budget["remaining_seconds"]
            )
            marketing_deadline = min(
                marketing_deadline,
                datetime.now(timezone.utc) + timedelta(seconds=remaining_seconds),
                check["started_at"]
                + timedelta(seconds=record["config"]["episode_timeout_seconds"]),
            )
            graph_prompt = marketing_actor_prompt(c, record, stage_index)
        old = c.execute(
            "SELECT * FROM anvil.harbor_agent_calls WHERE plan_id=%s ORDER BY stage_index",
            (plan_id,),
        ).fetchall()
        current = next((r for r in old if r["stage_index"] == stage_index), None)
        if current:
            if (
                record["config"].get("workflow")
                and current["usage"].get("workflow_effect_key") != broker_claim.effect_key
            ):
                raise RuntimeError("workflow_call_binding_changed")
            if current["status"] == "completed":
                return current["output_json"]["text"]
            raise RuntimeError("dispatch_outcome_unknown_no_retry")
        if not record["config"].get("workflow") and (
            len(old) != stage_index or any(r["status"] != "completed" for r in old)
        ):
            raise RuntimeError("stage_sequence_mismatch")
        package = one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (record["package_id"],))
        if graph_prompt is not None:
            prompt = graph_prompt
        elif package["manifest"].get("binding") == "mcp-tool-agent-v1":
            from anvil.import_execution import actor_prompt

            prompt = actor_prompt(c, record, package, stage_index)
        else:
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
        if marketing_deadline is not None and (
            marketing_deadline - datetime.now(timezone.utc)
        ).total_seconds() < 1:
            raise RuntimeError("marketing_original_cleanup_reserve_elapsed_no_retry")
        one(c, "SELECT id FROM anvil.workspace_credentials WHERE id=%s FOR SHARE", (cred["id"],))
        secret = workspace_credentials.resolve(c, cred["id"], cred["version_id"])
        bound = required_cost(record["config"]) // record["config"]["max_calls"]
        if (
            sum(r["reserved_micro_usd"] for r in old) + bound
            > record["config"]["max_total_micro_usd"]
        ):
            raise RuntimeError("spend_ceiling")
        cid = uid()
        dispatch_usage = {"dispatch_origin": dispatch_origin}
        if broker_claim is not None:
            dispatch_usage.update(
                worker_broker_job=str(broker_claim.job_id),
                worker_broker_lease_sha256=hashlib.sha256(
                    str(broker_claim.lease_token).encode()
                ).hexdigest(),
            )
            if broker_claim.effect_key:
                dispatch_usage["workflow_effect_key"] = broker_claim.effect_key
        c.execute(
            "INSERT INTO anvil.harbor_agent_calls(id,project_id,plan_id,stage_index,request_sha256,reserved_micro_usd,status,usage) VALUES(%s,%s,%s,%s,%s,%s,'dispatching',%s)",
            (
                cid,
                project,
                plan_id,
                stage_index,
                hashlib.sha256(prompt.encode()).hexdigest(),
                bound,
                Jsonb(dispatch_usage),
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
        pilot_ticket = pilot_budget.ticket(
            group(c, record["config"]["workspace_execution_group"]), str(record["id"]), cid
        )
    request = providers.ActorRequest(
        model=binding["model_id"],
        actor_text=prompt,
        max_output_tokens=record["config"]["max_output_tokens"],
        timeout_seconds=min(
            record["config"]["request_timeout_seconds"],
            remaining_seconds if remaining_seconds is not None else 600,
        ),
    )
    result = None
    try:
        if record["config"].get("golden_kyc_paid") and kyc_policy_deadline is not None:
            from anvil.marketing_native_wire_bounds import remaining

            seconds = int(remaining(kyc_policy_deadline))
            if seconds < 1:
                raise TimeoutError("Original KYC provider deadline elapsed; no retry")
            request = providers.ActorRequest(model=request.model,actor_text=request.actor_text,
                max_output_tokens=request.max_output_tokens,timeout_seconds=min(request.timeout_seconds,seconds))
        if marketing_deadline is not None:
            # The intent above is committed. Check its retained prompt against
            # the actual SDK request, never a separately reconstructed string.
            with transaction(project, user) as c:
                worker_dispatch_broker.authorize(c, broker_claim)
                request = _marketing_dispatch_request(
                    c, plan_id, stage_index, cid, request, marketing_deadline
                )
        if pilot_ticket is None:
            result = workspace_dispatch.execute(binding, secret, request, transport=transport)
        else:
            result = workspace_dispatch.execute(
                binding, secret, request, transport=transport, pilot_ticket=pilot_ticket
            )
        output = result.text or ""
        usage = result.usage or {}
        # The transport owns this label; a test adapter may inject MockTransport
        # inside the API broker rather than through this function's argument.
        dispatch_usage["dispatch_origin"] = usage.get("dispatch_origin", dispatch_origin)
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
        actual = workspace_costs.billed_cost(price, usage, inputs, outputs)
        if actual > bound:
            raise ValueError()
    except Exception:
        if result and (result.usage or {}).get("dispatch_origin") == "sdk_mock":
            dispatch_origin = "sdk_mock"
        dispatch_usage["dispatch_origin"] = dispatch_origin
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
            "malformed_provider_response",
            "empty_or_malformed_output",
        }
        error_code = (
            result.error_code
            if result and result.error_code in safe_errors
            else "response_model_or_usage_not_admitted"
        )
        evidence = provider_evidence(result)
        with transaction(project, user) as c:
            project_fence(c, project)
            c.execute(
                "UPDATE anvil.harbor_agent_calls SET status='execution_unknown',usage=usage||%s::jsonb,request_id=%s,finished_at=now() WHERE id=%s",
                (
                    Jsonb(
                        {
                            "dispatch_origin": dispatch_origin,
                            "error_code": error_code,
                            "provider_evidence": evidence,
                            **dispatch_usage,
                        }
                    ),
                    evidence.get("request_id"),
                    cid,
                ),
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
    with transaction(project, user) as c:
        project_fence(c, project)
        c.execute(
            "UPDATE anvil.harbor_agent_calls SET status='completed',output_json=%s,usage=usage||%s::jsonb,request_id=%s,actual_micro_usd=%s,finished_at=now() WHERE id=%s",
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
                        **dispatch_usage,
                    }
                ),
                result.request_id,
                actual,
                cid,
            ),
        )
        audit(c, project, user, "workspace.output_captured", cid, {"actual_micro_usd": actual})
    if (
        record["config"].get("golden_kyc_paid")
        and os.environ.get("ANVIL_TASK_SAFETY_HOST_ENABLED") == "true"
    ):
        from anvil.task_safety_runtime import broker_capture

        # Preserve the completed SDK/billing ledger even if safety evidence
        # capture fails; that failure blocks safety scoring, never re-dispatches.
        with transaction(project, user) as c:
            broker_capture(c, project, plan_id, cid, prompt, output)
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
                if prep["snapshot"].get("semantic_judge_gaps"):
                    raise HTTPException(
                        409,
                        "Anvil semantic judge qualification is incomplete; the task population was preserved",
                    )
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
                    row = one(c, "SELECT * FROM anvil.connections WHERE id=%s", (bound["id"],))
                    snapshot["pricing"].append(workspace_costs.for_model(row))
                    snapshot["processing_terms"].append(
                        row["config"].get("workspace_terms") if row else None
                    )
                trials = prep["snapshot"].get("trials_per_model", 1)
                package_snapshots = {
                    p["id"]: p
                    for p in prep["snapshot"].get("task_packages", [prep["snapshot"]["package"]])
                }
                members = [
                    (index, bound, trial, case_assignment)
                    for index, bound in enumerate(prep["snapshot"]["models"])
                    for case_assignment in prep["snapshot"].get("case_assignments", [None])
                    for trial in range(1, trials + 1)
                ]
                if (
                    prep["snapshot"].get("case_assignments")
                    and len(members) * prep["snapshot"].get("max_agent_steps", 1) > 1000
                ):
                    raise HTTPException(
                        422,
                        "This aggregate native run exceeds1000 priced physical request slots; select fewer cases, models, repeats or turns",
                    )
                plan_ids = [uid() for _ in members]
                templates = prep["snapshot"].get("semantic_judge_templates", [])
                if templates:
                    from anvil.campaign_semantic_budget import (
                        fixed_judge_snapshots,
                        plan_blueprints,
                    )
                    from anvil.campaign_semantic_budget import quote as semantic_quote

                    candidates, blueprints = [], {}
                    for ordinal, (index, bound, trial, assignment) in enumerate(members):
                        selected = (
                            package_snapshots.get(assignment["package_id"]) if assignment else None
                        )
                        native = selected["manifest"].get("native_binding", {}) if selected else {}
                        if native.get("task_mode") != "reusable_campaign_workflow":
                            raise HTTPException(
                                422,
                                "Private campaign judge requires the exact Marketing task population",
                            )
                        pid = plan_ids[ordinal]
                        candidates.append(
                            {
                                "plan_id": pid,
                                "max_calls": prep["snapshot"]["max_agent_steps"],
                                "max_output_tokens": prep["snapshot"]["max_output_tokens"],
                                "model_binding": bound,
                                "pricing": snapshot["pricing"][index],
                            }
                        )
                        try:
                            blueprints[pid] = plan_blueprints(
                                prep["snapshot"], native | {"case_assignment": assignment}, bound
                            )
                        except ValueError as error:
                            raise HTTPException(409, str(error)) from None
                    try:
                        snapshot["shared_call_quote"] = semantic_quote(
                            candidates,
                            blueprints,
                            prep["snapshot"]["aggregate_cap_micro_usd"],
                            fixed_judges=fixed_judge_snapshots(prep["snapshot"]),
                        )
                    except ValueError as error:
                        raise HTTPException(422, str(error)) from None
                subject = digest({"id": gid, "created_by": str(user), "snapshot": snapshot})
                c.execute(
                    "INSERT INTO anvil.workspace_execution_groups(id,project_id,preparation_id,created_by,snapshot,subject_hash) VALUES(%s,%s,%s,%s,%s,%s)",
                    (gid, project, body.preparation_id, user, Jsonb(snapshot), subject),
                )
                for ordinal, (index, bound, trial, case_assignment) in enumerate(members):
                    selected_package_id = (
                        case_assignment["package_id"]
                        if case_assignment
                        else prep["snapshot"]["package"]["id"]
                    )
                    selected_package = package_snapshots.get(selected_package_id)
                    if not selected_package:
                        raise HTTPException(
                            409, "Case assignment is outside the immutable task package set"
                        )
                    pid = plan_ids[ordinal]
                    config = {
                        "workspace_execution_group": gid,
                        "workspace_model": bound,
                        "trial": trial,
                        "environment": prep["snapshot"].get("environment"),
                        "model": bound["model_id"],
                        "connection_hash": bound["config_hash"],
                        "package_sha256": selected_package["package_sha256"],
                        "max_calls": prep["snapshot"].get(
                            "max_agent_steps",
                            len(selected_package["manifest"]["stage_order"]),
                        ),
                        "max_output_tokens": prep["snapshot"]["max_output_tokens"],
                        "request_timeout_seconds": request_timeout_seconds(
                            bound, prep["snapshot"]["episode_timeout_seconds"]
                        ),
                        "episode_timeout_seconds": prep["snapshot"]["episode_timeout_seconds"],
                        "pricing": snapshot["pricing"][index],
                        "adapter_sha256": snapshot["adapter_sha256"],
                    }
                    config["max_total_micro_usd"] = required_cost(config)
                    native = selected_package["manifest"].get("native_binding")
                    if (
                        selected_package["manifest"].get("binding")
                        == "golden-kyc-openenv-tool-agent-v1"
                    ):
                        if not native:
                            raise HTTPException(409, "Native Golden package binding is absent")
                        if native.get("task_mode") in {"reusable_state_workflow", "reusable_application_workflow"}:
                            if not case_assignment:
                                raise HTTPException(
                                    409,
                                    "Reusable state-task plan requires an immutable case assignment",
                                )
                            native = native | {
                                "application_id": case_assignment["application_id"],
                                "application_sha256": case_assignment["application_sha256"],
                                "case_assignment": case_assignment,
                            }
                        config.update(golden_kyc_paid=True, golden_native_binding=native)
                    elif (
                        selected_package["manifest"].get("binding")
                        == "marketing-task2-five-role-v1"
                    ):
                        if (
                            not native
                            or not case_assignment
                            or native.get("task_mode") != "reusable_campaign_workflow"
                        ):
                            raise HTTPException(
                                409, "Marketing requires one frozen campaign assignment per plan"
                            )
                        config.update(
                            marketing_paid=True,
                            marketing_native_binding=native | {"case_assignment": case_assignment},
                        )
                    if prep["snapshot"].get("workflow"):
                        config["workflow"] = prep["snapshot"]["workflow"]
                    child_hash = digest({"id": pid, "created_by": str(user), "config": config})
                    c.execute(
                        "INSERT INTO anvil.harbor_agent_plans(id,project_id,package_id,connection_id,created_by,config,subject_hash) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                        (
                            pid,
                            project,
                            selected_package_id,
                            bound["id"],
                            user,
                            Jsonb(config),
                            child_hash,
                        ),
                    )
                    c.execute(
                        "INSERT INTO anvil.workspace_execution_models(project_id,group_id,ordinal,plan_id) VALUES(%s,%s,%s,%s)",
                        (project, gid, ordinal, pid),
                    )
                    if config.get("marketing_paid"):
                        from anvil.marketing_paid_budget import bind as bind_marketing

                        bind_marketing(
                            c, one(c, "SELECT * FROM anvil.harbor_agent_plans WHERE id=%s", (pid,))
                        )
                        for reservation in snapshot.get("shared_call_quote", {}).get(
                            "judge_reservations", []
                        ):
                            if reservation["plan_id"] == pid:
                                extra_columns, extra_values = "", ()
                                if reservation["blueprint"]["schema_version"] == (
                                    "anvil.campaign-semantic-judge-blueprint.v2"
                                ):
                                    extra_columns = ",model_binding,pricing"
                                    extra_values = (
                                        Jsonb(reservation["model_binding"]),
                                        Jsonb(reservation["pricing"]),
                                    )
                                c.execute(
                                    "INSERT INTO marketing_runtime.semantic_quotes(id,project_id,group_id,plan_id,batch_index,blueprint,blueprint_sha256,model_binding_sha256,pricing_sha256,bound_micro_usd,physical_calls"
                                    + extra_columns
                                    + ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s"
                                    + (",%s,%s" if extra_values else "")
                                    + ")",
                                    (
                                        uid(),
                                        project,
                                        gid,
                                        pid,
                                        reservation["batch_index"],
                                        Jsonb(reservation["blueprint"]),
                                        reservation["blueprint_sha256"],
                                        reservation["model_binding_sha256"],
                                        reservation["pricing_sha256"],
                                        reservation["bound_micro_usd"],
                                        reservation["physical_calls"],
                                    )
                                    + extra_values,
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
                "SELECT * FROM anvil.workspace_execution_groups WHERE (%s::uuid IS NULL OR preparation_id=%s) AND (%s::uuid IS NULL OR (created_at,id)<(SELECT created_at,id FROM anvil.workspace_execution_groups WHERE id=%s)) ORDER BY created_at DESC,id DESC LIMIT %s",
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

    @router.post("/execution-groups/{gid}/authorize")
    def authorize(project: UUID, gid: UUID, body: AdminRun, request: Request):
        recent_admin_signin(request)
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def act():
                row = group(c, gid, True)
                if row["state"] != "draft":
                    raise HTTPException(409, "This group has already started")
                authorize_admin(c, row, user, body)
                return public(c, row)

            return wrap(
                idempotent(c, project, user, request, body.model_dump(mode="json"), act), request
            )

    @router.post("/execution-groups/{gid}/revoke-authorization")
    def revoke_authorization(project: UUID, gid: UUID, body: Revocation, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def act():
                row = group(c, gid, True)
                record = one(
                    c,
                    "SELECT id FROM anvil.workspace_admin_run_authorizations WHERE group_id=%s",
                    (gid,),
                )
                if not record:
                    raise HTTPException(409, "No authorization to revoke")
                c.execute(
                    "INSERT INTO anvil.workspace_admin_run_revocations(id,project_id,authorization_id,revoked_by,rationale) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(project_id,authorization_id) DO NOTHING",
                    (uid(), project, record["id"], user, body.rationale),
                )
                audit(
                    c,
                    project,
                    user,
                    "workspace.admin_run_revoked",
                    gid,
                    {"rationale": body.rationale},
                )
                return public(c, row)

            return wrap(
                idempotent(c, project, user, request, body.model_dump(mode="json"), act), request
            )

    @router.post("/execution-groups/{gid}/launch")
    def launch(project: UUID, gid: UUID, request: Request, body: AdminRun | None = None):
        if body is not None:
            recent_admin_signin(request)
        with context(request, project) as (c, user, roles):
            auth.require(roles, *PLAN_ROLES)

            def act():
                row = group(c, gid, True)
                if row["snapshot"].get("profile") == "sme-offline-comparison-v1":
                    raise HTTPException(
                        409, "Launch benchmark children only through their parent comparison"
                    )
                if row["state"] == "launched":
                    return public(c, row)
                if body is not None:
                    authorize_admin(c, row, user, body)
                policy = authority(c, row)
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
                current_policy = authority(c, row)
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
                pilot_budget.reserve(c, row)
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
                        "INSERT INTO anvil.jobs(id,project_id,kind,target_id,operation_key) VALUES(%s,%s,%s,%s,%s)",
                        (
                            uid(),
                            project,
                            "benchmark_golden_paid"
                            if child["config"].get("golden_kyc_paid")
                            else "benchmark_marketing_paid"
                            if child["config"].get("marketing_paid")
                            else "harbor_check",
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

            return wrap(
                idempotent(
                    c, project, user, request, body.model_dump(mode="json") if body else {}, act
                ),
                request,
            )

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
