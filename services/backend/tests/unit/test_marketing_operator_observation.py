import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from anvil import marketing_native_operator_observation as observation
from anvil.marketing_native_private_records import original_operator_repository
from anvil.marketing_native_world_binding import verify_opening_graph_sources


def packet():
    def endpoint(key, ip):
        return {"NetworkID": "c" * 64, "EndpointID": key, "IPAddress": ip}

    operator = {
        "Id": "a" * 64,
        "Image": "sha256:" + "d" * 64,
        "State": {"Running": True, "Pid": 123},
        "HostConfig": {
            "NetworkMode": "c" * 64,
            "PidMode": "host",
            "CgroupnsMode": "host",
            "ReadonlyRootfs": True,
            "Privileged": False,
            "PortBindings": {},
            "PublishAllPorts": False,
        },
        "NetworkSettings": {"Networks": {"bridge": endpoint("operator", "172.19.0.2")}},
    }
    api = {
        "Id": "b" * 64,
        "State": {"Running": True},
        "NetworkSettings": {
            "Networks": {"bridge": {**endpoint("api", "172.19.0.3"), "Aliases": ["api"]}}
        },
    }
    network = {
        "Id": "c" * 64,
        "Driver": "bridge",
        "Scope": "local",
        "Ingress": False,
        "Containers": {
            name * 64: {"EndpointID": key, "IPv4Address": ip}
            for name, key, ip in [("a", "operator", "172.19.0.2/16"), ("b", "api", "172.19.0.3/16")]
        },
    }
    return {"a" * 64: operator, "b" * 64: api, "c" * 64: network}


@pytest.fixture
def observed(monkeypatch):
    values, calls = packet(), []

    def inspect(kind, identifier, deadline):
        calls.append((kind, identifier, deadline))
        return json.dumps(values[identifier], sort_keys=True).encode()

    monkeypatch.setattr(observation, "_inspect", inspect)

    @contextmanager
    def process(*_):
        yield lambda: ({"device": 4, "inode": 99}, 17)

    monkeypatch.setattr(observation, "_process", process)
    monkeypatch.setattr(observation, "monotonic", lambda: 100)
    monkeypatch.setattr(observation.sys, "platform", "linux")
    monkeypatch.setattr(observation.os, "geteuid", lambda: 0)
    return values, calls


def observe():
    return observation.observe_container_operator_network(
        "a" * 64, "b" * 64, "c" * 64, "sha256:" + "d" * 64, absolute_deadline=200, cleanup_seconds=5
    )


def test_retains_original_inspects_and_cleanup_tail_without_mutations(observed):
    _, calls = observed
    result = observe()
    profile = json.loads(result.profile)
    assert calls == [
        ("container", "a" * 64, 195),
        ("container", "b" * 64, 195),
        ("network", "c" * 64, 195),
        ("container", "a" * 64, 195),
        ("container", "b" * 64, 195),
        ("network", "c" * 64, 195),
    ]
    assert profile["operator_inspect_sha256"] == hashlib.sha256(result.operator_inspect).hexdigest()
    assert profile["original_deadline_monotonic"] == 200
    assert "qualified" not in profile
    frame = observation.bootstrap_frame(result, {"scope": "manufactured-runtime-only"})
    assert len(frame[9:]) == int(frame[:8], 16) and frame[8:9] == b"\n"
    body = json.loads(frame[9:])
    assert body["operator_inspect"].encode() == result.operator_inspect
    assert "Config.Env" not in observation.CONTAINER_FORMAT
    assert ".Config" not in observation.CONTAINER_FORMAT


@pytest.mark.parametrize("change", ["image", "pid", "network", "alias"])
def test_mismatched_original_identity_is_rejected(observed, change):
    values, _ = observed
    if change == "image":
        values["a" * 64]["Image"] = "sha256:" + "f" * 64
    elif change == "pid":
        values["a" * 64]["State"]["Pid"] = 0
    elif change == "network":
        values["c" * 64]["Containers"]["b" * 64]["IPv4Address"] = "172.19.0.99/16"
    else:
        values["b" * 64]["NetworkSettings"]["Networks"]["bridge"]["Aliases"] = ["foreign"]
    with pytest.raises(ValueError):
        observe()


def test_pid_or_namespace_change_cannot_reuse_observation(observed, monkeypatch):
    values = iter([({"device": 4, "inode": 99}, 17), ({"device": 4, "inode": 99}, 18)])

    @contextmanager
    def process(*_):
        yield lambda: next(values)

    monkeypatch.setattr(observation, "_process", process)
    with pytest.raises(ValueError, match="pid_or_namespace_changed"):
        observe()


def test_expired_cutoff_and_malformed_identifiers_never_inspect(observed, monkeypatch):
    _, calls = observed
    monkeypatch.setattr(observation, "monotonic", lambda: 196)
    with pytest.raises(TimeoutError):
        observe()
    with pytest.raises(ValueError):
        observation.observe_container_operator_network(
            "named-container",
            "b" * 64,
            "c" * 64,
            "sha256:" + "d" * 64,
            absolute_deadline=300,
            cleanup_seconds=5,
        )
    assert calls == []


def test_operator_source_root_is_build_bound_not_environment(monkeypatch):
    monkeypatch.setenv("ANVIL_ROOT", "/not-a-proof-root")
    assert original_operator_repository() == Path(__file__).parents[4]


def test_successor_source_map_matches_actual_files_without_rewriting_predecessor():
    from anvil import marketing_native_private_sources as old
    from anvil import marketing_native_private_sources_v2 as current

    assert (
        old.PRIVATE_SOURCE_MANIFEST_SHA256
        == "3e74f8a196c5f34ae905dd245ddcda2736239065868c2290df71f512e56b6767"
    )
    assert current.PRIVATE_GRAPH_SOURCES["db.py"] != old.PRIVATE_GRAPH_SOURCES["db.py"]
    assert set(verify_opening_graph_sources(private=True)) == set(current.PRIVATE_GRAPH_SOURCES)
    raw = (
        (Path(__file__).parents[4] / "docs/generated/marketing-private-source-nomination-v2.json")
        .read_bytes()
        .rstrip(b"\n")
    )
    assert hashlib.sha256(raw).hexdigest() == current.PRIVATE_SOURCE_MANIFEST_SHA256
    assert json.loads(raw)["native_qualified"] is False


def test_inspect_signal_error_still_closes_stream_and_attempts_original_reap(monkeypatch):
    import os
    from types import SimpleNamespace

    incoming, outgoing = os.pipe()
    os.write(outgoing, b"{}")
    os.close(outgoing)
    stream = os.fdopen(incoming, "rb", buffering=0)
    child = SimpleNamespace(stdout=stream, pid=123, returncode=0)
    calls = []

    def launch(command, **kwargs):
        assert command[:3] == ["/usr/bin/docker", "--host", "unix:///run/docker.sock"]
        assert "DOCKER_HOST" not in kwargs["env"]
        return child

    class Group:
        def __init__(self, original):
            assert original is child

        def exited(self):
            return True

        def signal(self, number):
            calls.append("signal")
            raise PermissionError("manufactured_signal_denial")

        def reap(self, timeout):
            assert stream.closed and 0 <= timeout <= 5
            calls.append("reap")

    monkeypatch.setattr(observation.subprocess, "Popen", launch)
    monkeypatch.setattr(observation, "UnreapedProcessGroup", Group)
    monkeypatch.setattr(observation, "monotonic", lambda: 100)
    monkeypatch.setenv("DOCKER_HOST", "tcp://untrusted.invalid:2375")
    try:
        with pytest.raises(RuntimeError, match="cleanup_unknown"):
            observation._inspect("container", "a" * 64, 105)
        assert calls == ["signal", "reap"] and stream.closed
    finally:
        if not stream.closed:
            stream.close()
