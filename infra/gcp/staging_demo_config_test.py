"""Fixture-only config safety tests. No cloud, network, Docker or SQL calls."""
import copy
import io
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from staging_demo_config import generate, main, SECRET_KEYS, IMAGE_KEYS, ROOT, NATIVE_IMAGE


def fixture():
    c = {"mode": "fictional_demo_preparation", "project": "adi-anvil-mvp-2026", "root": ROOT,
         "cloud_service_account": None, "runtime_cloud_credentials": False,
         "native_fixture_image": NATIVE_IMAGE,
         "web_host": "anvil-stage.example.test", "auth_host": "auth-stage.example.test",
         "issuer": "https://auth-stage.example.test/realms/anvil-staging-demo",
         "source_sha": "a" * 40, "source_manifest_sha256": "b" * 64,
         "reviewed_invitation_sha256": "c" * 64,
         "images": {key: f"example/{key}@sha256:" + "d" * 64 for key in IMAGE_KEYS},
         "identity": {"user_id": "11111111-1111-4111-8111-111111111111", "subject": "22222222-2222-4222-8222-222222222222",
                      "organization_id": "33333333-3333-4333-8333-333333333333", "project_id": "44444444-4444-4444-8444-444444444444",
                      "email": "fixture-reviewer@example.test", "name": "Explicit fictional config fixture", "origin": "real_invited_oidc_identity", "organization_name": "Explicit fixture organization", "project_name": "Explicit fixture project"},
         "secret_references": {key: "projects/adi-anvil-mvp-2026/secrets/anvil-staging-demo-" + key.replace("_", "-") for key in SECRET_KEYS}}
    s = {key: hashlib.sha256(("FAKE-CONFIG-ONLY-" + key).encode()).hexdigest() for key in SECRET_KEYS}
    return c, s


def read_env(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines())


class DemoConfiguration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.parent = Path(self.temp.name).resolve()
        self.c, self.s = fixture()
        self.out = self.parent/"config"

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_private_artifacts_and_no_secret_status(self):
        status = generate(self.c, self.s, self.out)
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)
        for path in self.out.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        for secret in self.s.values():
            self.assertNotIn(secret, json.dumps(status))
        self.assertFalse(status["deployment_authorized"])
        self.assertTrue({"app.env", "worker.env", "migrate.env", "postgres.env", "realm.json", "Caddyfile", "operator.env", "postgres-init.sh"}.issubset(status["files"]))
        compose = json.loads((self.out/"compose.json").read_text())
        self.assertEqual(compose["name"], "adi-anvil-staging-demo")
        for service in compose["services"].values():
            for path in service["env_file"]:
                self.assertTrue(path.startswith("/var/lib/anvil-staging-demo/config/"))
                self.assertTrue((self.out/Path(path).name).is_file())

    def test_routing_and_exact_identity_callback_no_auto_approvals(self):
        generate(self.c, self.s, self.out)
        caddy = (self.out/"Caddyfile").read_text()
        self.assertLess(caddy.index("handle /api/*"), caddy.index("reverse_proxy web:3202"))
        self.assertIn("reverse_proxy api:8200", caddy)
        self.assertIn("rewrite * /api/v1/health", caddy)
        self.assertNotIn("127.0.0.1:8200", caddy)
        realm = json.loads((self.out/"realm.json").read_text())
        client = realm["clients"][0]
        self.assertEqual(client["redirectUris"], ["https://anvil-stage.example.test/api/v1/auth/callback"])
        self.assertFalse(client["directAccessGrantsEnabled"])
        self.assertFalse(client["serviceAccountsEnabled"])
        self.assertEqual(realm["users"][0]["id"], self.c["identity"]["subject"])
        self.assertTrue(realm["users"][0]["credentials"][0]["temporary"])
        self.assertFalse(realm["users"][0]["enabled"])
        self.assertFalse(realm["users"][0]["emailVerified"])
        self.assertNotIn("realmRoles", realm["users"][0])
        boot = json.loads((self.out/"identity-bootstrap-contract.json").read_text())
        self.assertEqual(boot["identity"]["user_id"], self.c["identity"]["user_id"])
        self.assertEqual(set(boot), {"schema", "target", "identity", "organization", "project", "reviewed_invitation_sha256"})
        self.assertEqual(boot["schema"], "anvil.staging.initial-admin.v1")
        self.assertEqual(boot["identity"]["origin"], "real_invited_oidc_identity")
        guards = json.loads((self.out/"deployment-guards.json").read_text())
        self.assertFalse(guards["identity_bootstrap"]["automatic_apply"])
        self.assertFalse(guards["identity_bootstrap"]["review_assignments_or_approvals_created"])
        self.assertIsNone(boot["target"]["vm_id"])
        observer = json.loads((self.out/"deployment-identity-manifest.json").read_text())
        self.assertEqual(observer["state"], "expected_not_observed")
        self.assertIsNone(observer["observed"]["postgres_system_identifier"])
        self.assertNotIn("identity", observer)

    def test_only_operator_has_evaluator_and_native_host_binding(self):
        generate(self.c, self.s, self.out)
        for name in ("app.env", "worker.env", "migrate.env"):
            env = read_env(self.out/name)
            self.assertNotIn("ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL", env)
            self.assertNotIn("ANVIL_HARBOR_DOCKER_HOST", env)
            self.assertEqual(env["ANVIL_TEST_HARBOR"], "0")
            self.assertEqual(env["ANVIL_SUPPORT_VERTEX_PROJECT"], "")
            for flag in ("ANVIL_LIVE_PROVIDERS_ENABLED", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", "ANVIL_IMPORT_GENERATION_ENABLED", "ANVIL_REAL_EMAIL_ENABLED"):
                self.assertEqual(env[flag], "false")
        api = read_env(self.out/"app.env")
        worker = read_env(self.out/"worker.env")
        self.assertNotIn("WORKER_DATABASE_URL", api)
        self.assertNotIn("ANVIL_BENCHMARK_VAULT_ROOT", worker)
        self.assertIn("anvil_worker:", worker["WORKER_DATABASE_URL"])
        operator = read_env(self.out/"operator.env")
        self.assertEqual(operator["ANVIL_HARBOR_DOCKER_HOST"], "unix://" + ROOT + "/.local/benchmark-docker/docker.sock")
        self.assertIn("anvil_staging_benchmark_evaluator_login:", operator["ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL"])
        self.assertIn("role%3Danvil_benchmark_evaluator", operator["ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL"])
        self.assertEqual(operator["ANVIL_BENCHMARK_OFFLINE_ENABLED"], "false")
        guards = json.loads((self.out/"deployment-guards.json").read_text())
        compose = json.loads((self.out/"compose.json").read_text())
        self.assertIn(guards["mounts"]["API_vault"]["host"]+":"+api["ANVIL_BENCHMARK_VAULT_ROOT"], compose["services"]["api"]["volumes"])
        self.assertEqual(guards["mounts"]["API_vault"]["host"], operator["ANVIL_BENCHMARK_VAULT_ROOT"])
        self.assertTrue(Path(operator["ANVIL_BENCHMARK_VAULT_ROOT"]).is_relative_to(ROOT))
        self.assertTrue(Path(operator["ARTIFACT_ROOT"]).is_relative_to(ROOT))
        self.assertFalse(guards["mounts"]["aliases_or_symlinks"])
        self.assertTrue(guards["migration_owner"]["initial_POSTGRES_USER_is_superuser"])

    def test_demo_opt_in_only_api_three_flags(self):
        self.c["fictional_benchmark_demo"] = True
        generate(self.c, self.s, self.out)
        for name in ("app.env", "worker.env", "operator.env"):
            env = read_env(self.out/name)
            for flag in ("ANVIL_BENCHMARK_ENABLED", "ANVIL_BENCHMARK_EVALUATION_ENABLED", "ANVIL_BENCHMARK_OFFLINE_ENABLED"):
                self.assertEqual(env[flag], "true" if name == "app.env" else "false")
            self.assertEqual(env["ANVIL_TEST_HARBOR"], "0")

    def test_real_config_module_accepts_generated_backend_settings_without_network(self):
        generate(self.c, self.s, self.out)
        source = Path(__file__).resolve().parents[2]/"services/backend/src"
        for name in ("app.env", "worker.env", "migrate.env", "operator.env"):
            env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(source), **read_env(self.out/name)}
            result = subprocess.run([sys.executable, "-c", "import anvil.config; assert anvil.config.ENV=='cloud'; print('actual config accepted')"], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "actual config accepted")

    def test_reject_unsafe_targets_secrets_identity_and_mutable_images_before_write(self):
        mutations = [lambda c: c.update(web_host="anvil-34-36-217-66.sslip.io"),
                     lambda c: c.update(auth_host="bad\n}", issuer="https://bad/realms/anvil-staging-demo"),
                     lambda c: c.update(issuer="https://other.example.test/realms/anvil"),
                     lambda c: c["identity"].update(subject="invented-non-uuid"),
                     lambda c: c["images"].update(backend="mutable:latest"),
                     lambda c: c.update(root="/var/lib/anvil"),
                     lambda c: c.update(cloud_service_account="current-production-account"),
                     lambda c: c.update(native_fixture_image="python:latest"),
                     lambda c: c["secret_references"].update(session="projects/adi-anvil-mvp-2026/secrets/anvil-session-key"),
                     lambda c: c.update(fictional_benchmark_demo=1)]
        for mutate in mutations:
            c = copy.deepcopy(self.c);mutate(c)
            with self.assertRaises((ValueError, TypeError, KeyError)):
                generate(c, self.s, self.out)
            self.assertFalse(self.out.exists())
        for secret in ("short", "x" * 32 + "\nINJECT=true"):
            s = self.s.copy();s["session"] = secret
            with self.assertRaises(ValueError):generate(self.c, s, self.out)
            self.assertFalse(self.out.exists())

    def test_existing_and_symlink_output_rejected(self):
        self.out.mkdir()
        with self.assertRaises(ValueError):generate(self.c, self.s, self.out)
        self.out.rmdir()
        target = self.parent/"other";target.mkdir()
        self.out.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):generate(self.c, self.s, self.out)
        self.assertEqual(list(target.iterdir()), [])

    def test_cli_fixture_secret_input_no_stdout_leak_or_execution(self):
        contract = self.parent/"contract.json";contract.write_text(json.dumps(self.c))
        secrets = self.parent/"fixture-secrets.json";secrets.write_text(json.dumps(self.s));secrets.chmod(0o600)
        argv = ["staging_demo_config", "--contract", str(contract), "--secrets-file", str(secrets), "--output", str(self.out)]
        stream = io.StringIO()
        with patch("sys.argv", argv), patch("subprocess.run", side_effect=AssertionError("execution forbidden")), redirect_stdout(stream):
            self.assertEqual(main(), 0)
        for value in self.s.values():self.assertNotIn(value, stream.getvalue())
        self.assertFalse(json.loads(stream.getvalue())["deployment_authorized"])

    def test_cli_rejects_nonprivate_secret_material_without_creating_output(self):
        contract = self.parent/"contract.json";contract.write_text(json.dumps(self.c))
        secrets = self.parent/"fixture-secrets.json";secrets.write_text(json.dumps(self.s));secrets.chmod(0o644)
        stream = io.StringIO()
        argv = ["staging_demo_config", "--contract", str(contract), "--secrets-file", str(secrets), "--output", str(self.out)]
        with patch("sys.argv", argv), redirect_stdout(stream):self.assertEqual(main(), 2)
        self.assertFalse(self.out.exists())
        for value in self.s.values():self.assertNotIn(value, stream.getvalue())

    def test_invitation_activation_requires_separate_explicit_binding(self):
        self.c["activate_invited_user"] = True
        with self.assertRaises(ValueError):generate(self.c, self.s, self.out)
        self.assertFalse(self.out.exists())
        self.c["reviewed_account_activation_sha256"] = "f" * 64
        generate(self.c, self.s, self.out)
        realm = json.loads((self.out/"realm.json").read_text())
        self.assertTrue(realm["users"][0]["enabled"])
        self.assertFalse(realm["users"][0]["emailVerified"])
        self.assertNotIn("realmRoles", realm["users"][0])
        guards = json.loads((self.out/"deployment-guards.json").read_text())
        self.assertFalse(guards["deployment_authorized"])
        self.assertFalse(guards["invited_account"]["trusted_activation_receipt_verified"])


if __name__ == "__main__":
    unittest.main()
