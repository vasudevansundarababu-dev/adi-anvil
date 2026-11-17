"""Durable bounded graph scheduling; adapters own isolated actor execution.

The journal serializes admission and state mutations. Adapter calls happen only
after committed one-way claims, outside SQL locks. Restarts never resend claims.
This module does not grant native qualification, credentials or paid authority.
"""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from anvil.db import digest
from anvil.workflow_fixture_runtime import validate_response
from anvil.workflow_projection import role_input

TERMINAL = {"completed", "escalated", "cancelled", "expired", "unknown", "failed"}


def validate_output(node, response, graph):
    if len(json.dumps(response, allow_nan=False).encode()) > 65536:
        raise ValueError("workflow_response_size_limit")
    validate_response(node, response, graph)


def initial(binding):
    return {
        "schema": "anvil.workflow-runtime.v1",
        "binding_sha256": digest(binding.model_dump()),
        "status": "running",
        "nodes": {n.id: "pending" for n in binding.graph.nodes},
        "edges": {e.id: None for e in binding.graph.edges if not e.loop},
        "visits": {},
        "iterations": {},
        "artifacts": {},
        "effects": {},
        "humans": {},
        "transitions": 0,
        "calls": 0,
        "trace": [],
    }


class Runtime:
    """Journal.update(fn) must admit, lock, mutate and commit before returning.

    The journal must bind this definition, actor, project, source rights and
    expiry on every update. Native adapters must recheck their own lease and paid
    admission before any effect. Values returned to adapters are role projections.
    """

    def __init__(self, binding, journal, adapter, *, workers=4):
        if type(workers) is not int or not 1 <= workers <= 16:
            raise ValueError("workflow_worker_bound")
        self.binding, self.journal, self.adapter = binding, journal, adapter
        self.graph = binding.graph
        self.nodes = {n.id: n for n in self.graph.nodes}
        self.workers = workers

    def _check(self, state):
        if state["binding_sha256"] != digest(self.binding.model_dump()):
            raise ValueError("workflow_binding_changed")

    def _event(self, state, node, outcome, **extra):
        state["trace"].append(
            {"index": len(state["trace"]), "node": node, "outcome": outcome, **extra}
        )

    def _route(self, state, node, outcome):
        selected = [e for e in self.graph.edges if e.source == node.id and e.outcome == outcome]
        loop_edge = next((e for e in selected if e.loop), None)
        if loop_edge:
            loop = next(x for x in self.graph.loops if x.id == loop_edge.loop)
            count = state["iterations"].get(loop.id, 0)
            if count >= loop.max_iterations:
                outcome = "exhausted"
                selected = [
                    e for e in self.graph.edges if e.source == node.id and e.outcome == outcome
                ]
            else:
                state["iterations"][loop.id] = count + 1
                forward = {n: [] for n in self.nodes}
                reverse = {n: [] for n in self.nodes}
                for edge in self.graph.edges:
                    if not edge.loop:
                        forward[edge.source].append(edge.target)
                        reverse[edge.target].append(edge.source)

                def reach(start, adjacency):
                    seen, todo = set(), [start]
                    while todo:
                        cursor = todo.pop()
                        if cursor not in seen:
                            seen.add(cursor)
                            todo.extend(adjacency[cursor])
                    return seen

                region = reach(loop_edge.target, forward) & reach(loop_edge.source, reverse)
                # A concurrent uncompleted effect cannot be reset or orphaned.
                if any(state["nodes"][n] in {"running", "waiting_human"} for n in region):
                    raise ValueError("workflow_loop_has_pending_effect")
                for n in region:
                    state["nodes"][n] = "pending"
                for edge in self.graph.edges:
                    if not edge.loop and edge.source in region:
                        state["edges"][edge.id] = None
                for artifact in self.graph.artifacts:
                    if artifact.producer in region:
                        state["artifacts"].pop(artifact.id, None)
                self._event(state, node.id, "loop_return", loop=loop.id, iteration=count + 1)
                return
        chosen = {e.id for e in selected}
        for edge in self.graph.edges:
            if edge.source == node.id and not edge.loop:
                state["edges"][edge.id] = edge.id in chosen
        self._event(state, node.id, outcome)

    def _finish(self, state, node, response=None, outcome="next"):
        if response is not None:
            validate_output(node, response, self.graph)
            state["artifacts"].update(copy.deepcopy(response))
        state["nodes"][node.id] = "completed"
        state["visits"][node.id] = state["visits"].get(node.id, 0) + 1
        self._route(state, node, outcome)

    def _prepare(self, state, now):
        self._check(state)
        if state["status"] in TERMINAL:
            return []
        # Only the worker that owns a returned claim can finish it. A later tick
        # seeing a committed actor intent cannot know whether external IO occurred.
        if any(n == "running" for n in state["nodes"].values()):
            state["status"] = "unknown"
            return []
        for key, wait in state["humans"].items():
            node = self.nodes[wait["node"]]
            if state["nodes"][node.id] != "waiting_human":
                continue
            if wait["status"] == "answered":
                self._finish(
                    state,
                    node,
                    wait["response"] if wait.get("outcome", "next") == "next" else None,
                    outcome=wait.get("outcome", "next"),
                )
                wait["status"] = "consumed"
            elif now >= datetime.fromisoformat(wait["deadline"]):
                wait["status"] = "timed_out"
                self._finish(state, node, outcome="timeout")
        claims = []
        changed = True
        while changed:
            changed = False
            for node in self.graph.nodes:
                if state["nodes"][node.id] != "pending":
                    continue
                incoming = [e for e in self.graph.edges if e.target == node.id and not e.loop]
                values = [state["edges"][e.id] for e in incoming]
                if any(v is None for v in values):
                    continue
                if node.id != self.graph.entry and (
                    not any(values) or (node.kind == "join" and not all(values))
                ):
                    state["nodes"][node.id] = "skipped"
                    for edge in self.graph.edges:
                        if edge.source == node.id and not edge.loop:
                            state["edges"][edge.id] = False
                    changed = True
                    continue
                if state["transitions"] >= self.graph.bounds.transitions:
                    state["status"] = "failed"
                    self._event(state, node.id, "transition_limit")
                    return []
                if any(a not in state["artifacts"] for a in node.inputs):
                    state["status"] = "failed"
                    self._event(state, node.id, "missing_required_input")
                    return []
                if (
                    node.kind in {"agent_step", "human_step"}
                    and node.human_mode != "actual"
                    and len(claims) >= self.workers
                ):
                    continue
                state["transitions"] += 1
                changed = True
                if node.kind in {"agent_step", "human_step"}:
                    key = f"{node.id}:{state['visits'].get(node.id, 0)}"
                    request = role_input(
                        self.graph,
                        node.id,
                        node.role,
                        state["artifacts"],
                        {n for n, status in state["nodes"].items() if status == "completed"},
                    )
                    request["response_mode"] = (
                        "Actual human response" if node.human_mode == "actual" else "Actor response"
                    )
                    if node.human_mode == "actual":
                        from datetime import timedelta

                        state["nodes"][node.id] = "waiting_human"
                        state["humans"][key] = {
                            "node": node.id,
                            "role": node.role,
                            "request": request,
                            "request_sha256": digest(request),
                            "status": "waiting",
                            "deadline": (now + timedelta(seconds=node.timeout_seconds)).isoformat(),
                        }
                        self._event(state, node.id, "waiting_human", request_key=key)
                    else:
                        if state["calls"] >= self.graph.bounds.calls:
                            state["status"] = "failed"
                            self._event(state, node.id, "call_limit")
                            return []
                        state["calls"] += 1
                        state["nodes"][node.id] = "running"
                        state["effects"][key] = {
                            "status": "dispatched",
                            "request_sha256": digest(request),
                            "call_index": state["calls"] - 1,
                        }
                        claims.append((key, request))
                elif node.kind == "decision":
                    value = state["artifacts"][node.decision_artifact][node.decision_field]
                    self._finish(
                        state,
                        node,
                        outcome="true"
                        if value is True
                        else "false"
                        if value is False
                        else "unknown",
                    )
                else:
                    self._finish(state, node)
        if not claims:
            pending = set(state["nodes"].values())
            if "waiting_human" in pending:
                state["status"] = "waiting_human"
            elif "pending" in pending:
                state["status"] = "failed"
                self._event(state, self.graph.entry, "unresolved_dependencies")
            else:
                escalated = any(
                    n.kind == "escalation" and state["nodes"][n.id] == "completed"
                    for n in self.graph.nodes
                )
                state["status"] = "escalated" if escalated else "completed"
        else:
            state["status"] = "running"
        return claims

    def tick(self, *, now=None):
        with self.journal.scheduler():
            self.journal.restore_answers()
            return self._tick(now=now)

    def _tick(self, *, now=None):
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("aware_workflow_clock_required")
        claims = self.journal.update(lambda state: self._prepare(state, now))

        def execute(claim):
            key, request = claim
            try:
                # A journal read/admission immediately before external IO; no
                # claim replay if cancellation/revocation or process death wins.
                self.journal.admission()
                response = self.adapter.invoke(key, copy.deepcopy(request))
                node = self.nodes[request["node_id"]]
                validate_output(node, response, self.graph)
            except Exception:

                def unknown(state):
                    state["effects"][key]["status"] = "unknown"
                    state["status"] = "unknown"
                    self._event(state, request["node_id"], "dispatch_unknown")

                self.journal.update(unknown)
                return

            def complete(state):
                effect = state["effects"][key]
                if effect["status"] != "dispatched" or state["status"] in TERMINAL:
                    return
                effect.update(
                    status="completed",
                    response=copy.deepcopy(response),
                    response_sha256=digest(response),
                )
                self._finish(state, node, response)

            self.journal.update(complete)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            list(pool.map(execute, claims))
        return self.journal.snapshot()


def answer(state, binding, key, actor, response, now, outcome="next"):
    """Called only after journal checks the exact persisted role assignment."""
    wait = state["humans"].get(key)
    if not wait or wait["status"] != "waiting" or now >= datetime.fromisoformat(wait["deadline"]):
        raise ValueError("human_request_closed_or_expired")
    node = next(n for n in binding.graph.nodes if n.id == wait["node"])
    if outcome == "next":
        validate_output(node, response, binding.graph)
    elif outcome != "error" or response != {}:
        raise ValueError("human_error_response_must_be_empty")
    wait.update(
        status="answered",
        actor=str(actor),
        response=copy.deepcopy(response),
        response_sha256=digest(response),
        outcome=outcome,
    )


def plan_native_wave(runtime, now):
    """LangGraph coordinates one API wave; SQL owns checkpoints and effect IDs.

    No candidate IO occurs inside this graph. Re-entering after a lost worker
    observes the committed journal intent and becomes Unknown, never a retry.
    The caller holds the journal scheduler fence across this bounded invocation.
    """
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    class WaveState(TypedDict):
        execution_id: str
        claims: list

    def restore(state):
        if state["execution_id"] != runtime.journal.execution:
            raise ValueError("workflow_checkpoint_binding_changed")
        runtime.journal.restore_answers()
        return {}

    def schedule(state):
        return {"claims": runtime.journal.update(lambda value: runtime._prepare(value, now))}

    graph = StateGraph(WaveState)
    graph.add_node("restore_human_receipts", restore)
    graph.add_node("schedule_bounded_wave", schedule)
    graph.add_edge(START, "restore_human_receipts")
    graph.add_edge("restore_human_receipts", "schedule_bounded_wave")
    graph.add_edge("schedule_bounded_wave", END)
    return graph.compile().invoke({"execution_id": runtime.journal.execution, "claims": []})[
        "claims"
    ]


def compile_coordinator(runtime, checkpointer):
    """LangGraph pause/resume over the authoritative SQL journal.

    Resume payloads never become human answers. The authenticated answer ledger
    must already contain the response. Checkpoints contain no provider secrets,
    expected answers or role artifacts, and cannot override the journal binding.
    """
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt

    class CoordinatorState(TypedDict):
        execution_id: str
        status: str

    def advance(state):
        if state["execution_id"] != runtime.journal.execution:
            raise ValueError("workflow_checkpoint_binding_changed")
        result = runtime.tick()
        return {"status": result["status"]}

    def wait(state):
        runtime.journal.admission()
        snapshot = runtime.journal.snapshot()
        interrupt(
            {
                "execution_id": state["execution_id"],
                "request_keys": [
                    key for key, value in snapshot["humans"].items() if value["status"] == "waiting"
                ],
                "answer_via": "authenticated_workflow_human_answers",
            }
        )
        return {}

    graph = StateGraph(CoordinatorState)
    graph.add_node("advance", advance)
    graph.add_node("human_wait", wait)
    graph.add_edge(START, "advance")
    graph.add_conditional_edges(
        "advance",
        lambda state: (
            "advance"
            if state["status"] == "running"
            else "human_wait"
            if state["status"] == "waiting_human"
            else END
        ),
    )
    graph.add_edge("human_wait", "advance")
    return graph.compile(checkpointer=checkpointer)
