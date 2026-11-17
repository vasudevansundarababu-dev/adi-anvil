"""Independent receiver's fixed exec attester custody; no private key in parent.

Source only. Operational launch requires the original qualified receiver and
profile. Fixed public metadata and owned pidfds are the only exec inputs.
"""

import asyncio
import hashlib
import os
import secrets
import select
import signal
import socket
from time import monotonic

from anvil.marketing_attester_enrollment import check_original, parse_public_ready
from anvil.marketing_capture_attestation import _decode
from anvil.marketing_native_attempt import _write_at
from anvil.marketing_native_attester_key import KEY_PROOF_DOMAIN
from anvil.marketing_native_boundary import _bounded_canonical
from anvil.marketing_native_enrollment_client import _receive_packet, _send_packet
from anvil.marketing_native_kernel_scope import _remaining
from anvil.marketing_native_records import _parse_record
from anvil.praxis_generic_contract import canonical


class _IndependentAttesterProcess:
    __slots__ = ('_owner', '_child', '_pidfd', '_channel', '_state', '_ticks',
                 '_peer_observation_state', '_ready', '_ready_raw', '_proof_raw', '_passed', '_abort_state')

    def __init__(self, owner):
        self._owner = owner
        self._child = self._pidfd = self._channel = self._ticks = None
        self._state, self._peer_observation_state = 'unstarted', 'unobserved'
        self._ready = self._ready_raw = self._proof_raw = None
        self._passed = {}
        self._abort_state = 'unused'

    async def start(self, sdk_pidfd, graph_pidfd):
        from anvil.marketing_native_launcher import _process_identity, _runtime_assets
        from anvil.marketing_native_private_environment import ISOLATED_BASE_ENV

        if self._state != 'unstarted':
            raise ValueError('marketing_independent_attester_start_once_required')
        self._state = 'spawn_unknown_no_replay'
        owner = self._owner
        deadline = owner._phase_deadline
        _remaining(deadline)
        interpreter, _ = _runtime_assets(owner._records, owner._plan,
                                          {**owner._context, 'deadline_monotonic': deadline}, opening=True, private=True)
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
        parent.setblocking(False)
        receiver_pidfd = None
        try:
            receiver_pidfd = os.pidfd_open(os.getpid(), 0)
            inherited = (child.fileno(), receiver_pidfd, sdk_pidfd, graph_pidfd)
            if len(set(inherited)) != 4 or any(type(fd) is not int or fd < 3 for fd in inherited):
                raise ValueError('marketing_exact_original_attester_inherited_handles_required')
            self._passed = {name: {'fd': fd, 'device': os.fstat(fd).st_dev, 'inode': os.fstat(fd).st_ino}
                            for name, fd in zip(('channel', 'receiver_pidfd', 'sdk_pidfd', 'graph_pidfd'), inherited)}
            _write_at(owner._root, 'independent-attester-launch-intent.json', _bounded_canonical({
                'schema_version': 'anvil.marketing-independent-attester-launch-intent.v1',
                'request_sha256': owner._facts.original.request_sha256,
                'operation_nonce': owner._facts.original.operation_nonce,
                'original_deadline_monotonic': owner._context['deadline_monotonic'],
                'phase_deadline_monotonic': deadline, 'public_inherited_handles': self._passed,
                'private_key_in_parent': False, 'native_qualified': False, 'replay_permitted': False,
            }, 4096))
            self._channel, parent = parent, None
            self._child = await asyncio.wait_for(asyncio.create_subprocess_exec(
                str(interpreter), '-I', '-B', '-m', 'anvil.marketing_native_attester_worker',
                *(str(fd) for fd in inherited), str(owner._context['deadline_monotonic']),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                close_fds=True, pass_fds=inherited, start_new_session=True, umask=0o077,
                env=dict(ISOLATED_BASE_ENV),
            ), max(0, deadline - monotonic()))
            self._pidfd = os.pidfd_open(self._child.pid, 0)
            self._ticks = _process_identity(self._child.pid)
            child.close()  # Original worker endpoint is no longer held in parent.
            await _send_packet(self._channel, _bounded_canonical({
                'schema_version': 'anvil.marketing-independent-attester-start.v1',
                'request': owner._request.canonical_bytes.decode('utf-8'),
                'original_deadline_monotonic': owner._context['deadline_monotonic'],
            }, 16384), deadline=deadline)
            self._ready_raw = await _receive_packet(self._channel, deadline=deadline)
            self._ready = parse_public_ready(self._ready_raw)
            check_original(self._ready, owner._facts.original)
            self._state = 'public_ready_waiting_for_fixed_challenge'
            self.require_live()
        finally:
            if receiver_pidfd is not None:
                os.close(receiver_pidfd)
            child.close()
            if parent is not None:
                parent.close()

    def require_live(self):
        if (self._state not in {'public_ready_waiting_for_fixed_challenge', 'key_possession_observed',
                               'registration_retained', 'private_input_sealed'}
                or self._child is None or self._pidfd is None or self._child.returncode is not None
                or select.select([self._pidfd], [], [], 0)[0]
                or monotonic() >= self._owner._context['deadline_monotonic'] - self._owner._plan['bounds']['cleanup_seconds']):
            raise RuntimeError('marketing_original_independent_attester_not_live')

    async def verify_key_possession(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        self.require_live()
        if self._state != 'public_ready_waiting_for_fixed_challenge':
            raise ValueError('marketing_attester_fixed_challenge_once_required')
        self._state = 'key_proof_unknown_no_replay'
        challenge = secrets.token_bytes(32)
        deadline = self._owner._phase_deadline
        await _send_packet(self._channel, _bounded_canonical({
            'schema_version': 'anvil.marketing-attester-key-challenge.v1', 'receiver_challenge_hex': challenge.hex(),
        }, 4096), deadline=deadline)
        raw = await _receive_packet(self._channel, deadline=deadline)
        proof = _parse_record(raw)
        fields = {'schema_version', 'public_ready_sha256', 'receiver_challenge_hex', 'signature_base64url'}
        if (set(proof) != fields or proof['schema_version'] != 'anvil.marketing-attester-key-possession.v1'
                or proof['public_ready_sha256'] != hashlib.sha256(self._ready_raw).hexdigest()
                or proof['receiver_challenge_hex'] != challenge.hex()):
            raise ValueError('marketing_original_attester_key_possession_changed')
        signature = _decode(proof['signature_base64url'], 100)
        if len(signature) != 64:
            raise ValueError('marketing_original_attester_key_proof_signature_required')
        claims = {key: value for key, value in proof.items() if key != 'signature_base64url'}
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(self._ready.public_key_hex)).verify(signature, KEY_PROOF_DOMAIN + canonical(claims))
        _remaining(deadline)
        _write_at(self._owner._root, 'attester-key-possession-proof.json', raw)
        self._proof_raw, self._state = raw, 'key_possession_observed'
        self.require_live()

    async def retain_registration(self, reply):
        self.require_live()
        if self._state != 'key_possession_observed':
            raise ValueError('marketing_attester_registration_delivery_once_required')
        self._state = 'registration_delivery_unknown_no_replay'
        deadline = self._owner._phase_deadline
        await _send_packet(self._channel, _bounded_canonical(reply, 32768), deadline=deadline)
        value = _parse_record(await _receive_packet(self._channel, deadline=deadline))
        if (set(value) != {'schema_version', 'request_sha256', 'operation_nonce', 'capture_accepted', 'run_authority'}
                or value['schema_version'] != 'anvil.marketing-attester-registration-retained.v1'
                or value['request_sha256'] != self._owner._facts.original.request_sha256
                or value['operation_nonce'] != self._owner._facts.original.operation_nonce
                or value['capture_accepted'] is not False or value['run_authority'] != 'not_granted'):
            raise RuntimeError('marketing_attester_registration_delivery_unknown_no_retry')
        self._state = 'registration_retained'
        self.require_live()

    async def abort(self):
        if self._abort_state != 'unused':
            raise RuntimeError('marketing_attester_abort_unknown_no_retry')
        self._abort_state = 'abort_unknown_no_retry'
        deadline = self._owner._context['deadline_monotonic']
        if self._child is not None:
            if self._child.returncode is None:
                if self._pidfd is None:
                    # This is the original unreaped Process object retained
                    # immediately on return from spawn, never a looked-up PID.
                    try:
                        self._child.kill()
                    except ProcessLookupError:
                        pass
                else:
                    try:
                        signal.pidfd_send_signal(self._pidfd, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                _remaining(deadline)  # Signal first, but never renew reap budget.
                await asyncio.wait_for(self._child.wait(), max(0, deadline - monotonic()))
            else:
                await self._child.wait()
        self._abort_state = 'owned_attester_exit_observed'

    async def seal_private_input(self):
        self.require_live()
        if self._state != 'registration_retained':
            raise ValueError('marketing_attester_private_seal_once_required')
        self._state = 'private_seal_unknown_no_retry'
        owner = self._owner
        deadline = owner._context['deadline_monotonic'] - owner._plan['bounds']['cleanup_seconds'] - 8
        await _send_packet(self._channel, _bounded_canonical({
            'schema_version': 'anvil.marketing-attester-seal-private-input.v1',
            'request_sha256': owner._facts.original.request_sha256,
            'operation_nonce': owner._facts.original.operation_nonce,
        }, 4096), deadline=deadline)
        raw = await _receive_packet(self._channel, deadline=deadline)
        value = _parse_record(raw)
        if (set(value) != {'schema_version', 'request_sha256', 'operation_nonce', 'seal_receipt_sha256',
                          'capture_accepted', 'native_qualified', 'run_authority'}
                or value['schema_version'] != 'anvil.marketing-attester-private-input-ready.v1'
                or value['request_sha256'] != owner._facts.original.request_sha256
                or value['operation_nonce'] != owner._facts.original.operation_nonce
                or value['seal_receipt_sha256'] != hashlib.sha256(
                    owner._store._read(owner._root, 'private-verifier-seal-receipt.json')).hexdigest()
                or value['capture_accepted'] is not False or value['native_qualified'] is not False
                or value['run_authority'] != 'not_granted'):
            raise RuntimeError('marketing_attester_private_seal_unknown_no_retry')
        self._state = 'private_input_sealed'
        self.require_live()
        return value

    async def finalize_owned_capture(self):
        self.require_live()
        if self._state != 'private_input_sealed':
            raise ValueError('marketing_attester_final_status_trigger_once_required')
        self._state = 'final_status_unknown_no_retry'
        deadline = self._owner._context['deadline_monotonic'] - self._owner._plan['bounds']['cleanup_seconds']
        await _send_packet(self._channel, _bounded_canonical({
            'schema_version': 'anvil.marketing-attester-observe-final-status.v1',
            'request_sha256': self._owner._facts.original.request_sha256,
            'operation_nonce': self._owner._facts.original.operation_nonce,
        }, 4096), deadline=deadline)
        raw = await _receive_packet(self._channel, deadline=deadline)
        value = _parse_record(raw)
        if (set(value) != {'schema_version', 'request_sha256', 'operation_nonce', 'capture_response_sha256',
                          'capture_wire_sha256', 'capture_accepted'}
                or value['schema_version'] != 'anvil.marketing-attester-owned-capture-observation.v1'
                or value['request_sha256'] != self._owner._facts.original.request_sha256
                or value['operation_nonce'] != self._owner._facts.original.operation_nonce
                or value['capture_accepted'] is not True):
            raise RuntimeError('marketing_attester_original_final_status_reply_unknown')
        response = self._owner._store._read(self._owner._root, 'attester-owned-final-capture-response.json')
        wire = self._owner._store._read(self._owner._root, 'private-final-capture-wire.json')
        if (hashlib.sha256(response).hexdigest() != value['capture_response_sha256']
                or hashlib.sha256(wire).hexdigest() != value['capture_wire_sha256']):
            raise ValueError('marketing_attester_own_retained_capture_bytes_changed')
        from anvil.marketing_private_capture_receipt import validate_capture_acceptance

        validate_capture_acceptance(response, _parse_record(self._owner._store._read(
            self._owner._root, 'attester-grade-enrollment.json')), value['capture_wire_sha256'])
        code = await asyncio.wait_for(self._child.wait(), max(0, deadline - monotonic()))
        if type(code) is not int or code != 0:
            raise RuntimeError('marketing_attester_status_worker_exit_unknown')
        self._state = 'own_status_and_key_worker_exit_observed_NOT_capture'
        return value

    def close(self):
        if self._channel is not None:
            self._channel.close()
            self._channel = None
        if self._pidfd is not None:
            os.close(self._pidfd)
            self._pidfd = None
