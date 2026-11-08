"""Real process/pipe/filesystem/Unix tests; only paid provider HTTP is simulated."""

import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager

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
