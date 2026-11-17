"""Role-bound native graph adapter over the existing one-way SDK broker.

Dispatch is an injected trusted broker callback, never a provider client. SQL
intents and completed SDK/tool receipts, rather than actor assertions, establish
the returned artifact. Exceptions propagate to the existing uncertain journal.
"""

from math import isfinite
from threading import Lock
from time import monotonic

from anvil.db import digest
from anvil.marketing_paid_turn import (
    BeforeEffect,
    apply_turn,
    claim_turn,
    record_turn,
    response,
    validate_response_protocol,
)


class RoleAdapter:
    def __init__(
        self,
        connections,
        job,
        episode_id,
        generation,
        execution,
        dispatch,
        client,
        *,
        episode_timeout_seconds=600,
        clock=monotonic,
        absolute_deadline=None,
    ):
        if type(episode_timeout_seconds) is not int or not 1 <= episode_timeout_seconds <= 600:
            raise ValueError("Marketing campaign elapsed bound must be1–600seconds")
        self.connections, self.job = connections, job
        self.episode_id, self.generation = episode_id, generation
        self.execution, self.dispatch, self.client = execution, dispatch, client
        self.lock = Lock()
        now = clock()
        if absolute_deadline is not None and (
            type(absolute_deadline) not in (int, float)
            or not isfinite(absolute_deadline)
            or not now < absolute_deadline <= now + episode_timeout_seconds
        ):
            raise ValueError(
                "Exact unexpired outer campaign deadline required; it cannot be extended"
            )
        self.clock = clock
        self.deadline = (
            now + episode_timeout_seconds if absolute_deadline is None else absolute_deadline
        )

    def remaining(self):
        seconds = int(self.deadline - self.clock())
        if seconds < 1:
            raise TimeoutError("marketing_campaign_elapsed_limit_no_truncation_or_replay")
        return seconds

    def __call__(self, node, inputs, week, visit):
        if node["type"] != "agent_step":
            raise RuntimeError("marketing_non_agent_effect_requires_qualified_host_adapter")
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("marketing_concurrent_role_dispatch_denied")
        try:
            while True:
                remaining = self.remaining()
                stage, context = claim_turn(
                    self.connections,
                    self.job,
                    self.episode_id,
                    self.generation,
                    self.execution,
                    node,
                    inputs,
                    week,
                    visit,
                )
                # The physical call is attempted once. A timeout is never
                # retried here, even if no response reached this process.
                text = self.dispatch(stage, context, remaining)
                completed = response(self.connections, self.job, stage, text)
                self.remaining()
                validate_response_protocol(
                    self.connections, self.job, stage, completed, self.execution, context["role"]
                )
                before = BeforeEffect(self.connections, self.job, stage, completed["id"])

                def guarded_before(*args):
                    self.remaining()
                    return before(*args)

                self.remaining()
                with self.client(context["role"], guarded_before) as client:
                    apply_turn(client, completed["text"], self.execution, context["role"])
                observation = record_turn(self.connections, self.job, stage, completed)
                if observation["completed_node"] is True:
                    if not isinstance(observation.get("artifact"), dict):
                        raise RuntimeError("marketing_actual_artifact_receipt_required")
                    return {
                        "artifact": observation["artifact"],
                        "receipt": {
                            "input_sha256": digest(inputs),
                            "role": context["role"],
                            "stage_index": stage,
                            "physical_call_id": str(completed["id"]),
                            "observation_sha256": digest(observation),
                            "origin": "completed_broker_and_tool_receipts",
                            "model_performance_validated": False,
                        },
                    }
        finally:
            self.lock.release()
