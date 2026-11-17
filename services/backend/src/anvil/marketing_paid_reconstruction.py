"""Read-only reconstruction from private SQL records, never effect replay.

The private API/grader must load these records from scoped immutable SQL and
verify native seals separately. This module accepts no worker completion flag,
never calls an adapter/journal/tool/SDK and grants no score or run authority.
"""

from copy import deepcopy

from anvil.campaign_semantic_contract import bounded_json
from anvil.db import digest
from anvil.marketing_paid_world import Attachment, Effect, OpeningEffect
from anvil.marketing_paid_world import released as decode_release
from anvil.marketing_task2_workflow import advance, initial, initial_opening
from anvil.praxis_generic_contract import digest as wire_digest
from anvil.praxis_marketing_contract import MarketingExecution


class MissingRecordedEffect(Exception):
    """A partial or uncertain attempt cannot supply a completed transition."""


def load_turns(connection, project, plan):
    """Only the private grader has SQL permission; NULL is broken custody."""
    rows = connection.execute(
        "SELECT marketing_runtime.reconstruction_turns(%s,%s) AS value", (project, plan)
    ).fetchall()
    if len(rows) > 1000 or any(type(row["value"]) is not dict for row in rows):
        raise ValueError("Complete actual turn custody projection required")
    return [row["value"] for row in rows]


def release_artifact(record):
    release = decode_release(record)
    result = {
        "week": release.week,
        "released_at": release.released_at.isoformat(),
        "window_ref": release.window_ref,
        "evidence_refs": release.evidence_refs,
        "world_receipt_ref": str(release.receipt_id) + ":" + release.receipt_sha256,
    }
    if release.week == 0:
        result.update(phase=release.phase, operator_program_id=release.operator_program_id)
    if hasattr(release, "baseline_delivery_manifest"):
        result["baseline_delivery_manifest"] = (
            release.baseline_delivery_manifest.model_dump(mode="json") if release.baseline_delivery_manifest is not None else None
        )
    return result


def reconstruct(execution, attachment, releases, effects, turns, *, opening_required=False):
    """SQL-loader inputs only; hashes validate bytes, not their provenance.

    `turns` is the narrow grader-only completed-turn custody projection, not raw
    model output. Missing/unknown effects produce partial state. Extra effects,
    cross-scope records and altered receipts fail rather than being ignored.
    The result must still be joined to actual independent native collection.
    """
    bounded_json([execution, attachment, releases, effects, turns], 33554432, max_nodes=300000)
    contract = MarketingExecution.model_validate(execution)
    bound = Attachment.model_validate(attachment)
    if wire_digest(contract.model_dump()) != bound.execution_sha256:
        raise ValueError("Reconstruction requires exact published execution")
    if any(type(value) is not list for value in (releases, effects, turns)) or (
        len(releases) > (13 if opening_required else 12) or len(effects) > 400 or len(turns) > 1000
    ):
        raise ValueError("Bounded complete SQL record populations required")
    nodes = {node["id"]: node for node in contract.workflow_graph["nodes"]}
    windows, journal, proof, used_effects, used_turns = {}, {}, {}, set(), set()
    for item in releases:
        row = decode_release(item)
        if (
            any(
                getattr(row, name) != getattr(bound, name)
                for name in (
                    "world_binding_id",
                    "world_binding_sha256",
                    "episode_id",
                    "generation",
                    "case_id",
                    "case_snapshot_sha256",
                )
            )
            or row.week in windows or (row.week == 0 and not opening_required)
        ):
            raise ValueError("Exact unique world release scope required")
        windows[row.week] = release_artifact(item)
    for row in effects:
        if (
            str(row["project_id"]) != str(bound.project_id)
            or str(row["episode_id"]) != str(bound.episode_id)
            or type(row["generation"]) is not int
            or row["generation"] != bound.generation
            or row["execution_sha256"] != bound.execution_sha256
            or row["node_id"] not in nodes
            or type(row["week"]) is not int
            or not (0 if opening_required else 1) <= row["week"] <= 12
            or type(row["visit"]) is not int
            or not 1 <= row["visit"] <= 400
            or row["state"] not in {"claimed", "execution_unknown", "completed"}
        ):
            raise ValueError("Exact SQL workflow effect scope required")
        key = (row["node_id"], row["week"], row["visit"])
        if key in journal or row["node_sha256"] != digest(nodes[row["node_id"]]):
            raise ValueError("Unique immutable workflow effect identity required")
        journal[key] = row
    for row in turns:
        if (
            str(row["project_id"]) != str(bound.project_id)
            or str(row["plan_id"]) != str(bound.plan_id)
            or str(row["job_id"]) != str(bound.job_id)
            or str(row["episode_id"]) != str(bound.episode_id)
            or type(row["generation"]) is not int
            or row["generation"] != bound.generation
            or type(row["stage_index"]) is not int
            or not 0 <= row["stage_index"] < 1000
            or row["origin"] not in {"provider", "sdk_mock"}
            or row["observation_sha256"] != digest(row["observation"])
            or row["stage_index"] in proof
        ):
            raise ValueError("Exact immutable completed turn custody required")
        proof[row["stage_index"]] = row
    if sorted(proof) != list(range(len(proof))):
        raise ValueError("Complete contiguous completed-turn population required")

    def released(week):
        if week not in windows:
            raise MissingRecordedEffect("world_window_not_recorded")
        return deepcopy(windows[week])

    def effect(node, inputs, week, visit):
        key = (node["id"], week, visit)
        row = journal.get(key)
        if row is None:
            raise MissingRecordedEffect("workflow_effect_not_recorded")
        used_effects.add(key)
        if row["input_sha256"] != digest(inputs):
            raise ValueError("Recorded effect input differs from reconstructed state")
        if row["state"] != "completed":
            raise MissingRecordedEffect("workflow_effect_" + row["state"])
        result = row["result"]
        bounded_json(result, 60000, max_nodes=10000)
        if row["result_sha256"] != digest(result) or result["receipt"]["input_sha256"] != digest(
            inputs
        ):
            raise ValueError("Recorded workflow result custody changed")
        if node["type"] == "agent_step":
            stages = sorted(
                index for index, turn in proof.items() if str(turn["effect_id"]) == str(row["id"])
            )
            if not stages:
                raise ValueError("Completed agent effect lacks actual completed turn custody")
            for index in stages:
                turn = proof[index]
                if turn["role"] != node["roleId"]:
                    raise ValueError("Completed turn belongs to another assigned role")
                if turn["observation"]["completed_node"] is not (index == stages[-1]):
                    raise ValueError("Exactly one final node artifact is required")
            last = proof[stages[-1]]
            receipt = result["receipt"]
            if (
                receipt.get("origin") != "completed_broker_and_tool_receipts"
                or receipt.get("role") != node["roleId"]
                or receipt.get("stage_index") != stages[-1]
                or str(receipt.get("physical_call_id")) != str(last["call_id"])
                or receipt.get("observation_sha256") != last["observation_sha256"]
                or result.get("artifact") != last["observation"].get("artifact")
            ):
                raise ValueError("Actual final role artifact and completed call must agree")
            used_turns.update(stages)
        else:
            actual = (OpeningEffect if opening_required and week == 0 else Effect).model_validate(result)
            if (
                actual.receipt.world_binding_sha256 != bound.world_binding_sha256
                or actual.receipt.episode_id != bound.episode_id
                or actual.receipt.generation != bound.generation
                or actual.receipt.node_id != node["id"]
                or actual.receipt.week != week
                or actual.receipt.visit != visit
            ):
                raise ValueError("Persisted world effect differs from exact reconstructed scope")
        return deepcopy(result)

    partial_reason = None
    state = None
    try:
        state = (initial_opening(bound.campaign_context.model_dump(mode="json"), released(0))
                 if opening_required else initial(bound.campaign_context.model_dump(mode="json"), released(1)))
        for _ in range(contract.workflow_graph["limits"]["maxTransitions"] + 1):
            if state["terminal"]:
                break
            state = advance(execution, state, effect, released)
        if not state["terminal"]:
            raise ValueError("Reconstruction exceeded published transition bound")
    except MissingRecordedEffect as missing:
        partial_reason = str(missing)
    if set(journal) != used_effects:
        raise ValueError("Stored effects exist outside the actual reconstructed path")
    # Completed turns of an uncertain current effect are retained as partial
    # evidence, never relabelled as a successfully closed role.
    remaining = [row for index, row in proof.items() if index not in used_turns]
    if any(
        not any(
            str(effect["id"]) == str(row["effect_id"]) and effect["state"] != "completed"
            for effect in journal.values()
        )
        for row in remaining
    ):
        raise ValueError("Completed turns exist outside recorded workflow effects")
    done = state is not None and state["terminal"] == "done" and partial_reason is None
    role_status = {}
    for role in contract.workflow_graph["roles"]:
        role_id = role["id"]
        observed = any(row["role"] == role_id for row in proof.values())
        role_status[role_id] = (
            "closed"
            if done and observed
            else ("unscheduled" if done else "partial" if observed else "not_yet_exercised")
        )
    body = {
        "schema_version": ("anvil.marketing-workflow-reconstruction.v2" if opening_required
                           else "anvil.marketing-workflow-reconstruction.v1"),
        "attachment_sha256": wire_digest(bound.model_dump(mode="json")),
        "execution_sha256": bound.execution_sha256,
        "state": state,
        "state_sha256": wire_digest(state),
        "workflow_status": "closed"
        if done
        else "partial"
        if partial_reason
        else "hold_requires_qualification",
        "partial_reason": partial_reason,
        "role_status": role_status,
        "effect_ids": sorted(str(row["id"]) for row in journal.values()),
        "turn_stages": sorted(proof),
        "model_origins": sorted({row["origin"] for row in proof.values()}),
        "native_collection_required": True,
        "model_performance_validated": False,
        "qualification": "Private SQL loader and native seals must be verified separately; hashes alone are not authority",
    }
    return body | {"reconstruction_sha256": wire_digest(body)}
