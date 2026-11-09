"""Preparation-only argv, rejection and redaction checks; no cloud or execution."""

import hashlib
import io
import json
import os
import socket
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from staging_benchmark_operator import (
    MIN_BOOT_FREE_BYTES,
    OFF,
    REQUIRED_SOURCE,
    _source_path,
    boot_space_guard,
    exclusive_native_guard,
    prepare,
    run_guarded_one_shot,
)


class OperatorPreparation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp", prefix="anvil-op-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.vault.mkdir(mode=0o700)
        locks = {}
        for relative in ("services/backend/uv.lock", "services/harbor/requirements.lock"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fictional locked dependency test\n")
            locks[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        inventory = locks.copy()
        for relative in REQUIRED_SOURCE:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# original fictional preparation fixture\n")
            inventory[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.manifest = self.root / "source-manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "scope": "Original fictional preparation fixture",
                    "git_head": "a" * 40,
                    "files": inventory,
                }
            )
        )
        self.contract = {
            "operation": "offlineworker",
            "project": str(uuid4()),
            "operator": str(uuid4()),
            "target": str(uuid4()),
            "max_trials": 18,
            "source_sha": "a" * 40,
            "checkout": str(self.root),
            "vault_root": str(self.vault),
            "source_manifest": str(self.manifest),
            "source_manifest_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            "lock_sha256": locks,
            "evaluator_login_role": "anvil_staging_benchmark_evaluator_login",
        }
        self.env = {
            "DATABASE_URL": "postgresql://anvil_app:TOP_SECRET_APP@127.0.0.1/test_only",
            "ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL": "postgresql://anvil_staging_benchmark_evaluator_login:TOP_SECRET_EVAL@127.0.0.1/test_only?options=-c%20role%3Danvil_benchmark_evaluator",
        }

    def test_only_printable_argv_no_execution_or_secret_values(self):
        with (
            patch("subprocess.run", side_effect=AssertionError("execution forbidden")),
            patch("socket.create_connection", side_effect=AssertionError("network forbidden")),
        ):
            recipe = prepare(self.contract, self.env)
        output = json.dumps(recipe)
        self.assertNotIn("TOP_SECRET", output)
        self.assertNotIn("postgresql://", output)
        self.assertFalse(recipe["execution_supported"])
        self.assertEqual(recipe["default_environment"], OFF)
        self.assertEqual(recipe["argv"][-2:], ["--max-trials", "18"])
        self.assertIn("exact_dedicated_native_daemon_socket_required", recipe["blockers"])
        self.assertTrue(recipe["unverified_human_and_runtime_gates"])

    def test_real_temporary_lock_is_exclusive_and_inode_is_never_unlinked(self):
        parent = self.root / ".local"
        parent.mkdir(mode=0o700)
        with (
            patch("staging_benchmark_operator.OPERATOR_ROOT", self.root),
            patch("staging_benchmark_operator.boot_space_guard"),
        ):
            with exclusive_native_guard(str(self.root)):
                inode = (parent / "staging-native.lock").stat().st_ino
                with self.assertRaises(BlockingIOError):
                    with exclusive_native_guard(str(self.root)):
                        self.fail("concurrent admission")
            self.assertTrue((parent / "staging-native.lock").is_file())
            with exclusive_native_guard(str(self.root)):
                self.assertEqual((parent / "staging-native.lock").stat().st_ino, inode)

    def test_boot_guard_requires_reviewed_root_device_and_ten_gib_free(self):
        for free in (MIN_BOOT_FREE_BYTES - 1, MIN_BOOT_FREE_BYTES):
            with (
                patch.object(Path, "stat", return_value=SimpleNamespace(st_dev=11)),
                patch("shutil.disk_usage", return_value=SimpleNamespace(free=free)),
            ):
                if free < MIN_BOOT_FREE_BYTES:
                    with self.assertRaises(RuntimeError):
                        boot_space_guard(self.root)
                else:
                    boot_space_guard(self.root)
        with (
            patch.object(
                Path, "stat", side_effect=[SimpleNamespace(st_dev=11), SimpleNamespace(st_dev=22)]
            ),
            self.assertRaises(RuntimeError),
        ):
            boot_space_guard(self.root)

    def test_lock_denies_unowned_modes_aliases_and_unknown_marker(self):
        parent = self.root / ".local"
        parent.mkdir(mode=0o700)
        lock = parent / "staging-native.lock"
        with (
            patch("staging_benchmark_operator.OPERATOR_ROOT", self.root),
            patch("staging_benchmark_operator.boot_space_guard"),
        ):
            parent.chmod(0o755)
            with self.assertRaises(ValueError):
                with exclusive_native_guard(str(self.root)):
                    self.fail("public parent")
            parent.chmod(0o700)
            target = self.root / "private-canary"
            target.write_text("unchanged")
            lock.symlink_to(target)
            with self.assertRaises(OSError):
                with exclusive_native_guard(str(self.root)):
                    self.fail("symlink lock")
            self.assertEqual(target.read_text(), "unchanged")
            lock.unlink()
            lock.write_bytes(b"1")
            lock.chmod(0o600)
            with self.assertRaises(RuntimeError):
                with exclusive_native_guard(str(self.root)):
                    self.fail("unknown admission")

    def guarded_fixture(self):
        (self.root / ".local").mkdir(mode=0o700)
        argv = [
            str(self.root / ".local/backend-venv/bin/python"),
            "-m",
            "anvil.benchmark_offline_worker",
            "--project",
            self.contract["project"],
            "--run",
            self.contract["target"],
            "--operator",
            self.contract["operator"],
            "--max-trials",
            "1",
        ]
        env = {
            **OFF,
            **{key: value.replace("/test_only", "/anvil") for key, value in self.env.items()},
            "ANVIL_ROOT": str(self.root),
            "ANVIL_TEST_HARBOR": "1",
            "ANVIL_BENCHMARK_OFFLINE_ENABLED": "true",
            "ANVIL_HARBOR_DOCKER_HOST": "unix://"
            + str(self.root / ".local/benchmark-docker/docker.sock"),
            "ARTIFACT_ROOT": str(self.root / ".data/artifacts"),
            "ANVIL_BENCHMARK_VAULT_ROOT": str(self.root / ".local/benchmark-vault"),
        }
        return argv, env

    def test_guarded_dispatch_is_fixed_one_shot_and_low_space_never_starts(self):
        argv, env = self.guarded_fixture()

        def dispatch_receipt(*args, **kwargs):
            self.assertEqual((self.root / ".local/staging-native.lock").read_bytes(), b"1")
            self.assertEqual(os.fstat(kwargs["stdout"].fileno()).st_mode & 0o777, 0o600)
            self.assertEqual(os.fstat(kwargs["stderr"].fileno()).st_mode & 0o777, 0o600)
            kwargs["stdout"].write(b'{"statuses":["completed"],"paid_calls":false}')
            kwargs["stderr"].write(b"PRIVATE-DIAGNOSTIC-NEVER-RETURN")
            return SimpleNamespace(returncode=0)

        with (
            patch("staging_benchmark_operator.OPERATOR_ROOT", self.root),
            patch(
                "staging_benchmark_operator.boot_space_guard", side_effect=RuntimeError("low space")
            ),
            patch("subprocess.run") as dispatch,
        ):
            with self.assertRaises(RuntimeError):
                run_guarded_one_shot(argv, env)
            dispatch.assert_not_called()
        with (
            patch("staging_benchmark_operator.OPERATOR_ROOT", self.root),
            patch("staging_benchmark_operator.boot_space_guard"),
            patch("subprocess.run", side_effect=dispatch_receipt) as dispatch,
        ):
            status = run_guarded_one_shot(argv, env)
            self.assertFalse(status["paid_calls"])
            self.assertNotIn("PRIVATE-DIAGNOSTIC", repr(status))
            self.assertEqual(dispatch.call_args.args, (argv,))
            self.assertNotIn("shell", dispatch.call_args.kwargs)
            self.assertEqual(dispatch.call_args.kwargs["timeout"], 3600)
            self.assertEqual((self.root / ".local/staging-native.lock").read_bytes(), b"0")
            for invalid in (
                ["/bin/sh", "-c", "true"],
                [*argv[:-1], "18"],
                [*argv[:2], "unapproved.module", *argv[3:]],
            ):
                with self.assertRaises(ValueError):
                    run_guarded_one_shot(invalid, env)
            with self.assertRaises(ValueError):
                run_guarded_one_shot(argv, {**env, "PYTHONPATH": "/untrusted"})

    def test_timeout_is_unknown_and_persistent_marker_blocks_subsequent_dispatch(self):
        argv, env = self.guarded_fixture()
        with (
            patch("staging_benchmark_operator.OPERATOR_ROOT", self.root),
            patch("staging_benchmark_operator.boot_space_guard"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(argv, 3600)) as dispatch,
        ):
            with self.assertRaisesRegex(RuntimeError, "descendants are not assumed stopped"):
                run_guarded_one_shot(argv, env)
            self.assertEqual((self.root / ".local/staging-native.lock").read_bytes(), b"1")
            with self.assertRaises(RuntimeError):
                run_guarded_one_shot(argv, env)
            self.assertEqual(dispatch.call_count, 1)

    def test_qualification_failed_receipt_even_exit_zero_does_not_reopen_admission(self):
        argv, env = self.guarded_fixture()
        argv = [
            *argv[:2],
            "anvil.benchmark_pipeline_worker",
            "--project",
            self.contract["project"],
            "--operation",
            self.contract["target"],
            "--admin",
            self.contract["operator"],
        ]

        def failed_receipt(*args, **kwargs):
            kwargs["stdout"].write(b"failed\n")
            return SimpleNamespace(returncode=0)

        with (
            patch("staging_benchmark_operator.OPERATOR_ROOT", self.root),
            patch("staging_benchmark_operator.boot_space_guard"),
            patch("subprocess.run", side_effect=failed_receipt) as dispatch,
        ):
            with self.assertRaisesRegex(RuntimeError, "known terminal receipt"):
                run_guarded_one_shot(argv, env)
            self.assertEqual((self.root / ".local/staging-native.lock").read_bytes(), b"1")
            with self.assertRaises(RuntimeError):
                run_guarded_one_shot(argv, env)
            self.assertEqual(dispatch.call_count, 1)

    def test_qualification_argv_has_no_trial_or_shell_switches(self):
        self.contract.update(operation="qualification", max_trials=1)
        recipe = prepare(self.contract, self.env)
        self.assertEqual(recipe["argv"][1:3], ["-m", "anvil.benchmark_pipeline_worker"])
        self.assertIn("--operation", recipe["argv"])
        self.assertNotIn("--run", recipe["argv"])
        self.assertNotIn("--max-trials", recipe["argv"])

    def test_rejects_arbitrary_command_ids_bounds_and_paths(self):
        cases = [
            ("operation", "bash"),
            ("project", "x; touch /tmp/unwanted"),
            ("target", "not-a-uuid"),
            ("max_trials", 19),
            ("max_trials", True),
            ("source_sha", "main"),
            ("vault_root", "/tmp/../tmp"),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                prepare({**self.contract, key: value}, self.env)

    def test_mismatched_locks_source_and_vault_cannot_prepare(self):
        (self.root / "services/backend/uv.lock").write_text("modified")
        os.chmod(self.vault, 0o755)
        result = prepare(self.contract, self.env)
        self.assertIn("exact_source_manifest_or_runtime_locks_unverified", result["blockers"])
        self.assertIn("fresh_owner_only_private_vault_required", result["blockers"])

    def test_role_separation_and_paid_flags_remain_gated(self):
        env = {
            **self.env,
            "ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL": self.env["DATABASE_URL"],
            "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "true",
        }
        result = prepare(self.contract, env)
        self.assertIn(
            "anvil_benchmark_evaluator_database_url_separate_role_reference_required",
            result["blockers"],
        )
        self.assertIn("paid_generation_and_email_flags_must_remain_off", result["blockers"])

    def test_never_claims_ready_even_with_local_socket(self):
        daemon = self.root / ".local/benchmark-docker/docker.sock"
        daemon.parent.mkdir(parents=True)
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind(str(daemon))
            recipe = prepare(self.contract, self.env)
        self.assertEqual(recipe["status"], "blocked_preparation")
        self.assertIn(
            "actual_evaluator_login_membership_and_current_user_sql_proof_required",
            recipe["blockers"],
        )
        self.assertFalse(recipe["execution_supported"])
        self.assertTrue(recipe["unverified_human_and_runtime_gates"])

    def test_evaluator_nologin_requires_dedicated_login_and_exact_role_option(self):
        original = self.env["ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL"]
        rejected = [
            original.replace("anvil_staging_benchmark_evaluator_login:", role + ":")
            for role in ("anvil_app", "postgres", "anvil_owner", "anvil_benchmark_evaluator")
        ]
        rejected += [
            original.split("?")[0],
            original.replace("role%3Danvil_benchmark_evaluator", "role%3Danvil_app"),
            original + "&options=-c%20role%3Dpostgres",
            original + "&role=postgres",
            original + "&user=postgres",
            original + "%20-c%20role%3Dpostgres",
        ]
        for dsn in rejected:
            with self.subTest(dsn_kind=rejected.index(dsn)):
                result = prepare(
                    self.contract, {**self.env, "ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL": dsn}
                )
                self.assertIn(
                    "anvil_benchmark_evaluator_database_url_separate_role_reference_required",
                    result["blockers"],
                )
                self.assertNotIn("TOP_SECRET", json.dumps(result))
        for role in (None, "anvil_app", "postgres", "anvil_owner", "anvil_benchmark_evaluator"):
            result = prepare({**self.contract, "evaluator_login_role": role}, self.env)
            self.assertIn("reviewed_dedicated_evaluator_login_role_required", result["blockers"])

    def test_same_database_separate_identity_is_required_not_same_dsn(self):
        valid = prepare(self.contract, self.env)
        self.assertNotIn(
            "anvil_benchmark_evaluator_database_url_separate_role_reference_required",
            valid["blockers"],
        )
        self.assertEqual(
            valid["evaluator_sql_contract"]["verify_current_user"], "anvil_benchmark_evaluator"
        )
        self.assertFalse(valid["evaluator_sql_contract"]["sql_proof_recorded"])
        for change in ("test_only?", "other_database?"):
            evaluator = self.env["ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL"].replace(
                "test_only?", change
            )
            result = prepare(
                self.contract, {**self.env, "ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL": evaluator}
            )
            self.assertEqual(
                "anvil_benchmark_evaluator_database_url_separate_role_reference_required"
                in result["blockers"],
                change != "test_only?",
            )
        owner_app = {
            **self.env,
            "DATABASE_URL": self.env["DATABASE_URL"].replace("anvil_app:", "postgres:"),
        }
        self.assertIn(
            "database_url_separate_role_reference_required",
            prepare(self.contract, owner_app)["blockers"],
        )
        alias_only = {key: value for key, value in self.env.items() if key != "DATABASE_URL"}
        alias_only["ANVIL_DATABASE_URL"] = self.env["DATABASE_URL"]
        self.assertIn(
            "database_url_separate_role_reference_required",
            prepare(self.contract, alias_only)["blockers"],
        )

    def test_rejects_symlink_vault_and_incomplete_source_manifest(self):
        link = self.root / "vault-link"
        link.symlink_to(self.vault)
        with self.assertRaises(ValueError):
            prepare({**self.contract, "vault_root": str(link)}, self.env)
        self.manifest.write_text(
            json.dumps(
                {
                    "scope": "Incomplete fixture",
                    "git_head": "a" * 40,
                    "files": self.contract["lock_sha256"],
                }
            )
        )
        self.contract["source_manifest_sha256"] = hashlib.sha256(
            self.manifest.read_bytes()
        ).hexdigest()
        self.assertIn(
            "exact_source_manifest_or_runtime_locks_unverified",
            prepare(self.contract, self.env)["blockers"],
        )

    def test_published_exact_source_manifest_shape_and_current_bytes(self):
        checkout = Path(__file__).resolve().parents[2]
        manifest = (
            checkout
            / "docs/agent-team/runs/anvil-codex-transition-2026-11-08/qa-candidate-source.json"
        )
        inventory = json.loads(manifest.read_text())
        contract = {
            **self.contract,
            "checkout": str(checkout),
            "source_manifest": str(manifest),
            "source_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "source_sha": inventory["git_head"],
            "lock_sha256": {
                relative: inventory["files"][relative] for relative in self.contract["lock_sha256"]
            },
        }
        result = prepare(contract, self.env)
        changed = [
            relative
            for relative, digest in inventory["files"].items()
            if hashlib.sha256((checkout / relative).read_bytes()).hexdigest() != digest
        ]
        self.assertEqual(
            "exact_source_manifest_or_runtime_locks_unverified" in result["blockers"], bool(changed)
        )
        self.assertEqual(result["source_sha"], inventory["git_head"])
        self.assertIn(".node-version", inventory["files"])
        self.assertIn(".python-version", inventory["files"])
        # The published receipt also lists explicitly uncommitted preparation
        # paths. Never rewrite it to conceal drift or call those e4 source.
        archive = subprocess.run(
            ["git", "archive", inventory["git_head"]], cwd=checkout, check=True, capture_output=True
        ).stdout
        extracted = self.root / "exact-source-archive"
        extracted.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            for member in source:
                relative = Path(member.name)
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or member.issym()
                    or member.islnk()
                ):
                    raise AssertionError("unsafe archive member")
                if member.isfile():
                    destination = extracted / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(source.extractfile(member).read())
        missing = [
            relative for relative in inventory["files"] if not (extracted / relative).is_file()
        ]
        self.assertTrue(missing)
        self.assertTrue(set(missing) <= set(inventory["uncommitted_manifest_paths"]))
        contract["checkout"] = str(extracted)
        self.assertIn(
            "exact_source_manifest_or_runtime_locks_unverified",
            prepare(contract, self.env)["blockers"],
        )
        derived_path = manifest.with_name("operator-e4bb2d5-source.json")
        derived = json.loads(derived_path.read_text())
        self.assertEqual(
            derived["provenance"]["source_manifest_sha256"],
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            set(derived["provenance"]["omitted_paths"]),
            set(inventory["uncommitted_manifest_paths"]),
        )
        self.assertEqual(
            derived["files"],
            {
                path: value
                for path, value in inventory["files"].items()
                if path not in inventory["uncommitted_manifest_paths"]
            },
        )
        contract.update(
            source_manifest=str(derived_path),
            source_manifest_sha256=hashlib.sha256(derived_path.read_bytes()).hexdigest(),
        )
        self.assertNotIn(
            "exact_source_manifest_or_runtime_locks_unverified",
            prepare(contract, self.env)["blockers"],
        )

    def test_allow_reviewed_tracked_dotfiles_but_reject_secret_and_generated_paths(self):
        for path in [
            ".node-version",
            ".python-version",
            ".github/workflows/verify.yml",
            "services/backend/src/anvil/config.py",
        ]:
            self.assertEqual(str(_source_path(path)), path)
        for path in [
            ".git/config",
            ".local/private",
            ".env",
            "config/.env.staging",
            ".aws/credentials",
            ".ssh/id_rsa",
            ".github/secrets.yml",
            "secrets/provider.json",
            "config/private.key",
            "node_modules/package/index.js",
            "../outside",
            "./.python-version",
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                _source_path(path)


if __name__ == "__main__":
    unittest.main()
