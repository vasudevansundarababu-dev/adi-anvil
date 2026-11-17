"""Independent receiver's fixed private verifier process/result collection.

An actual zero container exit produces a result, not a pass or native acceptance.
The original SDK is necessarily alive here; whole-root shutdown follows its exit.
"""

import hashlib
import json
import os
import select
import stat

from anvil.marketing_capture_verifier import OriginalVerifierBinding, validate_private_result
from anvil.marketing_native_attempt import _owned, _write_at
from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical
from anvil.marketing_native_kernel_scope import _remaining
from anvil.marketing_native_records import _parse_record
from anvil.praxis_generic_contract import canonical


def require_private_reply_capacity(program):
    """Conservative legal shape bound, not an execution/expected-answer fixture."""
    from anvil.marketing_capture_verifier import CRITERION_WEIGHTS
    from anvil.marketing_task2_contract import CRITICAL, GROUPS

    identity = {'job_id': str(program['scope']['job_id']), 'framework_trial_id': 'f' * 36,
                **dict.fromkeys(('operation_nonce', 'request_sha256', 'plan_sha256'), 'f' * 64)}
    bound = {'schema_version': 'anvil.marketing-private-result.v1', 'profile': 'anvil.marketing-private-verifier.v1',
        **{k: program[k] for k in ('scope', 'source_sha256', 'rubric_id', 'rubric_version', 'scoring_contract', 'scoring_source_pins')},
        'identity': identity, 'input_sha256': 'f' * 64,
        'input_files': dict.fromkeys(('actor-output.json', 'private-evidence.json', 'evaluation-profile.json'), 'f' * 64),
        'scale': 'zero_to_four', 'levels': dict.fromkeys(CRITERION_WEIGHTS, None),
        'groups': dict.fromkeys(GROUPS, {'numerator': 400, 'denominator': 4}),
        'total': {'numerator': 400, 'denominator': 4}, 'result': 'unscored', 'output_gate': False,
        'unscored_criteria': sorted(CRITERION_WEIGHTS), 'unknown_critical_rules': sorted(CRITICAL),
        'critical_failures': sorted(CRITICAL), 'human_legal_acceptance': 'not_established',
        'model_performance_validated': False, 'native_qualification_granted': False, 'paid_calls': False}
    result = json.dumps(bound, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
    reply = {'schema_version': 'anvil.marketing-private-component-reply.v1', 'event': 'collect_private',
        'identity': identity, 'scope': program['scope'], 'session_id': 'x' * 80,
        'status': 'private_process_completed', 'result': result.decode(), 'result_sha256': 'f' * 64,
        'result_bytes': 1048576, 'container_id': 'f' * 64, 'container_exit_code': 0, 'process_receipt_sha256': 'f' * 64}
    # Include the receiver's envelope too; the public control cap remains16KiB.
    outer = {'schema_version': 'anvil.marketing-original-private-role-reply.v1', 'request_sha256': 'f' * 64,
        'operation_nonce': 'f' * 64, 'result': reply, 'capture_accepted': False, 'run_authority': 'not_granted'}
    _bounded_canonical(outer, 16384)
    return len(result)


def _result_file(store, root, claim, deadline):
    parent = store._walk(root, ['trials', claim['trial_name']])
    folder = fd = None
    try:
        folder = os.open('verifier', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        before_dir = os.fstat(folder)
        _owned(before_dir, 10001, directory=True, private=True)
        if stat.S_IMODE(before_dir.st_mode) != 0o700 or before_dir.st_gid != 10001 or os.listdir(folder) != ['result.json']:
            raise ValueError('marketing_exact_original_private_result_directory_required')
        fd = os.open('result.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=folder)
        before = os.fstat(fd)
        _owned(before, 10001)
        if stat.S_IMODE(before.st_mode) != 0o600 or before.st_gid != 10001 or not 0 < before.st_size <= DOCUMENT_CAP:
            raise ValueError('marketing_actual_original_private_result_file_required')
        chunks, count = [], 0
        while True:
            _remaining(deadline)
            chunk = os.read(fd, min(32768, DOCUMENT_CAP + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            if count > DOCUMENT_CAP:
                raise ValueError('marketing_complete_private_result_capacity')
            chunks.append(chunk)
        after, after_dir = os.fstat(fd), os.fstat(folder)
        def identity(i):
            return (i.st_dev, i.st_ino, i.st_mode, i.st_uid, i.st_gid, i.st_nlink, i.st_size, i.st_mtime_ns, i.st_ctime_ns)
        if identity(before) != identity(after) or identity(before_dir) != identity(after_dir) or count != before.st_size:
            raise ValueError('marketing_private_result_changed_during_capture')
        raw = b''.join(chunks)
        return raw, {'source': '/logs/verifier/result.json', 'device': before.st_dev, 'inode': before.st_ino,
            'uid': before.st_uid, 'gid': before.st_gid, 'mode': '0600', 'links': before.st_nlink,
            'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    finally:
        for value in (fd, folder, parent):
            if value is not None:
                os.close(value)


async def collect_original_private_result(owner, event):
    from anvil.marketing_native_actor_capture import validate_actor_capture_files
    from anvil.marketing_native_attester_receiver import _ReceiverOperation
    from anvil.marketing_native_engine import _request
    from anvil.marketing_native_physical import _assets, _inspect_profile
    from anvil.marketing_native_start import _check, _profile
    from anvil.marketing_native_stop import _container_binding, _inspect

    if type(owner) is not _ReceiverOperation or owner._stage != 'verifier':
        raise ValueError('marketing_original_independent_verifier_receiver_required')
    store, root, claim, plan, context = owner._store, owner._root, owner._claim, owner._plan, owner._context
    deadline = context['deadline_monotonic'] - plan['bounds']['cleanup_seconds'] - 8
    _remaining(deadline)
    binding_raw = store._read(root, 'private-verifier-binding.json')
    original = OriginalVerifierBinding.model_validate_json(binding_raw)
    binding = original.model_dump(mode='json')
    fields = {'schema_version', 'event', 'job_id', 'framework_trial_id', 'operation_nonce', 'request_sha256',
              'plan_sha256', 'scope', 'role', 'session_id', 'input_sha256', 'source_sha256', 'profile_sha256'}
    if (set(event) != fields or event['schema_version'] != 'anvil.marketing-private-component-event.v1'
            or event['event'] != 'collect_private' or event['role'] != 'tests'
            or any(event[k] != v for k, v in binding['identity'].items()) or event['scope'] != binding['scope']
            or event['session_id'] != claim['trial_name'] + '__verifier__trial'
            or event['input_sha256'] != binding['input_sha256'] or event['source_sha256'] != binding['source_sha256']
            or event['profile_sha256'] != binding['input_files']['evaluation-profile.json']
            or not select.select([owner._actors['graph']['pidfd']], [], [], 0)[0]
            or select.select([owner._actors['framework']['pidfd']], [], [], 0)[0]):
        raise ValueError('marketing_actual_original_private_collection_identity_required')
    actor_proof = validate_actor_capture_files(store, root, claim, plan)
    _check(store, owner._request, role='tests', stage='before_collection', opening=True)
    container = _container_binding(store, root, claim, plan, 'tests')
    _write_at(root, 'private-verifier-collect-intent.json', _bounded_canonical({
        'schema_version': 'anvil.marketing-private-process-collection-intent.v1', 'identity': binding['identity'],
        'container_id': container['container_id'], 'work_deadline_monotonic': deadline,
        'replay_permitted': False}, 4096), mode=0o400)
    waited = await _request('wait_private_verifier', container['container_id'], deadline=deadline, private=True)
    after = await _request('inspect', container['container_id'], deadline=deadline, private=True)
    _inspect(after, container, stopped=True)
    profile = _profile(store, root, claim, plan, 'tests', 'start')
    _, _, image = _assets(owner._records, context)
    _inspect_profile(after, profile['services']['main'], image, container['session_id'], container['container_id'],
                     running=True, private_verifier=True)
    state = after['State']
    if (state.get('Running') is not False or type(state.get('ExitCode')) is not int or state['ExitCode'] != 0
            or type(state.get('FinishedAt')) is not str or not state['FinishedAt'] or state['FinishedAt'].startswith('0001-')):
        raise ValueError('marketing_actual_private_verifier_completed_exit_required')
    raw, output = _result_file(store, root, claim, deadline)
    validate_private_result(raw, original)
    # Fixed producer ASCII representation is retained, never silently rewritten.
    if json.dumps(json.loads(raw), ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii') != raw:
        raise ValueError('marketing_original_fixed_private_result_representation_required')
    program = _parse_record(store._read(root, 'private-verifier-program.json'))
    if len(raw) > require_private_reply_capacity(program):
        raise ValueError('marketing_private_result_exceeds_preprovider_shape_bound')
    inspection = _bounded_canonical(after, DOCUMENT_CAP)
    _write_at(root, 'private-verifier-completed-inspect.json', inspection, mode=0o400)
    receipt = _bounded_canonical({
        'schema_version': 'anvil.marketing-private-verifier-process-observed.v1',
        'identity': binding['identity'], 'scope': binding['scope'], 'role': 'tests',
        'session_id': container['session_id'], 'container_id': container['container_id'], 'image_id': container['image_id'],
        'argv': ['python3', '-I', '-B', '-m', 'anvil_harbor.marketing_private_verifier'],
        'source_sha256': binding['source_sha256'], 'sdk_binding_sha256': hashlib.sha256(binding_raw).hexdigest(),
        'program_sha256': hashlib.sha256(store._read(root, 'private-verifier-program.json')).hexdigest(),
        'input_seal_receipt_sha256': hashlib.sha256(store._read(root, 'private-verifier-seal-receipt.json')).hexdigest(),
        'input_sha256': binding['input_sha256'], 'input_files': binding['input_files'],
        'mounts': after['Mounts'], 'container_binding_sha256': hashlib.sha256(canonical(container)).hexdigest(),
        'created_inspect_sha256': hashlib.sha256(store._read(root, 'tests-created-engine-inspect.json')).hexdigest(),
        'started_inspect_sha256': hashlib.sha256(store._read(root, 'tests-started-engine-inspect.json')).hexdigest(),
        'completed_inspect_sha256': hashlib.sha256(inspection).hexdigest(), 'engine_wait': waited,
        'exit_code': state['ExitCode'], 'started_at': state['StartedAt'], 'finished_at': state['FinishedAt'],
        'output': output, 'actor_capture_sha256': hashlib.sha256(actor_proof).hexdigest(),
        # Complete original canonical objects, not another caller-only hash.
        # The API can now connect its authenticated actor-stop digest to this
        # actual graph/environment capture proof through native_stop_receipt.
        'actor_stop': _parse_record(store._read(root, 'actor-stop.json')),
        'actor_capture_proof': _parse_record(actor_proof),
        'whole_operation_stopped': False, 'capture_accepted': False, 'native_qualified': False, 'run_authority': 'not_granted',
    }, DOCUMENT_CAP)
    _write_at(root, 'private-verifier-result.json', raw, mode=0o400)
    _write_at(root, 'private-verifier-process.json', receipt, mode=0o400)
    reply = {'schema_version': 'anvil.marketing-private-component-reply.v1', 'event': 'collect_private',
        'identity': binding['identity'], 'scope': binding['scope'], 'session_id': container['session_id'],
        'status': 'private_process_completed', 'result': raw.decode('ascii'), 'result_sha256': output['sha256'],
        'result_bytes': len(raw), 'container_id': container['container_id'], 'container_exit_code': 0,
        'process_receipt_sha256': hashlib.sha256(receipt).hexdigest()}
    _bounded_canonical(reply, 16384)
    _remaining(deadline)
    return reply
