"""Short private native workspace paths on both Linux and macOS."""

import os
import stat
import tempfile
from pathlib import Path


def workspace(prefix):
    if prefix not in {"anvil-env-native-", "anvil-openenv-episode-"}:
        raise ValueError("Unrecognized native workspace purpose")
    # Fixed OS /tmp ignores inherited TMPDIR and keeps Unix socket paths short.
    # macOS aliases /tmp to /private/tmp; resolve before native custody validation.
    root = Path(tempfile.mkdtemp(prefix=prefix, dir="/tmp")).resolve(strict=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Unsafe native workspace")
    return root
