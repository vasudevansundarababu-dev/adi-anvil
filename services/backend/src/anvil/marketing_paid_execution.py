"""API-side Marketing admission; provider secrets and private sources stay here.

This module does not provision fixtures, grant Run authority or accept a worker's
success assertion. Finalization requires separate durable framework/SQL custody.
"""

import os

from anvil import harbor_agents, pilot_environment, workspace_execution
from anvil.db import Jsonb, audit, one, project_fence, transaction
from anvil.marketing_paid_session import require_frozen
from anvil.worker_dispatch_broker import authorize


def admitted(c, claim, *, preparing=False):
    if (
        pilot_environment.current() != "qa"
        or os.environ.get("ANVIL_MARKETING_PAID_ENABLED") != "true"
    ):
        raise RuntimeError("marketing_paid_qa_admission_disabled")
    project_fence(c, claim.project_id)
    authorize(c, claim, preparing=preparing)
    plan = harbor_agents.plan(c, claim.plan_id)
    workspace_execution.group(c, plan["config"]["workspace_execution_group"], True)
    plan = harbor_agents.plan(c, claim.plan_id, True)
    if (
        plan["config"].get("marketing_paid") is not True
        or plan["config"].get("golden_kyc_paid")
        or not workspace_execution.plan_readiness(c, plan)["ready"]
    ):
        raise RuntimeError("marketing_paid_admission_revoked")
    native = plan["config"]["marketing_native_binding"]
    context = require_frozen(
        c, claim.project_id, native, case_id=native["case_assignment"]["case_id"]
    )
    return plan, context


def prepare(claim):
    if os.environ.get("ANVIL_MARKETING_WORLD_ENABLED") != "true":
        raise RuntimeError("marketing_private_world_preparation_disabled")
    with transaction(claim.project_id, claim.actor_id) as c:
        plan, context = admitted(c, claim, preparing=True)
        check = one(
            c, "SELECT * FROM anvil.harbor_checks WHERE id=%s FOR UPDATE", (plan["check_id"],)
        )
        if (
            check["invocation_count"]
            or one(
                c, "SELECT 1 FROM anvil.harbor_agent_calls WHERE plan_id=%s LIMIT 1", (plan["id"],)
            )
            or one(
                c,
                "SELECT 1 FROM marketing_runtime.paid_episode_links WHERE plan_id=%s",
                (plan["id"],),
            )
        ):
            raise RuntimeError("marketing_paid_invocation_not_replayable")
        c.execute(
            "UPDATE anvil.harbor_checks SET state='running',started_at=now(),invocation_count=1 WHERE id=%s",
            (check["id"],),
        )
        from anvil.marketing_world_api import allocate
        from anvil.marketing_world_registry import load
        from anvil.marketing_world_quiescence import Scope
        from anvil.praxis_generic_contract import digest as wire_digest
        import hashlib

        world, source, qualification = load(c, claim, plan)
        attachment = allocate(c, claim, plan, world, source, qualification)
        stop_scope = Scope.model_validate({
            **{name: attachment[name] for name in (
                "project_id", "job_id", "plan_id", "world_binding_id",
                "world_binding_sha256", "episode_id", "generation", "execution_sha256",
            )},
            "lease_sha256": hashlib.sha256(str(claim.lease_token).encode()).hexdigest(),
            "source_qualification_sha256": qualification["receipt_sha256"],
        }).model_dump(mode="json")
        audit(
            c,
            claim.project_id,
            claim.actor_id,
            "marketing.paid_prepared",
            plan["id"],
            {
                "private_reference_to_actor": False,
                "provider_credentials_to_scheduler": False,
                "workflow_graph_sha256": context["native_binding"]["workflow_graph_sha256"],
            },
        )
        return {
            "mode": "marketing-native",
            "world_attachment": attachment,
            "world_attachment_sha256": wire_digest(attachment),
            "world_stop_scope": stop_scope,
            "group_id": plan["config"]["workspace_execution_group"],
            "native_binding": plan["config"]["marketing_native_binding"],
            "public_actor": context["actor"],
            "execution": context["execution"],
            "max_calls": plan["config"]["max_calls"],
            "episode_timeout_seconds": plan["config"]["episode_timeout_seconds"],
            "request_timeout_seconds": plan["config"]["request_timeout_seconds"],
            "model_label": plan["config"]["workspace_model"]["model_id"],
            "repetition": plan["config"]["trial"],
        }


def finish(claim):
    """A failure report can only close/retain custody, never certify success."""
    if claim.native.get("failure") is not True:
        raise RuntimeError("marketing_durable_native_finish_qualification_required")
    with transaction(claim.project_id, claim.actor_id) as c:
        project_fence(c, claim.project_id)
        plan = harbor_agents.plan(c, claim.plan_id)
        if plan["config"].get("marketing_paid") is not True:
            raise RuntimeError("marketing_paid_plan_required")
        workspace_execution.group(c, plan["config"]["workspace_execution_group"], True)
        plan = harbor_agents.plan(c, claim.plan_id, True)
        attempt = one(
            c,
            "SELECT j.*,h.state AS check_state FROM anvil.jobs j JOIN anvil.harbor_checks h ON h.id=j.target_id AND h.project_id=j.project_id WHERE j.id=%s AND j.project_id=%s AND j.kind='benchmark_marketing_paid' AND h.id=%s AND h.agent_plan_id=%s FOR UPDATE OF j,h",
            (claim.job_id, claim.project_id, plan["check_id"], plan["id"]),
        )
        if not attempt or str(attempt["lease_token"]) != str(claim.lease_token):
            raise RuntimeError("marketing_paid_lease_changed")
        if attempt["status"] != "leased" or attempt["check_state"] not in {"queued", "running"}:
            return {"status": attempt["check_state"], "terminal_result_preserved": True}
        authorize(c, claim, preparing=attempt["check_state"] == "queued", allow_cancel=True)
        calls = c.execute(
            "SELECT id,status FROM anvil.harbor_agent_calls WHERE project_id=%s AND plan_id=%s",
            (claim.project_id, plan["id"]),
        ).fetchall()
        pending = one(
            c,
            "SELECT marketing_runtime.paid_attempt_pending(%s,%s,%s) AS pending",
            (claim.job_id, claim.lease_token, plan["id"]),
        )["pending"]
        if pending is None:
            raise RuntimeError("marketing_paid_attempt_scope_changed")
        unknown = (
            pending["pending_tools"]
            or pending["pending_workflow"]
            or any(call["status"] in {"dispatching", "execution_unknown"} for call in calls)
        )
        state = "execution_unknown" if unknown else "failed"
        result = {
            "status": state,
            "reservation_retained": True,
            "replay_permitted": False,
            "scores": None,
            "model_performance_validated": False,
            "physical_call_ids": [str(call["id"]) for call in calls],
        }
        c.execute(
            "UPDATE anvil.harbor_checks SET state=%s,result=%s,finished_at=now() WHERE id=%s AND state IN('queued','running')",
            (state, Jsonb(result), plan["check_id"]),
        )
        c.execute(
            "UPDATE anvil.jobs SET status='failed' WHERE id=%s AND lease_token=%s",
            (claim.job_id, claim.lease_token),
        )
        audit(
            c, claim.project_id, claim.actor_id, "marketing.paid_capture_failed", plan["id"], result
        )
        return result
