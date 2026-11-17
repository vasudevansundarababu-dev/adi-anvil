"""One recorded original opening release; never advance to later feedback."""

from anvil.db import uid
from anvil.marketing_paid_world import OpeningRelease
from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_world_opening_definition import OpeningWorldDefinition
from anvil.marketing_world_population_definition import PopulationWorldDefinition
from anvil.marketing_world_release import inventory_refs, recorded
from anvil.marketing_world_services import baseline_manifest
from anvil.praxis_generic_contract import canonical, digest


def opening(connection, claim, row, controller, world, execution):
    if (type(world) not in (OpeningWorldDefinition, PopulationWorldDefinition) or row["last_week"] != 0
            or timestamp(controller._clock) != world.opening.instant):
        raise ValueError("Exact original opening clock/source required; no reset or replay")
    _, raw = recorded(connection, claim, row, execution)
    if (raw.get("operator_program_id") != world.operator_program_id
            or raw["effects"] or raw["turns"] or raw["releases"]):
        raise ValueError("Fresh opening-only private records required")
    inventory = []
    for name, records in sorted(controller._initial.items()):
        rows = sorted([
            {"id": record["public"]["id"], "public_sha256": digest(record["public"]),
             "released_at": record["released_at"]}
            for record in records if record.get("actor_visible") is True
            and record.get("outcome_binding") is None
            and timestamp(record["released_at"]) <= world.opening.instant
        ], key=lambda row: row["id"])
        inventory.append({"collection": name, "record_count": len(rows), "records_sha256": digest(rows)})
    identifier = uid()
    body = {"schema_version": "anvil.marketing-world-opening-release.v1", "week": 0, "phase": "opening",
            "operator_program_id": world.operator_program_id,
            **{key: row["attachment"][key] for key in ("world_binding_id", "world_binding_sha256", "episode_id",
                                                        "generation", "case_id", "case_snapshot_sha256")},
            "released_at": world.opening.instant.isoformat().replace("+00:00", "Z"),
            "window_ref": world.opening.window_ref, "receipt_id": identifier,
            "evidence_refs": inventory_refs(identifier, inventory),
            "baseline_delivery_manifest": baseline_manifest(controller, world.service_contract, row["attachment"], 0)}
    body["receipt_sha256"] = digest(body)
    reply = OpeningRelease.model_validate(body).model_dump(mode="json")
    allowed = connection.execute(
        "SELECT marketing_runtime.commit_private_world_opening(%s,%s,%s,%s,%s,%s,%s) AS allowed",
        (claim.job_id, claim.lease_token, claim.plan_id, row["controller_state_sha256"], canonical(reply).decode(),
         digest(reply), canonical(inventory).decode()),
    ).fetchone()["allowed"]
    if allowed is not True:
        raise RuntimeError("marketing_opening_commit_unconfirmed_no_replay")
    return reply
