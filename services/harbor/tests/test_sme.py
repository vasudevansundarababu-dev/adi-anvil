import asyncio
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
        for network in ("none", "host"):
            with self.subTest(network=network), tempfile.TemporaryDirectory() as temporary:
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
                                "network_mode": network,
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

                runtime = SimpleNamespace(engine=("sudo", "-n", "/usr/bin/docker"))
                with (
                    patch.object(SMEDocker, "runtime", return_value=runtime),
                    patch(
                        "anvil_harbor.sme.subprocess.run",
                        side_effect=[
                            SimpleNamespace(stdout=b""),
                            SimpleNamespace(stdout=b'[{"Os":"linux"}]'),
                        ],
                    ),
                    patch.object(instance, "_write_mounts_compose_file"),
                    patch.object(instance, "_write_env_compose_file"),
                    patch.object(instance, "_write_resources_compose_file", new=AsyncMock()),
                    patch.object(instance, "_run_docker_compose_command", side_effect=compose),
                    patch.object(instance, "ensure_dirs", new=AsyncMock()),
                ):
                    if network == "none":
                        asyncio.run(instance.start(False))
                        self.assertEqual(
                            json.loads((trial / "sme-compose-environment.json").read_text()),
                            json.loads(resolved),
                        )
                        self.assertEqual(
                            calls[-1], ["up", "--detach", "--wait", "--no-build", "--pull", "never"]
                        )
                    else:
                        with self.assertRaises(ValueError):
                            asyncio.run(instance.start(False))
                        self.assertEqual(calls, [["config", "--format", "json"]])
                        self.assertFalse((trial / "sme-compose-environment.json").exists())
                self.assertEqual(calls[0], ["config", "--format", "json"])

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
