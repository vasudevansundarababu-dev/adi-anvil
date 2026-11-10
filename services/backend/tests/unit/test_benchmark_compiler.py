import base64
import io
import json
import os
import tomllib
import zipfile
from dataclasses import replace
from datetime import timedelta

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_benchmark_archive import FIXTURE, NOW, bundle, validate

from anvil.benchmark_bundle import TrustedSigner
from anvil.benchmark_compiler import compile_task, fixture_binding, seal_outputs


def signed_source():
    private = Ed25519PrivateKey.generate()
    root = TrustedSigner(
        "compiler-test",
        private.public_key().public_bytes_raw(),
        NOW - timedelta(days=1),
        NOW + timedelta(days=1),
    )
    manifest = json.loads((FIXTURE / "manifest.json").read_bytes())
    signature = json.dumps(
        {
            "profile": "ed25519-jcs-v1",
            "algorithm": "Ed25519",
            "key_id": root.key_id,
            "signature_base64": base64.b64encode(private.sign(rfc8785.dumps(manifest))).decode(),
        }
    ).encode()
    raw = bundle(signature=signature)
    signers = {root.key_id: root}
    return raw, validate(raw, signers=signers), signers


@pytest.mark.parametrize("task_id", ["FX-001", "FX-002", "FX-003"])
def test_compiler_is_reproducible_and_archive_is_actor_only(tmp_path, task_id):
    raw, receipt, signers = signed_source()
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    binding = fixture_binding()
    compiled = compile_task(
        io.BytesIO(raw), receipt, task_id, binding, first, signers=signers, now=NOW
    )
    repeated = compile_task(
        io.BytesIO(raw), receipt, task_id, binding, second, signers=signers, now=NOW
    )
    assert first.read_bytes() == second.read_bytes()
    assert compiled.archive_sha256 == repeated.archive_sha256
    assert compiled.binding_sha256 == repeated.binding_sha256
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        combined = b"".join(archive.read(name) for name in names)
        assert b"PRIVATE-FICTIONAL" not in combined
        assert b"eval_pack" not in combined and b"expected" not in combined
        for other in {"FX-001", "FX-002", "FX-003"} - {task_id}:
            assert other.encode() not in combined
        config = tomllib.loads(archive.read("task.toml").decode())
        assert config["verifier"]["environment_mode"] == "separate"
        assert config["environment"]["network_mode"] == "no-network"
        assert config["agent"]["user"] == "10001"
        assert "tests/evaluator.py" not in names
        assert any(name.startswith("environment/actor/runtime_pack/" + task_id) for name in names)


@pytest.mark.parametrize(
    "fault",
    ["unsigned", "changed_bytes", "unreviewed", "image", "implementation", "policy", "bank"],
)
def test_compile_failures_leave_no_published_archive(tmp_path, fault):
    raw, receipt, signers = signed_source()
    binding = fixture_binding()
    if fault == "unsigned":
        raw = bundle()
        receipt = validate(raw)
    elif fault == "changed_bytes":
        raw = bundle()
    else:
        field = {
            "unreviewed": "review_reference",
            "image": "image_digest",
            "implementation": "implementation_sha256",
            "policy": "policy_sha256",
            "bank": "bank_id",
        }[fault]
        binding = replace(binding, **{field: "" if fault == "unreviewed" else "changed"})
    target = tmp_path / "unpublished.zip"
    with pytest.raises(ValueError):
        compile_task(io.BytesIO(raw), receipt, "FX-001", binding, target, signers=signers, now=NOW)
    assert not target.exists()
    assert not list(tmp_path.glob(".compile-*"))


def test_sealed_outputs_are_hash_bound_independent_copies(tmp_path):
    raw, receipt, signers = signed_source()
    source, sealed = tmp_path / "outputs", tmp_path / "sealed"
    source.mkdir()
    (source / "answers.json").write_text('{"item-001":1}')
    (source / "report.md").write_text("Original fictional output")
    task = receipt.parsed.manifest.tasks[0]
    result = seal_outputs(source, sealed, task.outputs)
    assert len(result.files) == 2
    assert all(file.sha256 and file.byte_size for file in result.files)
    assert all((sealed / file.path).stat().st_mode & 0o222 == 0 for file in result.files)
    (source / "answers.json").write_text("changed")
    assert (sealed / "answers.json").read_text() == '{"item-001":1}'


@pytest.mark.parametrize("fault", ["symlink", "hardlink", "directory", "oversize", "parent_alias"])
def test_sealing_rejects_aliases_and_limits_without_publishing(tmp_path, fault):
    _, receipt, _ = signed_source()
    task = receipt.parsed.manifest.tasks[0]
    source, sealed = tmp_path / "outputs", tmp_path / "sealed"
    source.mkdir()
    payload = source / "answers.json"
    payload.write_text("{}")
    if fault == "symlink":
        payload.unlink()
        payload.symlink_to(tmp_path / "outside")
    elif fault == "hardlink":
        os.link(payload, source / "alias")
    elif fault == "directory":
        payload.unlink()
        payload.mkdir()
    elif fault == "oversize":
        next(output for output in task.outputs if output.path == "answers.json").max_bytes = 1
    else:
        moved = tmp_path / "other"
        source.rename(moved)
        source.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ValueError):
        seal_outputs(source, sealed, task.outputs)
    assert not sealed.exists()


def test_missing_outputs_have_explicit_absence_not_fabricated_files(tmp_path):
    _, receipt, _ = signed_source()
    source = tmp_path / "outputs"
    source.mkdir()
    result = seal_outputs(source, tmp_path / "sealed", receipt.parsed.manifest.tasks[0].outputs)
    assert result.files == ()
    assert set(result.missing) == {"answers.json", "report.md"}
    assert result.manifest_sha256
