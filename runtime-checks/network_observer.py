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
import select
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
        failures, stopped = [], None
        try:
            if self.process.poll() is None:
                try:
                    stopped = subprocess.run(["docker", "stop", "--time", "1", self.name], capture_output=True, timeout=6).returncode
                except (OSError, subprocess.SubprocessError) as error:
                    failures.append(type(error).__name__)
            # A timeout may race the CLI's exit. Retain the original handles
            # even then, rather than losing communicate()'s partial buffers.
            if not (self.evidence / (self.role + ".stdout")).exists():
                try:
                    stdout, stderr = self.process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    stdout, stderr = self.process.communicate(timeout=3)
                private(self.evidence / (self.role + ".partial.stdout"), stdout)
                private(self.evidence / (self.role + ".partial.stderr"), stderr)
                private(self.evidence / (self.role + ".abort.json"), json.dumps({"top_level_stop_exit": stopped, "failures": failures,
                    "framework_cleanup": "unknown_requires_owned_reconciliation", "qualification_granted": False}).encode())
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


class FilteredSDKObserver(NetworkObserver):
    """Pinned launch-time seccomp tracing for the trusted host-PID SDK only.

    Unlike attaching with -p, this installs the socket/connect filter before
    Python exec, avoiding ptrace stops for every dependency-file hash syscall.
    -D preserves the original SDK init PID. No image/mount/cap/env additions.
    Host PIDFDs and every tracee's terminal record establish capture closure;
    a non-child tracer exit code is explicitly unknown, never fabricated zero.
    """

    def __init__(self, command, evidence, role, bridge):
        if os.geteuid() != 0 or os.uname().nodename != "anvil-qa-v1" or role != "sdk":
            raise ValueError("Existing host-root SDK observer only")
        if BINARY.stat().st_uid != 0 or BINARY.stat().st_mode & 0o022 or hashlib.sha256(BINARY.read_bytes()).hexdigest() != BINARY_SHA256:
            raise ValueError("Exact checksum-pinned private observer required")
        index = command.index("--entrypoint")
        if command[index+1] != "/opt/anvil-runtime/bin/python" or command[command.index("--pid")+1] != "host":
            raise ValueError("Fixed host-PID installed SDK required")
        self.evidence, self.role, self.bridge = evidence, role, bridge
        self.name = command[command.index("--name")+1]
        self.started = time.time()
        self.tracer, self.descriptor, self.error_stream, self.tracer_descriptor = None, None, None, None
        self.tracer_owned = False
        self.prefix = evidence / "sdk.syscalls"
        host_prefix = "/proc/1/root" + str(ROOT / "extracted")
        trace_command = ["--library-path", host_prefix + "/usr/lib/x86_64-linux-gnu:" + host_prefix + "/lib/x86_64-linux-gnu",
            host_prefix + "/usr/bin/strace", "-D", "--seccomp-bpf", "-ff", "-ttt", "-q", "-e", "trace=socket,connect",
            "-o", "/proc/1/root" + str(self.prefix), "/opt/anvil-runtime/bin/python", *command[index+3:]]
        launched = command[:index+1] + ["/lib64/ld-linux-x86-64.so.2", command[index+2], *trace_command]
        self.process = subprocess.Popen(launched, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            cutoff = time.monotonic() + 20
            expected = ["/opt/anvil-runtime/bin/python", *command[index+3:]]
            while time.monotonic() < cutoff:
                result = subprocess.run(["docker", "inspect", self.name], capture_output=True, timeout=2)
                if result.returncode == 0:
                    info = json.loads(result.stdout)[0]
                    pid = info["State"]["Pid"]
                    if pid > 1:
                        proc = Path("/proc") / str(pid)
                        actual = proc.joinpath("cmdline").read_bytes().split(b"\0")[:-1]
                        status = proc.joinpath("status").read_text()
                        tracer = re.search(r"^TracerPid:\s*([0-9]+)$", status, re.M)
                        filters = re.search(r"^Seccomp_filters:\s*([0-9]+)$", status, re.M)
                        if actual == [item.encode() for item in expected] and tracer and int(tracer[1]) > 1 and filters and int(filters[1]) >= 2:
                            break
                if self.process.poll() is not None:
                    raise RuntimeError("Filtered SDK exited before original custody was observed")
                time.sleep(.02)
            else:
                raise TimeoutError("Original SDK filtered trace custody unavailable")
            if info["Config"]["Image"] != command[index+2] or not info["State"]["Running"]:
                raise ValueError("Exact original SDK image required")
            self.pid, self.image = pid, info["Config"]["Image"]
            self.identity = proc.joinpath("stat").read_text().rpartition(") ")[2].split()[19]
            self.descriptor = os.pidfd_open(pid, 0)
            self.tracer_pid = int(tracer[1])
            tracer_proc = Path("/proc") / str(self.tracer_pid)
            tracer_identity = tracer_proc.joinpath("stat").read_text().rpartition(") ")[2].split()[19]
            self.tracer_descriptor = os.pidfd_open(self.tracer_pid, 0)
            tracer_argv = tracer_proc.joinpath("cmdline").read_bytes().split(b"\0")[:-1]
            if not any(value == (host_prefix + "/usr/bin/strace").encode() for value in tracer_argv):
                raise ValueError("Actual pinned launch tracer required")
            current_status = proc.joinpath("status").read_text()
            if (proc.joinpath("stat").read_text().rpartition(") ")[2].split()[19] != self.identity
                    or tracer_proc.joinpath("stat").read_text().rpartition(") ")[2].split()[19] != tracer_identity
                    or re.search(r"^TracerPid:\s*([0-9]+)$", current_status, re.M)[1] != str(self.tracer_pid)
                    or proc.joinpath("cmdline").read_bytes().split(b"\0")[:-1] != actual):
                raise ValueError("Original SDK/tracer identity changed during PIDFD acquisition")
            self.tracer_owned = True
            self.filter_count = int(filters[1])
        except BaseException:
            self.abort()
            raise

    def finish(self):
        if self.process.poll() != 0:
            raise ValueError("Original filtered SDK must complete successfully")
        poller = select.poll()
        poller.register(self.tracer_descriptor, select.POLLIN)
        if not poller.poll(5000):
            raise ValueError("Original filtered tracer has not terminated")
        poller = select.poll()
        poller.register(self.descriptor, select.POLLIN)
        if not poller.poll(0):
            raise ValueError("Original SDK PIDFD has not terminated")
        stderr = (self.evidence / "sdk.stderr").read_bytes()
        if re.search(rb"(?:^|\n)strace:", stderr):
            raise ValueError("Filtered observer reported a capture error")
        files = sorted(self.evidence.glob("sdk.syscalls.*"))
        if not 1 <= len(files) <= 2048 or self.prefix.with_name(self.prefix.name + "." + str(self.pid)) not in files:
            raise ValueError("Original filtered process-tree trace required")
        raw, hashes = b"", {}
        for path in files:
            data = path.read_bytes()
            complete_trace(data)
            raw += data
            if len(raw) > 16 * 1024**2:
                raise ValueError("Bounded filtered trace required")
            hashes[path.name] = hashlib.sha256(data).hexdigest()
            path.chmod(0o600)
        counters = classify(raw, self.bridge)
        packet = {"schema_version": "anvil.owned-control-network-observation.v1", "scope": "transport_worker_and_sdk_descendants",
            "role": self.role, "container": self.name, "image": self.image, "host_pid": self.pid, "start_ticks": self.identity,
            "observed_from_pre_entry_pause": False, "observed_before_application_exec": True,
            "observer_mode": "pinned_launch_seccomp", "observer_exit_code": None,
            "observer_completion": "original_sdk_and_tracer_pidfds_exited_all_tracees_terminal", "seccomp_filters": self.filter_count,
            "tracer_pid": self.tracer_pid, "observer_stderr_clean": True,
            "observer_binary_sha256": BINARY_SHA256, "observer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "traces": hashes, "started_at_unix": self.started, "ended_at_unix": time.time(), **counters,
            "global_actual_model_calls": None, "qualification_granted": False}
        private(self.evidence / "sdk.network-observation.json", json.dumps(packet, sort_keys=True).encode())
        os.close(self.tracer_descriptor)
        self.tracer_descriptor = None
        os.close(self.descriptor)
        self.descriptor = None
        return packet

    def abort(self):
        failures = []
        partial = (b"", b"")
        try:
            try:
                super().abort()
            except (OSError, subprocess.SubprocessError) as error:
                failures.append(type(error).__name__)
                if isinstance(error, subprocess.TimeoutExpired):
                    partial = (error.output or b"", error.stderr or b"")
        finally:
            if self.tracer_descriptor is not None:
                try:
                    poller = select.poll()
                    poller.register(self.tracer_descriptor, select.POLLIN)
                    if not poller.poll(0):
                        if not self.tracer_owned:
                            failures.append("tracer_custody_unknown")
                        else:
                            try:
                                signal.pidfd_send_signal(self.tracer_descriptor, signal.SIGTERM)
                                if not poller.poll(3000):
                                    signal.pidfd_send_signal(self.tracer_descriptor, signal.SIGKILL)
                                    if not poller.poll(3000):
                                        failures.append("original_tracer_not_terminal")
                            except ProcessLookupError:
                                if not poller.poll(0):
                                    failures.append("tracer_disappeared_without_terminal_pidfd")
                            except OSError as error:
                                failures.append(type(error).__name__)
                    # A detached tracer can keep pipe FDs open after the CLI
                    # exits. Drain original handles AFTER its bounded cleanup.
                    if not (self.evidence / "sdk.stdout").exists():
                        try:
                            partial = self.process.communicate(timeout=3)
                        except subprocess.TimeoutExpired as error:
                            partial = (error.output or partial[0], error.stderr or partial[1])
                            failures.append("partial_pipe_drain_unknown")
                        for suffix, raw in zip(("stdout", "stderr"), partial):
                            path = self.evidence / ("sdk.partial." + suffix)
                            if not path.exists():
                                private(path, raw)
                    path = self.evidence / "sdk.filtered-abort.json"
                    if not path.exists():
                        private(path, json.dumps({"failures": failures, "framework_cleanup": "unknown_requires_owned_reconciliation",
                            "qualification_granted": False}).encode())
                finally:
                    os.close(self.tracer_descriptor)
                    self.tracer_descriptor = None
