"""Private API world operations; no provider dispatch or actor-selected source.

All calls require current native/source/rights qualification and the exact leased
parent job. Unfinished release/effect/finalization paths remain explicitly closed.
"""

import asyncio
import os
from uuid import UUID

from anvil.db import project_fence, transaction, uid
from anvil.marketing_paid_execution import admitted
from anvil.marketing_paid_state import effect_view
from anvil.marketing_paid_world import Attachment, WorldCall
from anvil.marketing_task2_persistence import freeze, restore
from anvil.marketing_task2_tools import execute
from anvil.marketing_world_registry import load
from anvil.marketing_world_role import RoleView, ToolReply
from anvil.praxis_generic_contract import canonical, digest


def allocate(connection, claim, plan, world, source, qualification):
    trial = plan["config"].get("trial")
    if type(trial) is not int or not 1 <= trial <= 1000:
        raise RuntimeError("marketing_explicit_frozen_case_repetition_required")
    controller = world.controller(trial - 1)
    state, fingerprint = freeze(controller)
    native = plan["config"]["marketing_native_binding"]
    public = {
        "schema_version": "anvil.marketing-world-attachment.v1",
        "project_id": str(claim.project_id),
        "actor_id": str(claim.actor_id),
        "job_id": str(claim.job_id),
        "plan_id": str(claim.plan_id),
        "world_binding_id": uid(),
        "episode_id": controller.trial_id,
        "generation": controller.generation,
        "case_id": world.case_id,
        "case_snapshot_sha256": world.case_snapshot_sha256,
        "execution_sha256": world.execution_sha256,
        "native_binding_sha256": digest(native),
        "source_manifest_sha256": world.source_manifest_sha256,
        "dataset_qualification_sha256": native["dataset_qualification"]["receipt_sha256"],
        "rights_receipt_sha256": world.rights_receipt_sha256,
        "campaign_context": world.campaign_context.model_dump(mode="json"),
    }
    public["world_binding_sha256"] = digest(
        {
            "attachment": public,
            "source_definition_sha256": source["definition_sha256"],
            "source_id": str(source["id"]),
            "world_qualification_sha256": qualification["receipt_sha256"],
            "repeat_index": trial - 1,
        }
    )
    attachment = Attachment.model_validate(public).model_dump(mode="json")
    allowed = connection.execute(
        "SELECT marketing_runtime.create_private_world_session(%s,%s,%s,%s,%s,%s,%s,%s) AS allowed",
        (
            claim.job_id,
            claim.lease_token,
            claim.plan_id,
            source["id"],
            qualification["id"],
            canonical(attachment).decode(),
            canonical(state).decode(),
            fingerprint,
        ),
    ).fetchone()["allowed"]
    if not allowed:
        raise RuntimeError("marketing_world_attach_denied_no_replay")
    return attachment


def attach(connection, claim, world, source, qualification):
    """Read the once-prepared world; never allocate/reset during native start."""
    row = connection.execute(
        "SELECT marketing_runtime.private_world_session(%s,%s,%s) AS value",
        (claim.job_id, claim.lease_token, claim.plan_id),
    ).fetchone()["value"]
    if (
        not row
        or str(row["source_id"]) != str(source["id"])
        or str(row["qualification_id"]) != str(qualification["id"])
    ):
        raise RuntimeError("marketing_exact_prepared_world_required")
    attachment = Attachment.model_validate(row["attachment"])
    if (
        attachment.project_id != claim.project_id
        or attachment.actor_id != claim.actor_id
        or attachment.job_id != claim.job_id
        or attachment.plan_id != claim.plan_id
        or attachment.case_id != world.case_id
        or attachment.case_snapshot_sha256 != world.case_snapshot_sha256
    ):
        raise ValueError("Exact server-prepared world attachment identity required")
    return attachment.model_dump(mode="json")


def session(connection, claim, world, source, qualification):
    if claim.operation == "role_tool":
        row = connection.execute(
            "SELECT marketing_runtime.private_world_session_for_existing_tool(%s,%s,%s,%s) AS value",
            (claim.job_id, claim.lease_token, claim.plan_id, UUID(claim.value["request_id"])),
        ).fetchone()["value"]
    else:
        row = connection.execute(
            "SELECT marketing_runtime.private_world_session(%s,%s,%s) AS value",
            (claim.job_id, claim.lease_token, claim.plan_id),
        ).fetchone()["value"]
    if (
        not row
        or str(row["source_id"]) != str(source["id"])
        or str(row["qualification_id"]) != str(qualification["id"])
    ):
        raise RuntimeError("marketing_current_private_world_session_required")
    for name in ("world_binding_id", "episode_id"):
        if UUID(claim.value[name]) != UUID(row[name]):
            raise ValueError("Actual bound world identity required")
    if (
        claim.value["generation"] != row["generation"]
        or claim.value["world_binding_sha256"] != row["world_binding_sha256"]
    ):
        raise ValueError("Actual bound world generation and source required")
    controller = restore(row["controller_state"], row["controller_state_sha256"])
    if (
        controller.trial_id != row["episode_id"]
        or controller.generation != row["generation"]
        or controller.case_id != world.case_id
    ):
        raise ValueError("Private controller identity differs from actual world session")
    return row, controller


def role_view(row, role):
    attachment = Attachment.model_validate(row["attachment"])
    return RoleView(
        world_binding_id=attachment.world_binding_id,
        world_binding_sha256=attachment.world_binding_sha256,
        episode_id=attachment.episode_id,
        generation=attachment.generation,
        role=role,
        execution_sha256=attachment.execution_sha256,
        snapshot_sha256=attachment.case_snapshot_sha256,
        state_sha256=row["controller_state_sha256"],
    ).model_dump(mode="json")


def tool(connection, claim, row, controller, execution):
    value = claim.value
    context = connection.execute(
        "SELECT marketing_runtime.private_world_tool_context(%s,%s,%s,%s) AS value",
        (claim.job_id, claim.lease_token, claim.plan_id, UUID(value["request_id"])),
    ).fetchone()["value"]
    if (
        not context
        or context["session"]["controller_state_sha256"] != row["controller_state_sha256"]
    ):
        raise RuntimeError("marketing_actual_correlated_tool_intent_required")
    intent = context["intent"]
    if (
        intent["role"] != value["role"]
        or intent["operation"] != value["operation"]
        or digest(value["arguments"]) != intent["arguments_sha256"]
        or digest(intent["arguments"]) != intent["arguments_sha256"]
    ):
        raise ValueError("Actual leased model tool request must match before-effect intent")
    result = execute(controller, value["role"], value["operation"], value["arguments"], execution)
    after, fingerprint = freeze(controller)
    view = effect_view(after)
    result_hash = digest(result)
    allowed = connection.execute(
        "SELECT marketing_runtime.commit_private_world_tool(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS allowed",
        (
            claim.job_id,
            claim.lease_token,
            claim.plan_id,
            UUID(value["request_id"]),
            row["controller_state_sha256"],
            canonical(after).decode(),
            fingerprint,
            canonical(result).decode(),
            result_hash,
            canonical(view).decode(),
            digest(view),
        ),
    ).fetchone()["allowed"]
    if not allowed:
        raise RuntimeError("marketing_world_tool_commit_unconfirmed_no_replay")
    return ToolReply.model_validate(
        role_view(row | {"controller_state_sha256": fingerprint}, value["role"])
        | {
            "request_id": value["request_id"],
            "operation": value["operation"],
            "result": result,
            "result_sha256": result_hash,
        }
    ).model_dump(mode="json")


def dispatch(claim, *, after_response=None):
    claim = WorldCall.model_validate(claim)
    if claim.operation in {"fence", "drain", "quiescence"}:
        from anvil import pilot_environment
        from anvil.marketing_world_quiescence import dispatch as stop_dispatch

        if (
            pilot_environment.current() != "qa"
            or os.environ.get("ANVIL_MARKETING_WORLD_STOP_ENABLED") != "true"
        ):
            raise RuntimeError("marketing_world_stop_qa_api_disabled")
        if os.environ.get("ANVIL_MARKETING_NATIVE_CAPTURE_ENABLED") == "true":
            if claim.operation in {"fence", "drain"} and not callable(after_response):
                raise RuntimeError("API evidence requires after-response custody; no synchronous cleanup work")
            from anvil.marketing_capture_evidence_async import after_response as collect
            from anvil.marketing_capture_world_stop import dispatch as capture_stop

            original = claim.model_copy(deep=True)
            result, scheduled = asyncio.run(capture_stop(original))
            if scheduled is not None:
                async def callback():
                    await collect(original, scheduled)

                after_response(callback)
            return result
        # Legacy software-only path; never an error fallback from async capture.
        with transaction(claim.project_id, claim.actor_id) as connection:
            project_fence(connection, claim.project_id)
            return stop_dispatch(connection, claim)
    if os.environ.get("ANVIL_MARKETING_WORLD_ENABLED") != "true":
        raise RuntimeError("marketing_private_world_api_disabled")
    with transaction(claim.project_id, claim.actor_id) as connection:
        plan, context = admitted(connection, claim)
        world, source, qualification = load(connection, claim, plan)
        if claim.operation == "attach":
            return attach(connection, claim, world, source, qualification)
        if claim.operation == "effect":
            from anvil.marketing_world_service_api import effect

            return effect(connection, claim, world, source, qualification, context["execution"])
        row, controller = session(connection, claim, world, source, qualification)
        if claim.operation == "opening":
            from anvil.marketing_world_opening import opening

            return opening(connection, claim, row, controller, world, context["execution"])
        if claim.operation == "role_attach":
            return role_view(row, claim.value["role"])
        if claim.operation == "role_tool":
            return tool(connection, claim, row, controller, context["execution"])
        if claim.operation == "release":
            from anvil.marketing_world_release import release

            return release(connection, claim, row, controller, world, context["execution"])
        raise RuntimeError("marketing_private_world_release_effect_producer_unfinished")
