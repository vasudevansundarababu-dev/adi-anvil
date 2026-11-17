"""Fake processes/fds/selectors only: no child, socket, HTTP or native run."""

from collections import deque
from types import SimpleNamespace

import pytest

from anvil import marketing_paid_world_transport as transport


def fixture(monkeypatch, mode="complete", *, cleanup_fail=False, wait_advance=0):
    clock, writes, launches = [100.0], [], []

    class Pipe:
        def __init__(self, fd):
            self.fd, self.closed = fd, False

        def fileno(self):
            return self.fd

        def close(self):
            self.closed = True

    class Process:
        def __init__(self):
            self.stdin, self.stdout = Pipe(10), Pipe(11)
            self.done, self.killed, self.wait_timeout = None, False, None

        def poll(self):
            return self.done

        def kill(self):
            self.killed, self.done = True, -9

        def wait(self, timeout):
            self.wait_timeout = timeout
            clock[0] += wait_advance
            if cleanup_fail:
                raise TimeoutError("Manufactured cleanup uncertainty")
            return self.done

    process = Process()
    chunks = deque([b'{"public":true}', b""])

    class Selector:
        def __init__(self):
            self.files = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def register(self, file, event):
            self.files[file] = event

        def unregister(self, file):
            self.files.pop(file)

        def select(self, timeout):
            clock[0] += min(timeout, 0.09 if mode == "drip" else 0.01)
            if mode == "blocked":
                return []
            file = process.stdin if process.stdin in self.files else process.stdout
            return [(SimpleNamespace(fileobj=file), self.files[file])]

    def read(fd, count):
        assert fd == process.stdout.fd and count == 4096
        if mode in {"drip", "oversized"}:
            return b"x" if mode == "drip" else b"x" * 4096
        chunk = chunks.popleft()
        if not chunk:
            process.done = 0
        return chunk

    def launch(args, **kwargs):
        launches.append((args, kwargs))
        return process

    monkeypatch.setattr(transport, "monotonic", lambda: clock[0])
    monkeypatch.setattr(transport.os, "set_blocking", lambda *args: None)
    monkeypatch.setattr(transport.os, "write", lambda fd, raw: writes.append(raw) or len(raw))
    monkeypatch.setattr(transport.os, "read", read)
    monkeypatch.setattr(transport.selectors, "DefaultSelector", Selector)
    monkeypatch.setattr(transport.subprocess, "Popen", launch)
    return process, launches, writes, clock


def test_one_fixed_isolated_child_payload_only_stdin_and_bounded_reap(monkeypatch):
    process, launches, writes, clock = fixture(monkeypatch)
    raw = b'{"lease":"manufactured-private-capability"}'
    assert transport.execute(raw, absolute_deadline=110.0, request_seconds=5) == b'{"public":true}'
    assert len(launches) == 1 and b"".join(writes) == raw
    args, kwargs = launches[0]
    assert args[1:3] == ["-I", "-S"] and args[3].endswith("marketing_paid_world_rpc.py")
    assert "manufactured-private-capability" not in str(args) + str(kwargs)
    assert kwargs["env"] == {"LANG": "C.UTF-8"}
    assert kwargs["stderr"] == transport.subprocess.DEVNULL
    assert kwargs["start_new_session"] is False
    assert process.wait_timeout == pytest.approx(105.0 - clock[0]) and not process.killed
    assert process.stdin.closed and process.stdout.closed


@pytest.mark.parametrize("mode", ["drip", "blocked"])
def test_slow_bytes_or_blocked_stdin_cannot_reset_one_absolute_deadline(monkeypatch, mode):
    process, launches, writes, clock = fixture(monkeypatch, mode)
    with pytest.raises(TimeoutError, match="absolute_rpc_deadline"):
        transport.execute(b'{"public":true}', absolute_deadline=101.0, request_seconds=5)
    assert len(launches) == 1 and process.killed
    assert clock[0] <= 101.000001
    assert process.wait_timeout == pytest.approx(101.0 - clock[0])
    assert 0 <= process.wait_timeout <= transport.CLEANUP_SECONDS
    assert process.stdin.closed and process.stdout.closed


def test_response_limit_fails_before_retaining_extra_bytes_and_does_not_retry(monkeypatch):
    process, launches, _, _ = fixture(monkeypatch, "oversized")
    with pytest.raises(ValueError, match="response_limit"):
        transport.execute(b"{}", absolute_deadline=110.0, request_seconds=5)
    assert len(launches) == 1 and process.killed


def test_uncertain_owned_cleanup_remains_unknown(monkeypatch):
    process, launches, _, _ = fixture(monkeypatch, cleanup_fail=True)
    with pytest.raises(RuntimeError, match="cleanup_unknown_no_retry"):
        transport.execute(b"{}", absolute_deadline=110.0, request_seconds=5)
    assert len(launches) == 1 and 0 < process.wait_timeout < 5


def test_expired_or_oversized_request_never_starts_a_child(monkeypatch):
    _, launches, _, _ = fixture(monkeypatch)
    with pytest.raises(TimeoutError):
        transport.execute(b"{}", absolute_deadline=100.5, request_seconds=5)
    with pytest.raises(ValueError):
        transport.execute(b"x" * 98305, absolute_deadline=110.0, request_seconds=5)
    assert launches == []


@pytest.mark.parametrize("cleanup_fail", [False, True])
def test_successful_bytes_cannot_escape_deadline_during_cleanup_and_unknown_takes_precedence(
    monkeypatch, cleanup_fail
):
    process, launches, _, clock = fixture(monkeypatch, cleanup_fail=cleanup_fail, wait_advance=2.0)
    error, reason = (
        (RuntimeError, "cleanup_unknown_no_retry")
        if cleanup_fail
        else (TimeoutError, "deadline_after_cleanup")
    )
    with pytest.raises(error, match=reason):
        transport.execute(b"{}", absolute_deadline=101.0, request_seconds=5)
    assert len(launches) == 1 and 0 < process.wait_timeout < 1
    assert clock[0] > 101.0
