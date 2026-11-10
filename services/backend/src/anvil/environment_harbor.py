"""Dedicated host-only Harbor lifecycle with actual collection and sealed verifier.

Uses only an explicitly configured local Unix Docker socket and exact cached image.
No build, pull, network, volume deletion, provider credential or cloud operation.
The actor is a declared software script; business tools remain server-owned SQL.
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path
from uuid import uuid4

from anvil.benchmark_compiler import FIXTURE_IMAGE
from anvil.benchmark_qualification import NativeDocker, NativeGateway
from anvil.config import ROOT
from anvil.environment_collect import harbor_collection
from anvil.harbor_worker import child_environment

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


def layout(folder, actor):
    """No task rubric/reference/private source enters the actor projection."""
    task = folder / "task"
    for name in ("environment/actor", "tests", "solution"):
        (task / name).mkdir(parents=True, mode=0o700)
    for name in ("private", "sealed"):
        (folder / name).mkdir(mode=0o700)
    public = task / "environment/actor/context.json"
    public.write_text(json.dumps(actor))
    public.chmod(0o444)
    public.parent.chmod(0o555)

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
        (task / role / "docker-compose.yaml").write_text(
            json.dumps({"services": {"main": service(role)}})
        )
    (task / "instruction.md").write_text(
        "Execute the declared public software tool script through the host mediator. This is not a model benchmark. No private evaluator is available to the actor."
    )
    (task / "tests/test.sh").write_text("#!/bin/sh\nset -eu\ntrue\n")
    (task / "task.toml").write_text(f'''schema_version = "1.4"
[[artifacts]]
source = "/workspace/output.json"
destination = "agent-output.json"
service = "main"
[agent]
timeout_sec = 90.0
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
''')
    return task


def execute(folder, actor, callback, *, host, python):
    """Callback returns actual tool output and trusted collector receipt.

    Native diagnostic reward certifies custody only. Task grading remains the
    unchanged separate Anvil evaluator after trusted capture.
    """
    if os.environ.get("ANVIL_ENVIRONMENT_NATIVE_ENABLED") != "true":
        raise ValueError("Dedicated native worker is disabled")
    folder = Path(folder)
    if not folder.is_absolute() or folder.exists():
        raise ValueError("Fresh canonical native attempt root required")
    folder.mkdir(mode=0o700)
    if folder.resolve() != folder:
        raise ValueError("Aliased native attempt root")
    docker = LocalDocker(folder, host)
    image = json.loads(docker.run(["image", "inspect", FIXTURE_IMAGE]))[0]
    if image["Os"] != "linux" or image["Id"] != FIXTURE_IMAGE.split("@")[1]:
        raise ValueError("Exact cached Linux image required")
    task = layout(folder, actor)
    name = "anvil-bm-" + uuid4().hex[:20]
    collected = {}

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
            output, receipt = callback()
            raw = json.dumps(output, allow_nan=False).encode()
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

    gateway = NativeGateway(folder, gateway_call, socket_root=folder)
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
    (folder / "trial.json").write_text(json.dumps(config))
    env = docker.environment | {
        "PYTHONPATH": str(ROOT / "services/harbor/src"),
        "ANVIL_ENVIRONMENT_DOCKER_COMMAND": json.dumps(docker.command),
        "ANVIL_HARBOR_GATEWAY_SOCKET": gateway.path,
        "ANVIL_HARBOR_GATEWAY_TOKEN": gateway.token,
        "DO_NOT_TRACK": "1",
        "OTEL_SDK_DISABLED": "true",
    }
    try:
        child_process = subprocess.Popen(
            [str(python), "-m", "anvil_harbor.environment", str(folder / "trial.json")],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = child_process.communicate(timeout=180)
        except subprocess.TimeoutExpired:
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
        return {
            "harness": "harbor-0.25.0-host-mediated-components-v1",
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
    finally:
        failures = []
        for session in (name + "__env", name + "__verifier__trial"):
            try:
                ids = (
                    docker.run(
                        ["ps", "-aq", "--filter", "label=com.docker.compose.project=" + session]
                    )
                    .decode()
                    .split()
                )
                for identifier in ids:
                    item = docker.inspect(identifier)
                    if item["Config"]["Labels"].get("com.docker.compose.project") != session:
                        raise RuntimeError("Native cleanup ownership mismatch")
                    docker.run(["stop", "--time", "1", identifier])
            except Exception as exc:
                failures.append({"owned_session": session, "error": type(exc).__name__})
        gateway.close()
        (folder / "cleanup.json").write_text(
            json.dumps({"complete": not failures, "failures": failures, "retained": True})
        )
        if failures:
            raise RuntimeError(
                "Native cleanup incomplete; exact owned sessions retained for reconciliation"
            )
