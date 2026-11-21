"""Append a wire-normalized draft context; never edit its original bundle or approvals."""
import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from check_kyc_context_bundle import verify
from prepare_kyc_context import dataset_membership, write_bundle

from anvil.db import digest as snapshot_digest
from anvil.praxis_generic_contract import canonical, digest, load
from anvil.project_input_contract import INPUT


def normalize(source, expected_manifest_sha256, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.is_relative_to(source):
        raise ValueError('Output must be outside the immutable source bundle')
    original_manifest = (source / 'manifest.json').read_bytes()
    if hashlib.sha256(original_manifest).hexdigest() != expected_manifest_sha256:
        raise ValueError('Exact original preparation manifest required')
    verify(source)
    manifest = load(original_manifest)
    values = {}
    for name, expected in manifest['files'].items():
        path = source / name
        if path.resolve() != path or not path.is_relative_to(source) or not path.is_file():
            raise ValueError('Exact in-bundle artifact required')
        raw = path.read_bytes()
        if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
            raise ValueError('Captured source artifact hash or length changed')
        value = json.loads(raw)
        if canonical(value) != raw:
            raise ValueError('Canonical source artifact required')
        values[name] = value
    original = values['actor-input.json']
    actor = INPUT.validate_python(original).model_dump(mode='json')
    reversible = deepcopy(actor)
    additions = 0
    for old, new in zip(original['applications'], reversible['applications'], strict=True):
        for old_doc, new_doc in zip(old['documents'], new['documents'], strict=True):
            if 'quality' not in old_doc:
                if new_doc.get('quality') != 'unspecified':
                    raise ValueError('Only explicit unspecified document quality is permitted')
                del new_doc['quality']
                additions += 1
    if reversible != original or not additions:
        raise ValueError('Normalization must add only missing unspecified document quality')
    scenarios = values['private/scenarios.json']
    expectations = values['private/expectations.json']
    lineage = values['lineage.json']
    for old, new, scenario, expected, record in zip(
        original['applications'], actor['applications'], scenarios, expectations, lineage, strict=True
    ):
        old_sha, new_sha = snapshot_digest(old), snapshot_digest(new)
        if (record['application_id'] != old['id'] or record['child_sha256'] != old_sha
                or expected['expectation']['independent_expectation_review'] != 'pending'):
            raise ValueError('Original lineage and pending expectations must remain explicit')
        scenario['snapshot_sha256'] = expected['snapshot_sha256'] = record['child_sha256'] = new_sha
        if new_sha != old_sha:
            record['changed_fields'].append('documents[*].quality')
    context = values['context.json']
    if (context['rights_review'] != 'pending' or context['policy_approval'] != 'not_granted'
            or context['expectation_review'] != 'pending' or context['run_authority'] != 'not_granted'):
        raise ValueError('Normalization cannot inherit or create review authority')
    context.update(child_population_sha256=snapshot_digest(actor['applications']),
                   lineage_sha256=digest(lineage), private_scenarios_sha256=digest(scenarios),
                   private_expectations_sha256=digest(expectations),
                   normalized_from_manifest_sha256=expected_manifest_sha256,
                   task_revision_bindings='await_exact_imported_revisions')
    values['impact.json']['wire_normalization'] = {
        'source_manifest_sha256': expected_manifest_sha256,
        'original_actor_sha256': snapshot_digest(original),
        'normalized_actor_sha256': snapshot_digest(actor),
        'added_unspecified_document_quality_fields': additions,
        'document_bytes_changed': False, 'review_approval': False,
    }
    values['actor-input.json'] = actor
    values['dataset-manifest.json'], values['private/type-index.json'] = dataset_membership(actor)
    values['evaluator-plan.json']['binding_status'] = 'await_exact_registered_environment_and_imported_tasks'
    write_bundle(output, values)
    acceptance = verify(output)
    return {'status': 'normalized_draft_not_registered_or_approved',
            'manifest_sha256': hashlib.sha256((output / 'manifest.json').read_bytes()).hexdigest(),
            'population_sha256': context['child_population_sha256'],
            'added_quality_fields': additions, 'acceptance': acceptance, 'run_authority': 'not_granted'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(normalize(args.source, args.source_manifest_sha256, args.output), sort_keys=True))
