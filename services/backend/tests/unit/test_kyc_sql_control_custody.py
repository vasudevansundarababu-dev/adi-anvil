"""Operator config safety only; these controls never connect to a database."""
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def script():
    path = Path(__file__).resolve().parents[4] / "runtime-checks/kyc_sql_component_controls.py"
    spec = importlib.util.spec_from_file_location("synthetic_sql_controls", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def config():
    return {"schema_version": "anvil.synthetic-sql-component-config.v2",
        "fixture_nonce": "a" * 64, "fixture_label": "synthetic-component-control-not-performance",
        "database": "anvil_golden_kyc_component_test", "scheduler_dsn": "synthetic-private",
        "grader_dsn": "synthetic-private", "app_dsn": "synthetic-private", "project_id": str(uuid4()), "user_id": str(uuid4()),
        "pack_id": "synthetic-pack", "application_id": "GB-001", **{name: "b" * 64 for name in (
            "snapshot_sha256", "golden_source_sha256", "broker_source_sha256", "runtime_image_sha256")}}


def test_private_bounded_exact_config_required_before_database_import(script, tmp_path):
    path = tmp_path / "operator.json"
    body = config()
    path.write_text(json.dumps(body))
    path.chmod(0o600)
    assert script.read_config(path) == body
    path.chmod(0o644)
    with pytest.raises(ValueError):
        script.read_config(path)
    path.chmod(0o600)
    body["database"] = "serving_database"
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError):
        script.read_config(path)
    path.unlink()
    path.symlink_to(tmp_path / "not-an-operator-file")
    with pytest.raises(ValueError):
        script.read_config(path)


def test_global_deadline_cannot_be_swallowed_as_an_individual_failure(script):
    assert not issubclass(script.ControlDeadline, Exception)


def test_failure_frames_do_not_disclose_exception_text_locals_or_directory(script):
    namespace = {"planted_secret": "never-print-this-password"}
    try:
        exec(compile("raise RuntimeError(planted_secret)", "/private/sensitive/location/control.py", "exec"), namespace)
    except RuntimeError as error:
        frames = script.safe_exception_frames(error)
    raw = json.dumps(frames)
    assert frames[-1]["file"] == "control.py"
    assert "never-print-this-password" not in raw
    assert "sensitive" not in raw
    assert "private/" not in raw
    assert all(set(frame) == {"file", "line", "function"} for frame in frames)


def test_old_schema_and_missing_app_identity_cannot_reuse_v1_fixture(script, tmp_path):
    path = tmp_path / "old.json"
    body = config()
    body["schema_version"] = "anvil.synthetic-sql-component-config.v1"
    path.write_text(json.dumps(body))
    path.chmod(0o600)
    with pytest.raises(ValueError):
        script.read_config(path)
    body["schema_version"] = "anvil.synthetic-sql-component-config.v2"
    body.pop("app_dsn")
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError):
        script.read_config(path)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "remote.example", "relative/socket"])
def test_all_database_credentials_require_unix_socket_host(script, host):
    with pytest.raises(ValueError):
        script.validate_unix_params({"host": host, "dbname": "anvil_golden_kyc_component_test"}, "anvil_golden_kyc_component_test")


def test_unix_socket_alias_or_wrong_database_is_refused(script, tmp_path, monkeypatch):
    socket = tmp_path / "socket"
    socket.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(socket)
    monkeypatch.setattr(Path, "is_socket", lambda self: True)
    script.validate_unix_params({"host": str(socket), "dbname": "synthetic"}, "synthetic")
    with pytest.raises(ValueError):
        script.validate_unix_params({"host": str(alias), "dbname": "synthetic"}, "synthetic")
    with pytest.raises(ValueError):
        script.validate_unix_params({"host": str(socket), "dbname": "serving"}, "synthetic")
