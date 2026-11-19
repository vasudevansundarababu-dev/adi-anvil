"""Create one fresh isolated synthetic database; no serving DB or approvals.

Requires a new PostgreSQL cluster reachable through a Unix socket only. A failed
setup is retained for investigation and cannot be overwritten or replayed.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import signal
import stat
import sys
from pathlib import Path
from uuid import uuid4


def require(condition):
    if not condition:
        raise ValueError("Fresh synthetic fixture setup refused")


def read_private(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o077
                and info.st_nlink == 1 and info.st_size <= 8192)
        raw = stream.read(8193)
    return json.loads(raw)


def setup(path, output):
    require(os.geteuid() == 0 and sys.flags.isolated and sys.dont_write_bytecode)
    config = read_private(path)
    require(set(config) == {"schema_version", "host", "dbname", "user", "password", "new_database", "runtime_image_sha256"}
            and config["schema_version"] == "anvil.synthetic-sql-fixture-setup.v2"
            and config["dbname"] == "postgres" and config["user"] == "postgres"
            and type(config["password"]) is str and 1 <= len(config["password"]) <= 256
            and re.fullmatch(r"anvil_golden_kyc_component_[a-z0-9_]{1,36}", config["new_database"])
            and re.fullmatch(r"[a-f0-9]{64}", config["runtime_image_sha256"])
            and os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST") == config["runtime_image_sha256"])
    host = Path(config["host"])
    require(host.is_absolute() and host.resolve() == host and host.is_dir()
            and (host / ".s.PGSQL.5432").is_socket())
    output = Path(output)
    parent = output.parent
    require(output.is_absolute() and parent.resolve() == parent and not output.exists() and not output.is_symlink())
    info = parent.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o077)

    import psycopg
    from alembic import command
    from alembic.config import Config
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from psycopg.rows import dict_row
    from sqlalchemy.engine import URL

    from anvil.config import ROOT
    from anvil.golden_kyc_anvil import source_hash
    from anvil.golden_kyc_runtime import seed
    from anvil.harbor_agents import code_digest

    admin = {key: config[key] for key in ("host", "dbname", "user", "password")}
    passwords = {role: secrets.token_urlsafe(40) for role in ("anvil_app", "anvil_worker")}
    runtime_roles = {role: "component_" + role + "_" + secrets.token_hex(5) for role in ("scheduler", "grader", "app")}
    for role in runtime_roles.values():
        passwords[role] = secrets.token_urlsafe(40)
    database = config["new_database"]
    with psycopg.connect(**admin, connect_timeout=2, autocommit=True, row_factory=dict_row) as connection:
        identity = connection.execute("SELECT session_user AS login,current_database() AS database,inet_server_addr() AS address").fetchone()
        require(identity == {"login": "postgres", "database": "postgres", "address": None})
        require(not connection.execute("SELECT datname FROM pg_database WHERE datname NOT IN('postgres','template0','template1')").fetchall())
        require(not connection.execute("SELECT rolname FROM pg_roles WHERE rolname<>'postgres' AND rolname NOT LIKE 'pg\\_%' ESCAPE '\\'").fetchall())
        for role, password in passwords.items():
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION").format(sql.Identifier(role), sql.Literal(password)))
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    target = admin | {"dbname": database}
    with psycopg.connect(**target, connect_timeout=2, autocommit=True) as connection:
        connection.execute("CREATE SCHEMA anvil")
    old = os.environ.get("MIGRATION_DATABASE_URL")
    try:
        # Alembic runs in this process using installed packages. No source path
        # insertion, subprocess environment or credential-bearing command line.
        os.environ["MIGRATION_DATABASE_URL"] = URL.create("postgresql", username="postgres", password=config["password"],
            database=database, query={"host": str(host)}).render_as_string(hide_password=False)
        migration = Config(str(ROOT / "services/backend/alembic.ini"))
        migration.set_main_option("prepend_sys_path", "")
        command.upgrade(migration, "131")
        command.upgrade(migration, "131")
    finally:
        if old is None:
            os.environ.pop("MIGRATION_DATABASE_URL", None)
        else:
            os.environ["MIGRATION_DATABASE_URL"] = old
    organization, project, user = str(uuid4()), str(uuid4()), str(uuid4())
    nonce = secrets.token_hex(32)
    label = "synthetic-component-control-not-performance"
    with psycopg.connect(**target, connect_timeout=2, autocommit=True, row_factory=dict_row) as connection:
        require(connection.execute("SELECT version_num FROM anvil.alembic_version").fetchone()["version_num"] == "131")
        connection.execute("SET search_path TO anvil_checkpoints")
        PostgresSaver(connection).setup()
        connection.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA anvil_checkpoints TO anvil_worker")
        connection.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA anvil_checkpoints TO anvil_worker")
        connection.execute("SET search_path TO public")
        for role, login in runtime_roles.items():
            connection.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier("anvil_app" if role == "app" else "anvil_golden_" + role), sql.Identifier(login)))
    with psycopg.connect(**target, connect_timeout=2, row_factory=dict_row) as connection:
        connection.execute("INSERT INTO anvil.organizations VALUES(%s,%s)", (organization, label))
        connection.execute("INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,%s)", (project, organization, label))
        connection.execute("INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,'synthetic-component-control',%s,%s)", (user, organization, user, label))
        connection.execute("INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,'admin')", (project, user))
        pack = seed(connection, project, user, include_expectations=True)["pack_id"]
        application = connection.execute("SELECT id,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id LIMIT 1", (project, pack)).fetchone()
        connection.execute("CREATE TABLE anvil.component_control_fixture(fixture_nonce text PRIMARY KEY,fixture_label text NOT NULL,project_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),consumed_at timestamptz)")
        connection.execute("INSERT INTO anvil.component_control_fixture(fixture_nonce,fixture_label,project_id) VALUES(%s,%s,%s)", (nonce, label, project))
        for login in runtime_roles.values():
            connection.execute(sql.SQL("GRANT USAGE ON SCHEMA anvil TO {}").format(sql.Identifier(login)))
            connection.execute(sql.SQL("GRANT SELECT ON anvil.component_control_fixture TO {}").format(sql.Identifier(login)))
        connection.execute(sql.SQL("GRANT UPDATE(consumed_at) ON anvil.component_control_fixture TO {}").format(sql.Identifier(runtime_roles["scheduler"])))
    control = {"schema_version": "anvil.synthetic-sql-component-config.v2", "fixture_nonce": nonce,
        "fixture_label": label, "database": database, "project_id": project, "user_id": user, "pack_id": str(pack),
        "application_id": application["id"], "snapshot_sha256": application["snapshot_sha256"],
        "golden_source_sha256": source_hash(), "broker_source_sha256": code_digest(),
        "runtime_image_sha256": config["runtime_image_sha256"]}
    for role, login in runtime_roles.items():
        control[role + "_dsn"] = make_conninfo(host=str(host), dbname=database, user=login, password=passwords[login])
    raw = json.dumps(control, sort_keys=True).encode()
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {"status": "fresh_synthetic_fixture_created_not_qualified", "database": database,
            "control_config_sha256": hashlib.sha256(raw).hexdigest(), "source_sha256": control["golden_source_sha256"],
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "native_qualified": False, "qualification_written": False, "model_calls_authorized": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, lambda *args: (_ for _ in ()).throw(TimeoutError("Bounded fixture setup deadline")))
    signal.alarm(180)
    try:
        print(json.dumps(setup(args.config, args.output), sort_keys=True))
    except Exception as error:
        print(json.dumps({"status": "setup_failed_retained_no_replay", "exception_type": type(error).__name__, "native_qualified": False}))
        raise SystemExit(1) from None
