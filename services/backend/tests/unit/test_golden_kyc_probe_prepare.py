"""Synthetic preparation controls; no QA authority, containers or SQL effects."""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from anvil import golden_kyc_probe_prepare as prep


def request(tmp_path):
    return {"schema_version": prep.REQUEST_SCHEMA, "business_context": {
        "project_id": str(uuid4()), "user_id": str(uuid4()), "pack_id": "synthetic-pack",
        "application_id": "synthetic-application", "environment_version": "synthetic-v1",
        "snapshot_sha256": "a" * 64}, "request_reference": "Synthetic test, not approval",
        "docker_host": "unix://" + str(tmp_path / "docker.sock"),
        "binaries": {"docker": "/test/docker", "compose": "/test/compose", "opa": "/test/opa"},
        "database_provider": {"path": "/private/provider.json", "database": "test", "server_version": "test"}}


def test_preparer_rejects_non_root_before_reading_any_request(monkeypatch):
    monkeypatch.setattr(prep.os, "geteuid", lambda: 501)
    monkeypatch.setattr(prep, "private_read", lambda _: pytest.fail("request must not be opened"))
    with pytest.raises(ValueError):
        prep.prepare("/private/request.json")


def test_preparer_rejects_other_root_host_before_request_read(monkeypatch):
    monkeypatch.setattr(prep.os, "geteuid", lambda: 0)
    monkeypatch.setattr(prep.os, "uname", lambda: SimpleNamespace(nodename="not-qa"))
    monkeypatch.setattr(prep, "private_read", lambda _: pytest.fail("request must not be opened"))
    with pytest.raises(ValueError):
        prep.prepare("/private/request.json")


def test_capsule_derives_only_fixed_two_read_actor_and_rejects_extra_authority(tmp_path, monkeypatch):
    module = prep.native.operator_proof_module()
    original = request(tmp_path)
    # Synthetic socket observation only; sandbox forbids binding Unix sockets.
    (tmp_path / "docker.sock").touch()
    monkeypatch.setattr(prep.stat, "S_ISSOCK", lambda _: True)
    capsule = prep.request_capsule(module, original)
    assert capsule["actor"]["paid_calls"] is False
    assert capsule["business_context"]["script_sha256"] == module.sha(module.canonical(module.TechnicalProbeStore.SCRIPT))
    assert set(capsule["actor"]) == {"paid_calls", "application_id", "environment_version", "snapshot_sha256", "script_sha256"}
    for key, value in (("paid_calls", True), ("script_sha256", "b" * 64)):
        modified = json.loads(json.dumps(original))
        modified["business_context"][key] = value
        with pytest.raises(ValueError):
            prep.request_capsule(module, modified)


def test_immutable_content_addressed_assets_reuse_exact_bytes_only(tmp_path):
    class Store:
        def _directory(self, name):
            return os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)

        def _read(self, directory, name):
            return (tmp_path / name).read_bytes()

    store = Store()
    first = prep.asset(store, {"synthetic": True})
    target = tmp_path / (first + ".json")
    before = target.stat().st_ino
    assert prep.asset(store, {"synthetic": True}) == first
    assert target.stat().st_ino == before
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        prep.exclusive_json(store, "operation-assets", first + ".json", {"changed": True}, reuse=True)
    assert target.read_bytes() == prep.native.canonical({"synthetic": True})


def test_task_projection_survives_canonical_plan_round_trip(tmp_path):
    # Plan storage canonicalizes object keys. Revalidation must reproduce the
    # same actor-file bytes after reading that immutable stored plan.
    actor = {"snapshot_sha256": "a" * 64, "application_id": "synthetic", "paid_calls": False}
    restored = json.loads(prep.native.canonical(actor))
    before = prep.native.layout_projection(tmp_path, actor, actor_seconds=30)
    after = prep.native.layout_projection(tmp_path, restored, actor_seconds=30)
    assert before == after
    assert before["environment/actor/context.json"].encode() == prep.native.canonical(actor)


def test_compose_is_config_only_and_keeps_final_attempt_mount_paths(tmp_path, monkeypatch):
    attempts = tmp_path / "technical-probe-attempts"
    attempts.mkdir(mode=0o700)
    final = attempts / ("c" * 64)
    projection = prep.native.layout_projection(final, {"paid_calls": False}, actor_seconds=30)
    calls = []

    def config(arguments, **kwargs):
        if arguments[0] == str(prep.PREFIX / "bin/python"):
            payload = json.loads(kwargs["input"])
            return SimpleNamespace(stdout=json.dumps({role: [str(Path(payload["staging"]) / (role + ".json"))]
                                                      for role in ("environment", "tests")}).encode())
        calls.append(arguments)
        assert arguments[0] == "/test/compose"
        assert arguments[-3:] == ["config", "--format", "json"]
        path = Path(arguments[arguments.index("--file") + 1])
        assert path.parent.parent == attempts
        source = json.loads(path.read_text())
        assert source["services"]["main"]["volumes"][0]["source"].startswith(str(final))
        return SimpleNamespace(stdout=json.dumps(source).encode())

    monkeypatch.setattr(prep.subprocess, "run", config)
    services = prep.compose_services(SimpleNamespace(root=tmp_path), request(tmp_path), projection,
                                     folder=final, name="anvil-bm-" + "c" * 20)
    assert set(services) == {"environment", "tests"} and len(calls) == 2
    assert not final.exists() and not list(attempts.iterdir())


def test_provider_measurement_hashes_without_parsing(tmp_path, monkeypatch):
    # Synthetic bytes only. Root ownership is the actual production boundary.
    if os.geteuid() != 0:
        pytest.skip("actual root custody test")
    path = tmp_path / "provider.json"
    path.write_bytes(b"not-json synthetic private bytes")
    path.chmod(0o600)
    monkeypatch.setattr(prep.json, "loads", lambda _: pytest.fail("provider must not be parsed"))
    assert prep.measured(path) == prep.hashlib.sha256(path.read_bytes()).hexdigest()
