"""Independent host observer for fixed no-model transport controls only.

The target pauses before its installed Python entry. A host-root tracer attaches
to its original kernel PIDFD, then resumes that exact process. Trace only socket
families/connection addresses, never payloads, credentials or model contents.
This proves the stated control scope, not global absence of provider activity.
"""

import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import time
from pathlib import Path

ROOT = Path("/var/lib/anvil-qa-v1/runtime-functional/observer-strace-6.1")
BINARY = ROOT / "extracted/usr/bin/strace"
BINARY_SHA256 = "aebaf212ce84a12208c5fa25f08c892029e6f6949b778da55e071ac145404a1e"


def private(path, raw):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def classify(raw, bridge):
    if len(raw) > 16 * 1024**2:
        raise ValueError("Bounded syscall trace required")
    text = raw.decode("utf-8", "strict")
    inet_sockets = 0
    unix = []
    for line in text.splitlines():
        if "socket(" in line and re.search(r'\bsocket\(AF_UNIX,', line) is None:
            # urllib3 probes IPv6 availability at import. Socket creation is
            # observable, but is not an outbound request. No INET connect is
            # accepted below; the container also has network=none throughout.
            if re.search(r'\bsocket\(AF_INET6?,', line) is None:
                raise ValueError("Unexpected socket family")
            inet_sockets += 1
        if "<... connect resumed>" in line or "sun_path=" in line and "connect(" not in line:
            raise ValueError("Incomplete connection trace")
        if "connect(" not in line:
            continue
        match = re.fullmatch(r'\s*(?:[0-9]+\.[0-9]+\s+)?connect\([0-9]+, \{sa_family=AF_UNIX, sun_path="([^"\\\n]+)"\}, [0-9]+\)\s+=\s+.*', line)
        if match is None:
            raise ValueError("Unrecognized, abstract or incomplete connection trace")
        if match[1] == "/var/run/nscd/socket" and re.search(r'= -1 ENOENT \(No such file or directory\)$', line):
            continue
        unix.append(match[1])
    allowed = [r"/run/docker\.sock", re.escape(str(bridge)) + r"/(?:\.bm-gw-[a-z0-9_]+|\.sg-[a-z0-9_]+/\.bm-gw-[a-z0-9_]+)/gateway\.sock",
               r"/tmp/\.anvil-ng-[a-z0-9_]+/\.bm-gw-[a-z0-9_]+/gateway\.sock"]
    unknown = [path for path in unix if not any(re.fullmatch(pattern, path) for pattern in allowed)]
    if unknown or not unix:
        raise ValueError("Unexpected network family or non-control Unix peer observed")
    return {"internet_socket_events": inet_sockets, "internet_connect_events": 0,
            "unix_connect_events": len(unix), "unknown_unix_peers": 0}


def complete_trace(raw):
    lines = raw.decode("utf-8", "strict").splitlines()
    if not lines or re.fullmatch(r'(?:[0-9]+\.[0-9]+\s+)?\+\+\+ (?:exited with [0-9]+|killed by SIG[A-Z0-9]+(?: \(core dumped\))?) \+\+\+', lines[-1]) is None:
        raise ValueError("Each traced process must have a terminal record")


class NetworkObserver:
    def __init__(self, command, evidence, role, bridge):
        if os.geteuid() != 0 or os.uname().nodename != "anvil-qa-v1":
            raise ValueError("QA host-root observer required")
        info = BINARY.stat()
        if (info.st_uid != 0 or info.st_mode & 0o022 or not stat.S_ISREG(info.st_mode)
                or hashlib.sha256(BINARY.read_bytes()).hexdigest() != BINARY_SHA256):
            raise ValueError("Exact private checksum-pinned observer required")
        self.evidence, self.role, self.bridge = evidence, role, bridge
        self.name = command[command.index("--name") + 1]
        self.tracer = None
        self.descriptor = None
        self.error_stream = None
        self.started = time.time()
        index = command.index("--entrypoint")
        if command[index+1] != "/opt/anvil-runtime/bin/python":
            raise ValueError("Fixed installed control interpreter required")
        gate = 'set -eu; mkfifo -m600 /tmp/forge-observer-start; read -r forge_go < /tmp/forge-observer-start; [ "$forge_go" = go ]; exec "$@"'
        paused = command[:index+1] + ["/bin/sh", command[index+2], "-c", gate,
            "forge-observer-gate", "/opt/anvil-runtime/bin/python", *command[index+3:]]
        self.process = subprocess.Popen(paused, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            cutoff = time.monotonic() + 15
            while time.monotonic() < cutoff:
                result = subprocess.run(["docker", "inspect", self.name], capture_output=True, timeout=2)
                if result.returncode == 0:
                    observed = json.loads(result.stdout)[0]
                    pid = observed["State"]["Pid"]
                    if pid > 1:
                        break
                if self.process.poll() is not None:
                    raise RuntimeError("Owned control exited before observation")
                time.sleep(.05)
            else:
                raise TimeoutError("Original paused control was not observed")
            if observed["Config"]["Image"] != command[index+2] or not observed["State"]["Running"]:
                raise ValueError("Actual original control image required")
            self.pid, self.image = pid, observed["Config"]["Image"]
            actual_command = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0")[:-1]
            if actual_command != [item.encode() for item in paused[index+1:index+2] + paused[index+3:]]:
                raise ValueError("Original fixed pre-entry gate required")
            self.identity = (Path("/proc") / str(pid) / "stat").read_text().rpartition(") ")[2].split()[19]
            self.descriptor = os.pidfd_open(pid, 0)
            signal.pidfd_send_signal(self.descriptor, signal.SIGSTOP)
            self.prefix = evidence / (role + ".syscalls")
            error_path = evidence / (role + ".observer.stderr")
            self.error_stream = os.fdopen(os.open(error_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb")
            env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LD_LIBRARY_PATH": str(ROOT / "extracted/usr/lib/x86_64-linux-gnu") + ":" + str(ROOT / "extracted/lib/x86_64-linux-gnu")}
            self.tracer = subprocess.Popen([str(BINARY), "-ff", "-ttt", "-q", "-e", "trace=socket,connect", "-o", str(self.prefix), "-p", str(pid)],
                env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=self.error_stream)
            while time.monotonic() < cutoff:
                status = (Path("/proc") / str(pid) / "status").read_text()
                tracer = re.search(r"^TracerPid:\s*([0-9]+)$", status, re.M)
                if tracer and int(tracer[1]) == self.tracer.pid:
                    break
                if self.tracer.poll() is not None:
                    raise RuntimeError("Independent observer failed before control entry")
                time.sleep(.02)
            else:
                raise TimeoutError("Original control tracer custody unavailable")
            signal.pidfd_send_signal(self.descriptor, signal.SIGCONT)
            subprocess.run(["docker", "exec", "--user", observed["Config"]["User"], self.name,
                "/bin/sh", "-c", 'printf "go\\n" > /tmp/forge-observer-start'], check=True, capture_output=True, timeout=3)
        except BaseException:
            self.abort()
            raise

    def finish(self):
        if self.process.poll() is None:
            raise ValueError("Observe the original control through its terminal state")
        code = self.tracer.wait(timeout=5)
        self.error_stream.close()
        os.close(self.descriptor)
        self.descriptor = None
        if code or (self.evidence / (self.role + ".observer.stderr")).stat().st_size:
            raise ValueError("Independent observer did not complete cleanly")
        files = sorted(self.evidence.glob(self.role + ".syscalls.*"))
        if not 1 <= len(files) <= 2048:
            raise ValueError("Bounded original process-tree traces required")
        if self.prefix.with_name(self.prefix.name + "." + str(self.pid)) not in files:
            raise ValueError("Original observed process trace required")
        raw = b""
        hashes = {}
        for path in files:
            data = path.read_bytes()
            complete_trace(data)
            raw += data
            if len(raw) > 16 * 1024**2:
                raise ValueError("Bounded process-tree trace bytes required")
            hashes[path.name] = hashlib.sha256(data).hexdigest()
            path.chmod(0o600)
        counters = classify(raw, self.bridge)
        packet = {"schema_version": "anvil.owned-control-network-observation.v1", "scope": "transport_worker_and_sdk_descendants",
            "role": self.role, "container": self.name, "image": self.image, "host_pid": self.pid, "start_ticks": self.identity,
            "observed_from_pre_entry_pause": True, "observer_exit_code": code, "observer_binary_sha256": BINARY_SHA256,
            "observer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "traces": hashes,
            "started_at_unix": self.started, "ended_at_unix": time.time(), **counters,
            "global_actual_model_calls": None, "qualification_granted": False}
        private(self.evidence / (self.role + ".network-observation.json"), json.dumps(packet, sort_keys=True).encode())
        return packet

    def abort(self):
        try:
            if self.process.poll() is None:
                subprocess.run(["docker", "stop", "--time", "1", self.name], capture_output=True, timeout=6, check=True)
                self.process.communicate(timeout=3)
        finally:
            try:
                if self.tracer is not None and self.tracer.poll() is None:
                    self.tracer.terminate()
                    try:
                        self.tracer.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.tracer.kill()
                        self.tracer.wait(timeout=3)
            finally:
                if self.error_stream is not None and not self.error_stream.closed:
                    self.error_stream.close()
                if self.descriptor is not None:
                    os.close(self.descriptor)
                    self.descriptor = None
