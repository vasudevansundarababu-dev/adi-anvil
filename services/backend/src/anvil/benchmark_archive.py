"""Bounded gzip/USTAR inspection. Members are hashed, never extracted or executed."""

import gzip
import hashlib
import tarfile
import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO

from anvil.benchmark_bundle import (
    MAX_EXPANDED_BYTES,
    MAX_FILE_BYTES,
    MAX_MANIFEST_BYTES,
    ParsedManifest,
    SignatureDecision,
    TrustedSigner,
    canonical_path,
    parse_manifest,
    unique_paths,
    verify_signature,
)

MAX_COMPRESSED_BYTES = 100 * 1024 * 1024
BLOCK = 512
CHUNK = 65536


class ArchiveError(ValueError):
    def __init__(self, code: str, *, status=422):
        super().__init__(code)
        self.code, self.status = code, status


class CountingInput:
    def __init__(self, source: BinaryIO, limit: int):
        self.source, self.limit = source, limit
        self.count, self.calls = 0, 0
        self.digest = hashlib.sha256()

    def read(self, size=-1):
        if size < 0:
            raise ArchiveError("unbounded_archive_read")
        self.calls += 1
        if self.calls > 32768:
            raise ArchiveError("archive_complexity_limit", status=413)
        data = self.source.read(size)
        self.count += len(data)
        if self.count > self.limit:
            raise ArchiveError("archive_byte_limit", status=413)
        self.digest.update(data)
        return data


@dataclass(frozen=True)
class MemberDigest:
    path: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class ValidatedArchive:
    archive_sha256: str
    parsed: ParsedManifest
    signature: SignatureDecision
    member_count: int
    members: tuple[MemberDigest, ...]


def _exact(stream, size):
    parts, remaining = [], size
    while remaining:
        value = stream.read(min(remaining, CHUNK))
        if not value:
            raise ArchiveError("truncated_archive")
        parts.append(value)
        remaining -= len(value)
    return b"".join(parts)


def validate_archive(
    source: BinaryIO,
    *,
    signers: dict[str, TrustedSigner],
    now: datetime,
    max_compressed=MAX_COMPRESSED_BYTES,
    max_expanded=MAX_EXPANDED_BYTES,
    max_file=MAX_FILE_BYTES,
    max_members=5000,
) -> ValidatedArchive:
    compressed = CountingInput(source, max_compressed)
    members, raw_manifest, signature_raw = {}, None, None
    try:
        with gzip.GzipFile(fileobj=compressed, mode="rb") as decompressor:
            expanded = CountingInput(decompressor, max_expanded)
            while True:
                header = _exact(expanded, BLOCK)
                if header == bytes(BLOCK):
                    if _exact(expanded, BLOCK) != bytes(BLOCK):
                        raise ArchiveError("malformed_tar_terminator")
                    padding = 0
                    while chunk := expanded.read(CHUNK):
                        padding += len(chunk)
                        if any(chunk) or padding > 10240:
                            raise ArchiveError("undeclared_tar_trailer")
                    break
                if len(members) == max_members:
                    raise ArchiveError("archive_member_limit", status=413)
                if header[257:263] != b"ustar\0" or header[263:265] != b"00":
                    raise ArchiveError("unsupported_tar_profile")
                info = tarfile.TarInfo.frombuf(header, "utf-8", "strict")
                if not info.isreg() or info.linkname or info.mode & 0o7000:
                    raise ArchiveError("nonregular_archive_member")
                canonical_path(info.name)
                if info.name in members:
                    raise ArchiveError("duplicate_archive_member")
                if info.size < 0 or info.size > max_file:
                    raise ArchiveError("archive_member_byte_limit", status=413)
                if (
                    info.name in {"manifest.json", "signature.json"}
                    and info.size > MAX_MANIFEST_BYTES
                ):
                    raise ArchiveError("metadata_byte_limit", status=413)
                member_hash, remaining, metadata = hashlib.sha256(), info.size, []
                while remaining:
                    chunk = _exact(expanded, min(remaining, CHUNK))
                    member_hash.update(chunk)
                    if info.name in {"manifest.json", "signature.json"}:
                        metadata.append(chunk)
                    remaining -= len(chunk)
                if any(_exact(expanded, (-info.size) % BLOCK)):
                    raise ArchiveError("nonzero_member_padding")
                members[info.name] = MemberDigest(info.name, info.size, member_hash.hexdigest())
                if info.name == "manifest.json":
                    raw_manifest = b"".join(metadata)
                elif info.name == "signature.json":
                    signature_raw = b"".join(metadata)
    except ArchiveError:
        raise
    except (ValueError, UnicodeError, EOFError, OSError, tarfile.TarError, zlib.error) as exc:
        raise ArchiveError("malformed_archive") from exc
    if raw_manifest is None:
        raise ArchiveError("missing_manifest")
    try:
        unique_paths(list(members))
        parsed = parse_manifest(raw_manifest)
        signature = verify_signature(raw_manifest, signature_raw, signers=signers, now=now)
    except ValueError as exc:
        raise ArchiveError("invalid_manifest_or_signature") from exc
    payloads = {
        name: member
        for name, member in members.items()
        if name not in {"manifest.json", "signature.json"}
    }
    if set(payloads) != {file.path for file in parsed.manifest.files}:
        raise ArchiveError("manifest_member_set_mismatch")
    for file in parsed.manifest.files:
        actual = payloads[file.path]
        if actual.byte_size != file.byte_size or actual.sha256 != file.sha256:
            raise ArchiveError("manifest_member_integrity_mismatch")
    return ValidatedArchive(
        compressed.digest.hexdigest(), parsed, signature, len(members), tuple(payloads.values())
    )
