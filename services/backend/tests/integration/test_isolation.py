import json

import psycopg
import pytest

from anvil.cli import ORG, OUTSIDER_PROJECT, PROJECT
from anvil.config import ROOT, setting
from anvil.db import Jsonb, digest, transaction, uid


def test_missing_context_and_cross_project_rls():
    users = json.loads((ROOT / ".local/demo-identities.json").read_text())
    rid, rev = uid(), uid()
    with transaction(PROJECT, users["researcher"]) as c:
        c.execute(
            "INSERT INTO anvil.resources(id,org_id,project_id,kind,created_by) VALUES(%s,%s,%s,%s,%s)",
            (rid, ORG, PROJECT, "objective", users["researcher"]),
        )
        c.execute(
            "INSERT INTO anvil.revisions(id,project_id,resource_id,revision,content,content_hash,created_by) VALUES(%s,%s,%s,1,%s,%s,%s)",
            (rev, PROJECT, rid, Jsonb({"test": True}), digest({"test": True}), users["researcher"]),
        )
    with transaction() as c:
        assert c.execute("SELECT * FROM anvil.resources WHERE id=%s", (rid,)).fetchone() is None
    with transaction(OUTSIDER_PROJECT, users["outsider"]) as c:
        assert c.execute("SELECT * FROM anvil.resources WHERE id=%s", (rid,)).fetchone() is None
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(
                "INSERT INTO anvil.resources(id,org_id,project_id,kind,created_by) VALUES(%s,%s,%s,%s,%s)",
                (uid(), ORG, PROJECT, "objective", users["outsider"]),
            )
    with transaction(PROJECT, users["researcher"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE anvil.revisions SET content='{}' WHERE id=%s", (rev,))
    with transaction(OUTSIDER_PROJECT, users["outsider"]) as c:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            c.execute(
                "INSERT INTO anvil.revisions(id,project_id,resource_id,revision,content,content_hash,created_by) VALUES(%s,%s,%s,2,%s,%s,%s)",
                (uid(), OUTSIDER_PROJECT, rid, Jsonb({}), digest({}), users["outsider"]),
            )
    # Exercise the same physical connection across transactions, as a pool would reuse it.
    with psycopg.connect(setting("DATABASE_URL"), autocommit=True) as reused:
        with reused.transaction():
            reused.execute(
                "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                (PROJECT, users["researcher"]),
            )
            assert reused.execute("SELECT id FROM anvil.resources WHERE id=%s", (rid,)).fetchone()
        with reused.transaction():
            assert (
                reused.execute("SELECT id FROM anvil.resources WHERE id=%s", (rid,)).fetchone()
                is None
            )


def test_runtime_roles_are_nonowners_without_bypass():
    for worker in (False, True):
        with transaction(worker=worker) as c:
            role = c.execute(
                "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
            assert not role["rolsuper"] and not role["rolbypassrls"]
            assert c.execute(
                "SELECT tableowner FROM pg_tables WHERE schemaname='anvil' AND tablename='resources'"
            ).fetchone()["tableowner"] not in ("anvil_app", "anvil_worker")


def test_web_role_cannot_access_checkpoints_and_worker_cannot_read_private_references():
    users = json.loads((ROOT / ".local/demo-identities.json").read_text())
    with transaction(PROJECT, users["data-engineer"]) as c:
        reference = c.execute(
            "SELECT id FROM anvil.artifacts WHERE classification='hidden_reference' LIMIT 1"
        ).fetchone()
        assert reference
        with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
            c.execute("SELECT * FROM anvil_checkpoints.checkpoints LIMIT 1")
    with transaction(PROJECT, worker=True) as c:
        assert (
            c.execute("SELECT id FROM anvil.artifacts WHERE id=%s", (reference["id"],)).fetchone()
            is None
        )
        assert (
            c.execute(
                "SELECT v.content FROM anvil.revisions v JOIN anvil.resources r ON r.id=v.resource_id WHERE r.kind='rubric'"
            ).fetchall()
            == []
        )
