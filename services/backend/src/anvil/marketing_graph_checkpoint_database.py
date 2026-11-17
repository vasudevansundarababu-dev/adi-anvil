"""Fixed thread-free scheduler connections for the original graph process.

No pool, worker thread, caller DSN/factory/role, reconnect or deadline renewal.
Actual kernel/filesystem/libpq timing and cancellation still need qualification.
Closing locally never asserts server rollback or absence of an ambiguous commit.
"""

import hmac
import os
import re
from contextlib import contextmanager
from threading import get_native_id
from uuid import UUID

import psycopg
from psycopg import capabilities, pq, waiting
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from anvil.marketing_capture_database import CANCEL_RESERVE_SECONDS, DatabaseUnknown, remaining
from anvil.marketing_capture_database_target import inspect_target
from anvil.praxis_generic_contract import digest

PIN = "ANVIL_GRAPH_SCHEDULER_DATABASE_TARGET_SHA256"


class _GraphConnection(psycopg.Connection):
    def __init__(self, pgconn, deadline):
        super().__init__(pgconn, row_factory=dict_row)
        self.capture_deadline = deadline
        self.capture_server_cancel_observed = False
        self._original_process = os.getpid()
        self._original_thread = get_native_id()

    def wait(self, gen, interval=.01, timeout=None):
        if os.getpid() != self._original_process or get_native_id() != self._original_thread:
            self.pgconn.finish()
            raise DatabaseUnknown()
        started = False
        try:
            seconds = remaining(self.capture_deadline)
            if timeout is not None:
                seconds = min(seconds, timeout)
            work = seconds - CANCEL_RESERVE_SECONDS
            if work <= 0:
                raise TimeoutError("Original graph database cancellation reserve reached")
            started = True
            return waiting.wait(gen, self.pgconn.socket, interval=min(.01, interval), timeout=work)
        except BaseException:
            try:
                if started and capabilities.has_cancel_safe():
                    # libpq17 secure nonblocking cancel; no old-libpq/thread
                    # fallback. Both cancel and SAME-generator drain stay inside
                    # time reserved before the ORIGINAL graph cutoff.
                    self.cancel_safe(timeout=remaining(self.capture_deadline))
                    try:
                        waiting.wait(gen, self.pgconn.socket, interval=.01, timeout=remaining(self.capture_deadline))
                    except psycopg.errors.QueryCanceled:
                        self.capture_server_cancel_observed = True
            except BaseException:
                pass  # Cleanup uncertainty remains Unknown, never retry permission.
            finally:
                self.pgconn.finish()
            raise DatabaseUnknown() from None


def _connect_poll(pgconn, deadline):
    # Retain the actual PGconn before polling, so timeout/error always closes
    # that SAME original socket rather than an inaccessible driver attempt.
    while True:
        remaining(deadline)
        state = pgconn.connect_poll()
        if state == pq.PollingStatus.OK:
            pgconn.nonblocking = 1
            return
        if state not in (pq.PollingStatus.READING, pq.PollingStatus.WRITING):
            raise DatabaseUnknown()
        ready = 0
        while not ready:
            remaining(deadline)
            ready = yield pgconn.socket, waiting.Wait.R if state == pq.PollingStatus.READING else waiting.Wait.W


def _connect(deadline):
    if not capabilities.has_cancel_safe():
        raise ValueError("Qualified nonblocking libpq17 graph scheduler required")
    parameters, target = inspect_target(setting_name="ANVIL_GOLDEN_SCHEDULER_DATABASE_URL")
    expected = digest({"schema_version": "anvil.marketing-graph-checkpoint-target.v1", "target_sha256": target})
    configured = os.environ.get(PIN, "")
    if not re.fullmatch(r"[a-f0-9]{64}", configured) or not hmac.compare_digest(configured, expected):
        raise ValueError("Original graph scheduler target pin required")
    remaining(deadline)
    pgconn = None
    try:
        # No psycopg.connect host-attempt loop/default timeout, DNS resolver,
        # service expansion, implicit endpoint or background connection worker.
        pgconn = pq.PGconn.connect_start(make_conninfo("", **parameters).encode())
        waiting.wait_conn(_connect_poll(pgconn, deadline), interval=.01, timeout=remaining(deadline))
        remaining(deadline)
        return _GraphConnection(pgconn, deadline)
    except BaseException:
        if pgconn is not None:
            pgconn.finish()
        raise DatabaseUnknown() from None


def scheduler_connections(job, *, absolute_deadline):
    """Fixed callable for GraphRunner.connections; configuration is Anvil-owned.

    Original trusted job is snapshotted BEFORE child/checkpoint calls. No private
    dataset/expectations or provider credential is returned to the graph process.
    Each connection belongs to one calling thread and the same original PID.
    """
    if type(job) is not dict:
        raise ValueError("Original scheduler job required")
    project, actor, job_id, plan, lease = (UUID(str(job[key])) for key in
                                         ("project_id", "actor_id", "id", "plan_id", "lease_token"))
    remaining(absolute_deadline)
    original_pid = os.getpid()

    @contextmanager
    def connections():
        remaining(absolute_deadline)
        if os.getpid() != original_pid:
            raise ValueError("Construct graph scheduler factory in the original graph child")
        connection = None
        try:
            connection = _connect(absolute_deadline)
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                role = connection.execute(
                    "SELECT current_user::text=session_user::text AND rolcanlogin "
                    "AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication "
                    "AND pg_has_role(session_user,'anvil_golden_scheduler','MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_app','MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_worker','MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_golden_grader','MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_capture_registrar','MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_capture_peer_writer','MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_capture_enrollment_owner','MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_private_grade_owner','MEMBER') "
                    "AND NOT has_table_privilege(session_user,'banking_private.expectations','SELECT') "
                    "AND NOT has_any_column_privilege(session_user,'banking_private.expectations','SELECT') "
                    "AND NOT has_table_privilege(session_user,'campaign_private.world_sources','SELECT') "
                    "AND NOT has_column_privilege(session_user,'campaign_private.world_sources','definition','SELECT') "
                    "AND NOT has_table_privilege(session_user,'marketing_runtime.seals','SELECT') "
                    "AND NOT has_column_privilege(session_user,'marketing_runtime.seals','capture','SELECT') AS allowed "
                    "FROM pg_roles WHERE rolname=session_user"
                ).fetchone()
                if not role or role["allowed"] is not True:
                    raise ValueError("Disjoint original scheduler identity required")
                connection.execute("SET LOCAL ROLE anvil_golden_scheduler")
                connection.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                                   (str(project), str(actor)))
                milliseconds = int(remaining(absolute_deadline) * 1000)
                if milliseconds < 1:
                    raise TimeoutError("Original graph scheduler deadline reached")
                connection.execute("SELECT set_config('statement_timeout',%s,true),set_config('lock_timeout',%s,true)",
                                   (str(milliseconds) + "ms", str(milliseconds) + "ms"))
                current = connection.execute("SELECT marketing_runtime.paid_job_current(%s,%s,%s) AS allowed",
                                             (job_id, lease, plan)).fetchone()
                if not current or current["allowed"] is not True:
                    raise ValueError("Original current graph job/lease authority required")
                yield connection
                remaining(absolute_deadline)
            connection.close()
            remaining(absolute_deadline)
            if not connection.closed:
                raise DatabaseUnknown()
        except BaseException:
            if connection is not None:
                connection.pgconn.finish()
            raise DatabaseUnknown() from None

    return connections
