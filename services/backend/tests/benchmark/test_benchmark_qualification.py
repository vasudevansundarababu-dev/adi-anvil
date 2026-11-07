import base64
import hashlib
import io
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_benchmark_imports import archive

from anvil.benchmark_archive import validate_archive
from anvil.benchmark_bundle import TrustedSigner
from anvil.benchmark_compiler import compile_task, fixture_binding
from anvil.benchmark_qualification import native_trial
from anvil.config import ROOT


@pytest.fixture(scope="module")
def signed_native_fixture():
    now = datetime.now(timezone.utc)
    key = Ed25519PrivateKey.generate()
    root = TrustedSigner(
        "native-software-only",
        key.public_key().public_bytes_raw(),
        now - timedelta(hours=1),
        now + timedelta(hours=2),
    )
    manifest = json.loads(
        (ROOT / "fixtures/benchmark-bundle/fictional-points-v1/manifest.json").read_bytes()
    )
    signature = json.dumps(
        {
            "profile": "ed25519-jcs-v1",
            "algorithm": "Ed25519",
            "key_id": root.key_id,
            "signature_base64": base64.b64encode(key.sign(rfc8785.dumps(manifest))).decode(),
        }
    ).encode()
    raw = archive(signature)
    signers = {root.key_id: root}
    return raw, validate_archive(io.BytesIO(raw), signers=signers, now=now), signers, now


@pytest.mark.parametrize("task_id,maximum", [("FX-001", 24), ("FX-002", 6), ("FX-003", 51)])
@pytest.mark.parametrize("mode", ["positive", "empty", "guardrail"])
def test_real_native_harbor_trial(signed_native_fixture, task_id, maximum, mode):
    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Dedicated native opt-in absent; not qualification evidence")
    raw, receipt, signers, now = signed_native_fixture
    folder = ROOT / ".local/benchmark-native" / uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
    target = folder / "actor.zip"
    compiled = compile_task(
        io.BytesIO(raw), receipt, task_id, fixture_binding(), target, signers=signers, now=now
    )
    task = next(task for task in receipt.parsed.manifest.tasks if task.id == task_id)
    private = ROOT / "fixtures/benchmark-bundle/fictional-points-v1/eval_pack" / task_id
    result = native_trial(target, compiled, task, private, folder, mode=mode)
    assert result["origin"] == "original_synthetic_software_conformance"
    assert result["binding_sha256"] == compiled.binding_sha256
    assert result["points"] == (maximum if mode == "positive" else 0)
    assert result["possible_points"] == maximum
    assert result["candidate_stopped_before_evaluation"]
    assert result["candidate_container"] != result["evaluator_container"]
    assert not result["candidate_mounts_private"] and not result["evaluator_mounts_actor"]
    assert result["provider_calls"] == 0
    assert result["seal_sha256"] and result["adapter_sha256"]
    assert (
        hashlib.sha256((folder / "native-receipt.json").read_bytes()).hexdigest()
        == result["native_receipt_sha256"]
    )
    assert result["control_checks"]["non_root_readonly_no_egress_cgroups"]
    assert result["control_checks"]["fresh_actor"]
    assert result["forbidden_access_attempts_denied"] == 4
    if mode == "positive":
        assert result["tool_calls"] == maximum
    if mode == "guardrail":
        assert result["denied_tool_calls"] == 1


@pytest.mark.parametrize("fault", ["package", "rules", "extra_private"])
def test_native_rejects_stale_package_or_evaluator_before_execution(signed_native_fixture, fault):
    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Explicit isolated native opt-in required")
    raw, receipt, signers, now = signed_native_fixture
    folder = ROOT / ".local/benchmark-native-negative" / uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
    package = folder / "actor.zip"
    compiled = compile_task(
        io.BytesIO(raw), receipt, "FX-001", fixture_binding(), package, signers=signers, now=now
    )
    private = folder / "changed-private"
    shutil.copytree(
        ROOT / "fixtures/benchmark-bundle/fictional-points-v1/eval_pack/FX-001", private
    )
    if fault == "package":
        with package.open("ab") as stream:
            stream.write(b"changed")
    elif fault == "rules":
        with (private / "rules.json").open("ab") as stream:
            stream.write(b"\n")
    else:
        (private / "unexpected.txt").write_text("Unreviewed fictional extra")
    with pytest.raises(ValueError, match="changed"):
        native_trial(
            package, compiled, receipt.parsed.manifest.tasks[0], private, folder, mode="positive"
        )
    assert not (folder / "trial.json").exists()
    assert not (folder / "native-receipt.json").exists()
