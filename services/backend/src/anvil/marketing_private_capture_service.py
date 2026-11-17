"""Fixed API admission over actual retained private originals; never replays."""

import hashlib
import os
from uuid import UUID

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import json_object
from anvil.marketing_capture_database import remaining
from anvil.marketing_capture_submission import parse
from anvil.marketing_private_actor_store import load_original as load_actor
from anvil.marketing_private_capture_check import check
from anvil.marketing_private_capture_receipt import validate_capture_acceptance
from anvil.marketing_private_grade_store import load as load_frame
from anvil.marketing_private_result_store import load_original as load_result
from anvil.praxis_generic_contract import canonical, digest


async def accept(connection, context, raw_receipt, raw, *, api_source_sha256):
    """Caller must commit this SAME bounded transaction before returning success."""
    if (type(raw) is not bytes or raw_receipt.get("classification") != "raw_received_unqualified"
            or raw_receipt.get("raw_sha256") != hashlib.sha256(raw).hexdigest()):
        raise ValueError("Actual complete original capture custody required")
    remaining(connection.capture_deadline)
    row = await (await connection.execute("SELECT marketing_runtime.private_capture_context(%s,%s) AS value",
        (UUID(context["enrollment_id"]), UUID(raw_receipt["private_intake_id"])))).fetchone()
    original = row["value"] if row else None
    if (type(original) is not dict or original.get("raw_sha256") != raw_receipt["raw_sha256"]
            or original.get("raw_bytes") != len(raw)):
        raise ValueError("Current qualified original physical capture context required")
    bounded_json(original, 196608, max_nodes=20000, max_depth=24)
    enrollment = original["enrollment"]
    submission = parse(raw, context)
    frame = await load_frame(connection, enrollment)
    actor = await load_actor(connection, enrollment, api_source_sha256=api_source_sha256)
    result_id, files, checked = await load_result(connection, enrollment, api_source_sha256=api_source_sha256)
    checked_capture = check(submission, enrollment, original, frame, actor, files, checked, result_id,
                            api_source_sha256=api_source_sha256)
    recorded_frame = json_object(frame.raw)
    provenance = json_object(recorded_frame["provenance"].encode())
    native = provenance["native_evidence"]
    release = os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256")
    if (recorded_frame.get("mapping_qualified") is not True or not release
            or native.get("deployment_release_sha256") != release or not native.get("native_registry_sha256")):
        raise ValueError("Original independently qualified native mapping and release required")
    row = await (await connection.execute("SELECT marketing_runtime.private_native_ordinal_acceptance_context(%s,%s,%s) AS value",
        (UUID(enrollment["enrollment_id"]), UUID(enrollment["manifest_id"]), release))).fetchone()
    current_registry = row["value"] if row else None
    if current_registry is None or digest(current_registry) != native["native_registry_sha256"]:
        raise ValueError("Original native calibration/configuration/access changed before acceptance")
    remaining(connection.capture_deadline)
    row = await (await connection.execute("SELECT marketing_runtime.accept_private_capture(%s,%s,%s,%s) AS value",
        (UUID(enrollment["enrollment_id"]), UUID(raw_receipt["private_intake_id"]), UUID(result_id), submission.wire_sha256))).fetchone()
    receipt = row["value"] if row else None
    result = validate_capture_acceptance(canonical(receipt), enrollment, submission.wire_sha256)
    if any(result[key] != checked_capture[key] for key in checked_capture):
        raise RuntimeError("Actual original acceptance binding changed; no retry")
    remaining(connection.capture_deadline)
    return result
