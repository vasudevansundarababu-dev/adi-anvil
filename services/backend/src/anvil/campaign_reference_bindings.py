"""Opaque reference identity freezes into preparation before model execution."""

from uuid import UUID

from anvil.db import Jsonb, digest
from anvil.diagnostic_measures import valid_sha


def freeze(c, group_id, assignments):
    manifest = c.execute("SELECT anvil.campaign_reference_metadata(%s,%s) AS manifest", (group_id, Jsonb(assignments))).fetchone()["manifest"]
    return {"campaign_reference_manifest": manifest, "campaign_reference_sha256": digest(manifest)}


def bound(prepared, task, case_id, case_sha256):
    manifest = prepared.get("campaign_reference_manifest")
    if not isinstance(manifest, dict) or digest(manifest) != prepared.get("campaign_reference_sha256"):
        raise ValueError("Campaign references must be frozen in the original execution preparation")
    if manifest.get("schema_version") != "anvil.campaign-reference-manifest.v1" or manifest.get("private_contents_included") is not False:
        raise ValueError("Exact opaque campaign reference manifest required")
    if any(manifest.get(key) != task[key] for key in ("task_id", "task_version", "payload_sha256")):
        raise ValueError("Frozen campaign reference task identity differs")
    members = manifest.get("cases", [])
    expected = {row["case_id"]: row["snapshot_sha256"] for row in prepared.get("case_assignments", [])}
    if not expected or len(members) != len(expected) or len({row["case_id"] for row in members}) != len(members) or {row["case_id"]: row["snapshot_sha256"] for row in members} != expected:
        raise ValueError("Exact frozen campaign reference population required")
    row = next((row for row in members if row["case_id"] == case_id), None)
    if not row or row["snapshot_sha256"] != case_sha256:
        raise ValueError("Frozen campaign reference case identity differs")
    if row.get("reference_id") is None:
        if row.get("reference_sha256") is not None or row.get("status") != "missing_at_preparation":
            raise ValueError("Missing reference cannot be replaced after execution")
    else:
        UUID(row["reference_id"])
        if not valid_sha(row.get("reference_sha256")) or row.get("status") != "bound":
            raise ValueError("Exact private reference revision/hash required")
    return row | {"manifest_sha256": prepared["campaign_reference_sha256"]}
