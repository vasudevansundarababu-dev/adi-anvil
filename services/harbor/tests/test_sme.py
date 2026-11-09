import asyncio
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

from anvil_harbor.sme import (
    IMAGE,
    SMEDocker,
    guard_compose,
    operator_command,
    write_compose_snapshot,
)
from harbor.models.task.config import EnvironmentConfig, NetworkMode, NetworkPolicy
from harbor.models.trial.paths import TrialPaths


class RestrictedAdapterTests(unittest.TestCase):
    def test_compose_snapshot_is_operator_owned_fresh_private_and_never_follows_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            data = '{"services":{"main":{}}}'
            snapshot = write_compose_snapshot(folder, "environment", data)
            self.assertEqual(snapshot.read_text(), data)
            self.assertEqual(snapshot.stat().st_uid, os.getuid())
            self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                write_compose_snapshot(folder, "environment", "replacement")
            target = folder / "untouched"
            target.write_text("original")
            (folder / "sme-compose-tests.json").symlink_to(target)
            with self.assertRaises(FileExistsError):
                write_compose_snapshot(folder, "tests", data)
            self.assertEqual(target.read_text(), "original")
            link = folder / "linked-directory"
            link.symlink_to(folder, target_is_directory=True)
            with self.assertRaises(ValueError):
                write_compose_snapshot(link, "tests", data)

    def test_native_start_captures_sudo_config_stdout_without_root_created_file(self):
        for scenario in ("valid_warning", "unsafe", "malformed", "nonzero", "oversized", "timeout"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary).resolve()
                environment = folder / "environment"
                environment.mkdir()
                trial = folder / "trial"
                trial.mkdir(mode=0o700)
                instance = SMEDocker(
                    environment_dir=environment,
                    environment_name="fixture",
                    session_id="anvil-bm-unit__env",
                    trial_paths=TrialPaths(trial_dir=trial),
                    task_env_config=EnvironmentConfig(
                        docker_image=IMAGE, network_mode="no-network", cpus=1, memory_mb=2048
                    ),
                    auto_mounts=[],
                    network_policy=NetworkPolicy(network_mode=NetworkMode.NO_NETWORK),
                )
                resolved = json.dumps(
                    {
                        "services": {
                            "main": {
                                "image": IMAGE,
                                "network_mode": "host" if scenario == "unsafe" else "none",
                                "read_only": True,
                                "user": "10001:10001",
                                "pull_policy": "never",
                                "volumes": [],
                            }
                        }
                    }
                )
                calls = []

                async def compose(command, *args, **kwargs):
                    calls.append(command)
                    # Reproduces the privilege boundary: the old --output form
                    # asks sudo Docker to create an unreadable root-owned file.
                    if "--output" in command:
                        raise PermissionError("privileged writer boundary")
                    return SimpleNamespace(stdout=resolved)

                runtime = SimpleNamespace(
                    engine=("sudo", "-n", "/usr/bin/docker"),
                    compose=("sudo", "-n", "/usr/bin/docker", "compose"),
                    supports_compose_project_directory=True,
                )
                stdout = (
                    b"warning-prefix\n" + resolved.encode()
                    if scenario == "malformed"
                    else b"x" * 1048577
                    if scenario == "oversized"
                    else resolved.encode()
                )
                stderr = b"Compose diagnostic warning; PRIVATE-TEST-ONLY"
                config_result = SimpleNamespace(
                    stdout=stdout, stderr=stderr, returncode=1 if scenario == "nonzero" else 0
                )
                files = [environment / "docker-compose.yaml", trial / "mounts.yaml"]
                with (
                    patch.object(SMEDocker, "runtime", return_value=runtime),
                    patch(
                        "anvil_harbor.sme.subprocess.run",
                        side_effect=[
                            SimpleNamespace(stdout=b""),
                            SimpleNamespace(stdout=b'[{"Os":"linux"}]'),
                            subprocess.TimeoutExpired("config", 10, stderr=stderr)
                            if scenario == "timeout"
                            else config_result,
                        ],
                    ) as run,
                    patch.object(
                        SMEDocker,
                        "_docker_compose_paths",
                        new_callable=PropertyMock,
                        return_value=files,
                    ),
                    patch.object(
                        instance,
                        "_compose_env_vars",
                        return_value={"HOME": "/owned/config", "SECRET_TEST_VALUE": "NEVER_LOG"},
                    ) as env,
                    patch.object(instance, "_write_mounts_compose_file"),
                    patch.object(instance, "_write_env_compose_file"),
                    patch.object(instance, "_write_resources_compose_file", new=AsyncMock()),
                    patch.object(instance, "_run_docker_compose_command", side_effect=compose),
                    patch.object(instance, "ensure_dirs", new=AsyncMock()),
                ):
                    if scenario == "valid_warning":
                        asyncio.run(instance.start(False))
                        self.assertEqual(
                            json.loads((trial / "sme-compose-environment.json").read_text()),
                            json.loads(resolved),
                        )
                        self.assertEqual(
                            calls[-1], ["up", "--detach", "--wait", "--no-build", "--pull", "never"]
                        )
                        receipt = trial / "sme-compose-environment.stderr"
                        self.assertEqual(receipt.read_bytes(), stderr)
                        self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
                    else:
                        with self.assertRaises((ValueError, RuntimeError)) as error:
                            asyncio.run(instance.start(False))
                        self.assertNotIn("PRIVATE-TEST-ONLY", str(error.exception))
                        self.assertNotIn("NEVER_LOG", str(error.exception))
                        self.assertEqual(calls, [])
                        self.assertFalse((trial / "sme-compose-environment.json").exists())
                    config_call = run.call_args_list[2]
                    self.assertEqual(
                        config_call.args[0],
                        [
                            *runtime.compose,
                            "--project-name",
                            "anvil-bm-unit__env",
                            "--project-directory",
                            str(environment),
                            "-f",
                            str(files[0]),
                            "-f",
                            str(files[1]),
                            "config",
                            "--format",
                            "json",
                        ],
                    )
                    self.assertTrue(config_call.kwargs["capture_output"])
                    self.assertFalse(config_call.kwargs["check"])
                    self.assertEqual(config_call.kwargs["timeout"], 10)
                    self.assertEqual(config_call.kwargs["cwd"], str(environment))
                    self.assertEqual(config_call.kwargs["env"], env.return_value)
                    env.assert_called_once_with(include_os_env=True)

    def test_engine_probe_and_mutations_rejected_before_operator_access(self):
        for verb in ["run", "container", "pull", "build", "rm", "volume", "system", "network"]:
            with self.subTest(verb=verb), self.assertRaises(ValueError):
                SMEDocker._engine_cmd(verb)

    def test_group_accessible_or_nonempty_client_config_rejected(self):
        with tempfile.TemporaryDirectory() as home:
            folder = Path(home)
            command = ["/usr/bin/docker", "--config", home, "--host", "unix:///tmp/owned.sock"]
            folder.chmod(0o770)
            with self.assertRaises(ValueError):
                operator_command(json.dumps(command))
            folder.chmod(0o700)
            (folder / "config.json").write_text("{}")
            with self.assertRaises(ValueError):
                operator_command(json.dumps(command))

    def test_static_none_needs_no_probe_or_privileged_sidecar(self):
        policy = NetworkPolicy(network_mode=NetworkMode.NO_NETWORK)
        self.assertFalse(
            SMEDocker._requires_egress_control(
                startup_network_policy=policy, phase_network_policies=[policy]
            )
        )
        with self.assertRaises(ValueError):
            SMEDocker._egress_control_kernel_support()

    def test_public_allowlist_and_network_transitions_fail_closed(self):
        none = NetworkPolicy(network_mode=NetworkMode.NO_NETWORK)
        for policy in [
            NetworkPolicy(network_mode=NetworkMode.PUBLIC),
            NetworkPolicy(network_mode=NetworkMode.ALLOWLIST, allowed_hosts=["example.com"]),
        ]:
            for startup, phases in [(policy, []), (none, [policy])]:
                with self.subTest(startup=startup, phases=phases), self.assertRaises(ValueError):
                    SMEDocker._requires_egress_control(
                        startup_network_policy=startup, phase_network_policies=phases
                    )

    def test_compose_mutations_and_implicit_pull_flags_are_rejected(self):
        commands = [
            [verb] for verb in ["build", "pull", "down", "rm", "run", "restart", "create", "kill"]
        ]
        commands += [
            ["up"],
            ["up", "--build"],
            ["up", "--remove-orphans"],
            ["up", "--pull", "always"],
            ["exec", "--privileged", "main", "true"],
        ]
        for command in commands:
            with self.subTest(command=command), self.assertRaises(ValueError):
                guard_compose(command)
        for command in [
            ["up", "--detach", "--wait", "--no-build", "--pull", "never"],
            ["exec", "-T", "main", "true"],
            ["cp", "main:/logs/agent", "/tmp/owned"],
            ["config", "--format", "json"],
            ["stop"],
            ["ps", "-q"],
        ]:
            guard_compose(command)

    def test_explicit_operator_command_requires_local_socket_and_empty_private_config(self):
        with tempfile.TemporaryDirectory() as home:
            command = [
                "sudo",
                "-n",
                "/usr/bin/docker",
                "--config",
                home,
                "--host",
                "unix:///workspace/anvil-recovered/.local/benchmark-docker/docker.sock",
            ]
            self.assertEqual(operator_command(json.dumps(command)), tuple(command))
            for bad in [
                command[:-2],
                command[:-1] + ["tcp://remote:2375"],
                ["sh", "-c", "docker"],
                command + ["--context", "default"],
            ]:
                with self.subTest(command=bad), self.assertRaises(ValueError):
                    operator_command(json.dumps(bad))

    def test_constructor_is_inert_and_drops_private_actor_mount(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            environment = folder / "environment"
            environment.mkdir()
            config = EnvironmentConfig(
                docker_image="python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e",
                network_mode="no-network",
                cpus=1,
                memory_mb=2048,
            )
            instance = SMEDocker(
                environment_dir=environment,
                environment_name="fixture",
                session_id="anvil-bm-unit__env",
                trial_paths=TrialPaths(trial_dir=folder / "trial"),
                task_env_config=config,
                auto_mounts=[
                    {"type": "bind", "source": str(folder / "private"), "target": "/logs/verifier"},
                    {"type": "bind", "source": str(folder / "actor"), "target": "/logs/agent"},
                ],
                network_policy=NetworkPolicy(network_mode=NetworkMode.NO_NETWORK),
            )
            self.assertTrue(instance.capabilities.disable_internet)
            self.assertFalse(instance.capabilities.dynamic_network_policy)
            self.assertFalse(instance._enable_egress_control)
            self.assertTrue(instance._keep_containers)
            self.assertNotIn("/logs/verifier", [mount["target"] for mount in instance._host_mounts])
            self.assertFalse((folder / "private").exists())


if __name__ == "__main__":
    unittest.main()
