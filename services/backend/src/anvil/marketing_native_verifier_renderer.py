"""Explicit private-verifier renderer successor; legacy v1/v2 bytes unchanged.

Pure source projection, never source/profile qualification or native launch.
The generic materialization/context envelope remains a file-custody protocol;
the distinct assets/entry/runtime pins select this private verifier explicitly.
"""

import hashlib
from dataclasses import dataclass

from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    _bounded_canonical,
    _digest,
    marketing_native_gate,
)
from anvil.marketing_native_records import _parse_record
from anvil.marketing_native_renderer import (
    MarketingRenderAssetsV2,
    _exact,
    project_marketing_opening_task,
)
from anvil.marketing_world_quiescence import Scope

COMMAND = ['python3', '-I', '-B', '-m', 'anvil_harbor.marketing_private_verifier']


@dataclass(frozen=True, slots=True)
class MarketingPrivateRenderAssetsV1:
    canonical_bytes: bytes


@dataclass(frozen=True, slots=True)
class MarketingPrivateProjectionV1:
    files: tuple[tuple[str, bytes], ...]
    lifecycle_plan: bytes
    private_program: bytes


def validate_private_program(value):
    fields = {'schema_version', 'scope', 'source_sha256', 'evaluation_profile_sha256', 'rubric_id', 'rubric_version',
              'scoring_contract', 'scoring_source_pins', 'criterion_weights', 'qualification_sha256'}
    _exact(value, fields)
    if value['schema_version'] != 'anvil.marketing-private-verifier-program.v1':
        raise ValueError('marketing_explicit_private_verifier_program_required')
    scope = Scope.model_validate(value['scope'])
    if scope.model_dump(mode='json') != value['scope']:
        raise ValueError('marketing_private_program_original_scope_required')
    for key in ('source_sha256', 'evaluation_profile_sha256', 'qualification_sha256'):
        pin = value[key]
        if type(pin) is not str or len(pin) != 64 or any(c not in '0123456789abcdef' for c in pin):
            raise ValueError('marketing_private_program_original_hash_required')
    # Native scorer is metadata-only here; no controller facts/answers are
    # manufactured and no candidate predicate map is made qualified.
    from anvil.marketing_capture_verifier import CRITERION_WEIGHTS, ScoringSourcePins

    # Full late binding validation additionally requires the actual trial/input
    # manifest and is performed by the producer and collector, not invented here.
    if value['scoring_contract'] != 'marketing-task2-native-23-ordinal-v1':
        raise ValueError('marketing_private_program_original_scoring_contract_required')
    ScoringSourcePins.model_validate(value['scoring_source_pins'])
    if (value['criterion_weights'] != CRITERION_WEIGHTS
            or any(type(weight) is not int for weight in value['criterion_weights'].values())
            or any(type(value[key]) is not str or not 1 <= len(value[key]) <= 200 for key in ('rubric_id', 'rubric_version'))):
        raise ValueError('marketing_private_program_original_rubric_metadata_required')
    raw = _bounded_canonical(value, 16384)
    from anvil.marketing_native_private_collect import require_private_reply_capacity

    require_private_reply_capacity(value)
    return raw


def project_private_marketing_task(request, prepared, assets):
    if type(assets) is not MarketingPrivateRenderAssetsV1:
        raise ValueError('marketing_exact_private_render_assets_required')
    value = _parse_record(assets.canonical_bytes)
    _exact(value, {'schema_version', 'opening_assets', 'private_program', 'expected_files', 'expected_effective_services'})
    if value['schema_version'] != 'anvil.marketing-private-render-assets.v1':
        raise ValueError('marketing_explicit_private_renderer_successor_required')
    program = validate_private_program(value['private_program'])
    if _bounded_canonical(prepared.get('world_stop_scope'), DOCUMENT_CAP) != _bounded_canonical(value['private_program']['scope'], DOCUMENT_CAP):
        raise ValueError('marketing_private_program_original_prepared_world_scope_required')
    original = value['opening_assets']
    base = project_marketing_opening_task(request, prepared, MarketingRenderAssetsV2(_bounded_canonical(original, DOCUMENT_CAP)))
    plan = _parse_record(base.lifecycle_plan)
    # Attester finalization time is reserved from this SAME verifier allocation
    # by the private lifecycle; profiles too small must block, never grow it.
    if plan['bounds']['verifier_seconds'] < 20:
        raise ValueError('marketing_existing_verifier_budget_cannot_fit_private_finalization')
    files = dict(base.files)
    tests = _parse_record(files['tests/docker-compose.yaml'])
    service = tests['services']['main']
    service['command'] = COMMAND
    service['volumes'].append({'type': 'bind', 'source': original['attempt_root'] + '/sealed-verifier',
                               'target': '/sealed-verifier', 'read_only': True})
    files['tests/docker-compose.yaml'] = _bounded_canonical(tests, DOCUMENT_CAP)
    files['tests/test.sh'] = b'#!/bin/sh\nset -eu\nexec python3 -I -B -m anvil_harbor.marketing_private_verifier\n'
    pins = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    services = {**plan['expected_effective_services'], 'tests': _digest(service)}
    if pins != value['expected_files'] or services != value['expected_effective_services']:
        raise ValueError('marketing_independent_private_file_and_service_pins_changed')
    plan['expected_files'], plan['expected_effective_services'] = pins, services
    return MarketingPrivateProjectionV1(tuple(sorted(files.items())), _bounded_canonical(plan, DOCUMENT_CAP), program)


def private_context_assets(records):
    """Explicit new payload only; no legacy renderer accepts this schema."""
    data = _parse_record(dict(records.records)['task'])['payload']['render_assets']
    _exact(data, {'schema_version', 'opening_assets', 'private_program', 'expected_files', 'expected_effective_services'})
    if data['schema_version'] != 'anvil.marketing-private-render-assets.v1':
        raise ValueError('marketing_private_renderer_root_assets_required')
    validate_private_program(data['private_program'])
    return {**data['opening_assets'], 'expected_files': data['expected_files'],
            'expected_effective_services': data['expected_effective_services']}, data['private_program']


def render_private_marketing_task(request, prepared):
    marketing_native_gate()
    from anvil.marketing_native_private_records import resolve_private_marketing_records

    records = resolve_private_marketing_records(request)
    payload = _parse_record(dict(records.records)['task'])['payload']
    _exact(payload, {'render_assets'})
    data = payload['render_assets']
    actual, _ = private_context_assets(records)
    # Original independent sections bind the FINAL rendered profile, not the
    # base v2 inputs used only by the pure renderer to preserve actor bytes.
    expected = {'image': actual['image'], 'runtime': actual['runtime'],
                'profile': actual['expected_effective_services'], 'recovery': actual['bounds'],
                'host': {key: actual[key] for key in ('attempt_root', 'trial_name')}}
    for name, binding in expected.items():
        if _parse_record(dict(records.records)[name])['payload'].get('renderer_binding') != binding:
            raise ValueError('marketing_independent_private_renderer_section_changed')
    return project_private_marketing_task(request, prepared, MarketingPrivateRenderAssetsV1(_bounded_canonical(data, DOCUMENT_CAP)))
