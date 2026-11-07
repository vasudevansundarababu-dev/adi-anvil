import base64
import gzip
import hashlib
import io
import json
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from anvil.benchmark_archive import ArchiveError, validate_archive
from anvil.benchmark_bundle import TrustedSigner

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures/benchmark-bundle/fictional-points-v1"
NOW = datetime(2026, 11, 7, 18, tzinfo=timezone.utc)


def bundle(*, overrides=None, extra=None, signature=None, format=tarfile.USTAR_FORMAT):
    overrides = overrides or {}
    members = [
        (str(p.relative_to(FIXTURE)), p.read_bytes())
        for p in sorted(FIXTURE.rglob("*"))
        if p.is_file()
    ]
    if signature is not None:
        members.append(("signature.json", signature))
    members += extra or []
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=format) as archive:
        for name, data in members:
            data = overrides.get(name, data)
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(data))
    return gzip.compress(raw.getvalue(), mtime=0)


def validate(raw, **kwargs):
    return validate_archive(io.BytesIO(raw), signers=kwargs.pop("signers", {}), now=NOW, **kwargs)


def test_original_unsigned_fixture_has_exact_hashes_and_quarantines():
    raw = bundle()
    result = validate(raw)
    assert result.archive_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.signature.status == "quarantined_unsigned"
    assert result.member_count == 28
    assert result.parsed.manifest.bank.id == "fictional-points"
    assert len(result.members) == len(result.parsed.manifest.files)


def test_real_external_trust_root_verifies_and_bundle_cannot_install_a_root():
    private = Ed25519PrivateKey.generate()
    root = TrustedSigner(
        "test-root",
        private.public_key().public_bytes_raw(),
        NOW - timedelta(days=1),
        NOW + timedelta(days=1),
    )
    manifest = json.loads((FIXTURE / "manifest.json").read_bytes())
    signature = json.dumps(
        {
            "profile": "ed25519-jcs-v1",
            "algorithm": "Ed25519",
            "key_id": root.key_id,
            "signature_base64": base64.b64encode(private.sign(rfc8785.dumps(manifest))).decode(),
        }
    ).encode()
    raw = bundle(signature=signature)
    assert validate(raw, signers={root.key_id: root}).signature.status == "verified"
    assert validate(raw).signature.status == "quarantined_unknown_signer"


@pytest.mark.parametrize(
    "name", ["../escape", "/absolute", "a\\b", "a/./b", "a//b", "a/.hidden", "a/é", "a/autorun.sh"]
)
def test_unsafe_tar_names_reject_without_extracting(name):
    with pytest.raises(ArchiveError):
        validate(bundle(extra=[(name, b"inert fixture")]))


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate",
        "case_alias",
        "undeclared",
        "hash",
        "missing_manifest",
        "gzip_truncated",
        "tar_trailing",
        "pax",
    ],
)
def test_aliases_incomplete_or_corrupt_archives_reject(kind):
    prompt = "runtime_pack/FX-001/prompt.md"
    if kind == "duplicate":
        raw = bundle(extra=[(prompt, b"duplicate")])
    elif kind == "case_alias":
        raw = bundle(extra=[(prompt.upper(), b"duplicate")])
    elif kind == "undeclared":
        raw = bundle(extra=[("runtime_pack/FX-001/extra.txt", b"undeclared")])
    elif kind == "hash":
        raw = bundle(overrides={prompt: b"tampered"})
    elif kind == "missing_manifest":
        raw = bundle(overrides={"manifest.json": b"{}"})
    elif kind == "gzip_truncated":
        raw = bundle()[:-9]
    elif kind == "tar_trailing":
        raw = gzip.compress(gzip.decompress(bundle()) + b"extra-nonzero-data")
    else:
        raw = bundle(
            extra=[("a" * 150, b"pax is intentionally unsupported")], format=tarfile.PAX_FORMAT
        )
    with pytest.raises(ArchiveError):
        validate(raw)


@pytest.mark.parametrize(
    "kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE]
)
def test_special_members_and_links_never_extract_or_execute(kind):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        info = tarfile.TarInfo("runtime_pack/FX-001/special")
        info.type = kind
        info.linkname = "/not-used"
        archive.addfile(info)
    with pytest.raises(ArchiveError):
        validate(gzip.compress(raw.getvalue()))


def test_enforced_small_limits_exercise_actual_stream_bytes_and_member_count():
    raw = bundle()
    for limits in [
        dict(max_compressed=10),
        dict(max_expanded=2048),
        dict(max_file=100),
        dict(max_members=2),
    ]:
        with pytest.raises(ArchiveError):
            validate(raw, **limits)


def test_repacking_preserves_manifest_but_not_original_archive_identity():
    raw = bundle()
    repacked = gzip.compress(gzip.decompress(raw), mtime=1)
    a, b = validate(raw), validate(repacked)
    assert a.parsed.canonical_sha256 == b.parsed.canonical_sha256
    assert a.archive_sha256 != b.archive_sha256


def test_gzip_header_cannot_force_unbounded_single_byte_metadata_reads():
    raw = bytearray(bundle())
    raw[3] |= 8
    raw[10:10] = b"x" * 40000 + bytes(1)
    with pytest.raises(ArchiveError) as exc:
        validate(raw)
    assert exc.value.code == "archive_complexity_limit"
