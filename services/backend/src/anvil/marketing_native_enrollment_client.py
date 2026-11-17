"""Original graph-child exchange and separate committed registry observation.

Fixed private AF_UNIX endpoint, original qualified receiver process identity and
one bounded request/reply. No callback, public flag, file success marker, world
reattach, registration retry or lookup-based ambiguous-write recovery.
Public/native activation remains gated independently.
"""

import array
import asyncio
import hashlib
import os
import re
import socket
import struct
from time import monotonic

from anvil.marketing_attester_enrollment import (
    check_original,
    observe_committed,
    parse_public_ready,
    validate_receipt,
)
from anvil.marketing_native_actor_scope import _pid_identity
from anvil.marketing_native_attempt import _write_at
from anvil.marketing_native_boundary import _bounded_canonical
from anvil.marketing_native_enrollment_receiver import _original_receiver_facts
from anvil.marketing_native_kernel_scope import _read, _remaining
from anvil.marketing_native_records import _parse_record
from anvil.praxis_generic_contract import canonical


async def _ready(fd, *, writing, deadline):
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def ready():
        if not future.done():
            future.set_result(None)

    (loop.add_writer if writing else loop.add_reader)(fd, ready)
    try:
        async with asyncio.timeout(max(0, deadline - monotonic())):
            await future
    finally:
        (loop.remove_writer if writing else loop.remove_reader)(fd)


async def _send_packet(channel, raw, *, deadline):
    if type(raw) is not bytes or not 0 < len(raw) <= 32768:
        raise ValueError('marketing_fixed_enrollment_packet_bound')
    while True:
        _remaining(deadline)
        try:
            count = channel.send(raw, socket.MSG_NOSIGNAL)
        except BlockingIOError:
            await _ready(channel.fileno(), writing=True, deadline=deadline)
            continue  # EAGAIN means no seqpacket was sent, not a new operation.
        if count != len(raw):
            raise RuntimeError('marketing_enrollment_packet_send_unknown_no_retry')
        return


async def _receive_packet(channel, *, deadline):
    while True:
        _remaining(deadline)
        try:
            raw, ancillary, flags, _ = channel.recvmsg(32769, socket.CMSG_SPACE(64), socket.MSG_CMSG_CLOEXEC)
        except BlockingIOError:
            await _ready(channel.fileno(), writing=False, deadline=deadline)
            continue
        for level, kind, data in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                received = array.array('i')
                received.frombytes(data[:len(data) - len(data) % received.itemsize])
                for fd in received:
                    os.close(fd)
        if not raw or len(raw) > 32768 or ancillary or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
            raise RuntimeError('marketing_enrollment_reply_unknown_no_retry')
        _remaining(deadline)
        return raw


async def _observe_original_enrollment(owner):
    """Same original world stays attached in this child across every await."""
    world = owner.original_for_cleanup()
    scope = owner.stop_scope()
    phases = owner.phase_bounds()
    deadline = phases['graph_deadline_monotonic']
    _remaining(deadline)
    context = _parse_record(owner._store._read(owner._root, 'component-context.json'))
    # The private original records, not a lookup/reply, supply the expectations.
    # Owner already retains its immutable record set's world binding; resolve
    # the full original root again only for readonly byte custody, never attach.
    from anvil.marketing_native_private_records import resolve_private_marketing_records

    records = resolve_private_marketing_records(owner._request)
    facts = _original_receiver_facts(owner._request, records, context)
    if canonical(scope) != canonical(facts.original.scope.model_dump(mode='json')):
        raise ValueError('marketing_original_child_enrollment_scope_changed')
    nonce = context['operation_nonce']
    if type(nonce) is not str or not re.fullmatch(r'[a-f0-9]{64}', nonce):
        raise ValueError('marketing_original_enrollment_nonce_required')
    # Consume the one exchange BEFORE socket/connection/DB effects.
    _write_at(owner._root, 'original-enrollment-exchange-intent.json', _bounded_canonical({
        'schema_version': 'anvil.marketing-original-enrollment-exchange-intent.v1',
        'request_sha256': facts.original.request_sha256, 'operation_nonce': nonce,
        'peer_binding_id': str(facts.original.peer_binding_id),
        'phase_deadline_monotonic': deadline, 'original_deadline_monotonic': context['deadline_monotonic'],
        'native_qualified': False, 'replay_permitted': False,
    }, 4096))
    channel = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
    proc = None
    try:
        loop = asyncio.get_running_loop()
        async with asyncio.timeout(max(0, deadline - monotonic())):
            await loop.sock_connect(channel, '/run/anvil-marketing-attester/' + nonce[:20] + '.sock')
        peer = struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
        if peer != (facts.receiver_pid, facts.receiver_uid, facts.receiver_gid):
            raise ValueError('marketing_original_independent_receiver_peer_changed')
        proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        _, receiver_ticks = _pid_identity(proc, peer[0], deadline)
        _, own_ticks = _pid_identity(proc, os.getpid(), deadline)
        if (receiver_ticks != facts.receiver_start_ticks or peer[0] in (os.getpid(), os.getppid())
                or _read(proc, 'sys/kernel/random/boot_id', 64, deadline).strip() != str(facts.original.boot_id)):
            raise ValueError('marketing_original_independent_receiver_process_required')
        outgoing = _bounded_canonical({
            'schema_version': 'anvil.marketing-original-child-enrollment-request.v1',
            'request': owner._request.canonical_bytes.decode('utf-8'),
            'peer_binding_id': str(facts.original.peer_binding_id), 'operation_nonce': nonce,
            'original_scope': scope, 'graph_pid': os.getpid(), 'graph_start_ticks': own_ticks,
            'phase_deadline_monotonic': deadline,
        }, 16384)
        await _send_packet(channel, outgoing, deadline=deadline)
        raw = await _receive_packet(channel, deadline=deadline)
        reply = _parse_record(raw)
        fields = {'schema_version', 'peer_binding_id', 'request_sha256', 'operation_nonce', 'public_ready',
                  'peer_receipt_sha256', 'os_peer_receipt_sha256', 'enrollment', 'capture_accepted', 'run_authority'}
        if (set(reply) != fields or reply['schema_version'] != 'anvil.marketing-original-enrollment-commits-observed.v1'
                or reply['peer_binding_id'] != str(facts.original.peer_binding_id)
                or reply['request_sha256'] != facts.original.request_sha256 or reply['operation_nonce'] != nonce
                or reply['capture_accepted'] is not False or reply['run_authority'] != 'not_granted'
                or any(type(reply[k]) is not str or not re.fullmatch(r'[a-f0-9]{64}', reply[k])
                       for k in ('peer_receipt_sha256', 'os_peer_receipt_sha256'))):
            raise RuntimeError('marketing_original_receiver_commit_reply_rejected_no_retry')
        ready = parse_public_ready(canonical(reply['public_ready']))
        check_original(ready, facts.original)
        validate_receipt(reply['enrollment'], facts.original, ready)
        # Receipt/peer words alone never release graph. This one separate DB
        # read is reached ONLY after the authenticated receiver's complete reply.
        observed = await observe_committed(facts.original, ready, reply['peer_receipt_sha256'], world._job,
                                           absolute_deadline=deadline,
                                           private_actor_maximum_bytes=_parse_record(facts.private_actor_transport_raw)['wire_limit'])
        if owner.original_for_cleanup() is not world or canonical(owner.stop_scope()) != canonical(scope):
            raise ValueError('marketing_original_world_changed_during_enrollment')
        _remaining(deadline)
        _write_at(owner._root, 'original-enrollment-committed-observation.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-original-child-enrollment-observation.v1',
            'request_sha256': facts.original.request_sha256, 'operation_nonce': nonce,
            'peer_binding_id': str(facts.original.peer_binding_id),
            'peer_receipt_sha256': observed.peer_receipt_sha256,
            'committed_observation_sha256': hashlib.sha256(canonical(observed.model_dump(mode='json'))).hexdigest(),
            'receiver_reply_sha256': hashlib.sha256(raw).hexdigest(),
            'phase_deadline_monotonic': deadline, 'capture_accepted': False, 'run_authority': 'not_granted',
        }, 4096))
        return observed
    finally:
        channel.close()
        if proc is not None:
            os.close(proc)


async def _prepare_original_attester(owner):
    """Independent receiver observes BOTH original children BEFORE either G.

    This authorizes no enrollment, model run or capture. The SDK G release stays
    with the trusted original launcher after this private prelaunch exchange.
    """
    owner._scope.require_pair()
    context = owner._context
    deadline = context['deadline_monotonic'] - owner._plan['bounds']['cleanup_seconds'] - owner._plan['bounds']['verifier_seconds']
    _remaining(deadline)
    facts = _original_receiver_facts(owner._request, owner._records, context)
    graph = owner._scope._members['graph']
    sdk = owner._scope._members['framework']
    _write_at(owner._root, 'attester-prelaunch-exchange-intent.json', _bounded_canonical({
        'schema_version': 'anvil.marketing-attester-prelaunch-exchange-intent.v1',
        'request_sha256': facts.original.request_sha256, 'operation_nonce': facts.original.operation_nonce,
        'original_deadline_monotonic': context['deadline_monotonic'], 'phase_deadline_monotonic': deadline,
        'sdk_pid': sdk['pid'], 'sdk_start_ticks': sdk['start_ticks'],
        'graph_pid': graph['pid'], 'graph_start_ticks': graph['start_ticks'],
        'native_qualified': False, 'replay_permitted': False,
    }, 4096))
    channel = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
    proc = None
    try:
        loop = asyncio.get_running_loop()
        async with asyncio.timeout(max(0, deadline - monotonic())):
            await loop.sock_connect(channel, '/run/anvil-marketing-attester/' + facts.original.operation_nonce[:20] + '.sock')
        peer = struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
        proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        if (peer != (facts.receiver_pid, facts.receiver_uid, facts.receiver_gid)
                or peer[0] == os.getpid() or _pid_identity(proc, peer[0], deadline)[1] != facts.receiver_start_ticks
                or _read(proc, 'sys/kernel/random/boot_id', 64, deadline).strip() != str(facts.original.boot_id)):
            raise ValueError('marketing_original_prelaunch_independent_receiver_required')
        outgoing = _bounded_canonical({
            'schema_version': 'anvil.marketing-original-prelaunch-request.v1',
            'request': owner._request.canonical_bytes.decode('utf-8'),
            'peer_binding_id': str(facts.original.peer_binding_id), 'operation_nonce': facts.original.operation_nonce,
            'phase_deadline_monotonic': deadline,
        }, 16384)
        await _send_packet(channel, outgoing, deadline=deadline)
        raw = await _receive_packet(channel, deadline=deadline)
        reply = _parse_record(raw)
        fields = {'schema_version', 'request_sha256', 'operation_nonce', 'peer_binding_id', 'sdk_pid', 'sdk_start_ticks',
                  'graph_pid', 'graph_start_ticks', 'os_observation_sha256', 'public_ready_sha256',
                  'key_possession_proof_sha256', 'enrollment_state', 'capture_accepted', 'run_authority'}
        if (set(reply) != fields or reply['schema_version'] != 'anvil.marketing-attester-prelaunch-observed.v1'
                or reply['request_sha256'] != facts.original.request_sha256
                or reply['operation_nonce'] != facts.original.operation_nonce
                or reply['peer_binding_id'] != str(facts.original.peer_binding_id)
                or any(type(reply[key]) is not int or reply[key] != value for key, value in (
                    ('sdk_pid', sdk['pid']), ('sdk_start_ticks', sdk['start_ticks']),
                    ('graph_pid', graph['pid']), ('graph_start_ticks', graph['start_ticks'])))
                or any(type(reply[key]) is not str or not re.fullmatch(r'[a-f0-9]{64}', reply[key]) for key in
                       ('os_observation_sha256', 'public_ready_sha256', 'key_possession_proof_sha256'))
                or reply['enrollment_state'] != 'not_registered_waiting_original_world'
                or reply['capture_accepted'] is not False or reply['run_authority'] != 'not_granted'):
            raise RuntimeError('marketing_original_prelaunch_observation_unknown_no_retry')
        owner._scope.require_pair()
        _remaining(deadline)
        _write_at(owner._root, 'attester-prelaunch-observed.json', raw)
        return reply
    finally:
        channel.close()
        if proc is not None:
            os.close(proc)


async def request_original_helper(store, root, request, records, operation_id, *, work_deadline):
    """Fixed command name only; receiver reconstructs executable/argv/env."""
    context = _parse_record(store._read(root, 'component-context.json'))
    facts = _original_receiver_facts(request, records, context)
    if not 0 < work_deadline <= context['deadline_monotonic']:
        raise ValueError('marketing_original_helper_phase_cutoff_required')
    _remaining(work_deadline)
    channel = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
    proc = None
    try:
        loop = asyncio.get_running_loop()
        async with asyncio.timeout(max(0, work_deadline - monotonic())):
            await loop.sock_connect(channel, '/run/anvil-marketing-attester/' + facts.original.operation_nonce[:20] + '.sock')
        peer = struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
        proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        if (peer != (facts.receiver_pid, facts.receiver_uid, facts.receiver_gid)
                or _pid_identity(proc, peer[0], work_deadline)[1] != facts.receiver_start_ticks
                or _read(proc, 'sys/kernel/random/boot_id', 64, work_deadline).strip() != str(facts.original.boot_id)):
            raise ValueError('marketing_original_helper_independent_receiver_required')
        await _send_packet(channel, _bounded_canonical({
            'schema_version': 'anvil.marketing-original-helper-request.v1',
            'request': request.canonical_bytes.decode('utf-8'), 'operation_nonce': facts.original.operation_nonce,
            'operation_id': operation_id, 'work_deadline_monotonic': work_deadline,
        }, 16384), deadline=work_deadline)
        reply = _parse_record(await _receive_packet(channel, deadline=work_deadline))
        if (set(reply) != {'schema_version', 'request_sha256', 'operation_nonce', 'operation_id',
                          'work_deadline_monotonic', 'metadata', 'capture_accepted', 'run_authority'}
                or reply['schema_version'] != 'anvil.marketing-original-helper-reply.v1'
                or reply['request_sha256'] != facts.original.request_sha256
                or reply['operation_nonce'] != facts.original.operation_nonce or reply['operation_id'] != operation_id
                or reply['work_deadline_monotonic'] != work_deadline or type(reply['metadata']) is not dict
                or reply['capture_accepted'] is not False or reply['run_authority'] != 'not_granted'):
            raise RuntimeError('marketing_original_helper_reply_unknown_no_retry')
        return reply['metadata']
    finally:
        channel.close()
        if proc is not None:
            os.close(proc)


async def request_original_private_input(owner):
    """Fixed phase transition only; no protected files or signing input in IPC."""
    return await _request_original_fixed_phase(owner, final=False)


async def request_original_final_capture(owner):
    """Only after the actual original SDK exit record has been retained."""
    return await _request_original_fixed_phase(owner, final=True)


async def _request_original_fixed_phase(owner, *, final):
    facts = _original_receiver_facts(owner._request, owner._records, owner._context)
    deadline = owner._context['deadline_monotonic'] - owner._plan['bounds']['cleanup_seconds'] - (0 if final else 8)
    channel = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
    proc = None
    try:
        async with asyncio.timeout(max(0, deadline - monotonic())):
            await asyncio.get_running_loop().sock_connect(channel,
                '/run/anvil-marketing-attester/' + facts.original.operation_nonce[:20] + '.sock')
        peer = struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
        proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        if (peer != (facts.receiver_pid, facts.receiver_uid, facts.receiver_gid)
                or _pid_identity(proc, peer[0], deadline)[1] != facts.receiver_start_ticks
                or _read(proc, 'sys/kernel/random/boot_id', 64, deadline).strip() != str(facts.original.boot_id)):
            raise ValueError('marketing_original_private_input_receiver_required')
        await _send_packet(channel, _bounded_canonical({
            'schema_version': ('anvil.marketing-original-final-capture-request.v1' if final else
                               'anvil.marketing-original-private-input-request.v1'),
            'request': owner._request.canonical_bytes.decode('utf-8'),
            'operation_nonce': facts.original.operation_nonce,
        }, 16384), deadline=deadline)
        value = _parse_record(await _receive_packet(channel, deadline=deadline))
        if final:
            if (set(value) != {'schema_version', 'request_sha256', 'operation_nonce', 'capture_response_sha256',
                              'capture_wire_sha256', 'capture_accepted'}
                    or value['schema_version'] != 'anvil.marketing-attester-owned-capture-observation.v1'
                    or value['request_sha256'] != facts.original.request_sha256
                    or value['operation_nonce'] != facts.original.operation_nonce
                    or value['capture_accepted'] is not True
                    or value['capture_response_sha256'] != hashlib.sha256(owner._store._read(
                        owner._root, 'attester-owned-final-capture-response.json')).hexdigest()
                    or value['capture_wire_sha256'] != hashlib.sha256(owner._store._read(
                        owner._root, 'private-final-capture-wire.json')).hexdigest()):
                raise RuntimeError('marketing_original_final_capture_reply_unknown_no_retry')
            return value
        if (set(value) != {'schema_version', 'request_sha256', 'operation_nonce', 'seal_receipt_sha256',
                          'capture_accepted', 'native_qualified', 'run_authority'}
                or value['schema_version'] != 'anvil.marketing-attester-private-input-ready.v1'
                or value['request_sha256'] != facts.original.request_sha256
                or value['operation_nonce'] != facts.original.operation_nonce
                or value['seal_receipt_sha256'] != hashlib.sha256(
                    owner._store._read(owner._root, 'private-verifier-seal-receipt.json')).hexdigest()
                or value['capture_accepted'] is not False or value['native_qualified'] is not False
                or value['run_authority'] != 'not_granted'):
            raise RuntimeError('marketing_original_private_input_reply_unknown_no_retry')
        return value
    finally:
        channel.close()
        if proc is not None:
            os.close(proc)


def original_private_role_deadline(store, root, request, event):
    context = _parse_record(store._read(root, 'component-context.json'))
    plan = _parse_record(store._read(root, 'lifecycle-plan.json'))
    if event['role'] == 'tests':
        return context['deadline_monotonic'] - plan['bounds']['cleanup_seconds'] - 8
    if event['event'] == 'logs':
        from anvil.marketing_native_actor_timing import opening_phases

        actor = _parse_record(store._read(root, 'opening-actor-control-intent.json'))
        value = _parse_record(request.canonical_bytes)
        phases = opening_phases(plan['bounds'], deadline=context['deadline_monotonic'],
                                started=actor['actor_started_monotonic'], now=actor['actor_started_monotonic'],
                                request_timeout=value['request_timeout_seconds'], private=True)
        return phases['actor_join_deadline_monotonic']
    return context['deadline_monotonic'] - plan['bounds']['cleanup_seconds'] - plan['bounds']['verifier_seconds']


async def request_original_physical_event(store, root, request, records, raw_event):
    """Root control delegates privileged fixed role operations, not arbitrary exec."""
    context = _parse_record(store._read(root, 'component-context.json'))
    facts = _original_receiver_facts(request, records, context)
    event = _parse_record(raw_event)
    role = event.get('role')
    if (role not in {'environment', 'tests'} or event.get('event') not in {'before_start', 'start', 'logs', 'collect_private'}
            or event.get('event') == 'collect_private' and role != 'tests'):
        raise ValueError('marketing_fixed_original_private_role_event_required')
    deadline = original_private_role_deadline(store, root, request, event)
    _remaining(deadline)
    channel = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
    proc = None
    try:
        loop = asyncio.get_running_loop()
        async with asyncio.timeout(max(0, deadline - monotonic())):
            await loop.sock_connect(channel, '/run/anvil-marketing-attester/' + facts.original.operation_nonce[:20] + '.sock')
        peer = struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
        proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        if (peer != (facts.receiver_pid, facts.receiver_uid, facts.receiver_gid)
                or _pid_identity(proc, peer[0], deadline)[1] != facts.receiver_start_ticks):
            raise ValueError('marketing_original_physical_independent_receiver_required')
        await _send_packet(channel, _bounded_canonical({
            'schema_version': 'anvil.marketing-original-private-role-request.v1',
            'request': request.canonical_bytes.decode('utf-8'), 'operation_nonce': facts.original.operation_nonce,
            'event': event, 'work_deadline_monotonic': deadline,
        }, 16384), deadline=deadline)
        value = _parse_record(await _receive_packet(channel, deadline=deadline))
        if (set(value) != {'schema_version', 'request_sha256', 'operation_nonce', 'result', 'capture_accepted', 'run_authority'}
                or value['schema_version'] != 'anvil.marketing-original-private-role-reply.v1'
                or value['request_sha256'] != facts.original.request_sha256
                or value['operation_nonce'] != facts.original.operation_nonce or type(value['result']) is not dict
                or value['capture_accepted'] is not False or value['run_authority'] != 'not_granted'):
            raise RuntimeError('marketing_original_private_role_reply_unknown_no_retry')
        return value['result']
    finally:
        channel.close()
        if proc is not None:
            os.close(proc)
