"""Private read-only KYC queries under one original absolute deadline.

Reuses the reviewed nonblocking driver wait/cancel/drain implementation unchanged.
Generic anvil.db defaults and Marketing connection/configuration are not changed.
No target discovery, DNS fallback, thread cancellation, reconnect or retry.
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
from anvil.praxis_case_dataset import content_hash

PIN = "ANVIL_KYC_REGISTRY_DATABASE_TARGET_SHA256"


def configuration(*, setting_name="DATABASE_URL"):
    if setting_name not in {"DATABASE_URL", "ANVIL_GOLDEN_SCHEDULER_DATABASE_URL"}:
        raise ValueError("Fixed KYC registry identity required")
    parameters, original_target = inspect_target() if setting_name == "DATABASE_URL" else inspect_target(setting_name=setting_name)
    fingerprint = content_hash({"schema_version": "anvil.private-kyc-registry-target.v1",
                                "target_sha256": original_target})
    pin = os.environ.get(PIN, "")
    if not re.fullmatch(r"[a-f0-9]{64}", pin) or not hmac.compare_digest(pin, fingerprint):
        raise ValueError("Anvil KYC registry target binding required")
    return parameters


async def _connect(*, setting_name="DATABASE_URL"):
    if not capabilities.has_cancel_safe():
        raise ValueError("Qualified nonblocking cancellation required; no fallback")
    parameters = configuration() if setting_name == "DATABASE_URL" else configuration(setting_name=setting_name)
    remaining(_cutoff.get())
    return await _CaptureConnection.connect(row_factory=dict_row, **parameters)


@asynccontextmanager
async def transaction(project, user, *, absolute_deadline, setting_name="DATABASE_URL"):
    """Original caller cutoff covers connect, read-only setup, work and closure.

    A timeout is Unknown, not proof of server termination or license to replay.
    Actual exact-image target/libpq/OS cancellation still needs qualification.
    """
    remaining(absolute_deadline)
    token = _cutoff.set(absolute_deadline)
    connection = None
    try:
        async with asyncio.timeout(remaining(absolute_deadline)):
            connection = await _connect() if setting_name == "DATABASE_URL" else await _connect(setting_name=setting_name)
            async with connection.transaction():
                await connection.execute("SET TRANSACTION READ ONLY")
                await connection.execute(
                    "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                    (str(project), str(user)),
                )
                milliseconds = int(remaining(absolute_deadline) * 1000)
                if milliseconds < 1:
                    raise TimeoutError("Original KYC registry deadline reached")
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
