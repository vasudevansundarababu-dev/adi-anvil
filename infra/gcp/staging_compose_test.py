"""Offline tests for container separation and paid-off rendering."""
import unittest
from pathlib import Path
from staging_compose import render


class ComposeSafety(unittest.TestCase):
    def setUp(self):
        self.images = {name: f"example/{name}@sha256:" + "a" * 64 for name in ("backend", "web", "postgres", "neo4j", "keycloak", "caddy")}
        self.compose = render(self.images)

    def test_ordinary_worker_and_migration_have_no_private_access(self):
        for name in ("worker", "migrate"):
            service = self.compose["services"][name]
            self.assertNotIn("vault", str(service.get("volumes", [])))
            self.assertNotIn("ANVIL_BENCHMARK_VAULT_ROOT", service["environment"])
        self.assertNotIn("docker.sock", str(self.compose))
        self.assertNotIn("evaluator", self.compose["services"])

    def test_paid_flags_override_env_files_and_are_actual_config_names(self):
        for name in ("api", "worker", "migrate"):
            env = self.compose["services"][name]["environment"]
            for flag in ("ANVIL_LIVE_PROVIDERS_ENABLED", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", "ANVIL_IMPORT_GENERATION_ENABLED", "ANVIL_REAL_EMAIL_ENABLED", "ANVIL_BENCHMARK_ENABLED", "ANVIL_BENCHMARK_EVALUATION_ENABLED", "ANVIL_BENCHMARK_OFFLINE_ENABLED"):
                self.assertEqual(env[flag], "false")
            self.assertEqual(env["ANVIL_TEST_HARBOR"], "0")
            self.assertEqual(env["ANVIL_SUPPORT_VERTEX_PROJECT"], "")
        support = Path(__file__).parents[2] / "services/backend/src/anvil/support.py"
        self.assertIn('os.environ.get("ANVIL_SUPPORT_VERTEX_PROJECT", "")', support.read_text())

    def test_isolated_env_paths_and_ports(self):
        env_paths = []
        for service in self.compose["services"].values():
            env_paths.extend(service["env_file"])
            self.assertEqual(service["restart"], "no")
        self.assertEqual(len(set(env_paths)), len(env_paths))
        self.assertTrue(all(p.startswith("/var/lib/anvil-staging/config/") for p in env_paths))
        api = self.compose["services"]["api"]
        self.assertEqual(api["command"][api["command"].index("--port") + 1], "8200")
        self.assertEqual(api["expose"], ["8200"])
        self.assertEqual(self.compose["services"]["web"]["expose"], ["3202"])

    def test_mutable_missing_extra_images_fail(self):
        for images in ({}, {**self.images, "backend": "latest"}, {**self.images, "extra": self.images["web"]}):
            with self.assertRaises(ValueError):
                render(images)


if __name__ == "__main__":
    unittest.main()
