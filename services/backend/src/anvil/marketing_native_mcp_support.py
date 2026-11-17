"""Unchanged non-HTTP MCP gateway/file/schema helpers; no API config import.

Source-only extraction. Original file ownership, framing, schema and transport
checks remain; this supplies no runtime admission or capability.
"""

import errno
import hmac
import json
import math
import os
import socket
import stat
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from uuid import uuid4

# Installed code root ONLY for stdio PYTHONPATH/default local gateway home.
# It is not a selector for private artifact/data/vault authority.
ROOT = Path(__file__).resolve().parents[4]


class UnixHTTPServer(ThreadingMixIn, HTTPServer):
    address_family = socket.AF_UNIX
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass


class _GatewayServer(UnixHTTPServer):
    framing_seconds = 1.0
    max_connections = 4

    def __init__(self, path, handler):
        self._guard = threading.Lock()
        self._slots = threading.BoundedSemaphore(self.max_connections)
        self._active = {}
        self._closing = False
        super().__init__(path, handler)

    def process_request(self, request, address):
        with self._guard:
            if self._closing or not self._slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            self._active[request] = None
        try:
            super().process_request(request, address)
        except BaseException:
            self.release(request)
            raise

    def release(self, request):
        with self._guard:
            if request in self._active:
                del self._active[request]
                self._slots.release()

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.release(request)

    def framing_complete(self, request):
        with self._guard:
            framing = self._active.get(request)
            if framing is None or time.monotonic() >= framing[1]:
                raise TimeoutError("Native request framing deadline")
            framing[0].cancel()
            self._active[request] = None

    def expire(self, request):
        with self._guard:
            if self._active.get(request) is not None:
                self.interrupt(request)

    def arm_deadline(self, request):
        timer = threading.Timer(self.framing_seconds, self.expire, args=(request,))
        timer.daemon = True
        with self._guard:
            if self._closing or request not in self._active:
                raise ConnectionError("Gateway closing")
            self._active[request] = (timer, time.monotonic() + self.framing_seconds)
            timer.start()
        return timer

    @staticmethod
    def interrupt(request):
        try:
            request.shutdown(socket.SHUT_RDWR)
        except OSError as exc:
            if exc.errno not in (errno.ENOTCONN, errno.EBADF):
                raise

    def interrupt_all(self):
        with self._guard:
            self._closing = True
            for request, framing in self._active.items():
                if framing is not None:
                    framing[0].cancel()
                self.interrupt(request)


class NativeGateway:
    def __init__(self, folder, callback, *, socket_root=None):
        # Unix socket limits apply to the full path, not only the basename.
        parent = Path(socket_root) if socket_root is not None else ROOT / ".local"
        if socket_root is not None:
            info = parent.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or parent.is_symlink()
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
            ):
                raise ValueError("Owned private socket root required")
        self.socket_home = tempfile.TemporaryDirectory(prefix=".bm-gw-", dir=parent)
        os.chmod(self.socket_home.name, 0o700)
        self.path = str(Path(self.socket_home.name) / "gateway.sock")
        self.token = uuid4().hex + uuid4().hex
        self.result, self.error = {}, None
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def handle(self):
                timer = self.server.arm_deadline(self.connection)
                self.connection.settimeout(self.server.framing_seconds)
                try:
                    super().handle()
                except (OSError, ValueError) as exc:
                    gateway.error = exc
                    raise
                finally:
                    timer.cancel()

            def do_POST(self):
                try:
                    lengths = self.headers.get_all("Content-Length", [])
                    if (
                        len(lengths) != 1
                        or not lengths[0].isascii()
                        or not lengths[0].isdecimal()
                        or self.headers.get_all("Transfer-Encoding")
                        or self.headers.get_all("Expect")
                    ):
                        raise ValueError("Ambiguous native request framing")
                    length = int(lengths[0])
                    if not 0 < length <= 256:
                        raise ValueError("Invalid native request")
                    # Finish only this bounded frame so a header-first client can send
                    # its body before rejection; no authorization or dispatch is granted.
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        raise ValueError("Incomplete native request")
                    self.server.framing_complete(self.connection)
                    authorization = self.headers.get_all("Authorization", [])
                    if len(authorization) != 1 or not hmac.compare_digest(
                        authorization[0], "Bearer " + gateway.token
                    ):
                        raise ValueError("Native gateway auth denied")
                    body = json.loads(raw)
                    if set(body) != {"session_id"}:
                        raise ValueError("Invalid native request fields")
                    self.connection.settimeout(1.0)
                    data = json.dumps(
                        callback(self.path, body["session_id"], gateway.result), allow_nan=False
                    ).encode()
                    status = 200
                except Exception as exc:
                    gateway.error = exc
                    data = b'{"error":"native_check_failed_no_retry"}'
                    status = 409
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        try:
            self.server = _GatewayServer(self.path, Handler)
            os.chmod(self.path, 0o600)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        except Exception:
            self.socket_home.cleanup()
            raise

    def close(self):
        try:
            self.server.interrupt_all()
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
        finally:
            self.socket_home.cleanup()


def private_json(path, value):
    with open(path, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
        json.dump(value, stream, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def owned_json(folder, name):
    path = folder / name
    stat = path.lstat()
    if (
        path.is_symlink()
        or not path.is_file()
        or stat.st_uid != os.getuid()
        or stat.st_mode & 0o077
        or stat.st_size > 65536
    ):
        raise RuntimeError("native_recovery_record_invalid")
    return json.loads(path.read_bytes())


def schema_check(value, schema):
    """Deliberately supported JSON-schema subset; unknown keywords fail qualification."""
    allowed = {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "description",
        "title",
    }
    if set(schema) - allowed:
        raise ValueError(
            "Unsupported tool/output schema keyword: " + ",".join(sorted(set(schema) - allowed))
        )
    kind = schema.get("type")
    matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "number": type(value) in (int, float) and math.isfinite(value),
        "boolean": type(value) is bool,
        "null": value is None,
    }
    if kind and not matches.get(kind, False):
        raise ValueError("Tool/output schema type mismatch")
    if (
        "enum" in schema
        and value not in schema["enum"]
        or "const" in schema
        and value != schema["const"]
    ):
        raise ValueError("Tool/output schema value mismatch")
    if isinstance(value, dict):
        if not set(schema.get("required", [])) <= set(value):
            raise ValueError("Required tool/output field missing")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in props:
                schema_check(item, props[key])
            elif extra is False:
                raise ValueError("Unexpected tool/output field")
            elif isinstance(extra, dict):
                schema_check(item, extra)
    if isinstance(value, list):
        for item in value:
            schema_check(item, schema.get("items", {}))
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 100000):
            raise ValueError("Array length outside schema")
    if isinstance(value, str) and (
        len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1048576)
    ):
        raise ValueError("String length outside schema")
    if type(value) in (int, float) and (
        value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf)
    ):
        raise ValueError("Number outside schema")
