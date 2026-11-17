"""Actual result custody against Anvil's recorded grade frame, never admission."""

import hashlib
from uuid import UUID

from anvil.marketing_capture_attestation import _instant
from anvil.marketing_capture_database import remaining
from anvil.marketing_capture_verifier import validate_private_result
from anvil.marketing_private_grade_store import load as load_grade_frame
from anvil.marketing_private_result_auth import VerifiedResult, verify
from anvil.marketing_private_result_frame import parse
from anvil.marketing_world_quiescence import Scope


async def begin(connection, enrollment, verified):
    if (type(verified) is not VerifiedResult or verified.enrollment_id != enrollment["enrollment_id"]
            or verified.manifest_id != enrollment["manifest_id"] or verified.profile_sha256 != enrollment["profile_sha256"]):
        raise ValueError("Actual authenticated original result required")
    remaining(connection.capture_deadline)
    row = await (await connection.execute(
        "SELECT marketing_runtime.begin_private_result(%s,%s,%s,%s,%s,%s,%s,%s) AS value",
        (UUID(verified.enrollment_id), UUID(verified.manifest_id), verified.wire_bytes, verified.wire_sha256,
         verified.attestation_sha256, verified.grade_frame_sha256, verified.verifier_result_sha256,
         verified.process_receipt_sha256),
    )).fetchone()
    value = row["value"] if row else None
    if (type(value) is not dict or value.get("capture_accepted") is not False
            or value.get("native_qualified") is not False or value.get("run_authority") != "not_granted"
            or any(value.get(key) != enrollment[key] for key in
                   ("enrollment_id", "manifest_id", "request_sha256", "operation_nonce"))
            or Scope.model_validate(value["scope"]) != Scope.model_validate(enrollment["scope"])
            or value["wire_bytes"] != verified.wire_bytes or value["wire_sha256"] != verified.wire_sha256
            or value["grade_frame_sha256"] != verified.grade_frame_sha256
            or _instant(value["expires_at"]) != _instant(enrollment["expires_at"])):
        raise RuntimeError("Original private result intent unknown or consumed; no retry")
    remaining(connection.capture_deadline)
    return value


async def retain(connection, enrollment, context, raw, verified):
    originals = parse(raw, enrollment, verified)
    if (context["enrollment_id"] != verified.enrollment_id or context["manifest_id"] != verified.manifest_id
            or context["grade_frame_sha256"] != originals.grade_frame_sha256):
        raise ValueError("Original result intent changed")
    frame = await load_grade_frame(connection, enrollment)
    if frame.sha256 != originals.grade_frame_sha256:
        raise ValueError("Result must reference actual Anvil-recorded grade frame")
    checked = validate_private_result(originals.verifier_result, frame.binding)
    # The complete original process document is retained, but its presence or
    # a signed hash is not physical qualification. Final admission stays closed
    # until the actual host producer and six-document proof are checked.
    remaining(connection.capture_deadline)
    row = await (await connection.execute(
        "SELECT marketing_runtime.retain_private_result(%s,%s,%s,%s,%s,%s) AS value",
        (UUID(context["intent_id"]), originals.wire, originals.verifier_result,
         originals.process_receipt, verified.original_header, checked.status),
    )).fetchone()
    value = row["value"] if row else None
    if (type(value) is not dict or value.get("schema_version") != "anvil.marketing-private-result-custody.v1"
            or value.get("raw_sha256") != originals.wire_sha256 or value.get("raw_bytes") != len(raw)
            or value.get("enrollment_id") != verified.enrollment_id or value.get("manifest_id") != verified.manifest_id
            or value.get("grade_frame_sha256") != frame.sha256
            or value.get("verifier_result_sha256") != originals.verifier_result_sha256
            or value.get("process_receipt_sha256") != originals.process_receipt_sha256
            or value.get("grade_status") != checked.status or value.get("capture_accepted") is not False
            or value.get("native_qualified") is not False or value.get("run_authority") != "not_granted"):
        raise RuntimeError("Original private result custody unknown; no retry")
    remaining(connection.capture_deadline)
    return value


async def load_original(connection, enrollment, *, api_source_sha256):
    remaining(connection.capture_deadline)
    row = await (await connection.execute("SELECT marketing_runtime.private_result_original(%s,%s) AS value",
                                        (UUID(enrollment["enrollment_id"]), UUID(enrollment["manifest_id"])))).fetchone()
    value = row["value"] if row else None
    if (type(value) is not dict or value.get("schema_version") != "anvil.marketing-private-result-original.v1"
            or value.get("enrollment_id") != enrollment["enrollment_id"]
            or value.get("manifest_id") != enrollment["manifest_id"]
            or value.get("capture_accepted") is not False or value.get("native_qualified") is not False
            or value.get("run_authority") != "not_granted"):
        raise ValueError("Actual original result custody required")
    verified = verify(value["attestation_header"], enrollment, api_source_sha256=api_source_sha256)
    originals = parse(value["raw_utf8"].encode(), enrollment, verified)
    frame = await load_grade_frame(connection, enrollment)
    checked = validate_private_result(originals.verifier_result, frame.binding)
    if (frame.sha256 != originals.grade_frame_sha256 or value["grade_frame_sha256"] != frame.sha256
            or value["raw_bytes"] != len(originals.wire) or value["raw_sha256"] != originals.wire_sha256
            or value["verifier_utf8"].encode() != originals.verifier_result
            or value["process_utf8"].encode() != originals.process_receipt
            or value["verifier_result_sha256"] != hashlib.sha256(originals.verifier_result).hexdigest()
            or value["process_receipt_sha256"] != hashlib.sha256(originals.process_receipt).hexdigest()
            or value["grade_status"] != checked.status):
        raise ValueError("Actual original result/process custody changed")
    remaining(connection.capture_deadline)
    return value["id"], originals, checked
