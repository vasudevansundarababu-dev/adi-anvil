"""Offline LangGraph conformance runner, separate from qualified Harbor dispatch.

Only predeclared software responses run here. No provider, tool process or actual
human is invoked. Checkpoints alone are not an effect ledger: the store protocol
must commit an intent before returning a new claim and retain ambiguous claims.
The production benchmark admission remains blocked for graph-bearing tasks.
"""

from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from anvil.workflow_contract import WorkflowBinding
from anvil.workflow_projection import role_input


class Store(Protocol):
    def admission(self, trial: str, binding: WorkflowBinding): ...
    def claim(self, trial: str, key: str, request: dict) -> dict: ...
    def complete(self, trial: str, key: str, response: dict): ...


class State(TypedDict):
    trial: str
    current: str
    transitions: int
    visits: dict[str, int]
    iterations: dict[str, int]
    artifacts: dict
    trace: list[dict]
    status: str


def fixture_capability(binding):
    graph = binding.graph
    blockers = []
    if any(n.human_mode == "actual" for n in graph.nodes):
        blockers.append("actual_human_not_supported")
    if any(n.kind == "join" for n in graph.nodes) or any(
        sum(e.source == n.id and e.outcome == "next" for e in graph.edges) > 1 for n in graph.nodes
    ):
        blockers.append("parallel_fixture_scheduling_not_qualified")
    if any(r.tools for r in graph.roles):
        blockers.append("fixture_runtime_has_no_tools")
    if any(n.outputs and n.kind not in {"agent_step", "human_step"} for n in graph.nodes):
        blockers.append("fixture_output_producer_not_supported")
    for loop in graph.loops:
        edge = next(e for e in graph.edges if e.id == loop.edge)
        cursor, seen = edge.target, set()
        while cursor != edge.source:
            if cursor in seen:
                blockers.append("fixture_loop_body_not_linear")
                break
            seen.add(cursor)
            successors = [
                e.target
                for e in graph.edges
                if e.source == cursor and e.outcome == "next" and not e.loop
            ]
            if len(successors) != 1:
                blockers.append("fixture_loop_body_not_linear")
                break
            cursor = successors[0]
    return blockers


def validate_response(node, response, graph):
    if set(response) != set(node.outputs):
        raise ValueError("fixture_output_set_mismatch")
    definitions = {a.id: a for a in graph.artifacts}
    types = {"boolean": bool, "integer": int, "string": str}
    for artifact_id, value in response.items():
        fields = definitions[artifact_id].fields
        if not isinstance(value, dict) or set(value) != fields.keys():
            raise ValueError("fixture_output_schema_mismatch")
        if any(
            (value[k] is not None and type(value[k]) is not bool)
            if t == "boolean_or_unknown"
            else type(value[k]) is not types[t]
            for k, t in fields.items()
        ):
            raise ValueError("fixture_output_type_mismatch")


def compile_fixture(binding: WorkflowBinding, responses: dict, store: Store, checkpointer):
    """Compile only the explicitly supported offline subset with caller-owned saver.

    Production supplies its PostgreSQL saver; unit tests also exercise restart via
    a fresh compiled graph using the same saver and separately durable store.
    Responses contain actor outputs, never an evaluator/rubric/reference object.
    """
    blockers = fixture_capability(binding)
    if blockers:
        raise ValueError(",".join(blockers))
    graph = binding.graph
    nodes = {n.id: n for n in graph.nodes}

    def step(state):
        # Admission binds the exact immutable snapshot and checks active identity,
        # cancellation, rights/expiry and zero-cost fixture policy at every step.
        store.admission(state["trial"], binding)
        state = {
            **state,
            "visits": dict(state["visits"]),
            "iterations": dict(state["iterations"]),
            "artifacts": dict(state["artifacts"]),
            "trace": list(state["trace"]),
        }
        if state["transitions"] >= graph.bounds.transitions:
            return {**state, "status": "transition_limit"}
        node = nodes[state["current"]]
        if any(a not in state["artifacts"] for a in node.inputs):
            return {**state, "status": "missing_input"}
        outcome = "next"
        visit = state["visits"].get(node.id, 0)
        if node.kind in {"agent_step", "human_step"}:
            key = f"{node.id}:{visit}:0"
            request = role_input(
                graph, node.id, node.role, state["artifacts"], set(state["visits"])
            )
            claim = store.claim(state["trial"], key, request)
            if claim["status"] == "completed":
                response = claim["response"]
            elif claim["status"] != "new":
                return {**state, "status": "unknown"}
            else:
                # Recheck after reservation and immediately before the effect.
                store.admission(state["trial"], binding)
                response = responses.get(key)
                if response is None:
                    # A missing response after committed intent remains Unknown;
                    # a replay never claims a fresh effect or releases its budget.
                    return {**state, "status": "unknown"}
                validate_response(node, response, graph)
                store.complete(state["trial"], key, response)
            validate_response(node, response, graph)
            state["artifacts"].update(response)
        elif node.kind == "decision":
            value = state["artifacts"].get(node.decision_artifact, {}).get(node.decision_field)
            outcome = "true" if value is True else "false" if value is False else "unknown"
        elif node.kind in {"output", "escalation"}:
            state["status"] = "completed" if node.kind == "output" else "escalated"
        state["visits"][node.id] = visit + 1
        state["transitions"] += 1
        edges = [e for e in graph.edges if e.source == node.id and e.outcome == outcome]
        if edges:
            edge = edges[0]
            if edge.loop:
                loop = next(loop for loop in graph.loops if loop.id == edge.loop)
                count = state["iterations"].get(loop.id, 0)
                if count >= loop.max_iterations:
                    edge = next(
                        e for e in graph.edges if e.source == node.id and e.outcome == "exhausted"
                    )
                    outcome = "exhausted"
                else:
                    state["iterations"][loop.id] = count + 1
                    # Never retain output from a previous loop iteration as new
                    # evidence. Sequential subset has one unambiguous loop body.
                    cursor, region = edge.target, set()
                    while cursor != node.id:
                        region.add(cursor)
                        cursor = next(
                            e.target
                            for e in graph.edges
                            if e.source == cursor and not e.loop and e.outcome == "next"
                        )
                    for artifact in graph.artifacts:
                        if artifact.producer in region:
                            state["artifacts"].pop(artifact.id, None)
            state["current"] = edge.target
        state["trace"].append(
            {
                "node": node.id,
                "visit": visit,
                "outcome": outcome,
                "response_mode": "Scripted human response"
                if node.kind == "human_step"
                else "Software fixture",
            }
        )
        return state

    builder = StateGraph(State)
    builder.add_node("step", step)
    builder.add_edge(START, "step")
    builder.add_conditional_edges("step", lambda s: "step" if s["status"] == "running" else END)
    return builder.compile(checkpointer=checkpointer)


def initial_state(trial, binding):
    return {
        "trial": trial,
        "current": binding.graph.entry,
        "transitions": 0,
        "visits": {},
        "iterations": {},
        "artifacts": {},
        "trace": [],
        "status": "running",
    }
