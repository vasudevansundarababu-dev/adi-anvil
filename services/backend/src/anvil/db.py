import hashlib
import json
from contextlib import contextmanager
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from anvil.config import setting


def uid():
    return str(uuid4())


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


@contextmanager
def transaction(project=None, user=None, worker=False):
    with psycopg.connect(
        setting("WORKER_DATABASE_URL" if worker else "DATABASE_URL"), row_factory=dict_row
    ) as conn:
        conn.execute(
            "SELECT set_config('anvil.project', %s, true), set_config('anvil.user', %s, true)",
            (str(project or ""), str(user or "")),
        )
        yield conn


def audit(conn, project, user, action, target=None, metadata=None):
    conn.execute(
        "INSERT INTO anvil.audit_events(project_id,actor_id,action,target_id,metadata) "
        "VALUES (%s,%s,%s,%s,%s)",
        (project, user, action, target, Jsonb(metadata or {})),
    )


def one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def project_fence(conn, project):
    """Harbor intent/outcome transactions lock project before group/job/plan/check rows.

    KEY SHARE is compatible with audit FK checks. Do not add it to generic API
    transactions, whose concurrent shared-to-exclusive lock upgrades could deadlock.
    """
    if not conn.execute(
        "SELECT id FROM anvil.projects WHERE id=%s FOR KEY SHARE", (project,)
    ).fetchone():
        raise RuntimeError("project_unavailable")
