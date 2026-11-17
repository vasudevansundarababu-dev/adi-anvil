"""Exact authored workflow locations, separate from descriptive design labels.

No step ID is generated for a list item. A versioned JSON pointer and content
hash identify it instead. Template graphs retain their real node/role IDs.
"""

from typing import Literal

from pydantic import Field, model_validator

from anvil.db import one
from anvil.golden_targets import family
from anvil.marketing_task2_contract import WIRE_ROLES
from anvil.praxis_generic_contract import digest
from anvil.schemas import Strict


class StepReference(Strict):
    source: Literal["actor", "template_execution"]
    path: str = Field(min_length=1, max_length=500, pattern=r"^/")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SkillMapping(Strict):
    target: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=120)
    steps: list[StepReference] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_steps(self):
        if len({(step.source, step.path) for step in self.steps}) != len(self.steps):
            raise ValueError("Duplicate authored workflow location")
        return self


def workflow_options(task, template=None):
    """Only public authored fields, with explicit role provenance and missingness."""
    actor = task.get("actor") or {}
    graph = actor.get("workflowGraph")
    source, graph_path = "actor", "/workflowGraph"
    if graph is None and template is not None:
        graph = template.get("execution", {}).get("workflow_graph")
        source, graph_path = "template_execution", "/workflow_graph"
    identity = {key: task.get(key) for key in ("task_id", "task_version", "payload_sha256")}
    steps = []
    if isinstance(graph, dict):
        roles = {
            role["id"]: (index, role)
            for index, role in enumerate(graph.get("roles", []))
            if isinstance(role, dict) and isinstance(role.get("id"), str)
        }
        for index, node in enumerate(graph.get("nodes", [])):
            if not isinstance(node, dict) or node.get("type") != "agent_step":
                continue
            identifier, role_id = node.get("id"), node.get("roleId")
            if not isinstance(identifier, str) or role_id not in roles:
                continue
            role_index, role = roles[role_id]
            steps.append(
                identity
                | {
                    "source": source,
                    "path": f"{graph_path}/nodes/{index}",
                    "sha256": digest(node),
                    "node_id": identifier,
                    "node_type": "agent_step",
                    "label": str(node.get("label") or identifier)[:300],
                    "instruction_preview": str(node.get("instruction") or "")[:500],
                    "authored_role_id": role_id,
                    "role": WIRE_ROLES.get(role_id, role_id)
                    if family(task) == "marketing"
                    else role_id,
                    "role_name": role.get("name"),
                    "role_source": source,
                    "role_source_path": f"{graph_path}/roles/{role_index}",
                    "role_source_sha256": digest(role),
                    "role_kind": "authored_graph_role",
                }
            )
    else:
        procedure = actor.get("sections", {}).get("S5", {}).get("steps")
        mode = (template or {}).get("authoring", {}).get("profile", {}).get("agentMode")
        if isinstance(procedure, list):
            for index, item in enumerate(procedure):
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("action"), str)
                    or not item["action"].strip()
                ):
                    continue
                steps.append(
                    identity
                    | {
                        "source": "actor",
                        "path": f"/sections/S5/steps/{index}",
                        "sha256": digest(item),
                        "node_id": None,
                        "node_type": "authored_procedure_item",
                        "label": item["action"][:300],
                        "instruction_preview": item["action"][:500],
                        "authored_role_id": None,
                        "role": "kyc_analyst"
                        if mode == "SINGLE" and family(task) == "kyc"
                        else None,
                        "role_name": "Single task agent" if mode == "SINGLE" else None,
                        "role_source": "template" if mode == "SINGLE" else None,
                        "role_source_path": "/authoring/profile/agentMode"
                        if mode == "SINGLE"
                        else None,
                        "role_source_sha256": digest(mode) if mode == "SINGLE" else None,
                        "role_kind": "single_agent_template_runtime_role"
                        if mode == "SINGLE"
                        else "authored_role_mapping_required",
                    }
                )
    return identity | {
        "steps": steps,
        "status": "authored_locations_available"
        if steps
        else "authored_workflow_locations_missing",
        "qualified": False,
        "mapping_authority": "review_and_save_exact_project_binding",
        "template_sha256": digest(template) if template is not None else None,
    }


def resolve(mapping, descriptor, options):
    """A user choice cannot name a synthetic, foreign or changed node/role."""
    if mapping.target != descriptor["target"]:
        raise ValueError("Skill target source identity changed")
    lookup = {(step["source"], step["path"]): step for step in options["steps"]}
    selected = []
    for reference in mapping.steps:
        step = lookup.get((reference.source, reference.path))
        if step is None or step["sha256"] != reference.sha256:
            raise ValueError("Authored workflow location is absent or changed")
        if any(
            step.get(key) != descriptor.get(key)
            for key in ("task_id", "task_version", "payload_sha256")
        ):
            raise ValueError("Workflow location belongs to another task revision")
        selected.append(step)
    if mapping.role not in {step.get("role") for step in selected}:
        raise ValueError("Selected responsible role must own an actual selected authored step")
    return {
        "target": mapping.target,
        "role": mapping.role,
        "steps": [
            {
                key: step[key]
                for key in (
                    "source",
                    "path",
                    "sha256",
                    "node_id",
                    "authored_role_id",
                    "role",
                    "role_source",
                    "role_source_path",
                    "role_source_sha256",
                    "role_kind",
                )
            }
            for step in selected
        ],
        "task_id": descriptor["task_id"],
        "task_version": descriptor["task_version"],
        "payload_sha256": descriptor["payload_sha256"],
        "template_sha256": options.get("template_sha256"),
        "status": "reviewed_project_binding_mapping",
    }


def options(c, project, imported):
    values, templates = [], {}
    for task in imported["content"].get("tasks", []):
        reference = task.get("source", {}).get("template") or {}
        key = (reference.get("id"), reference.get("version"), reference.get("sha256"))
        if key not in templates:
            row = (
                one(
                    c,
                    "SELECT spec,spec_sha256 FROM anvil.praxis_template_versions WHERE project_id=%s AND template_key=%s AND version=%s AND spec_sha256=%s",
                    (project, *key),
                )
                if all(value is not None for value in key)
                else None
            )
            if row is not None and digest(row["spec"]) != row["spec_sha256"]:
                raise ValueError("Bound template source integrity changed")
            templates[key] = row["spec"] if row else None
        values.append(workflow_options(task, templates[key]))
    return values


def resolve_all(mappings, descriptors, workflow_options):
    if len({mapping.target for mapping in mappings}) != len(mappings):
        raise ValueError("Duplicate skill mapping target")
    if sum(len(mapping.steps) for mapping in mappings) > 1000:
        raise ValueError("At most1000 exact authored step references per Project binding")
    by_target = {row["target"]: row for row in descriptors}
    by_task = {row["task_id"]: row for row in workflow_options}
    output = []
    for mapping in mappings:
        descriptor = by_target.get(mapping.target)
        if descriptor is None or descriptor["task_id"] not in by_task:
            raise ValueError("Unknown exact-source skill mapping target")
        output.append(resolve(mapping, descriptor, by_task[descriptor["task_id"]]))
    return output


def mapped(descriptors, preparation):
    """Project only already-frozen safe mappings; never consult the current UI."""
    bindings = {row["target"]: row for row in preparation.get("skill_mapping_bindings", [])}
    if len(bindings) != len(preparation.get("skill_mapping_bindings", [])):
        raise ValueError("Ambiguous duplicate frozen skill mappings")
    output = []
    for descriptor in descriptors:
        row = bindings.get(descriptor["target"])
        if row is None:
            output.append(descriptor)
            continue
        if any(
            row.get(key) != descriptor.get(key)
            for key in ("task_id", "task_version", "payload_sha256")
        ) or not row.get("steps"):
            raise ValueError("Frozen skill mapping task revision mismatch")
        output.append(
            descriptor
            | {
                "role": row["role"],
                "step": row["steps"][0]["node_id"] or row["steps"][0]["path"],
                "authored_steps": row["steps"],
                "step_status": "reviewed_source_mapping",
                "role_mapping_status": "reviewed_source_role_mapping_not_execution_evidence",
                "skill_mapping_sha256": digest(row),
                "skill_mapping_binding": preparation.get("project_binding"),
            }
        )
    return output


def public_mapping(descriptor):
    return {
        key: descriptor[key]
        for key in (
            "step_status",
            "role_mapping_status",
            "authored_steps",
            "skill_mapping_sha256",
            "skill_mapping_binding",
        )
        if key in descriptor
    }
