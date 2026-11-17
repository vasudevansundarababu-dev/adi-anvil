"""Recorded-path-only release of baseline windows; no candidate clock control.

Conditional services/branch activation require their own qualified producer.
This module never treats reaching a date as approval or experiment activation.
"""

import re
from datetime import timezone

from anvil.campaign_semantic_contract import bounded_json
from anvil.db import uid
from anvil.marketing_paid_reconstruction import reconstruct
from anvil.marketing_paid_world import Attachment, released
from anvil.marketing_task2_persistence import freeze
from anvil.marketing_task2_runtime import timestamp
from anvil.praxis_generic_contract import canonical, digest


def inventory_refs(receipt_id, inventory):
    if type(inventory) is not list or len(inventory) > 50:
        raise ValueError("Bounded complete released collection inventory required")
    names, references = set(), []
    for item in inventory:
        if (
            type(item) is not dict
            or set(item) != {"collection", "record_count", "records_sha256"}
            or type(item["collection"]) is not str
            or not 1 <= len(item["collection"]) <= 100
            or item["collection"] in names
            or type(item["record_count"]) is not int
            or item["record_count"] < 0
            or type(item["records_sha256"]) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", item["records_sha256"])
        ):
            raise ValueError("Exact distinct released collection index required")
        names.add(item["collection"])
        references.append(
            "anvil-world-release-index:"
            + str(receipt_id)
            + ":"
            + item["collection"]
            + ":"
            + item["records_sha256"]
        )
    return sorted(references)


def recorded(connection, claim, row, execution):
    from anvil.marketing_world_service_api import records

    raw = connection.execute(
        "SELECT marketing_runtime.private_world_graph_records(%s,%s,%s) AS value",
        (claim.job_id, claim.lease_token, claim.plan_id),
    ).fetchone()["value"]
    if raw is not None:
        raw["service_records"] = records(connection, claim)
    return recorded_records(raw, row, execution)


def recorded_records(raw, row, execution):
    """Validate records from a locked private API projection without replay."""
    if not raw or raw["attachment"] != row["attachment"]:
        raise ValueError("Actual current private world graph records required")
    bounded_json(raw, 33554432, max_nodes=300000)
    if "service_records" in raw:
        from anvil.marketing_world_service_api import verify_records

        verify_records(raw, execution, raw["service_records"])
    elif any(e["state"] == "completed" and e["node_id"] in {
        n["id"] for n in execution["workflow_graph"]["nodes"] if n["type"] in {"human_step", "external_system"}
    } for e in raw["effects"]):
        raise ValueError("Actual API service return proof is missing")
    if any(type(turn) is not dict for turn in raw["turns"]):
        raise ValueError("Complete actual completed-turn custody required")
    releases = []
    for item in raw["releases"]:
        reply = item["reply"]
        if (
            digest(reply) != item["reply_sha256"]
            or digest({key: value for key, value in reply.items() if key != "receipt_sha256"})
            != reply["receipt_sha256"]
        ):
            raise ValueError("Immutable actual released-window receipt custody required")
        if sorted(reply["evidence_refs"]) != inventory_refs(reply["receipt_id"], item["inventory"]):
            raise ValueError("Actual released collection index custody required")
        releases.append(reply)
    opening_required = raw.get("operator_program_id") == "marketing-opening0-and-twelve-reviews-v1"
    result = reconstruct(execution, raw["attachment"], releases, raw["effects"], raw["turns"], opening_required=opening_required)
    return result, raw


def release(connection, claim, row, controller, world, execution):
    week = claim.value["week"]
    if week != row["last_week"] + 1:
        raise ValueError("Exactly the next unreleased world window required; no replay")
    result, raw = recorded(connection, claim, row, execution)
    opening_required = world.schema_version in {"anvil.marketing-private-world-definition.v5", "anvil.marketing-private-world-definition.v6"}
    if opening_required and raw.get("operator_program_id") != world.operator_program_id:
        raise ValueError("Actual opening program missing from private graph records")
    if week == 1 and not opening_required:
        if raw["effects"] or raw["turns"] or raw["releases"]:
            raise ValueError("Fresh actual world required before the first window")
    elif (
        result["partial_reason"] != "world_window_not_recorded"
        or result["state"] is None
        or result["state"]["week"] != week - 1
        or result["state"]["completed"].get("weekly", []) != list(range(0 if opening_required else 1, week))
        or len(raw["releases"]) != week - (0 if opening_required else 1)
    ):
        raise ValueError("Actual completed prior weekly path required before advancing")
    window = world.windows[week - 1]
    from anvil.marketing_world_campaign_release import prepare as prepare_campaign_release

    advanced = prepare_campaign_release(controller, world, window.instant.isoformat())
    if advanced is not None:
        controller = advanced
    controller.control(
        controller.controller_credential(),
        controller.generation,
        "advance",
        {"instant": window.instant.isoformat()},
        idempotency_key="anvil-world-window:" + str(week),
    )
    # Only baseline or already independently activated records can exist here.
    # Actual private alternatives are never copied into the controller by this
    # release function, even if their timestamps have passed.
    inventory = []
    for name, records in sorted(controller._initial.items()):
        released_records = sorted(
            [
                {
                    "id": record["public"]["id"],
                    "public_sha256": digest(record["public"]),
                    "released_at": record["released_at"],
                }
                for record in records
                if record.get("actor_visible") is True
                and record.get("outcome_binding") in (None, controller._outcome)
                and timestamp(record["released_at"]) <= timestamp(controller._clock)
            ],
            key=lambda value: value["id"],
        )
        inventory.append(
            {
                "collection": name,
                "record_count": len(released_records),
                "records_sha256": digest(released_records),
            }
        )
    receipt_id = uid()
    refs = inventory_refs(receipt_id, inventory)
    bound = Attachment.model_validate(row["attachment"])
    body = {
        "schema_version": "anvil.marketing-world-release.v1",
        **{
            key: bound.model_dump(mode="json")[key]
            for key in (
                "world_binding_id",
                "world_binding_sha256",
                "episode_id",
                "generation",
                "case_id",
                "case_snapshot_sha256",
            )
        },
        "week": week,
        "released_at": timestamp(controller._clock)
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "window_ref": window.window_ref,
        "evidence_refs": refs,
        "receipt_id": receipt_id,
    }
    if getattr(world, "service_contract", None) is not None:
        from anvil.marketing_world_services import baseline_manifest

        body["schema_version"] = "anvil.marketing-world-release.v2"
        body["baseline_delivery_manifest"] = baseline_manifest(controller, world.service_contract, row["attachment"], week)
    body["receipt_sha256"] = digest(body)
    reply = released(body).model_dump(mode="json")
    state, fingerprint = freeze(controller)
    commit = ("SELECT marketing_runtime.commit_private_world_campaign_release(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS allowed"
              if advanced is not None else
              "SELECT marketing_runtime.commit_private_world_release(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS allowed")
    if not connection.execute(
        commit,
        (
            claim.job_id,
            claim.lease_token,
            claim.plan_id,
            row["controller_state_sha256"],
            week,
            canonical(state).decode(),
            fingerprint,
            canonical(reply).decode(),
            digest(reply),
            canonical(inventory).decode(),
        ),
    ).fetchone()["allowed"]:
        raise RuntimeError("marketing_world_release_commit_unconfirmed_no_replay")
    return reply
