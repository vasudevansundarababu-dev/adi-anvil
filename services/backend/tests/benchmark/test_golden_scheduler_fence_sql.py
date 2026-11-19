"""Actual restricted LOGIN and lock races in the fresh isolated SQL fixture."""
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from test_golden_kyc_sql import connection
from test_golden_kyc_sql import owned as owned_fixture

owned = owned_fixture


def login(owned, capability="anvil_golden_scheduler", *, mixed=False):
    name, password = "fence_test_" + secrets.token_hex(5), secrets.token_urlsafe(32)
    with connection(owned) as c:
        c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION").format(sql.Identifier(name), sql.Literal(password)))
        c.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(capability), sql.Identifier(name)))
        if mixed:
            c.execute(sql.SQL("GRANT anvil_app TO {}").format(sql.Identifier(name)))
    return conninfo_to_dict(owned[0]) | {"user": name, "password": password}


def fence(c, project, user, *, argument=None):
    c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (project, user))
    return c.execute("SELECT anvil.golden_scheduler_project_fence(%s) AS allowed", (argument or project,)).fetchone()["allowed"]


def test_actual_dedicated_scheduler_can_fence_without_any_project_update_grant(owned):
    with psycopg.connect(**login(owned), row_factory=dict_row) as c:
        c.execute("SET LOCAL ROLE anvil_golden_scheduler")
        assert fence(c, owned[1], owned[2]) is True
        assert not c.execute("SELECT has_table_privilege(current_user,'anvil.projects','UPDATE') OR has_any_column_privilege(current_user,'anvil.projects','UPDATE') AS allowed").fetchone()["allowed"]
        assert fence(c, owned[1], owned[2], argument=str(uuid4())) is False
        assert fence(c, owned[1], str(uuid4())) is False


def test_wrong_login_role_mixed_capability_superlogin_and_inactive_member_are_denied(owned):
    with psycopg.connect(**login(owned, "anvil_app"), row_factory=dict_row) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            fence(c, owned[1], owned[2])
    with psycopg.connect(**login(owned, mixed=True), row_factory=dict_row) as c:
        assert fence(c, owned[1], owned[2]) is False
    with connection(owned) as c:
        assert fence(c, owned[1], owned[2]) is False
        c.execute("UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s", (owned[1], owned[2]))
    with psycopg.connect(**login(owned), row_factory=dict_row) as c:
        assert fence(c, owned[1], owned[2]) is False


def test_wrong_user_cannot_retain_an_unauthorized_project_row_lock(owned):
    with psycopg.connect(**login(owned), row_factory=dict_row) as scheduler:
        assert fence(scheduler, owned[1], str(uuid4())) is False
        with connection(owned) as owner:
            assert owner.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE NOWAIT", (owned[1],)).fetchone()


def test_repeatable_read_is_refused_before_any_project_lock(owned):
    with psycopg.connect(**login(owned), row_factory=dict_row) as scheduler:
        scheduler.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        assert fence(scheduler, owned[1], owned[2]) is False
        with connection(owned) as owner:
            assert owner.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE NOWAIT", (owned[1],)).fetchone()


def test_project_exclusive_revocation_waits_for_actual_scheduler_fence_transaction(owned):
    scheduler = psycopg.connect(**login(owned), row_factory=dict_row)
    waiting = Queue()

    def revoke():
        with connection(owned) as c:
            waiting.put(c.info.backend_pid)
            c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (owned[1],))
            c.execute("UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s", (owned[1], owned[2]))
        return True

    try:
        assert fence(scheduler, owned[1], owned[2]) is True
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(revoke)
            pid = waiting.get(timeout=2)
            try:
                deadline = time.monotonic() + 2
                blocked = False
                while time.monotonic() < deadline:
                    with connection(owned) as observer:
                        blocked = scheduler.info.backend_pid in observer.execute("SELECT pg_blocking_pids(%s) AS pids", (pid,)).fetchone()["pids"]
                    if blocked:
                        break
                    time.sleep(0.02)
                assert blocked and not future.done()
            finally:
                scheduler.commit()
            assert future.result(timeout=3) is True
        assert fence(scheduler, owned[1], owned[2]) is False
    finally:
        scheduler.close()
