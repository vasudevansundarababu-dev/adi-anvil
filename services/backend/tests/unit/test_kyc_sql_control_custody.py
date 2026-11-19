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
    return {"schema_version": "anvil.synthetic-sql-component-config.v1",
        "fixture_nonce": "a" * 64, "fixture_label": "synthetic-component-control-not-performance",
        "database": "anvil_golden_kyc_component_test", "scheduler_dsn": "synthetic-private",
        "grader_dsn": "synthetic-private", "project_id": str(uuid4()), "user_id": str(uuid4()),
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
