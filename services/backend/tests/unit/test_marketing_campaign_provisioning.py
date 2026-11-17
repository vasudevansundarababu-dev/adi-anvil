"""Manufactured local files; no real dataset or qualification is produced."""

import hashlib
import json

import pytest

from anvil.marketing_campaign_provisioning import candidate


def fixture(tmp_path, extra=None):
    files = {
        f"cases/{case}/case.json": json.dumps({"case_id": case, "focus_locale": "en-US"}).encode()
        for case in ("GT2-R01", "GT2-R02")
    }
    for name, raw in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    hashes.update(extra or {})
    data = json.dumps(hashes).encode()
    (tmp_path / "checksums.json").write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def build(tmp_path, fingerprint):
    return candidate(
        tmp_path,
        fingerprint,
        dataset_key="software-pair",
        version="fixture-1",
        source_sha256="a" * 64,
    )


def test_candidate_preserves_two_cases_without_self_qualification_or_private_paths(tmp_path):
    result = build(tmp_path, fixture(tmp_path))
    assert result["manifest"]["case_count"] == 2
    assert result["fixture_manifest"]["qualification"] == "not_granted"
    assert str(tmp_path) not in str(result)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "cases/../escape", "cases\\escape"])
def test_checksum_path_cannot_escape_private_pack(tmp_path, name):
    fingerprint = fixture(tmp_path, {name: "b" * 64})
    with pytest.raises(ValueError):
        build(tmp_path, fingerprint)


def test_changed_content_and_unreviewed_checksum_file_are_denied(tmp_path):
    fingerprint = fixture(tmp_path)
    with pytest.raises(ValueError, match="reviewed"):
        build(tmp_path, "f" * 64)
    (tmp_path / "cases/GT2-R01/case.json").write_text("{}")
    with pytest.raises(ValueError, match="immutable content"):
        build(tmp_path, fingerprint)


def test_symlinked_fixture_cannot_become_verified_source(tmp_path):
    fingerprint = fixture(tmp_path)
    source = tmp_path / "cases/GT2-R01/case.json"
    stored = tmp_path / "elsewhere.json"
    source.rename(stored)
    source.symlink_to(stored)
    with pytest.raises(ValueError, match="symlink"):
        build(tmp_path, fingerprint)
