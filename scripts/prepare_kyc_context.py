"""Prepare an append-only Golden context and binding assets offline.

This deliberately has no database writer, network client or approval producer.
Run with the repository's locked backend environment. Private controls remain in
a separate 0700 output directory and never enter the actor input or policy text.
"""
import argparse
import hashlib
import json
import os
from collections import Counter
from copy import deepcopy
from datetime import date
from pathlib import Path

from anvil.db import digest as snapshot_digest
from anvil.golden_kyc_data import PRODUCTS, STATES, age, generate
from anvil.golden_kyc_engine import business_date
from anvil.golden_kyc_evaluators import CRITERIA, OPA_POLICIES, TRACE_CHECKS, ZEN_TABLES
from anvil.golden_kyc_policy import RULES
from anvil.golden_kyc_policy_delivery import MAX_PUBLIC_TEXT_V2, PolicyArtifact
from anvil.praxis_case_dataset import from_snapshots
from anvil.praxis_generic_contract import canonical, digest, load
from anvil.project_input_contract import KycInput


def checked_file(root, relative, sha256):
    path = root / relative
    if (Path(relative).is_absolute() or '..' in Path(relative).parts
            or path.resolve() != path or not path.is_file()
            or not path.is_relative_to(root)):
        raise ValueError('Canonical in-bundle regular source file required')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError('Original source artifact hash mismatch')
    return raw


def prepare_dataset(parent, assessed, charter_profile):
    """Verify the actual parent against the frozen generator, retaining lineage."""
    manifest, originals, controls = generate()
    rows = parent['applications']
    if (parent['manifest'] != manifest or len(rows) != len(originals)
            or len({row['id'] for row in rows}) != len(rows)
            or [row['snapshot'] for row in rows] != originals
            or any(row['id'] != row['snapshot']['id'] or snapshot_digest(row['snapshot']) != row['snapshot_sha256'] for row in rows)):
        raise ValueError('Exact complete selected parent population and manifest required')
    date.fromisoformat(assessed)
    if type(charter_profile) is not str or not 1 <= len(charter_profile) <= 200:
        raise ValueError('Explicit bounded charter profile required')
    public, scenarios, expectations, lineage = [], [], [], []
    impact = {'party_age_changes': [], 'document_validity_changes': [], 'initial_deadlines': [],
              'later_rounds_and_private_expectations': 'review_required', 'document_bytes_changed': False,
              'calendar_offsets_checked': list(range(11)), 'party_age_comparisons': 0, 'document_date_comparisons': 0}
    for old, control in zip(originals, controls, strict=True):
        app = deepcopy(old)
        app['revision'] += 1
        app['assessment_date'] = assessed
        app['charter_applicability'] = {'profile': charter_profile, 'reviewed': False}
        for offset in range(11):
            old_clock, new_clock = business_date(old['assessment_date'], offset), business_date(assessed, offset)
            for party in old['parties']:
                before, after = age(party['birth_date'], old_clock), age(party['birth_date'], new_clock)
                impact['party_age_comparisons'] += 1
                if before != after:
                    impact['party_age_changes'].append({'application_id': old['id'], 'party_id': party['id'], 'business_day_offset': offset, 'before': before, 'after': after})
            for doc in [*old['documents'], *control['future_documents']]:
                fields = doc['fields']
                before, after = _document_dates(fields, old_clock), _document_dates(fields, new_clock)
                impact['document_date_comparisons'] += 1
                if before != after:
                    impact['document_validity_changes'].append({'application_id': old['id'], 'document_id': doc['id'], 'business_day_offset': offset, 'before': before, 'after': after})
        impact['initial_deadlines'].append({'application_id': old['id'],
            'parent_five_day': business_date(old['assessment_date'], 5), 'child_five_day': business_date(assessed, 5),
            'parent_ten_day': business_date(old['assessment_date'], 10), 'child_ten_day': business_date(assessed, 10)})
        public.append(app)
        scenario = deepcopy(control)
        scenario['snapshot_sha256'] = snapshot_digest(app)
        expectation = {key: scenario.pop(key) for key in ('intended_decision', 'independent_expectation_review')}
        # A context change never inherits case approval, even if a parent was reviewed.
        expectation['independent_expectation_review'] = 'pending'
        expectations.append({'application_id': app['id'], 'snapshot_sha256': snapshot_digest(app), 'expectation': expectation})
        scenarios.append(scenario)
        lineage.append({'application_id': app['id'], 'parent_sha256': snapshot_digest(old), 'child_sha256': snapshot_digest(app),
                        'changed_fields': ['revision', 'assessment_date', 'charter_applicability.profile']})
    actor = {'schema_version': 'anvil.kyc-actor-input.v1', 'applications': public}
    KycInput.model_validate(actor)
    cells = Counter((a['product'], a['governing_state']) for a in public)
    if set(cells) != {(p, s) for p in PRODUCTS for s in STATES} or set(cells.values()) != {10}:
        raise ValueError('All original twenty ten-case cells must be conserved')
    report = {'schema_version': 'anvil.kyc-context-preparation.v1', 'status': 'prepared_not_registered_or_approved',
        'parent_project_id': parent['project_id'], 'parent_pack_id': parent['pack_id'],
        'parent_population_sha256': manifest['public_sha256'], 'child_population_sha256': snapshot_digest(public),
        'snapshot_hash_scheme': 'anvil.db.digest', 'bundle_hash_scheme': 'RFC8785',
        'assessment_date': assessed, 'charter_profile': charter_profile, 'case_count': len(public),
        'lineage_sha256': digest(lineage), 'private_scenarios_sha256': digest(scenarios),
        'private_expectations_sha256': digest(expectations), 'original_cases_modified': False,
        'policy_approval': 'not_granted', 'rights_review': 'pending', 'expectation_review': 'pending',
        'task_revision_bindings': 'await_corrected_export', 'paid_calls': False, 'run_authority': 'not_granted'}
    return actor, scenarios, expectations, lineage, impact, report


def _document_dates(fields, assessed):
    """Mechanical evidence only; this does not decide which document law applies."""
    current = date.fromisoformat(assessed)
    values = {}
    if 'issued_date' in fields:
        issued = date.fromisoformat(fields['issued_date'])
        values['issued_not_future'] = issued <= current
        values['within_bank_90_day_window'] = 0 <= (current - issued).days <= 90
    if 'valid_through' in fields:
        values['not_expired'] = current <= date.fromisoformat(fields['valid_through'])
    return values


def prepare_policies(root):
    """Retain exact published sources and owner decisions, without issuing reviews."""
    root = root.resolve()
    manifest = load((root / 'manifest.json').read_bytes())
    entries = manifest['files']
    if len(entries) != manifest['file_count'] or len({item['path'] for item in entries}) != len(entries):
        raise ValueError('Complete unique source inventory required')
    originals = {}
    for entry in entries:
        raw = checked_file(root, entry['path'], entry['sha256'])
        if len(raw) != entry['bytes']:
            raise ValueError('Original artifact size changed')
        originals[entry['path']] = raw
    spec = load(originals['01-published-template/kyc-v8.template-spec.json'])
    decisions = load(originals['06-policy-sources/applicability-decisions.json'])
    temporal = load(originals['05-temporal-applicability/temporal-applicability-record.json'])
    if decisions['bank_profile']['effective_as_of'] != temporal['assessment_as_of']:
        raise ValueError('Policy and simulation context dates differ')
    federal = []
    for ref in spec['execution']['federalPolicies']:
        matches = [raw for raw in originals.values() if hashlib.sha256(raw).hexdigest() == ref['content_sha256']]
        if len(matches) != 1:
            raise ValueError('Each exact template federal source must resolve once')
        federal.append(_artifact('common', ref, matches[0]))
    cells = []
    for cell in decisions['cells']:
        state = []
        for source in cell['applicable_sources']:
            for item in source['files']:
                raw = originals['06-policy-sources/' + item['path']]
                if hashlib.sha256(raw).hexdigest() != item['sha256']:
                    raise ValueError('State decision does not match original source bytes')
                # One real captured file per reference, including all 25 IL sections.
                reference = {'id': source['source_key'] + '.' + Path(item['path']).stem,
                    'version': 'capture-' + source['captured_at'], 'content_sha256': item['sha256'],
                    'publication_ref': source['source_location']}
                state.append(_artifact('state', reference, raw))
        if cell['decision'] == 'not_applicable':
            if state or not cell['not_applicable_rationale']:
                raise ValueError('Explicit not-applicable rationale and no state sources required')
        elif cell['decision'] != 'applicable' or not state:
            raise ValueError('Every policy cell needs a genuine supplied decision')
        artifacts = [*federal, *state]
        if len({a['reference']['id'] for a in artifacts}) != len(artifacts):
            raise ValueError('Every exact source reference must be unique within its policy cell')
        if sum(len(a['public_text_utf8'].encode()) for a in artifacts) > MAX_PUBLIC_TEXT_V2:
            raise ValueError('Complete original policy texts exceed the existing v2 bound')
        cells.append({'product': cell['product'], 'governing_state': cell['state'],
            'state_applicability': cell['decision'], 'not_applicable_rationale': cell['not_applicable_rationale'],
            'source_decision': deepcopy(cell), 'federal_refs': [a['reference'] for a in federal],
            'state_refs': [a['reference'] for a in state], 'artifacts': artifacts,
            'effective_from': None, 'effective_until': None, 'domain_ledger_receipt': None,
            'task_revision': None, 'status': 'prepared_requires_exact_scope_and_reviewed_interval'})
    if len(cells) != 20 or {(c['product'], c['governing_state']) for c in cells} != {(p, s) for p in PRODUCTS for s in STATES}:
        raise ValueError('Complete unique twenty-cell policy coverage required')
    return {'schema_version': 'anvil.kyc-policy-preparation.v1', 'cells': cells,
        'assessment_date': temporal['assessment_as_of'], 'bank_profile': temporal['bank_profile'],
        'source_manifest_sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest(),
        'template_sha256': digest(spec), 'retained_limitations': temporal['limitations'],
        'qualification_granted': False, 'run_authority': 'not_granted'}


def _artifact(kind, ref, raw):
    value = {'kind': kind, 'reference': ref, 'hash_scheme': 'sha256_raw_utf8',
        'artifact_utf8': raw.decode('utf-8'), 'artifact_sha256': hashlib.sha256(raw).hexdigest(),
        'public_text_pointer': None, 'public_text_utf8': raw.decode('utf-8'),
        'public_text_sha256': hashlib.sha256(raw).hexdigest()}
    return PolicyArtifact.model_validate(value).model_dump(mode='json')


def evaluator_plan():
    groups = [('rubric', CRITERIA, 'zen'), ('business', ZEN_TABLES, 'zen'),
              ('safety', OPA_POLICIES, 'opa-local'), ('trace', TRACE_CHECKS, 'builtin')]
    # Semantic mappings are reviewable preparation, not a new approved rubric.
    mapping = {
        'GB-01': [('rubric', name) for name in ('profile', 'account_structure', 'account_roles', 'state_applicability', 'state_rule_selection')]
                 + [('business', name) for name in ('account_classification', 'party_obligations', 'policy_applicability')],
        'GB-02': [('rubric', name) for name in ('identification_parties', 'identification_verification')]
                 + [('business', name) for name in ('identification_completeness', 'verification_resolution')],
        'GB-03': [('rubric', name) for name in ('evidence', 'revision_integrity')]
                 + [('trace', name) for name in ('evidence_before_claim', 'staleness')],
        'GB-04': [('rubric', name) for name in ('account_eligibility', 'account_agreements', 'account_authority',
                    'account_party_separation', 'account_exceptions', 'account_resolution', 'state_dates', 'state_instrument')]
                 + [('business', name) for name in ('product_eligibility', 'joint', 'teen', 'custodial')],
        'GB-05': [('rubric', 'screening'), ('trace', 'escalation'), ('safety', 'decision_authority')],
        'GB-06': [('rubric', 'next_action')] + [('trace', name) for name in ('targeted_followup', 'reassess_response', 'partial_handling', 'safe_idempotency')],
        'GB-07': [('rubric', 'decision'), ('business', 'recommendation_consistency'), ('trace', 'closure')],
    }
    available = {(kind, name) for kind, names, _ in groups for name in names}
    assert set(mapping) == set(RULES) and all(check in available for checks in mapping.values() for check in checks)
    return {'schema_version': 'anvil.kyc-evaluator-preparation.v1', 'configuration_count': 50,
        'requirements': [{'kind': kind, 'requirement': name, 'adapter': adapter} for kind, names, adapter in groups for name in names],
        'bank_rule_source_hashes': {name: hashlib.sha256(text.encode()).hexdigest() for name, text in RULES.items()},
        'bank_rule_to_checks': {rule: [{'kind': kind, 'requirement': name} for kind, name in checks] for rule, checks in mapping.items()},
        'semantic_mapping_review': 'pending', 'configuration_ids': None, 'runtime_binding_control_receipt': None,
        'binding_status': 'await_exact_registered_environment_and_corrected_tasks', 'run_authority': 'not_granted'}


def dataset_membership(actor):
    dates = {app['assessment_date'] for app in actor['applications']}
    if len(dates) != 1:
        raise ValueError('One explicit context assessment date required')
    rows = [{'id': app['id'], 'snapshot': app, 'snapshot_sha256': snapshot_digest(app)} for app in actor['applications']]
    version = 'context-' + next(iter(dates)).replace('-', '') + '-' + snapshot_digest(actor['applications'])[:12]
    dataset = from_snapshots('golden-kyc-applications', version, rows)
    from anvil.golden_kyc_type_index import derive

    index = derive(dataset, dataset.reference(), rows)
    return dataset.model_dump(mode='json'), load(index.canonical_body)


def write_bundle(output, values):
    output.mkdir(mode=0o700)
    files = {}
    for name, body in values.items():
        path = output / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        raw = canonical(body)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        files[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                       'classification': 'hidden_reference' if name.startswith('private/') else 'preparation'}
    with (output / 'manifest.json').open('x') as stream:
        json.dump({'schema_version': 'anvil.kyc-context-preparation-bundle.v1', 'files': files,
                   'registered': False, 'run_authority': 'not_granted'}, stream, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    (output / 'manifest.json').chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent-readback', type=Path, required=True)
    parser.add_argument('--parent-readback-sha256', required=True)
    parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    policies = prepare_policies(args.export)
    parent_raw = args.parent_readback.read_bytes()
    if hashlib.sha256(parent_raw).hexdigest() != args.parent_readback_sha256:
        raise ValueError('Exact retained parent readback pin required')
    profile = policies['bank_profile'] | {'effective_as_of': policies['assessment_date']}
    if policies['bank_profile'] != {'charter': 'national bank', 'supervisor': 'OCC', 'home_state': 'NY'}:
        raise ValueError('This preparation requires the explicit supplied national/OCC/NY context')
    profile_id = 'national-occ-ny-' + policies['assessment_date'].replace('-', '') + '-' + digest(profile)[:12]
    actor, scenarios, expectations, lineage, impact, report = prepare_dataset(
        load(parent_raw), policies['assessment_date'], profile_id)
    report['parent_readback_sha256'] = args.parent_readback_sha256
    membership, index = dataset_membership(actor)
    write_bundle(args.output, {'actor-input.json': actor, 'private/scenarios.json': scenarios,
        'private/expectations.json': expectations, 'lineage.json': lineage, 'impact.json': impact,
        'context.json': report, 'policy-cells.json': policies, 'evaluator-plan.json': evaluator_plan(),
        'dataset-manifest.json': membership, 'private/type-index.json': index})
    print(json.dumps({'status': report['status'], 'case_count': report['case_count'],
        'policy_cells': len(policies['cells']), 'run_authority': 'not_granted'}))


if __name__ == '__main__':
    main()
