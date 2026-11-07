import json
import tempfile
import unittest
from pathlib import Path

from anvil_harbor.sme import SMEDocker, guard_compose, operator_command
from harbor.models.task.config import EnvironmentConfig, NetworkMode, NetworkPolicy
from harbor.models.trial.paths import TrialPaths


class RestrictedAdapterTests(unittest.TestCase):
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
