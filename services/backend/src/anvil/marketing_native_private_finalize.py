"""Original receiver whole-root stop and attester six-document producer.

These documents contain actual observations; admission additionally requires
independent OS/transport qualification and API physical validation. No accepted
reference is manufactured locally. The final capture never hashes itself.
"""

import asyncio
import hashlib
import os
import select
from time import monotonic

from anvil.marketing_native_attempt import _write_at
from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical
from anvil.marketing_native_kernel_scope import _fd_mount, _observe, _open_scope, _read, _remaining
from anvil.marketing_native_records import _parse_record
from anvil.praxis_generic_contract import canonical, digest


async def stop_original_operation(owner):
    from anvil.marketing_native_actor_scope import _write_control
    from anvil.marketing_native_attester_receiver import _ReceiverOperation
    from anvil.marketing_native_engine import _request
    from anvil.marketing_native_stop import _container_binding, _inspect

    if type(owner) is not _ReceiverOperation or owner._stage != 'waiting_sdk_exit':
        raise ValueError('marketing_original_receiver_final_stop_stage_required')
    store, root, context, plan = owner._store, owner._root, owner._context, owner._plan
    deadline = context['deadline_monotonic'] - plan['bounds']['cleanup_seconds']
    _remaining(deadline)
    if not all(select.select([v['pidfd']], [], [], 0)[0] for v in owner._actors.values()):
        raise ValueError('marketing_original_actor_pidfd_exits_required_before_final_root_stop')
    binding_raw = store._read(root, 'actor-scope-binding.json')
    binding = _parse_record(binding_raw)
    proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    group = None
    try:
        group = _open_scope(binding['operation_nonce'])
        info = os.fstat(group)
        if (binding['operation_nonce'] != context['operation_nonce']
                or binding['request_sha256'] != owner._facts.original.request_sha256
                or binding['original_deadline_monotonic'] != context['deadline_monotonic']
                or (info.st_dev, info.st_ino) != (binding['cgroup_device'], binding['cgroup_inode'])
                or _fd_mount(proc, group, deadline)[0] != binding['cgroup_mount_id']
                or _read(proc, 'sys/kernel/random/boot_id', 64, deadline).strip() != context['boot_id']):
            raise ValueError('marketing_original_root_identity_required_before_final_stop')
        _write_at(root, 'private-whole-root-stop-intent.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-private-whole-root-stop-intent.v1',
            'binding_sha256': hashlib.sha256(binding_raw).hexdigest(),
            'original_deadline_monotonic': context['deadline_monotonic'], 'work_deadline_monotonic': deadline,
            'controls': ['cgroup.freeze=1', 'cgroup.kill=1'], 'replay_permitted': False,
        }, 4096), mode=0o400)
        _write_control(group, 'cgroup.freeze', b'1', deadline)
        _write_control(group, 'cgroup.kill', b'1', deadline)
        while True:
            events = dict(line.split() for line in _read(group, 'cgroup.events', 512, deadline).splitlines())
            if events.get('frozen') == '1' and events.get('populated') == '0':
                break
            _remaining(deadline)
            await asyncio.sleep(min(.01, max(0, deadline - monotonic())))
        kernel = _observe(binding_raw, deadline=context['deadline_monotonic'], byte_limit=16384, phase_deadline=deadline)
        observed = _parse_record(kernel)
        children = _parse_record(store._read(root, 'actor-scope-children.json'))
        expected_names = {'framework', 'graph', 'host_helpers'}
        if set(children.get('children', {})) != expected_names:
            raise ValueError('marketing_original_three_child_root_required')
        for snapshot in ('snapshot_first', 'snapshot_second'):
            nodes = observed[snapshot]
            if {v['relative'] for v in nodes} != {'.', './framework', './graph', './host_helpers'}:
                raise ValueError('marketing_original_complete_helper_sdk_graph_root_required')
            for node in nodes:
                if node['relative'] != '.':
                    enrolled = children['children'][node['relative'][2:]]
                    if any(node[k] != enrolled[k] for k in ('device', 'inode', 'mount_id')):
                        raise ValueError('marketing_original_final_child_scope_changed')
                state = dict(line.split() for line in node['raw_kernel_files']['cgroup.events'].splitlines())
                if state.get('frozen') != '1' or state.get('populated') != '0':
                    raise ValueError('marketing_final_root_subtree_not_frozen_empty')
        _write_at(root, 'private-final-kernel-scope.json', kernel, mode=0o400)
        joined = {'schema_version': 'anvil.marketing-private-original-process-exits.v1',
            'request_sha256': owner._facts.original.request_sha256, 'operation_nonce': context['operation_nonce'],
            'boot_id': context['boot_id'], 'original_deadline_monotonic': context['deadline_monotonic'],
            'actors': {role: {'pid': value['pid'], 'start_ticks': value['start_ticks'], 'pidfd_exit_observed': True}
                       for role, value in owner._actors.items()},
            'before_G_sha256': hashlib.sha256(owner._actors_beforeG_raw).hexdigest(),
            'framework_exit': _parse_record(store._read(root, 'framework-exit-observed.json')),
            'graph_join': _parse_record(store._read(root, 'graph-process-join.json')),
            'kernel_scope_sha256': hashlib.sha256(kernel).hexdigest(),
            'capture_accepted': False, 'native_qualified': False}
        if (type(joined['framework_exit'].get('returncode')) is not int or joined['framework_exit']['returncode'] != 0
                or joined['framework_exit'].get('pid') != owner._actors['framework']['pid']
                or joined['framework_exit'].get('start_ticks') != owner._actors['framework']['start_ticks']):
            raise ValueError('marketing_original_sdk_successful_exit_required')
        _write_at(root, 'private-final-process-join.json', _bounded_canonical(joined, 8192), mode=0o400)
        containers = {}
        for role in ('environment', 'tests'):
            original = _container_binding(store, root, owner._claim, plan, role)
            current = await _request('inspect', original['container_id'], deadline=deadline, private=True)
            _inspect(current, original, stopped=True)
            if role == 'tests' and (type(current['State'].get('ExitCode')) is not int or current['State']['ExitCode'] != 0):
                raise ValueError('marketing_original_final_private_verifier_exit_required')
            current_raw = _bounded_canonical(current, DOCUMENT_CAP)
            _write_at(root, 'private-final-' + role + '-inspect.json', current_raw, mode=0o400)
            containers[role] = {'binding': original,
                'current_state': current['State'], 'restart_count': current['RestartCount'],
                'identity_fields_sha256': digest({k: current[k] for k in ('Id', 'Image', 'Name', 'Config', 'HostConfig', 'Mounts')}),
                'current_inspect_sha256': hashlib.sha256(current_raw).hexdigest(),
                'stop_observation': _parse_record(store._read(root, role + '-container-stop-observed.json'))}
        _write_at(root, 'private-final-containers.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-private-owned-containers-stopped.v1',
            'request_sha256': owner._facts.original.request_sha256, 'operation_nonce': context['operation_nonce'],
            'roles': containers, 'capture_accepted': False, 'native_qualified': False,
        }, 12288), mode=0o400)
        owner._stage = 'whole_root_stopped'
    finally:
        if group is not None:
            os.close(group)
        os.close(proc)


def produce_six_documents(store, root, facts, context, plan, final_status, result_custody):
    """Called inside the key worker after its OWN final status and result POST."""
    from anvil.marketing_capture_status import validate_response
    from anvil.marketing_native_capture_budget import (
        KIND_LIMITS,
        encode_v2_metadata,
        prepare_v2_metadata_budget,
    )

    _remaining(context['deadline_monotonic'] - plan['bounds']['cleanup_seconds'])
    enrollment = _parse_record(store._read(root, 'attester-grade-enrollment.json'))
    status = validate_response(final_status.raw_body, enrollment)
    grade_status = validate_response(store._read(root, 'attester-owned-grade-ready-status.json'), enrollment)
    if status.state != 'ready' or canonical(status.descriptor) != canonical(grade_status.descriptor):
        raise ValueError('marketing_final_own_original_ready_content_changed')
    sdk = _parse_record(store._read(root, 'private-verifier-binding.json'))
    binding_raw = store._read(root, 'actor-scope-binding.json')
    operation = _bounded_canonical({
        'schema_version': 'anvil.marketing-private-operation-binding.v1', 'identity': sdk['identity'], 'scope': sdk['scope'],
        'enrollment_id': enrollment['enrollment_id'], 'manifest_id': str(status.manifest_id),
        'boot_id': context['boot_id'], 'original_deadline_monotonic': context['deadline_monotonic'],
        'actor_scope_binding': _parse_record(binding_raw),
        'child_binding': _parse_record(store._read(root, 'actor-scope-children.json')),
        'original_peer_receipt_sha256': hashlib.sha256(store._read(root, 'independent-peer-os-receipt-final.json')).hexdigest(),
        'public_ready_sha256': hashlib.sha256(store._read(root, 'attester-own-public-ready.json')).hexdigest(),
        'api_descriptor_sha256': digest(status.descriptor),
        'capture_accepted': False, 'native_qualified': False, 'run_authority': 'not_granted',
    }, 4096)
    verifier = _bounded_canonical({
        'schema_version': 'anvil.marketing-private-verifier-custody-reference.v1',
        'identity': sdk['identity'], 'scope': sdk['scope'], 'custody': result_custody,
        'input_seal_receipt_sha256': hashlib.sha256(store._read(root, 'private-verifier-seal-receipt.json')).hexdigest(),
        'private_program_sha256': hashlib.sha256(store._read(root, 'private-verifier-program.json')).hexdigest(),
        'sdk_binding_sha256': hashlib.sha256(store._read(root, 'private-verifier-binding.json')).hexdigest(),
        'capture_accepted': False, 'native_qualified': False, 'run_authority': 'not_granted',
    }, 4096)
    owned_kernel = store._read(root, 'attester-own-final-kernel-scope.json')
    receiver_join = _parse_record(store._read(root, 'private-final-process-join.json'))
    own_join = {**receiver_join, 'receiver_kernel_scope_sha256': receiver_join['kernel_scope_sha256'],
                'kernel_scope_sha256': hashlib.sha256(owned_kernel).hexdigest()}
    docs = {'operation_binding': operation, 'kernel_scope': owned_kernel,
        'process_join': _bounded_canonical(own_join, 8192),
        'container_shutdown': store._read(root, 'private-final-containers.json'), 'verifier_result': verifier}
    seal = _bounded_canonical({
        'schema_version': 'anvil.marketing-private-whole-capture-seal.v1', 'identity': sdk['identity'], 'scope': sdk['scope'],
        'enrollment_id': enrollment['enrollment_id'], 'manifest_id': str(status.manifest_id),
        # Only the preceding FIVE documents; neither this seal nor outer wire
        # attempts to include its own digest.
        'documents_sha256': {k: hashlib.sha256(v).hexdigest() for k, v in docs.items()},
        'own_api_status_sha256': final_status.body_sha256, 'own_api_tls_certificate_sha256': final_status.tls_certificate_sha256,
        'api_descriptor_sha256': digest(status.descriptor),
        'actor_output_sha256': hashlib.sha256(store._read(root, 'captured-actor-output.json')).hexdigest(),
        'collection_receipt_sha256': hashlib.sha256(store._read(root, 'captured-collection-receipt.json')).hexdigest(),
        'actor_stop_sha256': hashlib.sha256(store._read(root, 'actor-stop.json')).hexdigest(),
        'input_seal': _parse_record(store._read(root, 'private-verifier-seal-receipt.json')),
        'capture_accepted': False, 'native_qualified': False, 'run_authority': 'not_granted',
    }, 8192)
    docs['capture_seal'] = seal
    budget = prepare_v2_metadata_budget(enrollment['enrollment_id'], facts.original.request_sha256,
        facts.original.operation_nonce, plan_receipt_bytes=enrollment['wire_limit'])
    for kind, limit in KIND_LIMITS:
        _bounded_canonical(_parse_record(docs[kind]), limit)
        _write_at(root, 'private-final-' + kind + '.json', docs[kind], mode=0o400)
    wire = encode_v2_metadata(budget, docs)
    _write_at(root, 'private-final-capture-wire.json', wire, mode=0o400)
    return wire


def observe_owned_final_stop(store, root, context, plan, sdk_pidfd, graph_pidfd):
    """Key worker independently re-reads kernel/Engine after receiver freeze."""
    from anvil.marketing_native_engine import _request
    from anvil.marketing_native_stop import _inspect

    deadline = context['deadline_monotonic'] - plan['bounds']['cleanup_seconds']
    _remaining(deadline)
    if not all(select.select([fd], [], [], 0)[0] for fd in (sdk_pidfd, graph_pidfd)):
        raise ValueError('marketing_attester_retained_original_actor_exit_handles_required')
    binding = store._read(root, 'actor-scope-binding.json')
    actual = _observe(binding, deadline=context['deadline_monotonic'], byte_limit=16384, phase_deadline=deadline)
    receiver = _parse_record(store._read(root, 'private-final-kernel-scope.json'))
    owned = _parse_record(actual)
    for key in ('independent_binding_sha256', 'boot_id'):
        if receiver[key] != owned[key]:
            raise ValueError('marketing_attester_receiver_final_kernel_binding_changed')
    for key in ('snapshot_first', 'snapshot_second'):
        def strip(rows):
            return [{k: v for k, v in row.items() if k != 'raw_fdinfo'} for row in rows]
        if strip(receiver[key]) != strip(owned[key]):
            raise ValueError('marketing_attester_original_final_root_observation_changed')
        if {v['relative'] for v in owned[key]} != {'.', './framework', './graph', './host_helpers'}:
            raise ValueError('marketing_attester_original_final_root_members_required')
        for node in owned[key]:
            events = dict(line.split() for line in node['raw_kernel_files']['cgroup.events'].splitlines())
            if events.get('frozen') != '1' or events.get('populated') != '0':
                raise ValueError('marketing_attester_final_kernel_not_frozen_empty')
    containers = _parse_record(store._read(root, 'private-final-containers.json'))
    if set(containers['roles']) != {'environment', 'tests'}:
        raise ValueError('marketing_attester_both_original_containers_required')
    for role, original in containers['roles'].items():
        current = asyncio.run(_request('inspect', original['binding']['container_id'], deadline=deadline, private=True))
        _inspect(current, original['binding'], stopped=True)
        if (digest({k: current[k] for k in ('Id', 'Image', 'Name', 'Config', 'HostConfig', 'Mounts')})
                != original['identity_fields_sha256'] or current['State'] != original['current_state']
                or current['RestartCount'] != original['restart_count']):
            raise ValueError('marketing_attester_original_final_container_changed')
        _write_at(root, 'attester-own-final-' + role + '-inspect.json', canonical(current), mode=0o400)
    _write_at(root, 'attester-own-final-kernel-scope.json', actual, mode=0o400)
    _remaining(deadline)
