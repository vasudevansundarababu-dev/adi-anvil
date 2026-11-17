"""Declarative workflow sidecar. No code, hidden references or dispatch authority.

The sidecar binds an unchanged legacy task payload; it does not allocate task v4.
This first capability accepts structured, reducible loops; overlapping/nested loops
are deliberately blocked until their join/reset semantics have been qualified.
"""

import hashlib
from typing import Literal

import rfc8785
from pydantic import Field, model_validator

from anvil.praxis_contract import Identifier, Model, Text


class Role(Model):
    id: Identifier
    responsibility: Text
    tools: list[Identifier] = Field(max_length=50)


class Artifact(Model):
    id: Identifier
    producer: Identifier
    readers: list[Identifier] = Field(min_length=1, max_length=30)
    fields: dict[Identifier, Literal["string", "boolean", "boolean_or_unknown", "integer"]] = Field(
        min_length=1, max_length=100
    )


class Node(Model):
    id: Identifier
    kind: Literal["input", "agent_step", "decision", "join", "human_step", "output", "escalation"]
    label: str = Field(min_length=1, max_length=160)
    instruction: Text
    role: Identifier | None = None
    inputs: list[Identifier] = Field(default_factory=list, max_length=50)
    outputs: list[Identifier] = Field(default_factory=list, max_length=50)
    # A decision reads exactly one declared typed field, never a reference answer.
    decision_artifact: Identifier | None = None
    decision_field: Identifier | None = None
    human_mode: Literal["scripted_fixture", "actual"] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=86400)


class Edge(Model):
    id: Identifier
    source: Identifier
    target: Identifier
    outcome: Literal["next", "true", "false", "unknown", "error", "timeout", "exhausted"]
    loop: Identifier | None = None


class Loop(Model):
    id: Identifier
    edge: Identifier
    max_iterations: int = Field(ge=1, le=100, strict=True)
    exhausted: Identifier


class Bounds(Model):
    transitions: int = Field(ge=1, le=10000, strict=True)
    calls: int = Field(ge=0, le=1000, strict=True)
    wall_seconds: int = Field(ge=1, le=86400, strict=True)
    tokens: int = Field(ge=0, le=10000000, strict=True)
    cost_micro_usd: int = Field(ge=0, le=1000000000, strict=True)


class WorkflowGraph(Model):
    schema_version: Literal["praxis.anvil.workflow-graph.v1"]
    template_id: Identifier
    template_version: Identifier
    entry: Identifier
    roles: list[Role] = Field(min_length=1, max_length=30)
    nodes: list[Node] = Field(min_length=2, max_length=100)
    edges: list[Edge] = Field(min_length=1, max_length=300)
    artifacts: list[Artifact] = Field(default_factory=list, max_length=100)
    loops: list[Loop] = Field(default_factory=list, max_length=20)
    bounds: Bounds

    @model_validator(mode="after")
    def consistent(self):
        groups = [self.roles, self.nodes, self.edges, self.artifacts, self.loops]
        for group in groups:
            if len({v.id for v in group}) != len(group):
                raise ValueError("duplicate_id")
        nodes = {n.id: n for n in self.nodes}
        roles = {r.id for r in self.roles}
        artifacts = {a.id: a for a in self.artifacts}
        edges = {e.id: e for e in self.edges}
        loops = {loop.id: loop for loop in self.loops}
        if self.entry not in nodes or nodes[self.entry].kind != "input":
            raise ValueError("entry_must_be_input")
        outgoing = {n: [] for n in nodes}
        incoming = {n: [] for n in nodes}
        for e in self.edges:
            if e.source not in nodes or e.target not in nodes:
                raise ValueError("unresolved_edge")
            if e.loop and (e.loop not in loops or loops[e.loop].edge != e.id):
                raise ValueError("unresolved_loop")
            outgoing[e.source].append(e)
            incoming[e.target].append(e)
        for n in self.nodes:
            if len(set(n.inputs)) != len(n.inputs) or len(set(n.outputs)) != len(n.outputs):
                raise ValueError("duplicate_artifact_reference")
            if set(n.inputs + n.outputs) - artifacts.keys():
                raise ValueError("unresolved_artifact")
            if n.role is not None and n.role not in roles:
                raise ValueError("unresolved_role")
            if n.kind in {"agent_step", "human_step"} and not n.role:
                raise ValueError("role_required")
            if n.kind == "human_step":
                if not n.human_mode or not n.timeout_seconds:
                    raise ValueError("human_contract_required")
            elif n.human_mode or n.timeout_seconds:
                raise ValueError("unexpected_human_contract")
            if n.kind == "decision":
                a = artifacts.get(n.decision_artifact)
                if (
                    not a
                    or n.decision_artifact not in n.inputs
                    or a.fields.get(n.decision_field) not in {"boolean", "boolean_or_unknown"}
                ):
                    raise ValueError("decision_requires_boolean_input")
            elif n.decision_artifact or n.decision_field:
                raise ValueError("unexpected_decision_contract")
            outcomes = [e.outcome for e in outgoing[n.id]]
            expected = {
                "decision": {"true", "false", "unknown", "error"},
                "human_step": {"next", "timeout", "error"},
                "output": set(),
                "escalation": set(),
            }.get(n.kind, {"next"})
            # Explicit fan-out is permitted on ordinary steps. Other routes deterministic.
            if set(outcomes) - {"exhausted"} != expected:
                raise ValueError("missing_or_unsupported_outcome")
            if n.kind in {"decision", "human_step"} and len(outcomes) != len(set(outcomes)):
                raise ValueError("ambiguous_outcome")
            if n.kind == "join" and len(incoming[n.id]) < 2:
                raise ValueError("join_requires_predecessors")
            if n.kind == "input" and n.id != self.entry:
                raise ValueError("multiple_inputs_unsupported")
        for a in self.artifacts:
            if a.producer not in nodes or a.id not in nodes[a.producer].outputs:
                raise ValueError("artifact_producer_mismatch")
            if set(a.readers) - roles or len(set(a.readers)) != len(a.readers):
                raise ValueError("artifact_reader_mismatch")
        for n in self.nodes:
            if any(artifacts[a].producer != n.id for a in n.outputs):
                raise ValueError("artifact_single_writer_required")
            if n.role and any(n.role not in artifacts[a].readers for a in n.inputs):
                raise ValueError("cross_role_artifact")

        def reach(start, adjacency):
            seen, todo = set(), [start]
            while todo:
                v = todo.pop()
                if v not in seen:
                    seen.add(v)
                    todo.extend(adjacency[v])
            return seen

        forward = {n: [e.target for e in outgoing[n] if not e.loop] for n in nodes}
        reverse = {n: [e.source for e in incoming[n] if not e.loop] for n in nodes}
        # Removing every declared return edge must produce an acyclic graph.
        visiting, visited = set(), set()

        def visit(v):
            if v in visiting:
                raise ValueError("undeclared_cycle")
            if v in visited:
                return
            visiting.add(v)
            for target in forward[v]:
                visit(target)
            visiting.remove(v)
            visited.add(v)

        visit(self.entry)
        if visited != nodes.keys():
            raise ValueError("unreachable_node")
        for node in self.nodes:
            if any(
                node.id not in reach(artifacts[a].producer, forward)
                or artifacts[a].producer == node.id
                for a in node.inputs
            ):
                raise ValueError("artifact_producer_not_upstream")
        terminals = {n.id for n in self.nodes if n.kind in {"output", "escalation"}}
        if not terminals or any(not (reach(n, forward) & terminals) for n in nodes):
            raise ValueError("terminal_unreachable")
        regions = []
        for loop in self.loops:
            e = edges.get(loop.edge)
            if not e or e.loop != loop.id or e.outcome not in {"true", "false"}:
                raise ValueError("loop_requires_decision_return")
            region = reach(e.target, forward) & reach(e.source, reverse)
            if e.source not in reach(e.target, forward) or e.source == e.target:
                raise ValueError("invalid_loop_return")
            if loop.exhausted in region or loop.exhausted not in nodes:
                raise ValueError("invalid_exhausted_exit")
            exits = [x for x in outgoing[e.source] if x.outcome == "exhausted"]
            if len(exits) != 1 or exits[0].target != loop.exhausted or exits[0].loop:
                raise ValueError("exhausted_route_required")
            if any(region & other for other in regions):
                raise ValueError("nested_or_overlapping_loops_not_supported")
            if any(x.target in region - {e.target} and x.source not in region for x in self.edges):
                raise ValueError("irreducible_loop")
            regions.append(region)
        for e in self.edges:
            if e.outcome == "exhausted" and not any(
                loop.exhausted == e.target and edges[loop.edge].source == e.source
                for loop in self.loops
            ):
                raise ValueError("orphan_exhausted_route")
        return self


def graph_hash(graph: WorkflowGraph):
    """RFC8785 bytes shared with JS; excludes nothing from the semantic contract."""
    return hashlib.sha256(rfc8785.dumps(graph.model_dump())).hexdigest()


class WorkflowBinding(Model):
    schema_version: Literal["praxis.anvil.workflow-binding.v1"]
    task_id: Identifier
    task_version: str = Field(min_length=1, max_length=80)
    revision_id: Identifier
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    graph_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    graph: WorkflowGraph

    @model_validator(mode="after")
    def bound(self):
        if graph_hash(self.graph) != self.graph_sha256:
            raise ValueError("workflow_hash_mismatch")
        return self

    def bind_task(self, task, payload_sha256):
        if (self.task_id, self.task_version, self.revision_id, self.payload_sha256) != (
            task.task_id,
            task.task_version,
            task.revision_id,
            payload_sha256,
        ):
            raise ValueError("workflow_task_binding_mismatch")
        from anvil.praxis_contract import actor_view

        tools = {action["id"] for action in actor_view(task).get("actions", [])}
        if any(
            set(role.tools) - tools or len(set(role.tools)) != len(role.tools)
            for role in self.graph.roles
        ):
            raise ValueError("workflow_tool_binding_mismatch")


def execution_blockers(graph):
    # Source acceptance/viewing is separate from native execution qualification.
    blockers = ["workflow_native_runtime_not_qualified"]
    if any(n.human_mode == "actual" for n in graph.nodes):
        blockers.append("actual_human_restore_resume_not_qualified")
    return blockers
