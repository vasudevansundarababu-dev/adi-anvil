"""Exercise the real pure mount validator without requiring Harbor imports."""
import ast
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def setup(tmp_path):
    source = Path(__file__).resolve().parents[3] / "harbor/src/anvil_harbor/sme.py"
    tree = ast.parse(source.read_text())
    function = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "owned_log_mounts")
    namespace = {"os": os, "stat": stat, "Path": Path}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    trial = root / "trials/synthetic"
    paths = SimpleNamespace(trial_dir=trial)
    config = {"trial_name": "synthetic"}
    mounts = [{"type": "bind", "source": str(path), "target": target, "bind": {"selinux": "z"}}
              for target, path in (("/logs/verifier", trial / "verifier"), ("/logs/agent", trial / "agent"),
                                   ("/logs/artifacts", trial / "artifacts/logs/artifacts"))]
    return namespace["owned_log_mounts"], root, paths, config, mounts


def test_exact_actor_and_verifier_explicit_mounts_leave_proof_parents_private(setup):
    check, root, paths, config, mounts = setup
    actor = check(root, config, root / "task/environment", "environment", paths, mounts)
    verifier = check(root, config, root / "task/tests", "tests", paths, mounts[:1])
    assert actor == mounts[1:] and verifier == mounts[:1]
    assert root.stat().st_mode & 0o777 == 0o700
    assert paths.trial_dir.stat().st_mode & 0o777 == 0o700
    assert (paths.trial_dir / "artifacts").stat().st_mode & 0o777 == 0o700
    assert all(Path(m["source"]).stat().st_mode & 0o777 == 0o777 for m in [*actor, *verifier])
    assert not (root / "private").exists() and not (root / "sealed").exists()


@pytest.mark.parametrize("mutation", ["foreign_ignored_verifier", "duplicate", "extra_option", "foreign_trial", "symlink", "writable_parent"])
def test_foreign_or_aliased_mounts_never_enter_base(setup, mutation, tmp_path):
    check, root, paths, config, mounts = setup
    if mutation == "foreign_ignored_verifier":
        mounts[0]["source"] = str(tmp_path)
    elif mutation == "duplicate":
        mounts.append(mounts[-1])
    elif mutation == "extra_option":
        mounts[1]["read_only"] = False
    elif mutation == "foreign_trial":
        paths.trial_dir = tmp_path
    elif mutation == "symlink":
        (root / "trials").symlink_to(tmp_path, target_is_directory=True)
    else:
        (root / "trials").mkdir(mode=0o777)
        (root / "trials").chmod(0o777)
    with pytest.raises(ValueError):
        check(root, config, root / "task/environment", "environment", paths, mounts)


def test_rejected_projection_is_private_distinct_and_never_an_accepted_proof(tmp_path):
    source = Path(__file__).resolve().parents[3] / "harbor/src/anvil_harbor/sme.py"
    function = next(item for item in ast.parse(source.read_text()).body
                    if isinstance(item, ast.FunctionDef) and item.name == "write_compose_snapshot")
    namespace = {"os": os, "stat": stat, "Path": Path}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    write = namespace["write_compose_snapshot"]
    root = tmp_path / "private-trial"
    root.mkdir(mode=0o700)
    raw = b'{"services":{"main":{"synthetic":"rejected"}}}'
    path = write(root, "environment", raw, phase="preflight", rejected=True)
    assert path.name == "sme-rejected-preflight-compose-environment.json"
    assert path.read_bytes() == raw and path.stat().st_mode & 0o777 == 0o600
    assert not (root / "sme-preflight-compose-environment.json").exists()
    assert not (root / "sme-compose-environment.json").exists()
    with pytest.raises(FileExistsError):
        write(root, "environment", raw, phase="preflight", rejected=True)
    with pytest.raises(ValueError):
        write(root, "environment", raw, rejected="true")
    with pytest.raises(ValueError):
        write(root, "tests", b"x" * 1048577, rejected=True)
