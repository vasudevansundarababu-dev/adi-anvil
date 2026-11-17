"""Fixed independent exec key worker. No lease, DB credential or signing RPC.

Only the independently bound receiver's private seqpacket channel is accepted.
Keys are generated here after exec and never enter the receiver/control heap.
Actual isolation/profile/TLS/native qualification stays gated and unexecuted.
"""

import ctypes
import os
import select
import signal
import socket
import struct
import sys
from time import monotonic

from anvil.marketing_attester_enrollment import validate_receipt
from anvil.marketing_native_actor_scope import _pid_identity
from anvil.marketing_native_attempt import MarketingAttemptStore, _write_at
from anvil.marketing_native_attester_key import _EphemeralAttester
from anvil.marketing_native_boundary import (
    _bounded_canonical,
    marketing_native_gate,
    prepare_marketing_request,
)
from anvil.marketing_native_enrollment_receiver import _original_receiver_facts
from anvil.marketing_native_kernel_scope import _read, _remaining
from anvil.marketing_native_mounts import _opening_context
from anvil.marketing_native_private_records import resolve_private_marketing_records
from anvil.marketing_native_records import _parse_record


def _packet(channel, parent_pidfd, *, deadline):
    _remaining(deadline)
    ready, _, _ = select.select([channel, parent_pidfd], [], [], max(0, deadline - monotonic()))
    if parent_pidfd in ready or channel not in ready:
        raise RuntimeError('marketing_original_attester_receiver_lost')
    raw, ancillary, flags, _ = channel.recvmsg(32769, 0, socket.MSG_CMSG_CLOEXEC)
    if not raw or len(raw) > 32768 or ancillary or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
        raise RuntimeError('marketing_attester_fixed_packet_unknown_no_retry')
    _remaining(deadline)
    return raw


def _send(channel, raw, *, deadline):
    _remaining(deadline)
    if not select.select([], [channel], [], max(0, deadline - monotonic()))[1]:
        raise TimeoutError('marketing_attester_original_send_cutoff')
    if channel.send(raw, socket.MSG_NOSIGNAL) != len(raw):
        raise RuntimeError('marketing_attester_original_send_unknown_no_retry')


def _owned_pidfd(proc, fd, expected_pid, expected_ticks, nonce, role, deadline):
    raw = _read(proc, 'self/fdinfo/' + str(fd), 1024, deadline)
    fields = {}
    for line in raw.splitlines():
        key, separator, value = line.partition(':')
        if not separator or key in fields:
            raise ValueError('marketing_attester_exact_original_pidfd_required')
        fields[key] = value.strip()
    if (fields.get('Pid') != str(expected_pid) or select.select([fd], [], [], 0)[0]
            or _pid_identity(proc, expected_pid, deadline)[1] != expected_ticks
            or _read(proc, str(expected_pid) + '/cgroup', 4096, deadline).strip()
            != '0::/anvil-marketing/' + nonce[:20] + '/' + role):
        raise ValueError('marketing_attester_original_actor_pidfd_binding_changed')


def _run(channel_fd, receiver_pidfd, sdk_pidfd, graph_pidfd):
    from anvil.marketing_native_actor_hardening import harden_watchdog

    # Only exec-inherited public channel/pidfds. No caller-selected import,
    # callback, URL, provider key, SQL connection or original job lease.
    # The key must die if its original independent receiver dies. This is set
    # before privilege reduction and checked again against the original pidfd.
    for descriptor in (0, 1, 2, channel_fd, receiver_pidfd, sdk_pidfd, graph_pidfd):
        os.set_inheritable(descriptor, False)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'attester original receiver death binding failed')
    harden_watchdog()
    channel = socket.socket(fileno=channel_fd)
    key = None
    proc = None
    try:
        if (channel.family != socket.AF_UNIX or channel.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET
                or len({channel_fd, receiver_pidfd, sdk_pidfd, graph_pidfd}) != 4):
            raise ValueError('marketing_attester_fixed_owned_channel_and_handles_required')
        # The initial hard cutoff is supplied as the original monotonic value,
        # then independently compared with the original retained context below.
        initial_deadline = float(sys.argv[5])
        _remaining(initial_deadline)
        raw = _packet(channel, receiver_pidfd, deadline=initial_deadline)
        initial = _parse_record(raw)
        if (set(initial) != {'schema_version', 'request', 'original_deadline_monotonic'}
                or initial['schema_version'] != 'anvil.marketing-independent-attester-start.v1'
                or initial['original_deadline_monotonic'] != initial_deadline):
            raise ValueError('marketing_attester_original_start_metadata_required')
        request = prepare_marketing_request(initial['request'].encode('utf-8'))
        records = resolve_private_marketing_records(request)
        with MarketingAttemptStore() as store:
            root, claim, plan = _opening_context(store, request)
            try:
                context = _parse_record(store._read(root, 'component-context.json'))
                facts = _original_receiver_facts(request, records, context)
                if context['deadline_monotonic'] != initial_deadline:
                    raise ValueError('marketing_attester_original_deadline_changed')
                peer = struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
                proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
                if (peer != (facts.receiver_pid, facts.receiver_uid, facts.receiver_gid)
                        or os.getppid() != facts.receiver_pid
                        or _pid_identity(proc, facts.receiver_pid, initial_deadline)[1] != facts.receiver_start_ticks
                        or _read(proc, 'sys/kernel/random/boot_id', 64, initial_deadline).strip() != context['boot_id']):
                    raise ValueError('marketing_attester_original_independent_receiver_required')
                parent_info = _read(proc, 'self/fdinfo/' + str(receiver_pidfd), 1024, initial_deadline)
                if ('Pid:\t' + str(facts.receiver_pid) + '\n') not in parent_info or select.select([receiver_pidfd], [], [], 0)[0]:
                    raise ValueError('marketing_attester_original_receiver_pidfd_required')
                for role, fd in (('framework', sdk_pidfd), ('graph', graph_pidfd)):
                    enrolled = _parse_record(store._read(root, role + '-scope-enrollment-intent.json'))
                    _owned_pidfd(proc, fd, enrolled['pid'], enrolled['start_ticks'], context['operation_nonce'], role, initial_deadline)
                own_cgroup = _read(proc, 'self/cgroup', 4096, initial_deadline).strip()
                actor = '0::/anvil-marketing/' + context['operation_nonce'][:20]
                if not own_cgroup.startswith('0::/') or own_cgroup == actor or own_cgroup.startswith(actor + '/'):
                    raise ValueError('marketing_attester_must_be_outside_actor_scope')
                # The independently checked pre-G inventory permits only the
                # original four passed handles and two private store folders.
                # No /proc directory survives into that checkpoint/key proof.
                os.close(proc)
                proc = None
                _write_at(root, 'attester-key-generation-intent.json', _bounded_canonical({
                    'schema_version': 'anvil.marketing-child-only-key-intent.v1',
                    'request_sha256': claim['request_sha256'], 'operation_nonce': context['operation_nonce'],
                    'peer_binding_id': str(facts.original.peer_binding_id), 'pid': os.getpid(),
                    'original_deadline_monotonic': initial_deadline, 'native_qualified': False,
                    'private_key_persisted': False, 'replay_permitted': False,
                }, 4096))
                key = _EphemeralAttester(facts.original, original_deadline=initial_deadline,
                                         plan_sha256=claim['plan_sha256'],
                                         private_grade_transport_raw=facts.private_grade_transport_raw,
                                         private_actor_transport_raw=facts.private_actor_transport_raw)
                public_ready_raw = key.public_ready_once()
                _write_at(root, 'attester-own-public-ready.json', public_ready_raw, mode=0o400)
                _send(channel, public_ready_raw, deadline=initial_deadline)
                challenge = _parse_record(_packet(channel, receiver_pidfd, deadline=initial_deadline))
                if (set(challenge) != {'schema_version', 'receiver_challenge_hex'}
                        or challenge['schema_version'] != 'anvil.marketing-attester-key-challenge.v1'
                        or type(challenge['receiver_challenge_hex']) is not str
                        or len(challenge['receiver_challenge_hex']) != 64):
                    raise ValueError('marketing_attester_fixed_peer_challenge_required')
                _send(channel, key.prove_original_key_once(bytes.fromhex(challenge['receiver_challenge_hex'])),
                      deadline=initial_deadline)
                # Data comes only from the independently authenticated receiver;
                # it still grants neither COMMIT proof nor graph-run authority.
                registration = _parse_record(_packet(channel, receiver_pidfd, deadline=initial_deadline))
                fields = {'schema_version', 'peer_binding_id', 'request_sha256', 'operation_nonce', 'public_ready',
                          'peer_receipt_sha256', 'os_peer_receipt_sha256', 'enrollment', 'capture_accepted', 'run_authority'}
                if (set(registration) != fields
                        or registration['schema_version'] != 'anvil.marketing-original-enrollment-commits-observed.v1'
                        or registration['peer_binding_id'] != str(facts.original.peer_binding_id)
                        or registration['request_sha256'] != facts.original.request_sha256
                        or registration['operation_nonce'] != facts.original.operation_nonce
                        or registration['capture_accepted'] is not False or registration['run_authority'] != 'not_granted'):
                    raise ValueError('marketing_attester_original_registration_reply_required')
                validate_receipt(registration['enrollment'], facts.original, key._ready)
                if canonical_ready(registration['public_ready']) != canonical_ready(key._ready.model_dump(mode='json')):
                    raise ValueError('marketing_attester_registration_public_key_changed')
                key.retain_registration(registration['enrollment'])
                _send(channel, _bounded_canonical({
                    'schema_version': 'anvil.marketing-attester-registration-retained.v1',
                    'request_sha256': facts.original.request_sha256, 'operation_nonce': facts.original.operation_nonce,
                    'capture_accepted': False, 'run_authority': 'not_granted',
                }, 4096), deadline=initial_deadline)
                command = _parse_record(_packet(channel, receiver_pidfd, deadline=initial_deadline))
                if (set(command) != {'schema_version', 'request_sha256', 'operation_nonce'}
                        or command['schema_version'] != 'anvil.marketing-attester-seal-private-input.v1'
                        or command['request_sha256'] != facts.original.request_sha256
                        or command['operation_nonce'] != facts.original.operation_nonce):
                    raise ValueError('marketing_attester_fixed_private_input_trigger_required')
                # Retained pidfds, not caller booleans or pid lookup: the graph
                # is gone while the same SDK remains alive for verifier startup.
                if not select.select([graph_pidfd], [], [], 0)[0] or select.select([sdk_pidfd], [], [], 0)[0]:
                    raise ValueError('marketing_attester_original_graph_exit_sdk_live_required')
                from anvil.marketing_native_actor_capture import validate_actor_capture_files
                from anvil.marketing_native_private_seal import seal_owned_private_input

                validate_actor_capture_files(store, root, claim, plan)
                entry = _parse_record(store._read(root, 'framework-entry.json'))
                identity = {k: entry[k] for k in ('job_id', 'framework_trial_id', 'operation_nonce',
                                                 'request_sha256', 'plan_sha256')}
                private_deadline = initial_deadline - plan['bounds']['cleanup_seconds'] - 8
                _remaining(private_deadline)
                private = key.read_owned_grade_input(store, root, identity, phase_deadline=private_deadline)
                sealed = seal_owned_private_input(store, root, records, facts, identity, private,
                                                   deadline=private_deadline)
                import hashlib

                _send(channel, _bounded_canonical({
                    'schema_version': 'anvil.marketing-attester-private-input-ready.v1',
                    'request_sha256': facts.original.request_sha256, 'operation_nonce': facts.original.operation_nonce,
                    'seal_receipt_sha256': hashlib.sha256(sealed).hexdigest(),
                    'capture_accepted': False, 'native_qualified': False, 'run_authority': 'not_granted',
                }, 4096), deadline=private_deadline)
                command = _parse_record(_packet(channel, receiver_pidfd, deadline=initial_deadline))
                if (set(command) != {'schema_version', 'request_sha256', 'operation_nonce'}
                        or command['schema_version'] != 'anvil.marketing-attester-observe-final-status.v1'
                        or command['request_sha256'] != facts.original.request_sha256
                        or command['operation_nonce'] != facts.original.operation_nonce):
                    raise ValueError('marketing_attester_fixed_final_trigger_required')
                from anvil.marketing_native_private_finalize import observe_owned_final_stop

                observe_owned_final_stop(store, root, context, plan, sdk_pidfd, graph_pidfd)
                final_deadline = initial_deadline - plan['bounds']['cleanup_seconds']
                key.upload_owned_result(store, root, facts, phase_deadline=final_deadline)
                observation = key.read_owned_final_status(phase_deadline=final_deadline)
                _write_at(root, 'attester-owned-api-status.json', observation.raw_body)
                response = key.upload_owned_capture(store, root, facts, context, plan, observation)
                from anvil.marketing_private_capture_receipt import validate_capture_acceptance

                wire = store._read(root, 'private-final-capture-wire.json')
                validate_capture_acceptance(response, key._enrollment, hashlib.sha256(wire).hexdigest())
                _send(channel, _bounded_canonical({
                    'schema_version': 'anvil.marketing-attester-owned-capture-observation.v1',
                    'request_sha256': facts.original.request_sha256, 'operation_nonce': facts.original.operation_nonce,
                    'capture_response_sha256': hashlib.sha256(response).hexdigest(),
                    'capture_wire_sha256': hashlib.sha256(wire).hexdigest(), 'capture_accepted': True,
                }, 4096), deadline=final_deadline)
            finally:
                os.close(root)
    finally:
        if key is not None:
            key.close()
        if proc is not None:
            os.close(proc)
        channel.close()


def canonical_ready(value):
    from anvil.marketing_attester_enrollment import parse_public_ready
    from anvil.praxis_generic_contract import canonical

    return canonical(parse_public_ready(canonical(value)).model_dump(mode='json'))


def main():
    marketing_native_gate()
    if len(sys.argv) != 6 or sys.platform != 'linux' or sys.version_info[:2] != (3, 12):
        return 42
    try:
        descriptors = tuple(int(value) for value in sys.argv[1:5])
        if any(fd < 3 for fd in descriptors):
            return 42
        _run(*descriptors)
        return 0
    except BaseException:
        return 42  # No private data, key, header or traceback in stdout/logs.


if __name__ == '__main__':
    raise SystemExit(main())
