"""Private API persistence for source-simulated descriptor/campaign effects."""

import re
from uuid import UUID

from anvil.campaign_semantic_contract import bounded_json
from anvil.db import uid
from anvil.marketing_paid_world import effect_result
from anvil.marketing_task2_persistence import freeze, restore
from anvil.marketing_world_requests import resolve_request
from anvil.marketing_world_services import descriptor_proposal
from anvil.praxis_generic_contract import canonical, digest


def effect(connection, claim, world, source, qualification, execution):
    sources = getattr(world, "service_contract", None)
    if type(sources) is not dict:
        raise RuntimeError("Qualified explicit service-world v2 required")
    node = next((n for n in execution["workflow_graph"]["nodes"] if n["id"] == claim.value["node_id"]), None)
    campaign = node is not None and node["id"] == "approver" and node["type"] == "human_step"
    if node is None or not campaign and (node["type"] != "external_system" or node["id"] != "task3"):
        raise RuntimeError("Exact published Task3 or independent campaign-controller node required")
    if campaign:
        from anvil.marketing_world_activation_definition import ActivationWorldDefinition
        from anvil.marketing_world_opening_definition import OpeningWorldDefinition
        from anvil.marketing_world_population_definition import PopulationWorldDefinition

        if type(world) not in (ActivationWorldDefinition, OpeningWorldDefinition, PopulationWorldDefinition):
            raise RuntimeError("Complete source-validated activation-world v4 required for campaign decisions")
        ctx = connection.execute(
            "SELECT marketing_runtime.private_world_campaign_context(%s,%s,%s,%s,%s) AS value",
            (claim.job_id, claim.lease_token, claim.plan_id, claim.value["week"], claim.value["visit"]),
        ).fetchone()["value"]
    else:
        ctx = connection.execute(
            "SELECT marketing_runtime.private_world_service_context(%s,%s,%s,%s,%s,%s) AS value",
            (claim.job_id, claim.lease_token, claim.plan_id, node["id"], claim.value["week"], claim.value["visit"]),
        ).fetchone()["value"]
    if not ctx:
        raise RuntimeError("Actual existing private workflow service intent required; no replay")
    row, intent = ctx["session"], ctx["effect"]
    if (str(row["source_id"]) != str(source["id"])
            or str(row["qualification_id"]) != str(qualification["id"])
            or any(str(row[k]) != str(claim.value[k]) for k in ("world_binding_id", "episode_id"))
            or row["generation"] != claim.value["generation"]
            or row["world_binding_sha256"] != claim.value["world_binding_sha256"]
            or intent["node_sha256"] != digest(node)
            or intent["input_sha256"] != digest(claim.value["inputs"])):
        raise ValueError("Exact qualified world and committed request-effect scope required")
    controller = restore(row["controller_state"], row["controller_state_sha256"])
    if (controller.case_id != world.case_id or controller.trial_id != row["episode_id"]
            or controller.generation != row["generation"]):
        raise ValueError("Actual persisted original service controller required")
    observed = resolve_request(controller, execution, node, claim.value["inputs"])
    before, before_hash = freeze(controller)
    if before_hash != row["controller_state_sha256"]:
        raise ValueError("Original service state must retain its exact canonical checkpoint")
    port = None
    after, after_hash = before, before_hash
    if campaign:
        from anvil.marketing_world_campaign_effect import prepare

        successor, artifact, port = prepare(controller, world, execution, node, claim.value["inputs"])
        if successor is not None:
            after, after_hash = freeze(successor)
    else:
        artifact = descriptor_proposal(controller, execution, node, claim.value["inputs"], sources)
    receipt = {
        "input_sha256": intent["input_sha256"], "artifact_sha256": digest(artifact),
        "post_state_sha256": after_hash,
        "world_binding_sha256": row["world_binding_sha256"], "world_effect_id": uid(),
        "episode_id": row["episode_id"], "generation": row["generation"],
        "node_id": node["id"], "week": claim.value["week"], "visit": claim.value["visit"],
        "origin": "persisted_environment_effect", "simulated_environment": True,
    }
    receipt["world_receipt_sha256"] = digest({"artifact": artifact, "receipt": receipt, "port": port})
    reply = effect_result({"artifact": artifact, "receipt": receipt, "port": port}).model_dump(mode="json")
    bounded_json(reply, 60000, max_nodes=10000)
    if campaign:
        allowed = connection.execute(
            "SELECT marketing_runtime.commit_private_world_campaign(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS allowed",
            (claim.job_id, claim.lease_token, claim.plan_id, claim.value["week"], claim.value["visit"], UUID(intent["id"]),
             before_hash, canonical(before).decode(), canonical(after).decode(), after_hash,
             canonical(reply).decode(), digest(reply), digest(sources), canonical(observed["request"]).decode(),
             observed["request_sha256"], canonical(claim.value["inputs"]).decode()),
        ).fetchone()["allowed"]
    else:
        allowed = connection.execute(
            "SELECT marketing_runtime.commit_private_world_service(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS allowed",
            (claim.job_id, claim.lease_token, claim.plan_id, node["id"], claim.value["week"], claim.value["visit"],
             UUID(intent["id"]), before_hash, canonical(reply).decode(), digest(reply), digest(sources),
             canonical(observed["request"]).decode(), observed["request_sha256"], canonical(claim.value["inputs"]).decode()),
        ).fetchone()["allowed"]
    if allowed is not True:
        raise RuntimeError("Private service commit unconfirmed; no retry")
    return reply


def records(connection, claim):
    value = connection.execute(
        "SELECT marketing_runtime.private_world_service_records(%s,%s,%s) AS value",
        (claim.job_id, claim.lease_token, claim.plan_id),
    ).fetchone()["value"]
    return checked_records(value)


def checked_records(value):
    if type(value) is not dict or set(value) != {"records", "source_contract_sha256"}:
        raise ValueError("Actual immutable private service records required")
    bounded_json(value, 524288, max_nodes=10000)
    return value


def verify_records(graph, execution, value):
    """A scheduler's scope-correct fabricated effect is not API return proof."""
    nodes = {n["id"]: n for n in execution["workflow_graph"]["nodes"]}
    effects = {str(e["id"]): e for e in graph["effects"]}
    rows, source_hash = value["records"], value["source_contract_sha256"]
    if type(rows) is not list or len(rows) > 400:
        raise ValueError("Bounded actual private service effect set required")
    seen = set()
    for row in rows:
        expected_fields = {"effect_id", "receipt_id", "reply_sha256", "source_contract_sha256",
                           "post_state_sha256", "request_sha256", "request_id", "request_version",
                           "input_sha256", "node_sha256"}
        if (type(row) is not dict or set(row) != expected_fields
                or type(row["request_version"]) is not int or not 1 <= row["request_version"] <= 3
                or type(row["request_id"]) is not str or not 1 <= len(row["request_id"]) <= 100
                or any(type(row[key]) is not str or not re.fullmatch(r"[0-9a-f]{64}", row[key])
                       for key in ("reply_sha256", "source_contract_sha256", "post_state_sha256", "request_sha256", "input_sha256", "node_sha256"))
                or any(type(row[key]) is not str or str(UUID(row[key])) != row[key] for key in ("effect_id", "receipt_id"))):
            raise ValueError("Exact bounded immutable service proof projection required")
        key = str(row["effect_id"])
        observed = effects.get(key)
        if (key in seen or observed is None or type(source_hash) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", source_hash)
                or row["source_contract_sha256"] != source_hash):
            raise ValueError("Actual service proof belongs to another source or effect")
        seen.add(key)
        if observed["state"] != "completed":
            # An API return may exist after a lost response. This does not
            # repair or complete the immutable unknown workflow observation.
            continue
        reply = effect_result(observed["result"]).model_dump(mode="json")
        body = reply["receipt"]
        base = {**reply, "receipt": {k: v for k, v in body.items() if k != "world_receipt_sha256"}}
        if (digest(reply) != row["reply_sha256"]
                or body["world_receipt_sha256"] != digest(base)
                or str(row["receipt_id"]) != body["world_effect_id"]
                or body["input_sha256"] != observed["input_sha256"]
                or row["input_sha256"] != observed["input_sha256"]
                or row["node_sha256"] != observed["node_sha256"]
                or reply["artifact"]["request_ref"] != {
                    "id": row["request_id"], "version": row["request_version"], "sha256": row["request_sha256"]}
                or body["node_id"] != observed["node_id"]
                or body["week"] != observed["week"] or body["visit"] != observed["visit"]
                or body["post_state_sha256"] != row["post_state_sha256"]):
            raise ValueError("Graph effect lacks matching immutable actual API service return")
    for key, observed in effects.items():
        node = nodes.get(observed["node_id"])
        if node is None:
            raise ValueError("Unpublished service effect in actual ledger")
        if observed["state"] == "completed" and node["type"] in {"human_step", "external_system"} and key not in seen:
            raise ValueError("Completed non-agent effect has no actual API service proof")
