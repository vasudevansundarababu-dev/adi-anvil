"""Pinned OpenEnv0.12 server adapter, loaded only in its separate trial runtime.

Each episode owns a distinct SQL instance. Native reward is None; Task scoring
uses the original separate evaluator. No provider dispatch or cloud operation.
"""

import hmac
from importlib.metadata import version as package_version

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import Action, Observation, State
from pydantic import ConfigDict, Field

from anvil import environment_runtime as runtime
from anvil.db import digest
from anvil.environment_api import Operation


class ComponentAction(Action):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(min_length=1, max_length=60)
    arguments: dict = Field(default_factory=dict)
    expected_generation: int = Field(ge=0, strict=True)


class ComponentObservation(Observation):
    result: dict
    environment_manifest_sha256: str
    pack_sha256: str


class ComponentState(State):
    generation: int
    pack_sha256: str
    environment_manifest_sha256: str
    state_sha256: str


class ComponentEnvironment(Environment[ComponentAction, ComponentObservation, ComponentState]):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, project, user, environment, connections, instance_id=None):
        if package_version("openenv") != "0.12.0":
            raise ValueError("Exact installed OpenEnv0.12.0 required")
        super().__init__()
        self.project, self.user, self.environment, self.connections = (
            project,
            user,
            environment,
            connections,
        )
        self.closed = False
        with connections() as c:
            self.version = runtime.get(c, "environment_versions", environment)
            runtime.current_runtime(self.version)
            self.pack = runtime.get(c, "environment_packs", self.version["pack_id"])
            if instance_id is not None:
                row = runtime.get(c, "environment_instances", instance_id)
                if (
                    str(row["environment_id"]) != str(environment)
                    or str(row["created_by"]) != str(user)
                    or row["state"] != "active"
                ):
                    raise ValueError("Wrong or inactive OpenEnv attempt instance")
                self.instance = row["id"]
            else:
                self.instance = runtime.create_instance(c, project, user, environment)["id"]

    def _observation(self, result):
        return ComponentObservation(
            result=result,
            done=False,
            reward=None,
            environment_manifest_sha256=self.version["manifest_sha256"],
            pack_sha256=self.pack["content_sha256"],
            metadata={
                "origin": "openenv_local_engineering_trial",
                "anvil_score": None,
                "provider_calls": 0,
                "model_performance": False,
            },
        )

    def reset(self, seed=None, episode_id=None, **kwargs):
        if (
            self.closed
            or kwargs
            or (
                seed is not None and (type(seed) is not int or seed != self.pack["content"]["seed"])
            )
            or (episode_id is not None and episode_id != str(self.instance))
        ):
            raise ValueError("Reset must preserve exact episode, seed, pack and clock")
        with self.connections() as c:
            row = runtime.get(c, "environment_instances", self.instance)
            runtime.reset(c, self.user, self.instance, row["generation"])
            return self._observation(
                {"generation": row["generation"] + 1, "state": runtime.state(c, self.instance)}
            )

    def step(self, action: ComponentAction, timeout_s=None, **kwargs):
        if (
            self.closed
            or kwargs
            or (
                timeout_s is not None
                and (type(timeout_s) not in (int, float) or not 0 < timeout_s <= 60)
            )
            or action.metadata
        ):
            raise ValueError("Unsupported episode controls or timeout")
        parsed = Operation(
            operation=action.operation,
            arguments=action.arguments,
            expected_generation=action.expected_generation,
        )
        with self.connections() as c:
            c.execute(
                "SELECT set_config('statement_timeout',%s,true)",
                (str(int((timeout_s or 60) * 1000)),),
            )
            result = runtime.execute(
                c,
                self.user,
                self.instance,
                parsed.operation,
                parsed.arguments,
                parsed.expected_generation,
            )
            return self._observation(result)

    @property
    def state(self):
        with self.connections() as c:
            row = runtime.get(c, "environment_instances", self.instance)
            count = c.execute(
                "SELECT count(*) AS n FROM anvil.environment_events WHERE instance_id=%s AND generation=%s AND operation<>'reset'",
                (self.instance, row["generation"]),
            ).fetchone()["n"]
            return ComponentState(
                episode_id=str(self.instance),
                step_count=count,
                generation=row["generation"],
                pack_sha256=self.pack["content_sha256"],
                environment_manifest_sha256=self.version["manifest_sha256"],
                state_sha256=digest(runtime.state(c, self.instance)),
            )

    def close(self):
        if not self.closed:
            with self.connections() as c:
                runtime.close(c, self.user, self.instance)
            self.closed = True


def create_app(factory, token):
    """Owner-scoped local service with real OpenEnv routes and strict bearer auth."""
    from openenv.core.env_server.http_server import create_app as openenv_app

    if not isinstance(token, str) or not 32 <= len(token) <= 128 or not token.isascii():
        raise ValueError("Private bounded local trial bearer required")
    app = openenv_app(
        factory,
        ComponentAction,
        ComponentObservation,
        env_name="anvil_reference",
        max_concurrent_envs=4,
    )

    class Gate:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] not in ("http", "websocket"):
                return await self.app(scope, receive, send)
            values = [
                v.decode("ascii", errors="replace")
                for k, v in scope.get("headers", [])
                if k.lower() == b"authorization"
            ]
            if len(values) != 1 or not hmac.compare_digest(values[0], "Bearer " + token):
                if scope["type"] == "websocket":
                    return await send({"type": "websocket.close", "code": 1008})
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                return await send(
                    {"type": "http.response.body", "body": b'{"error":"authentication_required"}'}
                )
            total = 0

            async def bounded_receive():
                nonlocal total
                message = await receive()
                body = (
                    message.get("body", b"")
                    or message.get("bytes", b"")
                    or message.get("text", "").encode()
                )
                total = total + len(body) if scope["type"] == "http" else len(body)
                if total > 65536:
                    raise ValueError("OpenEnv trial request exceeds64KiB")
                return message

            return await self.app(scope, bounded_receive, send)

    app.add_middleware(Gate)
    return app
