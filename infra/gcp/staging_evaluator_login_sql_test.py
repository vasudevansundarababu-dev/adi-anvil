"""Opt-in actual evaluator-login SQL contract; no job, GCE or OIDC proof."""

import json
import os
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ENV_FILE = os.environ.get("ANVIL_EVALUATOR_LOGIN_SQL_TEST_ENV")
LOGIN = "anvil_staging_benchmark_evaluator_login"
GROUP = "anvil_benchmark_evaluator"


@unittest.skipUnless(ENV_FILE, "Explicit newly owned evaluator-login SQL cluster required")
class ActualEvaluatorLoginSql(unittest.TestCase):
    def test_startup_role_identity_set_only_membership_and_private_denials(self):
        import psycopg
        from psycopg.rows import dict_row

        from anvil.benchmark_evaluator_worker import _identity

        state = json.loads(Path(ENV_FILE).read_text())
        self.assertEqual(state["purpose"], "isolated_evaluator_login_SQL_fixture_NOT_GCE_proof")
        address = urlsplit(state["evaluator_login_dsn"])
        self.assertEqual(
            (address.hostname, address.port, address.path), ("127.0.0.1", 5432, "/anvil")
        )
        self.assertEqual(address.username, LOGIN)
        with psycopg.connect(state["owner_dsn"], autocommit=True, row_factory=dict_row) as owner:
            role = owner.execute(
                "SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolcreatedb,"
                "rolcreaterole,rolreplication FROM pg_roles WHERE rolname=%s",
                (LOGIN,),
            ).fetchone()
            self.assertTrue(role["rolcanlogin"])
            self.assertFalse(
                any(role[key] for key in role if key not in {"rolname", "rolcanlogin"})
            )
            grants = owner.execute(
                "SELECT g.rolname,m.admin_option,m.inherit_option,m.set_option "
                "FROM pg_auth_members m JOIN pg_roles g ON g.oid=m.roleid "
                "JOIN pg_roles u ON u.oid=m.member WHERE u.rolname=%s",
                (LOGIN,),
            ).fetchall()
            self.assertEqual(
                grants,
                [
                    {
                        "rolname": GROUP,
                        "admin_option": False,
                        "inherit_option": False,
                        "set_option": True,
                    }
                ],
            )
            for forbidden in ("anvil_app", "anvil_worker", "anvil_staging_migration"):
                self.assertFalse(
                    owner.execute(
                        "SELECT pg_has_role(%s,%s,'MEMBER') allowed", (LOGIN, forbidden)
                    ).fetchone()["allowed"]
                )
            self.assertFalse(
                owner.execute(
                    "SELECT rolcanlogin FROM pg_roles WHERE rolname=%s", (GROUP,)
                ).fetchone()["rolcanlogin"]
            )
            before_jobs = owner.execute(
                "SELECT count(*) n FROM anvil.benchmark_evaluator_jobs"
            ).fetchone()["n"]

        # NOINHERIT means a plain connection has no protected evaluator identity.
        with psycopg.connect(
            state["evaluator_login_dsn"], autocommit=True, row_factory=dict_row
        ) as plain:
            self.assertEqual(
                plain.execute("SELECT current_user u,session_user s").fetchone(),
                {"u": LOGIN, "s": LOGIN},
            )
            with self.assertRaises(PermissionError):
                _identity(plain)

        # Exact proposed startup option, not a mocked identity or owner session.
        with psycopg.connect(
            state["evaluator_login_dsn"],
            options="-c role=anvil_benchmark_evaluator",
            autocommit=True,
            row_factory=dict_row,
        ) as evaluator:
            self.assertEqual(
                evaluator.execute("SELECT current_user u,session_user s").fetchone(),
                {"u": GROUP, "s": LOGIN},
            )
            _identity(evaluator)
            for table in (
                "benchmark_bundle_receipts",
                "benchmark_private_assignments",
                "benchmark_captured_outputs",
                "benchmark_native_evaluator_custody",
            ):
                with (
                    self.subTest(private_table=table),
                    self.assertRaises(psycopg.errors.InsufficientPrivilege),
                ):
                    evaluator.execute("SELECT * FROM anvil." + table)
            for forbidden in ("anvil_app", "anvil_worker", "anvil_staging_migration"):
                with (
                    self.subTest(forbidden_role=forbidden),
                    self.assertRaises(psycopg.errors.InsufficientPrivilege),
                ):
                    evaluator.execute("SET ROLE " + forbidden)

        for runtime in ("anvil_app", "anvil_worker"):
            with psycopg.connect(state[runtime + "_dsn"], autocommit=True) as connection:
                for forbidden in (GROUP, LOGIN):
                    with (
                        self.subTest(runtime=runtime, forbidden=forbidden),
                        self.assertRaises(psycopg.errors.InsufficientPrivilege),
                    ):
                        connection.execute("SET ROLE " + forbidden)
        with psycopg.connect(state["owner_dsn"], autocommit=True, row_factory=dict_row) as owner:
            self.assertEqual(
                owner.execute("SELECT count(*) n FROM anvil.benchmark_evaluator_jobs").fetchone()[
                    "n"
                ],
                before_jobs,
            )


if __name__ == "__main__":
    unittest.main()
