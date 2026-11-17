"""Complete result/process wire framing, not physical-proof admission."""

import hashlib
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from pydantic import Field

from anvil.dataset_export_contract import Model, Sha, json_object
from anvil.marketing_capture_verifier import Identity
from anvil.marketing_native_wire_bounds import bounded_json
from anvil.marketing_private_grade_auth import claims as grade_claims
from anvil.marketing_private_result_auth import KINDS, PrivateResultTransport, VerifiedResult
from anvil.marketing_world_quiescence import Scope
from anvil.praxis_generic_contract import canonical


class ResultFrame(Model):
    schema_version: Literal["anvil.marketing-private-result-upload.v1"]
    enrollment_id: UUID
    manifest_id: UUID
    request_sha256: Sha
    operation_nonce: Sha
    identity: Identity
    scope: Scope
    grade_frame_sha256: Sha
    documents: dict[str, str] = Field(min_length=2, max_length=2)


@dataclass(frozen=True, slots=True)
class OriginalResultFiles:
    wire: bytes = field(repr=False)
    wire_sha256: str
    grade_frame_sha256: str
    verifier_result: bytes = field(repr=False)
    process_receipt: bytes = field(repr=False)
    verifier_result_sha256: str
    process_receipt_sha256: str
    capture_accepted: bool = False
    native_qualified: bool = False


def parse(raw, enrollment, verified):
    """Retain actual raw ASCII result and actual process receipt or reject.

    Original grade binding must later come from the API's recorded grade frame.
    No SDK-submitted binding, caller file reference or inferred process pass is
    accepted. The process document remains custody-only until semantic validation.
    """
    if type(raw) is not bytes or type(verified) is not VerifiedResult:
        raise ValueError("Complete authenticated original result frame required")
    transport = PrivateResultTransport.model_validate_json(canonical(enrollment["private_result_transport"]))
    if (not 0 < len(raw) <= transport.wire_limit or len(raw) != verified.wire_bytes
            or hashlib.sha256(raw).hexdigest() != verified.wire_sha256):
        raise ValueError("Original full result transport changed")
    value = json_object(raw)
    bounded_json(value, transport.wire_limit, max_nodes=20000, max_depth=12)
    if canonical(value) != raw:
        raise ValueError("Exact original result wire representation required")
    frame = ResultFrame.model_validate_json(raw)
    if (str(frame.enrollment_id) != enrollment["enrollment_id"] or str(frame.manifest_id) != enrollment["manifest_id"]
            or frame.request_sha256 != enrollment["request_sha256"] or frame.operation_nonce != enrollment["operation_nonce"]
            or frame.identity.model_dump(mode="json") != enrollment["identity"]
            or frame.scope.model_dump(mode="json") != Scope.model_validate(enrollment["scope"]).model_dump(mode="json")
            or frame.grade_frame_sha256 != verified.grade_frame_sha256 or set(frame.documents) != KINDS):
        raise ValueError("Exact original result identity and grade frame required")
    grade_claims(enrollment)  # Check actual original framework identity/scope, no signer.
    originals = {}
    for kind in sorted(KINDS):
        data = frame.documents[kind].encode()
        if not 0 < len(data) <= transport.document_limits[kind]:
            raise ValueError("Complete result/process document exceeds preflight bound")
        bounded_json(json_object(data), transport.document_limits[kind], max_nodes=20000, max_depth=12)
        # Preserve inner raw bytes. The producer's ASCII serialization is not
        # silently rewritten to JCS when recording its original digest.
        originals[kind] = data
    result_sha = hashlib.sha256(originals["verifier_result"]).hexdigest()
    process_sha = hashlib.sha256(originals["process_receipt"]).hexdigest()
    if result_sha != verified.verifier_result_sha256 or process_sha != verified.process_receipt_sha256:
        raise ValueError("Original private result/process bytes changed")
    return OriginalResultFiles(raw, verified.wire_sha256, verified.grade_frame_sha256,
                               originals["verifier_result"], originals["process_receipt"], result_sha, process_sha)
