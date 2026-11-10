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
