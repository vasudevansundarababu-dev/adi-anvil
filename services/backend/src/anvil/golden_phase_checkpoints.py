"""Durable LangGraph phase boundaries with short, project-scoped transactions.

An interrupted effect is retained for reconciliation. We do not resume or replay
candidate dispatch from a graph checkpoint; SQL lease/broker state owns effects.
"""

from contextlib import contextmanager
from typing import TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from psycopg.rows import dict_row

from anvil.praxis_generic_contract import digest

VERSION = "anvil.golden-native-phases.v1"


class ScopedSaver(PostgresSaver):
    """Each official saver operation commits independently of the long episode."""

    def __init__(self, connections):
        super().__init__(None, serde=JsonPlusSerializer(pickle_fallback=False))
        self.connections = connections

    @contextmanager
    def _locked(self):
        from anvil.marketing_native_wire_bounds import remaining

        deadline=getattr(self.connections,'absolute_deadline',None)
        if deadline is None:
            with self.lock:
                yield
            return
        if not self.lock.acquire(timeout=remaining(deadline)):
            raise TimeoutError('Original KYC checkpoint lock cutoff elapsed')
        try:
            remaining(deadline)
            yield
        finally:
            self.lock.release()

    @contextmanager
    def _cursor(self, *, pipeline=False):
        # The injected connection factory enforces the scheduler login/role and
        # transaction-local project. Never borrow ordinary-worker credentials.
        with self._locked(), self.connections() as connection:
            connection.execute("SET LOCAL search_path TO anvil_golden_checkpoints")
            with connection.cursor(binary=True, row_factory=dict_row) as cursor:
                yield cursor


class PhaseState(TypedDict):
    project_id: str
    job_id: str
    plan_id: str
    lease_sha256: str
    graph_version: str
    phase: str
    result_sha256: str | None


def execute(connections, job, operation, *, checkpointer=None):
    saver = ScopedSaver(connections) if checkpointer is None else checkpointer
    project, identifier = str(job["project_id"]), str(job["id"])
    lease = digest(str(job["lease_token"]))
    config = {
        "configurable": {
            "thread_id": project + ":" + identifier + ":" + lease,
            "checkpoint_ns": "",
        },
        "recursion_limit": 6,
    }
    if saver.get_tuple(config) is not None:
        raise RuntimeError("golden_phase_attempt_already_recorded_no_replay")
    outcome = {}

    def started(state):
        return {"phase": "native_attempt_started"}

    def perform(state):
        result = operation()
        outcome["value"] = result
        return {"phase": "native_attempt_finished", "result_sha256": digest(result)}

    graph = StateGraph(PhaseState)
    graph.add_node("attempt_started", started)
    graph.add_node("native_capture_and_finalize", perform)
    graph.add_edge(START, "attempt_started")
    graph.add_edge("attempt_started", "native_capture_and_finalize")
    graph.add_edge("native_capture_and_finalize", END)
    graph.compile(checkpointer=saver).invoke(
        {
            "project_id": project,
            "job_id": identifier,
            "plan_id": str(job["plan_id"]),
            "lease_sha256": lease,
            "graph_version": VERSION,
            "phase": "claimed",
            "result_sha256": None,
        },
        config,
        durability="sync",
    )
    return outcome["value"]
