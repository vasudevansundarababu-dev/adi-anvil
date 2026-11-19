"""Typed/purpose/deadline refusals cannot create a native or provider effect."""

import copy
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest

from anvil.golden_native_mediated import read_owned, request
from anvil.praxis_generic_contract import canonical, digest


def body():
    public = {"task": {"objective": "synthetic control"}, "application_id": "synthetic"}
    binding = {key: str(uuid4()) for key in ("project_id", "job_id", "plan_id", "trial_id")}
    binding.update(lease_sha256="a" * 64, generation=0, input_sha256=digest(public))
    return {"schema_version": "anvil.native-bridge-request.v2", "binding": binding, "binding_sha256": digest(binding),
            "public_actor": public, "gateway_socket": "/private/.bm-gw-test/gateway.sock", "gateway_token": "b" * 64,
            "deadline": time.time() + 60, "actor_seconds": 60, "handler": "kyc_worker_candidate_v2",
            "preparation_sha256": "c" * 64, "original_deadline_monotonic": time.monotonic() + 60}


@pytest.mark.parametrize("fault", ["legacy", "technical", "callback", "deadline", "clock", "handler", "input", "generation", "oversized"])
def test_wrong_purpose_source_or_clock_is_refused_before_any_effect(fault):
    value = copy.deepcopy(body())
    if fault == "legacy":
        value["schema_version"] = "anvil.native-bridge-request.v1"
    elif fault == "technical":
        value["handler"] = "fixed_two_read_technical_probe"
    elif fault == "callback":
        value["callback"] = "os:system"
    elif fault == "deadline":
        value["deadline"] = time.time() - 1
    elif fault == "clock":
        value["original_deadline_monotonic"] = time.monotonic() + 1000
    elif fault == "handler":
        value["handler"] = "caller.provided:run"
    elif fault == "input":
        value["public_actor"]["hidden_reference"] = "must not enter actor"
    elif fault == "generation":
        value["binding"]["generation"] = -1
        value["binding_sha256"] = digest(value["binding"])
    else:
        value["actor_seconds"] = 600
    with pytest.raises(ValueError):
        request(value)


def test_request_is_only_metadata_not_qualification():
    value = body()
    assert request(value) is value
    assert "qualified" not in value and "spending_authority" not in value


def test_control_cannot_change_fixed_payload_or_use_production_handler():
    from anvil.golden_native_control import PREPARATION, PUBLIC

    value = body()
    value.update(schema_version="anvil.native-control-bridge-request.v2", handler="fixed_custody_ping_v2",
                 public_actor=copy.deepcopy(PUBLIC), preparation_sha256=PREPARATION)
    value["binding"]["input_sha256"] = digest(PUBLIC)
    value["binding_sha256"] = digest(value["binding"])
    assert request(value) is value
    value["handler"] = "kyc_worker_candidate_v2"
    with pytest.raises(ValueError):
        request(value)
    value["handler"] = "fixed_custody_ping_v2"
    value["public_actor"]["operation"] = "provider.dispatch"
    value["binding"]["input_sha256"] = digest(value["public_actor"])
    value["binding_sha256"] = digest(value["binding"])
    with pytest.raises(ValueError):
        request(value)


def test_control_result_cannot_finalize_production_before_receipt_checks():
    from anvil.golden_native_bridge import validate_framework

    value = {"framework_trial_id": str(uuid4()), "worker_bridge_purpose": "native_transport_control_only"}
    with pytest.raises(ValueError, match="disjoint"):
        validate_framework(value, purpose="kyc_worker_collection_only")


def test_control_module_entry_delegates_to_canonical_typed_session(monkeypatch, capsys):
    import runpy
    import sys
    import warnings

    from anvil import golden_native_control

    calls = []
    monkeypatch.setattr(sys, "argv", ["anvil.golden_native_control", "--root", "/synthetic-private-bridge"])
    original_flags = sys.flags

    class Flags:
        isolated = 1

        def __getattr__(self, name):
            return getattr(original_flags, name)

    monkeypatch.setattr(sys, "flags", Flags())
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    monkeypatch.setattr(golden_native_control, "run", lambda root: calls.append(root) or {"framework_trial_id": str(uuid4())})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("anvil.golden_native_control", run_name="__main__")
    assert calls == ["/synthetic-private-bridge"]
    assert '"qualification_granted": false' in capsys.readouterr().out


def test_sdk_bootstrap_is_explicit_and_refuses_ambient_credentials(tmp_path):
    from anvil.environment_harbor import mediated_sdk_environment

    arguments = {"plan_path": tmp_path / "not-an-admission.json", "nonce": "a" * 64,
                 "image_sha256": "b" * 64, "opa": {"path": "/opt/anvil/opa", "sha256": "c" * 64}}
    env = mediated_sdk_environment({"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PYTHONPATH": "/untrusted"}, **arguments)
    assert env["ANVIL_ENV"] == "local" and env["WEB_ORIGIN"] == "http://127.0.0.1:3202"
    assert "PYTHONPATH" not in env
    assert env["ANVIL_LIVE_PROVIDERS_ENABLED"] == env["ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED"] == "false"
    for key in ("DATABASE_URL", "ANVIL_SESSION_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "PROVIDER_API_KEY"):
        with pytest.raises(ValueError, match="bootstrap metadata"):
            mediated_sdk_environment({key: "synthetic-not-a-secret"}, **arguments)


def test_rejected_bootstrap_closes_actual_owned_gateway(tmp_path):
    import tempfile

    from anvil.benchmark_qualification import NativeGateway
    from anvil.environment_harbor import gateway_configuration, mediated_sdk_environment

    home = tempfile.TemporaryDirectory(prefix=".sgt-", dir="/tmp")
    gateway = NativeGateway(tmp_path, lambda *unused: None, socket_root=Path(home.name))
    socket_path = Path(gateway.path)
    with pytest.raises(ValueError):
        with gateway_configuration(gateway, home):
            mediated_sdk_environment({"DATABASE_URL": "synthetic"}, plan_path=tmp_path / "none", nonce="a" * 64,
                image_sha256="b" * 64, opa={"path": "/opt/anvil/opa", "sha256": "c" * 64})
    assert not socket_path.exists() and not gateway.thread.is_alive()


def test_owned_records_reject_reformat_alias_extra_hardlink_and_permissions(tmp_path):
    path = tmp_path / "record.json"
    value = body()
    path.write_bytes(canonical(value))
    path.chmod(0o600)
    assert read_owned(path, os.getuid()) == value
    path.write_bytes(canonical(value) + b"\n")
    with pytest.raises(ValueError, match="Canonical"):
        read_owned(path, os.getuid())
    path.write_bytes(canonical(value))
    alias = tmp_path / "alias.json"
    alias.symlink_to(path)
    with pytest.raises(ValueError):
        read_owned(alias, os.getuid())
    extra = tmp_path / "extra.json"
    os.link(path, extra)
    with pytest.raises(ValueError):
        read_owned(path, os.getuid())
    extra.unlink()
    path.chmod(0o644)
    with pytest.raises(ValueError):
        read_owned(path, os.getuid())
