"""Real process/pipe/filesystem/Unix tests; only paid provider HTTP is simulated."""

import hashlib
import http.client
import json
import os
import select
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing, contextmanager
from types import SimpleNamespace

import httpx
import pytest
from test_benchmark_provider_loop import binding, response, tool

from anvil.benchmark_conversation import Tool, run_contract
from anvil.benchmark_tool_gateway import ArtifactTools, StdioConnection, conversation_gateway
from anvil.config import ROOT


@contextmanager
def owned_process(script=None):
    fixture = (
        ROOT / "fixtures/benchmark-bundle/fictional-points-v1/runtime_pack/FX-001/tool-server.py"
    )
    if script is None:
        assert (
            hashlib.sha256(fixture.read_bytes()).hexdigest()
            == "a2f4197652df6a03503b18b1c20fa195f5cd596c47b450322ac958aab1af138d"
        )
    command = (
        [sys.executable, "-u", str(fixture)]
        if script is None
        else [sys.executable, "-u", "-c", script]
    )
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
    )

    def stop():
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)

    try:
        yield process, stop
    finally:
        stop()
        process.stdin.close()
        process.stdout.close()


def square_tool():
    data = json.loads(
        (
            ROOT / "fixtures/benchmark-bundle/fictional-points-v1/runtime_pack/FX-001/tools.json"
        ).read_bytes()
    )["tools"][0]
    return Tool(name=data["name"], description=data["description"], parameters=data["inputSchema"])


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
def test_real_stdio_calculation_and_correlated_final_artifact(provider, tmp_path):
    root = tmp_path / "out"
    root.mkdir(mode=0o700)
    requests = []
    with owned_process() as (process, stop):
        stdio = StdioConnection(process, [square_tool()], stop_owned=stop)
        stdio.initialize()

        def send(req):
            requests.append(req)
            if len(requests) == 1:
                return httpx.Response(
                    200,
                    json=response(
                        provider,
                        calls=[("calc-1", "square", {"n": 7}), ("calc-2", "square", {"n": 3})],
                    ),
                )
            if len(requests) == 2:
                assert "49" in req.content.decode() and "9" in req.content.decode()
                return httpx.Response(
                    200,
                    json=response(
                        provider,
                        calls=[
                            (
                                "write-1",
                                "write_artifact",
                                {
                                    "path": "report.md",
                                    "text": "Measured fixture tool outputs49 and9; not model performance",
                                },
                            )
                        ],
                    ),
                )
            return httpx.Response(200, json=response(provider, text="Finished"))

        result = run_contract(
            binding(provider),
            "Use fixture actor inputs only",
            [square_tool(), tool()],
            ArtifactTools(root, {"report.md": 1000}, stdio=stdio),
            httpx.MockTransport(send),
        )
        assert result.status == "completed" and len(requests) == 3, result
        assert stdio.counter == 4
        assert [o.value["content"][0]["text"] for o in result.turns[0].observations] == ["49", "9"]
        assert "49 and9" in (root / "report.md").read_text()


@pytest.mark.parametrize(
    "fault",
    [
        "traversal",
        "absolute",
        "undeclared",
        "symlink",
        "hardlink",
        "overwrite",
        "quota",
        "parent_symlink",
    ],
)
def test_output_writer_cannot_escape_declared_owned_namespace(fault, tmp_path):
    root = tmp_path / "out"
    root.mkdir(mode=0o700)
    outside = tmp_path / "private-canary"
    outside.write_text("PRIVATE")
    runner = ArtifactTools(root, {"report.md": 10, "sub/report.md": 10})
    path = "report.md"
    text = "output"
    if fault == "traversal":
        path = "../private-canary"
    elif fault == "absolute":
        path = str(outside)
    elif fault == "undeclared":
        path = "other.md"
    elif fault == "symlink":
        (root / path).symlink_to(outside)
    elif fault == "hardlink":
        os.link(outside, root / path)
    elif fault == "overwrite":
        (root / path).write_text("first")
    elif fault == "quota":
        text = "a" * 11
    else:
        (root / "sub").symlink_to(tmp_path, target_is_directory=True)
        path = "sub/report.md"
    with pytest.raises((ValueError, OSError)):
        runner.call("write_artifact", {"path": path, "text": text}, timeout=1)
    assert outside.read_text() == "PRIVATE"


@pytest.mark.parametrize("fault", ["bool_id", "wrong_id", "oversize", "timeout"])
def test_stdio_framing_failure_stops_only_owned_process(fault):
    expression = "True" if fault == "bool_id" else "r['id']+1" if fault == "wrong_id" else "r['id']"
    script = "import sys,json,time\nfor line in sys.stdin:\n r=json.loads(line)\n"
    script += (
        " time.sleep(3)\n"
        if fault == "timeout"
        else f" print(json.dumps({{'jsonrpc':'2.0','id':{expression},'result':{{'value':{'x' * 66000!r}}}}}),flush=True)\n"
        if fault == "oversize"
        else f" print(json.dumps({{'jsonrpc':'2.0','id':{expression},'result':{{}}}}),flush=True)\n"
    )
    with owned_process(script) as (process, stop):
        connection = StdioConnection(process, [square_tool()], stop_owned=stop)
        with pytest.raises((ValueError, TimeoutError)):
            connection.rpc("tools/list", {}, timeout=0.1)
        assert process.poll() is not None and connection.closed
        with pytest.raises(ValueError):
            connection.rpc("tools/list", {}, timeout=0.1)


def test_stdio_blocked_input_write_obeys_total_rpc_deadline():
    with owned_process("import time;time.sleep(3)") as (process, stop):
        os.set_blocking(process.stdin.fileno(), False)
        while True:
            try:
                os.write(process.stdin.fileno(), b"x" * 4096)
            except BlockingIOError:
                break
        connection = StdioConnection(process, [square_tool()], stop_owned=stop)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(connection.rpc, "tools/call", {"text": "x" * 60000}, timeout=0.05)
            try:
                with pytest.raises(TimeoutError):
                    future.result(timeout=0.5)
                assert process.poll() is not None, (
                    "RPC timeout did not stop blocked owned input pipe"
                )
            finally:
                stop()


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=3)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def gateway_request(gateway, session, token=None):
    with closing(UnixConnection(gateway.path)) as client:
        client.request(
            "POST",
            "/actor",
            json.dumps({"session_id": session}),
            {
                "Authorization": "Bearer " + (token or gateway.token),
                "Content-Type": "application/json",
            },
        )
        reply = client.getresponse()
        data = reply.read(65537)
        return reply.status, json.loads(data)


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
def test_real_unix_gateway_and_installed_harbor_host_agent_client(provider, tmp_path):
    root = tmp_path / "out"
    root.mkdir(mode=0o700)
    calls = []

    def send(req):
        calls.append(req)
        return httpx.Response(200, json=response(provider, text="Finished"))

    def execute():
        return run_contract(
            binding(provider),
            "Actor only",
            [tool()],
            ArtifactTools(root, {"report.md": 1}),
            httpx.MockTransport(send),
        )

    gateway = conversation_gateway(tmp_path, "owned-trial", execute)
    try:
        assert gateway_request(gateway, "owned-trial", "wrong")[0] == 409 and not calls
        assert gateway_request(gateway, "other-trial")[0] == 409 and not calls
        script = "import asyncio,logging;from types import SimpleNamespace;from anvil_harbor.sme import SMEAgent;agent=SMEAgent(logs_dir=None,model_name='offline-fixture',logger=logging.getLogger('test'));asyncio.run(agent.run('ignored',SimpleNamespace(session_id='owned-trial'),None))"
        env = {
            "PATH": os.defpath,
            "PYTHONPATH": str(ROOT / "services/harbor/src"),
            "ANVIL_HARBOR_GATEWAY_SOCKET": gateway.path,
            "ANVIL_HARBOR_GATEWAY_TOKEN": gateway.token,
        }
        result = subprocess.run(
            [str(ROOT / ".local/harbor-venv/bin/python"), "-c", script],
            env=env,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr.decode()
        assert len(calls) == 1 and gateway.result["conversation"].status == "completed"
        assert gateway_request(gateway, "owned-trial")[0] == 409 and len(calls) == 1
    finally:
        gateway.close()


def test_gateway_concurrent_duplicate_executes_at_most_once(tmp_path):
    calls = []

    def send(req):
        calls.append(req)
        return httpx.Response(200, json=response("openai", text="Finished"))

    def execute():
        return run_contract(binding("openai"), "Actor", [tool()], None, httpx.MockTransport(send))

    gateway = conversation_gateway(tmp_path, "owned", execute)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: gateway_request(gateway, "owned")[0], range(2)))
        assert sorted(results) == [200, 409] and len(calls) == 1
    finally:
        gateway.close()


def test_uninitialized_and_reinitialized_stdio_are_not_call_authority():
    with owned_process() as (process, stop):
        connection = StdioConnection(process, [square_tool()], stop_owned=stop)
        with pytest.raises(ValueError):
            connection.call("square", {"n": 3}, timeout=1)
        assert connection.counter == 0
        connection.initialize()
        with pytest.raises(ValueError):
            connection.initialize()


def test_aggregate_declared_output_quota_is_not_per_file_only(tmp_path):
    root = tmp_path / "out"
    root.mkdir(mode=0o700)
    with pytest.raises(ValueError):
        ArtifactTools(root, {"a.md": 16 * 1024 * 1024, "b.md": 1})


def test_bad_stdio_initialization_is_terminal_and_stops_owned_process():
    script = "import sys,json\nfor line in sys.stdin:\n r=json.loads(line);print(json.dumps({'jsonrpc':'2.0','id':r.get('id'),'result':{'protocolVersion':'wrong'}}),flush=True)"
    with owned_process(script) as (process, stop):
        connection = StdioConnection(process, [square_tool()], stop_owned=stop)
        with pytest.raises(ValueError):
            connection.initialize()
        assert connection.closed and not connection.ready and process.poll() is not None


def test_failed_unknown_gateway_response_is_terminal_not_retryable(tmp_path):
    calls = []

    def send(req):
        calls.append(req)
        raise httpx.ReadTimeout("private-canary", request=req)

    def execute():
        return run_contract(binding("openai"), "Actor", [tool()], None, httpx.MockTransport(send))

    gateway = conversation_gateway(tmp_path, "owned", execute)
    try:
        assert gateway_request(gateway, "owned")[0] == 409
        assert gateway_request(gateway, "owned")[0] == 409
        assert len(calls) == 1 and gateway.result["conversation"].status == "execution_unknown"
    finally:
        gateway.close()


def test_direct_stdio_bridge_rejects_schema_invalid_arguments_before_rpc():
    with owned_process() as (process, stop):
        connection = StdioConnection(process, [square_tool()], stop_owned=stop)
        connection.initialize()
        before = connection.counter
        with pytest.raises(ValueError):
            connection.call("square", {"n": True}, timeout=1)
        assert connection.counter == before and not connection.closed


@contextmanager
def raw_gateway(gateway):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(gateway.path)
        yield client


def request_headers(gateway, body, *, token=None, extra=b"", length=None):
    return (
        (
            f"POST /actor HTTP/1.0\r\nAuthorization: Bearer {token or gateway.token}\r\nContent-Length: {len(body) if length is None else length}\r\n"
        ).encode()
        + extra
        + b"\r\n"
    )


def raw_response(client):
    response = http.client.HTTPResponse(client)
    response.begin()
    body = response.read(65537)
    assert len(body) <= 65536
    return response.status, json.loads(body)


def counted_gateway(tmp_path):
    calls = []

    def execute():
        calls.append("dispatch")
        return SimpleNamespace(status="completed")

    return conversation_gateway(tmp_path, "owned", execute), calls


def test_wrong_auth_waits_for_split_bounded_body_and_never_spends_attempt(tmp_path):
    gateway, calls = counted_gateway(tmp_path)
    body = b'{"session_id":"owned"}'
    try:
        # Fixed32 header-first schedules, not a retry of any attempted dispatch.
        for index in range(32):
            with raw_gateway(gateway) as client:
                client.sendall(request_headers(gateway, body, token="wrong"))
                assert not select.select([client], [], [], 0.02)[0], (
                    "Rejected before bounded body arrived"
                )
                cut = 1 + index % (len(body) - 1)
                client.sendall(body[:cut])
                assert not select.select([client], [], [], 0.005)[0], "Rejected during split body"
                client.sendall(body[cut:])
                assert raw_response(client)[0] == 409
                assert calls == []
        assert gateway_request(gateway, "owned")[0] == 200 and calls == ["dispatch"]
        assert gateway_request(gateway, "owned")[0] == 409 and calls == ["dispatch"]
    finally:
        gateway.close()


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate_length",
        "nondecimal_length",
        "negative_length",
        "missing_length",
        "transfer_encoding",
        "oversized",
        "short_body",
        "bad_json",
        "bad_shape",
        "wrong_session",
        "wrong_route",
    ],
)
def test_invalid_frames_never_dispatch_or_consume_single_use(tmp_path, fault):
    gateway, calls = counted_gateway(tmp_path)
    body = b'{"session_id":"owned"}'
    headers = request_headers(gateway, body)
    if fault == "duplicate_length":
        headers = request_headers(gateway, body, extra=b"Content-Length: 21\r\n")
    elif fault == "nondecimal_length":
        headers = request_headers(gateway, body, length="+21")
    elif fault == "negative_length":
        headers = request_headers(gateway, body, length=-1)
    elif fault == "missing_length":
        headers = (
            b"POST /actor HTTP/1.0\r\nAuthorization: Bearer " + gateway.token.encode() + b"\r\n\r\n"
        )
    elif fault == "transfer_encoding":
        headers = request_headers(gateway, body, extra=b"Transfer-Encoding: chunked\r\n")
    elif fault == "oversized":
        headers = request_headers(gateway, body, length=257)
    elif fault == "short_body":
        body = body[:-1]
    elif fault == "bad_json":
        body = b"not-json"
        headers = request_headers(gateway, body)
    elif fault == "bad_shape":
        body = b'{"other":"owned"}'
        headers = request_headers(gateway, body)
    elif fault == "wrong_session":
        body = b'{"session_id":"other"}'
        headers = request_headers(gateway, body)
    else:
        headers = headers.replace(b"/actor", b"/other")
    try:
        with raw_gateway(gateway) as client:
            client.sendall(headers + body)
            if fault == "short_body":
                client.shutdown(socket.SHUT_WR)
            assert raw_response(client)[0] == 409
        assert calls == []
        assert gateway_request(gateway, "owned")[0] == 200 and calls == ["dispatch"]
    finally:
        gateway.close()


def test_absolute_framing_deadline_rejects_slow_body_not_just_idle_socket(tmp_path):
    gateway, calls = counted_gateway(tmp_path)
    body = b'{"session_id":"owned"}'
    try:
        with raw_gateway(gateway) as client:
            client.sendall(request_headers(gateway, body, length=256))
            started = time.monotonic()
            closed = False
            for _ in range(60):
                if select.select([client], [], [], 0.04)[0]:
                    client.recv(4096)
                    closed = True
                    break
                client.sendall(b" ")
            assert closed and time.monotonic() - started < 1.8
        assert calls == []
        assert gateway_request(gateway, "owned")[0] == 200 and calls == ["dispatch"]
    finally:
        gateway.close()


def test_stalled_header_or_body_does_not_block_shutdown(tmp_path):
    for prefix in (
        b"POST /actor HTTP/1.0\r\nX-Stall:",
        b"POST /actor HTTP/1.0\r\nContent-Length: 21\r\n\r\n",
    ):
        gateway, calls = counted_gateway(tmp_path)
        with raw_gateway(gateway) as client:
            client.sendall(prefix)
            started = time.monotonic()
            gateway.close()
            assert time.monotonic() - started < 1.5
            assert select.select([client], [], [], 0.5)[0], (
                "Owned shutdown left client handler alive"
            )
        assert calls == []


def test_slow_header_trickle_has_an_absolute_deadline(tmp_path):
    gateway, calls = counted_gateway(tmp_path)
    try:
        with raw_gateway(gateway) as client:
            client.sendall(b"POST /actor HTTP/1.0\r\nX-Stall:")
            started = time.monotonic()
            closed = False
            for _ in range(60):
                if select.select([client], [], [], 0.04)[0]:
                    client.recv(4096)
                    closed = True
                    break
                client.sendall(b"x")
            assert closed and time.monotonic() - started < 1.8
        assert calls == []
        assert gateway_request(gateway, "owned")[0] == 200 and calls == ["dispatch"]
    finally:
        gateway.close()


def test_stalled_connection_cap_is_bounded_and_shutdown_releases_every_slot(tmp_path):
    gateway, calls = counted_gateway(tmp_path)
    try:
        with ExitStack() as stack:
            for index in range(4):
                client = stack.enter_context(raw_gateway(gateway))
                client.sendall(b"POST /actor HTTP/1.0\r\nX-Stall:")
                deadline = time.monotonic() + 0.5
                while time.monotonic() < deadline:
                    with gateway.server._guard:
                        count = len(gateway.server._active)
                    if count == index + 1:
                        break
                    time.sleep(0.001)
                assert count == index + 1
            with raw_gateway(gateway) as overflow:
                assert overflow.recv(1) == b""
            with gateway.server._guard:
                assert len(gateway.server._active) == 4
            started = time.monotonic()
            gateway.close()
            assert time.monotonic() - started < 1.5
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                with gateway.server._guard:
                    remaining = len(gateway.server._active)
                if not remaining:
                    break
                time.sleep(0.001)
            assert not remaining and calls == []
    finally:
        gateway.close()


def test_framing_timer_never_cancels_an_authorized_slow_callback(tmp_path):
    calls = []

    def execute():
        calls.append("dispatch")
        time.sleep(1.1)
        return SimpleNamespace(status="completed")

    gateway = conversation_gateway(tmp_path, "owned", execute)
    try:
        assert gateway_request(gateway, "owned")[0] == 200 and calls == ["dispatch"]
        assert gateway_request(gateway, "owned")[0] == 409 and calls == ["dispatch"]
    finally:
        gateway.close()


def test_duplicate_authorization_and_expect_cannot_dispatch_or_spend_attempt(tmp_path):
    gateway, calls = counted_gateway(tmp_path)
    body = b'{"session_id":"owned"}'
    try:
        for extra in (b"Authorization: Bearer wrong\r\n", b"Expect: 100-continue\r\n"):
            with raw_gateway(gateway) as client:
                client.sendall(request_headers(gateway, body, extra=extra) + body)
                assert raw_response(client)[0] == 409 and calls == []
        assert gateway_request(gateway, "owned")[0] == 200 and calls == ["dispatch"]
    finally:
        gateway.close()


def test_valid_maximum_frame_and_exact_owned_route_after_header_first(tmp_path):
    gateway, calls = counted_gateway(tmp_path)
    body = b'{"session_id":"owned"}'
    body += b" " * (256 - len(body))
    try:
        with raw_gateway(gateway) as client:
            client.sendall(request_headers(gateway, body))
            assert not select.select([client], [], [], 0.02)[0]
            for part in (body[:5], body[5:20], body[20:]):
                client.sendall(part)
            assert raw_response(client) == (200, {"status": "completed"})
        assert calls == ["dispatch"]
        assert gateway_request(gateway, "owned")[0] == 409 and calls == ["dispatch"]
    finally:
        gateway.close()


def test_idle_stall_releases_capacity_and_a_parallel_valid_client_is_not_blocked(tmp_path):
    gateway, calls = counted_gateway(tmp_path)
    try:
        with raw_gateway(gateway) as stalled:
            stalled.sendall(b"POST /actor HTTP/1.0\r\nX-Stall:")
            assert gateway_request(gateway, "owned")[0] == 200 and calls == ["dispatch"]
            assert select.select([stalled], [], [], 1.5)[0]
            assert stalled.recv(4096) == b""
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            with gateway.server._guard:
                remaining = len(gateway.server._active)
            if not remaining:
                break
            time.sleep(0.001)
        assert not remaining
    finally:
        gateway.close()


def test_disconnect_after_authorized_dispatch_is_recorded_and_never_retried(tmp_path):
    entered, released = threading.Event(), threading.Event()
    calls = []

    def execute():
        calls.append("dispatch")
        entered.set()
        assert released.wait(2)
        return SimpleNamespace(status="completed")

    gateway = conversation_gateway(tmp_path, "owned", execute)
    try:
        with raw_gateway(gateway) as client:
            body = b'{"session_id":"owned"}'
            client.sendall(request_headers(gateway, body) + body)
            assert entered.wait(1)
            client.shutdown(socket.SHUT_RDWR)
        released.set()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and gateway.error is None:
            time.sleep(0.001)
        assert isinstance(gateway.error, OSError) and calls == ["dispatch"]
        assert gateway_request(gateway, "owned")[0] == 409 and calls == ["dispatch"]
    finally:
        released.set()
        gateway.close()
