"""Credential/reference-free pilot coordinator for host-mediated native custody."""

import hashlib
import json
import os

from anvil.db import one, transaction
from anvil.environment_structured_agent import output_value
from anvil.worker_dispatch_broker import forward


def process(job, user):
    from anvil import harbor_worker
    from anvil.environment_harbor import execute as native_execute
    from anvil.pilot_concurrency import limit, native_slot, recover_native

    with transaction(job["project_id"], user, worker=True) as c:
        row = one(
            c, "SELECT agent_plan_id FROM anvil.harbor_checks WHERE id=%s", (job["target_id"],)
        )
    if not row or not row["agent_plan_id"]:
        raise RuntimeError("pilot_native_plan_required")
    plan = row["agent_plan_id"]

    def execute(*args, **kwargs):
        with native_slot(job, user, args[0]):
            return native_execute(*args, **kwargs)

    try:
        folder = harbor_worker.check_workspace(job["target_id"])
        if folder.exists():
            if (
                folder.resolve() != folder
                or folder.stat().st_uid != os.getuid()
                or folder.stat().st_mode & 0o077
            ):
                raise RuntimeError("pilot_private_workspace_required")
        recover_native(job, user, folder)
        prepared = forward(job, user, plan, 0, operation="prepare")
        if prepared.get("status") in {"cancelled", "expired", "unknown"}:
            return
        folder.mkdir(mode=0o700, parents=True, exist_ok=prepared.get("mode") == "workflow")
        if (
            folder.resolve() != folder
            or folder.stat().st_uid != os.getuid()
            or folder.stat().st_mode & 0o077
        ):
            raise RuntimeError("pilot_private_workspace_required")
        if prepared.get("mode") == "workflow":
            process_graph(job, user, plan, folder, prepared, execute, workers=limit())
            return

        def act_and_collect():
            text = forward(job, user, plan, 0, remaining_seconds=prepared["remaining_seconds"])
            output = output_value(text)
            receipt = forward(job, user, plan, 0, operation="capture")
            if (
                receipt["output_sha256"]
                != hashlib.sha256(json.dumps(output, allow_nan=False).encode()).hexdigest()
            ):
                raise RuntimeError("pilot_capture_binding_changed")
            return output, receipt

        native = execute(
            folder / "attempt",
            {
                "task_id": prepared["task_id"],
                "source_sha256": prepared["source_sha256"],
                "origin": "guarded_structured_model_actor",
            },
            act_and_collect,
            host=os.environ["ANVIL_HARBOR_DOCKER_HOST"],
            python=os.environ["ANVIL_ENVIRONMENT_HARBOR_PYTHON"],
        )
        forward(job, user, plan, 0, operation="finish", native=native)
    except Exception:
        with transaction(job["project_id"], user, worker=True) as c:
            current = one(c, "SELECT status,lease_token FROM anvil.jobs WHERE id=%s", (job["id"],))
            if (
                not current
                or current["status"] != "leased"
                or str(current["lease_token"]) != str(job["lease_token"])
            ):
                return
            pending = one(
                c,
                "SELECT 1 FROM anvil.harbor_agent_calls WHERE plan_id=%s AND status IN('dispatching','execution_unknown') LIMIT 1",
                (plan,),
            )
        harbor_worker.finish(
            job,
            user,
            "execution_unknown" if pending else "failed",
            error="pilot_broker_or_native_outcome_unverified",
            live=True,
        )


def process_graph(job, user, plan, folder, prepared, execute, *, workers=1):
    from concurrent.futures import ThreadPoolExecutor

    # The API schedules, projects and verifies; worker never accepts graph state
    # mutation or sends a custom prompt/model/credential to the broker.
    def node(claim):
        index, key = claim["stage_index"], claim["effect_key"]

        def act():
            text = forward(
                job,
                user,
                plan,
                index,
                effect_key=key,
                remaining_seconds=prepared["remaining_seconds"],
            )
            output = output_value(text)
            receipt = forward(job, user, plan, index, effect_key=key, operation="capture")
            if (
                receipt["output_sha256"]
                != hashlib.sha256(json.dumps(output, allow_nan=False).encode()).hexdigest()
            ):
                raise RuntimeError("workflow_native_output_changed")
            return output, receipt

        native = execute(
            folder / hashlib.sha256(key.encode()).hexdigest(),
            {
                "task_id": prepared["task_id"],
                "source_sha256": prepared["source_sha256"],
                "origin": "guarded_workflow_role_actor",
                "node_id": claim["node_id"],
            },
            act,
            host=os.environ["ANVIL_HARBOR_DOCKER_HOST"],
            python=os.environ["ANVIL_ENVIRONMENT_HARBOR_PYTHON"],
        )
        forward(job, user, plan, index, effect_key=key, operation="finish", native=native)

    for _ in range(10001):
        wave = forward(job, user, plan, 0, operation="wave")
        if wave["status"] != "running":
            return
        claims = wave["claims"]
        if not isinstance(claims, list) or not 1 <= len(claims) <= 100:
            raise RuntimeError("workflow_wave_limit")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(node, claims))
    raise RuntimeError("workflow_transition_limit")
