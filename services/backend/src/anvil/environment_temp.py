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
    parent = Path("/tmp")
    if prefix == "anvil-env-native-" and os.environ.get("ANVIL_ENV") == "cloud":
        # Docker's daemon must see this path outside the worker's PrivateTmp.
        parent = Path(os.environ.get("ANVIL_ENVIRONMENT_NATIVE_TMP_ROOT", ""))
        if not parent.is_absolute() or parent.resolve(strict=True) != parent:
            raise ValueError("Explicit canonical cloud native workspace required")
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Unsafe cloud native workspace parent")
    root = Path(tempfile.mkdtemp(prefix=prefix, dir=parent)).resolve(strict=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Unsafe native workspace")
    return root
