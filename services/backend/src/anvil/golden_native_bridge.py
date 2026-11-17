"""Private one-attempt scheduler/Harbor bridge; no database or provider secrets.

The configured root must be mounted ONLY into scheduler and native coordinator.
Actor and verifier containers receive neither this directory nor Docker access.
Claimed requests are never replayed after restart or ambiguous completion.
"""

import hashlib
import json
import os
import re
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from contextlib import closing, contextmanager
from http.client import HTTPConnection
from pathlib import Path
from uuid import UUID, uuid4

from anvil.benchmark_qualification import NativeGateway
from anvil.environment_harbor import owned_json, private_json
from anvil.praxis_generic_contract import canonical, digest


def private_root(value):
    root = Path(value)
    info = root.lstat()
    if (
        not root.is_absolute()
        or root.resolve() != root
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("Existing canonical owner-only native bridge root required")
    return root


def publish(path, value):
    """Publish fully fsynced bytes once; readers never observe partial JSON."""
    temporary = path.parent / (".pending-" + uuid4().hex)
    private_json(temporary, value)
    try:
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink()


def heartbeat(attempt, subject, sequence):
    temporary = attempt / (".heartbeat-" + uuid4().hex)
    private_json(
        temporary, {"binding_sha256": subject, "sequence": sequence, "sent_at": time.time()}
    )
    os.replace(temporary, attempt / "heartbeat.json")


def coordinator_alive(attempt, subject):
    try:
        if (attempt / "failed.json").exists():
            return False
        value = owned_json(attempt, "heartbeat.json")
        return (
            set(value) == {"binding_sha256", "sequence", "sent_at"}
            and value["binding_sha256"] == subject
            and type(value["sequence"]) is int
            and value["sequence"] >= 0
            and type(value["sent_at"]) in (int, float)
            and 0 <= time.time() - value["sent_at"] <= 3
        )
    except (OSError, ValueError, TypeError):
        return False


@contextmanager
def live_attempt(attempt, subject):
    stopped = threading.Event()
    heartbeat(attempt, subject, 0)

    def pulse():
        sequence = 1
        while not stopped.wait(0.5):
            heartbeat(attempt, subject, sequence)
            sequence += 1

    pulser = threading.Thread(target=pulse, daemon=True)
    pulser.start()
    try:
        yield
    finally:
        stopped.set()
        pulser.join(timeout=2)


def validate_binding(binding, public_actor):
    required = {
        "project_id",
        "job_id",
        "plan_id",
        "lease_sha256",
        "trial_id",
        "generation",
        "input_sha256",
    }
    if (
        not isinstance(binding, dict)
        or set(binding) != required
        or len(canonical(binding)) > 2048
        or len(canonical(public_actor)) > 49152
        or binding.get("input_sha256") != digest(public_actor)
        or type(binding.get("generation")) is not int
        or binding["generation"] < 0
    ):
        raise ValueError("Exact bounded native attempt binding required")
    for key in ("project_id", "job_id", "plan_id", "trial_id"):
        UUID(binding[key])
    for key in ("lease_sha256", "input_sha256"):
        if type(binding[key]) is not str or re.fullmatch(r"[a-f0-9]{64}", binding[key]) is None:
            raise ValueError("Exact native attempt hash required")


def validate_framework(value):
    """Custody evidence never substitutes for broker spend or task scoring."""
    UUID(value["framework_trial_id"])
    if (
        value.get("harness") != "harbor-0.25.0-host-mediated-components-v1"
        or value.get("mediated_candidate") is not True
        or value.get("native_container_isolation") is not True
        or value.get("cleanup") != {"complete": True, "retained": True}
        or value.get("diagnostic_reward_purpose") != "collection_custody_only"
        or value.get("model_performance") is not False
        or value.get("provider_calls") != 0
        or value.get("collection", {}).get("complete") is not True
        or value.get("framework_result", {}).get("trial_id") != value["framework_trial_id"]
    ):
        raise ValueError("Actual isolated Harbor collection and cleanup required")
    sealed = json.dumps(
        value["trusted_receipt"], sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    if value.get("separate_verifier_bytes_sha256") != hashlib.sha256(sealed).hexdigest():
        raise ValueError("Separate verifier must attest exact collector receipt bytes")
    return value


def submit(root, binding, public_actor, callback, *, seconds):
    """Run callback only inside a real Harbor actor invocation, once at most."""
    root = private_root(root)
    if type(seconds) is not int or not 1 <= seconds <= 900:
        raise ValueError("Bounded native episode deadline required")
    # Explicit allowlist prevents leaking lease capabilities, credentials or
    # application-private state through an overbroad worker object.
    validate_binding(binding, public_actor)
    attempt = root / uuid4().hex
    attempt.mkdir(mode=0o700)
    subject = digest(binding)
    done = threading.Event()
    deadline = time.time() + seconds + 90
    result = {}

    def receive(route, session, state):
        if session != subject or time.time() >= deadline or route in state:
            raise ValueError("Native attempt expired, mismatched or replayed")
        if route == "/actor" and not state:
            # Persist consumption before any model/tool effect. A crash keeps
            # the attempt consumed; neither process may replay it.
            private_json(attempt / "actor-started.json", {"binding_sha256": subject})
            state[route] = {"started": True}
            output, receipt = callback(lambda: coordinator_alive(attempt, subject))
            value = {"output": output, "receipt": receipt}
            if len(canonical(value)) > 65536:
                raise ValueError("Native callback public result exceeds bound")
            result["callback_sha256"] = digest(value)
            return value
        if route == "/complete" and "/actor" in state:
            sealed = owned_json(attempt, "completion.json")
            if (
                set(sealed) != {"binding_sha256", "callback_sha256", "framework"}
                or sealed["binding_sha256"] != subject
                or sealed["callback_sha256"] != result.get("callback_sha256")
            ):
                raise ValueError("Native completion differs from this attempt")
            framework = validate_framework(sealed["framework"])
            if digest(framework["trusted_receipt"]) != result["receipt_sha256"]:
                raise ValueError("Native collector receipt differs from scheduler capture")
            result["framework"] = framework
            state[route] = {"complete": True}
            done.set()
            return {"status": "recorded"}
        raise ValueError("Native route or phase denied")

    original = callback

    # Avoid recursive closure rebinding when recording the trusted receipt.
    def recorded_callback(guard):
        if not guard():
            raise RuntimeError("native_coordinator_liveness_missing")
        output, receipt = original(guard)
        result["receipt_sha256"] = digest(receipt)
        return output, receipt

    callback = recorded_callback
    gateway = NativeGateway(attempt, receive, socket_root=root)
    try:
        publish(
            attempt / "request.json",
            {
                "schema_version": "anvil.native-bridge-request.v1",
                "binding": binding,
                "binding_sha256": subject,
                "public_actor": public_actor,
                "gateway_socket": gateway.path,
                "gateway_token": gateway.token,
                "deadline": deadline,
                "actor_seconds": seconds,
            },
        )
        while not done.wait(0.1):
            if (
                gateway.error
                or time.time() >= deadline
                or (attempt / "failed.json").exists()
                or (
                    (attempt / "actor-started.json").exists()
                    and not coordinator_alive(attempt, subject)
                )
            ):
                raise RuntimeError("native_attempt_failed_or_expired_no_retry")
        # The handler sets done before writing its HTTP response. Wait for the
        # coordinator's post-response acknowledgement before closing the socket.
        while not (attempt / "acknowledged.json").exists():
            if gateway.error or time.time() >= deadline:
                raise RuntimeError("native_completion_acknowledgement_missing_no_retry")
            time.sleep(0.01)
        if owned_json(attempt, "acknowledged.json") != {
            "binding_sha256": subject,
            "framework_sha256": digest(result["framework"]),
        }:
            raise RuntimeError("native_completion_acknowledgement_changed")
        if gateway.error:
            raise RuntimeError("native_attempt_failed_no_retry")
        return result["framework"]
    finally:
        gateway.close()


def rpc(request, route):
    """Fixed local socket only; no URL, arbitrary body or retry surface."""

    class UnixConnection(HTTPConnection):
        def __init__(self, path):
            super().__init__("localhost")
            self.path = path

        def connect(self):
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect(self.path)

    with closing(UnixConnection(request["gateway_socket"])) as client:
        client.timeout = max(1, min(990, request["deadline"] - time.time()))
        client.request(
            "POST",
            route,
            json.dumps({"session_id": request["binding_sha256"]}),
            {
                "Authorization": "Bearer " + request["gateway_token"],
                "Content-Type": "application/json",
            },
        )
        response = client.getresponse()
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            raise RuntimeError("native_bridge_denied_no_retry")
        return json.loads(raw)


def process_one(root, work_root, *, host, python, execute=None, attempt_id=None):
    """Coordinator has Docker only; it cannot import or connect to a SQL role."""
    root, work_root = private_root(root), private_root(work_root)
    if execute is None:
        from anvil.environment_harbor import execute
    if attempt_id is not None and not re.fullmatch(r"[a-f0-9]{32}", attempt_id):
        raise ValueError("Exact native attempt ID required")
    for attempt in [root / attempt_id] if attempt_id is not None else sorted(root.iterdir()):
        if not re.fullmatch(r"[a-f0-9]{32}", attempt.name):
            continue
        private_root(attempt)
        pending, claimed = attempt / "request.json", attempt / "claimed.json"
        if not pending.exists() or claimed.exists():
            continue
        # Exclusive link wins once; a death before unlink still leaves claimed
        # and is retained for operator reconciliation, never another dispatch.
        try:
            os.link(pending, claimed, follow_symlinks=False)
        except FileExistsError:
            continue
        pending.unlink()
        request = owned_json(attempt, "claimed.json")
        validate_binding(request["binding"], request["public_actor"])
        expected = {
            "schema_version",
            "binding",
            "binding_sha256",
            "public_actor",
            "gateway_socket",
            "gateway_token",
            "deadline",
            "actor_seconds",
        }
        socket_path = Path(request["gateway_socket"])
        if (
            set(request) != expected
            or request["schema_version"] != "anvil.native-bridge-request.v1"
            or digest(request["binding"]) != request["binding_sha256"]
            or socket_path.parent.parent != root
            or socket_path.name != "gateway.sock"
            or not re.fullmatch(r"[a-f0-9]{64}", request["gateway_token"])
            or type(request["actor_seconds"]) is not int
            or not 1 <= request["actor_seconds"] <= 900
            or type(request["deadline"]) not in (int, float)
            or not 0 < request["deadline"] - time.time() <= 990
        ):
            raise ValueError("Native request descriptor invalid or expired")
        private_root(socket_path.parent)
        info = socket_path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError("Private owned native socket required")
        callback_result = {}

        def actor():
            value = rpc(request, "/actor")
            if set(value) != {"output", "receipt"}:
                raise ValueError("Exact public actor and collector receipt required")
            callback_result.update(value)
            return value["output"], value["receipt"]

        try:
            with live_attempt(attempt, request["binding_sha256"]):
                framework = execute(
                    work_root / attempt.name,
                    request["public_actor"],
                    actor,
                    host=host,
                    python=python,
                    mediated_candidate=True,
                    actor_seconds=request["actor_seconds"],
                )
                validate_framework(framework)
                completion = {
                    "binding_sha256": request["binding_sha256"],
                    "callback_sha256": digest(callback_result),
                    "framework": framework,
                }
                if len(canonical(completion)) > 65536:
                    raise ValueError("Native completion exceeds bound")
                publish(attempt / "completion.json", completion)
                rpc(request, "/complete")
                publish(
                    attempt / "acknowledged.json",
                    {
                        "binding_sha256": request["binding_sha256"],
                        "framework_sha256": digest(framework),
                    },
                )
        except BaseException:
            publish(
                attempt / "failed.json",
                {"binding_sha256": request["binding_sha256"], "no_replay": True},
            )
            raise
        return {"attempt": attempt.name, "framework_trial_id": framework["framework_trial_id"]}
    return None


def recover_attempt(root, work_root, attempt_id, *, host):
    """Reconcile one crashed child, never restart its SDK or native effect."""
    root, work_root = private_root(root), private_root(work_root)
    if not re.fullmatch(r"[a-f0-9]{32}", attempt_id):
        raise ValueError("Exact native recovery attempt required")
    attempt = private_root(root / attempt_id)
    name = "claimed.json" if (attempt / "claimed.json").exists() else "request.json"
    request = owned_json(attempt, name)
    validate_binding(request["binding"], request["public_actor"])
    failed = {"binding_sha256": request["binding_sha256"], "no_replay": True}
    if not (attempt / "failed.json").exists():
        publish(attempt / "failed.json", failed)
    elif owned_json(attempt, "failed.json") != failed:
        raise ValueError("Native recovery binding changed")
    folder = work_root / attempt_id
    if folder.exists():
        from anvil.environment_harbor import recover

        # Kernel/PID namespace and process birth checks remain mandatory. Missing
        # provenance or a new namespace requires operator reconciliation, not a
        # guessed kill or a replay of the ambiguous request.
        recover(folder, host=host)
        record = owned_json(folder, "process.json")
        from anvil.harbor_worker import process_identity

        if process_identity(record["pid"]) == record["identity"]:
            try:
                os.waitpid(record["pid"], os.WNOHANG)
            except ChildProcessError:
                pass
    result = {
        "binding_sha256": request["binding_sha256"],
        "recovered": True,
        "physical_request_replayed": False,
        "native_attempt_replayed": False,
    }
    publish(attempt / ("supervisor-recovery-" + uuid4().hex + ".json"), result)
    return result


def main():
    """Dedicated coordinator entry point; disabled until the operator qualifies it."""
    if os.environ.get("ANVIL_GOLDEN_NATIVE_COORDINATOR_ENABLED") != "true":
        raise RuntimeError("golden_native_coordinator_disabled")
    if any(
        value and ("DATABASE" in key or key.endswith("API_KEY") or key.endswith("PRIVATE_KEY"))
        for key, value in os.environ.items()
    ):
        raise RuntimeError("native_coordinator_must_not_receive_database_or_provider_secrets")
    root = private_root(os.environ["ANVIL_NATIVE_BRIDGE_ROOT"])
    work = private_root(os.environ["ANVIL_GOLDEN_NATIVE_WORK_ROOT"])
    host = os.environ["ANVIL_HARBOR_DOCKER_HOST"]
    python = os.environ["ANVIL_HARBOR_PYTHON"]
    if len(sys.argv) == 3 and sys.argv[1] == "--once":
        process_one(root, work, host=host, python=python, attempt_id=sys.argv[2])
        return
    if len(sys.argv) != 1:
        raise ValueError("Unsupported native coordinator invocation")
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    while not stopping.is_set():
        pending = [
            p
            for p in sorted(root.iterdir())
            if re.fullmatch(r"[a-f0-9]{32}", p.name)
            and (p / "request.json").exists()
            and not (p / "claimed.json").exists()
            and not (p / "failed.json").exists()
        ]
        if not pending:
            if os.environ.get("ANVIL_CUSTOM_PYTHON_SCORING_ENABLED") == "true":
                from anvil.custom_python_grading import coordinator_once as private_grade

                grading_root = os.environ.get("ANVIL_PRIVATE_PYTHON_GRADING_ROOT")
                if not grading_root:
                    raise RuntimeError("Explicit grader-only Python bridge root required")
                if private_grade(grading_root, host=host) is not None:
                    continue
            if os.environ.get("ANVIL_CUSTOM_PYTHON_ENABLED") == "true":
                from anvil.custom_python_worker import coordinator_once

                custom_root = os.environ.get("ANVIL_CUSTOM_PYTHON_BRIDGE_ROOT")
                if not custom_root:
                    raise RuntimeError("Explicit private custom Python bridge root required")
                if coordinator_once(custom_root, host=host) is not None:
                    continue
            time.sleep(1)
            continue
        attempt = private_root(pending[0])
        child = subprocess.Popen(
            [sys.executable, "-m", "anvil.golden_native_bridge", "--once", attempt.name],
            start_new_session=True,
        )
        # This supervisor retains its Linux PID namespace while a worker child
        # is reconciled. It never respawns a consumed attempt.
        while child.poll() is None and not stopping.wait(0.2):
            pass
        interrupted = child.poll() is None
        if interrupted:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
        code = child.wait()
        if code or interrupted:
            recover_attempt(root, work, attempt.name, host=host)


if __name__ == "__main__":
    main()
