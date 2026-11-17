"""Child-private ephemeral key custody; not OS admission or a signing service.

Only the fixed independent attester worker may own this object. No private bytes
are exported, serialized, persisted or returned over IPC. There is no arbitrary
claims/body signing method. Actual exec/isolation/profile qualification remains
mandatory behind the unchanged native gates.
"""

import base64
import hashlib
import os
from datetime import datetime, timezone

from anvil.marketing_attester_enrollment import (
    OriginalBinding,
    parse_public_ready,
    validate_receipt,
)
from anvil.marketing_capture_status import DOMAIN as STATUS_DOMAIN
from anvil.marketing_capture_status import claims as status_claims
from anvil.marketing_capture_status import verify as verify_status_header
from anvil.marketing_native_kernel_scope import _remaining
from anvil.praxis_generic_contract import canonical

KEY_PROOF_DOMAIN = b'anvil.marketing.attester.key-possession.v1\x00'


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


class _EphemeralAttester:
    __slots__ = ('__key', '_pid', '_original', '_ready', '_deadline', '_enrollment',
                 '_state', '_status_state', '_capture_state', '_challenge_state', '_grade_state',
                 '_plan_sha256', '_grade_transport_raw', '_actor_transport_raw', '_grade_observation', '_grade_status')

    def __init__(self, original, *, original_deadline, plan_sha256, private_grade_transport_raw,
                 private_actor_transport_raw):
        # This private constructor is invoked after the worker's gated exec and
        # original independent-receiver/profile checks, never by its parent.
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        if type(original) is not OriginalBinding:
            raise ValueError('marketing_original_attester_binding_required')
        from anvil.marketing_private_grade_auth import PrivateGradeTransport

        if type(plan_sha256) is not str or len(plan_sha256) != 64 or any(c not in '0123456789abcdef' for c in plan_sha256):
            raise ValueError('marketing_original_attester_plan_hash_required')
        grade_transport = PrivateGradeTransport.model_validate_json(private_grade_transport_raw)
        if grade_transport.not_after < original.expires_at:
            raise ValueError('marketing_original_private_grade_transport_expiry_required')
        _remaining(original_deadline)
        if datetime.now(timezone.utc) >= original.expires_at:
            raise TimeoutError('marketing_original_attester_expired_before_key_generation')
        self._pid, self._original, self._deadline = os.getpid(), original, original_deadline
        self._state, self._status_state, self._capture_state = 'key_generation_unknown_no_replay', 'unused', 'unused'
        self._enrollment = None
        self._plan_sha256, self._grade_transport_raw = plan_sha256, private_grade_transport_raw
        from anvil.marketing_private_actor_auth import PrivateActorTransport

        actor_transport = PrivateActorTransport.model_validate_json(private_actor_transport_raw)
        if (actor_transport.wire_limit > grade_transport.file_limits['actor-output.json']
                or actor_transport.not_after < original.expires_at
                or any(getattr(actor_transport, name) != getattr(grade_transport, name) for name in
                       ('origin', 'api_image_digest', 'source_sha256', 'ingress_evidence_sha256', 'ca_bundle_sha256'))):
            raise ValueError('marketing_original_actor_grade_transport_pair_required')
        self._actor_transport_raw = private_actor_transport_raw
        self._grade_state, self._grade_observation, self._grade_status = 'unused', None, None
        self._challenge_state = 'unused'
        self.__key = Ed25519PrivateKey.generate()
        public = self.__key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        raw = canonical({
            'schema_version': 'anvil.marketing-attester-public-ready.v1',
            'peer_binding_id': str(original.peer_binding_id), 'request_sha256': original.request_sha256,
            'operation_nonce': original.operation_nonce, 'boot_id': str(original.boot_id),
            'profile_sha256': original.profile_sha256, 'public_key_hex': public.hex(),
            'public_key_fingerprint_sha256': hashlib.sha256(public).hexdigest(),
        })
        self._ready = parse_public_ready(raw)
        self._state = 'public_ready_not_enrolled'

    def __reduce__(self):
        raise TypeError('ephemeral attester custody cannot be serialized or resumed')

    def __copy__(self):
        raise TypeError('ephemeral attester custody cannot be copied')

    def __deepcopy__(self, _memo):
        raise TypeError('ephemeral attester custody cannot be copied')

    def __repr__(self):
        return '<private ephemeral attester custody>'

    def _current(self):
        if self._pid != os.getpid() or self.__key is None or self._state == 'closed':
            raise ValueError('marketing_original_attester_process_custody_required')
        _remaining(self._deadline)
        if datetime.now(timezone.utc) >= self._original.expires_at:
            raise TimeoutError('marketing_original_attester_expiry')

    def public_ready_once(self):
        self._current()
        if self._state != 'public_ready_not_enrolled':
            raise ValueError('marketing_attester_public_ready_once_required')
        self._state = 'registration_unknown_no_replay'
        return canonical(self._ready.model_dump(mode='json'))

    def retain_registration(self, value):
        """Receiver's validated receipt is binding data, not COMMIT/run proof.

        Graph-child release still requires its separate observed committed read.
        This object does not expose a graph-release or registration-success flag.
        """
        self._current()
        if self._state != 'registration_unknown_no_replay' or self._challenge_state != 'fixed_peer_proof_emitted':
            raise ValueError('marketing_attester_registration_once_required')
        self._state = 'registration_validation_unknown_no_replay'
        receipt = validate_receipt(value, self._original, self._ready)
        self._enrollment = receipt.model_dump(mode='json')
        self._state = 'registration_retained_NOT_commit_or_run_authority'

    def prove_original_key_once(self, challenge):
        """One fixed-domain key-possession proof, never arbitrary claims/body.

        The only variable is a 32-byte receiver challenge. All identity fields
        are generated from this process's original binding/public key. This
        proof cannot authenticate a status GET or capture POST in their distinct
        domains, and it does not establish OS/profile qualification.
        """
        self._current()
        if (self._state != 'registration_unknown_no_replay' or self._challenge_state != 'unused'
                or type(challenge) is not bytes or len(challenge) != 32):
            raise ValueError('marketing_original_fixed_peer_challenge_once_required')
        self._challenge_state = 'proof_unknown_no_replay'
        claims = {'schema_version': 'anvil.marketing-attester-key-possession.v1',
                  'public_ready_sha256': hashlib.sha256(canonical(self._ready.model_dump(mode='json'))).hexdigest(),
                  'receiver_challenge_hex': challenge.hex()}
        raw = canonical(claims)
        signature = self.__key.sign(KEY_PROOF_DOMAIN + raw)
        self._challenge_state = 'fixed_peer_proof_emitted'
        return canonical({**claims, 'signature_base64url': _b64(signature)})

    def _direct_status(self, *, phase_deadline=None):
        """Fixed empty GET only; no caller-selected claims/header/path/body."""
        from anvil.marketing_capture_status_client import read

        self._current()
        raw = canonical(status_claims(self._enrollment))
        if len(raw) > 2048:
            raise ValueError('marketing_attester_fixed_status_claim_capacity')
        signature = self.__key.sign(STATUS_DOMAIN + raw)
        header = 'v1.' + _b64(raw) + '.' + _b64(signature)
        verify_status_header(header, self._enrollment)
        deadline = self._deadline if phase_deadline is None else min(self._deadline, phase_deadline)
        _remaining(deadline)
        observation = read(self._enrollment, header, absolute_deadline=deadline)
        if observation.origin != 'certificate_verified_api':
            raise ValueError('marketing_attester_requires_own_certificate_verified_status')
        self._current()
        return observation

    def read_owned_final_status(self, *, phase_deadline):
        """Separate final-phase own GET, never a retry of a failed grade read."""
        self._current()
        if (self._state != 'registration_retained_NOT_commit_or_run_authority'
                or self._status_state != 'unused' or self._grade_state != 'own_private_input_observed'):
            raise ValueError('marketing_attester_status_read_once_required')
        self._status_state = 'read_unknown_no_retry'
        observation = self._direct_status(phase_deadline=phase_deadline)
        self._status_state = 'own_direct_status_observed_NOT_capture_authority'
        return observation

    def read_owned_grade_input(self, store, root, actual_framework_identity, *, phase_deadline):
        """Own READY status then own fixed separately signed private-grade GET.

        The worker obtains identity from its actual retained authenticated SDK
        entry. The API independently compares identity/manifest to its private
        original peer record; values never become expectations by lookup TOFU.
        """
        from anvil.marketing_capture_status import validate_response
        from anvil.marketing_capture_verifier import Identity
        from anvil.marketing_native_attempt import _write_at
        from anvil.marketing_native_private_actor_client import retain_own_actor
        from anvil.marketing_native_private_grade_client import read_own_private_grade
        from anvil.marketing_native_records import _parse_record
        from anvil.marketing_private_actor_auth import (
            DOMAIN as ACTOR_DOMAIN,
        )
        from anvil.marketing_private_actor_auth import (
            PrivateActorTransport,
        )
        from anvil.marketing_private_actor_auth import (
            claims as actor_claims,
        )
        from anvil.marketing_private_actor_auth import (
            verify as actor_verify,
        )
        from anvil.marketing_private_grade_auth import DOMAIN, PrivateGradeTransport, claims, verify

        self._current()
        _remaining(min(self._deadline, phase_deadline))
        if self._state != 'registration_retained_NOT_commit_or_run_authority' or self._grade_state != 'unused':
            raise ValueError('marketing_attester_private_grade_phase_once_required')
        identity = Identity.model_validate_json(canonical(actual_framework_identity))
        if (identity.job_id != self._original.scope.job_id or identity.request_sha256 != self._original.request_sha256
                or identity.operation_nonce != self._original.operation_nonce or identity.plan_sha256 != self._plan_sha256):
            raise ValueError('marketing_attester_original_private_grade_identity_required')
        self._grade_state = 'own_grade_read_unknown_no_retry'
        observation = self._direct_status(phase_deadline=phase_deadline)
        status = validate_response(observation.raw_body, self._enrollment)
        if status.state != 'ready':
            raise ValueError('marketing_attester_actual_original_ready_manifest_required')
        enrolled = {**self._enrollment, 'identity': identity.model_dump(mode='json'),
                    'manifest_id': str(status.manifest_id), 'descriptor': status.descriptor,
                    'private_grade_transport': PrivateGradeTransport.model_validate_json(
                        self._grade_transport_raw).model_dump(mode='json'),
                    'private_actor_transport': PrivateActorTransport.model_validate_json(
                        self._actor_transport_raw).model_dump(mode='json')}
        _write_at(root, 'attester-owned-grade-ready-status.json', observation.raw_body, mode=0o400)
        _write_at(root, 'attester-grade-enrollment.json', canonical(enrolled), mode=0o400)
        # Fixed original root files only. No body/claims are supplied through
        # the receiver command, and partial actor stop is never whole shutdown.
        actor = store._read(root, 'captured-actor-output.json')
        stop_raw = store._read(root, 'actor-stop.json')
        collection_raw = store._read(root, 'captured-collection-receipt.json')
        stop, collection = _parse_record(stop_raw), _parse_record(collection_raw)
        if (stop.get('schema_version') != 'anvil.marketing-actor-stop.v2'
                or stop.get('actor_output_sha256') != hashlib.sha256(actor).hexdigest()
                or stop.get('collection_receipt_sha256') != hashlib.sha256(collection_raw).hexdigest()
                or collection.get('schema_version') != 'anvil.marketing-collection-capture.v1'):
            raise ValueError('marketing_attester_original_actor_capture_pair_required')
        artifact = {'wire_bytes': len(actor), 'wire_sha256': hashlib.sha256(actor).hexdigest(),
                    'actor_stop_sha256': hashlib.sha256(stop_raw).hexdigest(),
                    'collection_receipt_sha256': hashlib.sha256(collection_raw).hexdigest()}
        actor_raw = canonical(actor_claims(enrolled, artifact))
        if len(actor_raw) > 2048:
            raise ValueError('marketing_attester_fixed_actor_claim_capacity')
        actor_header = 'v1.' + _b64(actor_raw) + '.' + _b64(self.__key.sign(ACTOR_DOMAIN + actor_raw))
        actor_verify(actor_header, enrolled)
        custody = retain_own_actor(enrolled, actor_header, actor, absolute_deadline=min(self._deadline, phase_deadline))
        _write_at(root, 'attester-owned-actor-custody.json', custody)
        raw = canonical(claims(enrolled))
        if len(raw) > 2048:
            raise ValueError('marketing_attester_private_grade_claim_capacity')
        header = 'v1.' + _b64(raw) + '.' + _b64(self.__key.sign(DOMAIN + raw))
        verify(header, enrolled)
        private = read_own_private_grade(enrolled, header, absolute_deadline=min(self._deadline, phase_deadline))
        self._current()
        self._grade_status, self._grade_observation = observation, private
        self._grade_state = 'own_private_input_observed'
        return private

    def upload_owned_result(self, store, root, facts, *, phase_deadline):
        """Fixed own original files only, after the worker observes full stop."""
        from anvil.marketing_native_attempt import _write_at
        from anvil.marketing_native_private_post import post_owned_result
        from anvil.marketing_native_records import _parse_record
        from anvil.marketing_private_result_auth import (
            DOMAIN,
            PrivateResultTransport,
            claims,
            verify,
        )
        from anvil.marketing_private_result_frame import ResultFrame

        self._current()
        if self._capture_state != 'unused' or self._grade_state != 'own_private_input_observed':
            raise ValueError('marketing_attester_owned_result_once_required')
        self._capture_state = 'result_upload_unknown_no_retry'
        enrollment = _parse_record(store._read(root, 'attester-grade-enrollment.json'))
        enrollment['private_result_transport'] = PrivateResultTransport.model_validate_json(
            facts.private_result_transport_raw).model_dump(mode='json')
        result = store._read(root, 'private-verifier-result.json')
        process = store._read(root, 'private-verifier-process.json')
        from anvil.marketing_capture_verifier import (
            OriginalVerifierBinding,
            validate_private_result,
        )

        validate_private_result(result, OriginalVerifierBinding.model_validate_json(
            store._read(root, 'private-verifier-binding.json')))
        frame = ResultFrame.model_validate_json(canonical({
            'schema_version': 'anvil.marketing-private-result-upload.v1',
            **{k: enrollment[k] for k in ('enrollment_id', 'manifest_id', 'request_sha256', 'operation_nonce', 'identity', 'scope')},
            'grade_frame_sha256': self._grade_observation.body_sha256,
            'documents': {'verifier_result': result.decode('utf-8'), 'process_receipt': process.decode('utf-8')},
        }))
        raw = canonical(frame.model_dump(mode='json'))
        artifact = {'wire_bytes': len(raw), 'wire_sha256': hashlib.sha256(raw).hexdigest(),
            'grade_frame_sha256': self._grade_observation.body_sha256,
            'verifier_result_sha256': hashlib.sha256(result).hexdigest(),
            'process_receipt_sha256': hashlib.sha256(process).hexdigest()}
        claim_raw = canonical(claims(enrollment, artifact))
        if len(claim_raw) > 2048:
            raise ValueError('marketing_attester_fixed_result_claim_capacity')
        signed = 'v1.' + _b64(claim_raw) + '.' + _b64(self.__key.sign(DOMAIN + claim_raw))
        verify(signed, enrollment)
        response = post_owned_result(enrollment, signed, raw, deadline=min(self._deadline, phase_deadline))
        _write_at(root, 'attester-owned-result-custody.json', response, mode=0o400)
        self._capture_state = 'result_custody_observed'
        return response

    def upload_owned_capture(self, store, root, facts, context, plan, final_status):
        """One fixed capture built from this worker's own final observations."""
        from anvil.marketing_capture_attestation import AUDIENCE, DOMAIN, PATH, SCHEMA, verify
        from anvil.marketing_native_attempt import _write_at
        from anvil.marketing_native_private_finalize import produce_six_documents
        from anvil.marketing_native_private_post import post_owned_capture
        from anvil.marketing_native_records import _parse_record

        self._current()
        if (self._capture_state != 'result_custody_observed'
                or self._status_state != 'own_direct_status_observed_NOT_capture_authority'):
            raise ValueError('marketing_attester_original_result_final_status_required')
        self._capture_state = 'final_capture_unknown_no_retry'
        custody = _parse_record(store._read(root, 'attester-owned-result-custody.json'))
        raw = produce_six_documents(store, root, facts, context, plan, final_status, custody)
        claims = {'schema_version': SCHEMA, **{k: self._enrollment[k] for k in (
            'enrollment_id', 'request_sha256', 'operation_nonce', 'boot_id', 'profile_sha256',
            'producer_qualification_sha256', 'body_schema')}, 'audience': AUDIENCE, 'method': 'POST', 'path': PATH,
            'expires_at': self._original.expires_at.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'wire_bytes': len(raw), 'wire_sha256': hashlib.sha256(raw).hexdigest()}
        claim_raw = canonical(claims)
        if len(claim_raw) > 2048:
            raise ValueError('marketing_attester_fixed_capture_claim_capacity')
        signed = 'v1.' + _b64(claim_raw) + '.' + _b64(self.__key.sign(DOMAIN + claim_raw))
        verify(signed, self._enrollment)
        response = post_owned_capture(self._enrollment, signed, raw,
            deadline=min(self._deadline, context['deadline_monotonic'] - plan['bounds']['cleanup_seconds']))
        _write_at(root, 'attester-owned-final-capture-response.json', response, mode=0o400)
        from anvil.marketing_private_capture_receipt import validate_capture_acceptance

        accepted = validate_capture_acceptance(response, self._enrollment, hashlib.sha256(raw).hexdigest())
        if (accepted['verifier_result_id'] != custody['id']
                or any(accepted[k] != custody[k] for k in (
                    'grade_frame_sha256', 'verifier_result_sha256', 'process_receipt_sha256', 'grade_status'))):
            raise ValueError('marketing_actual_accepted_private_result_custody_changed')
        # Actual accepted response semantics are independently checked by the
        # API contract before any success result is emitted by the worker.
        self._capture_state = 'own_api_accepted_capture_observed_NOT_run_authority'
        return response

    def close(self):
        # Python/cryptography do not promise allocator erasure. Actual process
        # exit and dump/core/ptrace isolation are mandatory qualification items.
        self.__key = None
        self._state = 'closed'
