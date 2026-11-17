"""Proposed v2 metadata envelope budgeting, never proof or intake authority.

Bulk model/tool/state evidence requires API-owned immutable references. Semantic
whole-operation/seal validators and the authenticated producer remain absent.
This pure encoder neither creates a reference nor sends or qualifies a capture.
"""

from dataclasses import dataclass
from uuid import UUID

from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical
from anvil.marketing_native_records import _parse_record

SCHEMA = 'anvil.marketing-native-capture-submission.v2'
FRAME_LIMIT = 4096
KIND_LIMITS = (
    ('operation_binding', 4096),
    ('kernel_scope', 16384),
    ('process_join', 8192),
    ('container_shutdown', 12288),
    ('capture_seal', 8192),
    ('verifier_result', 4096),
)


@dataclass(frozen=True, slots=True)
class CaptureMetadataBudgetV2:
    canonical_empty_frame: bytes
    wire_upper_bound: int
    original_wire_limit: int


def prepare_v2_metadata_budget(enrollment_id, request_sha256, operation_nonce, *, plan_receipt_bytes):
    """Run BEFORE SDK work; this is a budget calculation, not native admission."""
    if type(enrollment_id) is not str or str(UUID(enrollment_id)) != enrollment_id:
        raise ValueError('marketing_original_capture_enrollment_uuid_required')
    if any(type(value) is not str or len(value) != 64
           or any(c not in '0123456789abcdef' for c in value)
           for value in (request_sha256, operation_nonce)):
        raise ValueError('marketing_original_capture_binding_required')
    if type(plan_receipt_bytes) is not int or not 1 <= plan_receipt_bytes <= DOCUMENT_CAP:
        raise ValueError('marketing_original_capture_wire_limit_required')
    frame = _bounded_canonical({
        'schema_version': SCHEMA, 'enrollment_id': enrollment_id,
        'request_sha256': request_sha256, 'operation_nonce': operation_nonce,
        'documents': {kind: '' for kind, _ in KIND_LIMITS},
    }, FRAME_LIMIT)
    # Canonical inner JSON has no literal control bytes. Outer JSON quoting can
    # at most double its UTF8 bytes (quotes/backslashes); Unicode stays UTF8.
    bound = len(frame) + 2 * sum(limit for _, limit in KIND_LIMITS)
    if bound > plan_receipt_bytes:
        raise ValueError('marketing_metadata_profile_cannot_fit_before_sdk')
    return CaptureMetadataBudgetV2(frame, bound, plan_receipt_bytes)


def encode_v2_metadata(budget, documents):
    """Canonical framing only. Incomplete/unqualified proof cannot be accepted."""
    if type(budget) is not CaptureMetadataBudgetV2 or type(documents) is not dict:
        raise ValueError('marketing_exact_capture_metadata_budget_required')
    frame = _parse_record(budget.canonical_empty_frame)
    # Recompute fixed bounds; a manually instantiated dataclass has no authority.
    expected = prepare_v2_metadata_budget(
        frame['enrollment_id'], frame['request_sha256'], frame['operation_nonce'],
        plan_receipt_bytes=budget.original_wire_limit,
    )
    if expected != budget or set(documents) != {kind for kind, _ in KIND_LIMITS}:
        raise ValueError('marketing_fixed_capture_metadata_profile_required')
    values = {}
    for kind, limit in KIND_LIMITS:
        raw = documents[kind]
        if type(raw) is not bytes or not 0 < len(raw) <= limit:
            raise ValueError('marketing_capture_metadata_kind_capacity')
        _parse_record(raw)
        values[kind] = raw.decode('utf-8')
    raw = _bounded_canonical(frame | {'documents': values}, budget.original_wire_limit)
    if len(raw) > budget.wire_upper_bound:
        raise ValueError('marketing_capture_metadata_wire_bound_changed')
    return raw
