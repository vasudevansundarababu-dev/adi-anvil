"""PostgreSQL effect ledger for zero-cost software conformance, never live calls."""

from anvil.db import Jsonb, digest, one, transaction, uid
from anvil.workflow_contract import WorkflowBinding
from anvil.workflow_fixture_runtime import fixture_capability, validate_response
from anvil.workflow_projection import role_input


def create(c, project, actor, binding):
    if binding.graph.bounds.cost_micro_usd != 0 or fixture_capability(binding):
        raise ValueError("unsupported_software_fixture")
    row = one(
        c,
        "INSERT INTO anvil.workflow_fixture_trials(id,project_id,created_by,binding,binding_sha256,expires_at) "
        "VALUES(%s,%s,%s,%s,%s,now()+make_interval(secs=>%s)) RETURNING *",
        (
            uid(),
            project,
            actor,
            Jsonb(binding.model_dump()),
            digest(binding.model_dump()),
            binding.graph.bounds.wall_seconds,
        ),
    )
    return row


class PostgresFixtureStore:
    def __init__(self, project, actor):
        self.project, self.actor = project, actor

    def _admit(self, c, trial, binding=None):
        row = one(
            c,
            "SELECT *,expires_at>now() AS current FROM anvil.workflow_fixture_trials WHERE id=%s FOR UPDATE",
            (trial,),
        )
        if (
            not row
            or str(row["project_id"]) != str(self.project)
            or str(row["created_by"]) != str(self.actor)
        ):
            raise ValueError("fixture_trial_unavailable")
        if row["cancel_requested"] or not row["current"]:
            raise ValueError("fixture_cancelled_or_expired")
        if digest(row["binding"]) != row["binding_sha256"] or (
            binding and digest(binding.model_dump()) != row["binding_sha256"]
        ):
            raise ValueError("fixture_binding_changed")
        if not one(
            c,
            "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active AND m.role IN ('admin','rl-engineer')",
            (self.project, self.actor),
        ):
            raise ValueError("fixture_membership_revoked")
        parsed = WorkflowBinding.model_validate(row["binding"])
        if parsed.graph.bounds.cost_micro_usd != 0 or fixture_capability(parsed):
            raise ValueError("unsupported_software_fixture")
        return row, parsed

    def admission(self, trial, binding):
        with transaction(self.project, self.actor, worker=True) as c:
            self._admit(c, trial, binding)

    def claim(self, trial, key, request):
        with transaction(self.project, self.actor, worker=True) as c:
            _, binding = self._admit(c, trial)
            parts = key.split(":")
            node = next((n for n in binding.graph.nodes if n.id == parts[0]), None)
            if (
                len(parts) != 3
                or not node
                or not parts[1].isascii()
                or not parts[1].isdecimal()
                or int(parts[1]) >= binding.graph.bounds.transitions
                or parts[2] != "0"
            ):
                raise ValueError("fixture_effect_key_invalid")
            completed = {
                a.producer for a in binding.graph.artifacts if a.id in request.get("inputs", {})
            }
            expected = role_input(
                binding.graph, node.id, node.role, request.get("inputs", {}), completed
            )
            if request != expected:
                raise ValueError("fixture_actor_request_invalid")
            prior = one(
                c,
                "SELECT * FROM anvil.workflow_fixture_effects WHERE trial_id=%s AND effect_key=%s",
                (trial, key),
            )
            if prior:
                if prior["request_sha256"] != digest(request):
                    raise ValueError("fixture_effect_request_changed")
                if (
                    prior["status"] == "completed"
                    and digest(prior["response"]) != prior["response_sha256"]
                ):
                    raise ValueError("fixture_receipt_changed")
                return {"status": prior["status"], "response": prior["response"]}
            count = one(
                c,
                "SELECT count(*) AS n FROM anvil.workflow_fixture_effects WHERE trial_id=%s",
                (trial,),
            )["n"]
            if count >= binding.graph.bounds.calls:
                raise ValueError("fixture_call_limit")
            one(
                c,
                "INSERT INTO anvil.workflow_fixture_effects(project_id,trial_id,effect_key,request_sha256,status) VALUES(%s,%s,%s,%s,'dispatched') RETURNING effect_key",
                (self.project, trial, key, digest(request)),
            )
            return {"status": "new"}

    def complete(self, trial, key, response):
        with transaction(self.project, self.actor, worker=True) as c:
            _, binding = self._admit(c, trial)
            pending = one(
                c,
                "SELECT status FROM anvil.workflow_fixture_effects WHERE trial_id=%s AND effect_key=%s",
                (trial, key),
            )
            if not pending or pending["status"] != "dispatched":
                raise ValueError("fixture_effect_not_pending")
            node = next(n for n in binding.graph.nodes if n.id == key.split(":")[0])
            validate_response(node, response, binding.graph)
            if not one(
                c,
                "UPDATE anvil.workflow_fixture_effects SET status='completed',response=%s,response_sha256=%s,completed_at=now() WHERE trial_id=%s AND effect_key=%s AND status='dispatched' RETURNING effect_key",
                (Jsonb(response), digest(response), trial, key),
            ):
                raise ValueError("fixture_effect_not_pending")
