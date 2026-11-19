"""Dedicated host-only Harbor lifecycle with actual collection and sealed verifier.

Uses only an explicitly configured local Unix Docker socket and exact cached image.
No build, pull, network, volume deletion, provider credential or cloud operation.
The actor is a declared software script; business tools remain server-owned SQL.
"""

import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
import types
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from anvil.benchmark_compiler import FIXTURE_IMAGE
from anvil.benchmark_qualification import NativeDocker, NativeGateway
from anvil.config import ROOT
from anvil.environment_collect import harbor_collection
from anvil.harbor_worker import child_environment, process_identity, recover_child
from anvil.native_image_profile import require_cached_image
from anvil.native_process_identity import process_domain
from anvil.owned_process_group import UnreapedProcessGroup
from anvil.praxis_generic_contract import canonical

PRESTART_GUARD_SHA256 = "32cff9841bb9999a1ea4bcc7b8db94674a73cd71b67e33693fcd7732d5c0a19d"
OPERATOR_PROOF_SHA256 = "ea5f383a678af1db73d8d9458d68fe9cef67b152202ad02c1f550b19d601741d"


def prestart_guards():
    """Load exact shared stdlib-only guards without importing Harbor into the API."""
    path = ROOT / "services/harbor/src/anvil_harbor/prestart.py"
    metadata = path.lstat()
    if (
        path.resolve() != path
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_mode & 0o022
        or metadata.st_nlink != 1
        or metadata.st_size > 1000000
    ):
        raise ValueError("Pinned Harbor pre-start source custody required")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != PRESTART_GUARD_SHA256:
        raise ValueError("Pinned Harbor pre-start source changed")
    module = types.ModuleType("anvil_pinned_harbor_prestart")
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module


def operator_proof_module():
    """Load exact operator source; raw and fixed-operation paths share custody."""
    path = ROOT / "services/harbor/src/anvil_harbor/operator_proof.py"
    metadata = path.lstat()
    if (
        path.resolve() != path
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_mode & 0o022
        or metadata.st_nlink != 1
        or metadata.st_size > 1000000
    ):
        raise ValueError("Pinned operator proof source custody required")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != OPERATOR_PROOF_SHA256:
        raise ValueError("Pinned operator proof source changed")
    module = types.ModuleType("anvil_pinned_Harbor_operator_proof")
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module


def operator_business_bindings(actor, *, business_context=None):
    """Role/cutover proof alone never authorizes business effects."""
    module = operator_proof_module()
    with module.OperatorProofStore(ROOT) as store:
        bindings = store.load(actor)
    module.validate_business_context(business_context)
    if canonical(bindings["request_capsule"]["business_context"]) != canonical(business_context):
        raise ValueError("Harbor caller business context differs from operator qualification")
    if bindings.get("business_operation_authorized") is not True:
        raise ValueError(
            "Harbor business-operation authority unavailable; role proof is insufficient"
        )
    return bindings


def execute_fixed_software(folder, adapter, *, host, python):
    """Source-only typed integration boundary, before all business factories.

    Asset hashes establish custody, not actual runtime qualification. Until a
    reviewed native Trial bridge can validate effective assets and durable
    recovery, there is intentionally no route from here into execute/Trial.
    Do not pass the descriptor through the unchanged raw callback validator.
    """
    from anvil.golden_kyc_harbor import FixedSoftwareAdapter

    if type(adapter) is not FixedSoftwareAdapter:
        raise ValueError("Exact fixed software adapter type required")
    actor, business_context = adapter.validate()
    module = operator_proof_module()
    module.validate_business_context(business_context)
    with module.OperatorProofStore(ROOT) as store:
        binding = store.load_operation(actor, business_context)
    if binding["custody_scope"] != "root_owned_prestart_binding_only":
        raise ValueError("Owned local proof cannot admit actual QA operation")
    if (
        Path(folder).resolve() != Path(folder)
        or not Path(folder).is_absolute()
        or Path(folder).exists()
        or not isinstance(host, str)
        or not host.startswith("unix:///")
        or not Path(python).is_absolute()
    ):
        raise ValueError("Exact existing native host and fresh private attempt required")
    if (
        binding["business_operation_authorized"] is not True
        or binding["dispatch_authorized"] is not True
        or binding["native_trial_qualified"] is not True
    ):
        raise ValueError(
            "Actual Trial operation admission and native asset qualification unavailable"
        )
    with module.OperatorProofStore(ROOT) as store:
        assets = validate_fixed_assets(
            store, binding, folder=Path(folder), host=host, python=Path(python)
        )
    fixed_trial_gate()
    return _fixed_native_bridge(
        Path(folder), adapter, binding, assets, host=host, python=Path(python)
    )


def fixed_trial_gate():
    """Unconditional source-only gate; no environment/caller value opens it."""
    raise ValueError("Fixed native Trial source review and actual admission remain closed")


@contextmanager
def fixed_alarm(seconds, *, cleanup=False):
    """Unix main-thread hard phase bound; no thread-only timeout substitution."""
    if type(seconds) is not int or not 1 <= seconds <= (6 if cleanup else 120):
        raise ValueError("Fixed phase cap required")
    if threading.current_thread() is not threading.main_thread():
        raise ValueError("Fixed native lifecycle requires owned main thread")
    prior_timer = signal.getitimer(signal.ITIMER_REAL)
    if prior_timer[0] and not cleanup:
        raise ValueError("Foreign native alarm cannot be overridden")
    previous = signal.getsignal(signal.SIGALRM)

    def expired(*_):
        raise TimeoutError("Fixed native phase deadline exhausted")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if prior_timer[0]:
            signal.setitimer(signal.ITIMER_REAL, *prior_timer)


def _fixed_native_bridge(folder, adapter, binding, assets, *, host, python):
    fixed_trial_gate()
    limits = assets["validated_limits"]
    bindings = binding | {
        "callback_manifest_sha256": hashlib.sha256(
            canonical(
                {
                    "kind": "fixed_KYC_typed_adapter",
                    "request_sha256": binding["request_sha256"],
                    "dependency_source_sha256s": binding["dependency_source_sha256s"],
                }
            )
        ).hexdigest()
    }
    with fixed_alarm(limits["lifecycle_seconds"]):
        return _execute_lifecycle(
            folder,
            binding["request_capsule"]["actor"],
            None,
            host=host,
            python=python,
            mediated_candidate=False,
            actor_seconds=30,
            bindings=bindings,
            fixed_adapter=adapter,
            fixed_assets=assets,
        )


class FixedDeadline:
    def __init__(self, seconds):
        if type(seconds) is not int or not 1 <= seconds <= 120:
            raise ValueError("Reviewed bounded native deadline required")
        self.ends = time.monotonic() + seconds

    def remaining(self, ceiling):
        remaining = min(ceiling, self.ends - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("Fixed native aggregate deadline exhausted")
        return remaining


def validate_fixed_assets(store, binding, *, folder, host, python):
    """Substantive preflight, no native commands or effect factories."""
    assets = store.operation_assets(binding)
    store.validate_runtime_seal(assets["runtime_seal"])
    limits = store.validate_host_recovery(
        binding,
        assets["host_image_custody"],
        assets["recovery_recipe"],
        folder=folder,
        host=host,
        python=python,
    )
    config = assets["trial_config"]
    name = "anvil-bm-" + binding["operation_nonce"][:20]
    guards = prestart_guards()
    guards.validate_generated_config(config, attempt_root=str(folder), trial_name=name)
    for role in ("environment", "tests"):
        service = assets[role + "_service"]
        guards.validate_effective_service(
            service, role=role, reviewed_service_sha256=binding_profiles(binding, assets)[role]
        )
        allowed = (
            {"/workspace/inputs", "/logs/agent", "/logs/artifacts"}
            if role == "environment"
            else {"/private", "/sealed", "/logs/verifier"}
        )
        targets = set()
        for mount in service.get("volumes", []):
            source = Path(mount["source"])
            target = mount["target"]
            if (
                mount["type"] != "bind"
                or target not in allowed
                or target in targets
                or source.resolve() != source
                or not source.is_relative_to(folder)
                or target in ("/workspace/inputs", "/private", "/sealed")
                and mount.get("read_only") is not True
            ):
                raise ValueError("Fixed role mount custody changed")
            targets.add(target)
        required = {"/workspace/inputs"} if role == "environment" else {"/sealed"}
        if not required <= targets:
            raise ValueError("Fixed actor/separate verifier input mounts missing")
    projection = layout_projection(folder, binding["request_capsule"]["actor"], actor_seconds=30)
    task = assets["task_package"]
    expected = {
        name: hashlib.sha256(content.encode()).hexdigest() for name, content in projection.items()
    }
    if task != {"schema_version": "anvil.fixed-native-task.v1", "files": expected}:
        raise ValueError("Exact public task/config/tool projection changed")
    host_record = assets["host_image_custody"]
    if host_record["image_digest"] != FIXTURE_IMAGE:
        raise ValueError("Role image differs from fixed admitted image")
    child = assets["runtime_seal"]["components"]["harbor"]["interpreter"]
    if child != str(python):
        raise ValueError("Harbor interpreter differs from sealed runtime")
    return assets | {"validated_limits": limits}


def binding_profiles(binding, assets):
    # Already independently bound by the producer; never caller-selected hashes.
    return binding["service_projection_sha256s"]


def verify_fixed_role_snapshots(folder, config, bindings):
    """Both actual framework projections must exist before business dispatch.

    Both config-only preflights precede Trial.run. The actor must also have its
    actual-start projection here; verifier start is later and independently
    enforces equality with its earlier preflight. No asserted profile substitutes
    for actual bytes, and preflight is never postrun qualification.
    """
    trial_dir = folder / "trials" / config["trial_name"]
    guards = prestart_guards()
    for role in ("environment", "tests"):
        document = owned_json(trial_dir, "sme-preflight-compose-" + role + ".json")
        if set(document["services"]) != {"main"}:
            raise ValueError("Actual fixed role service set changed")
        guards.validate_effective_service(
            document["services"]["main"],
            role=role,
            reviewed_service_sha256=bindings["service_projection_sha256s"][role],
        )
        if role == "environment":
            started = owned_json(trial_dir, "sme-compose-environment.json")
            if started != document:
                raise ValueError("Actual actor start differs from paired preflight")


class FixedCaptureStopped(RuntimeError):
    def __init__(self, reason, evidence, *, private_prefixes=None):
        super().__init__(reason)
        self.evidence = evidence
        self._private_prefixes = private_prefixes or {}


def retain_fixed_capture_failure(folder, name, error):
    """Keep bounded raw diagnostics private; public evidence contains hashes only."""
    folder = Path(folder)
    info = folder.lstat()
    if (name not in {"harbor-private.log", "probe-callback.private.log"}
            or folder.resolve() != folder or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ValueError("Private fixed diagnostic custody required")
    parts = error._private_prefixes
    if (set(parts) - {"stdout", "stderr"} or any(type(value) is not bytes for value in parts.values())
            or len(parts.get("stdout", b"")) > 1048576 or len(parts.get("stderr", b"")) > 65536):
        raise ValueError("Bounded fixed diagnostic prefixes required")
    with open(folder / name, "xb", opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
        stream.write(parts.get("stdout", b"") + parts.get("stderr", b""))
        stream.flush()
        os.fsync(stream.fileno())
    private_json(folder / (name + ".capture.json"), error.evidence)


def _fixed_group_owned(child):
    """Prove the isolated Linux session before killing even an exited leader."""
    expected = getattr(child, "_anvil_start_identity", "")
    nonce = getattr(child, "_anvil_group_nonce", "")
    if not expected.startswith("linux:") or not re.fullmatch("[a-f0-9]{64}", nonce):
        raise RuntimeError("Fixed process-group custody unavailable")
    current = process_identity(child.pid)
    if current:
        if (
            current != expected
            or os.getpgid(child.pid) != child.pid
            or os.getsid(child.pid) != child.pid
        ):
            raise RuntimeError("Fixed process-group identity changed")
        return True
    parts = expected.split(":")
    if (
        len(parts) != 4
        or parts[2] != str(child.pid)
        or Path("/proc/sys/kernel/random/boot_id").read_text().strip() != parts[1]
    ):
        raise RuntimeError("Fixed process-group domain changed")
    found = False
    marker = b"ANVIL_FIXED_OPERATION_NONCE=" + nonce.encode() + b"\0"
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            fields = (proc / "stat").read_text().rpartition(") ")[2].split()
            if len(fields) < 20 or fields[2] != str(child.pid) or fields[3] != str(child.pid):
                continue
            with (proc / "environ").open("rb") as stream:
                environment = stream.read(65537)
            if (
                proc.stat().st_uid != os.geteuid()
                or int(fields[19]) < int(parts[3])
                or len(environment) > 65536
                or marker not in environment
            ):
                raise RuntimeError("Fixed descendant custody unconfirmed")
            found = True
        except FileNotFoundError:
            continue
    return found


def _stop_fixed_process(child, *, abnormal=False):
    from anvil.golden_kyc_fixed_process import stop

    lock = getattr(child, "_anvil_stop_lock", None)
    if lock is None:
        stop(child)
    else:
        with lock:
            stop(child)


def _collect_fixed_child(child, *, ends):
    """Concurrent incremental drains; bounded prefixes, no unbounded communicate."""
    values = {"stdout": bytearray(), "stderr": bytearray()}
    counts = {"stdout": 0, "stderr": 0}
    limits = {"stdout": 1048576, "stderr": 65536}

    def stopped(reason):
        return FixedCaptureStopped(
            reason,
            {
                "status": "unknown_no_replay",
                "reason": reason,
                "received_bytes": counts.copy(),
                "retained_prefix_bytes": {k: len(v) for k, v in values.items()},
                "prefix_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in values.items()},
            },
            private_prefixes={key: bytes(value) for key, value in values.items()},
        )

    try:
        with selectors.DefaultSelector() as selector:
            for name, stream in (("stdout", child.stdout), ("stderr", child.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map():
                remaining = ends - time.monotonic()
                if remaining <= 0:
                    raise stopped("callback_deadline")
                for key, _ in selector.select(min(0.1, remaining)):
                    name = key.data
                    room = limits[name] - len(values[name])
                    try:
                        chunk = os.read(key.fileobj.fileno(), min(8192, room + 1))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    counts[name] += len(chunk)
                    values[name].extend(chunk[:room])
                    if counts[name] > limits[name]:
                        raise stopped("callback_stream_limit")
        remaining = ends - time.monotonic()
        if remaining <= 0:
            raise stopped("callback_deadline")
        # Never reap here: retain the group's numeric identity through cleanup,
        # even when the leader exits and descendants close both capture pipes.
        owner = child._anvil_owned_group
        while not owner.exited():
            remaining = ends - time.monotonic()
            if remaining <= 0:
                raise stopped("callback_deadline")
            time.sleep(min(0.01, remaining))
        return bytes(values["stdout"]), bytes(values["stderr"])
    except FixedCaptureStopped:
        try:
            _stop_fixed_process(child, abnormal=True)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            raise stopped("callback_termination_unconfirmed") from None
        raise
    except TimeoutError:
        # SIGALRM's hard phase timeout is also an OSError subclass. Preserve its
        # deadline meaning instead of misreporting it as a broken pipe.
        try:
            _stop_fixed_process(child, abnormal=True)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            raise stopped("callback_termination_unconfirmed") from None
        raise stopped("callback_deadline") from None
    except (OSError, subprocess.TimeoutExpired):
        try:
            _stop_fixed_process(child, abnormal=True)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            raise stopped("callback_termination_unconfirmed") from None
        raise stopped("callback_stream_failure") from None
    finally:
        child.stdout.close()
        child.stderr.close()


def dispatch_fixed_child(request, *, folder, assets, deadline):
    """Only the sealed fixed module; 30-second process-group bound, no retry."""
    fixed_trial_gate()
    actor, context = request.validate()
    module = operator_proof_module()
    with module.OperatorProofStore(ROOT) as store:
        binding = store.load_operation(actor, context)
    runtime = assets["runtime_seal"]["components"]["backend"]
    source_root = str(Path(runtime["source_packages"]["anvil"]).parent)
    sealed_root = Path(source_root).parents[2]
    if (sealed_root / ".env").exists():
        raise ValueError("Fixed worker source root must not load an ambient env file")
    # This parent intent protects the spawn/PID-receipt window independently of
    # the child's effect intent. Neither missing PID nor timeout permits replay.
    private_json(
        folder / "callback-dispatch-intent.json",
        {
            "job_id": binding["job_id"],
            "operation_nonce": binding["operation_nonce"],
            "request_sha256": binding["request_sha256"],
            "no_replay": True,
        },
    )
    program = "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('anvil.golden_kyc_harbor',run_name='__main__')"
    capture_until = time.monotonic() + deadline.remaining(30)
    child = subprocess.Popen(
        [
            runtime["interpreter"],
            "-I",
            "-B",
            "-c",
            program,
            source_root,
            "--fixed-worker",
            binding["job_id"],
            binding["actor_sha256"],
        ],
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(folder),
            "ANVIL_ROOT": str(sealed_root),
            "LANG": "C",
            "ANVIL_ENV": "local",
            "WEB_ORIGIN": "http://127.0.0.1:3202",
            "ANVIL_LOCAL_WEB_PORT": "3202",
            "ANVIL_FIXED_OPERATION_NONCE": binding["operation_nonce"],
            "ANVIL_LIVE_PROVIDERS_ENABLED": "false",
            "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "false",
            "ANVIL_REAL_EMAIL_ENABLED": "false",
            "OTEL_SDK_DISABLED": "true",
            "DO_NOT_TRACK": "1",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    capture_complete = False
    child._anvil_owned_group = UnreapedProcessGroup(child)
    child._anvil_stop_lock = threading.RLock()
    try:
        child._anvil_start_identity = process_identity(child.pid)
        child._anvil_group_nonce = binding["operation_nonce"]
        private_json(
            folder / "callback-process.json",
            {"pid": child.pid, "identity": process_identity(child.pid)},
        )
        stdout, stderr = _collect_fixed_child(child, ends=capture_until)
        capture_complete = True
    except FixedCaptureStopped as stopped:
        private_json(folder / "callback-terminal.json", stopped.evidence)
        raise RuntimeError("Fixed callback capture stopped; no replay") from None
    finally:
        _stop_fixed_process(child, abnormal=not capture_complete)
    (folder / "fixed-callback.private.log").write_bytes(stdout + stderr)
    if child.returncode or len(stdout) > 1048576 or len(stderr) > 65536:
        raise RuntimeError("Fixed callback failed or exceeded output bound; no replay")
    result = json.loads(stdout)
    if set(result) != {"output", "receipt"}:
        raise ValueError("Fixed callback result contract changed")
    return result["output"], result["receipt"]


def stop_fixed_child(folder):
    intent = folder / "callback-dispatch-intent.json"
    process = folder / "callback-process.json"
    if not process.exists():
        if intent.exists():
            raise RuntimeError(
                "Fixed child spawn outcome unknown; operator reconciliation required"
            )
        return
    record = owned_json(folder, "callback-process.json")
    try:
        os.kill(record["pid"], 0)
        if process_identity(record["pid"]) != record["identity"]:
            raise RuntimeError("Fixed child process identity changed")
        os.killpg(record["pid"], signal.SIGKILL)
    except ProcessLookupError:
        pass


ACTOR_PROBE = """import json,os,socket
from pathlib import Path
assert os.geteuid()==10001
assert not any('API_KEY' in k or 'DATABASE' in k or 'DOCKER' in k or 'GATEWAY' in k for k in os.environ)
denied=0
for name in ('/sealed/evidence.json','/private/reference.json','/var/run/docker.sock'):
    try:fd=os.open(name,os.O_RDONLY);os.close(fd)
    except OSError:denied+=1
assert denied==3
assert Path('/workspace/inputs/context.json').is_file()
try:Path('/workspace/inputs/context.json').write_text('changed')
except OSError:readonly=True
else:readonly=False
assert readonly
blocked=0
for host,port in [('169.254.169.254',80),('8.8.8.8',53)]:
    s=socket.socket();s.settimeout(0.2)
    try:s.connect((host,port))
    except OSError:blocked+=1
    finally:s.close()
assert blocked==2
assert Path('/sys/fs/cgroup/pids.max').read_text().strip()=='64'
assert Path('/sys/fs/cgroup/memory.max').read_text().strip()=='536870912'
print(json.dumps({'private_path_attempts':3,'private_path_denials':denied,'egress_attempts':2,'egress_blocked':blocked,'inputs_readonly':readonly,'nonroot':True,'pids_limit':64,'memory_bytes':536870912}))
"""


class LocalDocker(NativeDocker):
    def __init__(self, home, host):
        if not host.startswith("unix:///") or not Path(host[7:]).exists():
            raise ValueError("Explicit existing Unix Docker socket required")
        self.environment = child_environment(home)
        config = home / "empty-docker-config"
        config.mkdir(mode=0o700)
        plugin = Path("/Applications/Docker.app/Contents/Resources/cli-plugins")
        if (plugin / "docker-compose").is_file():
            path = config / "config.json"
            path.write_text(json.dumps({"cliPluginsExtraDirs": [str(plugin)]}))
            path.chmod(0o600)
        binary = shutil.which("docker")
        if binary not in ("/opt/homebrew/bin/docker", "/usr/local/bin/docker", "/usr/bin/docker"):
            raise ValueError("Supported installed Docker executable required")
        self.command = [binary, "--config", str(config), "--host", host]


class DeadlineDocker(LocalDocker):
    def __init__(self, home, host, deadline):
        self.deadline = deadline
        super().__init__(home, host)

    def run(self, args, *, data=None, timeout=30, limit=1048576):
        return super().run(args, data=data, timeout=self.deadline.remaining(timeout), limit=limit)


def private_json(path, value):
    with open(path, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
        stream.write(canonical(value).decode())
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


def stop_owned(docker, name):
    failures = []
    for session in (name + "__env", name + "__verifier__trial"):
        try:
            identifiers = (
                docker.run(
                    [
                        "ps",
                        "-aq",
                        "--no-trunc",
                        "--filter",
                        "label=com.docker.compose.project=" + session,
                    ]
                )
                .decode()
                .split()
            )
            for identifier in identifiers:
                if not re.fullmatch(r"[a-f0-9]{64}", identifier):
                    raise RuntimeError("native_cleanup_identifier_invalid")
                item = docker.inspect(identifier)
                if item["Config"]["Labels"].get("com.docker.compose.project") != session:
                    raise RuntimeError("native_cleanup_ownership_mismatch")
                docker.run(["stop", "--time", "1", identifier])
                if docker.inspect(identifier)["State"]["Running"]:
                    raise RuntimeError("native_cleanup_still_running")
        except Exception as exc:
            failures.append({"owned_session": session, "error": type(exc).__name__})
    return failures


def recover(folder, *, host):
    """Reconcile only exact persisted attempt ownership; never guess or delete."""
    folder = Path(folder)
    stat = folder.lstat()
    if (
        folder.resolve() != folder
        or not folder.is_dir()
        or stat.st_uid != os.getuid()
        or stat.st_mode & 0o077
    ):
        raise RuntimeError("native_recovery_private_root_required")
    ownership = owned_json(folder, "runtime-ownership.json")
    if (
        set(ownership) != {"schema", "trial_name", "docker_host", "process_domain"}
        or ownership["schema"] != "anvil.native-ownership.v2"
        or ownership["docker_host"] != host
        or ownership["process_domain"] != process_domain()
        or not re.fullmatch(r"anvil-bm-[a-f0-9]{20}", ownership["trial_name"])
    ):
        raise RuntimeError("native_recovery_ownership_invalid")
    if (folder / "cleanup.json").exists() and owned_json(folder, "cleanup.json").get(
        "complete"
    ) is True:
        return
    # A death between spawn and PID receipt requires operator reconciliation;
    # absence of a PID is never evidence that no child exists.
    owned_json(folder, "process.json")
    recover_child(folder)
    with tempfile.TemporaryDirectory(prefix="anvil-native-recovery-") as temporary:
        failures = stop_owned(LocalDocker(Path(temporary), host), ownership["trial_name"])
    result = {"complete": not failures, "failures": failures, "retained": True}
    path = folder / "recovery.json"
    # Append receipts rather than overwriting the original cleanup evidence.
    private_json(
        path if not path.exists() else folder / ("recovery-" + uuid4().hex + ".json"), result
    )
    if failures:
        raise RuntimeError("native_cleanup_required")


def layout_projection(folder, actor, *, mediated_candidate=False, actor_seconds=90):
    """No task rubric/reference/private source enters the actor projection."""
    task = folder / "task"
    files = {"environment/actor/context.json": canonical(actor).decode()}

    def service(role):
        return {
            "image": FIXTURE_IMAGE,
            "pull_policy": "never",
            "user": "10001:10001",
            "read_only": True,
            "network_mode": "none",
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "cpus": 1,
            "mem_limit": "512m",
            "memswap_limit": "512m",
            "pids_limit": 64,
            "working_dir": "/workspace" if role == "environment" else "/tmp",
            "command": ["sleep", "infinity"],
            "tmpfs": [
                "/workspace:rw,nosuid,nodev,size=16m,uid=10001,gid=10001",
                "/tmp:rw,nosuid,nodev,noexec,size=16m,uid=10001,gid=10001",
            ]
            + (
                ["/logs/artifacts:rw,nosuid,nodev,noexec,size=16m,uid=10001,gid=10001"]
                if role == "tests"
                else []
            ),
            "environment": {"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
            "volumes": [
                {
                    "type": "bind",
                    "source": str(
                        (task / "environment/actor") if role == "environment" else folder / "sealed"
                    ),
                    "target": "/workspace/inputs" if role == "environment" else "/sealed",
                    "read_only": True,
                }
            ],
        }

    for role in ("environment", "tests"):
        files[role + "/docker-compose.yaml"] = json.dumps({"services": {"main": service(role)}})
    files["instruction.md"] = (
        "Execute the assigned public task through the trusted candidate/tool mediator. "
        "Candidate dispatch and spend are recorded separately by the broker. "
        "The Harbor verifier checks collection custody only, not task quality."
        if mediated_candidate
        else "Execute the declared public software tool script through the host mediator. This is not a model benchmark. No private evaluator is available to the actor."
    )
    files["tests/test.sh"] = "#!/bin/sh\nset -eu\ntrue\n"
    files["task.toml"] = f'''schema_version = "1.4"
[[artifacts]]
source = "/workspace/output.json"
destination = "agent-output.json"
service = "main"
[agent]
timeout_sec = {float(actor_seconds)}
user = "10001:10001"
[environment]
docker_image = "{FIXTURE_IMAGE}"
network_mode = "no-network"
cpus = 1
memory_mb = 512
storage_mb = 1024
[verifier]
timeout_sec = 30.0
environment_mode = "separate"
[verifier.environment]
docker_image = "{FIXTURE_IMAGE}"
network_mode = "no-network"
cpus = 1
memory_mb = 512
storage_mb = 1024
'''
    return files


def layout(folder, actor, *, mediated_candidate=False, actor_seconds=90):
    task = folder / "task"
    for name in ("environment/actor", "tests", "solution"):
        (task / name).mkdir(parents=True, mode=0o700)
    for name in ("private", "sealed"):
        (folder / name).mkdir(mode=0o700)
    for name, content in layout_projection(
        folder, actor, mediated_candidate=mediated_candidate, actor_seconds=actor_seconds
    ).items():
        (task / name).write_text(content)
    public = task / "environment/actor/context.json"
    public.chmod(0o444)
    public.parent.chmod(0o555)
    return task


def execute(
    folder,
    actor,
    callback,
    *,
    host,
    python,
    mediated_candidate=False,
    actor_seconds=90,
    business_context=None,
):
    """Callback returns actual tool output and trusted collector receipt.

    Native diagnostic reward certifies custody only. Task grading remains the
    unchanged separate Anvil evaluator after trusted capture.
    """
    if os.environ.get("ANVIL_ENVIRONMENT_NATIVE_ENABLED") != "true":
        raise ValueError("Dedicated native worker is disabled")
    if (
        type(mediated_candidate) is not bool
        or type(actor_seconds) is not int
        or not 1 <= actor_seconds <= 900
    ):
        raise ValueError("Explicit bounded native actor deadline required")
    bindings = operator_business_bindings(actor, business_context=business_context)
    callback_manifest = bindings["callback_manifest"]
    callback_manifest_sha256 = bindings["callback_manifest_sha256"]
    request_sha256 = bindings["request_sha256"]
    reviewed_service_sha256s = bindings["service_projection_sha256s"]
    guards = prestart_guards()
    guards.validate_service_proof_map(reviewed_service_sha256s)
    guards.validate_callback(
        callback,
        callback_manifest,
        trusted_source_root=str(ROOT / "services/backend/src"),
        request_sha256=request_sha256,
        reviewed_manifest_sha256=callback_manifest_sha256,
    )
    return _execute_lifecycle(
        folder,
        actor,
        callback,
        host=host,
        python=python,
        mediated_candidate=mediated_candidate,
        actor_seconds=actor_seconds,
        bindings=bindings,
    )


def _execute_lifecycle(
    folder,
    actor,
    callback,
    *,
    host,
    python,
    mediated_candidate,
    actor_seconds,
    bindings,
    fixed_adapter=None,
    fixed_assets=None,
    technical_probe_job=None,
):
    if fixed_adapter is not None:
        fixed_trial_gate()
    managed = fixed_adapter is not None or technical_probe_job is not None
    # Admission validation consumes the original lifecycle allowance too. Do not
    # start a second, later deadline after revalidating the installed runtime.
    deadline = (
        FixedDeadline(fixed_assets["validated_limits"]["lifecycle_seconds"])
        if managed else None
    )
    if technical_probe_job is not None:
        from anvil.golden_kyc_probe import validate_assets

        module = operator_proof_module()
        with module.TechnicalProbeStore(ROOT) as store:
            permission = store.load_probe(technical_probe_job)
            actual_assets = validate_assets(store, permission)
            host_record = actual_assets["host_image_custody"]
            if (canonical(actor) != canonical(permission["request_capsule"]["actor"])
                    or canonical(actual_assets) != canonical(fixed_assets)
                    or str(folder) != host_record["folder"] or host != host_record["docker_host"]
                    or str(python) != host_record["python"]
                    or any(bindings.get(key) != permission[key] for key in ("job_id", "plan_sha256", "request_sha256"))):
                raise ValueError("Exact independently stored probe required")
    callback_manifest_sha256 = bindings["callback_manifest_sha256"]
    request_sha256 = bindings["request_sha256"]
    reviewed_service_sha256s = bindings["service_projection_sha256s"]
    guards = prestart_guards()
    folder = Path(folder)
    if not folder.is_absolute() or folder.exists():
        raise ValueError("Fresh canonical native attempt root required")
    domain = process_domain()
    folder.mkdir(mode=0o700)
    if folder.resolve() != folder:
        raise ValueError("Aliased native attempt root")
    private_json(
        folder / "prestart-proof.json",
        {
            "schema_version": "anvil.harbor-prestart-source-proof.v1",
            "guard_source_sha256": PRESTART_GUARD_SHA256,
            "callback_manifest_sha256": callback_manifest_sha256,
            "request_sha256": request_sha256,
            "service_projection_sha256s": reviewed_service_sha256s,
            "runtime_qualification_granted": False,
        },
    )
    docker = DeadlineDocker(folder, host, deadline) if deadline else LocalDocker(folder, host)
    if technical_probe_job is not None and docker.command[0] != fixed_assets["host_image_custody"]["binaries"]["docker"]["path"]:
        raise ValueError("Actual Docker executable differs from measured probe binary")
    image = json.loads(docker.run(["image", "inspect", FIXTURE_IMAGE]))[0]
    require_cached_image(image)
    task = layout(folder, actor, mediated_candidate=mediated_candidate, actor_seconds=actor_seconds)
    name = (
        fixed_assets["trial_config"]["trial_name"]
        if managed
        else "anvil-bm-" + uuid4().hex[:20]
    )
    private_json(
        folder / "runtime-ownership.json",
        {
            "schema": "anvil.native-ownership.v2",
            "trial_name": name,
            "docker_host": host,
            "process_domain": domain,
        },
    )
    collected = {}
    if technical_probe_job is not None:
        collected["_callback_lock"] = threading.RLock()
        collected["_callback_closing"] = threading.Event()

    def gateway_call(route, session, state):
        expected = name + ("__env" if route == "/actor" else "__verifier__trial")
        if route not in ("/actor", "/evaluate") or route in state or session != expected:
            raise ValueError("Native attempt/session mismatch")
        container = docker.container(session)
        info = docker.inspect(container)
        if (
            info["Config"]["Image"] != FIXTURE_IMAGE
            or info["HostConfig"]["NetworkMode"] != "none"
            or not info["HostConfig"]["ReadonlyRootfs"]
            or info["Config"]["User"] != "10001:10001"
        ):
            raise ValueError("Native isolation contract changed")
        if (
            any(
                m["Destination"] in ("/private", "/sealed", "/logs/verifier")
                for m in info["Mounts"]
            )
            and route == "/actor"
        ):
            raise ValueError("Private verifier mount in actor")
        if route == "/actor":
            probe = json.loads(docker.execute(container, ["python", "-c", ACTOR_PROBE]))
            if not managed:
                output, receipt = callback()
            else:
                verify_fixed_role_snapshots(folder, fixed_assets["trial_config"], bindings)
                if technical_probe_job is not None:
                    from anvil.golden_kyc_probe import dispatch

                    output, receipt = dispatch(technical_probe_job, folder=folder, assets=fixed_assets, deadline=deadline,
                                               owner_holder=collected)
                else:
                    output, receipt = dispatch_fixed_child(
                        fixed_adapter.request, folder=folder, assets=fixed_assets, deadline=deadline
                    )
            raw = canonical(output)
            if not 0 < len(raw) <= 65536:
                raise ValueError("Actor output exceeds collector bound")
            program = "import sys; from pathlib import Path; p=Path('/workspace/output.json'); assert not p.exists(); p.write_bytes(sys.stdin.buffer.read(65537))"
            docker.execute(container, ["python", "-c", program], data=raw)
            from fastapi.encoders import jsonable_encoder

            receipt = jsonable_encoder(receipt)
            sealed = json.dumps(
                receipt, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
            if len(sealed) > 8 * 1024 * 1024:
                raise ValueError("Collector receipt exceeds native bound")
            target = folder / "sealed/evidence.json"
            target.write_bytes(sealed)
            target.chmod(0o444)
            target.parent.chmod(0o555)
            collected.update(
                receipt=receipt,
                receipt_bytes_sha256=hashlib.sha256(sealed).hexdigest(),
                actor_output_sha256=hashlib.sha256(raw).hexdigest(),
                actor_probe=probe,
            )
            state[route] = {"container": container}
            return {"status": "completed"}
        actor_container = state["/actor"]["container"]
        docker.run(["stop", "--time", "1", actor_container])
        if docker.inspect(actor_container)["State"]["Running"]:
            raise ValueError("Actor remains active at verification")
        program = "import hashlib; from pathlib import Path; print(hashlib.sha256(Path('/sealed/evidence.json').read_bytes()).hexdigest())"
        actual = (
            docker.execute(container, ["python", "-c", program], workdir="/tmp").decode().strip()
        )
        if actual != collected["receipt_bytes_sha256"]:
            raise ValueError("Separate verifier sealed receipt mismatch")
        state[route] = {"container": container, "receipt_bytes_sha256": actual}
        return {"reward": 1.0}

    # Attempt paths include execution/effect hashes and can exceed AF_UNIX's
    # length limit. The gateway owns a fresh short private directory, never a
    # candidate mount; the existing gateway closes/removes its socket on exit.
    gateway_home = tempfile.TemporaryDirectory(prefix=".anvil-ng-", dir="/tmp")
    try:
        gateway = NativeGateway(folder, gateway_call, socket_root=Path(gateway_home.name).resolve())
    except BaseException:
        gateway_home.cleanup()
        raise
    config = {
        "task": {"path": str(task)},
        "trial_name": name,
        "trials_dir": str(folder / "trials"),
        "agent": {"import_path": "anvil_harbor.sme:SMEAgent"},
        "environment": {
            "import_path": "anvil_harbor.environment:LocalComponentsDocker",
            "delete": False,
        },
        "verifier": {"import_path": "anvil_harbor.sme:SMEVerifier"},
    }
    try:
        guards.validate_generated_config(config, attempt_root=str(folder), trial_name=name)
        if managed and canonical(config) != canonical(fixed_assets["trial_config"]):
            raise ValueError("Generated native config differs from reviewed exact config")
        private_json(folder / "trial.json", config)
    except BaseException:
        # No framework/actor has started, but the gateway already owns a thread
        # and socket. Configuration failure must release them before returning.
        try:
            gateway.close()
        finally:
            gateway_home.cleanup()
        raise
    env = docker.environment | {
        "PYTHONPATH": str(ROOT / "services/harbor/src"),
        "ANVIL_ENVIRONMENT_DOCKER_COMMAND": json.dumps(docker.command),
        "ANVIL_HARBOR_GATEWAY_SOCKET": gateway.path,
        "ANVIL_HARBOR_GATEWAY_TOKEN": gateway.token,
        "DO_NOT_TRACK": "1",
        "OTEL_SDK_DISABLED": "true",
        "ANVIL_HARBOR_GATEWAY_TIMEOUT_SECONDS": str(actor_seconds + 30),
        "ANVIL_HARBOR_ATTEMPT_ROOT": str(folder),
        "ANVIL_HARBOR_TRIAL_CONFIG_SHA256": hashlib.sha256(
            (folder / "trial.json").read_bytes()
        ).hexdigest(),
        "ANVIL_HARBOR_SERVICE_SHA256S": json.dumps(reviewed_service_sha256s),
    }
    if fixed_adapter is not None:
        env["ANVIL_HARBOR_FIXED_CONTEXT"] = json.dumps(
            {
                "job_id": bindings["job_id"],
                "operation_nonce": bindings["operation_nonce"],
                "request_sha256": bindings["request_sha256"],
            }
        )
    if technical_probe_job is not None:
        env.pop("PYTHONPATH", None)
        env.update({"ANVIL_HARBOR_TECHNICAL_PROBE_JOB": technical_probe_job,
                    "ANVIL_ROOT": str(ROOT), "ANVIL_FIXED_OPERATION_NONCE": bindings["operation_nonce"]})
    child_process = None
    result = None
    try:
        child_process = subprocess.Popen(
            [str(python), *(["-I", "-B"] if technical_probe_job is not None else []),
             "-m", "anvil_harbor.environment", str(folder / "trial.json")],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        if technical_probe_job is not None:
            child_process._anvil_owned_group = UnreapedProcessGroup(child_process)
            child_process._anvil_stop_lock = threading.RLock()
            child_process._anvil_start_identity = process_identity(child_process.pid)
            child_process._anvil_group_nonce = bindings["operation_nonce"]
            private_json(folder / "framework-process.json", {"pid": child_process.pid,
                         "identity": child_process._anvil_start_identity, "host_domain": bindings["host_domain"],
                         "started_monotonic_ns": int(deadline.ends * 1000000000) - fixed_assets["validated_limits"]["lifecycle_seconds"] * 1000000000,
                         "deadline_monotonic_ns": int(deadline.ends * 1000000000)})
        private_json(
            folder / "process.json",
            {
                "pid": child_process.pid,
                "identity": process_identity(child_process.pid),
            },
        )
        try:
            if technical_probe_job is not None:
                try:
                    stdout, stderr = _collect_fixed_child(child_process,
                        ends=time.monotonic() + deadline.remaining(actor_seconds + 90))
                finally:
                    _stop_fixed_process(child_process)
            else:
                stdout, stderr = child_process.communicate(
                    timeout=deadline.remaining(actor_seconds + 90) if deadline else actor_seconds + 90
                )
        except FixedCaptureStopped as error:
            retain_fixed_capture_failure(folder, "harbor-private.log", error)
            raise
        except subprocess.TimeoutExpired:
            if technical_probe_job is not None:
                raise RuntimeError("Technical framework termination unconfirmed; no replay") from None
            os.killpg(child_process.pid, signal.SIGTERM)
            try:
                stdout, stderr = child_process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(child_process.pid, signal.SIGKILL)
                stdout, stderr = child_process.communicate(timeout=3)
            (folder / "harbor-private.log").write_bytes(stdout + stderr)
            raise RuntimeError(
                "Native Harbor deadline exceeded; owned process group stopped"
            ) from None
        child = subprocess.CompletedProcess(
            child_process.args, child_process.returncode, stdout, stderr
        )
        (folder / "harbor-private.log").write_bytes(child.stdout + child.stderr)
        if gateway.error or child.returncode or b"ANVIL_ENVIRONMENT_RESULT=" not in child.stdout:
            raise RuntimeError("Native Harbor lifecycle failed; owned diagnostic retained")
        markers = [
            line.removeprefix(b"ANVIL_ENVIRONMENT_RESULT=")
            for line in child.stdout.splitlines()
            if line.startswith(b"ANVIL_ENVIRONMENT_RESULT=")
        ]
        if len(markers) != 1 or len(markers[0]) > 4096:
            raise ValueError("One bounded actual Harbor result required")
        framework = json.loads(markers[0])
        UUID(framework["trial_id"])
        if framework.get("model_performance") is not False or framework.get("provider_calls") != 0:
            raise ValueError("Harbor custody verifier must not claim model performance")
        artifacts = folder / "trials" / name / "artifacts"
        entries = json.loads((artifacts / "manifest.json").read_bytes())
        normalized = []
        for entry in entries:
            if entry["destination"] != "artifacts/agent-output.json":
                continue
            path = artifacts / "agent-output.json"
            raw = path.read_bytes() if path.is_file() and not path.is_symlink() else b""
            normalized.append(
                {
                    "name": "agent-output.json",
                    "status": "collected" if entry["status"] == "ok" else entry["status"],
                    "service": entry.get("service"),
                    "byte_size": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
        checked = harbor_collection(normalized, required=["agent-output.json"])
        if not checked["complete"] or normalized[0]["sha256"] != collected["actor_output_sha256"]:
            raise ValueError("Harbor required artifact collection incomplete or changed")
        result = {
            "harness": "harbor-0.25.0-host-mediated-components-v1",
            "framework_trial_id": framework["trial_id"],
            "owned_trial_name": name,
            "framework_result": framework,
            "mediated_candidate": mediated_candidate,
            "collection": checked,
            "harbor_manifest": entries,
            "trusted_receipt": collected["receipt"],
            "separate_verifier_bytes_sha256": collected["receipt_bytes_sha256"],
            "provider_calls": 0,
            "model_performance": False,
            "diagnostic_reward_purpose": "collection_custody_only",
            "task_score": None,
            "native_container_isolation": True,
            "actor_probe": collected["actor_probe"],
            "business_components_location": "trusted_host_postgres",
            "cloud_provisioned": False,
        }
        return result
    finally:
        if managed:
            seconds = fixed_assets["validated_limits"]["cleanup_seconds"]
            docker.deadline = FixedDeadline(seconds)
            with fixed_alarm(seconds, cleanup=True):
                _cleanup_lifecycle(
                    folder, child_process, docker, name, gateway, gateway_home, result, fixed=True,
                    technical=technical_probe_job is not None, callback_holder=collected
                )
        else:
            _cleanup_lifecycle(folder, child_process, docker, name, gateway, gateway_home, result)


def _cleanup_lifecycle(
    folder, child_process, docker, name, gateway, gateway_home, result, *, fixed=False,
    technical=False, callback_holder=None
):
    def wait_cap():
        return docker.deadline.remaining(3) if fixed else 3

    failures = []
    callback_child = None
    if technical:
        with callback_holder["_callback_lock"]:
            callback_holder["_callback_closing"].set()
            callback_child = callback_holder.get("_owned_callback")
    if child_process is not None and hasattr(child_process, "_anvil_owned_group"):
        try:
            _stop_fixed_process(child_process)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            failures.append({"owned_session": "framework_process", "error": type(error).__name__})
    elif child_process is not None and child_process.poll() is None:
        os.killpg(child_process.pid, signal.SIGTERM)
        try:
            child_process.communicate(timeout=wait_cap())
        except subprocess.TimeoutExpired:
            os.killpg(child_process.pid, signal.SIGKILL)
            child_process.communicate(timeout=wait_cap())
    if fixed:
        try:
            if technical:
                if callback_child is not None:
                    _stop_fixed_process(callback_child)
                elif (folder / "callback-dispatch-intent.json").exists():
                    raise RuntimeError("Probe child spawn custody unknown; reconciliation required")
            else:
                stop_fixed_child(folder)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            failures.append({"owned_session": "fixed_callback", "error": type(error).__name__})
    failures.extend(stop_owned(docker, name))
    gateway.close()
    gateway_home.cleanup()
    private_json(
        folder / "cleanup.json", {"complete": not failures, "failures": failures, "retained": True}
    )
    if result is not None:
        result["cleanup"] = {"complete": not failures, "retained": True}
    if failures:
        raise RuntimeError(
            "Native cleanup incomplete; exact owned sessions retained for reconciliation"
        )
