"""Allowlisted per-node actor input; operator graph is never an actor prompt."""

import copy


def role_input(graph, node_id, role_id, artifacts, completed_nodes):
    node = next((n for n in graph.nodes if n.id == node_id), None)
    role = next((r for r in graph.roles if r.id == role_id), None)
    if (
        not node
        or not role
        or node.role != role_id
        or node.kind not in {"agent_step", "human_step"}
    ):
        raise ValueError("workflow_role_scope_denied")
    definitions = {a.id: a for a in graph.artifacts}
    inputs = {}
    for artifact_id in node.inputs:
        definition = definitions[artifact_id]
        if (
            role_id not in definition.readers
            or definition.producer not in completed_nodes
            or artifact_id not in artifacts
        ):
            raise ValueError("workflow_input_unavailable")
        value = artifacts[artifact_id]
        types = {"boolean": bool, "integer": int, "string": str}
        if (
            not isinstance(value, dict)
            or set(value) != definition.fields.keys()
            or any(
                (value[k] is not None and type(value[k]) is not bool)
                if t == "boolean_or_unknown"
                else type(value[k]) is not types[t]
                for k, t in definition.fields.items()
            )
        ):
            raise ValueError("workflow_input_schema_mismatch")
        inputs[artifact_id] = copy.deepcopy(value)
    return {
        "node_id": node.id,
        "role_id": role.id,
        "instruction": node.instruction,
        "tools": list(role.tools),
        "inputs": inputs,
        "outputs": [
            {"id": a.id, "fields": dict(a.fields)} for a in graph.artifacts if a.id in node.outputs
        ],
        "response_mode": "Scripted human response"
        if node.human_mode == "scripted_fixture"
        else "Software fixture",
    }
