"""Explicit operator import of actual historical fictional-control receipts.

No web route calls this module. No qualification, comparison, review, person or
permission record is created. Local test setup must separately provide current
artifact-scoped access. Preserved receipt bytes are never rewritten.
"""

import hashlib
import io
import json
import re
import tarfile
from datetime import datetime

from anvil.benchmark_qualification_evidence import public_projection
from anvil.benchmark_storage import bind_private, stage_private
from anvil.db import Jsonb, audit, one, uid


def parse_packet(raw, expected_sha256):
    if len(raw) > 32 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Historical packet digest or size mismatch")
    files, total = {}, 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for item in archive:
            if (
                not item.isfile()
                or item.name in files
                or item.name.startswith("/")
                or ".." in item.name.split("/")
                or item.size > 8 * 1024 * 1024
            ):
                raise ValueError("Invalid historical packet member")
            total += item.size
            if total > 64 * 1024 * 1024 or len(files) >= 256:
                raise ValueError("Historical packet exceeds bound")
            data = archive.extractfile(item).read(item.size + 1)
            if len(data) != item.size:
                raise ValueError("Historical member changed")
            files[item.name] = data
    manifest = json.loads(files["manifest.json"])
    if (
        manifest["profile"] != "HISTORICAL_NATIVE_BASELINE_EVIDENCE_ONLY"
        or manifest["current_qualification_authority"] is not False
        or manifest["intentional_signer_revocation_preserved"] is not True
        or not re.fullmatch(r"[a-f0-9]{40}", manifest["source_sha"])
    ):
        raise ValueError("Unsupported historical origin or authority")
    if set(files) != set(manifest["files"]) | {"manifest.json"}:
        raise ValueError("Historical packet membership changed")
    for path, item in manifest["files"].items():
        if (
            len(files[path]) != item["byte_size"]
            or hashlib.sha256(files[path]).hexdigest() != item["sha256"]
        ):
            raise ValueError("Historical member digest changed")
    summary = json.loads(files["baseline-summary.json"])
    if (
        summary["exit_code"] != 0
        or summary["source_sha"] != manifest["source_sha"]
        or summary["source_changes_after"]
    ):
        raise ValueError("Historical source/result mismatch")
    recorded = datetime.fromisoformat(summary["started_at"])
    if recorded.tzinfo is None:
        raise ValueError("Historical timestamp requires timezone")
    receipts = []
    seen = set()
    for ref in manifest["trial_receipts"]:
        digest = ref["sha256"]
        if not re.fullmatch(r"[a-f0-9]{64}", digest) or digest in seen:
            raise ValueError("Duplicate historical receipt")
        seen.add(digest)
        data = files["trials/" + digest + ".json"]
        value = json.loads(data)
        if (
            hashlib.sha256(data).hexdigest() != digest
            or value["origin"] != "original_synthetic_software_conformance"
            or value["task_id"] != ref["task_id"]
            or value["mode"] != ref["mode"]
            or value["binding_sha256"] != ref["binding_sha256"]
        ):
            raise ValueError("Historical receipt provenance changed")
        if value["mode"] not in {
            "positive",
            "empty",
            "guardrail",
            "offline_conversation",
        } or not re.fullmatch(r"FX-[0-9]{3}", value["task_id"]):
            raise ValueError("Unsupported fictional control")
        if (
            value["candidate_stopped_before_evaluation"] is not True
            or value["candidate_mounts_private"] is not False
            or value["evaluator_mounts_actor"] is not False
            or any(
                value["control_checks"].get(k) is not True
                for k in ("fresh_actor", "non_root_readonly_no_egress_cgroups")
            )
        ):
            raise ValueError("Historical isolation evidence is incomplete")
        public_projection(value.get("public_capture"))
        atif = value.get("atif")
        if (
            atif
            and atif.get("agent", {}).get("extra", {}).get("measured_model_performance")
            is not False
        ):
            raise ValueError("Historical SDK fixture must not claim model performance")
        receipts.append({"raw": data, "sha256": digest, "value": value})
    if len(receipts) != manifest["trial_receipt_count"] or len(receipts) != 27:
        raise ValueError("Incomplete historical baseline packet")
    return {
        "manifest": manifest,
        "recorded_at": recorded,
        "receipts": receipts,
        "packet_sha256": expected_sha256,
    }


def register(c, project, user, parsed, prepared):
    """Trusted offline owner connection only; web/app/worker have no INSERT grant.

    Staging bytes occurs before this SQL-only transaction. Current actor must be
    a real active admin identity in this project (synthetic only in a test DB).
    This grants no source/admission authority or reader permissions.
    """
    role = one(c, "SELECT current_user role")["role"]
    if (
        role != "anvil_migration"
        or not one(c, "SELECT anvil.benchmark_is_admin(%s,%s) allowed", (project, user))["allowed"]
    ):
        raise PermissionError("An explicit offline migration owner and project admin are required")
    if len(prepared) != len(parsed["receipts"]):
        raise ValueError("Prepared historical membership changed")
    ids = []
    for entry, artifact in zip(parsed["receipts"], prepared, strict=True):
        if (
            str(artifact.project_id) != str(project)
            or artifact.classification != "benchmark_trace"
            or artifact.sha256 != entry["sha256"]
            or artifact.byte_size != len(entry["raw"])
        ):
            raise ValueError("Prepared historical artifact changed")
        existing = one(
            c,
            "SELECT id FROM anvil.benchmark_trace_audit WHERE project_id=%s AND source_record_sha256=%s",
            (project, entry["sha256"]),
        )
        if existing:
            ids.append(str(existing["id"]))
            continue
        artifact_id = bind_private(c, artifact, created_by=user)
        value = entry["value"]
        metadata = {
            "kind": "historical_control",
            "origin": value["origin"],
            "current_authority": False,
            "measured_model_performance": False,
            "task_id": value["task_id"],
            "task_key": "fictional-points:1.0.0:" + value["task_id"],
            "mode": value["mode"],
            "points": value["points"],
            "possible_points": value["possible_points"],
            "duration_ms": value.get("duration_ms"),
            "timestamp_basis": "recorded_baseline_window_start; individual_trial_start_unavailable",
        }
        identifier = uid()
        c.execute(
            "INSERT INTO anvil.benchmark_trace_audit(id,project_id,artifact_id,source_record_sha256,source_commit,source_packet_sha256,recorded_at,environment,metadata,imported_by) VALUES(%s,%s,%s,%s,%s,%s,%s,'linux_qa',%s,%s)",
            (
                identifier,
                project,
                artifact_id,
                entry["sha256"],
                parsed["manifest"]["source_sha"],
                parsed["packet_sha256"],
                parsed["recorded_at"],
                Jsonb(metadata),
                user,
            ),
        )
        ids.append(identifier)
    audit(
        c,
        project,
        user,
        "benchmark.historical_controls_imported",
        None,
        {
            "packet_sha256": parsed["packet_sha256"],
            "trace_count": len(ids),
            "comparison_admitted": False,
            "current_authority": False,
        },
    )
    return ids


def prepare(project, parsed):
    return [
        stage_private(project, x["raw"], "benchmark_trace", "application/json")
        for x in parsed["receipts"]
    ]
