"""Attester-only original four-file input sealing, not native qualification.

No caller-supplied facts, replacement files, inferred mapping or changed limits.
Partial writes consume this operation; absence of the final receipt is terminal.
"""

import hashlib
import os
import stat

from anvil.dataset_export_contract import json_object
from anvil.marketing_capture_verifier import Identity, OriginalVerifierBinding
from anvil.marketing_native_attempt import _owned, _write_at
from anvil.marketing_native_boundary import _bounded_canonical
from anvil.marketing_native_kernel_scope import _remaining
from anvil.marketing_native_records import _parse_record
from anvil.marketing_native_verifier_renderer import (
    private_context_assets,
    validate_private_program,
)
from anvil.marketing_private_grade_auth import FILES, PrivateGradeTransport
from anvil.marketing_world_quiescence import Scope
from anvil.praxis_generic_contract import canonical, digest


def seal_owned_private_input(store, root, records, facts, identity, observation, *, deadline):
    _remaining(deadline)
    if observation.origin != 'certificate_verified_private_api':
        raise ValueError('marketing_original_attester_private_tls_observation_required')
    transport = PrivateGradeTransport.model_validate_json(facts.private_grade_transport_raw)
    raw = observation.raw_body
    if not 0 < len(raw) <= transport.response_limit or hashlib.sha256(raw).hexdigest() != observation.body_sha256:
        raise ValueError('marketing_original_private_frame_bytes_required')
    value = json_object(raw)
    expected_fields = {'schema_version', 'enrollment_id', 'manifest_id', 'request_sha256', 'operation_nonce',
                       'scope', 'identity', 'files', 'file_sha256', 'sdk_binding', 'provenance',
                       'provenance_sha256', 'mapping_qualified', 'capture_accepted', 'native_qualified', 'run_authority'}
    identity = Identity.model_validate_json(canonical(identity)).model_dump(mode='json')
    scope = Scope.model_validate_json(canonical(facts.original.scope.model_dump(mode='json'))).model_dump(mode='json')
    if (set(value) != expected_fields or value['schema_version'] != 'anvil.marketing-private-grade-input-reply.v1'
            or value['enrollment_id'] != str(facts.original.enrollment_id)
            or value['request_sha256'] != facts.original.request_sha256
            or value['operation_nonce'] != facts.original.operation_nonce or value['identity'] != identity
            or value['scope'] != scope or value['mapping_qualified'] is not True
            or value['capture_accepted'] is not False or value['native_qualified'] is not False
            or value['run_authority'] != 'not_granted' or type(value['files']) is not dict
            or set(value['files']) != FILES or type(value['file_sha256']) is not dict
            or set(value['file_sha256']) != FILES):
        raise ValueError('marketing_qualified_original_private_mapping_and_frame_required')
    originals = {}
    for name, text in value['files'].items():
        if type(text) is not str:
            raise ValueError('marketing_complete_original_private_file_required')
        original = text.encode('utf-8')
        if (not 0 < len(original) <= transport.file_limits[name]
                or hashlib.sha256(original).hexdigest() != value['file_sha256'][name]):
            raise ValueError('marketing_original_private_input_hash_or_cap_changed')
        json_object(original)
        originals[name] = original
    binding = OriginalVerifierBinding.model_validate_json(canonical(value['sdk_binding'])).model_dump(mode='json')
    _, program = private_context_assets(records)
    if store._read(root, 'private-verifier-program.json') != validate_private_program(program):
        raise ValueError('marketing_original_root_private_program_changed')
    manifest = json_object(originals['verifier-input.json'])
    other_hashes = {k: v for k, v in value['file_sha256'].items() if k != 'verifier-input.json'}
    if (set(manifest) != {'schema_version', 'identity', 'scope', 'profile', 'source_sha256', 'files'}
            or manifest['schema_version'] != 'anvil.marketing-private-input.v1'
            or manifest['profile'] != 'anvil.marketing-private-verifier.v1'
            or manifest['identity'] != identity or manifest['scope'] != scope
            or manifest['files'] != other_hashes or manifest['source_sha256'] != program['source_sha256']
            or binding['identity'] != identity or binding['scope'] != scope
            or binding['input_sha256'] != value['file_sha256']['verifier-input.json']
            or binding['input_files'] != other_hashes
            or binding['input_files']['evaluation-profile.json'] != program['evaluation_profile_sha256']
            or any(binding[k] != program[k] for k in ('source_sha256', 'scoring_contract', 'scoring_source_pins',
                                                     'rubric_id', 'rubric_version', 'criterion_weights'))
            or originals['actor-output.json'] != store._read(root, 'captured-actor-output.json')):
        raise ValueError('marketing_original_sdk_program_actor_or_input_binding_changed')
    provenance_raw = value['provenance'].encode('utf-8') if type(value['provenance']) is str else b''
    if (not 0 < len(provenance_raw) <= transport.reply_metadata_limit
            or hashlib.sha256(provenance_raw).hexdigest() != value['provenance_sha256']
            or len(canonical(binding)) + len(provenance_raw) > transport.reply_metadata_limit):
        raise ValueError('marketing_original_full_private_provenance_required')
    provenance = json_object(provenance_raw)
    native = provenance.get('native_evidence')
    from anvil.marketing_private_capture_check import PrivateCaptureProfile

    capture_profile = PrivateCaptureProfile.model_validate_json(canonical(
        _parse_record(facts.profile_raw)['private_capture_profile']))
    mapping = provenance.get('mapping_control')
    if (type(mapping) is not dict or type(mapping.get('control')) is not dict
            or mapping['control'].get('status') != 'passed'
            or mapping['control'].get('source_sha256') != capture_profile.binding_source_sha256
            or mapping['control'].get('mapping_sha256') != capture_profile.ordinal_mapping_sha256
            or provenance.get('mapping_sha256') != capture_profile.ordinal_mapping_sha256
            or type(native) is not dict
            or native.get('deployment_release_sha256') != capture_profile.deployment_release_sha256):
        raise ValueError('marketing_original_private_mapping_source_and_release_profile_required')
    # Compare to the worker's OWN READY response, not reply-selected expectations.
    from anvil.marketing_capture_status import validate_response

    status = validate_response(store._read(root, 'attester-owned-grade-ready-status.json'),
                               _parse_record(store._read(root, 'attester-grade-enrollment.json')))
    if (status.state != 'ready' or str(status.manifest_id) != value['manifest_id']
            or type(native) is not dict or native.get('origin') != 'api_immutable_native_records'
            or any(native.get(k) != value[k] for k in ('enrollment_id', 'manifest_id', 'request_sha256', 'operation_nonce',
                                                     'scope', 'identity'))
            or native.get('descriptor_sha256') != digest(status.descriptor)
            or provenance.get('mapping_status') != 'qualified_source_crosswalk'
            or provenance.get('capture_accepted') is not False or provenance.get('native_qualified') is not False):
        raise ValueError('marketing_own_ready_manifest_and_actual_private_provenance_required')
    _write_at(root, 'private-verifier-seal-intent.json', _bounded_canonical({
        'schema_version': 'anvil.marketing-private-input-seal-intent.v1', 'identity': identity,
        'scope': scope, 'api_frame_sha256': observation.body_sha256,
        'file_sha256': value['file_sha256'], 'replay_permitted': False,
    }, 4096), mode=0o400)
    folder = store._dir(root, 'sealed-verifier')
    try:
        info = os.fstat(folder)
        if stat.S_IMODE(info.st_mode) != 0o700 or os.listdir(folder):
            raise ValueError('marketing_original_empty_root_private_input_directory_required')
        for name in sorted(FILES):
            _remaining(deadline)
            _write_at(folder, name, originals[name], mode=0o444)
            if store._read(folder, name) != originals[name]:
                raise RuntimeError('marketing_private_seal_write_unknown_no_replay')
        os.fchmod(folder, 0o555)
        os.fsync(folder)
        _owned(os.fstat(folder), 0, directory=True)
        _remaining(deadline)
        _write_at(root, 'private-verifier-provenance.json', provenance_raw, mode=0o400)
        _write_at(root, 'private-verifier-binding.json', canonical(binding), mode=0o400)
        receipt = _bounded_canonical({
            'schema_version': 'anvil.marketing-private-input-sealed.v1', 'identity': identity, 'scope': scope,
            'api_frame_sha256': observation.body_sha256, 'file_sha256': value['file_sha256'],
            'sdk_binding_sha256': hashlib.sha256(canonical(binding)).hexdigest(),
            'provenance_sha256': value['provenance_sha256'],
            'directory': {'device': info.st_dev, 'inode': info.st_ino, 'mode': '0555', 'uid': info.st_uid},
            'capture_accepted': False, 'native_qualified': False, 'run_authority': 'not_granted',
        }, 4096)
        _write_at(root, 'private-verifier-seal-receipt.json', receipt, mode=0o400)
        _remaining(deadline)
        return receipt
    finally:
        os.close(folder)
