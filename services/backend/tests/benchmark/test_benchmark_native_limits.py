import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from anvil.benchmark_compiler import FIXTURE_IMAGE
from anvil.benchmark_qualification import NativeDocker, StdioTools
from anvil.config import ROOT


@pytest.fixture
def sandbox():
    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Dedicated native opt-in absent; not limits evidence")
    folder = ROOT / ".local/benchmark-native-limits" / uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
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
    try:
        yield docker, container, folder
    finally:
        if docker.inspect(container)["State"]["Running"]:
            docker.run(["stop", "--time", "1", container])
        assert not docker.inspect(container)["State"]["Running"]


def test_actual_cgroup_memory_oom_and_pid_limit(sandbox):
    docker, container, folder = sandbox
    report = json.loads(
        docker.execute(
            container,
            [
                "python",
                "-c",
                """import json,subprocess,time
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
    before = docker.execute(container, ["cat", "/sys/fs/cgroup/memory.events"]).decode()
    with pytest.raises(RuntimeError, match="operation failed"):
        docker.execute(
            container,
            ["python", "-c", "data=[]\nwhile True:data.append(bytearray(8*1024*1024))"],
            timeout=15,
        )
    after = docker.execute(container, ["cat", "/sys/fs/cgroup/memory.events"]).decode()
    previous = dict(line.split() for line in before.splitlines())
    current = dict(line.split() for line in after.splitlines())
    assert int(current["oom_kill"]) > int(previous["oom_kill"])
    (folder / "limits.json").write_text(
        json.dumps({**report, "memory_oom_observed": True, "memory_max": 134217728})
    )


def test_timeout_stops_entire_owned_tree_and_preserves_container(sandbox):
    docker, container, folder = sandbox
    with pytest.raises(RuntimeError, match="process tree stopped after timeout"):
        docker.execute(
            container,
            [
                "python",
                "-c",
                "import subprocess,time;subprocess.Popen(['sleep','60']);time.sleep(60)",
            ],
            timeout=1,
        )
    state = docker.inspect(container)["State"]
    assert not state["Running"] and state["Pid"] == 0
    (folder / "limits.json").write_text(
        json.dumps({"owned_timeout_tree_stopped": True, "retained": True})
    )


def test_stdio_overflow_stops_owned_container(sandbox):
    docker, container, folder = sandbox
    tool = SimpleNamespace(
        command=[
            "python",
            "-c",
            "import sys;sys.stdin.readline();sys.stdout.write('x'*70000);sys.stdout.flush()",
        ],
        tool_timeout_seconds=2,
    )
    with pytest.raises(ValueError, match="response exceeds bound"):
        StdioTools(docker, container, SimpleNamespace(tools=[tool]))
    assert not docker.inspect(container)["State"]["Running"]
    (folder / "limits.json").write_text(
        json.dumps({"oversize_stdio_denied": True, "owned_tree_stopped": True})
    )


def test_stdio_timeout_stops_owned_container(sandbox):
    docker, container, folder = sandbox
    tool = SimpleNamespace(
        command=["python", "-c", "import time;time.sleep(60)"], tool_timeout_seconds=1
    )
    with pytest.raises(RuntimeError, match="tool tree stopped after timeout"):
        StdioTools(docker, container, SimpleNamespace(tools=[tool]))
    assert not docker.inspect(container)["State"]["Running"]
    (folder / "limits.json").write_text(
        json.dumps({"stdio_timeout_denied": True, "owned_tree_stopped": True})
    )
