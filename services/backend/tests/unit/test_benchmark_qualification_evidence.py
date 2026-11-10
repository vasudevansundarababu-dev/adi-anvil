"""Contract fixtures only; no native execution or human approval claim."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import rfc8785

from anvil.benchmark_compiler import seal_outputs
from anvil.benchmark_qualification_evidence import capture_public, project_report, public_projection


def fixture_capture(tmp_path):
    task = SimpleNamespace(
        outputs=[SimpleNamespace(path="answers.json", max_bytes=65536)],
        criteria=[SimpleNamespace(id="criterion-1", possible_points=1)],
    )
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    (source / "answers.json").write_text('{"answer":42}')
    sealed = tmp_path / "sealed"
    seal = seal_outputs(source, sealed, task.outputs)
    return task, sealed, seal


def test_capture_reads_only_sealed_declared_actor_output(tmp_path):
    task, sealed, seal = fixture_capture(tmp_path)
    capture = capture_public(
        sealed,
        task,
        {"criteria": {"criterion-1": 1}, "secret": "never-return"},
        seal.manifest_sha256,
    )
    assert capture["outputs"][0]["text"] == '{"answer":42}'
    assert capture["criteria"] == [
        {"criterion_id": "criterion-1", "earned_points": "1", "possible_points": "1"}
    ]
    assert "secret" not in json.dumps(capture)


@pytest.mark.parametrize("fault", ["seal_hash", "changed_bytes", "symlink", "extra", "criteria"])
def test_capture_rejects_changed_or_noncanonical_source(tmp_path, fault):
    task, sealed, seal = fixture_capture(tmp_path)
    expected = seal.manifest_sha256
    evaluation = {"criteria": {"criterion-1": 1}}
    sealed.chmod(0o700)
    if fault == "seal_hash":
        expected = "0" * 64
    elif fault == "criteria":
        evaluation = {"criteria": {"private-rule-path": 1}}
    elif fault == "extra":
        (sealed / "grader.py").write_text("private")
    else:
        p = sealed / "answers.json"
        p.unlink()
        if fault == "symlink":
            p.symlink_to(tmp_path / "source" / "answers.json")
        else:
            p.write_text("tampered")
    with pytest.raises((ValueError, OSError)):
        capture_public(sealed, task, evaluation, expected)


def test_worker_seal_root_symlink_is_not_followed(tmp_path):
    task, sealed, seal = fixture_capture(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(sealed)
    with pytest.raises(OSError):
        capture_public(link, task, {"criteria": {"criterion-1": 1}}, seal.manifest_sha256)


@pytest.mark.parametrize("fault", ["traversal", "hash", "size", "extra", "nan", "criterion_path"])
def test_projection_rejects_untrusted_fields_and_invalid_content(fault):
    data = b"hello"
    value = {
        "outputs": [
            {
                "path": "report.md",
                "sha256": hashlib.sha256(data).hexdigest(),
                "byte_size": 5,
                "text": "hello",
            }
        ],
        "missing": [],
        "criteria": [{"criterion_id": "c1", "earned_points": "1", "possible_points": "1"}],
    }
    if fault == "traversal":
        value["outputs"][0]["path"] = "../private"
    elif fault == "hash":
        value["outputs"][0]["sha256"] = "0" * 64
    elif fault == "size":
        value["outputs"][0]["byte_size"] = 1000000
    elif fault == "extra":
        value["outputs"][0]["private_path"] = "/grader"
    elif fault == "nan":
        value["criteria"][0]["earned_points"] = "NaN"
    else:
        value["criteria"][0]["criterion_id"] = "eval_pack/reference.json"
    with pytest.raises(ValueError):
        public_projection(value)


def report_fixture(capture=None):
    row = {
        "id": "qualification-contract-only",
        "task_id": "FX-001",
        "outcome": "passed",
        "binding_sha256": "a" * 64,
        "package_sha256": "b" * 64,
    }
    artifact = {"sha256": "d" * 64, "byte_size": 10000}
    build = {"subject_sha256": "e" * 64}
    trials = []
    for mode in ["positive", "empty", "guardrail"]:
        trial = {
            "task_id": "FX-001",
            "binding_sha256": "a" * 64,
            "compiled_archive_sha256": "b" * 64,
            "provider_calls": 0,
            "mode": mode,
            "points": 0,
            "possible_points": 1,
            "seal_sha256": "c" * 64,
            "control_checks": {"fresh_actor": True, "non_root_readonly_no_egress_cgroups": True},
            "qualification_sha256": "f" * 64,
            "compiler_source_sha256": "1" * 64,
            "adapter_sha256": "2" * 64,
            "private_file_bindings": {"never": "expose"},
            "evaluator_container": "never-expose",
        }
        if capture is not None:
            trial["public_capture"] = capture
            manifest = {
                "files": [
                    {k: v for k, v in item.items() if k != "text"} for item in capture["outputs"]
                ],
                "missing": capture["missing"],
            }
            trial["seal_sha256"] = hashlib.sha256(rfc8785.dumps(manifest)).hexdigest()
        trial["native_receipt_sha256"] = hashlib.sha256(
            json.dumps(trial, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        trials.append(trial)
    report = {
        "origin": "original_synthetic_software_conformance",
        "subject_sha256": "e" * 64,
        "binding_sha256": "a" * 64,
        "native_trials": trials,
        "private": "never-expose",
    }
    return row, artifact, build, report


def test_old_report_has_no_invented_output_and_never_spreads_private_fields():
    row, artifact, build, report = report_fixture()
    with patch(
        "anvil.benchmark_qualification_evidence.read_private_record",
        return_value=json.dumps(report).encode(),
    ):
        result = project_report(row, artifact, build)
    assert all(x["public_capture"] is None for x in result["trials"])
    assert "never-expose" not in json.dumps(result)


@pytest.mark.parametrize("fault", ["receipt", "task", "package", "subject", "seal"])
def test_report_rejects_substituted_refs_or_capture(fault):
    value = {"outputs": [], "missing": ["answers.json"], "criteria": []}
    row, artifact, build, report = report_fixture(value)
    if fault == "receipt":
        report["native_trials"][0]["points"] = 1
    elif fault == "task":
        row["task_id"] = "FX-other"
    elif fault == "package":
        row["package_sha256"] = "0" * 64
    elif fault == "subject":
        build["subject_sha256"] = "0" * 64
    else:
        t = report["native_trials"][0]
        t["public_capture"]["missing"] = ["report.md"]
        t.pop("native_receipt_sha256")
        t["native_receipt_sha256"] = hashlib.sha256(
            json.dumps(t, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
    with patch(
        "anvil.benchmark_qualification_evidence.read_private_record",
        return_value=json.dumps(report).encode(),
    ):
        with pytest.raises(ValueError):
            project_report(row, artifact, build)


def test_shared_frontend_contract_fixture_is_actual_allowlisted_projection():
    from pathlib import Path

    fixture = json.loads(
        (
            Path(__file__).resolve().parents[4]
            / "contracts/fixtures/benchmark-qualification-evidence-response.json"
        ).read_text()
    )
    assert "Manufactured contract" in fixture["fixture_notice"]
    data = fixture["data"]
    assert (
        data["primary"] is None
        and not data["comparison_admitted"]
        and not data["model_performance"]
    )
    q = data["qualifications"][0]
    capture = q["trials"][0]["public_capture"]
    row, artifact, build, report = report_fixture(capture)
    with patch(
        "anvil.benchmark_qualification_evidence.read_private_record",
        return_value=json.dumps(report).encode(),
    ):
        assert q == project_report(row, artifact, build)


def test_oversized_artifact_is_rejected_before_private_read():
    row, artifact, build, _ = report_fixture()
    artifact["byte_size"] = 1048577
    with patch("anvil.benchmark_qualification_evidence.read_private_record") as reader:
        with pytest.raises(ValueError):
            project_report(row, artifact, build)
        reader.assert_not_called()


@pytest.mark.parametrize(
    "fault",
    [
        "control",
        "digest",
        "points",
        "duplicate_output",
        "duplicate_missing",
        "duplicate_criterion",
        "overlap",
    ],
)
def test_reader_rejects_malformed_typed_fields_and_duplicate_membership(fault):
    capture = {
        "outputs": [
            {
                "path": "report.md",
                "sha256": hashlib.sha256(b"x").hexdigest(),
                "byte_size": 1,
                "text": "x",
            }
        ],
        "missing": [],
        "criteria": [{"criterion_id": "c1", "earned_points": "0", "possible_points": "1"}],
    }
    if fault.startswith("duplicate") or fault == "overlap":
        if fault == "duplicate_output":
            capture["outputs"] *= 2
        elif fault == "duplicate_missing":
            capture["missing"] = ["answers.json", "answers.json"]
        elif fault == "duplicate_criterion":
            capture["criteria"] *= 2
        else:
            capture["missing"] = ["report.md"]
        with pytest.raises(ValueError):
            public_projection(capture)
        return
    row, artifact, build, report = report_fixture(capture)
    t = report["native_trials"][0]
    if fault == "control":
        t["control_checks"]["fresh_actor"] = {"private": "never-expose"}
    elif fault == "digest":
        t["adapter_sha256"] = "private-path"
    else:
        t["points"] = -1
    t.pop("native_receipt_sha256")
    t["native_receipt_sha256"] = hashlib.sha256(
        json.dumps(t, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    with patch(
        "anvil.benchmark_qualification_evidence.read_private_record",
        return_value=json.dumps(report).encode(),
    ):
        with pytest.raises(ValueError):
            project_report(row, artifact, build)
