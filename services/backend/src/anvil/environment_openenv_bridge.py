"""Dedicated pinned OpenEnv interpreter, bounded private stdio control protocol."""

import json
import os
import sys

from anvil.db import transaction
from anvil.environment_openenv_installed import ComponentAction, ComponentEnvironment


def main():
    if os.environ.get("ANVIL_ENVIRONMENT_OPENENV_ENABLED") != "true":
        raise RuntimeError("OpenEnv worker disabled")
    line = sys.stdin.buffer.readline(65537)
    if len(line) > 65536:
        raise ValueError("OpenEnv initialization exceeds bound")
    request = json.loads(line)
    if set(request) != {"project", "user", "environment", "instance"}:
        raise ValueError("Invalid OpenEnv attempt identity")

    def connections():
        return transaction(request["project"], request["user"], worker=True)

    episode = ComponentEnvironment(
        request["project"],
        request["user"],
        request["environment"],
        connections,
        instance_id=request["instance"],
    )
    print(
        json.dumps(
            {
                "ready": True,
                "package": "openenv",
                "version": "0.12.0",
                "episode_id": str(episode.instance),
                "environment_manifest_sha256": episode.version["manifest_sha256"],
                "pack_sha256": episode.pack["content_sha256"],
            }
        ),
        flush=True,
    )
    while True:
        raw = sys.stdin.buffer.readline(65537)
        if not raw:
            break
        try:
            if len(raw) > 65536:
                raise ValueError("OpenEnv command exceeds bound")
            body = json.loads(raw)
            if set(body) != {"action"}:
                raise ValueError("Only bounded action commands are allowed")
            action = ComponentAction.model_validate(body["action"])
            observation = episode.step(action, timeout_s=30)
            value = {
                "result": observation.result,
                "reward": observation.reward,
                "anvil_score": observation.metadata["anvil_score"],
            }
            encoded = json.dumps(value, allow_nan=False).encode()
            if len(encoded) > 1024 * 1024:
                raise ValueError("OpenEnv result exceeds bound")
            sys.stdout.buffer.write(encoded + b"\n")
            sys.stdout.buffer.flush()
        except Exception as exc:
            print(
                json.dumps(
                    {"error": type(exc).__name__, "status": "episode_action_failed_no_retry"}
                ),
                flush=True,
            )
            break
    # Parent's trusted collector captures before closing the actual SQL instance.


if __name__ == "__main__":
    main()
