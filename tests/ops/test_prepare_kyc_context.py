"""Offline context/lineage/privacy controls; synthetic policy text, no approvals."""
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from anvil.db import digest as snapshot_digest
from anvil.golden_kyc_data import PRODUCTS, STATES, generate
from anvil.golden_kyc_engine import advance, execute, initial
from anvil.golden_kyc_policy_chunks import build, lookup
from anvil.praxis_generic_contract import canonical

spec = importlib.util.spec_from_file_location('prepare_context', Path(__file__).resolve().parents[2] / 'scripts/prepare_kyc_context.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
check_spec = importlib.util.spec_from_file_location('check_context', Path(__file__).resolve().parents[2] / 'scripts/check_kyc_context_bundle.py')
checker = importlib.util.module_from_spec(check_spec)
check_spec.loader.exec_module(checker)


def parent():
    manifest, apps, _ = generate()
    return {'project_id': 'a7454c18-602e-4907-bdd9-277067c36233',
            'pack_id': '7e17aa6b-4a23-4abc-a28f-f4ba97186c2d', 'manifest': manifest,
            'applications': [{'id': a['id'], 'snapshot': a, 'snapshot_sha256': snapshot_digest(a)} for a in apps]}


def prepared():
    return module.prepare_dataset(parent(), '2026-11-12', 'national-occ-ny-test')


def test_complete_successor_is_deterministic_and_does_not_rewrite_parent():
    original = parent()
    frozen = deepcopy(original)
    result = module.prepare_dataset(original, '2026-11-12', 'national-occ-ny-test')
    assert result == prepared() and original == frozen
    actor, scenarios, expectations, lineage, impact, report = result
    assert len(actor['applications']) == len(scenarios) == len(expectations) == len(lineage) == 200
    assert len({(a['product'], a['governing_state']) for a in actor['applications']}) == 20
    for row, child, relation in zip(original['applications'], actor['applications'], lineage, strict=True):
        expected = deepcopy(row['snapshot'])
        expected.update(revision=2, assessment_date='2026-11-12', charter_applicability={'profile': 'national-occ-ny-test', 'reviewed': False})
        assert child == expected
        assert relation['parent_sha256'] == row['snapshot_sha256']
        assert relation['child_sha256'] == snapshot_digest(child)
    assert not impact['party_age_changes'] and not impact['document_validity_changes']
    assert impact['party_age_comparisons'] == 350 * 11
    assert impact['initial_deadlines'][0]['child_ten_day'] == '2026-11-26'
    assert report['status'] == 'prepared_not_registered_or_approved' and report['run_authority'] == 'not_granted'


@pytest.mark.parametrize('mutation', ['omit', 'duplicate', 'reorder', 'tamper', 'private_hash'])
def test_parent_membership_and_content_must_match_exact_originals(mutation):
    data = parent()
    if mutation == 'omit':
        data['applications'].pop()
    elif mutation == 'duplicate':
        data['applications'][-1] = data['applications'][0]
    elif mutation == 'reorder':
        data['applications'].reverse()
    elif mutation == 'private_hash':
        data['manifest']['private_sha256'] = 'f' * 64
    else:
        data['applications'][0]['snapshot']['purpose'] = 'changed'
        data['applications'][0]['snapshot_sha256'] = snapshot_digest(data['applications'][0]['snapshot'])
    with pytest.raises(ValueError, match='parent population'):
        module.prepare_dataset(data, '2026-11-12', 'national-occ-ny-test')


def test_private_controls_and_future_documents_survive_without_approval_leakage():
    actor, scenarios, expectations, *_ = prepared()
    _, _, original_controls = generate()
    for app, scenario, expected, original in zip(actor['applications'], scenarios, expectations, original_controls, strict=True):
        original = deepcopy(original)
        original.pop('intended_decision')
        original.pop('independent_expectation_review')
        original['snapshot_sha256'] = snapshot_digest(app)
        assert scenario == original
        assert expected['expectation']['independent_expectation_review'] == 'pending'
    public = canonical(actor)
    for key in ('intended_decision', 'independent_expectation_review', 'future_documents', 'safety_exposure', 'response_mode'):
        assert key.encode() not in public


def test_all_200_simulator_resets_and_every_withheld_response_preserve_scenario_behavior():
    actor, scenarios, *_ = prepared()
    responses = 0
    for app, scenario in zip(actor['applications'], scenarios, strict=True):
        state = initial(app)
        assert state['clock'] == '2026-11-12' and state['revision'] == 2 and state['deadline'] == '2026-11-26'
        assert execute(state, scenario, 'application.read', {})['revision'] == 2
        if not scenario['future_documents']:
            continue
        doc = scenario['future_documents'][0]
        request = execute(state, scenario, 'information.request', {'party_id': doc['party_id'], 'items': [doc['kind']], 'reason': 'Resolve missing synthetic evidence'})
        advance(state, scenario, business_days=5)
        response = state['requests'][request['id']]['response']
        if scenario['response_mode'] == 'none':
            assert response is None
        else:
            assert response['status'] == scenario['response_mode']
            assert response['received_date'] == '2026-11-19'
            assert bool(response['documents']) is (scenario['response_mode'] == 'complete')
        responses += 1
    assert responses == 100


def policy_export(tmp_path):
    root = tmp_path / 'export'
    root.mkdir()
    originals = {}
    def add(name, body):
        raw = body if isinstance(body, bytes) else canonical(body)
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        originals[name] = raw
        return __import__('hashlib').sha256(raw).hexdigest()
    refs = []
    for index in range(2):
        sha = add(f'06-policy-sources/federal-{index}.txt', f'Synthetic federal source {index}'.encode())
        refs.append({'id': f'federal-{index}', 'version': 'synthetic', 'content_sha256': sha, 'publication_ref': 'https://example.invalid/federal'})
    cells = []
    for state in STATES:
        relative = f'sources/{state}.txt'
        sha = add('06-policy-sources/' + relative, ('Synthetic state text ' + state).encode())
        source = {'source_key': state + '-TEST', 'captured_at': '2026-11-18', 'source_location': 'https://example.invalid/state',
                  'files': [{'path': relative, 'sha256': sha}]}
        for product in PRODUCTS:
            cells.append({'product': product, 'state': state, 'decision': 'not_applicable' if product == 'individual' else 'applicable',
                'not_applicable_rationale': 'Synthetic test decision only' if product == 'individual' else None,
                'applicable_sources': [] if product == 'individual' else [source]})
    add('01-published-template/kyc-v8.template-spec.json', {'execution': {'federalPolicies': refs}})
    add('06-policy-sources/applicability-decisions.json', {'bank_profile': {'effective_as_of': '2026-11-12'}, 'cells': cells})
    add('05-temporal-applicability/temporal-applicability-record.json', {'assessment_as_of': '2026-11-12', 'bank_profile': {}, 'limitations': ['Synthetic sources only']})
    manifest = {'file_count': len(originals), 'files': [{'path': name, 'sha256': __import__('hashlib').sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in originals.items()]}
    (root / 'manifest.json').write_bytes(canonical(manifest))
    return root


def test_all_20_policies_preserve_original_bytes_and_do_not_create_scope_or_reviews(tmp_path):
    body = module.prepare_policies(policy_export(tmp_path))
    assert len(body['cells']) == 20 and body['qualification_granted'] is False
    for cell in body['cells']:
        assert len(cell['federal_refs']) == 2
        assert bool(cell['state_refs']) is (cell['product'] != 'individual')
        assert cell['effective_from'] is cell['effective_until'] is cell['domain_ledger_receipt'] is cell['task_revision'] is None
        for artifact in cell['artifacts']:
            assert artifact['artifact_utf8'] == artifact['public_text_utf8']
        public = {'schema_version': 'anvil.bound-application-policy.v2', 'application_id': 'synthetic',
            'bound_common_rules': [a['reference'] | {'text': a['public_text_utf8'], 'public_text_sha256': a['public_text_sha256']} for a in cell['artifacts'] if a['kind'] == 'common'],
            'bound_state_rules': [a['reference'] | {'text': a['public_text_utf8'], 'public_text_sha256': a['public_text_sha256']} for a in cell['artifacts'] if a['kind'] == 'state']}
        first, documents = build(public)
        assert first and documents
        for key in documents:
            assert lookup(documents, key) == documents[key]


@pytest.mark.parametrize('mutation', ['artifact', 'traversal', 'duplicate_cell', 'empty_applicable', 'false_not_applicable'])
def test_policy_preparation_rejects_tampering_and_ambiguous_coverage(tmp_path, mutation):
    root = policy_export(tmp_path)
    if mutation == 'artifact':
        (root / '06-policy-sources/sources/CA.txt').write_text('tampered')
    elif mutation == 'traversal':
        manifest = json.loads((root / 'manifest.json').read_text())
        manifest['files'][0]['path'] = '../outside'
        (root / 'manifest.json').write_bytes(canonical(manifest))
    else:
        path = root / '06-policy-sources/applicability-decisions.json'
        value = json.loads(path.read_text())
        if mutation == 'duplicate_cell':
            value['cells'][-1] = value['cells'][0]
        elif mutation == 'empty_applicable':
            value['cells'][1]['applicable_sources'] = []
        else:
            value['cells'][1]['decision'] = 'not_applicable'
        path.write_bytes(canonical(value))
        manifest = json.loads((root / 'manifest.json').read_text())
        for entry in manifest['files']:
            if entry['path'] == str(path.relative_to(root)):
                entry.update(sha256=__import__('hashlib').sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
        (root / 'manifest.json').write_bytes(canonical(manifest))
    with pytest.raises(ValueError):
        module.prepare_policies(root)


def test_bundle_is_private_immutable_and_never_registered(tmp_path):
    output = tmp_path / 'bundle'
    module.write_bundle(output, {'actor-input.json': {'synthetic': True}, 'private/expectations.json': {'hidden': 'synthetic'}})
    manifest = json.loads((output / 'manifest.json').read_bytes())
    assert output.stat().st_mode & 0o777 == 0o700
    assert manifest['files']['private/expectations.json']['classification'] == 'hidden_reference'
    assert manifest['registered'] is False
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in output.rglob('*') if p.is_file())
    with pytest.raises(FileExistsError):
        module.write_bundle(output, {})


def test_evaluator_plan_is_complete_but_not_a_placeholder_approval():
    plan = module.evaluator_plan()
    assert len(plan['requirements']) == plan['configuration_count'] == 50
    assert len({(r['kind'], r['requirement']) for r in plan['requirements']}) == 50
    assert len(plan['bank_rule_source_hashes']) == 7
    assert set(plan['bank_rule_to_checks']) == set(plan['bank_rule_source_hashes'])
    required = {(r['kind'], r['requirement']) for r in plan['requirements']}
    assert all((r['kind'], r['requirement']) in required for checks in plan['bank_rule_to_checks'].values() for r in checks)
    assert plan['configuration_ids'] is plan['runtime_binding_control_receipt'] is None
    assert plan['semantic_mapping_review'] == 'pending'
    assert plan['run_authority'] == 'not_granted'


def test_prepared_membership_routes_all_cases_without_inserting_optional_defaults():
    actor, *_ = prepared()
    before = deepcopy(actor)
    membership, index = module.dataset_membership(actor)
    assert actor == before
    assert membership['case_count'] == index['input_count'] == 200
    assert index['supported_type_counts'] == dict.fromkeys(PRODUCTS, 50)
    assert index['blocked_type_count'] == 0 and index['run_authority'] == 'not_granted'
    actor['applications'][0]['assessment_date'] = '2026-11-13'
    with pytest.raises(ValueError, match='One explicit'):
        module.dataset_membership(actor)


def test_complete_offline_bundle_checks_arrays_original_hashes_and_pending_grades(tmp_path):
    actor, scenarios, expectations, lineage, impact, context = prepared()
    membership, index = module.dataset_membership(actor)
    output = tmp_path / 'complete'
    module.write_bundle(output, {'actor-input.json': actor, 'private/scenarios.json': scenarios,
        'private/expectations.json': expectations, 'lineage.json': lineage, 'impact.json': impact,
        'context.json': context, 'policy-cells.json': module.prepare_policies(policy_export(tmp_path)),
        'evaluator-plan.json': module.evaluator_plan(), 'dataset-manifest.json': membership, 'private/type-index.json': index})
    checked = checker.verify(output)
    assert checked['case_resets'] == checked['pending_expectations_remain_unscored'] == 200
    assert checked['withheld_followups'] == 100 and checked['complete_policy_cells'] == 20
    assert checked['model_calls'] == checked['database_writes'] == 0
    with (output / 'private/expectations.json').open('ab') as stream:
        stream.write(b' ')
    with pytest.raises(ValueError, match='hash or length'):
        checker.verify(output)


def normalization_bundle(tmp_path):
    actor, scenarios, expectations, lineage, impact, context = prepared()
    membership, index = module.dataset_membership(actor)
    output = tmp_path / 'normalization-source'
    module.write_bundle(output, {'actor-input.json': actor, 'private/scenarios.json': scenarios,
        'private/expectations.json': expectations, 'lineage.json': lineage, 'impact.json': impact,
        'context.json': context, 'policy-cells.json': module.prepare_policies(policy_export(tmp_path)),
        'evaluator-plan.json': module.evaluator_plan(), 'dataset-manifest.json': membership, 'private/type-index.json': index})
    return output


def normalization_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'scripts'))
    import normalize_kyc_context

    return normalize_kyc_context


def test_wire_normalization_appends_version_preserves_controls_and_never_approves(tmp_path, monkeypatch):
    import hashlib

    from anvil.project_input_contract import INPUT

    source = normalization_bundle(tmp_path)
    original = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob('*') if p.is_file()}
    normalizer = normalization_module(monkeypatch)
    output = tmp_path / 'normalized'
    result = normalizer.normalize(source, hashlib.sha256(original['manifest.json']).hexdigest(), output)
    actor = json.loads((output / 'actor-input.json').read_bytes())
    assert actor == INPUT.validate_python(actor).model_dump(mode='json')
    assert result['added_quality_fields'] == 70
    assert result['acceptance']['case_resets'] == result['acceptance']['pending_expectations_remain_unscored'] == 200
    assert result['run_authority'] == 'not_granted'
    assert original == {str(p.relative_to(source)): p.read_bytes() for p in source.rglob('*') if p.is_file()}
    old_controls = json.loads(original['private/scenarios.json'])
    new_controls = json.loads((output / 'private/scenarios.json').read_bytes())
    for app, old, new in zip(actor['applications'], old_controls, new_controls, strict=True):
        assert new == old | {'snapshot_sha256': snapshot_digest(app)}
    assert (output / 'policy-cells.json').read_bytes() == original['policy-cells.json']
    assert json.loads((output / 'context.json').read_bytes())['rights_review'] == 'pending'


def test_normalization_rejects_unpinned_source_before_creating_output(tmp_path, monkeypatch):
    source = normalization_bundle(tmp_path)
    output = tmp_path / 'rejected'
    with pytest.raises(ValueError, match='Exact original'):
        normalization_module(monkeypatch).normalize(source, '0' * 64, output)
    assert not output.exists()


def test_normalization_rechecks_captured_source_after_acceptance(tmp_path, monkeypatch):
    import hashlib

    source = normalization_bundle(tmp_path)
    normalizer = normalization_module(monkeypatch)
    pinned = hashlib.sha256((source / 'manifest.json').read_bytes()).hexdigest()
    real_verify = normalizer.verify

    def swap_after_verify(root):
        result = real_verify(root)
        (root / 'policy-cells.json').write_bytes(b'{}')
        return result

    monkeypatch.setattr(normalizer, 'verify', swap_after_verify)
    output = tmp_path / 'rejected'
    with pytest.raises(ValueError, match='Captured source artifact'):
        normalizer.normalize(source, pinned, output)
    assert not output.exists()


def test_normalization_rejects_output_inside_original_bundle(tmp_path, monkeypatch):
    source = normalization_bundle(tmp_path)
    with pytest.raises(ValueError, match='outside'):
        normalization_module(monkeypatch).normalize(source, '0' * 64, source / 'child')
    assert not (source / 'child').exists()


def test_registration_handoff_omits_expected_answers_and_rechecks_exact_bytes(tmp_path, monkeypatch):
    import hashlib

    from anvil.praxis_generic_contract import canonical

    source = normalization_bundle(tmp_path)
    normalizer = normalization_module(monkeypatch)
    normalized = tmp_path / 'normalized-registration'
    normalizer.normalize(source, hashlib.sha256((source / 'manifest.json').read_bytes()).hexdigest(), normalized)
    import register_kyc_context as registrar

    pin = hashlib.sha256((normalized / 'manifest.json').read_bytes()).hexdigest()
    raw = registrar.registration_input(normalized, pin)
    files = registrar.read_registration_input(raw, pin)
    assert set(files) == registrar.REGISTRATION_FILES
    assert 'private/expectations.json' not in files
    assert b'independent_expectation_review' not in canonical(files)
    body = json.loads(raw)
    body['files']['actor-input.json']['applications'][0]['purpose'] = 'tampered'
    with pytest.raises(ValueError, match='differs from pinned'):
        registrar.read_registration_input(canonical(body), pin)
    body = json.loads(raw)
    body['files']['private/expectations.json'] = []
    with pytest.raises(ValueError, match='non-expectation'):
        registrar.read_registration_input(canonical(body), pin)


def test_normalization_rejects_serializer_changes_to_existing_facts(tmp_path, monkeypatch):
    import hashlib

    from anvil.project_input_contract import INPUT

    source = normalization_bundle(tmp_path)
    normalizer = normalization_module(monkeypatch)
    real_validate = INPUT.validate_python

    class ChangedSerializer:
        def model_dump(self, **kwargs):
            body = real_validate(json.loads((source / 'actor-input.json').read_bytes())).model_dump(**kwargs)
            body['applications'][0]['purpose'] = 'Unapproved changed purpose'
            return body

    class BadInput:
        @staticmethod
        def validate_python(value):
            return ChangedSerializer()

    monkeypatch.setattr(normalizer, 'INPUT', BadInput())
    output = tmp_path / 'rejected'
    with pytest.raises(ValueError, match='add only'):
        normalizer.normalize(source, hashlib.sha256((source / 'manifest.json').read_bytes()).hexdigest(), output)
    assert not output.exists()
