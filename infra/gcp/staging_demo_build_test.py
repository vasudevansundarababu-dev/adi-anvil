import copy
import io
import json
from pathlib import Path
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from staging_demo_build import recipe, main, CLI, CONFIG


class BuildPreparation(unittest.TestCase):
    def setUp(self):
        self.c = {"project": "adi-anvil-mvp-2026", "region": "us-west1", "build_identity": "anvil-staging-demo-build@adi-anvil-mvp-2026.iam.gserviceaccount.com", "registry": "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-staging-demo", "source_sha": "a"*40, "source_archive_sha256": "b"*64, "source_manifest_sha256": "c"*64, "build_context_sha256": "d"*64, "fresh_context_directory": "/private/tmp/FICTIONAL-NONEXISTENT-CONTEXT", "build_tag": "a"*12+"-fixture-only"}

    def test_exact_backend_web_only_with_isolated_identity_and_no_execution(self):
        result = recipe(self.c)
        self.assertFalse(result["executed"])
        self.assertFalse(result["build_authorized"])
        config = result["cloudbuild_config_to_review_and_materialize"]
        self.assertEqual([s["id"] for s in config["steps"]], ["backend", "web"])
        self.assertEqual(len(config["images"]), 2)
        self.assertEqual(config["serviceAccount"], "projects/adi-anvil-mvp-2026/serviceAccounts/"+self.c["build_identity"])
        command = result["prospective_submit_argv"]
        self.assertEqual(command[0], "env")
        self.assertIn(CLI, command)
        self.assertIn("CLOUDSDK_CONFIG="+CONFIG, command)
        self.assertNotIn("gcloud", command)
        self.assertNotIn("golden", json.dumps(config))
        self.assertNotIn("harbor", json.dumps(config))

    def test_missing_or_unapproved_target_identity_and_hashes_fail(self):
        for key in self.c:
            c = copy.deepcopy(self.c);c[key] = None
            with self.subTest(key=key), self.assertRaises((ValueError, TypeError)):
                recipe(c)
        for key, value in (("project", "praxis"), ("registry", "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil"), ("build_identity", "anvil-vm@adi-anvil-mvp-2026.iam.gserviceaccount.com"), ("fresh_context_directory", "/tmp/../current-secrets")):
            c = copy.deepcopy(self.c);c[key] = value
            with self.assertRaises(ValueError):recipe(c)

    def test_cli_only_prints_review_recipe(self):
        stream = io.StringIO()
        with patch("sys.argv", ["staging_demo_build", "--contract", "fixture.json"]), patch.object(Path, "read_text", return_value=json.dumps(self.c)), patch("subprocess.run", side_effect=AssertionError("execution forbidden")), redirect_stdout(stream):
            self.assertEqual(main(), 0)
        self.assertFalse(json.loads(stream.getvalue())["build_authorized"])


if __name__ == "__main__":
    unittest.main()
