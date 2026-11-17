"""Fresh local-only PostgreSQL execution test; retained database, no paid calls."""

import json
import os
import secrets
import subprocess
import time
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import sql

root = Path.cwd()
assert (root / "services/backend/src/anvil/golden_kyc_service.py").is_file()
assert not (root / ".env").exists(), "Use a clean isolated checkout, never operational credentials"
name = "forge-gym-sql-20261117-" + secrets.token_hex(3)
private = root / ".local" / name
private.mkdir(mode=0o700, parents=True)
owner, app, worker = (secrets.token_urlsafe(32) for _ in range(3))
envfile = private / "postgres.env"
envfile.write_text("POSTGRES_PASSWORD=" + owner + "\n")
envfile.chmod(0o600)
image = (
    "postgres:17.6-bookworm@sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3"
)
subprocess.run(
    [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--label",
        "io.adi.forge.scope=gym-software-test",
        "--memory",
        "1g",
        "--pids-limit",
        "256",
        "--env-file",
        str(envfile),
        "-p",
        "127.0.0.1::5432",
        image,
    ],
    check=True,
    capture_output=True,
)
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
    raise RuntimeError("Fresh PostgreSQL did not become ready")
database = "anvil_golden_kyc_" + secrets.token_hex(5)
with psycopg.connect(base, autocommit=True) as c:
    for role, password in [("anvil_app", app), ("anvil_worker", worker)]:
        c.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
    c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
owner_dsn = base.rsplit("/", 1)[0] + "/" + database
os.environ.update(
    {
        "ANVIL_ROOT": str(root),
        "ANVIL_ENV": "local",
        "WEB_ORIGIN": "http://127.0.0.1:3202",
        "DATABASE_URL": f"postgresql://anvil_app:{app}@127.0.0.1:{port}/{database}",
        "WORKER_DATABASE_URL": f"postgresql://anvil_worker:{worker}@127.0.0.1:{port}/{database}",
        "MIGRATION_DATABASE_URL": owner_dsn,
        "ANVIL_BENCHMARK_TEST_DATABASE_URL": owner_dsn,
        "ANVIL_SESSION_KEY": secrets.token_urlsafe(40),
        "ANVIL_GOLDEN_KYC_ENABLED": "true",
        "ANVIL_FIXTURE_MODE": "true",
        "ANVIL_LIVE_PROVIDERS_ENABLED": "false",
        "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "false",
        "ANVIL_REAL_EMAIL_ENABLED": "false",
        "ANVIL_OPA_BINARY": str(root / ".local/bin/opa-1.22.2"),
        "ANVIL_OPA_SHA256": "c7767cb68c21c3ea9866a76a2d6703d132a25ddad3cd1c1213925e2802ed1dce",
        "ANVIL_GOLDEN_COMPONENT_PYTHON": str(root / "services/openenv/.venv/bin/python"),
    }
)
assert Path(os.environ["ANVIL_OPA_BINARY"]).is_file()
from anvil.golden_kyc_source import source_hash  # noqa: E402

source_before = source_hash()
with psycopg.connect(owner_dsn, autocommit=True) as c:
    c.execute("CREATE SCHEMA anvil")
command.upgrade(Config(str(root / "services/backend/alembic.ini")), "head")
command.upgrade(Config(str(root / "services/backend/alembic.ini")), "head")
with psycopg.connect(owner_dsn, autocommit=True) as c:
    c.execute("SET search_path TO anvil_checkpoints")
    PostgresSaver(c).setup()
    c.execute(
        "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA anvil_checkpoints TO anvil_worker"
    )
    c.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA anvil_checkpoints TO anvil_worker")
print(
    json.dumps(
        {
            "container": name,
            "database": database,
            "fresh_and_repeated_migration": "passed",
            "model_calls": 0,
        }
    ),
    flush=True,
)
tests = [
    "services/backend/tests/benchmark/test_golden_kyc_sql.py",
    "services/backend/tests/benchmark/test_golden_kyc_anvil_sql.py",
    "services/backend/tests/benchmark/test_golden_phase_checkpoint_sql.py",
    "services/backend/tests/benchmark/test_marketing_workflow_sql.py",
]
log = private / "pytest.log"
with log.open("w") as handle:
    result = subprocess.run(
        [
            str(root / "services/openenv/.venv/bin/python"),
            "-m",
            "pytest",
            *tests,
            "-q",
            "--tb=short",
        ],
        stdout=handle,
        stderr=subprocess.STDOUT,
        timeout=1200,
    )
text = log.read_text()
for secret in (owner, app, worker):
    text = text.replace(secret, "[private test credential]")
print(text[-16000:])
assert source_hash() == source_before, (
    "Source changed during test; retain failure and use a new test import"
)
summary = {
    "exit_code": result.returncode,
    "evidence": str(private),
    "model_calls": 0,
    "source_sha256": source_before,
}
(private / "result.json").write_text(json.dumps(summary, indent=2) + "\n")
subprocess.run(["docker", "stop", name], check=True, capture_output=True)
print(json.dumps(summary))
raise SystemExit(result.returncode)
