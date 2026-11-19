"""Fresh SDK custody, authenticated by kernel root peers, never by heartbeat.

Host root and its Docker coordinator are trusted operators. The worker knows
the MAC key: MACs bind attempts and queries, not root authority. SO_PEERCRED
on each actual connected socket supplies that authority across PID namespaces.
"""

import hashlib
import hmac
import json
import os
import re
import socket
import stat
import struct
import tempfile
import threading
import time
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from uuid import uuid4

from anvil.praxis_generic_contract import canonical

PURPOSE = "kyc_worker_collection_only"


def peer(connection, uid, gid):
    if not hasattr(socket, "SO_PEERCRED"):
        raise RuntimeError("Linux kernel peer authentication required")
    pid, actual_uid, actual_gid = struct.unpack("3i", connection.getsockopt(
        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
    if (actual_uid, actual_gid) != (uid, gid):
        raise ValueError("Exact kernel coordinator identity required")
    return pid


def host_identity():
    for name in ("uid_map", "gid_map"):
        lines = [tuple(map(int, line.split())) for line in (Path("/proc/self") / name).read_text().splitlines()]
        if lines != [(0, 0, 4294967295)]:
            raise ValueError("Initial host user namespace identity required")


@contextmanager
def root_peer(connection):
    host_identity()
    peer(connection, 0, 0)
    yield


def signed(value, key):
    return {"body": value, "mac": hmac.new(bytes.fromhex(key), canonical(value), hashlib.sha256).hexdigest()}


def verify(value, key):
    if (set(value) != {"body", "mac"} or type(value["mac"]) is not str
            or not hmac.compare_digest(signed(value["body"], key)["mac"], value["mac"])):
        raise ValueError("Exact guardian message binding required")
    return value["body"]


class GuardianServer:
    """Root-owned, read-only status endpoint; no SQL or dispatch capability."""

    def __init__(self, attempt, request, holder, plan):
        from anvil.benchmark_qualification import NativeGateway
        from anvil.environment_harbor import private_json

        if os.geteuid() != 0 or os.getegid() != 0:
            raise ValueError("Actual root coordinator required")
        host_identity()
        self.request, self.holder, self.plan = request, holder, plan
        from anvil.golden_native_mediated import purpose

        self.purpose = purpose(request)
        self.sequence, self.lock = 0, threading.Lock()
        # Both containers mount this exact private bridge path. Only this
        # status directory is group traversable; ordinary roots stay private.
        self.home = tempfile.TemporaryDirectory(prefix=".sg-", dir=Path(attempt).parent)
        self.gateway = NativeGateway(attempt, self.status, socket_root=Path(self.home.name), peer_guard=self.worker_peer)
        self.gateway.token = request["gateway_token"]
        home = Path(self.gateway.path).parent
        os.chown(home, 0, 10001)
        os.chmod(home, 0o710)
        os.chown(self.home.name, 0, 10001)
        os.chmod(self.home.name, 0o710)
        os.chown(self.gateway.path, 0, 10001)
        os.chmod(self.gateway.path, 0o660)
        body = {"schema_version": "anvil.sdk-guardian-descriptor.v1", "purpose": self.purpose,
                "binding_sha256": request["binding_sha256"], "socket": self.gateway.path,
                "deadline_monotonic": request["original_deadline_monotonic"]}
        self.path = Path(attempt) / "sdk-guardian.json"
        try:
            private_json(self.path, signed(body, request["gateway_token"]))
            os.chown(self.path, 0, 10001)
            os.chmod(self.path, 0o640)
        except BaseException:
            self.close()
            raise

    @contextmanager
    def worker_peer(self, connection):
        peer(connection, 10001, 10001)
        yield

    def status(self, route, session, state):
        match = re.fullmatch(r"/status/([1-9][0-9]{0,3})/([a-f0-9]{32})", route)
        with self.lock:
            if not match or session != self.request["binding_sha256"] or int(match[1]) != self.sequence + 1:
                raise ValueError("Fresh once-only guardian query required")
            self.sequence += 1
            lease = self.holder.get("_sdk_peer_lease")
            if (self.sequence > 4096 or self.holder["_callback_closing"].is_set()
                    or time.monotonic() >= self.request["original_deadline_monotonic"] or lease is None):
                raise ValueError("Active original SDK custody required")
            lease.check()
            self.plan.body()
            lease.check()
            if self.holder["_callback_closing"].is_set():
                raise ValueError("SDK custody closing")
            return signed({"schema_version": "anvil.sdk-guardian-status.v1", "purpose": self.purpose,
                "binding_sha256": session, "sequence": self.sequence, "nonce": match[2], "live": True,
                "deadline_monotonic": self.request["original_deadline_monotonic"]}, self.request["gateway_token"])

    def close(self):
        try:
            self.gateway.close()
        finally:
            self.home.cleanup()


class GuardianClient:
    def __init__(self, attempt, binding, token, deadline, *, purpose=PURPOSE):
        self.path = Path(attempt) / "sdk-guardian.json"
        self.binding, self.token, self.deadline = binding, token, deadline
        self.sequence, self.lock = 0, threading.Lock()
        self.purpose = purpose

    def descriptor(self):
        with os.fdopen(os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or (info.st_uid, info.st_gid) != (0, 10001)
                    or stat.S_IMODE(info.st_mode) != 0o640 or info.st_nlink != 1 or info.st_size > 4096):
                raise ValueError("Root-owned bounded guardian descriptor required")
            raw = stream.read(4097)
        value = json.loads(raw)
        if canonical(value) != raw:
            raise ValueError("Canonical guardian descriptor required")
        body = verify(value, self.token)
        if (set(body) != {"schema_version", "purpose", "binding_sha256", "socket", "deadline_monotonic"}
                or body["schema_version"] != "anvil.sdk-guardian-descriptor.v1" or body["purpose"] != self.purpose
                or body["binding_sha256"] != self.binding or body["deadline_monotonic"] != self.deadline
                or Path(body["socket"]).parent.parent.parent != self.path.parent.parent
                or not re.fullmatch(r"\.sg-[a-z0-9_]+", Path(body["socket"]).parent.parent.name)
                or not re.fullmatch(r"\.bm-gw-[a-z0-9_]+", Path(body["socket"]).parent.name)
                or Path(body["socket"]).name != "gateway.sock"):
            raise ValueError("Exact current guardian attempt required")
        return body

    def check(self):
        with self.lock:
            if time.monotonic() >= self.deadline:
                raise RuntimeError("Original SDK deadline expired")
            body = self.descriptor()
            self.sequence += 1
            nonce = uuid4().hex
            connection = HTTPConnection("localhost", timeout=self.deadline-time.monotonic())
            try:
                connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                connection.sock.settimeout(connection.timeout)
                connection.sock.connect(body["socket"])
                peer(connection.sock, 0, 0)
                connection.request("POST", f"/status/{self.sequence}/{nonce}", canonical({"session_id": self.binding}),
                    {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
                response = connection.getresponse()
                raw = response.read(4097)
                if response.status != 200 or len(raw) > 4096:
                    raise ValueError("Guardian refused current SDK custody")
                actual = verify(json.loads(raw), self.token)
                expected = {"schema_version": "anvil.sdk-guardian-status.v1", "purpose": self.purpose,
                    "binding_sha256": self.binding, "sequence": self.sequence, "nonce": nonce,
                    "live": True, "deadline_monotonic": self.deadline}
                if actual != expected or time.monotonic() >= self.deadline:
                    raise ValueError("Stale or mismatched SDK guardian response")
                return True
            finally:
                connection.close()
