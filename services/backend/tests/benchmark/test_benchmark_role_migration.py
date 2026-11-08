"""Actual migration tests require a separate disposable PostgreSQL cluster.

Never point ANVIL_ROLEPROBE_DATABASE_URL at the normal browser/Coding database:
these tests intentionally change cluster-global test-role attributes.
"""

import os
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.exc import DBAPIError

from anvil.config import ROOT

ROLE = "anvil_benchmark_evaluator"
REJECTION = "existing benchmark evaluator role is not the required restricted principal"
RESET = "NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION"


@pytest.fixture(scope="module")
def cluster():
    dsn = os.environ.get("ANVIL_ROLEPROBE_DATABASE_URL")
    if not dsn:
        pytest.skip("Separate disposable role-probe cluster not configured; not migration evidence")
    parsed = urlsplit(dsn)
    assert parsed.hostname == "127.0.0.1" and parsed.path == "/anvil_roleprobe"
    with psycopg.connect(dsn, autocommit=True) as c:
        for name in ("anvil_app", "anvil_worker", "anvil_roleprobe_parent"):
            existing = c.execute(
                "SELECT rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=%s",
                (name,),
            ).fetchone()
            if existing is None:
                c.execute(
                    sql.SQL(
                        "CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
                    ).format(sql.Identifier(name))
                )
            else:
                assert existing == (False,) * 5
    return dsn


def fresh_038(cluster, monkeypatch):
    target = "anvil_roleprobe_" + uuid4().hex[:12]
    with psycopg.connect(cluster, autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(target)))
    dsn = urlsplit(cluster)._replace(path="/" + target).geturl()
    monkeypatch.setenv("MIGRATION_DATABASE_URL", dsn)
    with psycopg.connect(dsn) as c:
        c.execute("CREATE SCHEMA anvil")
    config = Config(str(ROOT / "services/backend/alembic.ini"))
    command.upgrade(config, "038")
    return dsn, config


def flags(c):
    return c.execute(
        "SELECT rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolinherit,rolreplication FROM pg_roles WHERE rolname=%s",
        (ROLE,),
    ).fetchone()


def test_actual_migration_reuses_only_restricted_cluster_role_across_databases(
    cluster, monkeypatch
):
    for _ in range(2):
        dsn, config = fresh_038(cluster, monkeypatch)
        command.upgrade(config, "039")
        command.upgrade(config, "039")
        with psycopg.connect(dsn) as c:
            assert flags(c) == (False,) * 7
            assert c.execute("SELECT version_num FROM anvil.alembic_version").fetchone() == ("039",)
            assert c.execute(
                "SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='anvil.benchmark_evaluator_jobs'::regclass"
            ).fetchone() == (True, True)


@pytest.mark.parametrize(
    "unsafe",
    [
        "LOGIN",
        "SUPERUSER",
        "BYPASSRLS",
        "CREATEDB",
        "CREATEROLE",
        "INHERIT",
        "REPLICATION",
        "membership",
    ],
)
def test_unsafe_existing_role_is_rejected_without_repair_or_partial_migration(
    cluster, monkeypatch, unsafe
):
    dsn, config = fresh_038(cluster, monkeypatch)
    with psycopg.connect(cluster, autocommit=True) as c:
        c.execute("ALTER ROLE anvil_benchmark_evaluator " + RESET)
        if unsafe == "membership":
            c.execute("GRANT anvil_roleprobe_parent TO anvil_benchmark_evaluator")
        else:
            c.execute("ALTER ROLE anvil_benchmark_evaluator " + unsafe)
        before = flags(c)
    try:
        with pytest.raises(DBAPIError) as error:
            command.upgrade(config, "039")
        assert REJECTION in str(error.value.orig)
        with psycopg.connect(dsn) as c:
            assert flags(c) == before
            assert c.execute("SELECT version_num FROM anvil.alembic_version").fetchone() == ("038",)
            assert c.execute("SELECT to_regclass('anvil.benchmark_evaluator_jobs')").fetchone() == (
                None,
            )
            if unsafe == "membership":
                assert (
                    c.execute(
                        "SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)",
                        (ROLE,),
                    ).fetchone()[0]
                    == 1
                )
    finally:
        # This explicitly dedicated cluster has no browser/Coding workload.
        with psycopg.connect(cluster, autocommit=True) as c:
            c.execute("REVOKE anvil_roleprobe_parent FROM anvil_benchmark_evaluator")
            c.execute("ALTER ROLE anvil_benchmark_evaluator " + RESET)
