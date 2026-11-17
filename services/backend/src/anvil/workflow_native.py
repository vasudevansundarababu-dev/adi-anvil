"""Exact source-bound native graph definitions; no inferred graph or approval."""

from uuid import UUID

from pydantic import Field

from anvil.db import digest
from anvil.schemas import Strict
from anvil.workflow_contract import WorkflowBinding
from anvil.workflow_runtime import validate_output


class OutputField(Strict):
    artifact: str = Field(min_length=1, max_length=100)
    field: str = Field(min_length=1, max_length=100)


class Definition(Strict):
    package_id: UUID
    binding: WorkflowBinding
    initial_artifacts: dict = Field(default_factory=dict, max_length=50)
    output_fields: dict[str, OutputField] = Field(min_length=1, max_length=100)
    review_artifact_id: UUID
    rights_confirmed: bool = Field(strict=True)


def validate(task, manifest, definition):
    binding = definition.binding
    binding.bind_task(task, manifest["source_sha256"])
    if definition.rights_confirmed is not True:
        raise ValueError("explicit_workflow_rights_confirmation_required")
    if (
        manifest["source_sha256"] != binding.payload_sha256
        or manifest.get("binding") != "structured-decision-v1"
    ):
        raise ValueError("exact_structured_workflow_source_required")
    graph = binding.graph
    if any(r.tools for r in graph.roles):
        raise ValueError("native_graph_tools_require_separate_adapter")
    if any(n.kind == "human_step" and n.human_mode != "actual" for n in graph.nodes):
        raise ValueError("native_graph_requires_actual_humans")
    if not any(n.kind == "agent_step" for n in graph.nodes) or graph.bounds.calls < 1:
        raise ValueError("native_model_graph_requires_agent_calls")
    entry = next(n for n in graph.nodes if n.id == graph.entry)
    validate_output(entry, definition.initial_artifacts, graph)
    if any(n.outputs and n.kind not in {"input", "agent_step", "human_step"} for n in graph.nodes):
        raise ValueError("native_control_output_producer_not_supported")
    artifacts = {a.id: a for a in graph.artifacts}
    required = {rule.binding.field for rule in [*task.constraints, *task.rubric.criteria]}
    if set(definition.output_fields) != required:
        raise ValueError("exact_original_task_output_projection_required")
    for target in definition.output_fields.values():
        if (
            target.artifact not in artifacts
            or target.field not in artifacts[target.artifact].fields
        ):
            raise ValueError("workflow_output_projection_unresolved")
        if not any(n.kind == "output" and target.artifact in n.inputs for n in graph.nodes):
            raise ValueError("workflow_projection_requires_final_output_input")
    return digest(definition.model_dump(mode="json"))


def project_output(definition, artifacts):
    try:
        return {
            name: artifacts[value.artifact][value.field]
            for name, value in definition.output_fields.items()
        }
    except (KeyError, TypeError):
        raise ValueError("workflow_final_output_missing") from None


def actor_request(binding, state, key):
    from anvil.workflow_projection import role_input

    effect = state["effects"].get(key)
    node = next(
        (n for n in binding.graph.nodes if key == f"{n.id}:{state['visits'].get(n.id, 0)}"), None
    )
    if (
        not effect
        or not node
        or state["nodes"][node.id] != "running"
        or effect["status"] != "dispatched"
    ):
        raise ValueError("workflow_effect_not_pending")
    request = role_input(
        binding.graph,
        node.id,
        node.role,
        state["artifacts"],
        {n for n, status in state["nodes"].items() if status == "completed"},
    )
    request["response_mode"] = "Actor response"
    if digest(request) != effect["request_sha256"]:
        raise ValueError("workflow_effect_request_changed")
    return request, effect["call_index"]
