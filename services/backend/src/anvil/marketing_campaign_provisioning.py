"""Operator-only immutable campaign candidates; no qualification or activation.

The existing operator path supplies the reviewed checksum-file fingerprint and
private pack root. Neither path nor fixture bodies enter public dataset discovery.
"""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from anvil.db import Jsonb, uid
from anvil.marketing_task2_contract import CASES
from anvil.praxis_generic_contract import digest
from anvil.praxis_marketing_contract import CampaignDataset


def candidate(root, checksum_sha256, *, dataset_key, version, source_sha256):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Owned private fixture directory required")
    root = root.resolve()
    checksum_file = root / "checksums.json"
    if checksum_file.is_symlink():
        raise ValueError("Checksum file cannot be a symlink")
    with checksum_file.open("rb") as stream:
        raw = stream.read(1048577)
    if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != checksum_sha256:
        raise ValueError("Exact reviewed fixture checksum-file fingerprint required")
    entries = json.loads(raw)
    if not isinstance(entries, dict) or not 1 <= len(entries) <= 2000:
        raise ValueError("Bounded fixture checksum map required")
    verified, total = {}, 0
    for name, fingerprint in sorted(entries.items()):
        if type(name) is not str or not name or "\\" in name:
            raise ValueError("Canonical relative fixture path required")
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or str(relative) != name:
            raise ValueError("Fixture path traversal denied")
        if type(fingerprint) is not str or not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            raise ValueError("Exact fixture content fingerprint required")
        file = root / name
        if any(
            part.is_symlink()
            for part in (file, *file.parents)
            if part != root and root in part.parents
        ) or not file.resolve().is_relative_to(root):
            raise ValueError("Fixture symlink or escaping path denied")
        if not file.is_file() or file.stat().st_size > 16777216:
            raise ValueError("Bounded regular fixture file required")
        with file.open("rb") as stream:
            content = stream.read(16777217)
        total += len(content)
        # Existing reviewed source pack is108,578,167bytes. This operator-only
        # read bound does not change public upload or per-episode data limits.
        if len(content) > 16777216 or total > 134217728:
            raise ValueError("Private fixture pack exceeds operator verification bound")
        if hashlib.sha256(content).hexdigest() != fingerprint:
            raise ValueError("Fixture immutable content mismatch")
        verified[name] = fingerprint
    cases = []
    for case_id in sorted(CASES):
        case_file = f"cases/{case_id}/case.json"
        if case_file not in verified:
            raise ValueError("Both supported US campaign cases are required")
        with (root / case_file).open("rb") as stream:
            body = stream.read(16777217)
        if hashlib.sha256(body).hexdigest() != verified[case_file]:
            raise ValueError("Case metadata changed during verification")
        case = json.loads(body)
        if case.get("case_id") != case_id or case.get("focus_locale") != "en-US":
            raise ValueError("Exact supported US campaign identity/locale required")
        files = {
            name: value
            for name, value in verified.items()
            if name.startswith((f"cases/{case_id}/", f"reviewer_only/us-pair/{case_id}/"))
        }
        cases.append(
            {
                "id": case_id,
                "locale": "en-US",
                "snapshot_sha256": digest(
                    {"case_id": case_id, "checksum_sha256": checksum_sha256, "files": files}
                ),
            }
        )
    dataset = CampaignDataset(
        schema_version="anvil.campaign-case-dataset.v1",
        id=dataset_key,
        version=version,
        case_count=len(cases),
        cases=cases,
    )
    return {
        "manifest": dataset.model_dump(),
        "manifest_sha256": dataset.reference().sha256,
        "source_sha256": source_sha256,
        "fixture_manifest": {
            "schema_version": "anvil.campaign-fixture-candidate.v1",
            "checksum_sha256": checksum_sha256,
            "source_hashes": verified,
            "verified_bytes": total,
            "scope": "US pair candidate; private alternatives not activated",
            "qualification": "not_granted",
        },
    }


def persist(c, project, prepared):
    """The normal application/scheduler roles have no INSERT authority here."""
    from anvil.praxis_template_registry import source_hash

    allowed = c.execute(
        "SELECT has_table_privilege(current_user,'anvil.campaign_dataset_versions','INSERT') AS allowed"
    ).fetchone()["allowed"]
    if not allowed:
        raise PermissionError("Existing privileged operator connection required")
    dataset = CampaignDataset.model_validate(prepared["manifest"])
    if (
        prepared["manifest_sha256"] != dataset.reference().sha256
        or prepared["source_sha256"] != source_hash()
    ):
        raise ValueError("Current immutable candidate source required")
    fixture = prepared["fixture_manifest"]
    if (
        fixture.get("schema_version") != "anvil.campaign-fixture-candidate.v1"
        or fixture.get("qualification") != "not_granted"
    ):
        raise ValueError("Unqualified fixture candidate required")
    old = c.execute(
        "SELECT * FROM anvil.campaign_dataset_versions WHERE project_id=%s AND dataset_key=%s AND version=%s",
        (project, dataset.id, dataset.version),
    ).fetchone()
    if old:
        if (
            old["manifest_sha256"] != prepared["manifest_sha256"]
            or old["source_sha256"] != prepared["source_sha256"]
            or old["fixture_manifest_sha256"] != digest(fixture)
        ):
            raise ValueError(
                "Immutable campaign candidate changed; use a new Anvil dataset version"
            )
        identifier = str(old["id"])
    else:
        identifier = uid()
        c.execute(
            "INSERT INTO anvil.campaign_dataset_versions(id,project_id,dataset_key,version,manifest,manifest_sha256,source_sha256,fixture_manifest,fixture_manifest_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                identifier,
                project,
                dataset.id,
                dataset.version,
                Jsonb(dataset.model_dump()),
                prepared["manifest_sha256"],
                prepared["source_sha256"],
                Jsonb(fixture),
                digest(fixture),
            ),
        )
    return {
        "id": identifier,
        "case_dataset": dataset.reference().model_dump(),
        "qualified": False,
        "run_authority": "not_granted",
        "model_calls": 0,
    }
