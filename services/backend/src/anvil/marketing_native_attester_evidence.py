"""Independent receiver's actual-handle checks plus retained QA policy custody.

No diagnostic is promoted by a caller flag. Nonobservable properties require
the original privately admitted policy/evidence records, exact source/profile,
current boot/image binding and current kernel constraints. This code issues no
qualification and creates no evidence-policy records. Missing records refuse.
"""

import hashlib
import os
import re
from datetime import datetime

from anvil.marketing_capture_peer import REQUIRED_EVIDENCE, parse_independent_receipt
from anvil.marketing_native_attester_peer import _status
from anvil.marketing_native_kernel_scope import _remaining
from anvil.marketing_native_records import _parse_record
from anvil.marketing_native_world_binding import _read_source_file
from anvil.praxis_generic_contract import canonical

PRODUCER_FILES_V1 = frozenset({
    'marketing_native_attester_key.py', 'marketing_native_attester_worker.py',
    'marketing_native_attester_process.py', 'marketing_native_attester_peer.py',
    'marketing_native_attester_evidence.py', 'marketing_native_enrollment_receiver.py',
    'marketing_native_attester_receiver.py',
    'marketing_native_private_control.py', 'marketing_native_helper_process.py',
    'marketing_native_receiver_worker.py', 'marketing_native_private_pair.py',
    'marketing_native_job_packet.py',
    'marketing_native_private_environment.py', 'marketing_native_wire_bounds.py',
    'marketing_native_private_records.py', 'marketing_native_private_sources.py',
    'marketing_native_worker_flags.py', 'marketing_native_mcp_support.py', 'golden_mcp_client.py', 'db.py',
    'marketing_native_private_actor_client.py', 'marketing_native_private_grade_client.py',
    'marketing_native_private_seal.py', 'marketing_native_private_collect.py',
    'marketing_native_private_finalize.py', 'marketing_native_private_post.py',
    'marketing_native_kernel_scope.py', 'marketing_native_actor_capture.py', 'marketing_native_actor_timing.py',
    'marketing_native_physical.py', 'marketing_native_engine.py', 'marketing_native_stop.py',
    'marketing_native_verifier_renderer.py', 'marketing_native_control.py',
    'marketing_private_capture_receipt.py', 'marketing_capture_verifier.py',
    'marketing_native_launcher.py', 'marketing_native_actor_owner.py', 'marketing_native_graph_process.py',
    'marketing_native_enrollment_client.py', 'marketing_native_actor_hardening.py',
    'marketing_capture_peer.py', 'marketing_attester_enrollment.py', 'marketing_operator_database.py',
})

# Successor policy closure. Existing retained policy hashes/receipts are never
# rewritten; their smaller dependency set cannot qualify this new source epoch.
PRODUCER_FILES_V2 = PRODUCER_FILES_V1 | frozenset({
    'marketing_native_private_sources_v2.py', 'qualification_resources.py',
    'marketing_native_operator_observation.py', 'owned_process_group.py',
    'marketing_native_operator_driver.py',
})
PRODUCER_FILES_V3 = PRODUCER_FILES_V2 | frozenset({'marketing_native_private_sources_v3.py'})
PRODUCER_FILES = PRODUCER_FILES_V3


def _namespace(proc, pid, name, deadline):
    _remaining(deadline)
    fd = os.open(str(pid) + '/ns/' + name, os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc)
    try:
        info = os.fstat(fd)
        return info.st_dev, info.st_ino
    finally:
        os.close(fd)


def _fdinfo(raw):
    fields = {}
    for line in raw.splitlines():
        key, separator, value = line.partition(':')
        if not separator or key in fields:
            raise ValueError('marketing_exact_independent_fdinfo_required')
        fields[key] = value.strip()
    if not fields.get('ino', '').isdecimal() or not fields.get('flags', '').isdigit():
        raise ValueError('marketing_independent_fd_identity_required')
    return fields


def _endpoints(process, observed):
    """Compare the actual child's ENTIRE inventory with retained parent custody."""
    owner = process._owner
    rows = observed['direct_kernel_snapshot']['descriptors']
    actual = {row['fd']: row for row in rows}
    if len(actual) != len(rows):
        raise ValueError('marketing_peer_duplicate_descriptor')
    known = process._passed
    expected_numbers = {value['fd'] for value in known.values()}
    if len(expected_numbers) != 4 or expected_numbers & {0, 1, 2}:
        raise ValueError('marketing_peer_exact_inherited_descriptor_custody_required')
    for name, expected in known.items():
        row = actual.get(expected['fd'])
        if row is None:
            raise ValueError('marketing_peer_inherited_endpoint_missing')
        info = _fdinfo(row['fdinfo'])
        if int(info['ino']) != expected['inode'] or not int(info['flags'], 8) & os.O_CLOEXEC:
            raise ValueError('marketing_peer_endpoint_identity_or_exec_closure_changed')
        if name == 'channel':
            if row['target'] != 'socket:[' + str(expected['inode']) + ']':
                raise ValueError('marketing_peer_fixed_private_channel_changed')
        else:
            expected_pid = {'receiver_pidfd': os.getpid(),
                            'sdk_pidfd': owner._actors['framework']['pid'],
                            'graph_pidfd': owner._actors['graph']['pid']}[name]
            if info.get('Pid') != str(expected_pid) or not row['target'].startswith('anon_inode:'):
                raise ValueError('marketing_peer_original_pidfd_endpoint_changed')
    for number in (0, 1, 2):
        if actual.get(number, {}).get('target') != '/dev/null':
            raise ValueError('marketing_peer_stdio_must_not_carry_secrets')
    extras = [row for number, row in actual.items() if number not in expected_numbers | {0, 1, 2}]
    expected_dirs = {str(owner._store.parent): os.fstat(owner._store.fd).st_ino,
                     str(owner._store.parent / owner._claim['trial_name']): os.fstat(owner._root).st_ino}
    if len(extras) != len(expected_dirs) or {row['target'] for row in extras} != set(expected_dirs):
        raise ValueError('marketing_peer_unexpected_inherited_or_live_descriptor')
    for row in extras:
        info = _fdinfo(row['fdinfo'])
        if (int(info['ino']) != expected_dirs[row['target']] or int(info['flags'], 8) & os.O_ACCMODE != os.O_RDONLY
                or not int(info['flags'], 8) & os.O_CLOEXEC):
            raise ValueError('marketing_peer_private_readonly_directory_endpoint_changed')


def _verify_policy(category, policy, process, observation, proc, deadline):
    constraints = policy['constraints']
    if type(constraints) is not dict:
        raise ValueError('marketing_independent_policy_constraints_required')
    owner = process._owner
    if category == 'loaded_source_and_image_identity':
        if set(constraints) != {'source_dependencies'} or set(constraints['source_dependencies']) != PRODUCER_FILES:
            raise ValueError('marketing_complete_current_attester_producer_sources_required')
        for name, pin in constraints['source_dependencies'].items():
            _remaining(deadline)
            _read_source_file(name, pin)
    elif category == 'dumpability_and_proc_access':
        if set(constraints) != {'hardening_source_sha256', 'kernel_release'} or constraints['kernel_release'] != os.uname().release:
            raise ValueError('marketing_original_kernel_privacy_policy_required')
        _read_source_file('marketing_native_actor_hardening.py', constraints['hardening_source_sha256'])
        # Dumpability is NOT inferred from this status. Its actual qualified
        # kernel/profile test is retained independently in the receipt below.
        _status(proc, process._child.pid, deadline)
        for actor in owner._actors.values():
            _status(proc, actor['pid'], deadline)
        parents = {actor['parent_pid'] for actor in _parse_record(owner._actors_beforeG_raw)['children'].values()}
        if len(parents) != 1:
            raise ValueError('marketing_original_disjoint_private_control_identity_required')
        _status(proc, next(iter(parents)), deadline)
    elif category == 'namespace_and_signal_isolation':
        if constraints != {'policy': 'outside-attester-private-actor-mounts-v1'}:
            raise ValueError('marketing_supported_original_namespace_policy_required')
        outside = observation['direct_kernel_snapshot']['namespaces']['mnt']
        identity = outside['device'], outside['inode']
        if identity != _namespace(proc, os.getpid(), 'mnt', deadline):
            raise ValueError('marketing_attester_must_use_independent_receiver_namespace')
        for actor in owner._actors.values():
            if _namespace(proc, actor['pid'], 'mnt', deadline) == identity:
                raise ValueError('marketing_actor_still_shares_attester_mount_namespace')
    elif category == 'exact_allowed_fd_endpoint_custody':
        if constraints != {'policy': 'fixed-key-worker-channel-pidfds-private-readonly-roots-v1'}:
            raise ValueError('marketing_supported_original_endpoint_policy_required')
        _endpoints(process, observation)
    elif category == 'qualified_verifier_profile':
        if constraints != {'receiver_pid': owner._facts.receiver_pid, 'receiver_start_ticks': owner._facts.receiver_start_ticks}:
            raise ValueError('marketing_original_independent_receiver_profile_changed')
        if owner._facts.receiver_pid != os.getpid():
            raise ValueError('marketing_only_original_independent_receiver_may_persist_peer')
    elif category == 'attester_key_and_public_ready_binding':
        if set(constraints) != {'key_source_sha256', 'worker_source_sha256', 'protocol'} or constraints['protocol'] != 'fixed-domain-key-possession-v1':
            raise ValueError('marketing_supported_original_private_key_protocol_required')
        _read_source_file('marketing_native_attester_key.py', constraints['key_source_sha256'])
        _read_source_file('marketing_native_attester_worker.py', constraints['worker_source_sha256'])
        if process._state != 'key_possession_observed' or process._proof_raw is None:
            raise ValueError('marketing_actual_owned_process_key_proof_required')
    else:
        raise ValueError('marketing_unknown_independent_evidence_policy')


def _independent_os_receipt(process, observation_raw):
    """Only a qualified actual receiver may call; SQL rechecks its identity/Q.

    Retained independent-QA receipts are INPUT authority from the private store,
    never created here from diagnostic metadata. Their bytes/policies, exact
    profile/source/current boot/image and current kernel constraints all bind.
    This function cannot mint missing qualification or claim tests ran.
    """
    from anvil.marketing_native_attester_process import _IndependentAttesterProcess
    from anvil.marketing_native_private_records import original_operator_store

    if type(process) is not _IndependentAttesterProcess or process._state != 'key_possession_observed':
        raise ValueError('marketing_independent_actual_key_process_custody_required')
    process.require_live()
    owner, facts = process._owner, process._owner._facts
    observation = _parse_record(observation_raw)
    deadline = owner._phase_deadline
    if observation['pid'] != process._child.pid or observation['start_ticks'] != process._ticks:
        raise ValueError('marketing_independent_observation_owned_child_changed')
    image = _parse_record(dict(owner._records.records)['image'])['payload']['renderer_binding']['digest']
    references = {}
    proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        with original_operator_store() as store:
            for category, policy_pin, receipt_pin in facts.evidence_references:
                _remaining(deadline)
                policy_raw = store._read('qualifications', policy_pin + '.json')
                receipt_raw = store._read('qualifications', receipt_pin + '.json')
                if hashlib.sha256(policy_raw).hexdigest() != policy_pin or hashlib.sha256(receipt_raw).hexdigest() != receipt_pin:
                    raise ValueError('marketing_independent_evidence_retained_bytes_changed')
                policy, receipt = _parse_record(policy_raw), _parse_record(receipt_raw)
                if (set(policy) != {'schema_version', 'category', 'verifier_profile_sha256', 'attester_profile_sha256',
                                    'producer_qualification_sha256', 'constraints', 'not_after'}
                        or set(receipt) != {'schema_version', 'origin', 'category', 'policy_sha256', 'verifier_profile_sha256',
                                          'attester_profile_sha256', 'producer_qualification_sha256', 'boot_id',
                                          'image_digest', 'evidence_sha256', 'not_after', 'status'}
                        or policy['schema_version'] != 'anvil.marketing-independent-os-policy.v1'
                        or receipt['schema_version'] != 'anvil.marketing-independent-os-evidence.v1'
                        or receipt['origin'] != 'independent_qa' or receipt['status'] != 'passed'
                        or receipt['policy_sha256'] != policy_pin or receipt['boot_id'] != str(facts.original.boot_id)
                        or receipt['image_digest'] != image or type(receipt['evidence_sha256']) is not str
                        or not re.fullmatch(r'[a-f0-9]{64}', receipt['evidence_sha256'])):
                    raise ValueError('marketing_original_independent_os_qualification_required')
                for document in (policy, receipt):
                    until = datetime.fromisoformat(document['not_after'].replace('Z', '+00:00'))
                    if (document['category'] != category
                            or document['verifier_profile_sha256'] != facts.verifier_profile_sha256
                            or document['attester_profile_sha256'] != facts.original.profile_sha256
                            or document['producer_qualification_sha256'] != facts.original.producer_qualification_sha256
                            or until.tzinfo is None or until < facts.original.expires_at):
                        raise ValueError('marketing_independent_qualification_profile_or_expiry_changed')
                _verify_policy(category, policy, process, observation, proc, deadline)
                references[category] = {'policy_sha256': policy_pin, 'receipt_sha256': receipt_pin}
        if set(references) != REQUIRED_EVIDENCE:
            raise ValueError('marketing_all_six_original_independent_evidence_items_required')
        process.require_live()
        _remaining(deadline)
        return parse_independent_receipt(canonical({
            'schema_version': 'anvil.marketing-attester-os-peer-receipt.v1',
            'channel_qualification_id': str(facts.channel_qualification_id),
            'producer_qualification_sha256': facts.original.producer_qualification_sha256,
            'verifier_profile_sha256': facts.verifier_profile_sha256, 'observation': observation,
            'public_ready': process._ready.model_dump(mode='json'), 'independent_evidence': references,
            'capture_accepted': False, 'run_authority': 'not_granted',
        }))
    finally:
        os.close(proc)
