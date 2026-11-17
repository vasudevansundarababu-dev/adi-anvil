"""SQL effect journal for the published graph; no provider credentials or retries."""

import json

from anvil.db import Jsonb, digest, uid
from anvil.marketing_task2_store import locked
from anvil.praxis_generic_contract import digest as wire_digest
from anvil.praxis_marketing_contract import MarketingExecution


class Journal:
    def __init__(
        self, connections, project, user, episode, generation, execution, adapter, *, paid_job=None
    ):
        self.connections = connections
        self.project, self.user = project, user
        self.episode, self.generation = episode, generation
        self.execution = MarketingExecution.model_validate(execution).model_dump()
        self.execution_sha = wire_digest(self.execution)
        self.adapter = adapter
        self.paid_job = dict(paid_job) if paid_job is not None else None
        if self.paid_job is not None and (
            str(project) != str(self.paid_job["project_id"])
            or str(user) != str(self.paid_job["actor_id"])
        ):
            raise ValueError("Exact paid job project and assigned actor required")

    def guard(self, c, *, completing_effect=None):
        if self.paid_job is not None:
            parameters = (
                self.paid_job["id"],
                self.paid_job["lease_token"],
                self.paid_job["plan_id"],
                self.episode,
                self.generation,
                self.execution_sha,
            )
            query = "SELECT marketing_runtime.paid_episode_current(%s,%s,%s,%s,%s,%s) AS allowed"
            if completing_effect is not None:
                query = "SELECT marketing_runtime.paid_episode_completion_current(%s,%s,%s,%s,%s,%s,%s) AS allowed"
                parameters += (completing_effect,)
            if not c.execute(
                query,
                parameters,
            ).fetchone()["allowed"]:
                raise ValueError("Current paid world episode and frozen execution required")
            return
        locked(c, self.project, self.user, self.episode, self.generation)
        if not c.execute(
            "SELECT marketing_runtime.execution_guard(%s,%s,%s) AS allowed",
            (self.user, self.episode, self.generation),
        ).fetchone()["allowed"]:
            raise ValueError("Current assigned Marketing execution membership required")

    def __call__(self, node, inputs, week, visit):
        expected = next(
            (n for n in self.execution["workflow_graph"]["nodes"] if n["id"] == node["id"]), None
        )
        if expected != node or node["type"] not in {"agent_step", "human_step", "external_system"}:
            raise ValueError("Exact frozen effect node required")
        key = (
            self.project,
            self.episode,
            self.generation,
            self.execution_sha,
            node["id"],
            week,
            visit,
        )
        identifier = uid()
        with self.connections() as c:
            self.guard(c)
            row = c.execute(
                "SELECT * FROM marketing_runtime.workflow_effects WHERE (project_id,episode_id,generation,execution_sha256,node_id,week,visit)=(%s,%s,%s,%s,%s,%s,%s) FOR UPDATE",
                key,
            ).fetchone()
            if row:
                if row["input_sha256"] != digest(inputs) or row["node_sha256"] != digest(node):
                    raise RuntimeError("Frozen workflow effect inputs changed")
                if row["state"] != "completed":
                    raise RuntimeError(
                        "Marketing effect uncertain; reconciliation required, no replay"
                    )
                if digest(row["result"]) != row["result_sha256"]:
                    raise RuntimeError("Workflow effect receipt custody mismatch")
                return row["result"]
            c.execute(
                "INSERT INTO marketing_runtime.workflow_effects(id,project_id,episode_id,generation,execution_sha256,node_id,week,visit,node_sha256,input_sha256,state) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'claimed')",
                (identifier, *key, digest(node), digest(inputs)),
            )
        # The claim has committed. A crash or timeout from here never releases it
        # for another invocation, regardless of LangGraph checkpoint position.
        try:
            result = self.adapter(node, inputs, week, visit)
            if not isinstance(result, dict) or len(json.dumps(result).encode()) > 60000:
                raise ValueError("Bounded workflow effect result required")
            if not isinstance(result.get("receipt"), dict) or result["receipt"].get(
                "input_sha256"
            ) != digest(inputs):
                raise ValueError("Exact workflow effect receipt required")
            with self.connections() as c:
                self.guard(c, completing_effect=identifier)
                c.execute(
                    "UPDATE marketing_runtime.workflow_effects SET state='completed',result=%s,result_sha256=%s,completed_at=clock_timestamp() WHERE project_id=%s AND id=%s AND state='claimed'",
                    (Jsonb(result), digest(result), self.project, identifier),
                )
            return result
        except Exception:
            with self.connections() as c:
                c.execute(
                    "UPDATE marketing_runtime.workflow_effects SET state='execution_unknown',completed_at=clock_timestamp() WHERE project_id=%s AND id=%s AND state='claimed'",
                    (self.project, identifier),
                )
            raise
