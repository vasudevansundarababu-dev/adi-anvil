"""Fixed private root-record resolver without API config or .env imports.

Uses the SAME original root-owned operator proof implementation/hash and store.
Source-root selection comes from this installed module, never environment/IPC.
No credential, root grant, new record, clock override or qualification is made.
"""

import hashlib
import os
import stat
import types
from datetime import datetime, timezone
from pathlib import Path

from anvil.marketing_native_boundary import marketing_native_gate
from anvil.marketing_native_records import _checked_opening_record_set

OPERATOR_PROOF_SHA256 = "98e21e6e0cd978cd470609e6c941edd00405eb319e7e164469e1e1857b6ac593"


def original_operator_repository():
    """Use the fixed, source-verified wheel layout or the actual source checkout.

    Neither ANVIL_ROOT, caller data nor the working directory selects proof
    authority. Installed wheels are checked against their root-owned sealed tree.
    """
    from anvil.qualification_resources import qualification_root

    return qualification_root()


def original_operator_store():
    source = Path(__file__)
    if source.resolve() != source:
        raise ValueError("marketing_private_installed_source_root_required")
    repository = original_operator_repository()
    path = repository / "services/harbor/src/anvil_harbor/operator_proof.py"
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
            )
            os.close(parent)
            parent = child
            info = os.fstat(parent)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError("marketing_private_root_source_directory_custody_required")
        fd = os.open(
            path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
        )
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != 0
            or before.st_nlink != 1
            or before.st_mode & 0o022
            or not 0 < before.st_size <= 1000000
        ):
            raise ValueError("marketing_private_original_operator_source_required")
        raw = bytearray()
        while True:
            chunk = os.read(fd, min(32768, 1000001 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > 1000000:
                raise ValueError("marketing_private_operator_source_capacity")
        after = os.fstat(fd)

        def identity(v):
            return (v.st_dev, v.st_ino, v.st_size, v.st_mtime_ns, v.st_ctime_ns)

        if (
            identity(before) != identity(after)
            or len(raw) != before.st_size
            or hashlib.sha256(raw).hexdigest() != OPERATOR_PROOF_SHA256
        ):
            raise ValueError("marketing_private_original_operator_source_changed")
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)
    module = types.ModuleType("anvil_private_pinned_operator_proof")
    exec(compile(bytes(raw), str(path), "exec"), module.__dict__)
    return module.OperatorProofStore(repository)


def resolve_private_marketing_records(request):
    marketing_native_gate()
    with original_operator_store() as store:
        return _checked_opening_record_set(request, store, now=datetime.now(timezone.utc))
