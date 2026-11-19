"""Lexical byte proof for nonspending Golden software SQL operations only.

No ambient/global cache, API input, paid admission, DB authority or qualification
receipt is represented here. Both full scans occur inside the caller's SQL
savepoint, so a changed closure aborts before the operation can commit.
"""

import hashlib
import os
import stat
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from anvil import qualification_resources as resources


def _identity(path):
    info = path.lstat()
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _witness(root, names):
    paths = {root / name for name in names}
    if root == resources.SEALED_ROOT:
        for base in (resources.INSTALLED_ROOT / "anvil", resources.INSTALLED_ROOT / "anvil_harbor",
                     root / "services/backend/src/anvil", root / "services/harbor/src/anvil_harbor",
                     resources.INSTALLED_ROOT / "beartype", resources.INSTALLED_ROOT / "beartype-0.23.1.dist-info"):
            for parent, directories, files in os.walk(base, followlinks=False):
                directories[:] = [name for name in directories if name != "__pycache__"]
                paths.add(Path(parent))
                paths.update(Path(parent) / name for name in files if not name.endswith(".pyc"))
                if len(paths) > 20000:
                    raise RuntimeError("Software witness inventory exceeds bound")
    # Ancestor custody changes and same-bytes/inode replacement are failures too.
    for path in tuple(paths):
        paths.update(path.parents)
    result = {}
    total = 0
    for path in sorted(paths):
        before = _identity(path)
        if not (stat.S_ISREG(before[2]) or stat.S_ISDIR(before[2])):
            raise RuntimeError("Unexpected software resource type")
        if stat.S_ISREG(before[2]):
            total += before[6]
            if before[6] > resources.MAX_MEMBER_BYTES or total > 512 * 1024 * 1024:
                raise RuntimeError("Software witness bytes exceed bound")
            content = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            content = None
        if _identity(path) != before:
            raise RuntimeError("Software resource changed while measuring")
        result[str(path)] = (before, content)
    return MappingProxyType(result)


@dataclass(frozen=True, slots=True)
class _Proof:
    _root: Path
    _digests: object
    _witnesses: object
    _pid: int
    _thread: int
    _deadline: float
    _connection: object
    _active: bool = True

    def _check(self):
        if (not self._active or os.getpid() != self._pid
                or threading.get_ident() != self._thread or time.monotonic() >= self._deadline):
            raise RuntimeError("Inactive or foreign software resource operation")

    def root(self):
        self._check()
        return self._root

    def sha256(self, relative):
        self._check()
        try:
            return self._digests[relative]
        except KeyError:
            raise RuntimeError("Resource outside software operation inventory") from None


def checked_root(proof):
    if type(proof) is not _Proof:
        raise RuntimeError("Exact software operation proof required")
    return proof.root()


def checked_sha256(proof, relative):
    checked_root(proof)
    return proof.sha256(relative)


def check_connection(proof, connection):
    checked_root(proof)
    if proof._connection is not connection:
        raise RuntimeError("Foreign software operation connection")


@contextmanager
def software_resources(connection):
    """Only trusted code creates this proof; callers cannot select paths/root/hash."""
    from anvil.evaluator_configurations import _source_paths as adapter_paths
    from anvil.golden_kyc_source import _source_paths as golden_paths

    root = resources.qualification_root()
    names = {str(path.relative_to(root)) for path in golden_paths(root)}
    for adapter in ("builtin", "zen", "opa-local"):
        names.update(adapter_paths(adapter))
    # qualification_path retains the ordinary resource custody/size checks.
    digests = MappingProxyType({name: hashlib.sha256(resources.qualification_path(root, name).read_bytes()).hexdigest()
                               for name in sorted(names)})
    proof = _Proof(root, digests, _witness(root, names), os.getpid(), threading.get_ident(), time.monotonic() + 300, connection)
    try:
        yield proof
        proof._check()
        # Includes late-loaded modules, actual loader bytecode and complete RECORD.
        if resources.qualification_root() != root or _witness(root, names) != proof._witnesses:
            raise RuntimeError("Software resource closure changed before commit")
        if any(hashlib.sha256(resources.qualification_path(root, name).read_bytes()).hexdigest() != value
               for name, value in proof._digests.items()):
            raise RuntimeError("Software resource digest changed before commit")
        proof._check()
    finally:
        object.__setattr__(proof, "_active", False)
