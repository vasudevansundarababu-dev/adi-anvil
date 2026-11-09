"""Synthetic parser contracts only: these bytes are not native execution evidence."""

import hashlib
import io
import json
import tarfile

import pytest

from anvil.benchmark_history_import import parse_packet


def packet(*, authority=False, revoke=True, duplicate=False, extra=False, corrupt=False):
    files = {
        "baseline-summary.json": json.dumps(
            {
                "exit_code": 0,
                "source_sha": "a" * 40,
                "source_changes_after": [],
                "started_at": "2026-11-09T00:00:00+00:00",
            }
        ).encode()
    }
    refs = []
    for n in range(27):
        value = {
            "origin": "original_synthetic_software_conformance",
            "task_id": "FX-001",
            "mode": "positive",
            "binding_sha256": "b" * 64,
            "candidate_stopped_before_evaluation": True,
            "candidate_mounts_private": False,
            "evaluator_mounts_actor": False,
            "control_checks": {"fresh_actor": True, "non_root_readonly_no_egress_cgroups": True},
            "synthetic_parser_case": n,
        }
        raw = json.dumps(value).encode()
        sha = hashlib.sha256(raw).hexdigest()
        files["trials/" + sha + ".json"] = raw
        refs.append(
            {"sha256": sha, "task_id": "FX-001", "mode": "positive", "binding_sha256": "b" * 64}
        )
    manifest = {
        "profile": "HISTORICAL_NATIVE_BASELINE_EVIDENCE_ONLY",
        "current_qualification_authority": authority,
        "intentional_signer_revocation_preserved": revoke,
        "source_sha": "a" * 40,
        "trial_receipt_count": 27,
        "trial_receipts": refs,
        "files": {
            k: {"sha256": hashlib.sha256(v).hexdigest(), "byte_size": len(v)}
            for k, v in files.items()
        },
    }
    if duplicate:
        manifest["trial_receipts"][-1] = manifest["trial_receipts"][0]
    if corrupt:
        files["baseline-summary.json"] += b" "
    files["manifest.json"] = json.dumps(manifest).encode()
    if extra:
        files["unexpected.json"] = b"{}"
    return archive(files)


def archive(files, *, bad_name=None, symlink=False, duplicate=False):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        for name, raw in files.items():
            member = tarfile.TarInfo(bad_name or name)
            member.size = len(raw)
            if symlink:
                member.type = tarfile.SYMTYPE
                member.linkname = "/tmp/foreign"
            tar.addfile(member, io.BytesIO(raw))
            if duplicate:
                tar.addfile(member, io.BytesIO(raw))
    return out.getvalue()


def parse(raw):
    return parse_packet(raw, hashlib.sha256(raw).hexdigest())


def test_parser_retains_explicit_historical_non_authority_without_mutating_bytes():
    parsed = parse(packet())
    assert len(parsed["receipts"]) == 27
    assert parsed["manifest"]["current_qualification_authority"] is False
    assert parsed["manifest"]["intentional_signer_revocation_preserved"] is True
    assert all(hashlib.sha256(x["raw"]).hexdigest() == x["sha256"] for x in parsed["receipts"])


@pytest.mark.parametrize(
    "options",
    [
        {"authority": True},
        {"revoke": False},
        {"duplicate": True},
        {"extra": True},
        {"corrupt": True},
    ],
)
def test_parser_rejects_authority_inventory_and_digest_substitution(options):
    with pytest.raises(ValueError):
        parse(packet(**options))


@pytest.mark.parametrize(
    "options",
    [{"bad_name": "../outside"}, {"bad_name": "/absolute"}, {"symlink": True}, {"duplicate": True}],
)
def test_parser_rejects_traversal_links_and_duplicate_members(options):
    with pytest.raises(ValueError):
        parse(archive({"manifest.json": b"{}"}, **options))


def test_parser_requires_operator_pinned_package_digest():
    with pytest.raises(ValueError, match="digest"):
        parse_packet(packet(), "0" * 64)
