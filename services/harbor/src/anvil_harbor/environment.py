"""Pinned, preloaded-only local Harbor component adapter. No paid SDKs or keys."""

import asyncio
import base64
import json
import os
import stat
from importlib.metadata import version
from pathlib import Path

from harbor.environments.docker.runtime import ContainerRuntime
from harbor.models.trial.config import TrialConfig
from harbor.trial.trial import Trial

from anvil_harbor.sme import SMEDocker


class LocalComponentsDocker(SMEDocker):
    @classmethod
    def runtime(cls):
        args = json.loads(os.environ["ANVIL_ENVIRONMENT_DOCKER_COMMAND"])
        if (
            not isinstance(args, list)
            or len(args) != 5
            or args[0]
            not in ("/opt/homebrew/bin/docker", "/usr/local/bin/docker", "/usr/bin/docker")
            or args[1] != "--config"
            or args[3] != "--host"
            or not args[4].startswith("unix:///")
        ):
            raise ValueError("Explicit local Docker command required")
        folder = Path(args[2])
        info = folder.lstat()
        if (
            not folder.is_absolute()
            or folder.is_symlink()
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise ValueError("Empty owner-only Docker configuration required")
        entries = list(folder.iterdir())
        if entries:
            config = folder / "config.json"
            if (
                entries != [config]
                or config.is_symlink()
                or config.stat().st_mode & 0o077
                or json.loads(config.read_text())
                != {
                    "cliPluginsExtraDirs": [
                        "/Applications/Docker.app/Contents/Resources/cli-plugins"
                    ]
                }
            ):
                raise ValueError(
                    "Only explicit public Compose-plugin discovery is allowed; no registry credentials"
                )
        return ContainerRuntime(engine=tuple(args), compose=(*args, "compose"))

    async def download_file(self, source_path, target_path):
        # docker cp does not reliably capture this runtime's tmpfs. Read a bounded
        # regular actor file through the pinned service and seal its actual bytes.
        if source_path != "/workspace/output.json":
            return await super().download_file(source_path, target_path)
        program = "import os,stat,base64; p='/workspace/output.json'; s=os.lstat(p); assert stat.S_ISREG(s.st_mode) and s.st_size<=65536; print(base64.b64encode(open(p,'rb').read()).decode())"
        import shlex

        result = await self.exec(
            "python -c " + shlex.quote(program), timeout_sec=10, user="10001:10001"
        )
        if result.return_code != 0:
            raise ValueError("Actor output missing or unsafe")
        raw = base64.b64decode(result.stdout.strip(), validate=True)
        target = Path(target_path)
        if (
            len(raw) > 65536
            or not target.resolve().is_relative_to(self.trial_paths.trial_dir.resolve())
            or target.exists()
        ):
            raise ValueError("Invalid fresh collector destination")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)


async def main(path):
    if version("harbor") != "0.25.0":
        raise ValueError("Exact installed Harbor 0.25.0 required")
    config = TrialConfig.model_validate_json(Path(path).read_bytes())
    if (
        config.environment.import_path != "anvil_harbor.environment:LocalComponentsDocker"
        or config.environment.delete
        or config.agent.import_path != "anvil_harbor.sme:SMEAgent"
        or config.verifier.import_path != "anvil_harbor.sme:SMEVerifier"
    ):
        raise ValueError("Exact retained component trial required")
    result = await (await Trial.create(config)).run()
    if result.exception_info or not result.verifier_result:
        raise RuntimeError("Harbor component trial incomplete")
    print(
        "ANVIL_ENVIRONMENT_RESULT="
        + json.dumps(
            {
                "trial_id": str(result.id),
                "diagnostic_rewards": result.verifier_result.rewards,
                "model_performance": False,
                "provider_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    import sys

    asyncio.run(main(sys.argv[1]))
