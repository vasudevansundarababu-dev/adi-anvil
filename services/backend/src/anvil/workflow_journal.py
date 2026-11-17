"""Project-scoped durable graph journal; no provider credentials in its process."""

import copy
from contextlib import contextmanager
from datetime import datetime, timezone

from anvil.db import Jsonb, digest, one, transaction, uid
from anvil.workflow_contract import WorkflowBinding
from anvil.workflow_runtime import answer, initial


def create(c, project, actor, binding, assignments):
    # Native launch must be supplied by a separately qualified plan adapter,
    # never by changing a public request's mode or attaching a source sidecar.
    if binding.graph.bounds.cost_micro_usd != 0 or any(r.tools for r in binding.graph.roles):
        raise ValueError("workflow_conformance_no_paid_or_tools")
    human_roles = {n.role for n in binding.graph.nodes if n.human_mode == "actual"}
    if set(assignments) != human_roles:
        raise ValueError("exact_human_role_assignments_required")
    for actor_id in assignments.values():
        if not one(
            c,
            "SELECT 1 FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id WHERE u.id=%s AND u.active AND NOT u.is_synthetic AND m.project_id=%s AND m.active AND m.role IN ('admin','rl-engineer')",
            (actor_id, project),
        ):
            raise ValueError("active_real_human_assignment_required")
    state = initial(binding)
    return one(
        c,
        "INSERT INTO anvil.workflow_executions(id,project_id,created_by,binding,binding_sha256,mode,assignments,state,state_sha256,expires_at) VALUES(%s,%s,%s,%s,%s,'software_conformance',%s,%s,%s,now()+make_interval(secs=>%s)) RETURNING *",
        (
            uid(),
            project,
            actor,
            Jsonb(binding.model_dump()),
            digest(binding.model_dump()),
            Jsonb(assignments),
            Jsonb(state),
            digest(state),
            binding.graph.bounds.wall_seconds,
        ),
    )


class PostgresJournal:
    mode = "software_conformance"

    def __init__(self, project, actor, execution, binding):
        self.project, self.actor, self.execution, self.binding = project, actor, execution, binding

    def connection(self):
        return transaction(self.project, self.actor, worker=self.mode != "native")

    @contextmanager
    def scheduler(self):
        # Session-level lock spans IO without a row transaction. A second process
        # cannot mistake an active claim for a crash; process death releases it.
        with self.connection() as c:
            if not one(
                c,
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) ok",
                ("workflow:" + self.execution,),
            )["ok"]:
                raise ValueError("workflow_scheduler_busy")
            try:
                yield
            finally:
                c.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s,0))",
                    ("workflow:" + self.execution,),
                )

    def _row(self, c):
        row = one(
            c,
            "SELECT *,expires_at>now() AS current FROM anvil.workflow_executions WHERE id=%s FOR UPDATE",
            (self.execution,),
        )
        if (
            not row
            or str(row["project_id"]) != str(self.project)
            or str(row["created_by"]) != str(self.actor)
        ):
            raise ValueError("workflow_execution_unavailable")
        if row["cancel_requested"] or not row["current"]:
            raise ValueError("workflow_cancelled_or_expired")
        if (
            digest(row["binding"]) != row["binding_sha256"]
            or digest(self.binding.model_dump()) != row["binding_sha256"]
            or digest(row["state"]) != row["state_sha256"]
        ):
            raise ValueError("workflow_journal_integrity_changed")
        if row["mode"] != self.mode:
            raise ValueError("workflow_native_admission_required")
        if not one(
            c,
            "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active AND m.role IN ('admin','rl-engineer')",
            (self.project, self.actor),
        ):
            raise ValueError("workflow_authorization_revoked")
        return row

    def admission(self):
        with self.connection() as c:
            self._row(c)

    def update(self, fn):
        with self.connection() as c:
            row = self._row(c)
            state = copy.deepcopy(row["state"])
            event_count = len(state["trace"])
            result = fn(state)
            for key, wait in state["humans"].items():
                c.execute(
                    "INSERT INTO anvil.workflow_human_requests(project_id,execution_id,request_key,assigned_to,request_sha256,deadline) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (
                        self.project,
                        self.execution,
                        key,
                        row["assignments"][wait["role"]],
                        wait["request_sha256"],
                        wait["deadline"],
                    ),
                )
            for event in state["trace"][event_count:]:
                c.execute(
                    "INSERT INTO anvil.workflow_events(project_id,execution_id,event_index,event,event_sha256) VALUES(%s,%s,%s,%s,%s)",
                    (self.project, self.execution, event["index"], Jsonb(event), digest(event)),
                )
            c.execute(
                "UPDATE anvil.workflow_executions SET state=%s,state_sha256=%s WHERE id=%s",
                (Jsonb(state), digest(state), self.execution),
            )
            return result

    def restore_answers(self):
        with self.connection() as c:
            row = self._row(c)
            responses = c.execute(
                "SELECT * FROM anvil.workflow_human_answers WHERE execution_id=%s",
                (self.execution,),
            ).fetchall()

        def restore(state):
            for response in responses:
                key = response["request_key"]
                if state["humans"][key]["status"] != "waiting":
                    continue
                if (
                    str(response["actor_id"]) != row["assignments"][state["humans"][key]["role"]]
                    or digest(response["response"]) != response["response_sha256"]
                ):
                    raise ValueError("workflow_human_receipt_changed")
                with self.connection() as c:
                    if not one(
                        c,
                        "SELECT 1 FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id WHERE u.id=%s AND u.active AND NOT u.is_synthetic AND m.project_id=%s AND m.active AND m.role IN ('admin','rl-engineer')",
                        (response["actor_id"], self.project),
                    ):
                        raise ValueError("workflow_human_authorization_revoked")
                answer(
                    state,
                    self.binding,
                    key,
                    response["actor_id"],
                    response["response"],
                    response["created_at"],
                    response["outcome"],
                )

        self.update(restore)

    def snapshot(self):
        with self.connection() as c:
            return self._row(c)["state"]


def submit_answer(c, project, actor, execution, key, response, outcome="next"):
    row = one(
        c,
        "SELECT * FROM anvil.workflow_executions WHERE id=%s AND project_id=%s FOR UPDATE",
        (execution, project),
    )
    if not row or row["cancel_requested"]:
        raise ValueError("workflow_execution_unavailable")
    state = copy.deepcopy(row["state"])
    wait = state["humans"].get(key)
    if not wait or row["assignments"][wait["role"]] != str(actor):
        raise ValueError("workflow_human_assignment_denied")
    answer(
        state,
        WorkflowBinding.model_validate(row["binding"]),
        key,
        actor,
        response,
        datetime.now(timezone.utc),
        outcome,
    )
    c.execute(
        "INSERT INTO anvil.workflow_human_answers(project_id,execution_id,request_key,actor_id,response,response_sha256,outcome) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (project, execution, key, actor, Jsonb(response), digest(response), outcome),
    )
