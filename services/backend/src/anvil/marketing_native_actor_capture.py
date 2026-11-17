"""Intermediate actor-scope custody; NEVER whole-operation/native acceptance.

Actual graph PID join/empty subgroup, API Q and stopped owned container precede
the private diagnostic capture. Independent attester/final operation seal remains
separate and unqualified. File/hash validation alone grants no runtime authority.
"""

import hashlib

from anvil.marketing_native_attempt import _write_at
from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical
from anvil.marketing_native_kernel_scope import _events
from anvil.marketing_native_records import _parse_record
from anvil.marketing_native_world_binding import (
    opening_source_nomination,
    retained_source_nomination,
)

KIND = 'actor_graph_and_environment_container'
REFS = {
    'operation_scope_binding_sha256': ('actor-scope-binding.json', 4096),
    'child_binding_sha256': ('actor-scope-children.json', 4096),
    'graph_scope_observation_sha256': ('graph-scope-empty.json', 16384),
    'graph_process_join_sha256': ('graph-process-join.json', 4096),
    'graph_process_return_sha256': ('graph-process-return.json', 2048),
    'graph_child_cleanup_sha256': ('graph-child-cleanup-observation.json', 16384),
    'world_fence_status_sha256': ('world-fence-status.json', 16384),
    'world_final_status_sha256': ('world-final-status.json', 16384),
    'container_stop_observed_sha256': ('environment-container-stop-observed.json', 16384),
    'container_current_inspect_sha256': ('actor-capture-final-container-inspect.json', DOCUMENT_CAP),
}


def _pin(raw):
    return hashlib.sha256(raw).hexdigest()


def _graph_empty(value, binding_raw, children):
    if (set(value) != {'schema_version', 'binding_sha256', 'first', 'second', 'whole_operation_stopped',
                       'capture_ready', 'native_qualified'}
            or value['schema_version'] != 'anvil.marketing-empty-graph-subscope-observation.v1'
            or value['binding_sha256'] != _pin(binding_raw)
            or any(value[k] is not False for k in ('whole_operation_stopped', 'capture_ready', 'native_qualified'))):
        raise ValueError('marketing_actual_graph_subscope_observations_required')
    original = children['children']['graph']
    if any(type(original.get(k)) is not int or original[k] <= 0 for k in ('device', 'inode', 'mount_id')):
        raise ValueError('marketing_original_graph_child_kernel_ids_required')
    for key in ('first', 'second'):
        rows = value[key]
        if type(rows) is not list or len(rows) != 1:
            raise ValueError('marketing_original_flat_graph_subscope_required')
        node = rows[0]
        if (type(node) is not dict or set(node) != {'relative', 'device', 'inode', 'mount_id', 'raw_kernel_files', 'raw_fdinfo'}
                or any(type(node.get(k)) is not int or node[k] <= 0 for k in ('device', 'inode', 'mount_id'))
                or node.get('relative') != '.' or node.get('device') != original['device']
                or node.get('inode') != original['inode'] or node.get('mount_id') != original['mount_id']):
            raise ValueError('marketing_original_graph_kernel_identity_changed')
        files = node['raw_kernel_files']
        if type(files) is not dict or set(files) != {'cgroup.events', 'cgroup.procs', 'cgroup.threads'}:
            raise ValueError('marketing_actual_graph_kernel_file_set_required')
        _events(files['cgroup.events'])
        if dict(line.split() for line in files['cgroup.events'].splitlines()).get('frozen') != '1':
            raise ValueError('marketing_graph_scope_freeze_not_observed')
        if files['cgroup.procs'].strip() or files['cgroup.threads'].strip():
            raise ValueError('marketing_original_graph_process_or_thread_remains')
    if ([{k: v for k, v in row.items() if k != 'raw_fdinfo'} for row in value['first']]
            != [{k: v for k, v in row.items() if k != 'raw_fdinfo'} for row in value['second']]):
        raise ValueError('marketing_graph_scope_changed_before_capture')


def validate_actor_capture_files(store, root, claim, plan):
    from anvil.marketing_native_stop import _container_binding, _inspect
    from anvil.marketing_native_world_stop import _status

    proof_raw = store._read(root, 'actor-scope-stop-observed.json')
    proof = _parse_record(proof_raw)
    fields = {'schema_version', 'scope_kind', 'request_sha256', 'plan_sha256', 'framework_trial_id',
              'operation_nonce', 'operator_program_sha256', 'source_nomination_sha256', 'api_scope',
              'quiescence_sha256', 'actor_output_sha256', 'graph_receipt_sha256', 'whole_operation_stopped',
              'native_qualified', 'capture_accepted', 'diagnostic_only'} | set(REFS)
    if (len(proof_raw) > 8192 or set(proof) != fields
            or proof['schema_version'] != 'anvil.marketing-actor-scope-stop-observed.v1' or proof['scope_kind'] != KIND
            or any(proof[k] != claim[k] for k in ('request_sha256', 'plan_sha256'))
            or proof['operator_program_sha256'] != plan['operator_program_sha256']
            or proof['source_nomination_sha256'] != retained_source_nomination(store, root)
            or proof['diagnostic_only'] is not True
            or any(proof[k] is not False for k in ('whole_operation_stopped', 'native_qualified', 'capture_accepted'))):
        raise ValueError('marketing_distinct_intermediate_actor_capture_required')
    documents = {}
    for key, (name, cap) in REFS.items():
        raw = store._read(root, name)
        if not 0 < len(raw) <= cap or _pin(raw) != proof[key]:
            raise ValueError('marketing_actual_actor_capture_reference_changed')
        documents[name] = _parse_record(raw)
    binding = documents['actor-scope-binding.json']
    context = _parse_record(store._read(root, 'component-context.json'))
    entry = _parse_record(store._read(root, 'framework-entry.json'))
    if (any(binding[k] != claim[k] for k in ('request_sha256', 'plan_sha256'))
            or binding['operation_nonce'] != context['operation_nonce']
            or binding['boot_id'] != context['boot_id']
            or binding['original_deadline_monotonic'] != context['deadline_monotonic']
            or any(proof[k] != entry[k] for k in ('request_sha256', 'plan_sha256', 'framework_trial_id', 'operation_nonce'))):
        raise ValueError('marketing_original_actor_capture_operation_changed')
    children = documents['actor-scope-children.json']
    child_shape = (children.get('schema_version'), set(children.get('children', {})))
    if (child_shape not in (
            ('anvil.marketing-original-actor-scope-children.v1', {'framework', 'graph'}),
            ('anvil.marketing-original-actor-scope-children.v2', {'framework', 'graph', 'host_helpers'}))
            or children.get('binding_sha256') != proof['operation_scope_binding_sha256']
            or children.get('native_qualified') is not False):
        raise ValueError('marketing_original_actor_child_bindings_required')
    _graph_empty(documents['graph-scope-empty.json'], store._read(root, 'actor-scope-binding.json'), children)
    join = documents['graph-process-join.json']
    enrollment = _parse_record(store._read(root, 'graph-scope-enrollment-intent.json'))
    if (join.get('schema_version') != 'anvil.marketing-original-graph-process-join.v1'
            or join.get('wait_status') != 0 or type(join.get('wait_status')) is not int
            or join.get('pid') != enrollment['pid'] or join.get('start_ticks') != enrollment['start_ticks']
            or join.get('graph_scope_observation_sha256') != proof['graph_scope_observation_sha256']
            or join.get('reply_sha256') != proof['graph_process_return_sha256']
            or any(join.get(k) != proof[k] for k in ('request_sha256', 'plan_sha256', 'operation_nonce'))
            or join.get('whole_operation_stopped') is not False or join.get('native_qualified') is not False):
        raise ValueError('marketing_actual_original_graph_process_join_required')
    returned = documents['graph-process-return.json']
    cleanup = documents['graph-child-cleanup-observation.json']
    if (returned.get('schema_version') != 'anvil.marketing-graph-child-return.v1'
            or returned.get('state') != 'original_graph_and_api_container_cleanup_returned'
            or returned.get('cleanup_observation_sha256') != proof['graph_child_cleanup_sha256']
            or any(returned.get(k) is not False for k in ('whole_actor_stopped', 'capture_ready', 'native_qualified'))
            or cleanup.get('schema_version') != 'anvil.marketing-candidate-api-container-stop.v1'
            or any(cleanup.get(k) is not False for k in ('whole_actor_stopped', 'physical_stop_verified',
                                                        'capture_ready', 'native_qualified', 'replay_permitted'))
            or cleanup.get('api', {}).get('api_quiescent') is not True
            or cleanup.get('api', {}).get('final_status_sha256') != proof['world_final_status_sha256']
            or _pin(_bounded_canonical(cleanup.get('container_observation'), DOCUMENT_CAP))
            != proof['container_stop_observed_sha256']):
        raise ValueError('marketing_original_graph_child_return_custody_required')
    owner = _parse_record(store._read(root, 'original-world-owner-intent.json'))
    if _pin(_bounded_canonical(proof['api_scope'], DOCUMENT_CAP)) != owner['independent_stop_scope_sha256']:
        raise ValueError('marketing_independent_original_api_scope_changed')
    fenced = _status(documents['world-fence-status.json'], proof['api_scope'])
    final = _status(documents['world-final-status.json'], proof['api_scope'], fenced['fence'])
    if final['state'] != 'api_quiescent' or final['quiescence']['receipt_sha256'] != proof['quiescence_sha256']:
        raise ValueError('marketing_actual_original_api_quiescence_required')
    stop = documents['environment-container-stop-observed.json']
    native_binding = _container_binding(store, root, claim, plan, 'environment')
    if (stop.get('schema_version') != 'anvil.marketing-container-stop-observed.v2'
            or stop.get('role') != 'environment' or stop.get('container_stopped_observed') is not True
            or stop.get('late_start_effects_unqualified') is not False or stop.get('binding_origin') != 'completed_start'
            or stop.get('binding_sha256') != _pin(_bounded_canonical(native_binding, DOCUMENT_CAP))
            or stop.get('container_id') != native_binding['container_id']
            or any(stop.get(k) != proof[k] for k in ('request_sha256', 'plan_sha256', 'framework_trial_id', 'operation_nonce'))):
        raise ValueError('marketing_complete_original_actor_container_stop_required')
    _inspect(documents['actor-capture-final-container-inspect.json'], native_binding, stopped=True)
    for name, key, cap in (('captured-actor-output.json', 'actor_output_sha256', plan['bounds']['output_bytes']),
                           ('graph-returned-receipt.json', 'graph_receipt_sha256', plan['bounds']['receipt_bytes'])):
        raw = store._read(root, name)
        if not 0 < len(raw) <= cap or _pin(raw) != proof[key]:
            raise ValueError('marketing_actual_actor_capture_bytes_changed')
    return proof_raw


async def produce_actor_capture(owner):
    from anvil.marketing_native_actor_timing import opening_phases
    from anvil.marketing_native_engine import _request
    from anvil.marketing_native_kernel_scope import _remaining
    from anvil.marketing_native_mounts import _capture_inputs
    from anvil.marketing_native_stop import _container_binding, _inspect
    from anvil.marketing_native_world_stop import _status

    store, root, claim, plan = owner._store, owner._root, owner._claim, owner._plan
    if (owner._graph is None or owner._graph._joined is not True
            or owner._graph._state != 'joined_and_graph_scope_empty_NOT_whole_operation'):
        raise ValueError('marketing_original_graph_join_before_capture_required')
    value = _parse_record(owner._request.canonical_bytes)
    phases = opening_phases(plan['bounds'], deadline=owner._context['deadline_monotonic'],
                            started=owner._actor_started, now=owner._actor_started,
                            request_timeout=value['request_timeout_seconds'], private=owner._private)
    capture_deadline = phases['actor_join_deadline_monotonic']
    _remaining(capture_deadline)
    _write_at(root, 'actor-capture-intent.json', _bounded_canonical({
        'schema_version': 'anvil.marketing-actor-scope-capture-intent.v1',
        'request_sha256': claim['request_sha256'], 'plan_sha256': claim['plan_sha256'],
        'scope_kind': KIND, 'original_deadline_monotonic': owner._context['deadline_monotonic'],
        'capture_phase_deadline_monotonic': capture_deadline, 'native_qualified': False, 'replay_permitted': False,
    }, 4096))
    world = _parse_record(dict(owner._records.records)['world'])['payload']
    expected = world['stop_scope']
    fenced = _status(_parse_record(store._read(root, 'world-fence-status.json')), expected)
    final = _status(_parse_record(store._read(root, 'world-final-status.json')), expected, fenced['fence'])
    if final['state'] != 'api_quiescent':
        raise ValueError('marketing_actual_api_quiescence_before_capture_required')
    binding = _container_binding(store, root, claim, plan, 'environment')
    actual = await _request('inspect', binding['container_id'], deadline=capture_deadline, private=owner._private)
    _inspect(actual, binding, stopped=True)
    _write_at(root, 'actor-capture-final-container-inspect.json', _bounded_canonical(actual, DOCUMENT_CAP))
    output = store._read(root, 'graph-returned-output.json')
    receipt = store._read(root, 'graph-returned-receipt.json')
    if not 0 < len(output) <= plan['bounds']['output_bytes'] or not 0 < len(receipt) <= plan['bounds']['receipt_bytes']:
        raise ValueError('marketing_original_graph_capture_cap_required')
    entry = _parse_record(store._read(root, 'framework-entry.json'))
    proof = {'schema_version': 'anvil.marketing-actor-scope-stop-observed.v1', 'scope_kind': KIND,
             **{k: entry[k] for k in ('request_sha256', 'plan_sha256', 'framework_trial_id', 'operation_nonce')},
             'operator_program_sha256': plan['operator_program_sha256'],
             'source_nomination_sha256': opening_source_nomination(private=owner._private),
             'api_scope': expected, 'quiescence_sha256': final['quiescence']['receipt_sha256'],
             'actor_output_sha256': _pin(output), 'graph_receipt_sha256': _pin(receipt),
             'whole_operation_stopped': False, 'native_qualified': False, 'capture_accepted': False, 'diagnostic_only': True}
    proof.update({key: _pin(store._read(root, name)) for key, (name, _) in REFS.items()})
    proof_raw = _bounded_canonical(proof, 8192)
    collection = _bounded_canonical({'schema_version': 'anvil.marketing-collection-capture.v1',
                                    **{k: entry[k] for k in ('request_sha256', 'framework_trial_id', 'operation_nonce')},
                                    'actor_output_sha256': _pin(output), 'graph_receipt_sha256': _pin(receipt),
                                    'diagnostic_only': True}, plan['bounds']['receipt_bytes'])
    stop = {'schema_version': 'anvil.marketing-actor-stop.v2',
            **{k: entry[k] for k in ('request_sha256', 'plan_sha256', 'framework_trial_id', 'operation_nonce')},
            'state': 'actor_stopped_observed', 'native_stop_receipt_sha256': _pin(proof_raw),
            'actor_output_sha256': _pin(output), 'collection_receipt_sha256': _pin(collection),
            'scope_kind': KIND, 'operator_program_sha256': plan['operator_program_sha256'],
            'source_nomination_sha256': opening_source_nomination(private=owner._private)}
    for name, body in (('captured-actor-output.json', output), ('captured-collection-receipt.json', collection),
                       ('actor-scope-stop-observed.json', proof_raw), ('actor-stop.json', _bounded_canonical(stop, 4096))):
        _remaining(capture_deadline)
        _write_at(root, name, body, mode=0o400)
        if store._read(root, name) != body:
            raise RuntimeError('marketing_actor_capture_write_unknown_no_retry')
    _capture_inputs(store, root, claim, plan, opening=True)
    _remaining(capture_deadline)
    return stop  # Intermediate actor scope only; final operation/native gate remains closed.
