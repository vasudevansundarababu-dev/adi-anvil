"""Manufactured pipes/HTTP only. No API preparation, admission or model calls."""

import io
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from anvil import marketing_paid_dispatch_rpc as rpc
from anvil import marketing_paid_dispatch_transport as transport
from anvil import worker_dispatch_broker as broker


def context(monkeypatch):
    monkeypatch.setattr(broker.pilot_environment, "current", lambda: "qa")
    monkeypatch.setenv("ANVIL_WORKER_BROKER_ROLE", "worker")
    monkeypatch.setenv("ANVIL_WORKER_BROKER_ENABLED", "true")
    monkeypatch.setenv("ANVIL_WORKER_BROKER_URL", "http://api:8200/internal/v1/worker-dispatch")
    monkeypatch.setattr(broker, "harbor_live_enabled", lambda: True)
    monkeypatch.setattr(broker, "monotonic", lambda: 100.0)
    job = {key: str(uuid4()) for key in ("id", "project_id", "lease_token")}
    return job, str(uuid4()), str(uuid4())


def test_prepare_uses_original_cutoff_and_exact_single_request(monkeypatch):
    job, actor, plan = context(monkeypatch)
    calls = []

    def execute(operation, payload, **bounds):
        calls.append((operation, payload, bounds))
        return b'{"once_prepared":true}'

    monkeypatch.setattr(transport, "execute", execute)
    assert broker.forward(
        job, actor, plan, 0, operation="prepare", remaining_seconds=120, absolute_deadline=110.0
    ) == {"once_prepared": True}
    assert len(calls) == 1
    operation, payload, bounds = calls[0]
    assert operation == "prepare" and payload["lease_token"] == job["lease_token"]
    assert bounds == {"absolute_deadline": 110.0, "request_seconds": 10}


def test_prepare_timeout_is_unknown_and_never_replayed(monkeypatch):
    job, actor, plan = context(monkeypatch)
    calls = []

    def execute(*args, **kwargs):
        calls.append(1)
        raise TimeoutError("manufactured-private-response")

    monkeypatch.setattr(transport, "execute", execute)
    with pytest.raises(RuntimeError, match="outcome_unknown_no_retry") as error:
        broker.forward(job, actor, plan, 0, operation="prepare", absolute_deadline=110.0)
    assert len(calls) == 1 and "manufactured-private-response" not in str(error.value)


def test_prepare_does_not_bypass_disabled_worker_dispatch(monkeypatch):
    job, actor, plan = context(monkeypatch)
    monkeypatch.setenv("ANVIL_WORKER_BROKER_ENABLED", "false")
    monkeypatch.setattr(transport, "execute", lambda *a, **k: pytest.fail("No request allowed"))
    with pytest.raises(RuntimeError, match="dispatch_disabled"):
        broker.forward(job, actor, plan, 0, operation="prepare", absolute_deadline=110.0)


@pytest.mark.parametrize("slow", [False, True])
def test_fixed_prepare_http_path_body_cap_and_delayed_response_without_retry(monkeypatch, slow):
    clock, calls, closed = [100.0], [], []

    class Response:
        status = 200
        first = True

        def read(self, amount):
            assert amount == 4096
            if slow:
                clock[0] = 102.0
            if not self.first:
                return b""
            self.first = False
            return b'{"once_prepared":true}'

    class Connection:
        sock = None

        def __init__(self, host, port, *, timeout):
            assert (host, port, timeout) == ("api", 8200, 1.0)

        def request(self, method, path, **kwargs):
            calls.append((method, path, kwargs))

        def getresponse(self):
            return Response()

        def close(self):
            closed.append(True)

    monkeypatch.setattr(rpc, "monotonic", lambda: clock[0])
    monkeypatch.setattr(rpc.http.client, "HTTPConnection", Connection)
    raw = json.dumps(
        {"operation": "prepare", "request": {"lease_token": "manufactured-capability"}}
    ).encode()
    if slow:
        with pytest.raises(TimeoutError, match="response deadline"):
            rpc.exchange(raw, 1.0)
    else:
        assert rpc.exchange(raw, 1.0) == b'{"once_prepared":true}'
    assert len(calls) == 1 and calls[0][:2] == ("POST", "/internal/v1/worker-dispatch/prepare")
    assert closed == [True]


@pytest.mark.parametrize("fail", [False, True])
def test_prepare_child_reserves_cleanup_inside_original_deadline(monkeypatch, fail):
    calls, killed, waits = [], [], []
    process = SimpleNamespace(
        stdin=io.BytesIO(),
        stdout=io.BytesIO(),
        poll=lambda: None if fail else 0,
        kill=lambda: killed.append(True),
        wait=lambda timeout: waits.append(timeout),
    )
    monkeypatch.setattr(transport, "monotonic", lambda: 100.0)

    def spawn(argv, **kwargs):
        calls.append((argv, kwargs))
        return process

    def pump(child, raw, deadline):
        assert child is process and deadline == 103.0
        assert json.loads(raw)["operation"] == "prepare"
        if fail:
            raise TimeoutError("manufactured-deadline")
        return b'{"once_prepared":true}'

    monkeypatch.setattr(transport.subprocess, "Popen", spawn)
    monkeypatch.setattr(transport, "_pump", pump)
    if fail:
        with pytest.raises(TimeoutError):
            transport.execute("prepare", {}, absolute_deadline=110.0, request_seconds=6)
    else:
        assert (
            transport.execute("prepare", {}, absolute_deadline=110.0, request_seconds=6)
            == b'{"once_prepared":true}'
        )
    assert len(calls) == 1 and calls[0][0][1:3] == ["-I", "-S"]
    assert calls[0][1]["env"] == {"LANG": "C.UTF-8"}
    assert waits == [5] and killed == ([True] if fail else [])
    assert process.stdin.closed and process.stdout.closed
