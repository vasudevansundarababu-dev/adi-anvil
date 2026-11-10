import unittest
from datetime import datetime, timezone

from overnight_qa_model_worker import environment, unit


class ModelWorkerBoundary(unittest.TestCase):
    def values(self):
        return {
            "DATABASE_URL": "postgresql://anvil_app:synthetic@postgres:5432/anvil",
            "WORKER_DATABASE_URL": "postgresql://anvil_worker:synthetic@postgres:5432/anvil",
            "ANVIL_SESSION_KEY": "synthetic-qa-session-test-only-123456789",
            "OPENAI_API_KEY": "must-not-forward",
            "MIGRATION_DATABASE_URL": "must-not-forward",
            "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "true",
        }

    def test_scoped_identities_no_inherited_provider_or_owner_keys(self):
        result = environment(self.values(), "a" * 64)
        self.assertTrue(result["DATABASE_URL"].startswith("postgresql://anvil_app:"))
        self.assertIn("127.0.0.1:55432/anvil?connect_timeout=5", result["DATABASE_URL"])
        self.assertEqual(result["ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED"], "false")
        self.assertNotIn("OPENAI_API_KEY", result)
        self.assertNotIn("MIGRATION_DATABASE_URL", result)
        self.assertNotIn("ANVIL_QA_SECRET_RESOURCE", result)
        path = result["ANVIL_HARBOR_WORK_ROOT"] + "/" + "0" * 36 + "/attempt/.bm-gw-12345678/gateway.sock"
        self.assertLess(len(path.encode()), 104, "Nested native socket needs AF_UNIX headroom")

    def test_owner_identity_and_production_secret_refused(self):
        for field, value in (
            ("DATABASE_URL", "postgresql://anvil_migration:synthetic@postgres:5432/anvil"),
            ("ANVIL_QA_SECRET_RESOURCE", "projects/123/secrets/anvil-import-generation"),
        ):
            values = self.values()
            values[field] = value
            with self.assertRaises(ValueError):
                environment(values, "a" * 64)

    def test_unit_retains_private_tmp_and_only_owned_artifact_bind(self):
        text = unit("a" * 64)
        self.assertIn("PrivateTmp=true", text)
        self.assertIn(
            "/var/lib/anvil-overnight-qa/artifacts:/opt/anvil-overnight-qa/source/.data/artifacts",
            text,
        )
        self.assertNotIn("cloud-config", text)
        self.assertNotIn("docker.sock:/", text)

    def test_explicit_qa_smoke_requires_store_and_rejects_shutdown(self):
        values = self.values()
        values["ANVIL_QA_MODEL_SMOKE_ENABLED"] = "true"
        with self.assertRaises(ValueError):
            environment(values, "a" * 64)
        values["ANVIL_QA_SECRET_RESOURCE"] = "projects/123/secrets/anvil-qa-model-credentials"
        result = environment(values, "a" * 64, now=datetime(2026, 11, 10, 15, tzinfo=timezone.utc))
        self.assertEqual(result["ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED"], "true")
        self.assertEqual(result["ANVIL_LIVE_PROVIDERS_ENABLED"], "false")
        with self.assertRaises(ValueError):
            environment(values, "a" * 64, now=datetime(2026, 11, 11, 18, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
