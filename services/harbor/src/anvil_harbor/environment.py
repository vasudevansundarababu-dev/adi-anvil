"""Pinned, preloaded-only local Harbor component adapter. No paid SDKs or keys."""

import asyncio
import base64
import json
import os
import stat
from importlib.metadata import version
from pathlib import Path

from harbor.environments.docker.runtime import ContainerRuntime
from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.verifier_mode import resolve_verifier_environment_definition
from harbor.models.trial.config import TrialConfig
from harbor.trial.trial import Trial

from anvil_harbor.prestart import validate_operator_config
from anvil_harbor.sme import SMEDocker

_TECHNICAL_RUNTIME = None


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
        if _TECHNICAL_RUNTIME is not None:
            if (entries or args[0] != _TECHNICAL_RUNTIME["docker"]
                    or args[4] != _TECHNICAL_RUNTIME["host"]
                    or os.environ.get("DOCKER_HOST") != args[4]
                    or os.environ.get("DOCKER_CONFIG") != str(folder)):
                raise ValueError("Exact measured technical Docker/Compose invocation required")
            return ContainerRuntime(engine=tuple(args), compose=(_TECHNICAL_RUNTIME["compose"],))
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


def fixed_component_gate():
    """Source-only fixed component path; no caller/environment value opens it."""
    raise ValueError("Fixed paired-role component admission remains closed")


async def preflight_fixed_roles(trial):
    """Construct the pinned separate verifier without entering its start context."""
    if type(trial.agent_environment) is not LocalComponentsDocker:
        raise ValueError("Exact fixed actor adapter required")
    definition = resolve_verifier_environment_definition(trial.task.config, trial.task.paths, None)
    if definition is None:
        raise ValueError("Actual separate verifier definition required")
    plan = trial._network_plan(None, env_config=definition.config)
    if plan.verifier_env_baseline is None:
        raise ValueError("Actual separate verifier baseline required")
    verifier = EnvironmentFactory.create_environment_from_config(
        config=trial.config.environment.model_copy(update={"extra_docker_compose": []}),
        stream=False,
        environment_dir=definition.directory,
        enable_environment_dir_upload=not definition.bundled_tests,
        environment_name=trial.task.short_name,
        session_id=trial._separate_verifier_session_id("trial"),
        trial_paths=trial.paths,
        task_env_config=definition.config,
        logger=trial.logger,
        auto_mounts=trial._verifier_env_mounts(definition.config),
        network_policy=plan.verifier_env_baseline,
        phase_network_policies=[plan.verifier_phase],
    )
    if (
        type(verifier) is not LocalComponentsDocker
        or trial.agent_environment.role != "environment"
        or verifier.role != "tests"
        or verifier.trial_paths.trial_dir != trial.agent_environment.trial_paths.trial_dir
    ):
        raise ValueError("Exact paired actor/separate verifier adapters required")
    verifier.context_id = trial.id
    trial._validate_separate_verifier_env_policies(verifier, plan=plan)
    # Both derive actual Compose bytes via config-only commands before Trial.run.
    # Later starts render again and must equal these distinct immutable snapshots.
    await trial.agent_environment.preflight_projection()
    await verifier.preflight_projection()


async def main(path):
    global _TECHNICAL_RUNTIME
    fixed = "ANVIL_HARBOR_FIXED_CONTEXT" in os.environ
    technical = os.environ.get("ANVIL_HARBOR_TECHNICAL_PROBE_JOB")
    permission = None
    if fixed and technical:
        raise ValueError("Business and technical control contexts cannot be combined")
    if fixed:
        fixed_component_gate()
    validated = validate_operator_config(path)
    if technical:
        from anvil_harbor.operator_proof import TechnicalProbeStore, canonical, parse

        with TechnicalProbeStore(Path(os.environ["ANVIL_ROOT"])) as store:
            permission = store.load_probe(technical)
            if not permission["technical_probe_authorized"]:
                raise ValueError("Actual QA probe custody required")
            assets = store.operation_assets(permission)
            root = Path(os.environ["ANVIL_HARBOR_ATTEMPT_ROOT"])
            if (assets["runtime_seal"]["schema_version"] != "anvil.fixed-runtime-seal.v2"
                    or root != store.root / "technical-probe-attempts" / permission["operation_nonce"]
                    or Path(path) != root / "trial.json"
                    or canonical(validated) != canonical(assets["trial_config"])):
                raise ValueError("Exact installed technical Trial configuration required")
            launch = parse(store._read("technical-probe-launches", technical + ".json"))
            if any(launch.get(key) != permission[key] for key in ("job_id", "plan_sha256", "operation_nonce")):
                raise ValueError("Actual one-shot probe launch required")
            store.validate_runtime_seal(assets["runtime_seal"])
            store.validate_loaded_origins(assets["runtime_seal"], component="harbor")
            host = assets["host_image_custody"]
            docker_args = json.loads(os.environ["ANVIL_ENVIRONMENT_DOCKER_COMMAND"])
            if (len(docker_args) != 5 or docker_args[0] != host["binaries"]["docker"]["path"]
                    or docker_args[2] != str(root / "empty-docker-config") or docker_args[4] != host["docker_host"]):
                raise ValueError("Measured probe engine/config/host required")
            for name in ("docker", "compose"):
                record = host["binaries"][name]
                store._sealed_file(record["path"], record["sha256"])
            _TECHNICAL_RUNTIME = {"docker": docker_args[0], "compose": host["binaries"]["compose"]["path"],
                                  "host": host["docker_host"]}
            os.environ["DOCKER_HOST"] = host["docker_host"]
            os.environ["DOCKER_CONFIG"] = docker_args[2]
    if version("harbor") != "0.25.0":
        raise ValueError("Exact installed Harbor 0.25.0 required")
    config = TrialConfig.model_validate(validated)
    if (
        config.environment.import_path != "anvil_harbor.environment:LocalComponentsDocker"
        or config.environment.delete
        or config.agent.import_path != "anvil_harbor.sme:SMEAgent"
        or config.verifier.import_path != "anvil_harbor.sme:SMEVerifier"
    ):
        raise ValueError("Exact retained component trial required")
    trial = await Trial.create(config)
    if fixed or technical:
        context = (json.loads(os.environ["ANVIL_HARBOR_FIXED_CONTEXT"]) if fixed else
                   {key: permission[key] for key in ("job_id", "operation_nonce", "request_sha256")})
        if set(context) != {"job_id", "operation_nonce", "request_sha256"}:
            raise ValueError("Exact fixed framework context required")
        root = Path(os.environ["ANVIL_HARBOR_ATTEMPT_ROOT"])
        raw = json.dumps(
            context | {"trial_name": config.trial_name, "framework_trial_id": str(trial.id)},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        fd = os.open(
            root / "framework-entry.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        await preflight_fixed_roles(trial)
    result = await trial.run()
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
