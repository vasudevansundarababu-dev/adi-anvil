"""Strict actual API acceptance response, never a local receipt producer."""

from typing import Literal
from uuid import UUID

from anvil.dataset_export_contract import Model, Sha, json_object
from anvil.marketing_native_wire_bounds import bounded_json
from anvil.praxis_generic_contract import canonical


class CaptureAcceptance(Model):
    schema_version: Literal["anvil.marketing-private-capture-accepted.v1"]
    id: UUID
    accepted_capture_reference: UUID
    enrollment_id: UUID
    manifest_id: UUID
    wire_sha256: Sha
    grade_frame_sha256: Sha
    verifier_result_id: UUID
    verifier_result_sha256: Sha
    process_receipt_sha256: Sha
    grade_status: Literal["passed", "failed", "unscored"]
    capture_accepted: Literal[True]
    native_qualified: Literal[True]
    run_authority: Literal["not_granted"]
    model_performance_validated: Literal[False]
    human_legal_acceptance: Literal["not_established"]


def validate_capture_acceptance(raw, enrollment, wire_sha256):
    """Called only on the worker's own authenticated fixed-POST TLS response.

    A standalone parser is consistency checking, not proof that the response
    came from the API or that its ID exists. Actual host transport and API
    durable acceptance remain mandatory. There is no local acceptance factory.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= 4096:
        raise ValueError("Actual complete API acceptance response required")
    value = json_object(raw)
    bounded_json(value, 4096, max_nodes=100, max_depth=4)
    receipt = CaptureAcceptance.model_validate_json(raw)
    if (canonical(value) != raw or receipt.id != receipt.accepted_capture_reference
            or str(receipt.enrollment_id) != enrollment["enrollment_id"]
            or str(receipt.manifest_id) != enrollment["manifest_id"] or receipt.wire_sha256 != wire_sha256
            or value["capture_accepted"] is not True or value["native_qualified"] is not True
            or value["model_performance_validated"] is not False):
        raise ValueError("Actual original API capture acceptance changed")
    return receipt.model_dump(mode="json")
