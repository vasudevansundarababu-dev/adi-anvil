"""Actual OpenEnv role session over the fixed private world API, without SQL.

No controller state, future fixture, provider credential or SQL connection is
accepted by this session. Reset attaches to the same world; it never resets it.
The API must authenticate the job/lease and actual before-effect intent itself.
"""

from importlib.metadata import version
from math import isfinite
from typing import Literal
from uuid import UUID

from openenv.core.env_server.interfaces import Environment
from pydantic import Field

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import Sha
from anvil.marketing_task2_contract import WIRE_ROLES
from anvil.marketing_task2_openenv import (
    MarketingNativeAction,
    MarketingObservation,
    MarketingState,
)
from anvil.praxis_generic_contract import digest
from anvil.schemas import Strict


class RoleView(Strict):
    world_binding_id: UUID
    world_binding_sha256: Sha
    episode_id: UUID
    generation: int = Field(strict=True, ge=0)
    role: Literal["orchestrator", "intent", "performance", "brief", "policy"]
    execution_sha256: Sha
    snapshot_sha256: Sha
    state_sha256: Sha


class ToolReply(RoleView):
    request_id: UUID
    operation: str = Field(min_length=1, max_length=60)
    result: dict
    result_sha256: Sha


class WorldRoleEnvironment(
    Environment[MarketingNativeAction, MarketingObservation, MarketingState]
):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, world, role, *, phase_deadline=None):
        from anvil.marketing_paid_world import QualifiedWorld

        if (
            type(world) is not QualifiedWorld
            or role not in WIRE_ROLES
            or version("openenv") != "0.12.0"
        ):
            raise ValueError("Fixed world facade, assigned role and pinned OpenEnv required")
        if phase_deadline is not None:
            if (type(phase_deadline) not in (int, float) or not isfinite(phase_deadline)
                    or phase_deadline > world._deadline):
                raise ValueError("Role phase deadline must fit original world deadline")
            world._remaining(phase_deadline)
        super().__init__()
        self.world, self.role = world, role
        self.execution_sha256 = world._bound.execution_sha256
        self.source_refs = []
        self.generation = world.generation
        self.attached, self.closed, self._view = False, False, None
        self._phase_options = {} if phase_deadline is None else {"phase_deadline": phase_deadline}

    def _accept(self, view):
        bound = self.world._bound
        if (
            any(
                getattr(view, key) != getattr(bound, key)
                for key in (
                    "world_binding_id",
                    "world_binding_sha256",
                    "episode_id",
                    "generation",
                    "execution_sha256",
                )
            )
            or view.role != self.role
            or view.snapshot_sha256 != bound.case_snapshot_sha256
        ):
            raise ValueError("Actual API reply differs from assigned world role scope")
        self._view = view

    def reset(self, seed=None, episode_id=None, **kwargs):
        if (
            self.closed
            or self.attached
            or seed is not None
            or kwargs
            or (episode_id is not None and episode_id != self.world.episode_id)
        ):
            raise ValueError("Attach once to assigned world; no reset or role change")
        try:
            self._accept(
                RoleView.model_validate(
                    self.world._call("role_attach", {"role": self.role}, request_seconds=60,
                                     **self._phase_options)
                )
            )
        except Exception:
            self.closed = True
            raise
        self.attached = True
        self.world._remaining(self._phase_options.get("phase_deadline", self.world._deadline))
        return MarketingObservation(
            result={
                "trial_id": self.world.episode_id,
                "generation": self.generation,
                "role": self.role,
                "attached": True,
            },
            done=False,
            reward=None,
        )

    def step(self, action, timeout_s=None, **kwargs):
        if (
            self.closed
            or not self.attached
            or kwargs
            or type(action) is not MarketingNativeAction
            or action.metadata
            or action.expected_generation != self.generation
            or (
                timeout_s is not None
                and (
                    type(timeout_s) not in (int, float)
                    or not isfinite(timeout_s)
                    or not 1 <= timeout_s <= 60
                )
            )
        ):
            raise ValueError("Current correlated role action and bounded deadline required")
        allowed = {
            tool["id"] for tool in self.world._execution["tools"] if self.role in tool["role_ids"]
        }
        if action.operation not in allowed:
            raise ValueError("Role tool not offered by exact published execution")
        try:
            raw = self.world._call(
                "role_tool",
                {
                    "role": self.role,
                    "request_id": action.request_id,
                    "operation": action.operation,
                    "arguments": action.arguments,
                },
                request_seconds=int(timeout_s) if timeout_s is not None else 60,
                **self._phase_options,
            )
            bounded_json(raw, 65536, max_nodes=10000)
            reply = ToolReply.model_validate(raw)
            if (
                reply.request_id != UUID(action.request_id)
                or reply.operation != action.operation
                or digest(reply.result) != reply.result_sha256
            ):
                raise ValueError("Actual correlated role tool result custody required")
            self._accept(reply)
            self.world._remaining(self._phase_options.get("phase_deadline", self.world._deadline))
        except Exception:
            self.closed = True
            raise
        return MarketingObservation(result=reply.result, done=False, reward=None)

    @property
    def state(self):
        if not self.attached or self.closed or self._view is None:
            raise ValueError("Attached current API role state required")
        return MarketingState(
            generation=self.generation,
            snapshot_sha256=self._view.snapshot_sha256,
            state_sha256=self._view.state_sha256,
        )

    @property
    def credentials(self):
        return {"generation": self.state.generation, "role": self.role}

    def close(self):
        self.closed = True
