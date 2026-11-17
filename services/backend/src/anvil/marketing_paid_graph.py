"""Durable published graph over role MCP and the API-only SDK broker.

The trusted runtime supplies a qualified world and native liveness guard. This
inner executor grants neither a Harbor operation nor fixture/source qualification.
It cannot resolve a model key or send a provider request directly.
"""

import math
from contextlib import contextmanager
from threading import Lock

from anvil.db import digest
from anvil.golden_phase_checkpoints import ScopedSaver
from anvil.marketing_graph_result import validate_graph_result
from anvil.marketing_mcp import MarketingMcpEpisode
from anvil.marketing_paid_contract import campaign_output
from anvil.marketing_paid_roles import RoleAdapter
from anvil.marketing_task2_workflow import compile_graph, initial_opening
from anvil.marketing_task2_workflow_store import Journal
from anvil.praxis_generic_contract import digest as wire_digest
from anvil.worker_dispatch_broker import forward


class GraphRunner:
    def __init__(
        self,
        connections,
        job,
        prepared,
        world,
        *,
        absolute_deadline=None,
        dispatch=forward,
        checkpointer=None,
    ):
        if (
            prepared.get("mode") != "marketing-native"
            or prepared["native_binding"]["case_assignment"]["case_id"] != world.case_id
        ):
            raise ValueError("Exact prepared campaign case and trusted world required")
        self.connections, self.job, self.prepared, self.world = connections, job, prepared, world
        self.execution = prepared["execution"]
        if wire_digest(self.execution) != prepared["native_binding"]["execution_sha256"]:
            raise ValueError("Exact published campaign execution required")
        if absolute_deadline is None:
            raise ValueError("Trusted outer campaign absolute deadline required")
        if (type(absolute_deadline) not in (int, float)
                or not math.isfinite(absolute_deadline)
                or absolute_deadline > world._deadline):
            raise ValueError("Graph phase must fit original world deadline")
        self._deadline = absolute_deadline
        self._run_started = False
        self._run_lock = Lock()
        self.dispatch, self.saver = dispatch, checkpointer or ScopedSaver(connections)
        self.native_guard = None
        self.roles = RoleAdapter(
            connections,
            job,
            world.episode_id,
            world.generation,
            self.execution,
            self._dispatch,
            self._client,
            episode_timeout_seconds=prepared["episode_timeout_seconds"],
            absolute_deadline=absolute_deadline,
        )

    def guard(self):
        if self.native_guard is None or self.native_guard() is not True:
            raise RuntimeError("marketing_native_coordinator_liveness_required")
        self.roles.remaining()
        with self.connections() as c:
            if not c.execute(
                "SELECT marketing_runtime.heartbeat_paid_agent_job(%s,%s) AS allowed",
                (self.job["id"], self.job["lease_token"]),
            ).fetchone()["allowed"]:
                raise RuntimeError("marketing_current_attempt_and_deadline_required")
        if (
            self.dispatch(
                self.job, self.job["actor_id"], self.job["plan_id"], 0, operation="readiness",
                remaining_seconds=min(self.roles.remaining(), self.prepared["request_timeout_seconds"]),
                absolute_deadline=self._deadline,
            )
            is not True
        ):
            raise RuntimeError("marketing_current_source_model_budget_authority_required")
        self.roles.remaining()
        return True

    def _dispatch(self, stage, context, remaining):
        self.guard()
        result = self.dispatch(
            self.job,
            self.job["actor_id"],
            self.job["plan_id"],
            stage,
            remaining_seconds=min(remaining, self.roles.remaining(), self.prepared["request_timeout_seconds"]),
            absolute_deadline=self._deadline,
        )
        self.guard()
        return result

    @contextmanager
    def _client(self, role, before_effect):
        env = self.world.role_environment(role, phase_deadline=self._deadline)
        env.reset()  # Attach the role; never reset the shared episode.
        scope = {
            "schema_version": "anvil.marketing-mcp-scope.v1",
            "project_id": str(self.job["project_id"]),
            "trial_id": str(self.world.episode_id),
            "generation": self.world.generation,
            "role": role,
            "workflow_graph_sha256": self.execution["workflow_graph_sha256"],
        }
        try:
            with MarketingMcpEpisode(
                env, scope, self.guard, self.execution, before_effect=before_effect
            ) as client:
                yield client
        finally:
            env.close()

    def _effect(self, node, inputs, week, visit):
        self.guard()
        if node["type"] == "agent_step":
            return self.roles(node, inputs, week, visit)
        value = self.world.effect(node, inputs, week, visit, phase_deadline=self._deadline)
        self.guard()
        return value

    def _release(self, week):
        self.guard()
        value = self.world.release(week, phase_deadline=self._deadline)
        if not isinstance(value, dict) or value.get("week") != week:
            raise RuntimeError("marketing_exact_host_released_window_required")
        return value

    def run(self, native_guard):
        if self._run_started or not self._run_lock.acquire(blocking=False):
            raise RuntimeError("marketing_graph_object_consumed_no_replay")
        # Consumed before guard/checkpoint/graph: an early failure does not grant
        # another attempt merely because no checkpoint was written yet.
        self._run_started = True
        self.native_guard = native_guard
        self.guard()
        config = {
            "configurable": {
                "thread_id": f"marketing:{self.job['project_id']}:{self.job['plan_id']}:{self.world.episode_id}:{self.world.generation}",
                "checkpoint_ns": "",
            },
            "recursion_limit": 410,
        }
        if self.saver.get_tuple(config) is not None:
            raise RuntimeError("marketing_existing_attempt_checkpoint_no_replay")
        journal = Journal(
            self.connections,
            self.job["project_id"],
            self.job["actor_id"],
            self.world.episode_id,
            self.world.generation,
            self.execution,
            self._effect,
            paid_job=self.job,
        )
        graph = compile_graph(self.execution, journal, self._release, self.saver)
        opening = self.world.opening(phase_deadline=self._deadline)
        state = graph.invoke(
            initial_opening(self.world.campaign_context, opening), config, durability="sync"
        )
        self.guard()
        with self.connections() as c:
            effects = c.execute(
                "SELECT id,node_id,week,result,result_sha256 FROM marketing_runtime.workflow_effects WHERE project_id=%s AND episode_id=%s AND generation=%s AND execution_sha256=%s AND state='completed' ORDER BY week,node_id,visit",
                (
                    self.job["project_id"],
                    self.world.episode_id,
                    self.world.generation,
                    wire_digest(self.execution),
                ),
            ).fetchall()
            turns = c.execute(
                "SELECT count(*) AS n FROM marketing_runtime.paid_turn_observations WHERE project_id=%s AND plan_id=%s",
                (self.job["project_id"], self.job["plan_id"]),
            ).fetchone()["n"]
        if any(digest(row["result"]) != row["result_sha256"] for row in effects):
            raise RuntimeError("marketing_completed_graph_effect_custody_changed")
        refs = {
            str(row["id"]): "marketing-effect:" + str(row["id"]) + ":" + row["result_sha256"]
            for row in effects
        }
        weekly = [refs[str(row["id"])] for row in effects if row["node_id"] == "weekly" and row["week"] > 0]
        opening_refs = [refs[str(row["id"])] for row in effects if row["week"] == 0]
        closeout = [refs[str(row["id"])] for row in effects if row["node_id"] == "closeout"]
        closed = state["terminal"] == "done"
        output = campaign_output(
            self.execution,
            status="campaign_closed" if closed else "awaiting_authority",
            weekly_review_refs=weekly,
            evidence_refs=list(refs.values()),
            closeout_report_ref=closeout[-1] if closed and closeout else None,
            hold_reason=state.get("reason") if not closed else None,
            workflow_state=state,
        )
        receipt = {
            "schema_version": "anvil.marketing-paid-graph-receipt.v2",
            "project_id": str(self.job["project_id"]),
            "job_id": str(self.job["id"]),
            "plan_id": str(self.job["plan_id"]),
            "trial_id": str(self.world.episode_id),
            "generation": self.world.generation,
            "execution_sha256": wire_digest(self.execution),
            "workflow_state_sha256": wire_digest(state),
            "output_sha256": wire_digest(output),
            "turns": turns,
            "closed": closed,
            "completed_weeks": [week for week in state["completed"].get("weekly", []) if week > 0],
            "opening_completed": 0 in state["completed"].get("weekly", []),
            "opening_effect_refs": opening_refs,
            "opening_release_ref": opening["world_receipt_ref"],
            "model_performance_validated": False,
        }
        result = (output, receipt)
        validate_graph_result(
            result, job=self.job, prepared=self.prepared, world=self.world, workflow_state=state
        )
        self.guard()
        return result
