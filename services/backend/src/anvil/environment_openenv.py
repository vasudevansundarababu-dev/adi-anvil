"""Explicit local episode action/reset adapter; not an installed OpenEnv server.

Typed protocol can be exercised without an OpenEnv dependency or model calls.
Native reward is absent and never becomes an Anvil rubric score.
"""

from pydantic import Field

from anvil import environment_runtime as runtime
from anvil.environment_api import Operation
from anvil.schemas import Strict


class Step(Operation):
    pass


class Reset(Strict):
    expected_generation: int = Field(ge=0, strict=True)
    expected_pack_sha256: str = Field(pattern="^[a-f0-9]{64}$")


class LocalEpisode:
    def __init__(self, c, user, instance):
        self.c, self.user, self.instance = c, user, instance

    def state(self):
        row = runtime.get(self.c, "environment_instances", self.instance)
        return {
            "instance_id": str(row["id"]),
            "generation": row["generation"],
            "state": runtime.state(self.c, self.instance),
            "native_reward": None,
            "anvil_score": None,
            "adapter": "openenv-local-protocol-v1",
            "installed_openenv_qualified": False,
        }

    def step(self, action: Step):
        result = runtime.execute(
            self.c,
            self.user,
            self.instance,
            action.operation,
            action.arguments,
            action.expected_generation,
        )
        return {"observation": result, "done": False, "native_reward": None, "anvil_score": None}

    def reset(self, request: Reset):
        instance = runtime.get(self.c, "environment_instances", self.instance)
        version = runtime.get(self.c, "environment_versions", instance["environment_id"])
        if version["manifest"]["pack_sha256"] != request.expected_pack_sha256:
            raise ValueError("episode_pack_changed")
        runtime.reset(self.c, self.user, self.instance, request.expected_generation)
        return self.state()

    def close(self):
        return runtime.close(self.c, self.user, self.instance)


class InstalledEpisode:
    """Actual OpenEnv0.12 in a separate interpreter; no provider or migration keys."""

    def __init__(self, project, user, environment, instance, manifest_sha256, pack_sha256):
        import os
        import subprocess
        import tempfile
        from pathlib import Path

        from anvil.config import ROOT, setting

        if os.environ.get("ANVIL_ENVIRONMENT_OPENENV_ENABLED") != "true":
            raise ValueError("Dedicated OpenEnv runtime is disabled")
        python = Path(os.environ.get("ANVIL_ENVIRONMENT_OPENENV_PYTHON", ""))
        if not python.is_absolute() or not python.is_file():
            raise ValueError("Exact installed OpenEnv interpreter required")
        self.home = Path(tempfile.mkdtemp(prefix="anvil-openenv-episode-", dir="/private/tmp"))
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(self.home),
            "LANG": "en_US.UTF-8",
            "PYTHONPATH": str(ROOT / "services/backend/src"),
            "ANVIL_ROOT": str(ROOT),
            "ANVIL_ENV": "local",
            "WEB_ORIGIN": "http://127.0.0.1:3202",
            "WORKER_DATABASE_URL": setting("WORKER_DATABASE_URL"),
            "ANVIL_ENVIRONMENT_OPENENV_ENABLED": "true",
            "DO_NOT_TRACK": "1",
            "HF_HUB_OFFLINE": "1",
            "ANVIL_LIVE_PROVIDERS_ENABLED": "false",
            "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "false",
            "ANVIL_REAL_EMAIL_ENABLED": "false",
            "ANVIL_GENERATION_ENABLED": "false",
        }
        self.log = (self.home / "operator-private.log").open("wb")
        self.process = subprocess.Popen(
            [str(python), "-m", "anvil.environment_openenv_bridge"],
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            start_new_session=True,
        )
        os.set_blocking(self.process.stdout.fileno(), False)
        os.set_blocking(self.process.stdin.fileno(), False)
        self.buffer = b""
        try:
            self.metadata = self.rpc(
                {
                    "project": str(project),
                    "user": str(user),
                    "environment": str(environment),
                    "instance": str(instance),
                },
                timeout=30,
            )
            if (
                self.metadata.get("version") != "0.12.0"
                or self.metadata.get("episode_id") != str(instance)
                or self.metadata.get("environment_manifest_sha256") != manifest_sha256
                or self.metadata.get("pack_sha256") != pack_sha256
            ):
                raise ValueError("OpenEnv initialization identity mismatch")
        except Exception:
            self.close()
            raise

    def rpc(self, body, *, timeout=35):
        import json
        import os
        import select
        import time

        raw = json.dumps(body, allow_nan=False).encode() + b"\n"
        if len(raw) > 65536 or self.process.poll() is not None:
            raise ValueError("OpenEnv process terminal or request exceeds bound")
        deadline = time.monotonic() + timeout
        offset = 0
        while offset < len(raw):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [self.process.stdin], [], remaining)[1]:
                raise TimeoutError("OpenEnv request write deadline")
            try:
                offset += os.write(self.process.stdin.fileno(), raw[offset:])
            except BlockingIOError:
                continue
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise TimeoutError("OpenEnv operation deadline; no retry")
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise ValueError("OpenEnv process exited before a complete response")
            self.buffer += chunk
            if len(self.buffer) > 1024 * 1024:
                raise ValueError("OpenEnv response exceeds bound")
        line, self.buffer = self.buffer.split(b"\n", 1)
        response = json.loads(line)
        if not isinstance(response, dict) or "error" in response:
            raise ValueError("OpenEnv action failed; no retry")
        return response

    def step(self, operation, arguments, generation):
        response = self.rpc(
            {
                "action": {
                    "operation": operation,
                    "arguments": arguments,
                    "expected_generation": generation,
                }
            }
        )
        if response.get("reward") is not None or response.get("anvil_score") is not None:
            raise ValueError("OpenEnv diagnostic reward cannot become a Task score")
        return response["result"]

    def close(self):
        import os
        import signal
        import subprocess

        if self.process.poll() is None:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=3)
        self.process.stdout.close()
        self.log.close()
