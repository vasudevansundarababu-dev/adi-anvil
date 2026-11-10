"""Private bounded intake staging. Never holds database/financial row locks."""

import fcntl
import os
import stat
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from starlette.requests import ClientDisconnect

from anvil.benchmark_archive import MAX_COMPRESSED_BYTES, ArchiveError, validate_archive
from anvil.benchmark_storage import stage_private, stage_private_stream, vault_root
from anvil.benchmark_trust import load_trust_policy
from anvil.request_limits import RequestBodyTooLarge


def _directory(path):
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RuntimeError("Unsafe benchmark intake directory")
    return path


def _permit(stack, folder, slots):
    for index in range(slots):
        descriptor = os.open(
            folder / f"slot-{index}", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
        )
        stream = os.fdopen(descriptor, "rb+")
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
            stream.close()
            raise RuntimeError("Unsafe intake quota slot")
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            stream.close()
            continue
        stack.enter_context(stream)
        return
    raise HTTPException(429, "Benchmark intake concurrency limit reached")


@contextmanager
def intake_file(project):
    root = _directory(vault_root() / ".intake")
    folder = _directory(root / str(UUID(str(project))))
    with ExitStack() as stack:
        _permit(stack, root, 4)
        _permit(stack, folder, 2)
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".upload-", delete=False) as stream:
            path = Path(stream.name)
            try:
                yield stream
            finally:
                path.unlink()


async def spool(request, stream):
    size = 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_COMPRESSED_BYTES:
                raise RequestBodyTooLarge()
            stream.write(chunk)
    except RequestBodyTooLarge as exc:
        raise HTTPException(413, "Benchmark archive exceeds size limit") from exc
    except ClientDisconnect as exc:
        raise HTTPException(400, "Benchmark upload interrupted") from exc
    if size == 0:
        raise HTTPException(422, "Benchmark archive is empty")
    stream.flush()
    os.fsync(stream.fileno())
    stream.seek(0)


def prepare_original(project, stream):
    prepared = stage_private_stream(project, stream, "benchmark_raw", "application/gzip")
    stream.seek(0)
    return prepared


def inspect_original(project, stream, *, now, expected_sha256):
    result = validate_archive(stream, signers=load_trust_policy(), now=now)
    if result.archive_sha256 != expected_sha256:
        raise ArchiveError("staged_original_changed", status=409)
    raw = stage_private(project, result.parsed.raw, "benchmark_raw", "application/json")
    canonical = stage_private(project, result.parsed.canonical, "benchmark_raw", "application/json")
    return result, raw, canonical
