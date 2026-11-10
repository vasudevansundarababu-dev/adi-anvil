"""Preloaded Harbor custody for existing guarded structured-decision plans.

Provider calls remain in workspace_execution.decision, with its durable intent,
rights, credential, budget and Unknown controls. No SDK or credential enters the
actor. This adapter does not invent component-world bindings for source Tasks.
"""

import hashlib
import json
import os

from anvil import artifacts
from anvil.db import digest, one
from anvil.praxis_contract import PraxisTask, grade
from anvil.task_parser import json_value


def source_task(raw, manifest):
    if (
        manifest.get("binding") != "structured-decision-v1"
        or manifest.get("schema_version") != "praxis.anvil.task.v1"
        or hashlib.sha256(raw).hexdigest() != manifest.get("source_sha256")
    ):
        raise ValueError("Exact supported structured source required")
    task = PraxisTask.model_validate_json(raw)
    if task.task_id != manifest["task_id"] or task.task_version != manifest["task_version"]:
        raise ValueError("Structured source identity changed")
    return task


def output_value(text):
    if not isinstance(text, str) or not 0 < len(text.encode()) <= 65536:
        raise ValueError("Bounded structured output required")
    value = json_value(text.encode())
    if not isinstance(value, dict):
        raise ValueError("A single JSON object is required")
    return value


def process(job, user, row, package, *, transport=None):
    from anvil import harbor_agents, harbor_worker
    from anvil.environment_harbor import execute

    if os.environ.get("ANVIL_HARBOR_HOST_MEDIATED_STRUCTURED_ENABLED") != "true":
        raise RuntimeError("harbor_runtime_unavailable")
    if row["candidate"] != "agent":
        # This path is solely the existing admitted model plan; no source-answer
        # fixtures are substituted for a model invocation.
        raise RuntimeError("harbor_runtime_unavailable")
    with harbor_worker.scoped(job, user) as c:
        harbor_worker.lease(c, job)
        current = harbor_worker.authorized(c, job, user)
        if current["cancel_requested"] or current["invocation_count"]:
            raise RuntimeError("live_agent_gates_revoked")
        record = harbor_agents.plan(c, row["agent_plan_id"])
        if not record["config"].get("workspace_execution_group") or str(record["check_id"]) != str(
            row["id"]
        ):
            raise RuntimeError("live_agent_gates_revoked")
        source = one(c, "SELECT * FROM anvil.praxis_sources WHERE id=%s", (package["source_id"],))
        task = source_task(artifacts.read(c, source["source_artifact_id"]), package["manifest"])
        if one(
            c, "SELECT 1 FROM anvil.harbor_agent_calls WHERE plan_id=%s LIMIT 1", (record["id"],)
        ):
            raise RuntimeError("live_agent_gates_revoked")
        c.execute(
            "UPDATE anvil.harbor_checks SET state='running',started_at=now(),invocation_count=1 WHERE id=%s",
            (row["id"],),
        )
        # Native custody has a hard 180s deadline. Renew only our still-owned
        # lease beyond that bound; a crash is retained, never auto-dispatched.
        c.execute(
            "UPDATE anvil.jobs SET lease_until=now()+interval '240 seconds' WHERE id=%s AND lease_token=%s AND status='leased'",
            (job["id"], job["lease_token"]),
        )
    folder = harbor_worker.check_workspace(row["id"])
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    if (
        folder.resolve() != folder
        or folder.stat().st_uid != os.getuid()
        or folder.stat().st_mode & 0o077
    ):
        raise ValueError("Canonical private structured workspace required")
    captured = {}

    def act_and_collect():
        from anvil.workspace_execution import decision

        with harbor_worker.scoped(job, user) as c:
            harbor_worker.lease(c, job)
            current = harbor_worker.authorized(c, job, user)
            if current["cancel_requested"]:
                raise RuntimeError("cancelled")
            c.execute(
                "UPDATE anvil.jobs SET lease_until=now()+interval '240 seconds' WHERE id=%s AND lease_token=%s AND status='leased'",
                (job["id"], job["lease_token"]),
            )
        # No custom prompt or secret injection: the broker reconstructs the
        # original public actor projection from the exact admitted package.
        text = decision(
            job["project_id"],
            user,
            record["id"],
            0,
            transport=transport,
            remaining_seconds=min(120, record["config"]["episode_timeout_seconds"]),
        )
        output = output_value(text)
        with harbor_worker.scoped(job, user) as c:
            current = harbor_worker.authorized(c, job, user)
            if current["cancel_requested"]:
                raise RuntimeError("cancelled")
            call = one(
                c,
                "SELECT * FROM anvil.harbor_agent_calls WHERE plan_id=%s AND stage_index=0",
                (record["id"],),
            )
            if not call or call["status"] != "completed" or call["output_json"]["text"] != text:
                raise RuntimeError("live_agent_gates_revoked")
            origin = call["usage"].get("dispatch_origin")
            if origin not in {"provider", "sdk_mock"}:
                raise RuntimeError("live_agent_gates_revoked")
            harbor_worker.lease(c, job)
            c.execute(
                "UPDATE anvil.jobs SET lease_until=now()+interval '240 seconds' WHERE id=%s AND lease_token=%s AND status='leased'",
                (job["id"], job["lease_token"]),
            )
        receipt = {
            "schema_version": "anvil.structured-model-capture.v1",
            "source_sha256": package["manifest"]["source_sha256"],
            "package_sha256": package["package_sha256"],
            "plan_id": str(record["id"]),
            "call_id": str(call["id"]),
            "dispatch_origin": origin,
            "output_sha256": hashlib.sha256(
                json.dumps(output, allow_nan=False).encode()
            ).hexdigest(),
        }
        captured.update(output=output, receipt=receipt, origin=origin)
        return output, receipt

    native = execute(
        folder / "attempt",
        {
            "task_id": task.task_id,
            "source_sha256": package["manifest"]["source_sha256"],
            "origin": "guarded_structured_model_actor",
        },
        act_and_collect,
        host=os.environ["ANVIL_HARBOR_DOCKER_HOST"],
        python=os.environ["ANVIL_ENVIRONMENT_HARBOR_PYTHON"],
    )
    if native["collection"]["entries"][0]["sha256"] != captured["receipt"]["output_sha256"]:
        raise RuntimeError("verifier_evidence_mismatch")
    if digest(native["trusted_receipt"]) != digest(captured["receipt"]):
        raise RuntimeError("verifier_evidence_mismatch")
    diagnostic = grade(task, captured["output"])
    mock = captured["origin"] == "sdk_mock"
    evidence_bytes = json.dumps(
        {
            "capture": captured["receipt"],
            "native": {k: v for k, v in native.items() if k != "trusted_receipt"},
            "output": captured["output"],
        },
        allow_nan=False,
    ).encode()
    with harbor_worker.scoped(job, user) as c:
        aid = artifacts.store(
            c,
            job["project_id"],
            evidence_bytes,
            "internal",
            mime="application/json",
            origin="illustrative" if mock else "adi_executed",
        )
    result = {
        "origin": "native_sdk_mock_verification" if mock else "live_model_unreviewed",
        "model_performance": not mock,
        "mock_execution": mock,
        "model": record["config"]["workspace_model"]["model_id"],
        "agent_plan_id": str(record["id"]),
        "harbor_version": "0.25.0",
        "package_sha256": package["package_sha256"],
        "candidate": "agent",
        "diagnostics": diagnostic,
        "evidence": [
            {
                "artifact_id": str(aid),
                "kind": "structured-native-capture",
                "sha256": hashlib.sha256(evidence_bytes).hexdigest(),
            }
        ],
        "provider_calls": 0 if mock else 1,
        "native_harbor": {k: v for k, v in native.items() if k != "trusted_receipt"},
        "trajectory": "Single public structured decision; no private reasoning inferred",
        "analysis": "Original Task rubric; human review pending",
    }
    harbor_worker.finish(job, user, "succeeded", result, live=True)
