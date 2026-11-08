"""Manufactured receipt documents test capture validation, not native qualification."""

import copy
import hashlib
import io
import json
import shutil
import socket
import stat
from pathlib import Path

import pytest
from test_benchmark_archive import NOW
from test_benchmark_compiler import signed_source

from anvil.benchmark_compiler import compile_task, fixture_binding
from anvil.benchmark_pipeline import SOURCE_FILES, current_dependencies
from anvil.benchmark_pipeline_worker import _validate_native, _validate_resources
from anvil.benchmark_qualification import NativeGateway
from anvil.config import ROOT


def receipt_hash(result):
    result["native_receipt_sha256"] = hashlib.sha256(
        json.dumps(
            {k: v for k, v in result.items() if k != "native_receipt_sha256"},
            sort_keys=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


@pytest.fixture
def capture(tmp_path):
    raw, parsed, signers = signed_source()
    task = parsed.parsed.manifest.tasks[0]
    compiled = compile_task(
        io.BytesIO(raw),
        parsed,
        task.id,
        fixture_binding(),
        tmp_path / "actor.zip",
        signers=signers,
        now=NOW,
    )
    dependencies = current_dependencies(signers)
    results = []
    possible = sum(c.possible_points for c in task.criteria)
    for index, mode in enumerate(("positive", "empty", "guardrail")):
        result = {
            "origin": "original_synthetic_software_conformance",
            "binding_sha256": compiled.binding_sha256,
            "harbor_version": "0.25.0",
            "task_id": task.id,
            "mode": mode,
            "compiled_archive_sha256": compiled.archive_sha256,
            "manifest_sha256": compiled.bindings["manifest_sha256"],
            "source_authenticity": "isolated_test_signer_not_product_authority",
            "private_file_bindings": compiled.bindings["private_files"],
            "qualification_sha256": dependencies["sources"][
                "services/backend/src/anvil/benchmark_qualification.py"
            ],
            "compiler_source_sha256": dependencies["sources"][
                "services/backend/src/anvil/benchmark_compiler.py"
            ],
            "adapter_sha256": dependencies["sources"]["services/harbor/src/anvil_harbor/sme.py"],
            "points": possible if mode == "positive" else 0,
            "possible_points": possible,
            "candidate_stopped_before_evaluation": True,
            "candidate_container": hashlib.sha256(
                f"manufactured-actor-{index}".encode()
            ).hexdigest(),
            "evaluator_container": hashlib.sha256(
                f"manufactured-evaluator-{index}".encode()
            ).hexdigest(),
            "candidate_mounts_private": False,
            "evaluator_mounts_actor": False,
            "provider_calls": 0,
            "seal_sha256": hashlib.sha256(b"manufactured-seal-not-native-evidence").hexdigest(),
            "tool_calls": possible if mode == "positive" else 0,
            "denied_tool_calls": 1 if mode == "guardrail" else 0,
            "forbidden_access_attempts_denied": 4,
            "control_checks": {"non_root_readonly_no_egress_cgroups": True, "fresh_actor": True},
        }
        receipt_hash(result)
        results.append(result)
    return compiled, task, results, dependencies


def test_complete_receipt_contract(capture):
    compiled, task, results, _ = capture
    _validate_native(compiled, task, results)


@pytest.mark.parametrize(
    "fault",
    [
        "empty_controls",
        "missing_control",
        "extra_control",
        "truthy_control",
        "integer_control",
        "truthy_stopped",
        "bool_counter",
        "float_counter",
        "negative_counter",
        "missing_field",
        "extra_field",
        "receipt_hash",
        "manifest",
        "private_bindings",
        "qualification_source",
        "compiler_source",
        "adapter_source",
        "harbor_version",
        "origin",
        "source_authority",
        "invalid_seal",
        "invalid_container",
        "reused_actor",
        "reused_evaluator",
        "cross_mode_actor",
        "unexpected_tool_calls",
        "unexpected_denials",
        "missing_mode",
        "duplicate_mode",
        "wrong_task",
        "changed_package",
        "changed_binding",
        "wrong_reward",
        "wrong_maximum",
        "provider_call",
        "private_mount",
        "actor_mount",
        "same_container",
        "failed_control",
    ],
)
def test_incomplete_or_changed_receipts_fail_closed(capture, fault):
    compiled, task, original, _ = capture
    results = copy.deepcopy(original)
    result = results[1]
    if fault == "empty_controls":
        result["control_checks"] = {}
    elif fault == "missing_control":
        result["control_checks"].pop("fresh_actor")
    elif fault == "extra_control":
        result["control_checks"]["invented"] = True
    elif fault == "truthy_control":
        result["control_checks"]["fresh_actor"] = "true"
    elif fault == "integer_control":
        result["control_checks"]["fresh_actor"] = 1
    elif fault == "truthy_stopped":
        result["candidate_stopped_before_evaluation"] = "yes"
    elif fault == "bool_counter":
        result["points"] = False
    elif fault == "float_counter":
        result["points"] = 0.0
    elif fault == "negative_counter":
        result["denied_tool_calls"] = -1
    elif fault == "missing_field":
        result.pop("seal_sha256")
    elif fault == "extra_field":
        result["approved"] = True
    elif fault == "receipt_hash":
        result["native_receipt_sha256"] = "0" * 64
    elif fault == "manifest":
        result["manifest_sha256"] = "0" * 64
    elif fault == "private_bindings":
        result["private_file_bindings"] = []
    elif fault == "qualification_source":
        result["qualification_sha256"] = "0" * 64
    elif fault == "compiler_source":
        result["compiler_source_sha256"] = "0" * 64
    elif fault == "adapter_source":
        result["adapter_sha256"] = "0" * 64
    elif fault == "harbor_version":
        result["harbor_version"] = "0.0.0"
    elif fault == "origin":
        result["origin"] = "model_performance"
    elif fault == "source_authority":
        result["source_authenticity"] = "production_approved"
    elif fault == "invalid_seal":
        result["seal_sha256"] = "invalid"
    elif fault == "invalid_container":
        result["candidate_container"] = "not-a-container"
    elif fault == "reused_actor":
        result["candidate_container"] = results[0]["candidate_container"]
    elif fault == "reused_evaluator":
        result["evaluator_container"] = results[0]["evaluator_container"]
    elif fault == "cross_mode_actor":
        result["evaluator_container"] = results[0]["candidate_container"]
    elif fault == "unexpected_tool_calls":
        result["tool_calls"] = 1
    elif fault == "unexpected_denials":
        result["denied_tool_calls"] = 1
    elif fault == "missing_mode":
        results.pop()
    elif fault == "duplicate_mode":
        result["mode"] = "positive"
    elif fault == "wrong_task":
        result["task_id"] = "FX-002"
    elif fault == "changed_package":
        result["compiled_archive_sha256"] = "0" * 64
    elif fault == "changed_binding":
        result["binding_sha256"] = "0" * 64
    elif fault == "wrong_reward":
        result["points"] = 1
    elif fault == "wrong_maximum":
        result["possible_points"] = 1
    elif fault == "provider_call":
        result["provider_calls"] = 1
    elif fault == "private_mount":
        result["candidate_mounts_private"] = True
    elif fault == "actor_mount":
        result["evaluator_mounts_actor"] = True
    elif fault == "same_container":
        result["evaluator_container"] = result["candidate_container"]
    elif fault == "failed_control":
        result["control_checks"]["fresh_actor"] = False
    if fault != "receipt_hash":
        receipt_hash(result)
    with pytest.raises(ValueError):
        _validate_native(compiled, task, results)


@pytest.fixture
def resource_documents():
    return [
        {
            "mode": "memory_pids",
            "container": "1" * 64,
            "retained": True,
            "pids_denied": True,
            "memory_oom_observed": True,
            "children_started": 14,
        },
        {
            "mode": "tree_timeout",
            "container": "2" * 64,
            "retained": True,
            "owned_timeout_tree_stopped": True,
        },
        {
            "mode": "stdio_overflow",
            "container": "3" * 64,
            "retained": True,
            "stdio_overflow_denied": True,
        },
        {
            "mode": "stdio_timeout",
            "container": "4" * 64,
            "retained": True,
            "stdio_timeout_denied": True,
        },
    ]


def test_complete_resource_document_contract(resource_documents):
    _validate_resources(resource_documents)


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "duplicate",
        "empty",
        "truthy",
        "failed",
        "extra",
        "reused",
        "invalid_id",
        "bool_children",
        "no_children",
        "unbounded_children",
        "missing_control",
    ],
)
def test_incomplete_resource_documents_fail_closed(resource_documents, fault):
    results = copy.deepcopy(resource_documents)
    if fault == "missing":
        results.pop()
    elif fault == "duplicate":
        results[1] = results[0]
    elif fault == "empty":
        results = []
    elif fault == "truthy":
        results[0]["memory_oom_observed"] = 1
    elif fault == "failed":
        results[0]["pids_denied"] = False
    elif fault == "extra":
        results[0]["unobserved"] = True
    elif fault == "reused":
        results[1]["container"] = results[0]["container"]
    elif fault == "invalid_id":
        results[1]["container"] = "invalid"
    elif fault == "bool_children":
        results[0]["children_started"] = True
    elif fault == "no_children":
        results[0]["children_started"] = 0
    elif fault == "unbounded_children":
        results[0]["children_started"] = 16
    elif fault == "missing_control":
        results[0].pop("memory_oom_observed")
    with pytest.raises(ValueError):
        _validate_resources(results)


@pytest.mark.parametrize("change", ["source", "rule", "calibration", "evaluator", "tool"])
def test_real_filesystem_dependency_changes_cannot_reuse_qualification(tmp_path, change):
    for relative in SOURCE_FILES:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    fixture = "fixtures/benchmark-bundle/fictional-points-v1"
    shutil.copytree(ROOT / fixture, tmp_path / fixture)
    baseline = current_dependencies({}, root=tmp_path)
    relative = {
        "source": SOURCE_FILES[0],
        "rule": fixture + "/eval_pack/FX-001/rules.json",
        "calibration": fixture + "/eval_pack/FX-001/calibration.json",
        "evaluator": fixture + "/eval_pack/FX-001/evaluator.py",
        "tool": fixture + "/runtime_pack/FX-001/tool-server.py",
    }[change]
    with (tmp_path / relative).open("ab") as stream:
        stream.write(b"\n")
    if change == "source":
        assert current_dependencies({}, root=tmp_path) != baseline
    else:
        with pytest.raises(ValueError, match="Fictional fixture"):
            current_dependencies({}, root=tmp_path)


@pytest.mark.parametrize("authorized", [True, False])
def test_real_private_gateway_supports_long_owned_trial_path_and_closes_socket(
    tmp_path, authorized
):
    trial = tmp_path / ("owned-trial-" + "x" * 90)
    trial.mkdir(mode=0o700)

    def callback(route, body, results):
        assert route == "/actor" and body == "manufactured-session"
        return {"checked": True}

    gateway = NativeGateway(trial, callback)
    path = gateway.path
    parent = Path(path).parent
    try:
        assert len(path.encode()) < 108
        assert stat.S_IMODE(Path(path).stat().st_mode) == 0o600
        assert stat.S_IMODE(parent.stat().st_mode) == 0o700
        body = json.dumps({"session_id": "manufactured-session"}).encode()
        token = gateway.token if authorized else "invalid"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(path)
            client.sendall(
                (
                    f"POST /actor HTTP/1.0\r\nAuthorization: Bearer {token}\r\nContent-Length: {len(body)}\r\n\r\n"
                ).encode()
                + body
            )
            response = b""
            while chunk := client.recv(4096):
                response += chunk
        assert response.startswith(b"HTTP/1.0 200" if authorized else b"HTTP/1.0 409")
        assert (gateway.error is None) == authorized
    finally:
        gateway.close()
    assert not parent.exists()
    assert trial.is_dir()
