"""One-attempt private custody of actual attester-collected actor bytes.

These calls never accept a path, synthesize output, issue native acceptance or
start grading. Caller owns authenticated scope and the original transaction.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import Model, json_object
from anvil.marketing_capture_attestation import _instant
from anvil.marketing_capture_database import remaining
from anvil.marketing_private_actor_auth import VerifiedActor, verify
from anvil.marketing_private_grade_auth import PrivateGradeTransport
from anvil.marketing_world_quiescence import Scope
from anvil.praxis_generic_contract import canonical

Reference = Annotated[str, Field(max_length=2000)]


class CapturedActorOutput(Model):
    outcome: Literal["campaign_closed", "awaiting_authority"]
    weekly_review_refs: list[Reference] = Field(max_length=10000)
    evidence_refs: list[Reference] = Field(max_length=10000)
    closeout_report_ref: Reference | None = None
    hold_reason: Reference | None = None


@dataclass(frozen=True, slots=True)
class OriginalActor:
    id: str
    raw: bytes = field(repr=False)
    sha256: str
    actor_stop_sha256: str
    collection_receipt_sha256: str
    capture_accepted: bool = False
    native_qualified: bool = False


async def begin(connection, enrollment, verified):
    if (type(verified) is not VerifiedActor or verified.enrollment_id != enrollment["enrollment_id"]
            or verified.manifest_id != enrollment["manifest_id"] or verified.profile_sha256 != enrollment["profile_sha256"]):
        raise ValueError("Actual verified original actor transport required")
    remaining(connection.capture_deadline)
    row = await (await connection.execute(
        "SELECT marketing_runtime.begin_private_actor(%s,%s,%s,%s,%s,%s,%s) AS value",
        (UUID(verified.enrollment_id), UUID(verified.manifest_id), verified.wire_bytes, verified.wire_sha256,
         verified.attestation_sha256, verified.actor_stop_sha256, verified.collection_receipt_sha256),
    )).fetchone()
    value = row["value"] if row else None
    if type(value) is not dict:
        raise RuntimeError("Original actor intent unavailable; no retry")
    bounded_json(value, 16384, max_nodes=1000, max_depth=8)
    if (value.get("capture_accepted") is not False
            or any(value.get(key) != enrollment[key] for key in
                   ("enrollment_id", "manifest_id", "request_sha256", "operation_nonce"))
            or Scope.model_validate(value["scope"]) != Scope.model_validate(enrollment["scope"])
            or value["wire_bytes"] != verified.wire_bytes or value["wire_sha256"] != verified.wire_sha256
            or _instant(value["expires_at"]) != _instant(enrollment["expires_at"])):
        raise ValueError("Original actor intent changed")
    remaining(connection.capture_deadline)
    return value


def _check_raw(raw, maximum):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise ValueError("Complete original actor byte bound required")
    value = json_object(raw)
    bounded_json(value, maximum, max_nodes=30000, max_depth=8)
    CapturedActorOutput.model_validate_json(raw)
    if any(key in value and type(value[key]) is not str for key in ("closeout_report_ref", "hold_reason")):
        raise ValueError("Original optional captured fields must be strings when present")
    if canonical(value) != raw:
        raise ValueError("Exact original captured actor representation required")


async def retain(connection, context, raw, verified):
    if (type(verified) is not VerifiedActor or len(raw) != verified.wire_bytes
            or hashlib.sha256(raw).hexdigest() != verified.wire_sha256
            or context["enrollment_id"] != verified.enrollment_id or context["manifest_id"] != verified.manifest_id):
        raise ValueError("Complete original actor wire bytes changed")
    _check_raw(raw, verified.wire_bytes)
    remaining(connection.capture_deadline)
    row = await (await connection.execute("SELECT marketing_runtime.retain_private_actor(%s,%s,%s) AS value",
                                        (UUID(context["intent_id"]), raw, verified.original_header))).fetchone()
    value = row["value"] if row else None
    if (type(value) is not dict or value.get("schema_version") != "anvil.marketing-private-actor-custody.v1"
            or value.get("raw_sha256") != verified.wire_sha256 or value.get("raw_bytes") != verified.wire_bytes
            or value.get("enrollment_id") != verified.enrollment_id or value.get("manifest_id") != verified.manifest_id
            or value.get("capture_accepted") is not False or value.get("native_qualified") is not False
            or value.get("run_authority") != "not_granted"):
        raise RuntimeError("Original actor storage outcome unknown; no retry")
    remaining(connection.capture_deadline)
    return value


async def load_original(connection, enrollment, *, api_source_sha256):
    """Actual bytes+original signature reload, never an API reference invented from a hash."""
    row = await (await connection.execute("SELECT marketing_runtime.private_actor_original(%s,%s) AS value",
                                        (UUID(enrollment["enrollment_id"]), UUID(enrollment["manifest_id"])))).fetchone()
    value = row["value"] if row else None
    if type(value) is not dict or value.get("schema_version") != "anvil.marketing-private-actor-original.v1":
        raise ValueError("Anvil original captured actor custody required")
    if value.get("enrollment_id") != enrollment["enrollment_id"] or value.get("manifest_id") != enrollment["manifest_id"]:
        raise ValueError("Original actor source scope changed")
    raw = value["raw_utf8"].encode()
    transport = PrivateGradeTransport.model_validate_json(canonical(enrollment["private_grade_transport"]))
    _check_raw(raw, transport.file_limits["actor-output.json"])
    verified = verify(value["attestation_header"], enrollment, api_source_sha256=api_source_sha256)
    if (len(raw) != value["raw_bytes"] or len(raw) != verified.wire_bytes
            or hashlib.sha256(raw).hexdigest() != value["raw_sha256"] or value["raw_sha256"] != verified.wire_sha256
            or value["actor_stop_sha256"] != verified.actor_stop_sha256
            or value["collection_receipt_sha256"] != verified.collection_receipt_sha256):
        raise ValueError("Actual original actor bytes/attestation changed")
    remaining(connection.capture_deadline)
    return OriginalActor(value["id"], raw, value["raw_sha256"], value["actor_stop_sha256"], value["collection_receipt_sha256"])
