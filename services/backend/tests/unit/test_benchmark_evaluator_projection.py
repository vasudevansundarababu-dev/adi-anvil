"""Reviewed evaluator-only projection; no Docker, SQL, candidates or paid calls."""

import os
import stat

import pytest

from anvil import benchmark_evaluator_native as native
from anvil.benchmark_evaluator_program import sha


def mode(path):
    return stat.S_IMODE(path.lstat().st_mode)


def test_restrictive_umask_exposes_only_reviewed_program_leaf(tmp_path):
    folder = tmp_path / "private-execution"
    folder.mkdir(mode=0o700)
    home = folder / "home"
    home.mkdir(mode=0o700)
    (home / "private-canary").write_text("must not be projected")
    os.chmod(home / "private-canary", 0o600)
    before = {path: mode(path) for path in (tmp_path, folder, home, home / "private-canary")}
    previous = os.umask(0o077)
    try:
        service = native.evaluator_program_projection(folder, sha(native.PROGRAM.read_bytes()))
        assert os.umask(0o077) == 0o077
    finally:
        os.umask(previous)
    assert mode(service) == 0o555
    script = service / "evaluator.py"
    assert mode(script) == 0o444
    assert script.read_bytes() == native.PROGRAM.read_bytes()
    assert script.stat().st_uid == os.getuid()
    assert set(service.iterdir()) == {script}
    assert all(mode(path) == original for path, original in before.items())


@pytest.mark.parametrize(
    "fault", ["hash", "existing", "symlink", "public_parent", "source_symlink", "source_hardlink"]
)
def test_unreviewed_or_nonfresh_projection_never_changes_permissions(tmp_path, monkeypatch, fault):
    folder = tmp_path / "private-execution"
    folder.mkdir(mode=0o700)
    expected = sha(native.PROGRAM.read_bytes())
    if fault == "hash":
        expected = "0" * 64
    elif fault == "existing":
        (folder / "service").mkdir(mode=0o700)
        (folder / "service/private-canary").write_text("never expose")
    elif fault == "symlink":
        (folder / "service").symlink_to(tmp_path, target_is_directory=True)
    elif fault == "public_parent":
        folder.chmod(0o755)
    else:
        source = tmp_path / "program.py"
        source.write_bytes(native.PROGRAM.read_bytes())
        alias = tmp_path / "alias.py"
        if fault == "source_symlink":
            alias.symlink_to(source)
        else:
            os.link(source, alias)
        monkeypatch.setattr(native, "PROGRAM", alias)
    before = {path: mode(path) for path in [folder, *folder.rglob("*")]}
    with pytest.raises((ValueError, FileExistsError)):
        native.evaluator_program_projection(folder, expected)
    assert {path: mode(path) for path in before} == before
    if fault not in {"existing", "symlink"}:
        assert not (folder / "service").exists()
