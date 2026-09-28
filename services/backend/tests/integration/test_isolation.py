import json

import psycopg
import pytest

from anvil.cli import ORG, OUTSIDER_PROJECT, PROJECT
from anvil.config import ROOT
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
