"""LangGraph phase orchestration; PostgreSQL owns durable jobs, cells and seals.

The graph never transports credentials, private expectations or customer records
in its state. Disjoint worker connections enter only through the trusted closure.
Interrupted running jobs are retained and never automatically replayed.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from anvil.golden_kyc_execution import capture_run, finish_run, grade_run


class PhaseState(TypedDict):
    project: str
    result: dict | None


def execute_phase(connections, project, phase, *, max_cells=2000):
    if phase not in ("capture", "grade", "finish"):
        raise ValueError("Unsupported Golden orchestration phase")

    def perform(state):
        result = (
            capture_run(connections, state["project"], max_cells=max_cells)
            if phase == "capture"
            else grade_run(connections, state["project"])
            if phase == "grade"
            else finish_run(connections, state["project"])
        )
        return {"project": state["project"], "result": result}

    graph = StateGraph(PhaseState)
    graph.add_node(phase, perform)
    graph.add_edge(START, phase)
    graph.add_edge(phase, END)
    result = graph.compile().invoke({"project": str(project), "result": None})
    return result["result"]
