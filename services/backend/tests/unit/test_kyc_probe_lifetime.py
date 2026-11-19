"""Manufactured lifetime controls, never physical QA qualification."""

import json
import threading
from types import SimpleNamespace

import pytest

from anvil import environment_harbor as native
from anvil import golden_kyc_probe as probe


def test_cleanup_closing_fence_prevents_late_callback_spawn(tmp_path, monkeypatch):
    holder = {"_callback_lock": threading.RLock(), "_callback_closing": threading.Event()}
    preflight_paused, release = threading.Event(), threading.Event()
    seen = []
    monkeypatch.setattr(probe.subprocess, "Popen", lambda *a, **k: seen.append("spawn"))
    monkeypatch.setattr(native, "stop_owned", lambda *a: [])

    def callback():
        preflight_paused.set()
        assert release.wait(2)
        try:
            probe._spawn_owned_child(["not-executed"], {}, holder, native.FixedDeadline(1), "a" * 64)
        except RuntimeError as error:
            seen.append(str(error))

    thread = threading.Thread(target=callback)
    thread.start()
    assert preflight_paused.wait(2)
    native._cleanup_lifecycle(tmp_path, None, object(), "synthetic", SimpleNamespace(close=lambda: None),
                              SimpleNamespace(cleanup=lambda: None), None,
                              technical=True, callback_holder=holder)
    release.set()
    thread.join(2)
    assert not thread.is_alive()
    assert seen == ["Probe callback closed before spawn"]
    assert json.loads((tmp_path / "cleanup.json").read_text())["complete"] is True


def test_expired_original_deadline_cannot_start_a_new_child(monkeypatch):
    calls = []
    holder = {"_callback_lock": threading.RLock(), "_callback_closing": threading.Event()}
    monkeypatch.setattr(probe.subprocess, "Popen", lambda *a, **k: calls.append(True))
    deadline = native.FixedDeadline(1)
    deadline.ends = 0
    with pytest.raises(TimeoutError):
        probe._spawn_owned_child(["not-executed"], {}, holder, deadline, "a" * 64)
    assert calls == []


def test_observation_records_are_canonical_and_owner_private(tmp_path):
    path = tmp_path / "framework-process.json"
    native.private_json(path, {"z": 2, "a": 1})
    assert path.read_bytes() == b'{"a":1,"z":2}'
    assert path.stat().st_mode & 0o777 == 0o600


def test_unowned_local_process_cannot_bootstrap_probe_execution():
    with pytest.raises(RuntimeError, match="existing_QA_root_operator_required"):
        probe.run("00000000-0000-0000-0000-000000000001")


def test_config_failure_closes_gateway_before_framework_spawn(tmp_path, monkeypatch):
    events = []

    def reject(*args, **kwargs):
        raise ValueError("synthetic config failure")

    monkeypatch.setattr(native, "prestart_guards", lambda: SimpleNamespace(validate_generated_config=reject))
    monkeypatch.setattr(native, "process_domain", lambda: {"synthetic": True})
    monkeypatch.setattr(native, "LocalDocker", lambda *args: SimpleNamespace(run=lambda *args: b'[{}]'))
    monkeypatch.setattr(native, "require_cached_image", lambda image: None)
    monkeypatch.setattr(native, "layout", lambda folder, *args, **kwargs: folder / "task")
    monkeypatch.setattr(native, "NativeGateway", lambda *args, **kwargs: SimpleNamespace(close=lambda: events.append("closed")))
    monkeypatch.setattr(native.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("framework must not launch"))
    with pytest.raises(ValueError, match="synthetic config failure"):
        native._execute_lifecycle(tmp_path / "attempt", {}, None, host="synthetic", python="synthetic",
                                  mediated_candidate=False, actor_seconds=30,
                                  bindings={"callback_manifest_sha256": "a" * 64, "request_sha256": "b" * 64,
                                            "service_projection_sha256s": {}})
    assert events == ["closed"]


@pytest.mark.parametrize("failure", ["framework_died", "permission_changed"])
def test_framework_loss_during_transaction_prevents_commit(failure):
    live = {"running": True, "pin": "original"}
    events = []

    class Store:
        def load_probe(self, job):
            return {"plan_sha256": live["pin"]}

        def _framework_entry(self, permission):
            if not live["running"]:
                raise RuntimeError("framework_died")

    # A connection's __exit__ commits only after the inner lease exits cleanly.
    class Transaction:
        def __enter__(self):
            return self

        def __exit__(self, error_type, error, trace):
            events.append("rollback" if error_type else "commit")

    with pytest.raises((RuntimeError, ValueError)):
        with Transaction():
            with probe.framework_lease(Store(), "synthetic", "original"):
                events.append("work")
                if failure == "framework_died":
                    live["running"] = False
                else:
                    live["pin"] = "changed"
    assert events == ["work", "rollback"]
