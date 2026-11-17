"""Private synchronous API facade over the nonblocking deadline-owned driver.

One owner thread/event loop/connection; no thread cancellation, reconnect, DNS or
fresh work/cleanup allowance. All inherited synchronous SQL helpers use the same
absolute cutoff, including cursor fetch, SAVEPOINT, COMMIT, rollback and close.
This is new unqualified source until actual driver/server acceptance is recorded.
"""

import asyncio
import hmac
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from threading import get_ident
from uuid import UUID

from psycopg import capabilities
from psycopg.rows import dict_row

from anvil.marketing_capture_database import DatabaseUnknown, _CaptureConnection, _cutoff
from anvil.marketing_capture_database_target import inspect_target
from anvil.marketing_native_wire_bounds import remaining
from anvil.praxis_case_dataset import content_hash

PIN="ANVIL_KYC_RUNTIME_DATABASE_TARGET_SHA256"
SCHEDULER_PIN="ANVIL_KYC_SCHEDULER_DATABASE_TARGET_SHA256"


def configuration(*,setting_name="DATABASE_URL"):
    if setting_name not in {"DATABASE_URL","ANVIL_GOLDEN_SCHEDULER_DATABASE_URL"}:
        raise ValueError("Fixed private KYC API/scheduler identity required")
    scheduler=setting_name=="ANVIL_GOLDEN_SCHEDULER_DATABASE_URL"
    parameters,target=inspect_target(setting_name=setting_name)
    expected=content_hash({"schema_version":"anvil.private-kyc-scheduler-target.v1" if scheduler else "anvil.private-kyc-runtime-target.v1","target_sha256":target})
    pin=os.environ.get(SCHEDULER_PIN if scheduler else PIN,"")
    if not re.fullmatch(r"[a-f0-9]{64}",pin) or not hmac.compare_digest(pin,expected):
        raise ValueError("Exact private KYC API database target qualification required")
    return parameters


class Cursor:
    def __init__(self,owner,cursor):
        self._owner,self._cursor=owner,cursor

    def fetchone(self):
        return self._owner._run(self._cursor.fetchone)

    def fetchmany(self,*args):
        return self._owner._run(self._cursor.fetchmany,*args)

    def fetchall(self):
        return self._owner._run(self._cursor.fetchall)

    def execute(self,*args,**kwargs):
        self._owner._run(self._cursor.execute,*args,**kwargs)
        return self

    def executemany(self,*args,**kwargs):
        self._owner._run(self._cursor.executemany,*args,**kwargs)
        return self

    def __iter__(self):
        return iter(self.fetchall())

    def __enter__(self):
        self._owner._check()
        return self

    def __exit__(self,*args):
        self._owner._run(self._cursor.close)

    @property
    def rowcount(self):
        self._owner._check()
        return self._cursor.rowcount


class Connection:
    def __init__(self,runner,connection,deadline):
        self._runner,self._connection,self.absolute_deadline=runner,connection,deadline
        self._owner_thread=get_ident()

    def tighten_deadline(self,deadline):
        self.absolute_deadline=min(self.absolute_deadline,deadline)
        self._connection.capture_deadline=min(self._connection.capture_deadline,self.absolute_deadline)
        remaining(self.absolute_deadline)

    def _check(self):
        if get_ident()!=self._owner_thread:
            raise RuntimeError("Private KYC connection cannot cross threads")
        remaining(self.absolute_deadline)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise RuntimeError("Private sync KYC facade cannot run in an active event loop")

    def _run(self,operation,*args,**kwargs):
        self._check()

        async def invoke():
            async with asyncio.timeout(remaining(self.absolute_deadline)):
                value=await operation(*args,**kwargs)
                remaining(self.absolute_deadline)
                return value

        return self._runner.run(invoke())

    def execute(self,*args,**kwargs):
        return Cursor(self,self._run(self._connection.execute,*args,**kwargs))

    def cursor(self,*args,**kwargs):
        self._check()
        return Cursor(self,self._connection.cursor(*args,**kwargs))

    @contextmanager
    def transaction(self):
        savepoint=self._connection.transaction()
        self._run(savepoint.__aenter__)
        try:
            yield self
        except BaseException as exc:
            self._run(savepoint.__aexit__,type(exc),exc,exc.__traceback__)
            raise
        else:
            self._run(savepoint.__aexit__,None,None,None)

    @property
    def info(self):
        self._check()
        return self._connection.info


@contextmanager
def transaction(project,user,*,absolute_deadline,setting_name="DATABASE_URL"):
    """Exact API identity/project, original clock and confirmed transaction exit."""
    remaining(absolute_deadline)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("Private sync KYC transaction requires a synchronous server route")
    if not capabilities.has_cancel_safe():
        raise ValueError("Qualified nonblocking libpq cancellation required")
    scheduler=setting_name=="ANVIL_GOLDEN_SCHEDULER_DATABASE_URL"
    parameters=configuration() if not scheduler and setting_name=="DATABASE_URL" else configuration(setting_name=setting_name)
    remaining(absolute_deadline)
    runner=asyncio.Runner()
    connection=None
    facade=None

    async def connect():
        token=_cutoff.set(absolute_deadline)
        try:
            async with asyncio.timeout(remaining(absolute_deadline)):
                return await _CaptureConnection.connect(row_factory=dict_row,autocommit=True,**parameters)
        finally:
            _cutoff.reset(token)

    try:
        connection=runner.run(connect())
        facade=Connection(runner,connection,absolute_deadline)
        facade.execute("BEGIN")
        role=facade.execute("SELECT NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication "
                            "AND pg_has_role(current_user,%s,'MEMBER') "
                            "AND NOT pg_has_role(current_user,'anvil_kyc_qualifier','MEMBER') "
                            "AND NOT pg_has_role(current_user,%s,'MEMBER') "
                            "AND NOT pg_has_role(current_user,'anvil_worker','MEMBER') "
                            "AND NOT pg_has_role(current_user,'anvil_golden_grader','MEMBER') AS restricted "
                            "FROM pg_roles WHERE rolname=current_user",
                            ("anvil_golden_scheduler" if scheduler else "anvil_app",
                             "anvil_app" if scheduler else "anvil_golden_scheduler")).fetchone()
        if not role or role["restricted"] is not True:
            raise ValueError("Existing restricted API identity required")
        if scheduler:
            forbidden=facade.execute("SELECT has_table_privilege(current_user,'banking_private.expectations','SELECT') AS forbidden").fetchone()
            if not forbidden or forbidden["forbidden"] is not False:
                raise ValueError("Scheduler cannot read private expected outcomes")
            facade.execute("SET LOCAL ROLE anvil_golden_scheduler")
        facade.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",(str(project),str(user or "")))
        milliseconds=int(remaining(absolute_deadline)*1000)
        if milliseconds<1:
            raise TimeoutError("Original KYC database cutoff elapsed")
        facade.execute("SELECT set_config('statement_timeout',%s,true),set_config('lock_timeout',%s,true)",
                       (str(milliseconds)+"ms",str(milliseconds)+"ms"))
        try:
            yield facade
        except BaseException:
            try:
                facade.execute("ROLLBACK")
            except BaseException:
                raise DatabaseUnknown() from None
            raise
        else:
            facade.execute("COMMIT")
        facade._run(connection.close)
        if not connection.closed:
            raise DatabaseUnknown()
    except (TimeoutError,asyncio.CancelledError):
        raise DatabaseUnknown() from None
    finally:
        if connection is not None and not connection.closed:
            connection.pgconn.finish()
        runner.close()


@dataclass(frozen=True,slots=True)
class SchedulerConnections:
    """Immutable per-attempt factory; every scheduler/checkpoint/tool SQL is bounded."""
    project_id: str
    absolute_deadline: float
    user_id: str | None = None

    def __call__(self):
        from anvil.golden_kyc_dispatch_scope import current

        if current() is not None:
            raise RuntimeError("Scheduler cannot borrow an API dispatch scope")
        remaining(self.absolute_deadline)
        return transaction(self.project_id,self.user_id,absolute_deadline=self.absolute_deadline,
                           setting_name="ANVIL_GOLDEN_SCHEDULER_DATABASE_URL")

    def for_actor(self,user,*,absolute_deadline):
        value=str(UUID(str(user)))
        if self.user_id is not None and self.user_id!=value:
            raise ValueError("Scheduler cannot change assigned actor")
        deadline=min(self.absolute_deadline,absolute_deadline)
        remaining(deadline)
        return SchedulerConnections(self.project_id,deadline,value)
