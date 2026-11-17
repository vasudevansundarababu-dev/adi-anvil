"""Actual pinned OpenEnv adapter, loaded only in the dedicated scheduler runtime."""

from importlib.metadata import version
from time import monotonic

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import Action, Observation, State
from pydantic import ConfigDict, Field

from anvil.db import digest
from anvil.golden_kyc_data import SEED, VERSION
from anvil.golden_kyc_runtime import locked, reset, step, tick


class GoldenAction(Action):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(min_length=1, max_length=60)
    arguments: dict = Field(default_factory=dict)
    expected_generation: int = Field(ge=0, strict=True)


class GoldenObservation(Observation):
    result: dict
    environment_version: str = VERSION


class GoldenState(State):
    generation: int
    snapshot_sha256: str
    state_sha256: str


class GoldenEnvironment(Environment[GoldenAction, GoldenObservation, GoldenState]):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, connections, project, user, trial_id):
        if version("openenv") != "0.12.0":
            raise ValueError("Exact OpenEnv0.12.0 required")
        super().__init__()
        self.connections, self.project, self.user, self.trial_id = (
            connections,
            project,
            user,
            trial_id,
        )
        self.credentials = None
        self.closed = False
        self.last_action = monotonic()
        self.policy_deadline = None

    def reset(self, seed=None, episode_id=None, **kwargs):
        if (
            self.closed
            or kwargs
            or (seed is not None and (type(seed) is not int or seed != SEED))
            or (episode_id is not None and episode_id != str(self.trial_id))
        ):
            raise ValueError("Frozen seed and assigned episode required")
        with self.connections() as c:
            self.credentials = reset(c, self.project, self.user, self.trial_id)
        self.last_action = monotonic()
        return GoldenObservation(
            result={
                "trial_id": str(self.trial_id),
                "generation": self.credentials["generation"],
                "reset": True,
            },
            done=False,
            reward=None,
        )

    def step(self, action: GoldenAction, timeout_s=None, **kwargs):
        from anvil.marketing_native_wire_bounds import remaining

        if self.policy_deadline is not None:
            remaining(self.policy_deadline)
        if (
            self.closed
            or self.credentials is None
            or kwargs
            or action.metadata
            or (
                timeout_s is not None
                and (type(timeout_s) not in (int, float) or not 0 < timeout_s <= 60)
            )
        ):
            raise ValueError("Reset required; unsupported action controls")
        if action.expected_generation != self.credentials["generation"]:
            raise ValueError("Stale generation")
        now = monotonic()
        elapsed = min(900, max(0, int(now - self.last_action)))
        with self.connections() as c:
            tick(c, self.project, self.user, self.trial_id, active_seconds=elapsed)
            result = step(
                c,
                self.project,
                self.user,
                self.trial_id,
                self.credentials["generation"],
                self.credentials["trial_token"],
                action.operation,
                action.arguments,
                absolute_deadline=self.policy_deadline,
            )
            row = locked(c, self.project, self.user, self.trial_id)
        self.last_action = now
        if self.policy_deadline is not None:
            remaining(self.policy_deadline)
        return GoldenObservation(
            result=result,
            done=row["closed"],
            reward=None,
            metadata={"provider_calls": 0, "model_performance": False, "anvil_score": None},
        )

    @property
    def state(self):
        with self.connections() as c:
            row = locked(c, self.project, self.user, self.trial_id)
            snapshot = c.execute(
                "SELECT snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s AND id=%s",
                (self.project, row["pack_id"], row["application_id"]),
            ).fetchone()["snapshot_sha256"]
        return GoldenState(
            episode_id=str(self.trial_id),
            step_count=row["state"]["counters"]["calls"],
            generation=row["generation"],
            snapshot_sha256=snapshot,
            state_sha256=digest(row["state"]),
        )

    def close(self):
        # No deletion; an interrupted investigation remains resumable by scheduler.
        self.closed = True


def create_app(factory, token):
    """SDK HTTP/WebSocket server with private scheduler-owned bearer gate."""
    import secrets

    from openenv.core.env_server.http_server import create_app as sdk_app

    if not isinstance(token, str) or not 32 <= len(token) <= 128 or not token.isascii():
        raise ValueError("Private bounded bearer required")
    app = sdk_app(
        factory, GoldenAction, GoldenObservation, env_name="golden_kyc", max_concurrent_envs=4
    )

    class Gate:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] in ("http", "websocket"):
                headers = dict(scope.get("headers", []))
                supplied = headers.get(b"authorization", b"")
                if not secrets.compare_digest(supplied, ("Bearer " + token).encode()):
                    if scope["type"] == "websocket":
                        await send({"type": "websocket.close", "code": 1008})
                    else:
                        await send(
                            {
                                "type": "http.response.start",
                                "status": 401,
                                "headers": [(b"content-type", b"application/json")],
                            }
                        )
                        await send(
                            {"type": "http.response.body", "body": b'{"error":"Unauthorized"}'}
                        )
                    return
            await self.app(scope, receive, send)

    app.add_middleware(Gate)
    return app
