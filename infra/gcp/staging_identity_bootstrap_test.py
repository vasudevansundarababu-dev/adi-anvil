"""Offline validation only; fictional field values are not invited identities."""

import copy
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from staging_identity_bootstrap import (
    DEPLOYMENT_IDENTITY,
    GceTargetObserver,
    apply,
    digest,
    main,
    metadata_get,
    root_deployment_identity,
    validate,
    validate_approval,
    validate_dsn,
)


class BootstrapPreparation(unittest.TestCase):
    def setUp(self):
        self.contract = {
            "schema": "anvil.staging.initial-admin.v1",
            "target": {
                "database": "anvil",
                "host": "127.0.0.1",
                "port": 5432,
                "migration_role": "anvil_staging_migration",
                "gcp_project": "adi-anvil-mvp-2026",
                "vm_name": "anvil-staging-demo",
                "vm_id": "123456789",
                "new_disk_manifest_sha256": "d" * 64,
                "postgres_system_identifier": "987654321",
            },
            "identity": {
                "user_id": str(uuid4()),
                "issuer": "https://auth-stage.example.test/realms/anvil-staging-demo",
                "subject": str(uuid4()),
                "name": "Original Fictional Validation Fixture",
                "origin": "real_invited_oidc_identity",
            },
            "organization": {"id": str(uuid4()), "name": "Original Fictional Contract Test"},
            "project": {"id": str(uuid4()), "name": "Anvil Staging Validation Only"},
            "reviewed_invitation_sha256": "a" * 64,
        }

    def test_explicit_contract_has_bound_digest_without_approving_identity(self):
        self.assertEqual(len(validate(self.contract)), 64)
        changed = copy.deepcopy(self.contract)
        changed["identity"]["subject"] = str(uuid4())
        self.assertNotEqual(validate(changed), validate(self.contract))

    def test_actual_config_generator_contract_is_compatible_but_unobserved_target_stays_blocked(
        self,
    ):
        from staging_demo_config import generate
        from staging_demo_config_test import fixture

        # The generator's existing explicitly fictional fixture is not an account
        # invitation, deployment approval or observed resource/cluster identity.
        configuration, secret_fixtures = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / "private-config"
            status = generate(configuration, secret_fixtures, output)
            contract = json.loads((output / "identity-bootstrap-contract.json").read_text())
            self.assertFalse(status["deployment_authorized"])
            self.assertEqual(contract["schema"], "anvil.staging.initial-admin.v1")
            self.assertEqual(contract["identity"]["origin"], "real_invited_oidc_identity")
            self.assertEqual(set(contract), set(self.contract))
            self.assertEqual(set(contract["identity"]), set(self.contract["identity"]))
            for field in ("vm_id", "new_disk_manifest_sha256", "postgres_system_identifier"):
                self.assertIsNone(contract["target"][field])
            with self.assertRaises((ValueError, TypeError)):
                validate(contract)
            manufactured_observation = copy.deepcopy(contract)
            for field in ("vm_id", "new_disk_manifest_sha256", "postgres_system_identifier"):
                manufactured_observation["target"][field] = self.contract["target"][field]
            self.assertEqual(len(validate(manufactured_observation)), 64)
            self.assertIsNone(
                json.loads((output / "identity-bootstrap-contract.json").read_text())["target"][
                    "vm_id"
                ]
            )
            realm = json.loads((output / "realm.json").read_text())
            self.assertFalse(realm["users"][0]["enabled"])
            self.assertEqual(realm["users"][0]["id"], contract["identity"]["subject"])

    def test_current_production_aliases_roles_and_synthetic_origins_rejected(self):
        for database in (
            "anvil_local",
            "praxis",
            "anvil_staging",
            "anvil_staging_demo;drop",
            "anvil_staging_demoprod",
        ):
            changed = copy.deepcopy(self.contract)
            changed["target"]["database"] = database
            with self.subTest(database=database), self.assertRaises(ValueError):
                validate(changed)
        for key, value in (
            ("vm_name", "anvil-linux-qa"),
            ("vm_name", "anvil-mvp-v1"),
            ("vm_id", None),
            ("host", "production.example.test"),
            ("port", 55482),
            ("new_disk_manifest_sha256", None),
        ):
            changed = copy.deepcopy(self.contract)
            changed["target"][key] = value
            with self.subTest(key=key), self.assertRaises((ValueError, TypeError)):
                validate(changed)
        for role in ("postgres", "anvil_app", "anvil_worker", "anvil_benchmark_evaluator"):
            changed = copy.deepcopy(self.contract)
            changed["target"]["migration_role"] = role
            with self.assertRaises(ValueError):
                validate(changed)
        changed = copy.deepcopy(self.contract)
        changed["identity"]["origin"] = "synthetic_fixture"
        with self.assertRaises(ValueError):
            validate(changed)
        changed = copy.deepcopy(self.contract)
        changed["identity"]["role"] = "admin"
        with self.assertRaises(ValueError):
            validate(changed)

    def test_identity_and_schema_aliases_cannot_supply_seed_payloads(self):
        for issuer in (
            "http://localhost/realms/anvil-staging-demo",
            "https://auth-stage.example.test/realms/anvil",
            "https://user:password@auth-stage.example.test/realms/anvil-staging-demo",
        ):
            changed = copy.deepcopy(self.contract)
            changed["identity"]["issuer"] = issuer
            with self.assertRaises(ValueError):
                validate(changed)
        for field in (
            "reviews",
            "assignments",
            "completed_runs",
            "rights_grants",
            "evaluator_login",
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate({**self.contract, field: []})

    def test_exact_separate_deployment_approval_and_expiry_required(self):
        now = datetime.now(timezone.utc)
        approval = {
            "action": "execute_initial_staging_admin_bootstrap",
            "contract_sha256": validate(self.contract),
            "approval_record_sha256": "b" * 64,
            "expires_at": (now + timedelta(hours=1)).isoformat(),
        }
        validate_approval(approval, validate(self.contract), now)
        for change in (
            {"action": "approve_linux_test_host"},
            {"contract_sha256": "c" * 64},
            {"expires_at": (now - timedelta(seconds=1)).isoformat()},
            {"expires_at": (now + timedelta(days=2)).isoformat()},
        ):
            with self.assertRaises(ValueError):
                validate_approval({**approval, **change}, validate(self.contract), now)

    def test_dsn_is_exact_target_not_alias_or_owner_options(self):
        dsn = "postgresql://anvil_staging_migration:TEST_SECRET_ONLY@127.0.0.1:5432/anvil?connect_timeout=5"
        validate_dsn(dsn, self.contract["target"])
        for changed in (
            dsn.replace("anvil_staging_migration:", "postgres:"),
            dsn.replace("127.0.0.1", "production.example.test"),
            dsn.replace("/anvil?", "/praxis?"),
            dsn + "&options=-c%20role%3Dpostgres",
            dsn + "&connect_timeout=1",
        ):
            with self.assertRaises(ValueError):
                validate_dsn(changed, self.contract["target"])

    def test_default_dry_run_never_connects_executes_or_prints_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "reviewed-nonsecret-contract.json"
            path.write_text(json.dumps(self.contract))
            output = io.StringIO()
            with (
                patch("sys.argv", ["bootstrap", "--contract", str(path)]),
                patch(
                    "psycopg.connect", side_effect=AssertionError("SQL forbidden during dry-run")
                ),
                patch("subprocess.run", side_effect=AssertionError("execution forbidden")),
                redirect_stdout(output),
            ):
                self.assertEqual(main(), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "dry_run_no_connection_or_changes")
            self.assertNotIn(self.contract["identity"]["subject"], output.getvalue())
            self.assertNotIn(self.contract["identity"]["name"], output.getvalue())
            output = io.StringIO()
            with (
                patch("sys.argv", ["bootstrap", "--contract", str(path), "--execute"]),
                patch("psycopg.connect", side_effect=AssertionError("approval missing")),
                redirect_stdout(output),
            ):
                self.assertEqual(main(), 2)
            self.assertEqual(json.loads(output.getvalue())["status"], "bootstrap_blocked")

    def test_caller_flags_are_not_trusted_target_metadata(self):
        approval = {
            "action": "execute_initial_staging_admin_bootstrap",
            "contract_sha256": validate(self.contract),
            "approval_record_sha256": "b" * 64,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        connection = SimpleNamespace()
        for observer in (
            True,
            False,
            {"trusted": True},
            SimpleNamespace(verify=lambda target, conn: True),
            SimpleNamespace(
                verify=lambda target, conn: {
                    "target_identity_sha256": "0" * 64,
                    "postgres_system_identifier": "987654321",
                    "observation_receipt_sha256": "e" * 64,
                }
            ),
        ):
            with (
                self.subTest(observer_type=type(observer).__name__),
                self.assertRaises(RuntimeError),
            ):
                apply(connection, self.contract, approval, trusted_target_observer=observer)

    def test_explicit_cli_executes_only_after_live_observer_preflight_mocked(self):
        # Unit wiring only: neither this observer nor this connection is real.
        approval = {
            "action": "execute_initial_staging_admin_bootstrap",
            "contract_sha256": validate(self.contract),
            "approval_record_sha256": "b" * 64,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            contract_path, approval_path = (
                Path(temporary) / "contract.json",
                Path(temporary) / "approval.json",
            )
            contract_path.write_text(json.dumps(self.contract))
            approval_path.write_text(json.dumps(approval))
            argv = [
                "bootstrap",
                "--contract",
                str(contract_path),
                "--execute",
                "--deployment-approval",
                str(approval_path),
            ]
            dsn = "postgresql://anvil_staging_migration:TEST_SECRET_ONLY@127.0.0.1:5432/anvil"
            for blocked in (False, True):
                observer = Mock()
                if blocked:
                    observer.preflight.side_effect = RuntimeError("wrong VM")
                result = io.StringIO()
                with (
                    patch("sys.argv", argv),
                    patch.dict(os.environ, {"MIGRATION_DATABASE_URL": dsn}),
                    patch("staging_identity_bootstrap.GceTargetObserver", return_value=observer),
                    patch("psycopg.connect") as connect,
                    patch(
                        "staging_identity_bootstrap.apply",
                        return_value={"status": "manufactured_sql_wiring_only"},
                    ) as applied,
                    redirect_stdout(result),
                ):
                    self.assertEqual(main(), 2 if blocked else 0)
                observer.preflight.assert_called_once_with(self.contract["target"])
                self.assertNotIn("TEST_SECRET_ONLY", result.getvalue())
                if blocked:
                    connect.assert_not_called()
                    applied.assert_not_called()
                else:
                    self.assertEqual(connect.call_args.args, (dsn,))
                    self.assertEqual(connect.call_args.kwargs["connect_timeout"], 5)
                    self.assertIs(applied.call_args.kwargs["trusted_target_observer"], observer)

    def test_fixed_metadata_transport_separates_trusted_headers_and_bounds(self):
        for path in (
            "instance/service-accounts/default/token",
            "instance/attributes/secret",
            "http://outside",
            "instance/disks/16/device-name",
        ):
            with (
                patch(
                    "http.client.HTTPConnection",
                    side_effect=AssertionError("must reject before HTTP"),
                ),
                self.assertRaises(ValueError),
            ):
                metadata_get(path)
        for status, flavor, data, valid in (
            (200, "Google", b"adi-anvil-mvp-2026", True),
            (302, "Google", b"redirect", False),
            (200, None, b"untrusted", False),
            (200, "Google", b"x" * 4097, False),
        ):
            response = Mock(status=status)
            response.getheader.return_value = flavor
            response.read.return_value = data
            connection = Mock()
            connection.getresponse.return_value = response
            with patch("http.client.HTTPConnection", return_value=connection) as factory:
                if valid:
                    self.assertEqual(metadata_get("project/project-id"), "adi-anvil-mvp-2026")
                else:
                    with self.assertRaises((RuntimeError, ValueError)):
                        metadata_get("project/project-id")
            factory.assert_called_once_with("169.254.169.254", 80, timeout=2)
            connection.request.assert_called_once_with(
                "GET",
                "/computeMetadata/v1/project/project-id",
                headers={"Metadata-Flavor": "Google"},
            )
            connection.close.assert_called_once()
            if status == 200 and flavor == "Google":
                response.read.assert_called_once_with(4097)

    def test_fake_metadata_fixture_binds_exact_vm_disk_and_actual_cluster_query(self):
        # Manufactured observer inputs test rejection contracts, NOT GCP proof.
        target = self.contract["target"]
        identity = {
            "schema": "anvil.staging.deployment-identity.v1",
            "gcp_project": target["gcp_project"],
            "vm_name": target["vm_name"],
            "vm_id": target["vm_id"],
            "postgres_system_identifier": target["postgres_system_identifier"],
            "creation_manifest_sha256": "e" * 64,
            "disks": [{"device_name": "anvil-staging-demo-data", "disk_id": "13579"}],
        }
        values = {
            "project/project-id": target["gcp_project"],
            "instance/name": target["vm_name"],
            "instance/id": target["vm_id"],
            "instance/disks/": "0/",
            "instance/disks/0/device-name": "anvil-staging-demo-data",
        }
        actual = {
            "db": "anvil",
            "role": "anvil_staging_migration",
            "session_role": "anvil_staging_migration",
            "cluster_id": target["postgres_system_identifier"],
        }
        connection = Mock(info=SimpleNamespace(host="127.0.0.1", port=5432))
        connection.execute.return_value.fetchone.return_value = actual
        with patch(
            "staging_identity_bootstrap.root_deployment_identity",
            return_value=(identity, target["new_disk_manifest_sha256"]),
        ):
            observer = GceTargetObserver(getter=lambda path: values[path])
            receipt = observer.verify(target, connection)
            self.assertEqual(receipt["target_identity_sha256"], digest(target))
            for key, wrong in (
                ("instance/name", "anvil-mvp-v1"),
                ("instance/name", "anvil-linux-qa"),
                ("project/project-id", "other-project"),
                ("instance/id", "999"),
                ("instance/disks/0/device-name", "existing-production-disk"),
            ):
                changed = {**values, key: wrong}
                with self.subTest(key=key), self.assertRaises((ValueError, RuntimeError)):
                    GceTargetObserver(getter=lambda path: changed[path]).verify(target, connection)
            connection.execute.return_value.fetchone.return_value = {**actual, "cluster_id": "999"}
            with self.assertRaises(RuntimeError):
                observer.verify(target, connection)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                root_deployment_identity(Path(temporary) / "caller-controlled.json")

    def test_root_file_custody_contract_with_explicit_manufactured_stat_metadata(self):
        # Manufactured stat records test custody guards; not an actual root file.
        class ManufacturedStream(io.BytesIO):
            def fileno(self):
                return 99

        raw = b'{"fixture":"not a deployment identity"}'
        directory = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        parent = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=0)
        file = {"st_mode": stat.S_IFREG | 0o600, "st_uid": 0, "st_nlink": 1, "st_size": len(raw)}
        for changed, valid in (
            ({}, True),
            ({"st_mode": stat.S_IFREG | 0o644}, False),
            ({"st_uid": 10001}, False),
            ({"st_nlink": 2}, False),
            ({"st_mode": stat.S_IFIFO | 0o600}, False),
        ):
            with (
                patch.object(Path, "lstat", return_value=directory),
                patch.object(Path, "stat", return_value=parent),
                patch("os.open", return_value=99) as opened,
                patch("os.fdopen", return_value=ManufacturedStream(raw)),
                patch("os.fstat", return_value=SimpleNamespace(**{**file, **changed})),
            ):
                if valid:
                    value, hash_ = root_deployment_identity(DEPLOYMENT_IDENTITY)
                    self.assertEqual(value, {"fixture": "not a deployment identity"})
                    self.assertEqual(len(hash_), 64)
                else:
                    with self.assertRaises(ValueError):
                        root_deployment_identity(DEPLOYMENT_IDENTITY)
                self.assertTrue(opened.call_args.args[1] & os.O_NOFOLLOW)
        for unsafe in (
            SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=0),
            SimpleNamespace(st_mode=stat.S_IFDIR | 0o777, st_uid=0),
            SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=10001),
        ):
            with (
                patch.object(Path, "lstat", return_value=unsafe),
                patch(
                    "os.open", side_effect=AssertionError("unsafe ancestor must block before read")
                ),
                self.assertRaises(ValueError),
            ):
                root_deployment_identity(DEPLOYMENT_IDENTITY)


if __name__ == "__main__":
    unittest.main()
