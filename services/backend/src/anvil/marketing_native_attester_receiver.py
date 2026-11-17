"""Independent two-phase original-operation receiver; SOURCE ONLY, gated.

PRE-G: independently retain SDK/graph kernel handles and verify the separate
exec key worker plus original qualified OS evidence. No database enrollment.
AFTER original child attach: peer COMMIT, disjoint registrar COMMIT, bounded
reply; the child still performs its own separate committed registry read.
No world object/lease/prepared body/DB credential/private key crosses IPC.
"""

import asyncio
import hashlib
import os
import select
import socket
import struct
from dataclasses import dataclass, field
from time import monotonic
from types import SimpleNamespace

from anvil.marketing_native_actor_scope import _pid_identity
from anvil.marketing_native_actor_timing import opening_phases
from anvil.marketing_native_attempt import MarketingAttemptStore, _owned, _write_at
from anvil.marketing_native_attester_evidence import _independent_os_receipt
from anvil.marketing_native_attester_peer import _observe_outside_candidate
from anvil.marketing_native_attester_process import _IndependentAttesterProcess
from anvil.marketing_native_boundary import _bounded_canonical, marketing_native_gate
from anvil.marketing_native_enrollment_client import _receive_packet, _send_packet
from anvil.marketing_native_enrollment_receiver import (
    _commit_peer_then_enrollment,
    _original_receiver_facts,
)
from anvil.marketing_native_kernel_scope import _directory, _fd_mount, _read, _remaining
from anvil.marketing_native_mounts import _opening_context
from anvil.marketing_native_private_records import resolve_private_marketing_records
from anvil.marketing_native_records import _parse_record
from anvil.praxis_generic_contract import canonical


@dataclass(slots=True)
class _ReceiverOperation:
    _store: object = field(repr=False)
    _root: int
    _request: object = field(repr=False)
    _records: object = field(repr=False)
    _claim: dict = field(repr=False)
    _plan: dict = field(repr=False)
    _context: dict = field(repr=False)
    _facts: object = field(repr=False)
    _scope: object = field(repr=False)
    _phase_deadline: float
    _actors: dict = field(default_factory=dict, repr=False)
    _actors_beforeG_raw: bytes | None = field(default=None, repr=False)
    _stage: str = 'prelaunch'


async def _accept(listener, deadline):
    _remaining(deadline)
    async with asyncio.timeout(max(0, deadline - monotonic())):
        channel, _ = await asyncio.get_running_loop().sock_accept(listener)
    channel.setblocking(False)
    return channel


def _original_control_peer(owner, channel, proc):
    intent = _parse_record(owner._store._read(owner._root, 'opening-actor-owner-intent.json'))
    peer = _peer(channel)
    if (intent.get('schema_version') != 'anvil.marketing-opening-actor-owner-intent.v2'
            or peer != (intent.get('control_pid'), 0, 0)
            or _pid_identity(proc, peer[0], owner._context['deadline_monotonic'])[1] != intent.get('control_start_ticks')
            or intent['request_sha256'] != owner._facts.original.request_sha256):
        raise ValueError('marketing_receiver_exact_original_control_peer_required')


def _original_helper_cutoff(owner, operation_id):
    parts = operation_id.split(':') if type(operation_id) is str else []
    if len(parts) == 2 and parts[0] == 'preflight' and parts[1] in {'environment', 'tests'}:
        if owner._stage != 'prelaunch':
            raise ValueError('marketing_receiver_preflight_replay_forbidden')
    elif len(parts) == 3 and parts[0] == 'physical':
        from anvil.marketing_native_physical import OPERATIONS

        if parts[1] not in OPERATIONS or parts[2] not in {'environment', 'tests'}:
            raise ValueError('marketing_receiver_fixed_helper_operation_required')
        if parts[2] == 'tests':
            if owner._stage != 'verifier':
                raise ValueError('marketing_receiver_private_inputs_required_before_verifier_helpers')
            return owner._context['deadline_monotonic'] - owner._plan['bounds']['cleanup_seconds'] - 8
        if owner._stage != 'sdk_starting':
            raise ValueError('marketing_receiver_actor_helper_stage_required')
    else:
        raise ValueError('marketing_receiver_fixed_helper_operation_required')
    return owner._context['deadline_monotonic'] - owner._plan['bounds']['cleanup_seconds'] - owner._plan['bounds']['verifier_seconds']


async def _phase_request(listener, owner, proc, deadline):
    """Serve only fixed original helpers while awaiting the next lifecycle step."""
    from anvil.marketing_native_helper_process import run_original_helper

    for _ in range(17):  # Two preflights + fourteen fixed role operations, then next phase.
        channel = await _accept(listener, deadline)
        try:
            value = _parse_record(await _receive_packet(channel, deadline=deadline))
            if value.get('schema_version') == 'anvil.marketing-original-private-role-request.v1':
                from anvil.marketing_native_enrollment_client import original_private_role_deadline
                from anvil.marketing_native_physical import _event

                _original_control_peer(owner, channel, proc)
                if (set(value) != {'schema_version', 'request', 'operation_nonce', 'event', 'work_deadline_monotonic'}
                        or value['request'].encode('utf-8') != owner._request.canonical_bytes
                        or value['operation_nonce'] != owner._facts.original.operation_nonce or type(value['event']) is not dict):
                    raise ValueError('marketing_receiver_original_private_role_request_required')
                event = value['event']
                role, action = event.get('role'), event.get('event')
                if (role == 'environment' and (action in {'before_start', 'start'} and owner._stage != 'sdk_starting'
                        or action == 'logs' and owner._stage != 'running_graph')
                        or role == 'tests' and owner._stage != 'verifier'
                        or role not in {'environment', 'tests'} or action not in {'before_start', 'start', 'logs', 'collect_private'}
                        or action == 'collect_private' and role != 'tests'):
                    raise ValueError('marketing_receiver_fixed_private_role_stage_required')
                cutoff = original_private_role_deadline(owner._store, owner._root, owner._request, event)
                if value['work_deadline_monotonic'] != cutoff:
                    raise ValueError('marketing_receiver_original_role_partition_changed')
                owner._phase_deadline = cutoff
                if action == 'collect_private':
                    from anvil.marketing_native_private_collect import (
                        collect_original_private_result,
                    )

                    result = await collect_original_private_result(owner, event)
                else:
                    result = await _event(owner._store, owner._request, canonical(event), opening=True,
                                           private=True, helper_owner=owner)
                await _send_packet(channel, _bounded_canonical({
                    'schema_version': 'anvil.marketing-original-private-role-reply.v1',
                    'request_sha256': owner._facts.original.request_sha256, 'operation_nonce': owner._facts.original.operation_nonce,
                    'result': result, 'capture_accepted': False, 'run_authority': 'not_granted',
                }, 16384), deadline=cutoff)
                channel.close()
                if action == 'collect_private':
                    return None, {'schema_version': 'anvil.marketing-receiver-private-collection-complete.v1'}
                continue
            if value.get('schema_version') != 'anvil.marketing-original-helper-request.v1':
                return channel, value
            _original_control_peer(owner, channel, proc)
            if (set(value) != {'schema_version', 'request', 'operation_nonce', 'operation_id', 'work_deadline_monotonic'}
                    or value['request'].encode('utf-8') != owner._request.canonical_bytes
                    or value['operation_nonce'] != owner._facts.original.operation_nonce):
                raise ValueError('marketing_receiver_original_helper_request_required')
            cutoff = _original_helper_cutoff(owner, value['operation_id'])
            if value['work_deadline_monotonic'] != cutoff:
                raise ValueError('marketing_receiver_original_helper_cutoff_changed')
            _remaining(cutoff)
            # Different stages use different PREEXISTING original partitions;
            # this is not a restarted timer or a longer operation deadline.
            owner._phase_deadline = cutoff
            metadata = await run_original_helper(owner, value['operation_id'], absolute_deadline=cutoff)
            await _send_packet(channel, _bounded_canonical({
                'schema_version': 'anvil.marketing-original-helper-reply.v1',
                'request_sha256': owner._facts.original.request_sha256, 'operation_nonce': owner._facts.original.operation_nonce,
                'operation_id': value['operation_id'], 'work_deadline_monotonic': cutoff, 'metadata': metadata,
                'capture_accepted': False, 'run_authority': 'not_granted',
            }, 16384), deadline=cutoff)
        except BaseException:
            channel.close()
            raise
        channel.close()
    raise RuntimeError('marketing_original_helper_operation_population_exhausted')


def _peer(channel):
    return struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))


def _retain_original_actor_handles(owner, control_pid, proc):
    """Actual independent before-G observation, not sender-supplied PID data."""
    deadline = owner._phase_deadline
    raw = owner._store._read(owner._root, 'actor-scope-binding.json')
    binding = _parse_record(raw)
    if (binding['request_sha256'] != owner._facts.original.request_sha256
            or binding['operation_nonce'] != owner._facts.original.operation_nonce
            or binding['boot_id'] != str(owner._facts.original.boot_id)
            or binding['original_deadline_monotonic'] != owner._context['deadline_monotonic']):
        raise ValueError('marketing_receiver_original_kernel_binding_changed')
    from anvil.marketing_native_watchdog_worker import _scope

    spawn = _parse_record(owner._store._read(owner._root, 'graph-process-spawn-intent.json'))
    if (spawn.get('schema_version') != 'anvil.marketing-original-graph-process-intent.v2'
            or spawn.get('parent_pid') != control_pid
            or _pid_identity(proc, control_pid, deadline)[1] != spawn.get('parent_start_ticks')):
        raise ValueError('marketing_receiver_original_control_process_changed')
    original = _scope(binding)  # Actual independent outside/boot/dev/inode/mount check.
    owned = {}
    try:
        original_info = os.fstat(original)
        actor_observations = {}
        children = _parse_record(owner._store._read(owner._root, 'actor-scope-children.json'))
        if (children['schema_version'] != 'anvil.marketing-original-actor-scope-children.v2'
                or set(children['children']) != {'framework', 'graph', 'host_helpers'}
                or children['binding_sha256'] != hashlib.sha256(raw).hexdigest()):
            raise ValueError('marketing_receiver_complete_original_private_scope_required')
        for role in ('framework', 'graph'):
            value = _parse_record(owner._store._read(owner._root, role + '-scope-enrollment-intent.json'))
            if (set(value) != {'schema_version', 'role', 'pid', 'start_ticks', 'original_scope_binding_sha256',
                              'original_deadline_monotonic', 'native_qualified'}
                    or value['schema_version'] != 'anvil.marketing-actor-child-enrollment-intent.v1'
                    or value['role'] != role or value['original_scope_binding_sha256'] != hashlib.sha256(raw).hexdigest()
                    or value['original_deadline_monotonic'] != owner._context['deadline_monotonic']
                    or value['native_qualified'] is not False
                    or type(value['pid']) is not int or type(value['start_ticks']) is not int
                    or _pid_identity(proc, value['pid'], deadline) != (control_pid, value['start_ticks'])
                    or _read(proc, str(value['pid']) + '/cgroup', 4096, deadline).strip()
                    != '0::/anvil-marketing/' + owner._context['operation_nonce'][:20] + '/' + role):
                raise ValueError('marketing_receiver_original_enrolled_actor_changed')
            pidfd = os.pidfd_open(value['pid'], 0)
            owned[role] = {**value, 'pidfd': pidfd}
            if select.select([pidfd], [], [], 0)[0] or _pid_identity(proc, value['pid'], deadline) != (control_pid, value['start_ticks']):
                raise ValueError('marketing_receiver_original_actor_not_live_before_G')
            group = _directory(original, role)
            try:
                info = os.fstat(group)
                mount, _ = _fd_mount(proc, group, deadline)
                expected = children['children'][role]
                if (info.st_dev, info.st_ino, mount) != (expected['device'], expected['inode'], expected['mount_id']):
                    raise ValueError('marketing_receiver_original_actor_group_changed')
                fdinfo = _read(proc, 'self/fdinfo/' + str(pidfd), 1024, deadline)
                pidfd_info = os.fstat(pidfd)
                actor_observations[role] = {
                    'pid': value['pid'], 'start_ticks': value['start_ticks'], 'parent_pid': control_pid,
                    'pidfd_identity': {'device': pidfd_info.st_dev, 'inode': pidfd_info.st_ino},
                    'raw_pidfd_fdinfo': fdinfo,
                    'cgroup_path': _read(proc, str(value['pid']) + '/cgroup', 4096, deadline).strip(),
                    'cgroup_device': info.st_dev, 'cgroup_inode': info.st_ino, 'cgroup_mount_id': mount,
                }
            finally:
                os.close(group)
        if owned['framework']['pid'] == owned['graph']['pid']:
            raise ValueError('marketing_receiver_disjoint_original_actor_processes_required')
        owner._actors_beforeG_raw = _bounded_canonical({
            'schema_version': 'anvil.marketing-original-actors-before-G.v1',
            'request_sha256': owner._facts.original.request_sha256, 'plan_sha256': owner._claim['plan_sha256'],
            'operation_nonce': owner._facts.original.operation_nonce, 'boot_id': str(owner._facts.original.boot_id),
            'original_deadline_monotonic': owner._context['deadline_monotonic'],
            'actor_scope_binding_sha256': hashlib.sha256(raw).hexdigest(),
            'original_actor_scope': {'device': original_info.st_dev, 'inode': original_info.st_ino,
                                     'mount_id': _fd_mount(proc, original, deadline)[0]},
            'children': actor_observations, 'capture_accepted': False, 'run_authority': 'not_granted',
        }, 8192)
        _write_at(owner._root, 'independent-actors-before-G.json', owner._actors_beforeG_raw)
        owner._actors = owned
        return
    except BaseException:
        for value in owned.values():
            os.close(value['pidfd'])
        raise
    finally:
        os.close(original)


def _final_framework_receipt(owner, receipt, proc):
    """SDK UUID exists after SDK G; never invent it in the before-G snapshot."""
    from anvil.marketing_capture_peer import parse_independent_receipt
    from anvil.marketing_native_start import _framework_entry

    deadline = owner._phase_deadline
    sdk = owner._actors['framework']
    if (select.select([sdk['pidfd']], [], [], 0)[0]
            or _pid_identity(proc, sdk['pid'], deadline)[1] != sdk['start_ticks']):
        raise ValueError('marketing_receiver_original_sdk_lost_before_registration')
    _framework_entry(owner._store, owner._root, owner._claim)
    raw = owner._store._read(owner._root, 'framework-entry.json')
    entry = _parse_record(raw)
    if (entry['operation_nonce'] != owner._facts.original.operation_nonce
            or hashlib.sha256(owner._store._read(owner._root, 'lifecycle-plan.json')).hexdigest() != owner._claim['plan_sha256']
            or owner._actors_beforeG_raw is None):
        raise ValueError('marketing_receiver_original_framework_entry_and_plan_required')
    identity = {key: entry[key] for key in ('job_id', 'framework_trial_id', 'operation_nonce', 'request_sha256', 'plan_sha256')}
    final = parse_independent_receipt(canonical({
        **receipt.model_dump(mode='json'), 'framework_identity': identity,
        'framework_identity_provenance': {'stage': 'post_sdk_G_pre_graph_work',
            'framework_entry_sha256': hashlib.sha256(raw).hexdigest(), 'original_plan_sha256': owner._claim['plan_sha256'],
            'sdk_pid': sdk['pid'], 'sdk_start_ticks': sdk['start_ticks'], 'boot_id': str(owner._facts.original.boot_id)},
        'preG_actor_observation': _parse_record(owner._actors_beforeG_raw),
    }))
    _write_at(owner._root, 'independent-peer-os-receipt-final.json', canonical(final.model_dump(mode='json')))
    _remaining(deadline)
    return final


def _validate_child_attach(owner, channel, request, proc):
    peer = _peer(channel)
    graph = owner._actors['graph']
    if (peer[0] != graph['pid'] or _pid_identity(proc, peer[0], owner._phase_deadline)[1] != graph['start_ticks']
            or select.select([graph['pidfd']], [], [], 0)[0]):
        raise ValueError('marketing_receiver_only_original_graph_child_may_register')
    fields = {'schema_version', 'request', 'peer_binding_id', 'operation_nonce', 'original_scope',
              'graph_pid', 'graph_start_ticks', 'phase_deadline_monotonic'}
    if (set(request) != fields or request['schema_version'] != 'anvil.marketing-original-child-enrollment-request.v1'
            or request['request'].encode('utf-8') != owner._request.canonical_bytes
            or request['peer_binding_id'] != str(owner._facts.original.peer_binding_id)
            or request['operation_nonce'] != owner._facts.original.operation_nonce
            or request['graph_pid'] != graph['pid'] or request['graph_start_ticks'] != graph['start_ticks']
            or canonical(request['original_scope']) != canonical(owner._facts.original.scope.model_dump(mode='json'))):
        raise ValueError('marketing_receiver_original_child_world_context_changed')
    actor = _parse_record(owner._store._read(owner._root, 'opening-actor-control-intent.json'))
    original = _parse_record(owner._store._read(owner._root, 'original-world-owner-intent.json'))
    native_request = _parse_record(owner._request.canonical_bytes)
    phases = opening_phases(owner._plan['bounds'], deadline=owner._context['deadline_monotonic'],
                            started=actor['actor_started_monotonic'], now=monotonic(),
                            request_timeout=native_request['request_timeout_seconds'], private=True)
    if (original['phase_bounds'] != phases or request['phase_deadline_monotonic'] != phases['graph_deadline_monotonic']
            or original['independent_stop_scope_sha256'] != hashlib.sha256(canonical(request['original_scope'])).hexdigest()):
        raise ValueError('marketing_receiver_original_world_scope_or_phase_changed')
    owner._phase_deadline = min(owner._phase_deadline, phases['graph_deadline_monotonic'])
    _remaining(owner._phase_deadline)


async def _serve_original(request, *, ready_fd=None):
    from anvil.marketing_native_actor_hardening import protect_independent_receiver

    protect_independent_receiver()
    records = resolve_private_marketing_records(request)
    with MarketingAttemptStore() as store:
        root, claim, plan = _opening_context(store, request)
        proc = base = listener = first = second = third = None
        worker = None
        owner = None
        original_error = None
        try:
            context = _parse_record(store._read(root, 'component-context.json'))
            facts = _original_receiver_facts(request, records, context)
            if (facts.receiver_pid, facts.receiver_uid, facts.receiver_gid) != (os.getpid(), os.geteuid(), os.getegid()):
                raise ValueError('marketing_independent_receiver_original_process_required')
            proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            if _pid_identity(proc, os.getpid(), context['deadline_monotonic'])[1] != facts.receiver_start_ticks:
                raise ValueError('marketing_independent_receiver_original_start_ticks_required')
            deadline = context['deadline_monotonic'] - plan['bounds']['cleanup_seconds'] - plan['bounds']['verifier_seconds']
            _remaining(deadline)
            owner = _ReceiverOperation(store, root, request, records, claim, plan, context, facts,
                                        SimpleNamespace(_binding=None), deadline)
            _write_at(root, 'independent-receiver-listen-intent.json', _bounded_canonical({
                'schema_version': 'anvil.marketing-independent-receiver-listen-intent.v1',
                'request_sha256': facts.original.request_sha256, 'operation_nonce': facts.original.operation_nonce,
                'receiver_pid': os.getpid(), 'receiver_start_ticks': facts.receiver_start_ticks,
                'original_deadline_monotonic': context['deadline_monotonic'], 'replay_permitted': False,
            }, 4096))
            run = os.open('/run', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                _owned(os.fstat(run), 0, directory=True)
                try:
                    os.mkdir('anvil-marketing-attester', 0o700, dir_fd=run)
                except FileExistsError:
                    pass
                base = os.open('anvil-marketing-attester', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=run)
                _owned(os.fstat(base), 0, directory=True, private=True)
            finally:
                os.close(run)
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
            name = facts.original.operation_nonce[:20] + '.sock'
            listener.bind('/run/anvil-marketing-attester/' + name)
            os.chmod(name, 0o600, dir_fd=base, follow_symlinks=False)
            listener.listen(1)
            if ready_fd is not None:
                import stat

                info = os.fstat(ready_fd)
                if ready_fd < 3 or not stat.S_ISFIFO(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
                    raise ValueError('marketing_original_receiver_ready_pipe_required')
                if os.write(ready_fd, b'R') != 1:
                    raise RuntimeError('marketing_original_receiver_listen_ready_unknown')
                os.close(ready_fd)
                ready_fd = None
            first, prelaunch = await _phase_request(listener, owner, proc, deadline)
            if (set(prelaunch) != {'schema_version', 'request', 'peer_binding_id', 'operation_nonce', 'phase_deadline_monotonic'}
                    or prelaunch['schema_version'] != 'anvil.marketing-original-prelaunch-request.v1'
                    or prelaunch['request'].encode('utf-8') != request.canonical_bytes
                    or prelaunch['peer_binding_id'] != str(facts.original.peer_binding_id)
                    or prelaunch['operation_nonce'] != facts.original.operation_nonce
                    or prelaunch['phase_deadline_monotonic'] != deadline):
                raise ValueError('marketing_receiver_original_prelaunch_request_required')
            control = _peer(first)
            if control[0] == os.getpid() or control[1:] != (0, 0):
                raise ValueError('marketing_receiver_separate_original_root_control_required')
            owner._scope._binding = _parse_record(store._read(root, 'actor-scope-binding.json'))
            _retain_original_actor_handles(owner, control[0], proc)
            worker = _IndependentAttesterProcess(owner)
            await worker.start(owner._actors['framework']['pidfd'], owner._actors['graph']['pidfd'])
            await worker.verify_key_possession()
            observation_raw = _observe_outside_candidate(worker)
            receipt = _independent_os_receipt(worker, observation_raw)
            _write_at(root, 'independent-peer-os-receipt.json', canonical(receipt.model_dump(mode='json')))
            ack = _bounded_canonical({
                'schema_version': 'anvil.marketing-attester-prelaunch-observed.v1',
                'request_sha256': facts.original.request_sha256, 'operation_nonce': facts.original.operation_nonce,
                'peer_binding_id': str(facts.original.peer_binding_id),
                'sdk_pid': owner._actors['framework']['pid'], 'sdk_start_ticks': owner._actors['framework']['start_ticks'],
                'graph_pid': owner._actors['graph']['pid'], 'graph_start_ticks': owner._actors['graph']['start_ticks'],
                'os_observation_sha256': hashlib.sha256(observation_raw).hexdigest(),
                'public_ready_sha256': hashlib.sha256(worker._ready_raw).hexdigest(),
                'key_possession_proof_sha256': hashlib.sha256(worker._proof_raw).hexdigest(),
                'enrollment_state': 'not_registered_waiting_original_world', 'capture_accepted': False, 'run_authority': 'not_granted',
            }, 4096)
            _write_at(root, 'independent-preG-observation.json', ack)
            await _send_packet(first, ack, deadline=deadline)
            first.close()
            first = None
            owner._stage = 'sdk_starting'
            # Only now can the trusted launcher send SDK G; the graph's later
            # G creates/retains its one original world before this second phase.
            second, attach = await _phase_request(listener, owner, proc, deadline)
            _validate_child_attach(owner, second, attach, proc)
            owner._stage = 'enrollment'
            worker.require_live()
            receipt = _final_framework_receipt(owner, receipt, proc)
            reply = await _commit_peer_then_enrollment(request, records, facts, receipt,
                                                       absolute_deadline=owner._phase_deadline)
            await worker.retain_registration(reply)
            await _send_packet(second, _bounded_canonical(reply, 32768), deadline=owner._phase_deadline)
            second.close()
            second = None
            owner._stage = 'running_graph'
            # Continue serving environment logs while the original graph exits
            # and control captures its original API-Q/container-stop outputs.
            verifier_deadline = context['deadline_monotonic'] - plan['bounds']['cleanup_seconds'] - 8
            third, grade = await _phase_request(listener, owner, proc, verifier_deadline)
            _original_control_peer(owner, third, proc)
            if (set(grade) != {'schema_version', 'request', 'operation_nonce'}
                    or grade['schema_version'] != 'anvil.marketing-original-private-input-request.v1'
                    or grade['request'].encode('utf-8') != request.canonical_bytes
                    or grade['operation_nonce'] != facts.original.operation_nonce
                    or not select.select([owner._actors['graph']['pidfd']], [], [], 0)[0]
                    or select.select([owner._actors['framework']['pidfd']], [], [], 0)[0]):
                raise ValueError('marketing_receiver_original_graph_exit_private_input_phase_required')
            owner._stage, owner._phase_deadline = 'private_input', verifier_deadline
            sealed = await worker.seal_private_input()
            await _send_packet(third, _bounded_canonical(sealed, 4096), deadline=verifier_deadline)
            third.close()
            third = None
            owner._stage = 'verifier'
            unused, completed = await _phase_request(listener, owner, proc, verifier_deadline)
            if unused is not None:
                unused.close()
                raise ValueError('marketing_receiver_unexpected_verifier_lifecycle_frame')
            if completed != {'schema_version': 'anvil.marketing-receiver-private-collection-complete.v1'}:
                raise ValueError('marketing_receiver_actual_private_collection_required')
            owner._stage = 'waiting_sdk_exit'
            # Control triggers only after retaining SDK exit; own pidfds below
            # remain mandatory. No file polling/adoption or late-write race.
            final_deadline = context['deadline_monotonic'] - plan['bounds']['cleanup_seconds']
            third, finish = await _phase_request(listener, owner, proc, final_deadline)
            _original_control_peer(owner, third, proc)
            if (set(finish) != {'schema_version', 'request', 'operation_nonce'}
                    or finish['schema_version'] != 'anvil.marketing-original-final-capture-request.v1'
                    or finish['request'].encode('utf-8') != request.canonical_bytes
                    or finish['operation_nonce'] != facts.original.operation_nonce):
                raise ValueError('marketing_original_final_capture_trigger_required')
            from anvil.marketing_native_private_finalize import stop_original_operation

            await stop_original_operation(owner)
            status = await worker.finalize_owned_capture()
            await _send_packet(third, _bounded_canonical(status, 4096), deadline=final_deadline)
            third.close()
            third = None
            return {'schema_version': 'anvil.marketing-enrollment-lifecycle-source-result.v1',
                    'request_sha256': facts.original.request_sha256, 'operation_nonce': facts.original.operation_nonce,
                    'original_actor_exits_observed': True, 'owned_status_observation': status,
                    'capture_accepted': False, 'run_authority': 'not_granted'}
        except BaseException as error:
            original_error = error
            raise
        finally:
            cleanup_error = None
            if worker is not None:
                try:
                    await worker.abort()
                except BaseException as cleanup:
                    cleanup_error = cleanup
                finally:
                    worker.close()
            if owner is not None:
                for value in owner._actors.values():
                    os.close(value['pidfd'])
            for channel in (first, second, third, listener):
                if channel is not None:
                    channel.close()
            for descriptor in (base, proc, root):
                if descriptor is not None:
                    os.close(descriptor)
            if ready_fd is not None:
                os.close(ready_fd)
            if cleanup_error is not None:
                if original_error is not None:
                    raise original_error from cleanup_error
                raise cleanup_error


async def serve_original_receiver(request):
    marketing_native_gate()
    return await _serve_original(request)
