"""Private source and original Task grading stay in the API, never the worker."""

import hashlib
import json
import os

from anvil import artifacts, harbor_agents, workspace_execution
from anvil.db import Jsonb, audit, digest, one, project_fence, transaction
from anvil.environment_collect import harbor_collection
from anvil.environment_structured_agent import output_value, source_task
from anvil.praxis_contract import grade
from anvil.worker_dispatch_broker import authorize


def source(c, plan):
    package = one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (plan["package_id"],))
    row = one(c, "SELECT * FROM anvil.praxis_sources WHERE id=%s", (package["source_id"],))
    # Existing original typed parser verifies exact payload and task identity.
    task = source_task(artifacts.read(c, row["source_artifact_id"]), package["manifest"])
    return package, task


def prepare(claim):
    if not any(os.environ.get(flag) == "true" for flag in (
        "ANVIL_HARBOR_HOST_MEDIATED_STRUCTURED_ENABLED",
        "ANVIL_HARBOR_WORKFLOW_ENABLED",
        "ANVIL_GOLDEN_KYC_PAID_ENABLED",
        "ANVIL_MARKETING_PAID_ENABLED",
    )):
        raise RuntimeError("pilot_native_runtime_disabled")
    with transaction(claim.project_id, claim.actor_id) as c:
        planned = harbor_agents.plan(c, claim.plan_id)
        if planned["config"].get("golden_kyc_paid"):
            from anvil.golden_kyc_paid_execution import prepare as prepare_golden

            return prepare_golden(claim)
        if planned["config"].get("marketing_paid"):
            from anvil.marketing_paid_execution import prepare as prepare_marketing

            return prepare_marketing(claim)
    if (
        os.environ.get("ANVIL_HARBOR_HOST_MEDIATED_STRUCTURED_ENABLED") != "true"
        and os.environ.get("ANVIL_HARBOR_WORKFLOW_ENABLED") != "true"
    ):
        raise RuntimeError("pilot_native_runtime_disabled")
    with transaction(claim.project_id, claim.actor_id) as c:
        planned = harbor_agents.plan(c, claim.plan_id)
        if planned["config"].get("workflow"):
            from anvil.workflow_native_execution import prepare as prepare_graph

            return prepare_graph(claim)
    if os.environ.get("ANVIL_HARBOR_HOST_MEDIATED_STRUCTURED_ENABLED") != "true":
        raise RuntimeError("pilot_native_runtime_disabled")
    with transaction(claim.project_id, claim.actor_id) as c:
        project_fence(c, claim.project_id)
        authorize(c, claim, preparing=True)
        plan = harbor_agents.plan(c, claim.plan_id)
        workspace_execution.group(c, plan["config"]["workspace_execution_group"], True)
        plan = harbor_agents.plan(c, claim.plan_id, True)
        check = one(
            c, "SELECT * FROM anvil.harbor_checks WHERE id=%s FOR UPDATE", (plan["check_id"],)
        )
        if (
            check["invocation_count"]
            or not workspace_execution.plan_readiness(c, plan)["ready"]
            or one(
                c,
                "SELECT 1 FROM anvil.harbor_agent_calls WHERE plan_id=%s LIMIT 1",
                (claim.plan_id,),
            )
        ):
            raise RuntimeError("pilot_native_admission_denied")
        package, task = source(c, plan)
        c.execute(
            "UPDATE anvil.harbor_checks SET state='running',started_at=now(),invocation_count=1 WHERE id=%s",
            (check["id"],),
        )
        c.execute(
            "UPDATE anvil.jobs SET lease_until=now()+interval '240 seconds' WHERE id=%s AND lease_token=%s",
            (claim.job_id, claim.lease_token),
        )
        audit(
            c,
            claim.project_id,
            claim.actor_id,
            "pilot.native_prepared",
            check["id"],
            {"package_sha256": package["package_sha256"], "private_source_to_worker": False},
        )
        return {
            "task_id": task.task_id,
            "source_sha256": package["manifest"]["source_sha256"],
            "remaining_seconds": min(120, plan["config"]["episode_timeout_seconds"]),
        }


def capture_receipt(c, claim):
    plan = harbor_agents.plan(c, claim.plan_id)
    if plan["config"].get("workflow"):
        from anvil.workflow_native_execution import capture_receipt as graph_receipt

        return graph_receipt(c, claim)
    package, _ = source(c, plan)
    call = one(
        c,
        "SELECT * FROM anvil.harbor_agent_calls WHERE plan_id=%s AND stage_index=%s AND status='completed'",
        (claim.plan_id, claim.stage_index),
    )
    if (
        not call
        or call["usage"].get("worker_broker_job") != str(claim.job_id)
        or call["usage"].get("worker_broker_lease_sha256")
        != hashlib.sha256(str(claim.lease_token).encode()).hexdigest()
    ):
        raise RuntimeError("pilot_capture_call_binding_changed")
    output = output_value(call["output_json"]["text"])
    origin = call["usage"].get("dispatch_origin")
    if origin not in {"provider", "sdk_mock"}:
        raise RuntimeError("pilot_capture_origin_missing")
    return {
        "schema_version": "anvil.structured-model-capture.v1",
        "source_sha256": package["manifest"]["source_sha256"],
        "package_sha256": package["package_sha256"],
        "plan_id": str(plan["id"]),
        "call_id": str(call["id"]),
        "dispatch_origin": origin,
        "output_sha256": hashlib.sha256(json.dumps(output, allow_nan=False).encode()).hexdigest(),
    }


def verify_capture(native, receipt):
    if len(json.dumps(native, allow_nan=False).encode()) > 1048576:
        raise RuntimeError("pilot_native_receipt_limit")
    checked = harbor_collection(
        native.get("collection", {}).get("entries"), required=["agent-output.json"]
    )
    sealed = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    if (
        native.get("harness") != "harbor-0.25.0-host-mediated-components-v1"
        or native.get("native_container_isolation") is not True
        or native.get("diagnostic_reward_purpose") != "collection_custody_only"
        or not checked["complete"]
        or native["collection"]["entries"][0]["sha256"] != receipt["output_sha256"]
        or digest(native["trusted_receipt"]) != digest(receipt)
        or native.get("separate_verifier_bytes_sha256") != sealed
    ):
        raise RuntimeError("pilot_native_custody_mismatch")


def finish(claim):
    with transaction(claim.project_id, claim.actor_id) as c:
        planned = harbor_agents.plan(c, claim.plan_id)
        if planned["config"].get("golden_kyc_paid"):
            from anvil.golden_kyc_paid_execution import finish as finish_golden

            return finish_golden(claim)
        if planned["config"].get("marketing_paid"):
            from anvil.marketing_paid_execution import finish as finish_marketing

            return finish_marketing(claim)
    if getattr(claim, "effect_key", None):
        from anvil.workflow_native_execution import complete

        return complete(claim)
    if len(json.dumps(claim.native, allow_nan=False).encode()) > 1048576 or claim.stage_index != 0:
        raise RuntimeError("pilot_native_receipt_limit")
    with transaction(claim.project_id, claim.actor_id) as c:
        project_fence(c, claim.project_id)
        authorize(c, claim)
        plan = harbor_agents.plan(c, claim.plan_id)
        workspace_execution.group(c, plan["config"]["workspace_execution_group"], True)
        plan = harbor_agents.plan(c, claim.plan_id, True)
        check = one(
            c, "SELECT * FROM anvil.harbor_checks WHERE id=%s FOR UPDATE", (plan["check_id"],)
        )
        if check["cancel_requested"] or not workspace_execution.plan_readiness(c, plan)["ready"]:
            raise RuntimeError("pilot_native_authority_revoked")
        receipt = capture_receipt(c, claim)
        native = claim.native
        verify_capture(native, receipt)
        call = one(c, "SELECT * FROM anvil.harbor_agent_calls WHERE id=%s", (receipt["call_id"],))
        output = output_value(call["output_json"]["text"])
        package, task = source(c, plan)
        diagnostic = grade(task, output)
        mock = receipt["dispatch_origin"] == "sdk_mock"
        evidence = json.dumps(
            {
                "capture": receipt,
                "native": {k: v for k, v in native.items() if k != "trusted_receipt"},
                "output": output,
            },
            allow_nan=False,
        ).encode()
        aid = artifacts.store(
            c,
            claim.project_id,
            evidence,
            "internal",
            mime="application/json",
            origin="illustrative" if mock else "adi_executed",
        )
        result = {
            "origin": "native_sdk_mock_verification" if mock else "live_model_unreviewed",
            "model_performance": not mock,
            "mock_execution": mock,
            "model": plan["config"]["workspace_model"]["model_id"],
            "agent_plan_id": str(plan["id"]),
            "harbor_version": "0.25.0",
            "package_sha256": package["package_sha256"],
            "candidate": "agent",
            "diagnostics": diagnostic,
            "evidence": [
                {
                    "artifact_id": str(aid),
                    "kind": "structured-native-capture",
                    "sha256": hashlib.sha256(evidence).hexdigest(),
                }
            ],
            "provider_calls": 0 if mock else 1,
            "native_harbor": {k: v for k, v in native.items() if k != "trusted_receipt"},
            "trajectory": "Single public structured decision; no private reasoning inferred",
            "analysis": "Original Task rubric; human review pending",
        }
        c.execute(
            "UPDATE anvil.harbor_checks SET state='succeeded',result=%s,finished_at=now() WHERE id=%s AND state='running'",
            (Jsonb(result), check["id"]),
        )
        c.execute(
            "UPDATE anvil.jobs SET status='succeeded' WHERE id=%s AND lease_token=%s",
            (claim.job_id, claim.lease_token),
        )
        audit(
            c,
            claim.project_id,
            claim.actor_id,
            "harbor.check_succeeded",
            check["id"],
            {
                "origin": result["origin"],
                "model_performance": not mock,
                "api_private_grading": True,
            },
        )
    return {"status": "recorded", "private_source_to_worker": False}
