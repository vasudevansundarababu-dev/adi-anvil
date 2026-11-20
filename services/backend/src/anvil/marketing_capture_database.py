"""Capture-only asynchronous DB operations under an original absolute cutoff.

Closing a local connection is not proof the server canceled or rolled back.
Timeouts/cleanup uncertainty always remain unknown and cannot authorize retry.
Shared anvil.db defaults and other application connections are unchanged.
"""

import asyncio
import math
import re
from contextlib import asynccontextmanager
from contextvars import ContextVar
from time import monotonic

import psycopg
from psycopg import capabilities, waiting
from psycopg.rows import dict_row

from anvil.marketing_capture_database_target import configuration

_cutoff = ContextVar("marketing_capture_database_cutoff", default=None)
CANCEL_RESERVE_SECONDS = .05  # Taken from original work time; never added after expiry.


class DatabaseUnknown(RuntimeError):
    def __init__(self, cause=None, *, stage=None):
        super().__init__("Capture database outcome/cleanup unknown; no retry")
        # Operator diagnostics need the cause CATEGORY, never its message,
        # query, DSN, credentials, repr or exception chain.
        name = type(cause).__name__ if cause is not None else None
        self.original_error_type = name if name and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", name) else None
        state = getattr(cause, "sqlstate", None)
        self.original_sqlstate = state if type(state) is str and re.fullmatch(r"[0-9A-Z]{5}", state) else None
        self.stage = stage if stage in {"wait", "transaction"} else None


def remaining(deadline):
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("Original absolute capture database deadline required")
    seconds = deadline - monotonic()
    if seconds <= 0:
        raise TimeoutError("Original capture database deadline reached")
    return seconds


class _CaptureConnection(psycopg.AsyncConnection):
    def __init__(self, pgconn, row_factory=dict_row):
        super().__init__(pgconn, row_factory)
        self.capture_deadline = _cutoff.get()
        self.capture_server_cancel_observed = False
        remaining(self.capture_deadline)

    async def wait(self, gen, interval=0.1, timeout=None):
        # The default driver's interruption path adds up to five seconds for
        # cancellation and another five for draining; old libpq may use a thread.
        # This scoped connection never enters that fallback or grants that time.
        started = False
        try:
            seconds = remaining(self.capture_deadline)
            if timeout is not None:
                seconds = min(seconds, timeout)
            work = seconds - CANCEL_RESERVE_SECONDS
            if work <= 0:
                raise TimeoutError("Original database cancellation reserve reached")
            async with asyncio.timeout(work):
                started = True
                return await waiting.wait_async(gen, self.pgconn.socket, interval=interval, timeout=work)
        except BaseException as error:
            try:
                # Closing the socket alone did not terminate a deferred-trigger
                # COMMIT in independent PostgreSQL testing. Cancel and drain
                # only within time reserved BEFORE the original cutoff. Never
                # use the old-libpq thread implementation or a new allowance.
                if started and capabilities.has_cancel_safe():
                    async with asyncio.timeout(remaining(self.capture_deadline)):
                        await self.cancel_safe(timeout=remaining(self.capture_deadline))
                        try:
                            await waiting.wait_async(gen, self.pgconn.socket, interval=interval,
                                                     timeout=remaining(self.capture_deadline))
                        except psycopg.errors.QueryCanceled:
                            self.capture_server_cancel_observed = True
            except BaseException:
                pass  # Unknown cancellation/cleanup stays unknown, never ready.
            finally:
                self.pgconn.finish()
            raise DatabaseUnknown(error, stage="wait") from None


async def _connect():
    """One original target/address only; never driver host failover/retry."""
    if not capabilities.has_cancel_safe():
        raise ValueError("Capture requires qualified nonblocking libpq cancellation; no thread fallback")
    parameters, fingerprint = configuration()
    remaining(_cutoff.get())
    from anvil.marketing_capture_database_qualification import installed

    if installed(fingerprint) is None:
        raise ValueError("Current exact capture API database qualification required")
    remaining(_cutoff.get())  # No DNS or implicit target lookup is performed.
    return await _CaptureConnection.connect(row_factory=dict_row, **parameters)


@asynccontextmanager
async def transaction(project=None, user=None, *, absolute_deadline, read_only=False):
    """Caller supplies an ORIGINAL trusted cutoff; no replacement allowance.

    Async DNS/connect, RLS setup, caller operations, commit/rollback and close
    share this deadline. No background connection task or sync fallback is used.
    A local close alone must never be labeled confirmed server cancellation.
    """
    if type(read_only) is not bool:
        raise ValueError("Fixed capture transaction mode required")
    remaining(absolute_deadline)
    token = _cutoff.set(absolute_deadline)
    connection = None
    try:
        async with asyncio.timeout(remaining(absolute_deadline)):
            connection = await _connect()
            async with connection.transaction():
                if read_only:
                    await connection.execute("SET TRANSACTION READ ONLY")
                await connection.execute(
                    "SELECT set_config('anvil.project', %s, true), set_config('anvil.user', %s, true)",
                    (str(project or ""), str(user or "")),
                )
                # Server-side waits are also bounded, but their expiry is not
                # itself evidence of rollback/cancellation on an actual server.
                milliseconds = int(remaining(absolute_deadline) * 1000)
                if milliseconds < 1:
                    raise TimeoutError("Original capture database deadline reached")
                await connection.execute(
                    "SELECT set_config('statement_timeout',%s,true), set_config('lock_timeout',%s,true)",
                    (str(milliseconds) + "ms", str(milliseconds) + "ms"),
                )
                yield connection
            await connection.close()
            if not connection.closed:
                raise DatabaseUnknown()
    except BaseException as error:
        if connection is not None:
            # No cancellation thread, reconnect, drain allowance or rollback
            # replay. Actual server termination remains independently observed.
            connection.pgconn.finish()
        if isinstance(error, DatabaseUnknown):
            raise
        raise DatabaseUnknown(error, stage="transaction") from None
    finally:
        _cutoff.reset(token)
