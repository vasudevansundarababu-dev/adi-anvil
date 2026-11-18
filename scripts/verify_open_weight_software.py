"""Fresh local PostgreSQL only. Never accepts an existing deployment/database."""

import json
import os
import secrets
import subprocess
import time
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql

root = Path.cwd()
assert (root / "services/backend/migrations/128_open_weight_credentials.sql").is_file()
assert not (root / ".env").exists()
name = "forge-open-weight-" + secrets.token_hex(5)
private = root / ".local" / name
private.mkdir(mode=0o700, parents=True)
owner, app, worker = (secrets.token_urlsafe(32) for _ in range(3))
envfile = private / "postgres.env"
envfile.write_text("POSTGRES_PASSWORD=" + owner + "\n")
envfile.chmod(0o600)
subprocess.run(
    [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--label",
        "io.adi.forge.scope=open-weight-software-test",
        "--memory",
        "1g",
        "--pids-limit",
        "256",
        "--env-file",
        str(envfile),
        "-p",
        "127.0.0.1::5432",
        "postgres:17.6-bookworm@sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3",
    ],
    check=True,
    capture_output=True,
)
try:
    port = json.loads(subprocess.check_output(["docker", "inspect", name]))[0]["NetworkSettings"][
        "Ports"
    ]["5432/tcp"][0]["HostPort"]
    base = f"postgresql://postgres:{owner}@127.0.0.1:{port}/postgres"
    for _ in range(60):
        try:
            with psycopg.connect(base, connect_timeout=1):
                pass
            break
        except psycopg.OperationalError:
            time.sleep(0.5)
    else:
        raise RuntimeError("Fresh PostgreSQL startup failed")
    database = "anvil_golden_kyc_" + secrets.token_hex(5)
    with psycopg.connect(base, autocommit=True) as c:
        for role, password in [("anvil_app", app), ("anvil_worker", worker)]:
            c.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    dsn = base.rsplit("/", 1)[0] + "/" + database
    os.environ.update(
        {
            "ANVIL_ROOT": str(root),
            "ANVIL_ENV": "local",
            "WEB_ORIGIN": "http://127.0.0.1:3202",
            "DATABASE_URL": f"postgresql://anvil_app:{app}@127.0.0.1:{port}/{database}",
            "WORKER_DATABASE_URL": f"postgresql://anvil_worker:{worker}@127.0.0.1:{port}/{database}",
            "MIGRATION_DATABASE_URL": dsn,
            "ANVIL_BENCHMARK_TEST_DATABASE_URL": dsn,
            "ANVIL_SESSION_KEY": secrets.token_urlsafe(40),
            "ANVIL_LIVE_PROVIDERS_ENABLED": "false",
            "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "false",
            "ANVIL_REAL_EMAIL_ENABLED": "false",
            "ANVIL_FIXTURE_MODE": "true",
        }
    )
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("CREATE SCHEMA anvil")
    config = Config(str(root / "services/backend/alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT version_num FROM anvil.alembic_version").fetchone()[0] == "128"
    result = subprocess.run(
        [
            str(root / "services/backend/.venv/bin/python"),
            "-m",
            "pytest",
            "services/backend/tests/benchmark/test_open_weight_sql.py",
            "-q",
            "--tb=short",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = result.stdout + result.stderr
    for secret in (owner, app, worker):
        output = output.replace(secret, "[private synthetic credential]")
    (private / "pytest.log").write_text(output)
    print(output)
    summary = {
        "exit_code": result.returncode,
        "fresh_and_repeated_migrations": "passed",
        "schema": 128,
        "model_calls": 0,
        "evidence": str(private),
    }
    (private / "result.json").write_text(json.dumps(summary) + "\n")
    print(json.dumps(summary))
    if result.returncode:
        raise SystemExit(result.returncode)
finally:
    subprocess.run(["docker", "stop", name], check=True, capture_output=True)
