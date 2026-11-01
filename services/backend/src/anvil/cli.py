import argparse
import json
import sys
import time
from uuid import UUID

import httpx
import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import sql
from psycopg.rows import dict_row

from anvil.config import CLOUD, ROOT, local_only, setting
from anvil.db import audit, transaction

ORG = "a0000000-0000-4000-8000-000000000001"
PROJECT = "a0000000-0000-4000-8000-000000000002"
OUTSIDER_PROJECT = "a0000000-0000-4000-8000-000000000003"


def migrate():
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), autocommit=True) as c:
        expected = "anvil" if CLOUD else "anvil_local"
        if c.info.dbname != expected:
            raise RuntimeError(f"Migration target must be {expected}")
        for name, key in [
            ("anvil_app", "ANVIL_DB_APP_PASSWORD"),
            ("anvil_worker", "ANVIL_DB_WORKER_PASSWORD"),
        ]:
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,)).fetchone():
                c.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
                    ).format(sql.Identifier(name), sql.Literal(setting(key)))
                )
        c.execute("CREATE SCHEMA IF NOT EXISTS anvil")
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config(str(ROOT / "services/backend/alembic.ini")), "head")
        c.execute("SET search_path TO anvil_checkpoints")
        PostgresSaver(c).setup()
        c.execute(
            "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA anvil_checkpoints TO anvil_worker"
        )
        c.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA anvil_checkpoints TO anvil_worker")
    print("Alembic canonical migrations and library-owned PostgreSQL checkpoints ready.")


def seed():
    local_only()
    ids = json.loads((ROOT / ".local/demo-identities.json").read_text())
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        c.execute(
            "INSERT INTO anvil.organizations VALUES(%s,%s) ON CONFLICT DO NOTHING",
            (ORG, "Anvil local synthetic lab"),
        )
        for name, user in ids.items():
            c.execute(
                "INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (user, ORG, setting("OIDC_ISSUER"), user, name),
            )
        for p, name in [
            (PROJECT, "Original synthetic diagnostics"),
            (OUTSIDER_PROJECT, "Isolation control"),
        ]:
            c.execute(
                "INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                (p, ORG, name),
            )
        for name, user in ids.items():
            role = "admin" if name.startswith("admin-") else "rl-engineer"
            p = PROJECT
            if name == "outsider":
                p, role = OUTSIDER_PROJECT, "rl-engineer"
            c.execute(
                "INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                (p, user, role),
            )
            if role == "admin":
                for capability in ["rights_reviewer", "release_owner"]:
                    c.execute(
                        "INSERT INTO anvil.project_assignments(project_id,user_id,capability) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                        (p, user, capability),
                    )
        if not c.execute(
            "SELECT 1 FROM anvil.audit_events WHERE action='synthetic_identity_bootstrap'"
        ).fetchone():
            audit(c, PROJECT, None, "synthetic_identity_bootstrap")
    print(
        "Synthetic identities/project seeded idempotently. No approvals or completed runs seeded."
    )


def health():
    with transaction() as c:
        c.execute("SELECT version FROM anvil.schema_versions WHERE version=1").fetchone()
    for _ in range(30):
        try:
            r = httpx.get(setting("OIDC_ISSUER") + "/.well-known/openid-configuration", timeout=3)
            r.raise_for_status()
            break
        except httpx.HTTPError:
            time.sleep(2)
    else:
        raise RuntimeError("OIDC unavailable")
    print("Canonical database and OIDC ready. Live inference disabled.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--name")
    parser.add_argument("--project-id", type=UUID)
    parser.add_argument("--username")
    parser.add_argument("--email")
    parser.add_argument("--project-name", default="ADI Anvil MVP v1")
    parser.add_argument("--role", action="append", default=[])
    parser.add_argument("--capability", action="append", default=[])
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()
    elif args.command == "seed":
        seed()
    elif args.command == "health":
        health()
    elif args.command == "live":
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "inference_requests": 0,
                    "reasons": [
                        "live authority absent",
                        "exact model/budget/rights/independent approvals required",
                    ],
                }
            )
        )
        sys.exit(2)
    elif args.command == "invite":
        from anvil.invitations import invite

        result = invite(
            args.username or "",
            args.email or "",
            args.name or args.username or "",
            args.project_name,
            args.role,
            args.capability,
        )
        print(json.dumps(result))
    elif args.command == "contracts":
        from anvil.api import app

        target = ROOT / "contracts/openapi/anvil.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(app.openapi(), indent=2))
        print("Generated API contract")
    elif args.command == "demo-new":
        from anvil.operations import new_demo

        new_demo(args.name)
    elif args.command == "backup":
        from anvil.operations import backup

        backup()
    elif args.command == "restore-test":
        from anvil.operations import restore_test

        restore_test()
    elif args.command == "graph-rebuild":
        if not args.project_id:
            raise SystemExit("--project-id required")
        from anvil.graph import project_graph

        with transaction(args.project_id, worker=True) as c:
            if not c.execute(
                "SELECT 1 FROM anvil.projects WHERE id=%s", (args.project_id,)
            ).fetchone():
                raise SystemExit("Project not found")
            audit(c, args.project_id, None, "local_cli.graph_rebuild")
        result = project_graph(args.project_id)
        print(json.dumps({"nodes": len(result["nodes"]), "edges": len(result["edges"])}))
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
