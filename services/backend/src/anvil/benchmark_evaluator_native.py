"""Explicit test-operator adapter for the reviewed fictional evaluator service.

Never imported by the API or ordinary/evaluator SQL coordinator. Preloaded pinned
image only; retained containers, no candidate mounts, socket or database credentials.
"""

import json
import os
from pathlib import Path
from uuid import uuid4

from anvil.benchmark_compiler import FIXTURE_IMAGE
from anvil.benchmark_evaluation import PROGRAM
from anvil.benchmark_evaluator_program import canonical, sha
from anvil.benchmark_qualification import NativeDocker

PROBE = """import json,os,socket
from pathlib import Path
assert os.geteuid()==10001
assert not any('API_KEY' in k or 'DATABASE' in k or 'DOCKER' in k or 'GATEWAY' in k for k in os.environ)
for p in ('/var/run/docker.sock','/private/oracle.json','/workspace/actor-canary','/logs/verifier'):
    assert not Path(p).exists()
try:Path('/service/evaluator.py').write_text('changed')
except OSError:pass
else:raise AssertionError('Writable evaluator')
for host,port in [('169.254.169.254',80),('8.8.8.8',53)]:
    s=socket.socket();s.settimeout(0.2)
    try:s.connect((host,port))
    except OSError:pass
    else:raise AssertionError('Egress allowed')
    finally:s.close()
print(json.dumps({'nonroot_readonly_no_credentials_no_socket_no_actor_no_egress':True}))
"""


def execute_native(job, folder, expected_implementation):
    if (
        os.environ.get("ANVIL_TEST_HARBOR") != "1"
        or sha(PROGRAM.read_bytes()) != expected_implementation
    ):
        raise ValueError("Explicit native scope and current reviewed source required")
    folder = Path(folder)
    if not folder.is_absolute() or folder.exists():
        raise ValueError("Fresh owned service root required")
    folder.mkdir(mode=0o700)
    docker = NativeDocker(folder)
    info = json.loads(docker.run(["image", "inspect", FIXTURE_IMAGE]))[0]
    if info["Os"] != "linux" or FIXTURE_IMAGE.split("@")[1] not in [
        r.split("@")[1] for r in info.get("RepoDigests", [])
    ]:
        raise ValueError("Exact preloaded image absent")
    service = folder / "service"
    service.mkdir(mode=0o700)
    script = service / "evaluator.py"
    script.write_bytes(PROGRAM.read_bytes())
    script.chmod(0o444)
    name = "anvil-t06-eval-" + uuid4().hex[:16]
    container = (
        docker.run(
            [
                "run",
                "--detach",
                "--name",
                name,
                "--pull",
                "never",
                "--network",
                "none",
                "--read-only",
                "--user",
                "10001:10001",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--cpus",
                "1",
                "--memory",
                "256m",
                "--memory-swap",
                "256m",
                "--pids-limit",
                "32",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,noexec,size=16m,uid=10001,gid=10001",
                "--mount",
                f"type=bind,source={service},target=/service,readonly",
                "--env",
                "HOME=/tmp",
                "--env",
                "PYTHONDONTWRITEBYTECODE=1",
                FIXTURE_IMAGE,
                "python",
                "-c",
                "import time; time.sleep(600)",
            ]
        )
        .decode()
        .strip()
    )
    try:
        controls = docker.inspect(container)
        host = controls["HostConfig"]
        if (
            host["NetworkMode"] != "none"
            or not host["ReadonlyRootfs"]
            or controls["Config"]["User"] != "10001:10001"
            or len(controls["Mounts"]) != 1
            or controls["Mounts"][0]["Destination"] != "/service"
        ):
            raise ValueError("Evaluator effective runtime changed")
        probe = json.loads(docker.execute(container, ["python", "-c", PROBE], workdir="/tmp"))
        result = docker.execute(
            container, ["python", "/service/evaluator.py"], data=canonical(job), workdir="/tmp"
        )
        (folder / "isolation.json").write_text(
            json.dumps(
                {
                    "container": container,
                    "probe": probe,
                    "image": FIXTURE_IMAGE,
                    "implementation_sha256": expected_implementation,
                    "report_sha256": sha(result),
                    "no_actor_or_vault_mount": True,
                },
                sort_keys=True,
            )
        )
        return result
    finally:
        docker.run(["stop", "--time", "1", container])
