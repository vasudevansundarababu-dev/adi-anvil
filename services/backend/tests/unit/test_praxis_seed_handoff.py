import hashlib

import pytest

from anvil.praxis_seed_handoff import verify


def test_manifest_exact_bytes_and_ready_gate():
    files = {"seed-export/index.json": b"{}"}
    manifest = (hashlib.sha256(b"{}").hexdigest() + "  seed-export/index.json\n").encode()
    assert verify(b"**Status: READY (version1).**", manifest, files)
    assert verify(b"**Status: READY**", manifest, files)
    for status, inventory, contents in (
        (b"**Status: IN PROGRESS**\nWhen READY then import", manifest, files),
        (b"**Status: READY**", manifest, {"seed-export/index.json": b"changed"}),
        (b"**Status: READY**", manifest + manifest, files),
        (b"**Status: READY**", manifest, {**files, "seed-export/extra.json": b"{}"}),
        (b"**Status: READY**", manifest.replace(b"index.json", b"../escape"), files),
    ):
        with pytest.raises(ValueError):
            verify(status, inventory, contents)
