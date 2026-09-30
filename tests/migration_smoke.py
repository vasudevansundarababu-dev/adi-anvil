"""Create a retained disposable database and verify all migrations from an empty schema."""

import os
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql

from anvil.config import ROOT, setting

original = setting("MIGRATION_DATABASE_URL")
target = "anvil_migrationcheck_" + uuid4().hex[:12]
with psycopg.connect(original, autocommit=True) as c:
    c.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(target)))
url = urlsplit(original)._replace(path="/" + target).geturl()
with psycopg.connect(url) as c:
    c.execute("CREATE SCHEMA anvil")
    c.execute("CREATE SCHEMA anvil_checkpoints")
try:
    os.environ["MIGRATION_DATABASE_URL"] = url
    config = Config(str(ROOT / "services/backend/alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with psycopg.connect(url) as c:
        assert c.execute(
            "SELECT version FROM anvil.schema_versions ORDER BY version"
        ).fetchall() == [(n,) for n in range(1, 18)]
        assert c.execute("SELECT version_num FROM anvil.alembic_version").fetchone()[0] == "017"
        assert c.execute(
            "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='anvil.sales_deliveries'::regclass"
        ).fetchone()[0]
    print(f"Fresh migration and repeat upgrade passed; retained disposable database: {target}")
finally:
    os.environ["MIGRATION_DATABASE_URL"] = original
