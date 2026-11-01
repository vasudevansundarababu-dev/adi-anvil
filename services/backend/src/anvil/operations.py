"""Local maintenance, always scoped and nondestructive."""

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from anvil.cli import ORG
from anvil.config import ROOT, local_only, setting
from anvil.db import audit, uid


def new_demo(name):
    local_only()
    if not name or not 3 <= len(name) <= 100:
        raise ValueError("Demo name must be 3..100 characters")
    project = uid()
    ids = json.loads((ROOT / ".local/demo-identities.json").read_text())
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        c.execute(
            "INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,%s)", (project, ORG, name)
        )
        for name, user in ids.items():
            if name == "outsider":
                continue
            role = "admin" if name.startswith("admin-") else "rl-engineer"
            c.execute(
                "INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,%s)",
                (project, user, role),
            )
            if role == "admin":
                for cap in ["rights_reviewer", "release_owner"]:
                    c.execute(
                        "INSERT INTO anvil.project_assignments(project_id,user_id,capability) VALUES(%s,%s,%s)",
                        (project, user, cap),
                    )
        audit(c, project, None, "demo.project_created", project, {"origin": "synthetic_fixture"})
    print(
        json.dumps(
            {
                "project_id": project,
                "url": f"http://127.0.0.1:3202/p/{project}/objectives",
                "status": "empty_isolated_demo",
            }
        )
    )


def docker(*args, stdout=None):
    subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(ROOT / ".env"),
            "-f",
            str(ROOT / "infra/local/compose.yaml"),
            "-p",
            "adi-anvil",
            "exec",
            "-T",
            "postgres",
            *args,
        ],
        check=True,
        stdout=stdout,
        cwd=ROOT,
    )


def backup():
    local_only()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uid()[:8]
    folder = ROOT / ".local/backups" / stamp
    folder.mkdir(parents=True, mode=0o700)
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot = c.execute("SELECT pg_export_snapshot() snapshot").fetchone()["snapshot"]
        metadata = c.execute("SELECT object_key,sha256 FROM anvil.artifacts").fetchall()
        with os.fdopen(
            os.open(folder / "database.dump", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
        ) as out:
            docker(
                "pg_dump",
                "-U",
                "anvil_migration",
                "-d",
                "anvil_local",
                "-Fc",
                "--snapshot",
                snapshot,
                stdout=out,
            )
        for row in metadata:
            src = ROOT / ".data/artifacts" / row["object_key"]
            if src.is_symlink() or not src.resolve().is_relative_to(
                (ROOT / ".data/artifacts").resolve()
            ):
                raise ValueError("Unsafe artifact path")
            data = src.read_bytes()
            if hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError("Artifact checksum mismatch")
            dst = folder / "artifacts" / row["object_key"]
            dst.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with os.fdopen(os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
                f.write(data)
        counts = {
            t: c.execute(
                sql.SQL("SELECT count(*) n FROM {}.{}").format(sql.Identifier(s), sql.Identifier(t))
            ).fetchone()["n"]
            for s, t in [
                ("anvil", "resources"),
                ("anvil", "episodes"),
                ("anvil", "assessments"),
                ("anvil", "import_batches"),
                ("anvil", "review_issues"),
                ("anvil", "review_resolutions"),
                ("anvil", "external_result_receipts"),
                ("anvil", "readiness_items"),
                ("anvil", "sales_contacts"),
                ("anvil", "delivery_approvals"),
                ("anvil", "sales_deliveries"),
                ("anvil_checkpoints", "checkpoints"),
            ]
        }
    manifest = {
        "schema": "anvil.local_backup.v1",
        "created_at": stamp,
        "artifacts": metadata,
        "counts": counts,
        "database_sha256": hashlib.sha256((folder / "database.dump").read_bytes()).hexdigest(),
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
    os.chmod(folder / "manifest.json", 0o600)
    (ROOT / ".local/latest-backup").write_text(str(folder))
    print("Private consistent backup created: " + str(folder.relative_to(ROOT)))


def restore_test():
    local_only()
    folder = Path((ROOT / ".local/latest-backup").read_text())
    if not folder.resolve().is_relative_to((ROOT / ".local/backups").resolve()):
        raise ValueError("Unregistered backup")
    manifest = json.loads((folder / "manifest.json").read_text())
    if (
        hashlib.sha256((folder / "database.dump").read_bytes()).hexdigest()
        != manifest["database_sha256"]
    ):
        raise ValueError("Backup integrity mismatch")
    target = "anvil_restore_" + uid().replace("-", "")[:12]
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
    # Restore never overwrites anvil_local and never drops any database or volume.
    with (folder / "database.dump").open("rb") as source:
        subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(ROOT / ".env"),
                "-f",
                str(ROOT / "infra/local/compose.yaml"),
                "-p",
                "adi-anvil",
                "exec",
                "-T",
                "postgres",
                "pg_restore",
                "-U",
                "anvil_migration",
                "-d",
                target,
                "--exit-on-error",
            ],
            stdin=source,
            check=True,
            cwd=ROOT,
        )
    with psycopg.connect(
        make_conninfo(setting("MIGRATION_DATABASE_URL"), dbname=target), row_factory=dict_row
    ) as c:
        for t, count in manifest["counts"].items():
            schema = "anvil_checkpoints" if t == "checkpoints" else "anvil"
            actual = c.execute(
                sql.SQL("SELECT count(*) n FROM {}.{}").format(
                    sql.Identifier(schema), sql.Identifier(t)
                )
            ).fetchone()["n"]
            if count != actual:
                raise ValueError("Restored count mismatch")
        for row in manifest["artifacts"]:
            if (
                hashlib.sha256((folder / "artifacts" / row["object_key"]).read_bytes()).hexdigest()
                != row["sha256"]
            ):
                raise ValueError("Restored artifact mismatch")
        pending = c.execute(
            "SELECT count(*) n FROM anvil.episodes WHERE state='awaiting_review'"
        ).fetchone()["n"]
    result = {
        "status": "passed",
        "target_database": target,
        "counts": manifest["counts"],
        "pending_reviews_preserved": pending,
        "artifact_checksums_verified": len(manifest["artifacts"]),
        "original_database_unchanged": True,
        "retained_for_inspection": True,
    }
    (folder / "restore-verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
