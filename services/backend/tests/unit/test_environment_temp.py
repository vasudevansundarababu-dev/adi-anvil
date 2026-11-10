import os
import shutil
from pathlib import Path

import pytest

from anvil.environment_temp import workspace


@pytest.mark.parametrize("prefix", ["anvil-env-native-", "anvil-openenv-episode-"])
def test_native_paths_are_private_canonical_short_and_ignore_inherited_temp(prefix, monkeypatch):
    monkeypatch.setenv("TMPDIR", "/untrusted/nonexistent/long/temp")
    root = workspace(prefix)
    try:
        assert root.parent == Path("/tmp").resolve()
        assert root == root.resolve()
        assert root.stat().st_uid == os.getuid()
        assert root.stat().st_mode & 0o777 == 0o700
        assert len(str(root / "gateway.sock").encode()) < 100
    finally:
        shutil.rmtree(root)


def test_unknown_workspace_purpose_refused():
    with pytest.raises(ValueError):
        workspace("../../unrelated")


def test_cloud_native_uses_explicit_private_daemon_visible_parent(monkeypatch, tmp_path):
    monkeypatch.setenv("ANVIL_ENV", "cloud")
    monkeypatch.setenv("ANVIL_ENVIRONMENT_NATIVE_TMP_ROOT", str(tmp_path))
    tmp_path.chmod(0o700)
    root = workspace("anvil-env-native-")
    try:
        assert root.parent == tmp_path
        assert root.stat().st_mode & 0o777 == 0o700
    finally:
        shutil.rmtree(root)
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match="Unsafe cloud"):
        workspace("anvil-env-native-")


def test_cloud_native_refuses_missing_or_aliased_parent(monkeypatch, tmp_path):
    monkeypatch.setenv("ANVIL_ENV", "cloud")
    monkeypatch.delenv("ANVIL_ENVIRONMENT_NATIVE_TMP_ROOT", raising=False)
    with pytest.raises(ValueError, match="Explicit canonical"):
        workspace("anvil-env-native-")
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setenv("ANVIL_ENVIRONMENT_NATIVE_TMP_ROOT", str(alias))
    with pytest.raises(ValueError, match="Explicit canonical"):
        workspace("anvil-env-native-")
