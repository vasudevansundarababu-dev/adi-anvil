"""Local build-packet validation only; no uploads, builds or cloud changes."""

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from staging_demo_build import CLI, CONFIG, LIFECYCLE, canonical, main, recipe


class BuildPreparation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.context = self.root / "public-context"
        self.context.mkdir(mode=0o700)
        rows = []
        for relative in (
            ".dockerignore",
            ".gcloudignore",
            ".env.example",
            "infra/docker/backend.Dockerfile",
            "infra/docker/web.Dockerfile",
            "source.py",
        ):
            path = self.context / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Original fictional build validation fixture: " + relative)
            rows.append(
                {
                    "path": relative,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "size": path.stat().st_size,
                }
            )
        rows.sort(key=lambda row: row["path"])
        selected = [row for row in rows if row["path"] not in {".gcloudignore", ".env.example"}]

        def write(name, value):
            path = self.root / name
            path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
            path.chmod(0o600)
            return str(path), hashlib.sha256(path.read_bytes()).hexdigest()

        native, native_sha = write(
            "native.json",
            {
                "git_head": "a" * 40,
                "files": {
                    "source.py": next(row["sha256"] for row in rows if row["path"] == "source.py")
                },
            },
        )
        context_sha, upload_sha = (
            hashlib.sha256(canonical(rows)).hexdigest(),
            hashlib.sha256(canonical(selected)).hexdigest(),
        )
        inventory, inventory_sha = write(
            "context.json",
            {
                "source_sha": "a" * 40,
                "source_archive_sha256": "b" * 64,
                "inventory": rows,
                "context_inventory_sha256": context_sha,
            },
        )
        upload, upload_receipt_sha = write(
            "upload.json",
            {
                "source_sha": "a" * 40,
                "source_archive_sha256": "b" * 64,
                "files": selected,
                "unfiltered_context_inventory_sha256": context_sha,
                "upload_inventory_sha256": upload_sha,
                "status": "local_upload_inventory_verified_not_uploaded",
                "cloud_mutations": False,
                "cloud_build_id": None,
                "gcs_object": None,
                "gcs_generation": None,
                "uploaded_package_sha256": None,
            },
        )
        lifecycle, lifecycle_sha = write("lifecycle.json", LIFECYCLE)
        self.c = {
            "staging_source_bucket": "gs://adi-anvil-mvp-2026-anvil-staging-build-source",
            "project": "adi-anvil-mvp-2026",
            "region": "us-west1",
            "build_identity": "anvil-staging-build@adi-anvil-mvp-2026.iam.gserviceaccount.com",
            "registry": "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-staging-demo",
            "source_sha": "a" * 40,
            "source_archive_sha256": "b" * 64,
            "source_manifest_sha256": native_sha,
            "build_context_sha256": context_sha,
            "upload_inventory_sha256": upload_sha,
            "fresh_context_directory": str(self.context),
            "build_tag": "a" * 12 + "-fixture-only",
            "source_manifest_file": native,
            "context_inventory_file": inventory,
            "context_inventory_receipt_sha256": inventory_sha,
            "upload_inventory_file": upload,
            "upload_inventory_receipt_sha256": upload_receipt_sha,
            "lifecycle_file": lifecycle,
            "lifecycle_sha256": lifecycle_sha,
            "build_config_file": str(self.root / "cloudbuild.json"),
        }
        config = recipe(self.c)["cloudbuild_config_to_review_and_materialize"]
        Path(self.c["build_config_file"]).write_text(
            json.dumps(config, sort_keys=True, indent=2) + "\n"
        )

    def test_exact_backend_web_only_isolated_identity_and_no_execution(self):
        result = recipe(self.c)
        self.assertFalse(result["executed"])
        self.assertFalse(result["build_authorized"])
        config = result["cloudbuild_config_to_review_and_materialize"]
        self.assertEqual([step["id"] for step in config["steps"]], ["backend", "web"])
        self.assertEqual(
            config["serviceAccount"],
            "projects/adi-anvil-mvp-2026/serviceAccounts/" + self.c["build_identity"],
        )
        command = result["prospective_submit_argv"]
        self.assertIn(CLI, command)
        self.assertIn("CLOUDSDK_CONFIG=" + CONFIG, command)
        self.assertIn(
            "--gcs-source-staging-dir=" + self.c["staging_source_bucket"] + "/source", command
        )
        self.assertEqual(len(result["prospective_resource_argv"]), 8)
        self.assertNotIn("enable", json.dumps(result["prospective_resource_argv"]))

    def test_missing_inputs_and_scope_alternatives_fail(self):
        for key in self.c:
            with self.subTest(key=key), self.assertRaises((ValueError, TypeError)):
                recipe({**self.c, key: None})
        for key, value in (
            ("staging_source_bucket", "gs://adi-anvil-mvp-2026_cloudbuild"),
            ("registry", "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil"),
            ("registry", "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-staging"),
            (
                "build_identity",
                "anvil-staging-demo-build@adi-anvil-mvp-2026.iam.gserviceaccount.com",
            ),
            ("build_identity", "anvil-vm@adi-anvil-mvp-2026.iam.gserviceaccount.com"),
        ):
            with self.assertRaises(ValueError):
                recipe({**self.c, key: value})

    def test_exact_seven_day_policy_even_if_changed_hash_matches(self):
        path = Path(self.c["lifecycle_file"])
        for policy in (
            {"rule": []},
            {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 8}}]},
            {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 7, "isLive": True}}]},
        ):
            path.write_text(json.dumps(policy))
            with self.assertRaises(ValueError):
                recipe(
                    {**self.c, "lifecycle_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                )

    def test_context_inventory_conflation_and_config_drift_fail(self):
        with self.assertRaises(ValueError):
            recipe({**self.c, "upload_inventory_sha256": self.c["build_context_sha256"]})
        Path(self.c["build_config_file"]).write_text("{}")
        with self.assertRaises(ValueError):
            recipe(self.c)
        (self.context / "source.py").write_text("changed")
        with self.assertRaises(ValueError):
            recipe(self.c)

    def test_receipt_keeps_post_upload_facts_absent(self):
        receipt = recipe(self.c)["proposed_receipt"]
        self.assertNotEqual(
            receipt["upload_inventory_sha256"], receipt["unfiltered_context_inventory_sha256"]
        )
        self.assertEqual(
            receipt["build_config_sha256"],
            hashlib.sha256(Path(self.c["build_config_file"]).read_bytes()).hexdigest(),
        )
        for key in (
            "uploaded_package_sha256",
            "gcs_object",
            "gcs_generation",
            "cloud_build_id",
            "output_digests",
            "sourceProvenance",
        ):
            self.assertIsNone(receipt[key])

    def test_missing_materialized_config_emits_no_mutation_or_submission_argv(self):
        Path(self.c["build_config_file"]).unlink()
        result = recipe(self.c)
        self.assertIsNone(result["prospective_resource_argv"])
        self.assertIsNone(result["prospective_submit_argv"])

    def test_cli_is_print_only(self):
        output = io.StringIO()
        with (
            patch("sys.argv", ["build", "--contract", "fixture.json"]),
            patch.object(Path, "read_text", return_value=json.dumps(self.c)),
            patch("subprocess.run", side_effect=AssertionError("execution forbidden")),
            redirect_stdout(output),
        ):
            self.assertEqual(main(), 0)
        self.assertFalse(json.loads(output.getvalue())["build_authorized"])


if __name__ == "__main__":
    unittest.main()
