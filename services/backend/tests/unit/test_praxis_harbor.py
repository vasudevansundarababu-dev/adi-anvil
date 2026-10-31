import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from anvil.harbor_package import compile_package, unpack
from anvil.praxis_contract import PraxisTask, actor_view, grade

SAMPLE = Path(__file__).resolve().parents[4] / "contracts/praxis/synthetic-marketing.task.json"


def task():
    return PraxisTask.model_validate_json(SAMPLE.read_bytes())


def test_reward_hard_failure_retains_diagnostics():
    t = task()
    assert grade(t, t.rubric.reference_output)["reward"] == 1
    bad = {**t.rubric.reference_output, "spend_usd": 1001}
    result = grade(t, bad)
    assert result["reward"] == 0
    assert result["diagnostic_score"] == 1
    assert result["hard_failures"] == ["rule-budget"]
    assert all(c["passed"] for c in result["criteria"].values())


@pytest.mark.parametrize(
    "mutation",
    ["unknown", "future", "duplicate", "weights", "review", "contradiction", "numeric_bool"],
)
def test_fail_closed_contract(mutation):
    raw = json.loads(SAMPLE.read_bytes())
    if mutation == "unknown":
        raw["environment"]["binding"] = "arbitrary-shell"
    elif mutation == "future":
        raw["stages"][0]["evidence_ids"].append("ev-private-note")
    elif mutation == "duplicate":
        raw["actions"][0]["id"] = raw["constraints"][0]["id"]
    elif mutation == "weights":
        raw["rubric"]["criteria"][0]["weight_bps"] = 1
    elif mutation == "review":
        raw["provenance"]["review"]["reviewed_revision_id"] = "other"
    elif mutation == "contradiction":
        raw["constraints"][1]["binding"]["value"] = 2000
    else:
        raw["constraints"][0]["binding"]["value"] = True
    with pytest.raises(ValidationError):
        PraxisTask.model_validate(raw)


def test_actor_and_build_context_exclude_private_reference(tmp_path):
    t, manifest, package = compile_package(SAMPLE.read_bytes())
    assert compile_package(SAMPLE.read_bytes())[2] == package
    assert manifest["source_sha256"] == hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    assert "PRIVATE-NORTHSTAR" not in json.dumps(actor_view(t))
    assert "rubric" not in actor_view(t)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        for path in archive.namelist():
            if path.startswith("environment/") or path == "instruction.md":
                data = archive.read(path)
                assert b"PRIVATE-NORTHSTAR" not in data
                assert b"reference_output" not in data
                assert b"criterion-channel" not in data
    unpack(package, tmp_path, hashlib.sha256(package).hexdigest())
    assert (tmp_path / "tests/grader.py").is_file()
    with pytest.raises(ValueError, match="integrity"):
        unpack(package + b"tamper", tmp_path, hashlib.sha256(package).hexdigest())


def test_invalid_reference_duplicate_keys_and_schema():
    raw = json.loads(SAMPLE.read_bytes())
    raw["rubric"]["reference_output"]["spend_usd"] = 1001
    with pytest.raises(ValueError, match="Reference"):
        compile_package(json.dumps(raw).encode())
    with pytest.raises(ValueError, match="Duplicate"):
        compile_package(b'{"task_id":"a","task_id":"b"}')
    schema = json.loads((SAMPLE.parent / "task.schema.json").read_text())
    assert schema == PraxisTask.model_json_schema()


def test_strict_numeric_output_and_missing_fields():
    t = task()
    assert grade(t, {**t.rubric.reference_output, "spend_usd": True})["reward"] == 0
    assert grade(t, {**t.rubric.reference_output, "spend_usd": float("inf")})["reward"] == 0
    assert grade(t, {})["reward"] == 0


def test_child_has_no_parent_credentials(monkeypatch, tmp_path):
    from anvil.harbor_worker import argv, child_environment

    monkeypatch.setenv("OPENAI_API_KEY", "canary-secret")
    monkeypatch.setenv("DATABASE_URL", "canary-db")
    env = child_environment(tmp_path)
    assert not {"OPENAI_API_KEY", "DATABASE_URL", "GOOGLE_APPLICATION_CREDENTIALS"} & env.keys()
    assert env["HOME"] == str(tmp_path)
    assert env["HARBOR_TELEMETRY"] == "0"
    with pytest.raises(ValueError):
        argv("harbor", tmp_path, tmp_path, "claude-code")


def test_staged_initial_actor_and_image_never_contain_future(tmp_path):
    t, manifest, package = compile_package(
        (SAMPLE.parent / "synthetic-marketing-staged.task.json").read_bytes()
    )
    view = json.dumps(actor_view(t))
    assert "FUTURE-NORTHSTAR" not in view
    assert "ev-budget-update" not in view
    assert "stage-revise" not in view
    unpack(package, tmp_path, hashlib.sha256(package).hexdigest())
    for path in [tmp_path / "instruction.md", *(tmp_path / "environment").rglob("*")]:
        if path.is_file():
            assert b"FUTURE-NORTHSTAR" not in path.read_bytes()
            assert b"PRIVATE-NORTHSTAR" not in path.read_bytes()
    assert b"FUTURE-NORTHSTAR" in (tmp_path / "steps/step-02/workdir/observation.json").read_bytes()
    assert b'user = "10001"' in (tmp_path / "task.toml").read_bytes()
    assert manifest["stage_order"] == ["stage-commit", "stage-revise"]


@pytest.mark.parametrize(
    "mutation",
    [
        "early_reveal",
        "private_reveal",
        "unknown_action",
        "duplicate_update",
        "missing_field",
        "nonfinite",
        "reference",
        "stage_weights",
    ],
)
def test_staged_fail_closed(mutation):
    from anvil.praxis_staged import PraxisTaskV2

    raw = json.loads((SAMPLE.parent / "synthetic-marketing-staged.task.json").read_text())
    if mutation == "early_reveal":
        raw["stages"][0]["evidence_ids"].append("ev-budget-update")
    elif mutation == "private_reveal":
        raw["stages"][1]["evidence_ids"].append("ev-private-note")
    elif mutation == "unknown_action":
        raw["stages"][0]["action_id"] = "missing"
    elif mutation == "duplicate_update":
        raw["stages"][1]["state_updates"][0]["id"] = "update-commit"
    elif mutation == "missing_field":
        raw["stages"][0]["state_updates"][0]["from_field"] = "absent"
    elif mutation == "nonfinite":
        raw["environment"]["initial_state"]["bad"] = float("inf")
    elif mutation == "reference":
        raw["stages"][0]["rubric"]["reference_output"]["spend_usd"] = 999
    else:
        raw["stages"][0]["rubric"]["criteria"][0]["weight_bps"] = 1
    with pytest.raises(ValidationError):
        PraxisTaskV2.model_validate(raw)


def test_export_hash_checked_and_payload_bytes_preserved():
    from anvil.praxis_export import parse_export

    raw = SAMPLE.read_bytes()
    envelope = {
        "schema_version": "praxis.anvil.export.v1",
        "source": {
            "record_id": "test-record",
            "record_hash": "a" * 64,
            "project_id": "test-project",
            "client_id": "test-client",
            "submission_time": "2026-10-30T00:00:00Z",
            "reviewer_id": None,
            "review_decision_time": None,
        },
        "payload_json": raw.decode(),
        "payload_sha256": hashlib.sha256(raw).hexdigest(),
    }
    payload, receipt = parse_export(json.dumps(envelope).encode())
    assert payload == raw and receipt.source.record_id == "test-record"
    envelope["payload_json"] += "\n"
    with pytest.raises(ValueError, match="sha256"):
        parse_export(json.dumps(envelope).encode())
