"""Actual Anvil-owned grade frame custody. No submitted binding is authority."""

import hashlib
from dataclasses import dataclass, field
from uuid import UUID

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import json_object
from anvil.marketing_capture_database import remaining
from anvil.marketing_capture_verifier import OriginalVerifierBinding
from anvil.marketing_private_actor_store import load_original
from anvil.marketing_private_grade_auth import RESPONSE_CAP, PrivateGradeTransport, claims
from anvil.praxis_generic_contract import canonical


@dataclass(frozen=True, slots=True)
class RecordedGradeFrame:
    id: str
    raw: bytes = field(repr=False)
    sha256: str
    binding: OriginalVerifierBinding = field(repr=False)


def check(raw, enrollment):
    if type(raw) is not bytes or not 0 < len(raw) <= RESPONSE_CAP:
        raise ValueError("Complete recorded private grade frame required")
    value = json_object(raw)
    bounded_json(value, RESPONSE_CAP, max_nodes=100000, max_depth=24)
    fields = {"schema_version", "enrollment_id", "manifest_id", "request_sha256", "operation_nonce", "scope", "identity",
              "files", "file_sha256", "sdk_binding", "provenance", "provenance_sha256", "mapping_qualified",
              "capture_accepted", "native_qualified", "run_authority"}
    claims(enrollment)  # Original framework identity/scope checks; no signer.
    if (set(value) != fields or canonical(value) != raw
            or value["schema_version"] != "anvil.marketing-private-grade-input-reply.v1"
            or any(value[key] != enrollment[key] for key in
                   ("enrollment_id", "manifest_id", "request_sha256", "operation_nonce", "scope", "identity"))
            or value["capture_accepted"] is not False or value["native_qualified"] is not False
            or value["run_authority"] != "not_granted" or type(value["mapping_qualified"]) is not bool):
        raise ValueError("Recorded original private grade identity changed")
    transport = PrivateGradeTransport.model_validate_json(canonical(enrollment["private_grade_transport"]))
    if (type(value["files"]) is not dict or type(value["file_sha256"]) is not dict
            or set(value["files"]) != set(transport.file_limits) or set(value["file_sha256"]) != set(transport.file_limits)):
        raise ValueError("Recorded complete private grade file inventory required")
    for name, maximum in transport.file_limits.items():
        text = value["files"][name]
        if (type(text) is not str or not 0 < len(text.encode()) <= maximum
                or hashlib.sha256(text.encode()).hexdigest() != value["file_sha256"][name]):
            raise ValueError("Recorded complete original private grade file changed")
    if (type(value["provenance"]) is not str
            or hashlib.sha256(value["provenance"].encode()).hexdigest() != value["provenance_sha256"]):
        raise ValueError("Recorded original private grade provenance changed")
    binding = OriginalVerifierBinding.model_validate_json(canonical(value["sdk_binding"]))
    if (binding.identity.model_dump(mode="json") != enrollment["identity"]
            or binding.scope.model_dump(mode="json") != enrollment["scope"]
            or binding.input_sha256 != value["file_sha256"]["verifier-input.json"]
            or binding.input_files != {name: sha for name, sha in value["file_sha256"].items() if name != "verifier-input.json"}):
        raise ValueError("Recorded original verifier binding changed")
    return binding


async def record(connection, enrollment, raw, *, api_source_sha256):
    check(raw, enrollment)
    actor = await load_original(connection, enrollment, api_source_sha256=api_source_sha256)
    value = json_object(raw)
    if (value["file_sha256"]["actor-output.json"] != actor.sha256
            or value["files"]["actor-output.json"].encode() != actor.raw):
        raise ValueError("Recorded grade actor bytes differ from actual retained original")
    remaining(connection.capture_deadline)
    row = await (await connection.execute("SELECT marketing_runtime.record_private_grade_frame(%s,%s,%s,%s) AS value",
                                        (UUID(enrollment["enrollment_id"]), UUID(enrollment["manifest_id"]), UUID(actor.id), raw))).fetchone()
    value = row["value"] if row else None
    if (type(value) is not dict or value.get("raw_sha256") != hashlib.sha256(raw).hexdigest()
            or value.get("raw_bytes") != len(raw) or value.get("capture_accepted") is not False
            or value.get("run_authority") != "not_granted"):
        raise RuntimeError("Original private grade frame custody unknown; no retry")
    remaining(connection.capture_deadline)
    return value


async def load(connection, enrollment):
    remaining(connection.capture_deadline)
    row = await (await connection.execute("SELECT marketing_runtime.private_grade_frame(%s,%s) AS value",
                                        (UUID(enrollment["enrollment_id"]), UUID(enrollment["manifest_id"])))).fetchone()
    value = row["value"] if row else None
    if type(value) is not dict or type(value.get("raw_utf8")) is not str:
        raise ValueError("Actual Anvil-recorded private grade frame required")
    raw = value["raw_utf8"].encode()
    if (value.get("enrollment_id") != enrollment["enrollment_id"] or value.get("manifest_id") != enrollment["manifest_id"]
            or value.get("raw_bytes") != len(raw) or value.get("raw_sha256") != hashlib.sha256(raw).hexdigest()):
        raise ValueError("Actual recorded private grade frame integrity changed")
    binding = check(raw, enrollment)
    remaining(connection.capture_deadline)
    return RecordedGradeFrame(value["id"], raw, value["raw_sha256"], binding)
