"""Async cancellation/identity controls with fake sockets; real SQL separate."""

import asyncio
from contextlib import asynccontextmanager
from time import monotonic
from types import SimpleNamespace

import pytest

from anvil import marketing_capture_database as database


@pytest.mark.parametrize("phase", [None, "connect", "rls", "timeout_setup", "operation", "commit", "close"])
def test_one_original_deadline_covers_connect_rls_work_commit_and_close(monkeypatch, phase):
    events = []

    async def pause(name):
        events.append(name)
        if phase == name:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                events.append(name + "_cancelled")
                raise

    class Connection:
        closed = False

        def finish(self):
            self.closed = True
            events.append("local_finish_not_server_proof")

        @property
        def pgconn(self):
            return self

        @asynccontextmanager
        async def transaction(self):
            events.append("begin")
            yield
            await pause("commit")

        async def execute(self, sql, args):
            if "anvil.project" in sql:
                assert args == ("original-project", "original-user")
                await pause("rls")
            elif "statement_timeout" in sql:
                assert args[0] == args[1] and 0 < int(args[0][:-2]) <= 1000
                await pause("timeout_setup")
            else:
                assert sql == "ACTUAL_SCOPED_OPERATION"
                await pause("operation")

        async def close(self):
            await pause("close")
            self.closed = True

    connection = Connection()

    async def connect():
        await pause("connect")
        return connection

    monkeypatch.setattr(database, "_connect", connect)

    async def run():
        async with database.transaction("original-project", "original-user", absolute_deadline=monotonic() + (1 if phase is None else .02)) as scoped:
            assert scoped is connection
            await scoped.execute("ACTUAL_SCOPED_OPERATION", ())

    if phase is None:
        asyncio.run(run())
        assert connection.closed and events == ["connect", "begin", "rls", "timeout_setup", "operation", "commit", "close"]
    else:
        with pytest.raises(database.DatabaseUnknown, match="no retry"):
            asyncio.run(run())
        assert phase + "_cancelled" in events
        if phase != "connect":
            assert connection.closed
        assert events.count("connect") == 1


def test_driver_interruption_closes_without_extra_cancel_drain_or_sync_fallback(monkeypatch):
    events = []

    async def wait(*_, **__):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            events.append("driver_wait_cancelled")
            raise

    monkeypatch.setattr(database.waiting, "wait_async", wait)
    fake = SimpleNamespace(capture_deadline=monotonic() + .2,
                           pgconn=SimpleNamespace(socket=1, finish=lambda: events.append("connection_closed_server_unknown")))
    with pytest.raises(database.DatabaseUnknown):
        asyncio.run(database._CaptureConnection.wait(fake, iter(())))
    assert events == ["driver_wait_cancelled", "connection_closed_server_unknown"]


@pytest.mark.parametrize("cancel_hangs", [False, True])
def test_nonblocking_cancel_and_drain_share_reserved_original_time_without_extension(monkeypatch, cancel_hangs):
    events = []
    hard = monotonic() + .15

    async def wait(*_, **__):
        if not events:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                events.append("work_cancelled")
                raise
        events.append("drain")
        raise database.psycopg.errors.QueryCanceled("manufactured server cancellation")

    async def cancel(*, timeout):
        events.append("cancel")
        assert 0 < timeout <= database.CANCEL_RESERVE_SECONDS + .002
        if cancel_hangs:
            await asyncio.sleep(60)

    monkeypatch.setattr(database.waiting, "wait_async", wait)
    fake = SimpleNamespace(capture_deadline=hard, capture_server_cancel_observed=False, cancel_safe=cancel,
                           pgconn=SimpleNamespace(socket=1, finish=lambda: events.append("closed")))
    with pytest.raises(database.DatabaseUnknown):
        asyncio.run(database._CaptureConnection.wait(fake, iter(())))
    assert monotonic() <= hard + .03
    assert events == (["work_cancelled", "cancel", "closed"] if cancel_hangs else ["work_cancelled", "cancel", "drain", "closed"])
    assert fake.capture_server_cancel_observed is (not cancel_hangs)


def test_reserved_cancellation_time_is_never_used_to_start_new_sql(monkeypatch):
    events = []

    async def forbidden(*_, **__):
        pytest.fail("No new SQL or cancellation channel without starting work")

    monkeypatch.setattr(database.waiting, "wait_async", forbidden)
    fake = SimpleNamespace(capture_deadline=monotonic() + .02, cancel_safe=forbidden,
                           pgconn=SimpleNamespace(socket=1, finish=lambda: events.append("closed")))
    with pytest.raises(database.DatabaseUnknown):
        asyncio.run(database._CaptureConnection.wait(fake, iter(())))
    assert events == ["closed"]


def test_old_libpq_cannot_enable_thread_fallback_or_start_connection(monkeypatch):
    monkeypatch.setattr(database.capabilities, "has_cancel_safe", lambda: False)
    with pytest.raises(ValueError, match="no thread fallback"):
        asyncio.run(database._connect())


def test_expired_deadline_starts_no_connect_or_setup(monkeypatch):
    async def forbidden():
        pytest.fail("No connect after original deadline")

    monkeypatch.setattr(database, "_connect", forbidden)

    async def run():
        async with database.transaction(absolute_deadline=monotonic() - 1):
            pytest.fail("No expired transaction")

    with pytest.raises(TimeoutError):
        asyncio.run(run())


def test_prebound_target_preserves_hostname_without_any_dns_or_reconnect(monkeypatch):
    calls = []
    parameters = {"host": "original-db.example", "hostaddr": "192.0.2.1", "sslmode": "verify-full"}
    monkeypatch.setattr(database, "configuration", lambda: (parameters, "a" * 64))

    async def connect(**values):
        calls.append(values)
        return object()

    monkeypatch.setattr(database._CaptureConnection, "connect", connect)

    async def run():
        async def forbidden(*_, **__):
            pytest.fail("No operation-time resolver")

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", forbidden)
        token = database._cutoff.set(monotonic() + 2)
        try:
            await database._connect()
        finally:
            database._cutoff.reset(token)

    asyncio.run(run())
    assert len(calls) == 1 and calls[0]["hostaddr"] == "192.0.2.1"
    assert calls[0]["host"] == "original-db.example" and calls[0]["sslmode"] == "verify-full"


def test_configuration_denial_starts_no_connection(monkeypatch):
    from anvil.marketing_capture_database_target import TargetUnavailable

    def unavailable():
        raise TargetUnavailable("capture_database_binding_pin_stale")

    async def forbidden(**_):
        pytest.fail("No connection for stale binding")

    monkeypatch.setattr(database, "configuration", unavailable)
    monkeypatch.setattr(database._CaptureConnection, "connect", forbidden)
    with pytest.raises(TargetUnavailable, match="pin_stale"):
        asyncio.run(database._connect())


def test_hostname_without_numeric_binding_never_resolves_or_connects(monkeypatch):
    from anvil import marketing_capture_database_target as target

    monkeypatch.delenv("PGHOSTADDR", raising=False)
    monkeypatch.setattr(target, "setting", lambda _: "host=original-db.example dbname=original user=original sslmode=verify-full gssencmode=disable")

    async def forbidden(*_, **__):
        pytest.fail("No operation-time DNS or connection")

    monkeypatch.setattr(database._CaptureConnection, "connect", forbidden)

    async def run():
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", forbidden)
        async with database.transaction(absolute_deadline=monotonic() + 1):
            pytest.fail("No transaction without Anvil target binding")

    with pytest.raises(database.DatabaseUnknown):
        asyncio.run(run())


def test_configuration_read_cannot_reset_original_connection_deadline(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(database, "monotonic", lambda: clock[0])

    def configuration():
        clock[0] = 102.0
        return {}, "a" * 64

    async def forbidden(**_):
        pytest.fail("No late connection after configuration read")

    monkeypatch.setattr(database, "configuration", configuration)
    monkeypatch.setattr(database._CaptureConnection, "connect", forbidden)
    token = database._cutoff.set(101.0)
    try:
        with pytest.raises(TimeoutError):
            asyncio.run(database._connect())
    finally:
        database._cutoff.reset(token)
