"""Static no-network, preloaded-only Harbor SME environment and host mediation."""

import asyncio
import importlib.metadata
import json
import os
import re
import stat
import subprocess
from contextlib import closing
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.capabilities import EnvironmentCapabilities
from harbor.environments.docker.docker import (
    DockerEnvironment,
    _sanitize_docker_compose_project_name,
)
from harbor.environments.docker.runtime import ContainerRuntime
from harbor.models.task.config import NetworkMode
from harbor.models.trial.config import TrialConfig
from harbor.models.verifier.result import VerifierResult
from harbor.trial.trial import Trial
from harbor.verifier.base import BaseVerifier

from anvil_harbor.agent import UnixConnection
from anvil_harbor.prestart import (
    validate_effective_service,
    validate_operator_config,
    validate_service_proof_map,
)

IMAGE = "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/native-fixture-security@sha256:72b8eaacefaa82ffdec3ee632375df24057962d8c14cc327f1990113f7c2b951"
IMAGE_ID = "sha256:72b8eaacefaa82ffdec3ee632375df24057962d8c14cc327f1990113f7c2b951"
ARCHITECTURE = "amd64"


def require_cached_image(info):
    if (
        not isinstance(info, dict)
        or info.get("Os") != "linux"
        or info.get("Architecture") != ARCHITECTURE
        or info.get("Id") != IMAGE_ID
        or IMAGE not in info.get("RepoDigests", [])
    ):
        raise ValueError("Exact cached security-profile Linux image required")


def operator_command(raw):
    args = json.loads(raw)
    prefix = (
        ["sudo", "-n", "/usr/bin/docker"]
        if args[:3] == ["sudo", "-n", "/usr/bin/docker"]
        else ["/usr/bin/docker"]
    )
    if not isinstance(args, list) or len(args) != len(prefix) + 4 or args[: len(prefix)] != prefix:
        raise ValueError("Explicit isolated Docker command required")
    config_flag, config, host_flag, host = args[len(prefix) :]
    if config_flag != "--config" or host_flag != "--host" or not host.startswith("unix:///"):
        raise ValueError("Only explicit local Docker/config paths supported")
    folder = Path(config)
    info = folder.lstat()
    if (
        not folder.is_absolute()
        or not stat.S_ISDIR(info.st_mode)
        or info.st_mode & 0o077
        or list(folder.iterdir())
    ):
        raise ValueError("Docker client config must be an empty owner-only directory")
    return tuple(args)


def guard_compose(command):
    if not command or command[0] not in {"config", "exec", "cp", "ps", "stop", "up"}:
        raise ValueError("Implicit build/pull/deletion is prohibited")
    if command[0] == "up" and command != [
        "up",
        "--detach",
        "--wait",
        "--no-build",
        "--pull",
        "never",
    ]:
        raise ValueError("Only preloaded no-build/no-pull startup supported")
    if "--privileged" in command or "--remove-orphans" in command:
        raise ValueError("Privileged or destructive Docker flags prohibited")


def write_compose_snapshot(trial_dir, role, stdout, *, stderr=False, phase="start", rejected=False):
    """The operator owns the snapshot; sudo Docker must never create this file."""
    folder = Path(trial_dir)
    if (
        role not in {"environment", "tests"}
        or phase not in {"start", "preflight"}
        or type(rejected) is not bool
        or not folder.is_absolute()
        or folder.resolve() != folder
    ):
        raise ValueError("Canonical owned trial directory required")
    metadata = folder.stat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o022
    ):
        raise ValueError("Operator-owned trial directory required")
    data = stdout.encode("utf-8") if isinstance(stdout, str) else stdout
    if not isinstance(data, bytes) or len(data) > 1048576 or (not stderr and not data):
        raise ValueError("Bounded resolved Compose snapshot required")
    prefix = ("sme-rejected-" + phase + "-compose-" if rejected else
              "sme-compose-" if phase == "start" else "sme-preflight-compose-")
    path = folder / (prefix + role + (".stderr" if stderr else ".json"))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def owned_log_mounts(root, config, environment_dir, role, trial_paths, supplied):
    """Explicit role log binds without Harbor's broad trial-root chmod path."""
    trial = root / "trials" / config["trial_name"]
    if (role not in {"environment", "tests"} or not root.is_absolute() or root.resolve() != root
            or Path(environment_dir) != root / "task" / role or trial_paths is None
            or trial_paths.trial_dir != trial or type(supplied) is not list):
        raise ValueError("Exact owned role and trial paths required")
    sources = {"/logs/agent": trial / "agent", "/logs/verifier": trial / "verifier",
               "/logs/artifacts": trial / "artifacts/logs/artifacts"}
    # Bind representation is exactly Harbor0.25's Linux-owned log mount.
    expected = {target: {"type": "bind", "source": str(path), "target": target,
                         "bind": {"selinux": "z"}} for target, path in sources.items()}
    wanted = ["/logs/agent", "/logs/artifacts"] if role == "environment" else ["/logs/verifier"]
    allowed = ["/logs/verifier", *wanted] if role == "environment" else wanted
    if (len(supplied) != len(allowed) or any(type(mount) is not dict for mount in supplied)
            or [mount.get("target") for mount in supplied] != allowed
            or any(mount != expected[mount["target"]] for mount in supplied)):
        raise ValueError("Exact Harbor-owned role log mounts required")
    for target in wanted:
        leaf = sources[target]
        current = root
        for part in leaf.relative_to(root).parts:
            info = current.lstat()
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or info.st_uid != os.getuid() or info.st_mode & 0o022):
                raise ValueError("Protected owned log parent required")
            current = current / part
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
        info = leaf.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("Owned output log directory required")
        # Only these candidate/verifier output leaves need container write access.
        # Trial directories, proofs, task inputs and sealed evidence stay private.
        leaf.chmod(0o777)
    return [expected[target] for target in wanted]


class SMEDocker(DockerEnvironment):
    @classmethod
    def runtime(cls):
        command = operator_command(os.environ["ANVIL_BENCHMARK_DOCKER_COMMAND"])
        return ContainerRuntime(engine=command, compose=(*command, "compose"))

    @classmethod
    def _engine_cmd(cls, *args):
        if not args or args[0] not in {"info", "inspect", "ps", "cp", "version"}:
            raise ValueError("Implicit engine mutation/probe is prohibited")
        return cls.runtime().engine_cmd(*args)

    @staticmethod
    def _requires_egress_control(*, startup_network_policy, phase_network_policies):
        if any(
            policy.network_mode != NetworkMode.NO_NETWORK or policy.allowed_hosts
            for policy in [startup_network_policy, *phase_network_policies]
        ):
            raise ValueError("Only constant no-network policy is supported")
        return False

    @classmethod
    def _egress_control_kernel_support(cls):
        raise ValueError("Implicit SDK kernel probe is prohibited")

    @property
    def capabilities(self):
        return EnvironmentCapabilities(disable_internet=True, mounted=True, docker_compose=True)

    def __init__(self, *args, environment_dir, auto_mounts, task_env_config, **kwargs):
        root = Path(os.environ.get("ANVIL_HARBOR_ATTEMPT_ROOT", ""))
        config = validate_operator_config(root / "trial.json")
        self._reviewed_services = validate_service_proof_map(
            json.loads(os.environ.get("ANVIL_HARBOR_SERVICE_SHA256S", "null"))
        )
        if (
            importlib.metadata.version("harbor") != "0.25.0"
            or task_env_config.docker_image != IMAGE
            or task_env_config.network_mode != NetworkMode.NO_NETWORK
        ):
            raise ValueError("Exact pinned SME runtime/image/network required")
        self.role = Path(environment_dir).name
        if (
            self.role not in {"environment", "tests"}
            or kwargs.get("stream")
            or kwargs.get("mounts")
            or kwargs.get("extra_docker_compose")
            or kwargs.get("persistent_env")
            or "auto_mounting" in kwargs
            or args
        ):
            raise ValueError("Unsupported SME role or runtime extension")
        logs = owned_log_mounts(root, config, environment_dir, self.role,
                                kwargs.get("trial_paths"), auto_mounts)
        kwargs.pop("mounts", None)
        super().__init__(
            *args,
            environment_dir=environment_dir,
            auto_mounts=[],
            auto_mounting=False,
            mounts=logs,
            task_env_config=task_env_config,
            keep_containers=True,
            **kwargs,
        )

    async def _run_docker_compose_command(self, command, *args, **kwargs):
        guard_compose(command)
        return await super()._run_docker_compose_command(command, *args, **kwargs)

    async def _read_compose_config(self, *, phase="start"):
        # Harbor0.25 combines stderr into stdout for ordinary commands. Machine
        # JSON needs separate pipes; never strip warnings or scan for a JSON start.
        command = ["config", "--format", "json"]
        guard_compose(command)
        if not re.fullmatch(r"anvil-bm-[a-z0-9]+__(env|verifier__trial)", self.session_id):
            raise ValueError("Fresh scoped SME session required")
        runtime = type(self).runtime()
        argv = [
            *runtime.compose,
            "--project-name",
            _sanitize_docker_compose_project_name(self.session_id),
        ]
        if runtime.supports_compose_project_directory:
            argv.extend(["--project-directory", str(self.environment_dir.resolve().absolute())])
        for path in self._docker_compose_paths:
            argv.extend(["-f", str(path.resolve().absolute())])
        argv.extend(command)
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                argv,
                capture_output=True,
                timeout=10,
                check=False,
                env=self._compose_env_vars(include_os_env=True),
                cwd=str(self.environment_dir.resolve().absolute())
                if self.environment_dir.is_dir()
                else None,
            )
        except subprocess.TimeoutExpired as exc:
            if isinstance(exc.stderr, bytes) and len(exc.stderr) <= 1048576:
                write_compose_snapshot(
                    self.trial_paths.trial_dir, self.role, exc.stderr, stderr=True, phase=phase
                )
            raise RuntimeError("Resolved Compose configuration timed out; no startup") from None
        if (
            not isinstance(result.stdout, bytes)
            or not isinstance(result.stderr, bytes)
            or len(result.stdout) > 1048576
            or len(result.stderr) > 1048576
        ):
            raise ValueError("Resolved Compose output exceeds its bounded machine contract")
        write_compose_snapshot(
            self.trial_paths.trial_dir, self.role, result.stderr, stderr=True, phase=phase
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Resolved Compose configuration failed; private stderr receipt retained"
            )
        if not result.stdout:
            raise ValueError("Resolved Compose configuration is empty")
        return result.stdout

    async def _prepare_compose_projection(self, *, phase):
        if phase not in {"start", "preflight"}:
            raise ValueError("Exact Compose projection phase required")
        self._use_prebuilt = True
        self._mounts_compose_path = self._write_mounts_compose_file()
        self._env_compose_path = self._write_env_compose_file()
        self._resources_compose_path = await self._write_resources_compose_file()
        config = await self._read_compose_config(phase=phase)
        document = json.loads(config)
        if set(document["services"]) != {"main"}:
            raise ValueError("Only one isolated service supported")
        main = document["services"]["main"]
        try:
            validate_effective_service(
                main,
                role=self.role,
                reviewed_service_sha256=self._reviewed_services[self.role],
            )
        except Exception:
            # Diagnostic only: this filename is never a preflight/start proof.
            write_compose_snapshot(self.trial_paths.trial_dir, self.role, config,
                                   phase=phase, rejected=True)
            raise
        if (
            main.get("image") != IMAGE
            or main.get("build")
            or main.get("network_mode") != "none"
            or not main.get("read_only")
            or main.get("user") != "10001:10001"
            or main.get("privileged")
            or main.get("ports")
            or main.get("devices")
            or main.get("pid")
            or main.get("ipc")
            or main.get("pull_policy") != "never"
        ):
            raise ValueError("Resolved SME isolation profile changed")
        allowed = (
            {"/workspace/inputs", "/logs/agent", "/logs/artifacts"}
            if self.role == "environment"
            else {"/private", "/sealed", "/logs/verifier"}
        )
        for mount in main.get("volumes", []):
            if (
                mount["type"] != "bind"
                or mount["target"] not in allowed
                or mount["target"] in {"/workspace/inputs", "/private", "/sealed"}
                and not mount.get("read_only")
            ):
                raise ValueError("Unapproved SME host mount")
            source = Path(mount["source"])
            root = self.environment_dir.parent.parent.resolve()
            if (
                not source.is_dir()
                or source.is_symlink()
                or not source.resolve().is_relative_to(root)
            ):
                raise ValueError("SME mount source is missing or outside the owned trial")
        if phase == "start" and "ANVIL_HARBOR_FIXED_CONTEXT" in os.environ:
            prior = self.trial_paths.trial_dir / ("sme-preflight-compose-" + self.role + ".json")
            info = prior.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or not 0 < info.st_size <= 1048576
                or json.loads(prior.read_bytes()) != document
            ):
                raise ValueError("Actual start projection differs from paired preflight")
        write_compose_snapshot(self.trial_paths.trial_dir, self.role, config, phase=phase)
        return document

    async def preflight_projection(self):
        # Config rendering only: no image probe, startup, upload, callback or stop.
        return await self._prepare_compose_projection(phase="preflight")

    async def start(self, force_build):
        if force_build or not re.fullmatch(
            r"anvil-bm-[a-z0-9]+__(env|verifier__trial)", self.session_id
        ):
            raise ValueError("Fresh scoped SME session required; builds prohibited")
        prefix = type(self).runtime().engine
        result = await asyncio.to_thread(
            subprocess.run,
            [
                *prefix,
                "ps",
                "-aq",
                "--filter",
                "label=com.docker.compose.project=" + self.session_id,
            ],
            capture_output=True,
            timeout=10,
            check=True,
        )
        if result.stdout.strip():
            raise ValueError("Existing native session cannot be reused")
        image = await asyncio.to_thread(
            subprocess.run,
            [*prefix, "inspect", "--type", "image", IMAGE],
            capture_output=True,
            timeout=10,
            check=True,
        )
        require_cached_image(json.loads(image.stdout)[0])
        await self._prepare_compose_projection(phase="start")
        await self._run_docker_compose_command(
            ["up", "--detach", "--wait", "--no-build", "--pull", "never"]
        )
        await self.ensure_dirs(self._mount_targets(writable_only=True))


def request_gateway(path, session):
    deadline = os.environ.get("ANVIL_HARBOR_GATEWAY_TIMEOUT_SECONDS", "120")
    if not deadline.isascii() or not deadline.isdecimal() or not 1 <= int(deadline) <= 930:
        raise ValueError("Bounded host-mediator deadline required")
    with closing(UnixConnection(os.environ["ANVIL_HARBOR_GATEWAY_SOCKET"])) as connection:
        connection.timeout = int(deadline)
        connection.request(
            "POST",
            path,
            json.dumps({"session_id": session}),
            {
                "Authorization": "Bearer " + os.environ["ANVIL_HARBOR_GATEWAY_TOKEN"],
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        data = response.read(65537)
        if response.status != 200 or len(data) > 65536:
            raise RuntimeError("SME gateway rejected request; no retry")
        return json.loads(data)


class SMEAgent(BaseAgent):
    @staticmethod
    def name():
        return "anvil-sme-mediated-v1"

    def version(self):
        return "1.0.0"

    async def setup(self, environment):
        return

    async def run(self, instruction, environment, context):
        if await asyncio.to_thread(request_gateway, "/actor", environment.session_id) != {
            "status": "completed"
        }:
            raise RuntimeError("Incomplete native actor")


class SMEVerifier(BaseVerifier):
    async def verify(self):
        result = await asyncio.to_thread(request_gateway, "/evaluate", self.environment.session_id)
        return VerifierResult(rewards={"reward": result["reward"]})


async def main(config_path):
    validated = validate_operator_config(config_path)
    config = TrialConfig.model_validate(validated)
    if (
        config.environment.import_path != "anvil_harbor.environment:LocalComponentsDocker"
        or config.verifier.import_path != "anvil_harbor.sme:SMEVerifier"
        or config.environment.delete
    ):
        raise ValueError("Exact retained SME profile required")
    canary = config.trials_dir / config.trial_name / "verifier/native-canary"
    canary.parent.mkdir(parents=True, exist_ok=True)
    canary.write_text("PRIVATE-FICTIONAL-ARITHMETIC-V1")
    trial = await Trial.create(config)
    result = await trial.run()
    if result.exception_info or result.verifier_result is None:
        raise RuntimeError("Native Harbor trial incomplete")
    print(
        "ANVIL_SME_RESULT="
        + json.dumps({"rewards": result.verifier_result.rewards, "trial_id": str(result.id)})
    )


if __name__ == "__main__":
    import sys

    asyncio.run(main(sys.argv[1]))
