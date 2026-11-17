"""Disjoint private operator transactions, never an API credential workflow.

Configuration and actual runtime/identity qualification remain Anvil-owned.
Nothing here issues a login, role membership, token, key or target pin. Missing
configuration fails closed; API/scheduler connections are never a fallback.
"""

import asyncio
import hmac
import os
import re
from contextlib import asynccontextmanager
from uuid import UUID

from psycopg import capabilities
from psycopg.rows import dict_row

from anvil.marketing_attester_enrollment import OriginalBinding, freeze_original
from anvil.marketing_capture_database import DatabaseUnknown, _CaptureConnection, _cutoff, remaining
from anvil.marketing_capture_database_target import inspect_target
from anvil.praxis_generic_contract import digest

PEER_SETTING = "ANVIL_CAPTURE_PEER_DATABASE_URL"
PEER_PIN = "ANVIL_CAPTURE_PEER_DATABASE_TARGET_SHA256"
REGISTRAR_SETTING = "ANVIL_CAPTURE_REGISTRAR_DATABASE_URL"
REGISTRAR_PIN = "ANVIL_CAPTURE_REGISTRAR_DATABASE_TARGET_SHA256"


async def _connect(capability, expected_login):
    if not capabilities.has_cancel_safe():
        raise ValueError("Qualified nonblocking independent operator connection required")
    if type(expected_login) is not str or not 0 < len(expected_login.encode()) <= 200:
        raise ValueError("Original independently qualified database identity required")
    if capability == "peer":
        setting, pin_name = PEER_SETTING, PEER_PIN
    elif capability == "registrar":
        setting, pin_name = REGISTRAR_SETTING, REGISTRAR_PIN
    else:
        raise ValueError("Fixed independent operator capability required")
    parameters, target = inspect_target(setting_name=setting)
    expected = digest({"schema_version": "anvil.marketing-operator-database-target.v1",
                       "capability": capability, "target_sha256": target})
    supplied = os.environ.get(pin_name, "")
    if (parameters["user"] != expected_login or not re.fullmatch(r"[a-f0-9]{64}", supplied)
            or not hmac.compare_digest(supplied, expected)):
        raise ValueError("Original independent operator target binding required")
    remaining(_cutoff.get())
    return await _CaptureConnection.connect(row_factory=dict_row, **parameters)


@asynccontextmanager
async def _transaction(capability, original, operator_id, expected_login, *, absolute_deadline):
    # All values originate in the independent receiver's retained qualified
    # operation. Never copy expected identity, scope or expiry from child data.
    if type(original) is not OriginalBinding or type(operator_id) is not UUID:
        raise ValueError("Original independent operator and immutable scope required")
    original = freeze_original(original)
    remaining(absolute_deadline)
    token = _cutoff.set(absolute_deadline)
    connection = None
    try:
        async with asyncio.timeout(remaining(absolute_deadline)):
            connection = await _connect(capability, expected_login)
            async with connection.transaction():
                await connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                desired = "anvil_capture_peer_writer" if capability == "peer" else "anvil_capture_registrar"
                other = "anvil_capture_registrar" if capability == "peer" else "anvil_capture_peer_writer"
                identity = await (await connection.execute(
                    "SELECT session_user::text AS login,current_user::text AS active,"
                    "rolcanlogin AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreatedb "
                    "AND NOT rolcreaterole AND NOT rolreplication "
                    "AND pg_has_role(session_user,%s,'MEMBER') AND NOT pg_has_role(session_user,%s,'MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_capture_enrollment_owner','MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_private_grade_owner','MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_app','MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_worker','MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_golden_scheduler','MEMBER') "
                    "AND NOT pg_has_role(session_user,'anvil_golden_grader','MEMBER') "
                    "AND NOT has_table_privilege(session_user,'banking_private.expectations','SELECT') "
                    "AND NOT has_any_column_privilege(session_user,'banking_private.expectations','SELECT') AS allowed "
                    "FROM pg_roles WHERE rolname=session_user", (desired, other),
                )).fetchone()
                if (not identity or identity["login"] != expected_login or identity["active"] != expected_login
                        or identity["allowed"] is not True):
                    raise ValueError("Disjoint authenticated operator session required")
                if capability == "peer":
                    await connection.execute("SET LOCAL ROLE anvil_capture_peer_writer")
                else:
                    await connection.execute("SET LOCAL ROLE anvil_capture_registrar")
                await connection.execute(
                    "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                    (str(original.scope.project_id), str(operator_id)),
                )
                milliseconds = int(remaining(absolute_deadline) * 1000)
                if milliseconds < 1:
                    raise TimeoutError("Original independent operator deadline reached")
                await connection.execute(
                    "SELECT set_config('statement_timeout',%s,true),set_config('lock_timeout',%s,true)",
                    (str(milliseconds) + "ms", str(milliseconds) + "ms"),
                )
                yield connection
                remaining(absolute_deadline)
            # The caller must not release graph work from inside the context:
            # COMMIT and close complete here on the SAME original cutoff.
            await connection.close()
            if not connection.closed:
                raise DatabaseUnknown()
            remaining(absolute_deadline)
    except BaseException:
        if connection is not None:
            connection.pgconn.finish()
        raise DatabaseUnknown() from None
    finally:
        _cutoff.reset(token)


def peer_transaction(original, operator_id, expected_login, *, absolute_deadline):
    """Validate peer readback INSIDE; observe commit only AFTER leaving context."""
    return _transaction("peer", original, operator_id, expected_login, absolute_deadline=absolute_deadline)


def registrar_transaction(original, operator_id, expected_login, *, absolute_deadline):
    """Separate identity/connection. Any Unknown aborts; never use read to retry."""
    return _transaction("registrar", original, operator_id, expected_login, absolute_deadline=absolute_deadline)
