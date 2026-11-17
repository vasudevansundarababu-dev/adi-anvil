"""Actual OpenEnv adapter for a host-bound role in one shared campaign episode.

Reset attaches a fresh role session to the already initialized case generation.
Only the trusted controller resets the shared world; one agent cannot erase the
other four agents' work or advance time/approve its own request.
"""

from importlib.metadata import version

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import Action, Observation, State
from pydantic import ConfigDict, Field

from anvil import marketing_task2_store as store
from anvil.marketing_task2_contract import VERSION, WIRE_ROLES
from anvil.praxis_generic_contract import digest
from anvil.praxis_marketing_contract import MarketingExecution


class MarketingAction(Action):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(min_length=1, max_length=60)
    arguments: dict = Field(default_factory=dict)
    expected_generation: int = Field(ge=0, strict=True)


class MarketingNativeAction(MarketingAction):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class MarketingObservation(Observation):
    result: dict
    environment_version: str = VERSION


class MarketingState(State):
    generation: int
    snapshot_sha256: str
    state_sha256: str


class MarketingEnvironment(Environment[MarketingAction, MarketingObservation, MarketingState]):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, connections, project, user, trial_id, generation, role):
        if version("openenv") != "0.12.0" or role not in WIRE_ROLES:
            raise ValueError("Pinned OpenEnv and a host-bound canonical role required")
        super().__init__()
        self.connections, self.project, self.user = connections, project, user
        self.trial_id, self.generation, self.role = trial_id, generation, role
        self.attached, self.closed = False, False

    def reset(self, seed=None, episode_id=None, **kwargs):
        if (
            self.closed
            or kwargs
            or seed is not None
            or (episode_id is not None and episode_id != str(self.trial_id))
        ):
            raise ValueError("Attach only to the assigned frozen campaign episode")
        with self.connections() as c:
            store.locked(c, self.project, self.user, self.trial_id, self.generation)
        self.attached = True
        return MarketingObservation(
            result={
                "trial_id": str(self.trial_id),
                "generation": self.generation,
                "role": self.role,
                "attached": True,
            },
            done=False,
            reward=None,
        )

    def step(self, action: MarketingAction, timeout_s=None, **kwargs):
        if (
            self.closed
            or not self.attached
            or kwargs
            or action.metadata
            or action.expected_generation != self.generation
            or (
                timeout_s is not None
                and (type(timeout_s) not in (int, float) or not 0 < timeout_s <= 60)
            )
        ):
            raise ValueError("Current attached role session and generation required")
        with self.connections() as c:
            result = store.call(
                c,
                self.project,
                self.user,
                self.trial_id,
                self.generation,
                self.role,
                action.operation,
                action.arguments,
            )
        return MarketingObservation(result=result, done=False, reward=None)

    @property
    def credentials(self):
        # Internal MCP scope check, never a candidate-controlled role switch.
        return {"generation": self.state.generation, "role": self.role}

    @property
    def state(self):
        with self.connections() as c:
            row, _ = store.locked(c, self.project, self.user, self.trial_id, self.generation)
        return MarketingState(
            generation=self.generation,
            snapshot_sha256=row["snapshot_sha256"],
            state_sha256=row["state_sha256"],
        )

    def close(self):
        self.closed = True


class MarketingNativeEnvironment(MarketingEnvironment):
    def __init__(
        self, connections, project, user, trial_id, generation, role, execution, *, source_refs=()
    ):
        super().__init__(connections, project, user, trial_id, generation, role)
        self.execution = MarketingExecution.model_validate(execution).model_dump()
        self.execution_sha256 = digest(self.execution)
        self.source_refs = list(source_refs)

    def step(self, action: MarketingNativeAction, timeout_s=None, **kwargs):
        if (
            self.closed
            or not self.attached
            or kwargs
            or action.metadata
            or action.expected_generation != self.generation
            or not isinstance(action, MarketingNativeAction)
            or (
                timeout_s is not None
                and (type(timeout_s) not in (int, float) or not 0 < timeout_s <= 60)
            )
        ):
            raise ValueError("Current host-correlated native Marketing role session required")
        with self.connections() as c:
            result = store.named_call(
                c,
                self.project,
                self.user,
                self.trial_id,
                self.generation,
                self.role,
                action.operation,
                action.arguments,
                self.execution,
                action.request_id,
                source_refs=self.source_refs,
            )
        return MarketingObservation(result=result, done=False, reward=None)
