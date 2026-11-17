"""Original independent receiver facts and disjoint enrollment transactions.

No root identity, caller flag, public-ready message or diagnostic receipt grants
OS authority. The independently qualified receiver must own original operation,
process/FD and six evidence-policy custody before this private commit path.
Operational entry stays unconditionally gated; no connection is opened on import.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from anvil.marketing_attester_enrollment import (
    OriginalBinding,
    check_original,
    register_public_ready,
)
from anvil.marketing_capture_peer import REQUIRED_EVIDENCE, IndependentOSReceipt, record_peer
from anvil.marketing_capture_status import Transport
from anvil.marketing_native_boundary import marketing_native_gate
from anvil.marketing_native_kernel_scope import _remaining
from anvil.marketing_native_records import _parse_record
from anvil.marketing_world_quiescence import Scope
from anvil.praxis_generic_contract import canonical


@dataclass(frozen=True, slots=True)
class _OriginalReceiverFacts:
    original: OriginalBinding = field(repr=False)
    operator_id: UUID
    peer_login: str
    registrar_login: str
    channel_qualification_id: UUID
    verifier_profile_sha256: str
    receiver_pid: int
    receiver_start_ticks: int
    receiver_uid: int
    receiver_gid: int
    evidence_references: tuple = field(repr=False)
    private_grade_transport_raw: bytes = field(repr=False)
    private_actor_transport_raw: bytes = field(repr=False)
    private_result_transport_raw: bytes = field(repr=False)
    profile_raw: bytes = field(repr=False)

    def __reduce__(self):
        raise TypeError('original receiver custody cannot be serialized or resumed')


def _original_receiver_facts(request, records, context):
    """Derive expectations before peer response, from original operator assets.

    This is consistency and custody, not a new qualification producer. Actual
    profile and policy admissions must exist independently before gates open.
    IDs, source/Q pins, expiry and database identities are never learned from a
    public-ready message, registry lookup or registrar response.
    """
    host = _parse_record(dict(records.records)['host'])['payload']
    profile = host['attester_receiver']
    expected = {'schema_version', 'peer_binding_id', 'enrollment_id', 'operator_id',
                'peer_database_login', 'registrar_database_login', 'channel_qualification_id',
                'producer_qualification_sha256', 'verifier_profile_sha256', 'attester_profile_sha256',
                'status_transport', 'private_grade_transport', 'private_actor_transport', 'private_result_transport',
                'private_capture_profile',
                'expires_at', 'receiver_pid', 'receiver_start_ticks',
                'receiver_uid', 'receiver_gid', 'independent_evidence'}
    if type(profile) is not dict or set(profile) != expected or profile['schema_version'] != 'anvil.marketing-attester-receiver-profile.v1':
        raise ValueError('marketing_original_independently_qualified_receiver_profile_required')
    request_pin = hashlib.sha256(request.canonical_bytes).hexdigest()
    if request_pin != records.request_sha256 or context['request_sha256'] != request_pin:
        raise ValueError('marketing_receiver_original_request_changed')
    for name in ('producer_qualification_sha256', 'verifier_profile_sha256', 'attester_profile_sha256'):
        if type(profile[name]) is not str or not re.fullmatch(r'[a-f0-9]{64}', profile[name]):
            raise ValueError('marketing_original_receiver_profile_hash_required')
    for name in ('receiver_pid', 'receiver_start_ticks', 'receiver_uid', 'receiver_gid'):
        if type(profile[name]) is not int or profile[name] < (1 if name in ('receiver_pid', 'receiver_start_ticks') else 0):
            raise ValueError('marketing_original_receiver_process_identity_required')
    for name in ('peer_database_login', 'registrar_database_login'):
        if type(profile[name]) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', profile[name]):
            raise ValueError('marketing_original_receiver_database_identity_required')
    if profile['peer_database_login'] == profile['registrar_database_login']:
        raise ValueError('marketing_disjoint_original_operator_identities_required')
    references = profile['independent_evidence']
    if type(references) is not dict or set(references) != REQUIRED_EVIDENCE:
        raise ValueError('marketing_original_six_independent_evidence_policies_required')
    pins = []
    for name in sorted(REQUIRED_EVIDENCE):
        value = references[name]
        if (type(value) is not dict or set(value) != {'policy_sha256', 'receipt_sha256'}
                or any(type(pin) is not str or not re.fullmatch(r'[a-f0-9]{64}', pin) for pin in value.values())):
            raise ValueError('marketing_original_independent_evidence_reference_required')
        pins.append((name, value['policy_sha256'], value['receipt_sha256']))
    scope_raw = _parse_record(dict(records.records)['world'])['payload']['stop_scope']
    scope = Scope.model_validate(scope_raw)
    if canonical(scope.model_dump(mode='json')) != canonical(scope_raw):
        raise ValueError('marketing_original_receiver_world_scope_required')
    transport = Transport.model_validate(profile['status_transport'])
    from anvil.marketing_private_actor_auth import PrivateActorTransport
    from anvil.marketing_private_grade_auth import PrivateGradeTransport
    from anvil.marketing_private_result_auth import PrivateResultTransport

    grade_transport = PrivateGradeTransport.model_validate_json(canonical(profile['private_grade_transport']))
    actor_transport = PrivateActorTransport.model_validate_json(canonical(profile['private_actor_transport']))
    result_transport = PrivateResultTransport.model_validate_json(canonical(profile['private_result_transport']))
    from anvil.marketing_capture_attestation import STOP
    from anvil.marketing_native_verifier_renderer import (
        private_context_assets,
        validate_private_program,
    )
    from anvil.marketing_private_capture_check import CONTROLS as CAPTURE_CONTROLS
    from anvil.marketing_private_capture_check import PrivateCaptureProfile

    capture_profile = PrivateCaptureProfile.model_validate_json(canonical(profile['private_capture_profile']))
    image = _parse_record(dict(records.records)['image'])['payload']
    _, private_program = private_context_assets(records)
    if (set(capture_profile.controls) != CAPTURE_CONTROLS
            or capture_profile.not_after > STOP
            or capture_profile.api_source_sha256 != grade_transport.source_sha256
            or capture_profile.runtime_image_digest != image['engine_image_id']
            or capture_profile.private_program_sha256 != hashlib.sha256(validate_private_program(private_program)).hexdigest()):
        raise ValueError('marketing_original_independent_whole_capture_profile_required_before_sdk')
    if (actor_transport.wire_limit > grade_transport.file_limits['actor-output.json']
            or context['output_bytes'] > actor_transport.wire_limit
            or any(getattr(actor_transport, key) != getattr(grade_transport, key) for key in
                   ('origin', 'api_image_digest', 'source_sha256', 'ca_bundle_sha256'))):
        raise ValueError('marketing_original_actor_and_private_grade_frames_cannot_fit_before_sdk')
    if any(getattr(result_transport, key) != getattr(grade_transport, key) for key in
           ('origin', 'api_image_digest', 'source_sha256', 'ingress_evidence_sha256', 'ca_bundle_sha256')):
        raise ValueError('marketing_original_result_grade_transport_pair_required')
    expires = datetime.fromisoformat(profile['expires_at'].replace('Z', '+00:00'))
    operation = _parse_record(records.operation_bytes)
    operation_expiry = datetime.fromisoformat(operation['expires_at'])
    instant = datetime.now(timezone.utc)
    from time import monotonic

    # A fixed operator expiry must fit the already-created monotonic lifecycle.
    # No fresh TTL, current-time-based expiry or extended cleanup is minted.
    if (expires.tzinfo is None or operation_expiry.tzinfo is None
            or not instant < expires <= min(operation_expiry, transport.not_after, grade_transport.not_after,
                                             actor_transport.not_after, result_transport.not_after)
            or expires > capture_profile.not_after
            or (expires - instant).total_seconds() > context['deadline_monotonic'] - monotonic()):
        raise ValueError('marketing_original_receiver_expiry_exceeds_existing_operation')
    original = OriginalBinding.model_validate({
        'peer_binding_id': profile['peer_binding_id'], 'enrollment_id': profile['enrollment_id'],
        'request_sha256': request_pin, 'operation_nonce': context['operation_nonce'], 'boot_id': context['boot_id'],
        'profile_sha256': profile['attester_profile_sha256'],
        'producer_qualification_sha256': profile['producer_qualification_sha256'],
        'status_transport_sha256': hashlib.sha256(canonical(profile['status_transport'])).hexdigest(),
        'scope': scope_raw, 'expires_at': expires,
    })
    return _OriginalReceiverFacts(original, UUID(profile['operator_id']), profile['peer_database_login'],
        profile['registrar_database_login'], UUID(profile['channel_qualification_id']), profile['verifier_profile_sha256'],
        profile['receiver_pid'], profile['receiver_start_ticks'], profile['receiver_uid'], profile['receiver_gid'],
        tuple(pins), canonical(profile['private_grade_transport']), canonical(profile['private_actor_transport']),
        canonical(profile['private_result_transport']), canonical(profile))


async def _commit_peer_then_enrollment(request, records, facts, receipt, *, absolute_deadline):
    """Exact independent receiver path, no transaction factory or role injection.

    Neither the return value nor a public-ready response is proof of OS facts.
    The receiver must first construct the receipt from actual original owned
    handles and independently verified retained evidence; missing facts refuse.
    Each context must finish COMMIT+close before the next step is attempted.
    Any Unknown exits with no registrar/readback fallback or replay.
    """
    from anvil.marketing_operator_database import peer_transaction, registrar_transaction

    if type(facts) is not _OriginalReceiverFacts or type(receipt) is not IndependentOSReceipt:
        raise ValueError('marketing_exact_independent_receiver_custody_required')
    check_original(receipt.public_ready, facts.original)
    if (receipt.channel_qualification_id != facts.channel_qualification_id
            or receipt.verifier_profile_sha256 != facts.verifier_profile_sha256
            or receipt.producer_qualification_sha256 != facts.original.producer_qualification_sha256
            or tuple((name, receipt.independent_evidence[name].policy_sha256,
                      receipt.independent_evidence[name].receipt_sha256) for name in sorted(REQUIRED_EVIDENCE)) != facts.evidence_references):
        raise ValueError('marketing_original_receiver_qualified_evidence_changed')
    _remaining(absolute_deadline)
    async with peer_transaction(facts.original, facts.operator_id, facts.peer_login,
                                absolute_deadline=absolute_deadline) as connection:
        peer = await record_peer(connection, request, records, facts.original, receipt,
                                 absolute_deadline=absolute_deadline)
    # Reaching here means the separate peer transaction AND close completed.
    _remaining(absolute_deadline)
    ready_raw = canonical(receipt.public_ready.model_dump(mode='json'))
    async with registrar_transaction(facts.original, facts.operator_id, facts.registrar_login,
                                     absolute_deadline=absolute_deadline) as connection:
        enrollment = await register_public_ready(connection, ready_raw, facts.original,
                                                  absolute_deadline=absolute_deadline)
    # Only this branch may notify the original child. It still performs its OWN
    # separate observe_committed; these words cannot release graph by themselves.
    _remaining(absolute_deadline)
    return {
        'schema_version': 'anvil.marketing-original-enrollment-commits-observed.v1',
        'peer_binding_id': str(facts.original.peer_binding_id),
        'request_sha256': facts.original.request_sha256, 'operation_nonce': facts.original.operation_nonce,
        'public_ready': receipt.public_ready.model_dump(mode='json'),
        'peer_receipt_sha256': peer['peer_receipt_sha256'],
        'os_peer_receipt_sha256': peer['os_peer_receipt_sha256'],
        'enrollment': enrollment.model_dump(mode='json'),
        'capture_accepted': False, 'run_authority': 'not_granted',
    }


async def commit_peer_then_enrollment(*args, **kwargs):
    marketing_native_gate()
    return await _commit_peer_then_enrollment(*args, **kwargs)
