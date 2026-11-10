"""Offline tests for container separation and paid-off rendering."""
import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from staging_compose import main, render, render_demo


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

    def test_explicit_demo_changes_only_three_api_gates(self):
        enabled = render(self.images, fictional_benchmark_demo=True)
        expected = copy.deepcopy(self.compose)
        for flag in ("ANVIL_BENCHMARK_ENABLED", "ANVIL_BENCHMARK_EVALUATION_ENABLED", "ANVIL_BENCHMARK_OFFLINE_ENABLED"):
            expected["services"]["api"]["environment"][flag] = "true"
        self.assertEqual(enabled, expected)
        self.assertEqual(render(self.images, fictional_benchmark_demo=False), self.compose)

    def test_demo_preserves_paid_off_and_operator_separation(self):
        rendered = render(self.images, fictional_benchmark_demo=True)
        for name in ("api", "worker", "migrate"):
            service = rendered["services"][name]
            env = service["environment"]
            for flag in ("ANVIL_LIVE_PROVIDERS_ENABLED", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", "ANVIL_IMPORT_GENERATION_ENABLED", "ANVIL_REAL_EMAIL_ENABLED"):
                self.assertEqual(env[flag], "false")
            self.assertEqual(env["ANVIL_TEST_HARBOR"], "0")
            self.assertEqual(env["ANVIL_SUPPORT_VERTEX_PROJECT"], "")
            self.assertEqual(env["ANVIL_SUPPORT_MODEL"], "")
            self.assertNotIn("ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL", env)
            self.assertNotIn("ANVIL_HARBOR_DOCKER_HOST", env)
            self.assertFalse(service.get("privileged", False))
            self.assertNotIn("sudo", service.get("command", []))
            self.assertNotIn("docker.sock", str(service))
        self.assertEqual(set(rendered["services"]), set(self.compose["services"]))
        for name in ("worker", "migrate"):
            self.assertEqual(rendered["services"][name], self.compose["services"][name])

    def test_profile_rejects_implicit_truthiness(self):
        for value in (None, "false", "true", 0, 1, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                render(self.images, fictional_benchmark_demo=value)

    def test_cli_is_static_opt_in_rendering_without_execution(self):
        for opt_in in (False, True):
            output = io.StringIO()
            argv = ["staging_compose", "--images", "/nonsecret/image-manifest.json"] + (["--fictional-benchmark-demo"] if opt_in else [])
            with patch("sys.argv", argv), patch.object(Path, "read_text", return_value=json.dumps(self.images)), patch("subprocess.run", side_effect=AssertionError("execution forbidden")), redirect_stdout(output):
                self.assertEqual(main(), 0)
            self.assertEqual(json.loads(output.getvalue()), render(self.images, fictional_benchmark_demo=opt_in))


    def test_explicit_new_demo_binding_leaves_old_default_unchanged(self):
        old = render(self.images)
        new = render_demo(self.images)
        self.assertEqual(old["name"], "adi-anvil-staging")
        self.assertIn("/var/lib/anvil-staging/config/app.env", old["services"]["api"]["env_file"])
        self.assertEqual(new["name"], "adi-anvil-staging-demo")
        self.assertEqual(new["networks"]["staging"]["name"], "adi-anvil-staging-demo")
        self.assertEqual(new["services"]["postgres"]["ports"], ["127.0.0.1:5432:5432"])
        self.assertEqual(new["services"]["api"]["volumes"], ["/opt/anvil/.data/artifacts:/app/.data/artifacts", "/opt/anvil/.local/benchmark-vault:/app/.data/benchmark-vault"])
        self.assertEqual(new["services"]["worker"]["volumes"], ["/opt/anvil/.data/artifacts:/app/.data/artifacts"])
        self.assertNotIn("volumes", new["services"]["migrate"])
        self.assertTrue(any("postgres-init.sh" in p for p in new["services"]["postgres"]["volumes"]))
        self.assertIn("realm.json", str(new["services"]["keycloak"]["volumes"]))
        self.assertEqual(new["services"]["migrate"]["depends_on"], {"postgres": {"condition": "service_healthy"}})

    def test_new_demo_paid_and_native_boundaries_with_opt_in(self):
        for opted in (False, True):
            new = render_demo(self.images, fictional_benchmark_demo=opted)
            self.assertEqual(len(new["services"]), 8)
            for name, service in new["services"].items():
                self.assertEqual(service["env_file"], [f"/var/lib/anvil-staging-demo/config/{'app' if name=='api' else name}.env"])
                self.assertNotIn("docker.sock", str(service))
                self.assertNotIn("ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL", service.get("environment", {}))
            for name in ("api", "worker", "migrate"):
                env = new["services"][name]["environment"]
                self.assertEqual(env["ANVIL_TEST_HARBOR"], "0")
                for key in ("ANVIL_LIVE_PROVIDERS_ENABLED", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", "ANVIL_IMPORT_GENERATION_ENABLED", "ANVIL_REAL_EMAIL_ENABLED"):
                    self.assertEqual(env[key], "false")
                self.assertEqual(env["ANVIL_SUPPORT_VERTEX_PROJECT"], "")
                self.assertEqual(env["ANVIL_BENCHMARK_OFFLINE_ENABLED"], "true" if opted and name=="api" else "false")


    def test_new_demo_resource_budget_and_migration_order_without_native_cap_changes(self):
        from decimal import Decimal
        new = render_demo(self.images)
        steady = [service for name, service in new["services"].items() if name != "migrate"]
        memory = sum(int(service["mem_limit"].removesuffix("m")) for service in steady)
        cpus = sum(Decimal(service["cpus"]) for service in steady)
        self.assertEqual(memory, 5760)
        self.assertLessEqual(memory, 6*1024)
        self.assertEqual(cpus, Decimal("3.00"))
        for service in new["services"].values():self.assertGreater(service["pids_limit"], 0)
        self.assertEqual(new["services"]["migrate"]["restart"], "no")
        for name in ("api", "worker"):
            self.assertEqual(new["services"][name]["depends_on"]["migrate"]["condition"], "service_completed_successfully")
        # There is no actor/evaluator service whose caps could be silently
        # reduced; the reviewed native profile remains separately source-bound.
        self.assertEqual(set(new["services"]), {"postgres", "neo4j", "keycloak", "migrate", "api", "worker", "web", "caddy"})
        for service in render(self.images)["services"].values():
            self.assertNotIn("mem_limit", service)
            self.assertNotIn("cpus", service)
            self.assertNotIn("pids_limit", service)


if __name__ == "__main__":
    unittest.main()
