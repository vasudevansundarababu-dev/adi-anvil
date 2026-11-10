"""Host-only tool mediation; no provider key or private evaluator input is accepted."""

import json
import os
import select
import stat
import threading
import time
from pathlib import Path

from anvil.benchmark_bundle import canonical_path
from anvil.benchmark_qualification import NativeGateway
from anvil.import_sandbox import schema_check
from anvil.task_parser import json_value


class ArtifactTools:
    def __init__(self, root, outputs, *, stdio=None):
        self.root = Path(root)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("Owned private output directory required")
        self.outputs = dict(outputs)
        if (
            not self.outputs
            or any(
                canonical_path(p) != p or type(n) is not int or not 1 <= n <= 16 * 1024 * 1024
                for p, n in self.outputs.items()
            )
            or sum(self.outputs.values()) > 16 * 1024 * 1024
        ):
            raise ValueError("Declared bounded outputs required")
        self.stdio = stdio

    def call(self, name, arguments, *, timeout):
        if name != "write_artifact":
            if self.stdio is None:
                raise ValueError("No reviewed stdio tool")
            return self.stdio.call(name, arguments, timeout=timeout)
        if set(arguments) != {"path", "text"} or type(arguments["text"]) is not str:
            raise ValueError("Invalid output request")
        path = canonical_path(arguments["path"])
        data = arguments["text"].encode()
        if path not in self.outputs or len(data) > self.outputs[path]:
            raise ValueError("Undeclared or oversized output")
        parts = path.split("/")
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
                )
                os.close(descriptor)
                descriptor = child
            target = os.open(
                parts[-1],
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=descriptor,
            )
            with os.fdopen(target, "wb") as stream:
                stream.write(data)
        finally:
            os.close(descriptor)
        return {"path": path, "byte_size": len(data)}


class StdioConnection:
    """Wrap only a trusted host-owned sandbox exec pipe; never starts imported code."""

    def __init__(self, process, tools, *, stop_owned):
        self.process, self.tools, self.stop_owned = process, {t.name: t for t in tools}, stop_owned
        self.counter, self.closed, self.ready = 0, False, False
        os.set_blocking(process.stdin.fileno(), False)
        self.lock = threading.Lock()

    def _write(self, raw, deadline):
        offset = 0
        while offset < len(raw):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [self.process.stdin], [], remaining)[1]:
                raise TimeoutError()
            try:
                offset += os.write(self.process.stdin.fileno(), raw[offset:])
            except BlockingIOError:
                continue

    def rpc(self, method, params, *, timeout):
        with self.lock:
            if self.closed or not 0 < timeout <= 60:
                raise ValueError("Stdio session is terminal or timeout outside bounds")
            self.counter += 1
            raw = (
                json.dumps(
                    {"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params},
                    allow_nan=False,
                ).encode()
                + b"\n"
            )
            if len(raw) > 65536:
                raise ValueError("Stdio request bound")
            try:
                deadline = time.monotonic() + timeout
                self._write(raw, deadline)
                data = bytearray()
                while b"\n" not in data:
                    remaining = deadline - time.monotonic()
                    if (
                        remaining <= 0
                        or not select.select([self.process.stdout], [], [], remaining)[0]
                    ):
                        raise TimeoutError()
                    chunk = os.read(self.process.stdout.fileno(), min(4096, 65537 - len(data)))
                    if not chunk or len(data) + len(chunk) > 65536:
                        raise ValueError("Stdio response bound")
                    data.extend(chunk)
                value = json_value(data)
                if (
                    not isinstance(value, dict)
                    or value.get("jsonrpc") != "2.0"
                    or type(value.get("id")) is not int
                    or value["id"] != self.counter
                    or set(value) != {"jsonrpc", "id", "result"}
                    or not isinstance(value["result"], dict)
                ):
                    raise ValueError("Stdio response correlation")
                return value["result"]
            except Exception:
                self.closed = True
                self.stop_owned()
                raise

    def initialize(self, *, timeout=5):
        if self.ready or self.closed:
            raise ValueError("Stdio initialization cannot be repeated")
        try:
            value = self.rpc(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "anvil-sme-tools", "version": "1"},
                },
                timeout=timeout,
            )
            if value.get("protocolVersion") != "2025-06-18":
                raise ValueError("Stdio protocol changed")
            self._write(
                b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n',
                time.monotonic() + timeout,
            )
            tools = self.rpc("tools/list", {}, timeout=timeout).get("tools")
            expected = [
                {"name": t.name, "description": t.description, "inputSchema": t.parameters}
                for t in self.tools.values()
            ]
            if tools != expected:
                raise ValueError("Stdio schema changed")
            self.ready = True
        except Exception:
            self.closed = True
            self.stop_owned()
            raise

    def call(self, name, arguments, *, timeout):
        if not self.ready or name not in self.tools:
            raise ValueError("Initialized declared stdio tool required")
        schema_check(arguments, self.tools[name].parameters)
        result = self.rpc("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)
        if result.get("isError") is True:
            raise ValueError("Tool returned an error")
        return result


def conversation_gateway(folder, session_id, execute):
    """Single-use trusted Harbor host request; not candidate-controlled session admission."""
    used = False
    lock = threading.Lock()

    def callback(route, session, state):
        nonlocal used
        with lock:
            if route != "/actor" or session != session_id or used:
                raise ValueError("Owned conversation session required; no retry")
            used = True
        result = execute()
        state["conversation"] = result
        if result.status != "completed":
            raise ValueError("Conversation did not complete; no retry")
        return {"status": "completed"}

    return NativeGateway(folder, callback)
