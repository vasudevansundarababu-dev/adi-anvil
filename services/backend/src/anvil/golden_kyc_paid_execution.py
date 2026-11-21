"""API admission/finalization for the dedicated Golden scheduler, not a grader.

Provider keys stay behind the existing lease broker. Completion is read from
the database seal and broker ledger, never accepted from the worker's claims.
"""

import os
from time import monotonic

from anvil import harbor_agents, pilot_environment, workspace_execution
from anvil.db import Jsonb, audit, one, project_fence, transaction
from anvil.golden_kyc_paid_session import task_context
from anvil.worker_dispatch_broker import authorize


def admitted(c, claim, preparing=False, *, absolute_deadline=None):
    if (
        pilot_environment.current() != "qa"
        or os.environ.get("ANVIL_GOLDEN_KYC_PAID_ENABLED") != "true"
    ):
        raise RuntimeError("golden_paid_qa_admission_disabled")
    project_fence(c, claim.project_id)
    authorize(c, claim, preparing=preparing)
    plan = harbor_agents.plan(c, claim.plan_id)
    workspace_execution.group(c, plan["config"]["workspace_execution_group"], True)
    plan = harbor_agents.plan(c, claim.plan_id, True)
    if (
        plan["config"].get("golden_kyc_paid") is not True
        or not workspace_execution.plan_readiness(c, plan)["ready"]
    ):
        raise RuntimeError("golden_paid_admission_revoked")
    native = plan["config"]["golden_native_binding"]
    from anvil.kyc_expectation_reviews import require_plan as require_expectations

    require_expectations(c, claim.project_id, plan)
    task_context(
        c,
        claim.project_id,
        native["resolved_task_id"],
        native["application_id"],
        execution_data=native.get("execution_data"),
        resolved_input=native.get("resolved_input"),
        require_policy=preparing, policy_scope=native.get("policy_scope"), policy_user=claim.actor_id,
        absolute_deadline=absolute_deadline,
    )
    return plan


def prepare(claim):
    from anvil.golden_kyc_dispatch_scope import current

    absolute_deadline = monotonic() + claim.remaining_seconds
    scope=current()
    if scope is not None:
        absolute_deadline=min(absolute_deadline,scope.absolute_deadline)
    with transaction(claim.project_id, claim.actor_id) as c:
        plan = admitted(c, claim, preparing=True, absolute_deadline=absolute_deadline)
        check = one(
            c, "SELECT * FROM anvil.harbor_checks WHERE id=%s FOR UPDATE", (plan["check_id"],)
        )
        if check["invocation_count"] or one(
            c, "SELECT 1 FROM anvil.harbor_agent_calls WHERE plan_id=%s LIMIT 1", (plan["id"],)
        ):
            raise RuntimeError("golden_paid_invocation_not_replayable")
        c.execute(
            "UPDATE anvil.harbor_checks SET state='running',started_at=now(),invocation_count=1 WHERE id=%s",
            (check["id"],),
        )
        audit(
            c,
            claim.project_id,
            claim.actor_id,
            "golden.paid_prepared",
            plan["id"],
            {"private_reference_to_actor": False, "provider_credentials_to_scheduler": False},
        )
        return {
            "mode": "golden-native",
            "group_id": plan["config"]["workspace_execution_group"],
            "native_binding": plan["config"]["golden_native_binding"],
            "max_calls": plan["config"]["max_calls"],
            "episode_timeout_seconds": plan["config"]["episode_timeout_seconds"],
            "request_timeout_seconds": plan["config"]["request_timeout_seconds"],
            "model_label": plan["config"]["workspace_model"]["model_id"],
            "repetition": plan["config"]["trial"],
            "public_actor": task_context(
                c,
                claim.project_id,
                plan["config"]["golden_native_binding"]["resolved_task_id"],
                plan["config"]["golden_native_binding"]["application_id"],
                execution_data=plan["config"]["golden_native_binding"].get("execution_data"),
                resolved_input=plan["config"]["golden_native_binding"].get("resolved_input"),
                require_policy=True,
                policy_scope=plan["config"]["golden_native_binding"].get("policy_scope"), policy_user=claim.actor_id,
                absolute_deadline=absolute_deadline,
            ),
        }


def finish(claim):
    with transaction(claim.project_id, claim.actor_id) as c:
        if claim.native.get("failure") is True:
            project_fence(c, claim.project_id)
            plan = harbor_agents.plan(c, claim.plan_id)
            if plan["config"].get("golden_kyc_paid") is not True:
                raise RuntimeError("golden_paid_plan_required")
            workspace_execution.group(c, plan["config"]["workspace_execution_group"], True)
            plan = harbor_agents.plan(c, claim.plan_id, True)
            attempt = lock_attempt(c, claim.project_id, plan, claim.job_id)
            if str(attempt["lease_token"]) != str(claim.lease_token):
                raise RuntimeError("golden_paid_lease_changed")
            if attempt["status"] != "leased" or attempt["check_state"] not in {"queued", "running"}:
                return {"status": attempt["check_state"], "terminal_result_preserved": True}
            authorize(c, claim, preparing=attempt["check_state"] == "queued", allow_cancel=True)
            calls = c.execute(
                "SELECT status FROM anvil.harbor_agent_calls WHERE project_id=%s AND plan_id=%s",
                (claim.project_id, plan["id"]),
            ).fetchall()
            return disposition(c, claim.project_id, claim.actor_id, plan, claim.job_id, calls)
        plan = admitted(c, claim)
        lock_attempt(c, claim.project_id, plan, claim.job_id)
        authorize(c, claim)
        capture = one(c, "SELECT banking.paid_agent_capture(%s) AS value", (plan["id"],))["value"]
        from anvil.golden_native_bridge import validate_framework
        from anvil.praxis_generic_contract import digest

        if claim.native.get("schema_version") != "anvil.golden-paid-finish.v2":
            raise RuntimeError("golden_actual_framework_capture_required")
        framework = validate_framework(claim.native.get("framework") or {}, purpose="kyc_worker_collection_only")
        receipt = framework["trusted_receipt"]
        if not capture or any(
            receipt.get(key) != value
            for key, value in {
                "project_id": str(claim.project_id),
                "job_id": str(claim.job_id),
                "plan_id": str(plan["id"]),
                "trial_id": str(capture["trial_id"]),
                "generation": capture["generation"],
                "turns": capture["turns"],
                "closed": capture["closed"],
            }.items()
        ):
            raise RuntimeError("golden_framework_and_sql_capture_differ")
        last = one(
            c,
            "SELECT observation,observation_sha256 FROM banking.paid_agent_observations WHERE project_id=%s AND plan_id=%s ORDER BY stage_index DESC LIMIT 1",
            (claim.project_id, plan["id"]),
        )
        if (
            not last
            or last["observation_sha256"] != receipt.get("last_observation_sha256")
            or framework.get("actor_output_sha256") != digest(last["observation"])
        ):
            raise RuntimeError("golden_framework_observation_changed")
        calls = c.execute(
            "SELECT id,status,usage,actual_micro_usd,request_id FROM anvil.harbor_agent_calls WHERE project_id=%s AND plan_id=%s ORDER BY stage_index",
            (claim.project_id, plan["id"]),
        ).fetchall()
        uncertain = any(call["status"] in {"dispatching", "execution_unknown"} for call in calls)
        complete = bool(
            capture
            and capture["closed"]
            and capture["state_sha256"]
            and capture["turns"] == len(calls)
            and calls
            and all(call["status"] == "completed" for call in calls)
        )
        if complete:
            complete = one(
                c,
                "SELECT banking.finalize_paid_agent_capture(%s,%s,%s) AS ok",
                (claim.job_id, claim.lease_token, plan["id"]),
            )["ok"]
        state = "execution_unknown" if uncertain else "succeeded" if complete else "failed"
        origins = {call["usage"].get("dispatch_origin") for call in calls}
        result = {
            "origin": "actual_model_capture"
            if origins == {"provider"}
            else "software_or_unverified_capture",
            "native_capture": capture,
            "agent_plan_id": str(plan["id"]),
            "provider_calls": sum(
                call["usage"].get("dispatch_origin") == "provider" for call in calls
            ),
            "physical_call_ids": [str(call["id"]) for call in calls],
            "scores": None,
            "model_performance_validated": False,
            "grading_status": "separate_sealed_state_evaluation_pending"
            if complete
            else "incomplete_or_unknown_execution",
            "reservation_retained": True,
            "framework_capture": framework,
            "framework_capture_sha256": digest(framework),
        }
        c.execute(
            "UPDATE anvil.harbor_checks SET state=%s,result=%s,finished_at=now() WHERE id=%s AND state='running'",
            (state, Jsonb(result), plan["check_id"]),
        )
        c.execute(
            "UPDATE anvil.jobs SET status=%s WHERE id=%s AND lease_token=%s",
            ("succeeded" if complete else "failed", claim.job_id, claim.lease_token),
        )
        audit(
            c,
            claim.project_id,
            claim.actor_id,
            "golden.paid_capture_finished",
            plan["id"],
            {
                "state": state,
                "grading_status": result["grading_status"],
                "reservation_retained": True,
            },
        )
        return {"status": state, "grading_status": result["grading_status"]}


def disposition(c, project, user, plan, job, calls):
    attempt = lock_attempt(c, project, plan, job)
    if attempt["status"] != "leased" or attempt["check_state"] not in {"queued", "running"}:
        return {"status": attempt["check_state"], "terminal_result_preserved": True}
    uncertain = any(call["status"] in {"dispatching", "execution_unknown"} for call in calls)
    state = "execution_unknown" if uncertain else "failed"
    reason = (
        "provider_outcome_requires_reconciliation"
        if uncertain
        else "interrupted_after_response"
        if calls
        else "failed_before_dispatch"
    )
    changed = one(
        c,
        "UPDATE anvil.harbor_checks SET state=%s,error_code=%s,finished_at=now() WHERE id=%s AND state IN ('queued','running') RETURNING id",
        (state, reason, plan["check_id"]),
    )
    if not changed:
        raise RuntimeError("golden_paid_terminal_result_changed")
    c.execute(
        "UPDATE anvil.jobs SET status='failed',error_code=%s WHERE id=%s AND status='leased' AND lease_token=%s",
        (reason, job, attempt["lease_token"]),
    )
    audit(
        c,
        project,
        user,
        "golden.paid_interruption_recorded",
        plan["id"],
        {
            "state": state,
            "reason": reason,
            "reservation_retained": True,
            "physical_request_retry": False,
        },
    )
    return {"status": state, "reason": reason, "reservation_retained": True}


def lock_attempt(c, project, plan, job):
    row = one(
        c,
        "SELECT j.*,h.state AS check_state,j.lease_until<=now() AS expired FROM anvil.jobs j JOIN anvil.harbor_checks h ON h.id=j.target_id AND h.project_id=j.project_id WHERE j.id=%s AND j.project_id=%s AND j.kind='benchmark_golden_paid' AND h.id=%s AND h.agent_plan_id=%s FOR UPDATE OF j,h",
        (job, project, plan["check_id"], plan["id"]),
    )
    if not row:
        raise RuntimeError("golden_paid_attempt_missing")
    return row


def reconcile(c, project, user, group_id):
    """Admin records expired interruption only; no lease renewal or dispatch."""
    workspace_execution.group(c, group_id, True)
    rows = c.execute(
        "SELECT j.id AS job_id,p.* FROM anvil.jobs j JOIN anvil.harbor_agent_plans p ON p.check_id=j.target_id AND p.project_id=j.project_id WHERE j.project_id=%s AND p.config->>'workspace_execution_group'=%s AND p.config->>'golden_kyc_paid'='true' AND j.kind='benchmark_golden_paid' AND j.status='leased' AND j.lease_until<=now() ORDER BY j.id",
        (project, str(group_id)),
    ).fetchall()
    results = []
    for plan in rows:
        harbor_agents.plan(c, plan["id"], True)
        attempt = lock_attempt(c, project, plan, plan["job_id"])
        if attempt["status"] != "leased" or not attempt["expired"]:
            continue
        calls = c.execute(
            "SELECT status FROM anvil.harbor_agent_calls WHERE project_id=%s AND plan_id=%s",
            (project, plan["id"]),
        ).fetchall()
        results.append(
            {
                "plan_id": str(plan["id"]),
                **disposition(c, project, user, plan, plan["job_id"], calls),
            }
        )
    return {"items": results, "model_requests": 0, "reservation_retained": True}
