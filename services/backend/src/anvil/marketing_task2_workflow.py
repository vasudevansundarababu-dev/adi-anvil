"""Bounded execution of the published five-role graph, with durable effect custody.

The host supplies role-bound candidate and fixture adapters. This interpreter
grants no provider authority, fixture approval, Harbor qualification or score.
SQL effect claims must commit before invoking an adapter; an uncertain claim is
never reclaimed. LangGraph checkpoints hold public artifacts only.
"""

from copy import deepcopy
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from anvil.db import digest
from anvil.praxis_marketing_contract import MarketingExecution


class State(TypedDict):
    pending: list[str]
    artifacts: dict
    completed: dict
    visits: dict
    loops: dict
    week: int
    transitions: int
    terminal: str | None
    reason: str | None


def released_artifacts(context, released):
    """Preexisting host evidence only; a missing manifest stays absent."""
    artifacts = {"campaign_context": deepcopy(context), "released_evidence": deepcopy(released)}
    if released.get("baseline_delivery_manifest") is not None:
        from anvil.marketing_paid_world import BaselineDescriptors, OpeningBaselineDescriptors

        manifest_type = OpeningBaselineDescriptors if released.get("phase") == "opening" else BaselineDescriptors
        manifest = manifest_type.model_validate(released["baseline_delivery_manifest"])
        if manifest.case_id != context.get("case_id") or manifest.week != released["week"]:
            raise ValueError("Baseline descriptor evidence belongs to another released case/window")
        artifacts["delivery_manifest"] = manifest.model_dump(mode="json")
    return artifacts


def initial(context, released):
    return {
        "pending": ["start"],
        "artifacts": released_artifacts(context, released),
        "completed": {},
        "visits": {},
        "loops": {},
        "week": 1,
        "transitions": 0,
        "terminal": None,
        "reason": None,
    }


def initial_opening(context, released):
    """Start from an actual API opening artifact, never a synthesized plan.

    Receipt/source provenance is checked by the API/native caller separately;
    the workflow still executes every published role/tool transition at index0.
    """
    if (type(released) is not dict or type(released.get("week")) is not int
            or released["week"] != 0 or released.get("phase") != "opening"
            or released.get("operator_program_id") != "marketing-opening0-and-twelve-reviews-v1"
            or type(released.get("world_receipt_ref")) is not str or not released["world_receipt_ref"]):
        raise ValueError("Actual explicit opening release artifact required")
    state = initial(context, released)
    state["week"] = 0
    return state


def stop(state, reason):
    state.update(pending=[], terminal="awaiting_authority", reason=reason)
    return state


def field(artifacts, path):
    value = artifacts
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None, False
        value = value[key]
    return value, True


def advance(execution, state, effect, release):
    """One deterministic transition; callbacks receive only exact public inputs.

    effect(node, inputs, week, visit) is a host journal, not an actor tool. It
    returns a completed receipt or raises on uncertainty. release(next_week)
    reads host-controlled fixtures and must prove that exact window is released.
    """
    contract = MarketingExecution.model_validate(execution)
    graph = contract.workflow_graph
    state = deepcopy(state)
    if state["terminal"] or not state["pending"]:
        return state
    if state["transitions"] >= graph["limits"]["maxTransitions"]:
        return stop(state, "transition_limit")
    nodes = {node["id"]: node for node in graph["nodes"]}
    node_id = state["pending"].pop(0)
    node = nodes[node_id]
    state["transitions"] += 1
    edges = [edge for edge in graph["edges"] if edge["from"] == node_id]
    port = None
    kind = node["type"]
    if kind == "escalation":
        return stop(state, node["reason"])
    if kind == "output":
        if (
            state["week"] != 12
            or state["completed"].get("weekly", []) not in (list(range(1, 13)), list(range(13)))
            or node["deliverable"] not in state["artifacts"]
        ):
            return stop(state, "complete_twelve_window_evidence_required")
        state.update(terminal="done", pending=[])
        return state
    if kind == "join":
        if not all(
            state["week"] in state["completed"].get(key, []) for key in node["requiredInputs"]
        ):
            # The other fork is still pending. Its edge will visit this join.
            if not state["pending"]:
                return stop(state, "missing_required_join_producer")
            return state
        if state["week"] in state["completed"].get(node_id, []):
            return state
    elif kind == "decision":
        port = "else"
        for condition in node["conditions"]:
            value, present = field(state["artifacts"], condition["field"])
            if not present:
                port = "unknown"
                break
            # Python considers False == 0; workflow wire equality does not.
            if type(value) is type(condition["value"]) and value == condition["value"]:
                port = condition["id"]
                break
        if node_id == "campaign_over":
            if port == "final" and state["week"] != 12:
                return stop(state, "candidate_cannot_end_campaign_before_window_twelve")
            if port == "next_week" and state["week"] >= 12:
                return stop(state, "campaign_window_limit")
    elif kind in {"agent_step", "external_system", "human_step"}:
        refs = node.get("inputRefs", node.get("sendsRefs", node.get("permittedEvidence", [])))
        if any(ref not in state["artifacts"] for ref in refs):
            return stop(state, "missing_exact_input_artifact:" + node_id)
        inputs = {ref: deepcopy(state["artifacts"][ref]) for ref in refs}
        visit = state["visits"].get(node_id, 0) + 1
        result = effect(deepcopy(node), inputs, state["week"], visit)
        if not isinstance(result, dict) or not isinstance(result.get("receipt"), dict):
            raise ValueError("Completed host effect receipt required")
        if result["receipt"].get("input_sha256") != digest(inputs):
            raise ValueError("Effect receipt differs from exact workflow inputs")
        state["visits"][node_id] = visit
        artifact = node.get("outputArtifact", node.get("returnsArtifact"))
        if artifact:
            if not isinstance(result.get("artifact"), dict):
                return stop(state, "missing_bound_output_artifact:" + node_id)
            state["artifacts"][artifact] = deepcopy(result["artifact"])
        if kind == "human_step":
            port = result.get("port")
            if port not in {"responded", "timeout"}:
                return stop(state, "exact_simulated_approval_receipt_required")
    elif kind != "input":
        raise ValueError("Unsupported graph node")
    state["completed"].setdefault(node_id, []).append(state["week"])
    if port is not None:
        edges = [edge for edge in edges if edge.get("port") == port]
    if not edges:
        return stop(state, "missing_exact_graph_edge:" + node_id)
    for edge in edges:
        loop = next((loop for loop in graph["loops"] if loop["returnEdgeId"] == edge["id"]), None)
        if loop:
            # Revision allowances apply to each reporting cycle, not a hidden
            # global reduction of the published two-round allowance.
            key = loop["id"] if loop["id"] == "weekly_cycle" else f"{loop['id']}:{state['week']}"
            count = state["loops"].get(key, 0) + 1
            if count > loop["maxIterations"]:
                return stop(state, "loop_limit:" + loop["id"])
            state["loops"][key] = count
            if loop["id"] == "weekly_cycle":
                window = release(state["week"] + 1)
                if not isinstance(window, dict) or window.get("week") != state["week"] + 1:
                    return stop(state, "next_window_not_released")
                # Previous-cycle outputs must not satisfy a new-cycle join or
                # decision. Preserve only host context and released evidence.
                state["week"] += 1
                state["artifacts"] = released_artifacts(state["artifacts"]["campaign_context"], window)
        if edge["to"] not in state["pending"]:
            state["pending"].append(edge["to"])
    return state


def compile_graph(execution, effect, release, checkpointer):
    MarketingExecution.model_validate(execution)
    graph = StateGraph(State)
    graph.add_node("transition", lambda state: advance(execution, state, effect, release))
    graph.add_edge(START, "transition")
    graph.add_conditional_edges(
        "transition", lambda state: END if state["terminal"] else "transition"
    )
    return graph.compile(checkpointer=checkpointer)
