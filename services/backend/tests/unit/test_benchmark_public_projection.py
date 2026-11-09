"""Actual compiled public input permissions; no native containers or model calls."""

import io
import os
import stat
import zipfile

import pytest
from test_benchmark_archive import NOW
from test_benchmark_compiler import signed_source

from anvil.benchmark_compiler import compile_task, fixture_binding
from anvil.benchmark_qualification import public_actor_projection


@pytest.fixture
def extracted(tmp_path):
    raw, receipt, signers = signed_source()
    task = receipt.parsed.manifest.tasks[0]
    package = tmp_path / "public.zip"
    compiled = compile_task(
        io.BytesIO(raw), receipt, task.id, fixture_binding(), package, signers=signers, now=NOW
    )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    (private / "secret").write_text("private evaluator must remain private")
    os.chmod(private / "secret", 0o600)
    actor = tmp_path / "task"
    actor.mkdir(mode=0o700)
    previous = os.umask(0o077)
    try:
        with zipfile.ZipFile(package) as archive:
            for entry in archive.infolist():
                target = actor / entry.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as outgoing:
                    outgoing.write(archive.read(entry))
    finally:
        os.umask(previous)
    return actor, compiled, task, private


def modes(root):
    return {str(path): stat.S_IMODE(path.lstat().st_mode) for path in [root, *root.rglob("*")]}


def test_restrictive_umask_only_declared_mounted_inputs_become_readable(extracted):
    actor, compiled, task, private = extracted
    root = actor / "environment/actor/runtime_pack" / task.id
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600 for path in root.rglob("*") if path.is_file()
    )
    before_private = modes(private)
    ancestors = {
        path: stat.S_IMODE(path.stat().st_mode)
        for path in root.parents
        if path.is_relative_to(actor)
    }
    before_files = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    previous = os.umask(0o077)
    try:
        assert public_actor_projection(actor, compiled, task) == root
        assert os.umask(0o077) == 0o077
    finally:
        os.umask(previous)
    assert {path: path.read_bytes() for path in before_files} == before_files
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in before_files)
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o555
        for path in [root, *root.rglob("*")]
        if path.is_dir()
    )
    assert all(stat.S_IMODE(path.stat().st_mode) == mode for path, mode in ancestors.items())
    assert modes(private) == before_private
    assert stat.S_IMODE(actor.stat().st_mode) == 0o700


@pytest.mark.parametrize(
    "fault",
    ["tampered", "missing", "extra", "extra_directory", "symlink", "hardlink", "projection"],
)
def test_invalid_public_input_tree_fails_before_any_permission_changes(extracted, fault):
    actor, compiled, task, private = extracted
    root = actor / "environment/actor/runtime_pack" / task.id
    target = root / "items.json"
    if fault == "tampered":
        target.write_bytes(target.read_bytes() + b" ")
    elif fault == "missing":
        target.unlink()
    elif fault == "extra":
        (root / "unexpected-private.txt").write_text("must not expose")
    elif fault == "extra_directory":
        (root / "unexpected").mkdir(mode=0o700)
    elif fault == "symlink":
        target.unlink()
        target.symlink_to(private / "secret")
    elif fault == "hardlink":
        os.link(target, actor / "alias")
    else:
        (actor / "actor.json").write_text("{}")
    before = modes(actor)
    before_private = modes(private)
    with pytest.raises((ValueError, KeyError, FileNotFoundError)):
        public_actor_projection(actor, compiled, task)
    assert modes(actor) == before
    assert modes(private) == before_private
