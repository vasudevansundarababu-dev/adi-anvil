"""Resolve actual versioned campaign requests before a private world effect.

This is a server-side primitive, not world qualification, approval or dispatch.
Its controller must come from the current scoped SQL episode, never the actor.
"""

from copy import deepcopy

from pydantic import Field

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import Sha
from anvil.marketing_task2_contract import WIRE_ROLES
from anvil.marketing_task2_runtime import Task2Controller
from anvil.praxis_generic_contract import digest
from anvil.praxis_marketing_contract import MarketingExecution
from anvil.schemas import Strict

KINDS = {
    "production_request": ("external_system", "production-requests"),
    "approval_request": ("human_step", "approval-requests"),
}


class RequestReference(Strict):
    id: str = Field(min_length=1, max_length=100)
    version: int = Field(strict=True, ge=1, le=3)
    sha256: Sha


class RequestArtifact(Strict):
    request_ref: RequestReference


def resolve_request(controller, execution, node, inputs):
    """Candidate text never creates a real request or approval by assertion."""
    if type(controller) is not Task2Controller:
        raise ValueError("Actual scoped persisted campaign controller required")
    bounded_json([execution, node, inputs], 262144, max_nodes=20000)
    contract = MarketingExecution.model_validate(execution)
    nodes = contract.workflow_graph["nodes"]
    expected = next((item for item in nodes if item["id"] == node.get("id")), None)
    if expected != node:
        raise ValueError("Exact published non-agent request node required")
    references = node.get("sendsRefs", node.get("permittedEvidence", []))
    if len(references) != 1 or set(inputs) != set(references) or references[0] not in KINDS:
        raise ValueError("Exact supported request artifact input required")
    artifact_name = references[0]
    node_type, kind = KINDS[artifact_name]
    if node["type"] != node_type:
        raise ValueError("World request node type differs from published effect")
    producers = [item for item in nodes if item.get("outputArtifact") == artifact_name]
    if len(producers) != 1 or producers[0]["type"] != "agent_step":
        raise ValueError("Exactly one published assigned request producer required")
    role = producers[0]["roleId"]
    if role not in WIRE_ROLES:
        raise ValueError("Known assigned request producer role required")
    reference = RequestArtifact.model_validate(inputs[artifact_name]).request_ref
    request = controller._objects.get(reference.id)
    if (
        type(request) is not dict
        or request.get("id") != reference.id
        or request.get("version") != reference.version
        or request.get("kind") != kind
        or request.get("created_by_role") != WIRE_ROLES[role]
        or request.get("simulation_only") is not True
        or digest(request) != reference.sha256
    ):
        raise ValueError("Current stored request kind, author, version and bytes required")
    return {
        "request": deepcopy(request),
        "request_sha256": reference.sha256,
        "producer_role": role,
        "node_id": node["id"],
        "episode_id": controller.trial_id,
        "generation": controller.generation,
    }
