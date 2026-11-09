"""Opt-in fictional native Harbor conformance; not product execution admission."""

import base64
import errno
import hashlib
import hmac
import json
import os
import select
import shutil
import socket
import stat
import subprocess
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import rfc8785

from anvil.benchmark_bundle import canonical_path
from anvil.benchmark_compiler import FIXTURE_IMAGE, seal_outputs
from anvil.config import ROOT
from anvil.harbor_agents import UnixHTTPServer
from anvil.harbor_worker import child_environment
from anvil.import_sandbox import schema_check


class NativeDocker:
    def __init__(self, home):
        host = os.environ["ANVIL_HARBOR_DOCKER_HOST"]
        if host != "unix://" + str(ROOT / ".local/benchmark-docker/docker.sock"):
            raise ValueError("Explicit dedicated local test daemon required")
        self.environment = child_environment(home)
        config = home / "empty-docker-config"
        config.mkdir(mode=0o700)
        self.command = [
            "sudo",
            "-n",
            "/usr/bin/docker",
            "--config",
            str(config),
            "--host",
            host,
        ]

    def run(self, args, *, data=None, timeout=30, limit=1048576):
        result = subprocess.run(
            [*self.command, *args],
            input=data,
            capture_output=True,
            timeout=timeout,
            env=self.environment,
            check=False,
        )
        if result.returncode or len(result.stdout) > limit:
            raise RuntimeError("Native Docker operation failed: " + args[0])
        return result.stdout

    def container(self, session):
        identifiers = (
            self.run(
                [
                    "ps",
                    "--no-trunc",
                    "--filter",
                    "label=com.docker.compose.project=" + session,
                    "--filter",
                    "label=com.docker.compose.service=main",
                    "--format",
                    "{{.ID}}",
                ]
            )
            .decode()
            .split()
        )
        if len(identifiers) != 1 or len(identifiers[0]) != 64:
            raise ValueError("Exact native session unavailable")
        return identifiers[0]

    def inspect(self, container):
        return json.loads(self.run(["inspect", container]))[0]

    def execute(self, container, args, *, data=None, timeout=20, workdir="/workspace"):
        try:
            return self.run(
                [
                    "exec",
                    "-i",
                    "--user",
                    "10001:10001",
                    "--workdir",
                    workdir,
                    container,
                    *args,
                ],
                data=data,
                timeout=timeout,
                limit=65536,
            )
        except subprocess.TimeoutExpired:
            self.run(["stop", "--time", "1", container])
            raise RuntimeError("Owned native process tree stopped after timeout") from None


class StdioTools:
    def __init__(self, docker, container, task):
        self.docker, self.container, self.task = docker, container, task
        self.process = subprocess.Popen(
            [
                *docker.command,
                "exec",
                "-i",
                "--user",
                "10001:10001",
                "--workdir",
                "/workspace",
                container,
                *task.tools[0].command,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=docker.environment,
        )
        self.counter, self.calls, self.denied = 0, 0, 0
        try:
            self._initialize()
        except BaseException:
            self.close()
            raise

    def _initialize(self):
        initialized = self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "anvil-native", "version": "1"},
            },
        )
        if initialized.get("protocolVersion") != "2025-06-18":
            raise ValueError("Stdio protocol mismatch")
        self.process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        self.process.stdin.flush()
        listed = self.rpc("tools/list", {})
        declared = self.docker.execute(self.container, ["cat", "/workspace/inputs/tools.json"])
        if (
            hashlib.sha256(declared).hexdigest() != self.task.tools[0].schema_sha256
            or listed.get("tools") != json.loads(declared)["tools"]
            or len(listed["tools"]) != 1
            or listed["tools"][0]["name"] != "square"
        ):
            raise ValueError("Stdio declaration mismatch")
        self.schema = listed["tools"][0]["inputSchema"]

    def rpc(self, method, params):
        self.counter += 1
        raw = (
            json.dumps(
                {"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params},
                allow_nan=False,
            ).encode()
            + b"\n"
        )
        if len(raw) > 65536:
            raise ValueError("Tool arguments exceed bound")
        self.process.stdin.write(raw)
        self.process.stdin.flush()
        deadline = time.monotonic() + self.task.tools[0].tool_timeout_seconds
        response = bytearray()
        while b"\n" not in response:
            remaining = deadline - time.monotonic()
            if (
                remaining <= 0
                or not select.select([self.process.stdout], [], [], max(0, remaining))[0]
            ):
                self.docker.run(["stop", "--time", "1", self.container])
                raise RuntimeError("Owned tool tree stopped after timeout")
            chunk = os.read(self.process.stdout.fileno(), min(4096, 65537 - len(response)))
            if not chunk or len(response) + len(chunk) > 65536:
                self.docker.run(["stop", "--time", "1", self.container])
                raise ValueError("Tool response exceeds bound or closed")
            response.extend(chunk)
        value = json.loads(response)
        if (
            value.get("jsonrpc") != "2.0"
            or value.get("id") != self.counter
            or set(value) != {"jsonrpc", "id", "result"}
        ):
            raise ValueError("Stdio response correlation mismatch")
        return value["result"]

    def call(self, name, arguments):
        if name != "square":
            self.denied += 1
            raise ValueError("Undeclared tool denied")
        schema_check(arguments, self.schema)
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError") or len(result.get("content", [])) != 1:
            raise ValueError("Tool calculation failed")
        self.calls += 1
        return int(result["content"][0]["text"])

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.docker.run(["stop", "--time", "1", self.container])
            self.process.kill()
            self.process.wait(timeout=3)
        self.process.stdout.close()


ACTOR_PROBE = """import json,os,socket
from pathlib import Path
assert os.geteuid()==10001
assert not list(Path('/workspace/output').iterdir())
assert json.loads(Path('/workspace/inputs/items.json').read_bytes())['items']
assert Path('/workspace/inputs/tool-server.py').is_file()
assert not any('API_KEY' in key or 'DATABASE' in key or 'GATEWAY' in key for key in os.environ)
denied=0
for path in ('/private/evaluator.py','/private/policy.json','/var/run/docker.sock','/logs/verifier/native-canary'):
    try:fd=os.open(path,os.O_RDONLY);os.close(fd)
    except OSError:denied+=1
assert denied==4
try:
    with open('/workspace/inputs/items.json','r+b'):pass
except OSError:readonly=True
else:readonly=False
assert readonly
for address,port in [('169.254.169.254',80),('8.8.8.8',53)]:
    client=socket.socket();client.settimeout(0.2)
    try:client.connect((address,port))
    except OSError:pass
    else:raise AssertionError('Unexpected egress')
    finally:client.close()
assert Path('/sys/fs/cgroup/pids.max').read_text().strip()=='64'
assert Path('/sys/fs/cgroup/memory.max').read_text().strip()=='2147483648'
assert Path('/sys/fs/cgroup/cpu.max').read_text().strip()=='100000 100000'
print(json.dumps({'denied':denied,'fresh':True,'non_root_readonly_no_egress_cgroups':True}))
"""

WRITE_OUTPUT = """import json,sys
from pathlib import Path
value=json.load(sys.stdin)
Path('/workspace/output/answers.json').write_text(json.dumps(value,allow_nan=False))
Path('/workspace/output/report.md').write_text('Original fictional tool-derived software output. Not model performance.')
"""

EVALUATE = """import json,hashlib,sys
from pathlib import Path
sys.path.insert(0,'/private')
from evaluator import evaluate
assert not Path('/workspace/inputs').exists() and not Path('/var/run/docker.sock').exists()
seal=json.loads(Path('/sealed/seal.json').read_bytes())
for file in seal['files']:
    data=(Path('/sealed')/file['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==file['sha256'] and len(data)==file['byte_size']
path=Path('/sealed/answers.json')
invalid_output=False
try:
    output=json.loads(path.read_bytes()) if path.exists() and path.stat().st_size else {}
    if not isinstance(output,dict):
        invalid_output=True
        output={}
except (ValueError,UnicodeError):
    invalid_output=True
    output={}
rules=json.loads(Path('/private/rules.json').read_bytes())
points=evaluate(rules,output)
assert set(points)=={r['id'] for r in rules} and all(type(v) is int and v in (0,1) for v in points.values())
print(json.dumps({'points':sum(points.values()),'possible_points':len(rules),'criteria':points,'invalid_output':invalid_output}))
"""

CAPTURE_OUTPUT = """import base64,json,os,stat,sys
from pathlib import Path
result={}
for output in json.load(sys.stdin):
    path=Path('/workspace/output')/output['path']
    try:descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except FileNotFoundError:continue
    with os.fdopen(descriptor,'rb') as stream:
        before=os.fstat(stream.fileno())
        assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=output['max_bytes']
        data=stream.read(output['max_bytes']+1)
        after=os.fstat(stream.fileno())
        assert len(data)<=output['max_bytes'] and (before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns)
    result[output['path']]=base64.b64encode(data).decode()
print(json.dumps(result))
"""


def check_container(docker, container, *, actor, compiled):
    info = docker.inspect(container)
    policy = info["HostConfig"]
    if (
        policy["NetworkMode"] != "none"
        or not policy["ReadonlyRootfs"]
        or policy["PidsLimit"] != 64
        or policy["Memory"] != 2147483648
        or info["Config"]["User"] != "10001:10001"
        or "ALL" not in policy["CapDrop"]
        or not any(option.startswith("no-new-privileges") for option in policy["SecurityOpt"])
    ):
        raise ValueError("Effective sandbox policy mismatch")
    digests = json.loads(docker.run(["image", "inspect", info["Image"]]))[0]["RepoDigests"]
    if not any(
        digest.endswith("@" + compiled.bindings["environment"]["oci_manifest_digest"])
        for digest in digests
    ):
        raise ValueError("Effective image changed")
    if actor and any(
        mount["Destination"].startswith(("/private", "/sealed", "/tests", "/logs/verifier"))
        for mount in info["Mounts"]
    ):
        raise ValueError("Private evaluator mount in candidate")
    if not actor and any(mount["Destination"] == "/workspace/inputs" for mount in info["Mounts"]):
        raise ValueError("Actor workspace mounted into evaluator")
    return info


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
    def __init__(self, folder, callback):
        # Unix socket limits apply to the full path, not only the basename.
        self.socket_home = tempfile.TemporaryDirectory(prefix=".bm-gw-", dir=ROOT / ".local")
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


def readable_projection(source, destination):
    destination.mkdir(mode=0o700)
    for path in source.iterdir():
        if not path.is_file() or path.is_symlink():
            raise ValueError("Only sealed regular files can be projected")
        target = destination / path.name
        with path.open("rb") as incoming, target.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, length=65536)
        os.chmod(target, 0o444)
    os.chmod(destination, 0o555)


def public_actor_projection(actor_dir, compiled, task):
    """Expose only the immutable declared actor inputs, independent of host umask."""
    actor_dir = Path(actor_dir)
    if not actor_dir.is_absolute() or actor_dir.resolve() != actor_dir:
        raise ValueError("Canonical owned actor task directory required")
    projection_path = actor_dir / "actor.json"
    metadata = projection_path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
    ):
        raise ValueError("Compiled actor metadata must be an owned regular file")
    projection = json.loads(projection_path.read_bytes())
    if (
        hashlib.sha256(rfc8785.dumps(projection)).hexdigest() != compiled.bindings["actor_sha256"]
        or projection["task_id"] != task.id
    ):
        raise ValueError("Compiled actor projection binding changed")
    expected = {
        task.prompt_path,
        *task.actor_asset_paths,
        *(tool.schema_path for tool in task.tools),
        *(output.schema_ref for output in task.outputs if output.schema_ref is not None),
    }
    declarations = projection["files"]
    if (
        not isinstance(declarations, list)
        or len(declarations) != len(expected)
        or {entry["path"] for entry in declarations} != expected
    ):
        raise ValueError("Declared actor input membership changed")
    prefix = f"runtime_pack/{task.id}/"
    root = actor_dir / "environment/actor/runtime_pack" / task.id
    for ancestor in [root, *root.parents]:
        if ancestor.is_symlink():
            raise ValueError("Actor input paths cannot contain symlinks")
        if ancestor == actor_dir:
            break
    files, directories = [], {root}
    for entry in declarations:
        path = canonical_path(entry["path"])
        if (
            not path.startswith(prefix)
            or entry["visibility"] != "actor"
            or entry["task_id"] != task.id
        ):
            raise ValueError("Only declared task-public inputs may be exposed")
        target = actor_dir / "environment/actor" / path
        for parent in target.parents:
            if not parent.is_dir() or parent.is_symlink():
                raise ValueError("Actor input directories cannot be aliases")
            directories.add(parent)
            if parent == root:
                break
        metadata = target.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or metadata.st_size != entry["byte_size"]
            or hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]
        ):
            raise ValueError("Actor input bytes or custody changed")
        files.append(target)
    actual_files = set()
    for member in root.rglob("*"):
        metadata = member.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            if member not in directories:
                raise ValueError("Undeclared actor input directory")
        elif stat.S_ISREG(metadata.st_mode):
            actual_files.add(member)
        else:
            raise ValueError("Actor inputs cannot include aliases or special files")
    if actual_files != set(files) or any(
        not directory.is_dir() or directory.is_symlink() or directory.stat().st_uid != os.getuid()
        for directory in directories
    ):
        raise ValueError("Actor input tree differs from declared public projection")
    # No permission changes occur until every declaration, path and byte passes.
    for target in files:
        os.chmod(target, 0o444, follow_symlinks=False)
    for directory in sorted(directories, key=lambda value: len(value.parts), reverse=True):
        os.chmod(directory, 0o555, follow_symlinks=False)
    return root


def native_trial(package, compiled, task, private, folder, *, mode, actor_driver=None):
    started_at = time.monotonic()
    if os.environ.get("ANVIL_TEST_HARBOR") != "1" or mode not in {
        "positive",
        "empty",
        "guardrail",
        "offline_conversation",
    }:
        raise ValueError("Explicit local software native scope required")
    if (mode == "offline_conversation") != (actor_driver is not None):
        raise ValueError("An explicit reviewed offline actor driver is required")
    if hashlib.sha256(Path(package).read_bytes()).hexdigest() != compiled.archive_sha256:
        raise ValueError("Native package changed")
    folder, private = Path(folder), Path(private)
    home = folder / "home"
    home.mkdir(mode=0o700)
    docker = NativeDocker(home)
    actor_dir = folder / "task"
    actor_dir.mkdir(mode=0o700)
    with zipfile.ZipFile(package) as archive:
        for entry in archive.infolist():
            if (
                entry.filename.startswith("/")
                or ".." in Path(entry.filename).parts
                or entry.file_size > 50 * 1024 * 1024
            ):
                raise ValueError("Invalid compiled package path")
            target = actor_dir / entry.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as incoming, target.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=65536)
    public_actor_projection(actor_dir, compiled, task)
    for name, key in [("evaluator.py", "implementation_sha256"), ("policy.json", "policy_sha256")]:
        if (
            hashlib.sha256((private / name).read_bytes()).hexdigest()
            != compiled.bindings["evaluator"][key]
        ):
            raise ValueError("Native evaluator binding changed")
    expected = {
        Path(file["path"]).name: file["sha256"] for file in compiled.bindings["private_files"]
    }
    if {path.name for path in private.iterdir()} != set(expected):
        raise ValueError("Task-private file membership changed")
    for name, digest in expected.items():
        if hashlib.sha256((private / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Task-private file digest changed")
    readable_projection(private, folder / "private")
    evaluator = {
        "image": FIXTURE_IMAGE,
        "pull_policy": "never",
        "user": "10001:10001",
        "read_only": True,
        "network_mode": "none",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "cpus": 1,
        "mem_limit": "2048m",
        "memswap_limit": "2048m",
        "pids_limit": 64,
        "tmpfs": [
            "/tmp:rw,nosuid,nodev,noexec,size=32m,uid=10001,gid=10001",
            "/logs/artifacts:rw,nosuid,nodev,noexec,size=16m,uid=10001,gid=10001",
        ],
        "environment": {"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
        "volumes": [
            {
                "type": "bind",
                "source": str((folder / "private").resolve()),
                "target": "/private",
                "read_only": True,
            },
            {
                "type": "bind",
                "source": str((folder / "evaluator-sealed").resolve()),
                "target": "/sealed",
                "read_only": True,
            },
        ],
    }
    (actor_dir / "tests/docker-compose.yaml").write_text(
        json.dumps({"services": {"main": evaluator}})
    )
    name = "anvil-bm-" + uuid4().hex[:20]

    def callback(route, session, state):
        expected = (
            name + "__env"
            if route == "/actor"
            else name + "__verifier__trial"
            if route == "/evaluate"
            else None
        )
        if session != expected or route in state:
            raise ValueError("Native session/fence mismatch")
        container = docker.container(session)
        if route == "/actor":
            check_container(docker, container, actor=True, compiled=compiled)
            probe = json.loads(docker.execute(container, ["python", "-c", ACTOR_PROBE]))
            tools = StdioTools(docker, container, task)
            conversation = None
            try:
                items = json.loads(
                    docker.execute(container, ["cat", "/workspace/inputs/items.json"])
                )["items"]
                output = {}
                if mode == "offline_conversation":
                    conversation = actor_driver(docker, container, task, tools, items)
                    if conversation["status"] != "completed":
                        raise ValueError("Offline candidate conversation did not complete")
                elif mode == "positive":
                    output = {item["id"]: tools.call("square", {"n": item["n"]}) for item in items}
                elif mode == "guardrail":
                    try:
                        tools.call("undeclared", {})
                    except ValueError:
                        pass
                    output = {item["id"]: -1 for item in items}
                if mode not in {"empty", "offline_conversation"}:
                    docker.execute(
                        container, ["python", "-c", WRITE_OUTPUT], data=json.dumps(output).encode()
                    )
            finally:
                tools.close()
            captured = folder / "captured"
            captured.mkdir(mode=0o700)
            snapshot = json.loads(
                docker.execute(
                    container,
                    ["python", "-c", CAPTURE_OUTPUT],
                    data=json.dumps([output.model_dump() for output in task.outputs]).encode(),
                )
            )
            docker.run(["stop", "--time", "1", container])
            declarations = {output.path: output for output in task.outputs}
            for path, payload in snapshot.items():
                if path not in declarations or "/" in path:
                    raise ValueError("Unexpected fixture output path")
                data = base64.b64decode(payload, validate=True)
                if len(data) > declarations[path].max_bytes:
                    raise ValueError("Captured output exceeds declaration")
                with (captured / path).open("xb") as stream:
                    stream.write(data)
            seal = seal_outputs(captured, folder / "sealed", task.outputs)
            # Projection is readable only through the separate evaluator mount; host parent stays0700.
            readable_projection(folder / "sealed", folder / "evaluator-sealed")
            state[route] = {
                "container": container,
                "probe": probe,
                "seal": seal.manifest_sha256,
                "calls": tools.calls,
                "denied": tools.denied,
                "conversation": conversation,
            }
            return {"status": "completed"}
        actor = state["/actor"]
        if docker.inspect(actor["container"])["State"]["Running"]:
            raise ValueError("Candidate still active during evaluation")
        check_container(docker, container, actor=False, compiled=compiled)
        value = json.loads(docker.execute(container, ["python", "-c", EVALUATE], workdir="/tmp"))
        state[route] = {"container": container, **value}
        return {"reward": value["points"] / value["possible_points"]}

    gateway = NativeGateway(folder, callback)
    config = {
        "task": {"path": str(actor_dir)},
        "trial_name": name,
        "trials_dir": str(folder / "trials"),
        "agent": {"import_path": "anvil_harbor.sme:SMEAgent"},
        "environment": {"import_path": "anvil_harbor.sme:SMEDocker", "delete": False},
        "verifier": {"import_path": "anvil_harbor.sme:SMEVerifier"},
    }
    config_path = folder / "trial.json"
    config_path.write_text(json.dumps(config))
    environment = {
        **docker.environment,
        "PYTHONPATH": str(ROOT / "services/harbor/src"),
        "ANVIL_BENCHMARK_DOCKER_COMMAND": json.dumps(docker.command),
        "ANVIL_HARBOR_GATEWAY_SOCKET": gateway.path,
        "ANVIL_HARBOR_GATEWAY_TOKEN": gateway.token,
        "DO_NOT_TRACK": "1",
        "OTEL_SDK_DISABLED": "true",
    }
    try:
        process = subprocess.run(
            [
                str(ROOT / ".local/harbor-venv/bin/python"),
                "-m",
                "anvil_harbor.sme",
                str(config_path),
            ],
            env=environment,
            capture_output=True,
            timeout=240,
            check=False,
        )
        (folder / "harbor.log").write_bytes(process.stdout + process.stderr)
        if gateway.error:
            raise RuntimeError(
                "Native gateway failed: " + type(gateway.error).__name__
            ) from gateway.error
        if process.returncode or b"ANVIL_SME_RESULT=" not in process.stdout:
            raise RuntimeError(
                "Native Harbor trial failed; inspect owned ignored log: " + str(folder)
            )
    finally:
        for session in (name + "__env", name + "__verifier__trial"):
            owned = (
                docker.run(
                    [
                        "ps",
                        "--no-trunc",
                        "--filter",
                        "label=com.docker.compose.project=" + session,
                        "--format",
                        "{{.ID}}",
                    ]
                )
                .decode()
                .split()
            )
            for container in owned:
                if len(container) != 64:
                    raise ValueError("Invalid owned container identity")
                docker.run(["stop", "--time", "1", container])
        gateway.close()
    actor, evaluation = gateway.result["/actor"], gateway.result["/evaluate"]
    result = {
        "origin": "original_synthetic_software_conformance",
        "binding_sha256": compiled.binding_sha256,
        "harbor_version": "0.25.0",
        "task_id": task.id,
        "mode": mode,
        "compiled_archive_sha256": compiled.archive_sha256,
        "manifest_sha256": compiled.bindings["manifest_sha256"],
        "source_authenticity": "isolated_test_signer_not_product_authority",
        "private_file_bindings": compiled.bindings["private_files"],
        "qualification_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "compiler_source_sha256": hashlib.sha256(
            (ROOT / "services/backend/src/anvil/benchmark_compiler.py").read_bytes()
        ).hexdigest(),
        "adapter_sha256": hashlib.sha256(
            (ROOT / "services/harbor/src/anvil_harbor/sme.py").read_bytes()
        ).hexdigest(),
        "points": evaluation["points"],
        "possible_points": evaluation["possible_points"],
        "candidate_stopped_before_evaluation": True,
        "candidate_container": actor["container"],
        "evaluator_container": evaluation["container"],
        "candidate_mounts_private": False,
        "evaluator_mounts_actor": False,
        "provider_calls": 0,
        "seal_sha256": actor["seal"],
        "tool_calls": actor["calls"],
        "denied_tool_calls": actor["denied"],
        "forbidden_access_attempts_denied": actor["probe"]["denied"],
        "control_checks": {
            "non_root_readonly_no_egress_cgroups": actor["probe"][
                "non_root_readonly_no_egress_cgroups"
            ],
            "fresh_actor": actor["probe"]["fresh"],
        },
    }
    raw = json.dumps(result, sort_keys=True, allow_nan=False).encode()
    if mode == "offline_conversation":
        from anvil.benchmark_atif import project, validate

        result["atif"] = validate(project(actor["conversation"], name), home)
        result["atif_validator"] = "harbor-0.25.0"
        result["duration_ms"] = int((time.monotonic() - started_at) * 1000)
        result["criteria"] = evaluation["criteria"]
        result["invalid_output"] = evaluation["invalid_output"]
        result["conversation"] = actor["conversation"]
        result["provider_calls"] = actor["conversation"]["turn_count"]
        raw = json.dumps(result, sort_keys=True, allow_nan=False).encode()
    (folder / "native-receipt.json").write_bytes(raw)
    return {**result, "native_receipt_sha256": hashlib.sha256(raw).hexdigest()}


def resource_probe(mode, folder):
    if os.environ.get("ANVIL_TEST_HARBOR") != "1" or mode not in {
        "memory_pids",
        "tree_timeout",
        "stdio_overflow",
        "stdio_timeout",
    }:
        raise ValueError("Explicit isolated resource-probe scope required")
    folder = Path(folder)
    folder.mkdir(mode=0o700)
    home = folder / "home"
    home.mkdir(mode=0o700)
    docker = NativeDocker(home)
    container = (
        docker.run(
            [
                "run",
                "--detach",
                "--pull",
                "never",
                "--name",
                "anvil-bm-g4-" + uuid4().hex[:20],
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--pids-limit",
                "16",
                "--memory",
                "128m",
                "--memory-swap",
                "128m",
                "--cpus",
                "1",
                "--user",
                "10001:10001",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,noexec,size=8m,uid=10001,gid=10001",
                "--tmpfs",
                "/workspace:rw,nosuid,nodev,noexec,size=8m,uid=10001,gid=10001",
                "--workdir",
                "/workspace",
                FIXTURE_IMAGE,
                "sleep",
                "infinity",
            ]
        )
        .decode()
        .strip()
    )
    result = {"mode": mode, "container": container, "retained": True}
    try:
        if mode == "memory_pids":
            result.update(
                json.loads(
                    docker.execute(
                        container,
                        [
                            "python",
                            "-c",
                            """import json,subprocess
from pathlib import Path
children=[]
try:
    while len(children)<30:children.append(subprocess.Popen(['sleep','20']))
except BlockingIOError:limited=True
else:limited=False
finally:
    for child in children:child.terminate()
    for child in children:child.wait()
assert limited and len(children)<16
assert Path('/sys/fs/cgroup/memory.max').read_text().strip()=='134217728'
print(json.dumps({'pids_denied':limited,'children_started':len(children)}))
""",
                        ],
                    )
                )
            )
            before = dict(
                line.split()
                for line in docker.execute(container, ["cat", "/sys/fs/cgroup/memory.events"])
                .decode()
                .splitlines()
            )
            try:
                docker.execute(
                    container,
                    ["python", "-c", "data=[]\nwhile True:data.append(bytearray(8*1024*1024))"],
                    timeout=15,
                )
            except RuntimeError:
                after = dict(
                    line.split()
                    for line in docker.execute(container, ["cat", "/sys/fs/cgroup/memory.events"])
                    .decode()
                    .splitlines()
                )
                if int(after["oom_kill"]) <= int(before["oom_kill"]):
                    raise ValueError("Memory OOM control was not observed") from None
            else:
                raise ValueError("Memory exhaustion was not denied")
            result["memory_oom_observed"] = True
        elif mode == "tree_timeout":
            try:
                docker.execute(
                    container,
                    [
                        "python",
                        "-c",
                        "import subprocess,time;subprocess.Popen(['sleep','60']);time.sleep(60)",
                    ],
                    timeout=1,
                )
            except RuntimeError as exc:
                if "process tree stopped after timeout" not in str(exc):
                    raise
            else:
                raise ValueError("Owned tree timeout was not observed")
            result["owned_timeout_tree_stopped"] = True
        else:
            tool = SimpleNamespace(
                command=[
                    "python",
                    "-c",
                    "import sys;sys.stdin.readline();sys.stdout.write('x'*70000);sys.stdout.flush()"
                    if mode == "stdio_overflow"
                    else "import time;time.sleep(60)",
                ],
                tool_timeout_seconds=1,
            )
            try:
                tools = StdioTools(docker, container, SimpleNamespace(tools=[tool]))
            except (ValueError, RuntimeError) as exc:
                expected = (
                    "response exceeds bound"
                    if mode == "stdio_overflow"
                    else "tool tree stopped after timeout"
                )
                if expected not in str(exc):
                    raise
            else:
                tools.close()
                raise ValueError("Stdio bound was not enforced")
            result[mode + "_denied"] = True
    finally:
        if docker.inspect(container)["State"]["Running"]:
            docker.run(["stop", "--time", "1", container])
    state = docker.inspect(container)["State"]
    if state["Running"] or state["Pid"] != 0:
        raise ValueError("Owned resource probe process tree is still running")
    return result
