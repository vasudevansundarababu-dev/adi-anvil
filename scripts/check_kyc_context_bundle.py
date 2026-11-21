"""No-model offline acceptance of a prepared Gym context; never admission."""
import argparse
import hashlib
import json
from pathlib import Path

from anvil.db import digest as snapshot_digest
from anvil.golden_kyc_engine import advance, execute, initial
from anvil.golden_kyc_evaluators import CRITERIA, evaluate
from anvil.golden_kyc_policy_chunks import CHUNK_SCHEMA, build, lookup
from anvil.golden_kyc_type_index import derive
from anvil.praxis_case_dataset import CaseDataset
from anvil.praxis_generic_contract import canonical, load
from anvil.project_input_contract import KycInput


def verify(root):
    if not __debug__:
        raise ValueError('Run acceptance without Python assertion optimization')
    root = root.resolve()
    manifest = load((root / 'manifest.json').read_bytes())
    assert manifest['registered'] is False and manifest['run_authority'] == 'not_granted'
    files = {}
    for name, expected in manifest['files'].items():
        path = root / name
        if (Path(name).is_absolute() or '..' in Path(name).parts or path.resolve() != path
                or not path.is_relative_to(root) or not path.is_file()):
            raise ValueError('Exact in-bundle regular artifacts required')
        raw = path.read_bytes()
        if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
            raise ValueError('Prepared artifact hash or length changed')
        value = json.loads(raw)
        if canonical(value) != raw:
            raise ValueError('Complete canonical artifact required')
        files[name] = value
    # Validate without serializing defaults into the immutable original records.
    KycInput.model_validate(files['actor-input.json'])
    apps = files['actor-input.json']['applications']
    scenarios, expectations = files['private/scenarios.json'], files['private/expectations.json']
    assert len(apps) == len(scenarios) == len(expectations) == 200
    dataset = CaseDataset.model_validate(files['dataset-manifest.json'])
    assert {c.id for c in dataset.cases} == {a['id'] for a in apps}
    rows = [{'id': app['id'], 'snapshot': app, 'snapshot_sha256': snapshot_digest(app)} for app in apps]
    assert load(derive(dataset, dataset.reference(), rows).canonical_body) == files['private/type-index.json']
    assert snapshot_digest(apps) == files['context.json']['child_population_sha256']
    resets, followups, unscored = 0, 0, 0
    for app, scenario, expected in zip(apps, scenarios, expectations, strict=True):
        assert app['id'] == scenario['application_id'] == expected['application_id']
        assert snapshot_digest(app) == scenario['snapshot_sha256'] == expected['snapshot_sha256']
        assert expected['expectation']['independent_expectation_review'] == 'pending'
        state = initial(app)
        execute(state, scenario, 'application.read', {})
        resets += 1
        if scenario['future_documents']:
            doc = scenario['future_documents'][0]
            request = execute(state, scenario, 'information.request', {'party_id': doc['party_id'],
                'items': [doc['kind']], 'reason': 'Offline synthetic follow-up control'})
            advance(state, scenario, business_days=5)
            response = state['requests'][request['id']]['response']
            if scenario['response_mode'] == 'none':
                assert response is None
            else:
                assert response['status'] == scenario['response_mode']
            followups += 1
        grade = evaluate(state, expected['expectation'], dict.fromkeys(CRITERIA, True))
        assert grade['overall_result'] == 'not_evaluated' and grade['rubric_score']['earned_points'] == 0
        unscored += 1
    policy_cells, chunks = 0, 0
    for cell in files['policy-cells.json']['cells']:
        assert cell['domain_ledger_receipt'] is cell['task_revision'] is cell['effective_from'] is cell['effective_until'] is None
        rules = [{'id': a['reference']['id'], 'version': a['reference']['version'],
            'content_sha256': a['reference']['content_sha256'], 'text': a['public_text_utf8'],
            'public_text_sha256': a['public_text_sha256'], 'artifact_sha256': a['artifact_sha256'],
            'hash_scheme': a['hash_scheme']} for a in cell['artifacts']]
        body = {'schema_version': 'anvil.bound-application-policy.v2', 'application_id': 'offline-' + cell['product'] + '-' + cell['governing_state'],
                'bound_common_rules': rules[:2], 'bound_state_rules': rules[2:]}
        public, documents = build(body)
        assert len(canonical(public)) <= 8192
        for ordinal, artifact in enumerate(cell['artifacts']):
            parts = [d for d in documents.values() if d.get('schema_version') == CHUNK_SCHEMA and d['source_ordinal'] == ordinal]
            parts.sort(key=lambda d: d['utf8_byte_start'])
            rebuilt = b''.join(lookup(documents, part['document_id'])['text'].encode() for part in parts)
            assert rebuilt == artifact['public_text_utf8'].encode()
            assert hashlib.sha256(rebuilt).hexdigest() == artifact['public_text_sha256']
            chunks += len(parts)
        assert all(len(canonical(doc)) <= 8192 for doc in documents.values())
        policy_cells += 1
    assert policy_cells == 20
    return {'schema_version': 'anvil.kyc-context-offline-acceptance.v1', 'case_resets': resets,
        'withheld_followups': followups, 'pending_expectations_remain_unscored': unscored,
        'complete_policy_cells': policy_cells, 'policy_chunks_reconstructed': chunks,
        'model_calls': 0, 'database_writes': 0, 'run_authority': 'not_granted',
        'scope': 'offline_mechanical_and_source_packaging_only', 'manifest_sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    print(json.dumps(verify(parser.parse_args().bundle), sort_keys=True))
