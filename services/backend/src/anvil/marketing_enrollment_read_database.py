"""Separate read-only graph observation using the existing scheduler identity.

No new credential, user-supplied connection factory, role grant or world attach.
Actual target/driver/OS/deadline qualification remains required before use.
"""

import asyncio
import hmac
import os
import re
from contextlib import asynccontextmanager

from psycopg import capabilities
from psycopg.rows import dict_row

from anvil.marketing_capture_database import DatabaseUnknown, _CaptureConnection, _cutoff, remaining
from anvil.marketing_capture_database_target import inspect_target
from anvil.praxis_generic_contract import digest

PIN = "ANVIL_CAPTURE_ENROLLMENT_READ_TARGET_SHA256"


async def _connect():
    if not capabilities.has_cancel_safe():
        raise ValueError("Qualified nonblocking scheduler read required")
    parameters, target = inspect_target(setting_name="ANVIL_GOLDEN_SCHEDULER_DATABASE_URL")
    expected = digest({"schema_version": "anvil.marketing-enrollment-read-target.v1", "target_sha256": target})
    pin = os.environ.get(PIN, "")
    if not re.fullmatch(r"[a-f0-9]{64}", pin) or not hmac.compare_digest(pin, expected):
        raise ValueError("Original scheduler read target binding required")
    remaining(_cutoff.get())
    return await _CaptureConnection.connect(row_factory=dict_row, **parameters)


@asynccontextmanager
async def transaction(project, actor, *, absolute_deadline):
    remaining(absolute_deadline)
    token = _cutoff.set(absolute_deadline)
    connection = None
    try:
        async with asyncio.timeout(remaining(absolute_deadline)):
            connection = await _connect()
            async with connection.transaction():
                await connection.execute("SET TRANSACTION READ ONLY")
                role = await (await connection.execute(
                    "SELECT NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication "
                    "AND pg_has_role(current_user,'anvil_golden_scheduler','MEMBER') "
                    "AND NOT pg_has_role(current_user,'anvil_app','MEMBER') "
                    "AND NOT pg_has_role(current_user,'anvil_worker','MEMBER') "
                    "AND NOT pg_has_role(current_user,'anvil_golden_grader','MEMBER') "
                    "AND NOT pg_has_role(current_user,'anvil_capture_registrar','MEMBER') "
                    "AND NOT pg_has_role(current_user,'anvil_capture_peer_writer','MEMBER') "
                    "AND NOT pg_has_role(current_user,'anvil_capture_enrollment_owner','MEMBER') "
                    "AND NOT pg_has_role(current_user,'anvil_private_grade_owner','MEMBER') "
                    "AND NOT has_table_privilege(current_user,'banking_private.expectations','SELECT') "
                    "AND NOT has_any_column_privilege(current_user,'banking_private.expectations','SELECT') AS allowed "
                    "FROM pg_roles WHERE rolname=current_user"
                )).fetchone()
                if not role or role["allowed"] is not True:
                    raise ValueError("Existing disjoint scheduler read identity required")
                # Same fixed already-assigned capability as the existing scheduler
                # factory; no caller-selected role or new membership is granted.
                await connection.execute("SET LOCAL ROLE anvil_golden_scheduler")
                await connection.execute(
                    "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                    (str(project), str(actor)),
                )
                milliseconds = int(remaining(absolute_deadline) * 1000)
                if milliseconds < 1:
                    raise TimeoutError("Original committed lookup deadline reached")
                await connection.execute(
                    "SELECT set_config('statement_timeout',%s,true),set_config('lock_timeout',%s,true)",
                    (str(milliseconds) + "ms", str(milliseconds) + "ms"),
                )
                yield connection
            await connection.close()
            if not connection.closed:
                raise DatabaseUnknown()
    except BaseException:
        if connection is not None:
            connection.pgconn.finish()
        raise DatabaseUnknown() from None
    finally:
        _cutoff.reset(token)
