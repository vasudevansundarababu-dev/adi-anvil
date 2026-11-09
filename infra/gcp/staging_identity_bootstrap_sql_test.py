"""Opt-in real SQL contract tests, never GCE/OIDC identity proof.

Only a newly owned disposable cluster on loopback5432 is permitted. The observer
is explicitly manufactured; real PostgreSQL identity/roles/transactions are not.
No real user, external account, deployment approval or metadata call is created.
"""

import copy
import hashlib
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import staging_identity_bootstrap as bootstrap

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = os.environ.get("ANVIL_BOOTSTRAP_SQL_TEST_ENV")
EXPECTED_HELPER_SHA = "c4d66a2a51d8bfee6c1b29ebdae0a43a8857239b7555ff211979cf9d5dc17369"


class ManufacturedObserver:
    """SQL fixture only: not an actual GCP VM, disk or invited identity receipt."""

    def __init__(self, system_identifier, barrier=None):
        self.system_identifier = system_identifier
        self.barrier = barrier

    def verify(self, target, connection):
        if self.barrier:
            self.barrier.wait(timeout=10)
        return {
            "target_identity_sha256": bootstrap.digest(target),
            "postgres_system_identifier": self.system_identifier,
            "observation_receipt_sha256": hashlib.sha256(
                b"manufactured SQL transaction fixture; NOT actual GCE identity proof"
            ).hexdigest(),
        }


@unittest.skipUnless(ENV_FILE, "Explicit newly owned bootstrap SQL cluster required")
class ActualBootstrapSql(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Default offline guards do not require optional backend SQL packages.
        global psycopg, command, Config, sql, dict_row
        import psycopg
        from alembic import command
        from alembic.config import Config
        from psycopg import sql
        from psycopg.rows import dict_row

        cls.environment = json.loads(Path(ENV_FILE).read_text())
        if cls.environment.get("purpose") != "isolated_bootstrap_SQL_fixture_NOT_GCE_proof":
            raise RuntimeError("Explicit fixture purpose required")
        cls.dsn = cls.environment["owner_dsn"]
        parsed = urlsplit(cls.dsn)
        if (
            parsed.hostname != "127.0.0.1"
            or parsed.port != 5432
            or parsed.username != "anvil_staging_migration"
            or parsed.path != "/anvil"
        ):
            raise RuntimeError("Only canonical isolated test endpoint is allowed")
        if hashlib.sha256(Path(bootstrap.__file__).read_bytes()).hexdigest() != EXPECTED_HELPER_SHA:
            raise RuntimeError("Bootstrap helper changed; coordinate a new frozen test window")
        cls.admin_dsn = urlunsplit(
            (parsed.scheme, parsed.netloc, "/postgres", parsed.query, parsed.fragment)
        )

    def connect(self, dsn=None):
        return psycopg.connect(dsn or self.dsn, autocommit=True, row_factory=dict_row)

    def setUp(self):
        # This role reset/database recreation is confined to our separate cluster.
        # It must never use the normal browser/native/Coding cluster.
        with self.connect(self.admin_dsn) as c:
            self.assertEqual(
                c.execute("SELECT current_user u").fetchone()["u"], bootstrap.MIGRATION_ROLE
            )
            for role in ("anvil_app", "anvil_worker"):
                if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                    c.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
                c.execute(
                    sql.SQL(
                        "ALTER ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB "
                        "NOCREATEROLE NOREPLICATION"
                    ).format(sql.Identifier(role))
                )
                c.execute(
                    sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(self.environment[role + "_password"])
                    )
                )
                c.execute(
                    sql.SQL("REVOKE anvil_staging_migration FROM {}").format(sql.Identifier(role))
                )
            if c.execute(
                "SELECT 1 FROM pg_roles WHERE rolname='anvil_benchmark_evaluator'"
            ).fetchone():
                c.execute(
                    "ALTER ROLE anvil_benchmark_evaluator NOLOGIN NOSUPERUSER NOBYPASSRLS "
                    "NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT"
                )
            c.execute("DROP ROLE IF EXISTS bootstrap_test_wrapper")
            c.execute("DROP DATABASE IF EXISTS anvil WITH (FORCE)")
            c.execute("CREATE DATABASE anvil OWNER anvil_staging_migration TEMPLATE template0")
        with self.connect() as c:
            c.execute("CREATE SCHEMA anvil AUTHORIZATION anvil_staging_migration")
        old = os.environ.get("MIGRATION_DATABASE_URL")
        os.environ["MIGRATION_DATABASE_URL"] = self.dsn
        try:
            command.upgrade(Config(str(ROOT / "services/backend/alembic.ini")), "head")
        finally:
            if old is None:
                os.environ.pop("MIGRATION_DATABASE_URL", None)
            else:
                os.environ["MIGRATION_DATABASE_URL"] = old
        with self.connect() as c:
            self.system_id = c.execute(
                "SELECT system_identifier::text id FROM pg_control_system()"
            ).fetchone()["id"]
        self.observer = ManufacturedObserver(self.system_id)
        self.contract = {
            "schema": "anvil.staging.initial-admin.v1",
            "target": {
                "database": "anvil",
                "host": "127.0.0.1",
                "port": 5432,
                "migration_role": bootstrap.MIGRATION_ROLE,
                "gcp_project": "adi-anvil-mvp-2026",
                "vm_name": "anvil-staging-demo",
                "vm_id": "123456789",
                "new_disk_manifest_sha256": "d" * 64,
                "postgres_system_identifier": self.system_id,
            },
            "identity": {
                "user_id": str(uuid4()),
                "issuer": "https://sql-fixture.example.test/realms/anvil-staging-demo",
                "subject": str(uuid4()),
                "name": "Fictional isolated SQL identity contract",
                "origin": "real_invited_oidc_identity",
            },
            "organization": {"id": str(uuid4()), "name": "Fictional SQL contract organization"},
            "project": {"id": str(uuid4()), "name": "Fictional SQL contract project"},
            "reviewed_invitation_sha256": "a" * 64,
        }

    def approval(self, contract=None):
        return {
            "action": "execute_initial_staging_admin_bootstrap",
            "contract_sha256": bootstrap.digest(contract or self.contract),
            "approval_record_sha256": "b" * 64,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }

    def run_bootstrap(self, connection=None, contract=None, observer=None):
        contract = contract or self.contract
        if connection is not None:
            return bootstrap.apply(
                connection,
                contract,
                self.approval(contract),
                trusted_target_observer=observer or self.observer,
            )
        with self.connect() as c:
            return self.run_bootstrap(c, contract, observer)

    def counts(self):
        with self.connect() as c:
            return {
                row["tablename"]: c.execute(
                    sql.SQL("SELECT count(*) n FROM anvil.{}").format(
                        sql.Identifier(row["tablename"])
                    )
                ).fetchone()["n"]
                for row in c.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname='anvil' "
                    "AND tablename NOT IN ('schema_versions','alembic_version')"
                ).fetchall()
            }

    def assert_empty(self):
        self.assertFalse(any(self.counts().values()))

    def test_only_five_intended_rows_and_hash_bound_audit(self):
        result = self.run_bootstrap()
        self.assertEqual(result["status"], "initial_real_admin_created")
        counts = self.counts()
        self.assertEqual(
            {name: n for name, n in counts.items() if n},
            {"organizations": 1, "users": 1, "projects": 1, "memberships": 1, "audit_events": 1},
        )
        with self.connect() as c:
            audit = c.execute("SELECT action,metadata FROM anvil.audit_events").fetchone()
            self.assertEqual(audit["action"], "staging.initial_admin_bootstrap")
            self.assertEqual(audit["metadata"]["contract_sha256"], bootstrap.digest(self.contract))
            self.assertEqual(audit["metadata"]["reviewed_invitation_sha256"], "a" * 64)
            self.assertEqual(audit["metadata"]["deployment_approval_record_sha256"], "b" * 64)
            self.assertEqual(
                audit["metadata"]["target_observation_receipt_sha256"],
                self.observer.verify(self.contract["target"], c)["observation_receipt_sha256"],
            )
            self.assertTrue(audit["metadata"]["privileged_migration_owner_only"])
            self.assertFalse(audit["metadata"]["rights_or_reviews_seeded"])
            self.assertEqual(
                c.execute("SELECT role FROM anvil.memberships").fetchone()["role"], "admin"
            )

    def test_repeated_bootstrap_refuses_existing_global_history(self):
        self.run_bootstrap()
        before = self.counts()
        with self.assertRaisesRegex(RuntimeError, "refuses existing"):
            self.run_bootstrap()
        self.assertEqual(self.counts(), before)

    def test_preexisting_unrelated_organization_is_not_overwritten(self):
        with self.connect() as c:
            c.execute(
                "INSERT INTO anvil.organizations(id,name) VALUES(%s,'Retained SQL fixture')",
                (str(uuid4()),),
            )
        with self.assertRaisesRegex(RuntimeError, "refuses existing"):
            self.run_bootstrap()
        self.assertEqual({k: n for k, n in self.counts().items() if n}, {"organizations": 1})

    def test_mid_insert_constraint_failure_rolls_back_every_identity_row(self):
        with self.connect() as c:
            c.execute("ALTER TABLE anvil.projects ADD CONSTRAINT sql_fixture_failure CHECK(false)")
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.run_bootstrap()
        self.assert_empty()

    def test_wrong_schema_ledger_refuses_before_writes(self):
        with self.connect() as c:
            c.execute("DELETE FROM anvil.schema_versions WHERE version=58")
        with self.assertRaisesRegex(RuntimeError, "schema58"):
            self.run_bootstrap()
        self.assert_empty()

    def test_runtime_elevation_and_evaluator_login_are_denied(self):
        for statement, restore in (
            ("ALTER ROLE anvil_app SUPERUSER", "ALTER ROLE anvil_app NOSUPERUSER"),
            ("ALTER ROLE anvil_worker BYPASSRLS", "ALTER ROLE anvil_worker NOBYPASSRLS"),
            (
                "ALTER ROLE anvil_benchmark_evaluator LOGIN",
                "ALTER ROLE anvil_benchmark_evaluator NOLOGIN",
            ),
            (
                "GRANT anvil_staging_migration TO anvil_app",
                "REVOKE anvil_staging_migration FROM anvil_app",
            ),
        ):
            with self.subTest(statement=statement), self.connect() as c:
                c.execute(statement)
                try:
                    with self.assertRaisesRegex(RuntimeError, "Runtime roles"):
                        self.run_bootstrap()
                    self.assert_empty()
                finally:
                    c.execute(restore)

    def test_actual_app_and_worker_cannot_bootstrap_or_set_owner_role(self):
        for role in ("anvil_app", "anvil_worker"):
            with self.subTest(role=role), self.connect(self.environment[role + "_dsn"]) as c:
                with self.assertRaisesRegex(RuntimeError, "migration identity"):
                    self.run_bootstrap(c)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    c.execute("SET ROLE anvil_staging_migration")
                self.assert_empty()

    def test_set_role_wrapper_cannot_spoof_session_migration_identity(self):
        with self.connect() as c:
            c.execute(
                sql.SQL("CREATE ROLE bootstrap_test_wrapper LOGIN PASSWORD {}").format(
                    sql.Literal(self.environment["wrapper_password"])
                )
            )
            c.execute("GRANT anvil_staging_migration TO bootstrap_test_wrapper")
        url = urlsplit(self.dsn)
        wrapper = urlunsplit(
            (
                url.scheme,
                "bootstrap_test_wrapper:"
                + quote(self.environment["wrapper_password"], safe="")
                + "@127.0.0.1:5432",
                "/anvil",
                "",
                "",
            )
        )
        with self.connect(wrapper) as c:
            c.execute("SET ROLE anvil_staging_migration")
            identity = c.execute("SELECT current_user u,session_user s").fetchone()
            self.assertEqual(identity["u"], bootstrap.MIGRATION_ROLE)
            self.assertEqual(identity["s"], "bootstrap_test_wrapper")
            with self.assertRaisesRegex(RuntimeError, "migration identity"):
                self.run_bootstrap(c)
        self.assert_empty()

    def test_actual_cluster_mismatch_is_rejected_by_observer_binding(self):
        contract = copy.deepcopy(self.contract)
        contract["target"]["postgres_system_identifier"] = "1"
        with self.assertRaisesRegex(RuntimeError, "observation"):
            self.run_bootstrap(contract=contract)
        self.assert_empty()

    def test_concurrent_bootstrap_has_one_atomic_winner(self):
        other = copy.deepcopy(self.contract)
        other["organization"]["id"] = str(uuid4())
        other["project"]["id"] = str(uuid4())
        other["identity"]["user_id"] = str(uuid4())
        other["identity"]["subject"] = str(uuid4())
        observer = ManufacturedObserver(self.system_id, Barrier(2))

        def attempt(contract):
            try:
                return self.run_bootstrap(contract=contract, observer=observer)["status"]
            except RuntimeError as exc:
                return str(exc)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, (self.contract, other)))
        self.assertEqual(results.count("initial_real_admin_created"), 1)
        self.assertEqual(sum("refuses existing" in item for item in results), 1)
        self.assertEqual(sum(self.counts().values()), 5)


if __name__ == "__main__":
    unittest.main()
