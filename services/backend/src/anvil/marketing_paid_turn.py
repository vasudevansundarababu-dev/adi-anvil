"""Trusted role-turn custody, before-effect SQL intents and actual MCP IO.

This module cannot resolve a provider key or issue a model request. Every effect
needs the existing broker lease and actual completed SDK response in105 SQL.
"""

import hashlib
from threading import Lock
from uuid import UUID

from anvil.db import Jsonb, digest
from anvil.marketing_paid_contract import phase, turn
from anvil.praxis_generic_contract import digest as wire_digest


def lease_hash(job):
    return hashlib.sha256(str(job["lease_token"]).encode()).hexdigest()


def claim_turn(connections, job, episode_id, generation, execution, node, inputs, week, visit):
    context = phase(execution, node["id"], inputs, week, visit, opening=week == 0)
    with connections() as c:
        if not c.execute(
            "SELECT marketing_runtime.heartbeat_paid_agent_job(%s,%s) AS allowed",
            (job["id"], job["lease_token"]),
        ).fetchone()["allowed"]:
            raise RuntimeError("marketing_current_lease_and_campaign_deadline_required")
        binding = c.execute(
            "SELECT * FROM marketing_runtime.paid_agent_bindings WHERE project_id=%s AND plan_id=%s",
            (job["project_id"], job["plan_id"]),
        ).fetchone()
        effect = c.execute(
            "SELECT id FROM marketing_runtime.workflow_effects WHERE project_id=%s AND episode_id=%s AND generation=%s AND execution_sha256=%s AND node_id=%s AND week=%s AND visit=%s AND state='claimed'",
            (
                job["project_id"],
                episode_id,
                generation,
                wire_digest(execution),
                node["id"],
                week,
                visit,
            ),
        ).fetchone()
        count = c.execute(
            "SELECT count(*) AS n FROM marketing_runtime.paid_turn_observations WHERE project_id=%s AND plan_id=%s",
            (job["project_id"], job["plan_id"]),
        ).fetchone()["n"]
        if not binding or not effect:
            raise RuntimeError("marketing_claimed_role_effect_required")
        if count >= binding["max_calls"]:
            raise RuntimeError("marketing_global_physical_call_limit")
        if not c.execute(
            "SELECT marketing_runtime.claim_paid_turn(%s,%s,%s,%s,%s,%s,%s,%s) AS allowed",
            (
                job["id"],
                job["lease_token"],
                job["plan_id"],
                count,
                effect["id"],
                Jsonb(context),
                digest(context),
                lease_hash(job),
            ),
        ).fetchone()["allowed"]:
            raise RuntimeError("marketing_role_turn_intent_denied_no_replay")
    return count, context


def response(connections, job, stage, text):
    with connections() as c:
        value = c.execute(
            "SELECT marketing_runtime.paid_agent_response(%s,%s,%s,%s) AS value",
            (job["id"], job["lease_token"], job["plan_id"], stage),
        ).fetchone()["value"]
    if not value or value["text"] != text or value["origin"] not in {"provider", "sdk_mock"}:
        raise RuntimeError("marketing_exact_completed_broker_response_required")
    return value


class CandidateProtocolRejected(RuntimeError):
    """A definite completed response was rejected before tool acquisition.

    The immutable SQL finding is required first. This is not a tool execution,
    a rubric award, or evidence that other turns had no effects.
    """


def validate_response_protocol(connections, job, stage, completed, execution, role):
    from anvil.marketing_response_diagnostics import inspect

    finding = inspect(completed["text"], execution, role)
    if finding["protocol_status"] == "valid":
        return
    with connections() as c:
        allowed = c.execute(
            "SELECT marketing_runtime.record_response_protocol_failure(%s,%s,%s,%s,%s,%s) AS allowed",
            (
                job["id"],
                job["lease_token"],
                job["plan_id"],
                stage,
                completed["id"],
                Jsonb(finding),
            ),
        ).fetchone()["allowed"]
        if not allowed:
            raise RuntimeError("marketing_response_protocol_custody_unconfirmed_no_replay")
    raise CandidateProtocolRejected("marketing_completed_response_protocol_rejected_no_replay")


class BeforeEffect:
    """The private MCP host invokes this before any actual role tool effect."""

    def __init__(self, connections, job, stage, call_id):
        self.connections, self.job, self.stage, self.call_id = connections, job, stage, call_id
        self.index, self.lock = 0, Lock()

    def __call__(self, identifier, operation, arguments):
        with self.lock:
            request = UUID(hex=identifier)
            with self.connections() as c:
                allowed = c.execute(
                    "SELECT marketing_runtime.claim_paid_tool_action(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS allowed",
                    (
                        self.job["id"],
                        self.job["lease_token"],
                        self.job["plan_id"],
                        self.stage,
                        self.index,
                        self.call_id,
                        request,
                        operation,
                        Jsonb(arguments),
                        wire_digest(arguments),
                    ),
                ).fetchone()["allowed"]
                if not allowed:
                    raise RuntimeError("marketing_tool_effect_intent_denied_no_replay")
            self.index += 1


def apply_turn(client, text, execution, role):
    value = turn(text, execution, role)
    if "artifact" in value:
        return value
    from anvil.marketing_task2_openenv import MarketingAction

    for action in value["actions"]:
        client.step(
            MarketingAction(
                operation=action["operation"],
                arguments=action["arguments"],
                expected_generation=client.credentials["generation"],
            )
        )
    return value


def record_turn(connections, job, stage, completed):
    with connections() as c:
        observation = c.execute(
            "SELECT marketing_runtime.paid_turn_value(%s,%s,%s,%s) AS value",
            (job["id"], job["lease_token"], job["plan_id"], stage),
        ).fetchone()["value"]
        if observation is None:
            raise RuntimeError("marketing_complete_tool_receipts_required_no_replay")
        if not c.execute(
            "SELECT marketing_runtime.record_paid_turn(%s,%s,%s,%s,%s,%s,%s,%s,%s) AS allowed",
            (
                job["id"],
                job["lease_token"],
                job["plan_id"],
                stage,
                completed["id"],
                completed["text"],
                hashlib.sha256(completed["text"].encode()).hexdigest(),
                Jsonb(observation),
                digest(observation),
            ),
        ).fetchone()["allowed"]:
            raise RuntimeError("marketing_turn_completion_unconfirmed_no_replay")
    return observation
