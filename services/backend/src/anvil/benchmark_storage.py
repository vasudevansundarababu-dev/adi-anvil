"""Private, project-addressed benchmark objects; no generic artifact downloads."""

import fcntl
import hashlib
import io
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from fastapi import HTTPException

from anvil import artifacts
from anvil.config import ROOT, setting
from anvil.db import one, uid

PRIVATE_CLASSES = artifacts.BENCHMARK_PRIVATE_CLASSES


def vault_root() -> Path:
    root = Path(setting("ANVIL_BENCHMARK_VAULT_ROOT"))
    if not root.is_absolute() or not root.is_relative_to(ROOT):
        raise RuntimeError("Benchmark vault must be explicitly configured inside this installation")
    ordinary = artifacts.storage_root().resolve()
    if root.resolve().is_relative_to(ordinary) or ordinary.is_relative_to(root.resolve()):
        raise RuntimeError("Benchmark vault and ordinary artifact storage must be disjoint")
    for path in [root, *root.parents]:
        if path.is_symlink():
            raise RuntimeError("Benchmark vault paths cannot contain symlinks")
        if path == ROOT:
            break
    root.mkdir(mode=0o700, exist_ok=True)
    info = root.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RuntimeError("Benchmark vault requires owner-only installation storage")
    return root


def _folder(root: Path, project: str, classification: str) -> Path:
    for name in [project, classification]:
        root = root / name
        root.mkdir(mode=0o700, exist_ok=True)
        info = root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise RuntimeError("Unsafe private object directory")
    return root


@dataclass(frozen=True)
class PreparedPrivate:
    artifact_id: str
    project_id: str
    classification: str
    sha256: str
    byte_size: int
    object_key: str
    mime_type: str


def stage_private(
    project, data: bytes, classification: str, mime="application/octet-stream"
) -> PreparedPrivate:
    return stage_private_stream(project, io.BytesIO(data), classification, mime)


def stage_private_stream(
    project, source: BinaryIO, classification: str, mime="application/octet-stream"
) -> PreparedPrivate:
    if classification not in PRIVATE_CLASSES:
        raise ValueError("Expected benchmark private access class")
    project = str(UUID(str(project)))
    folder = _folder(vault_root(), project, classification)
    digest, byte_size = hashlib.sha256(), 0
    descriptor = os.open(folder / ".write.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "rb+") as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
            raise RuntimeError("Unsafe private staging lock")
        # The atomic-link staging name briefly shares its inode with the final object.
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".staging-", delete=False) as stream:
            temporary = Path(stream.name)
            try:
                while chunk := source.read(65536):
                    byte_size += len(chunk)
                    if byte_size > 500 * 1024 * 1024:
                        raise ValueError("Private object exceeds limit")
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
                hexadecimal = digest.hexdigest()
                path = folder / hexadecimal
                try:
                    os.link(temporary, path, follow_symlinks=False)
                except FileExistsError:
                    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                    with os.fdopen(descriptor, "rb") as existing:
                        info = os.fstat(existing.fileno())
                        if (
                            not stat.S_ISREG(info.st_mode)
                            or info.st_nlink != 1
                            or info.st_uid != os.geteuid()
                            or info.st_mode & 0o077
                            or info.st_size != byte_size
                        ):
                            raise HTTPException(409, "Private object integrity mismatch")
                        old_hash = hashlib.sha256()
                        while chunk := existing.read(65536):
                            old_hash.update(chunk)
                        if old_hash.hexdigest() != hexadecimal:
                            raise HTTPException(409, "Private object integrity mismatch")
            finally:
                temporary.unlink()
        directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return PreparedPrivate(
        uid(),
        project,
        classification,
        hexadecimal,
        byte_size,
        f"benchmark-vault/{project}/{classification}/{hexadecimal}",
        mime,
    )


def bind_private(c, prepared: PreparedPrivate, *, created_by) -> str:
    # Staging/hashing must precede project/run/finance row locks; this phase is SQL-only.
    existing = one(
        c,
        "SELECT id FROM anvil.artifacts WHERE project_id=%s AND classification=%s AND sha256=%s",
        (prepared.project_id, prepared.classification, prepared.sha256),
    )
    if existing:
        return str(existing["id"])
    claim = one(c, "SELECT nullif(current_setting('anvil.user',true),'') AS user_id")
    if claim["user_id"] != str(created_by):
        raise HTTPException(403, "Private object author must match current identity")
    row = one(
        c,
        "INSERT INTO anvil.artifacts(id,project_id,object_key,sha256,byte_size,mime_type,classification,scan_status,origin,uploaded_by) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,'quarantined','restricted_source',%s) "
        "ON CONFLICT(project_id,classification,sha256) WHERE classification IN "
        "('benchmark_raw','benchmark_eval','benchmark_judge','benchmark_trace') DO NOTHING RETURNING id",
        (
            prepared.artifact_id,
            prepared.project_id,
            prepared.object_key,
            prepared.sha256,
            prepared.byte_size,
            prepared.mime_type,
            prepared.classification,
            created_by,
        ),
    )
    if row is None:
        row = one(
            c,
            "SELECT id FROM anvil.artifacts WHERE project_id=%s AND classification=%s AND sha256=%s",
            (prepared.project_id, prepared.classification, prepared.sha256),
        )
    if row is None:
        raise HTTPException(409, "Private object binding conflict")
    return str(row["id"])


def store_private(
    c, project, data: bytes, classification: str, *, created_by, mime="application/octet-stream"
) -> str:
    return bind_private(
        c, stage_private(project, data, classification, mime), created_by=created_by
    )


def read_private(c, artifact_id) -> bytes:
    artifact = one(c, "SELECT * FROM anvil.artifacts WHERE id=%s", (artifact_id,))
    if artifact is None:
        raise HTTPException(404, "Private artifact not found")
    if artifact["classification"] not in PRIVATE_CLASSES:
        raise HTTPException(403, "Not a private benchmark artifact")
    expected = f"benchmark-vault/{artifact['project_id']}/{artifact['classification']}/{artifact['sha256']}"
    if artifact["object_key"] != expected:
        raise HTTPException(403, "Invalid private object binding")
    root = vault_root()
    relative = artifact["object_key"].removeprefix("benchmark-vault/")
    path = root / relative
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise HTTPException(403, "Invalid private object location")
        if parent == root:
            break
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_size != artifact["byte_size"]
        ):
            raise HTTPException(409, "Private object integrity mismatch")
        data = stream.read()
    if hashlib.sha256(data).hexdigest() != artifact["sha256"]:
        raise HTTPException(409, "Private object integrity mismatch")
    return data
