from unittest.mock import Mock

from anvil.praxis_validation_report import binding_assessment, report


def test_blocked_never_claims_tasks_valid_or_fix_unnecessary():
    source = {'status': 'validation_blocked', 'valid': None, 'errors': [],
              'anvil_requirements': [{'code': 'AV_TEMPLATE_NOT_QUALIFIED', 'owner': 'anvil',
                                      'status': 'blocked', 'task_id': 'task'}]}
    result = report(source, 'request')
    assert result['valid'] is None and result['request_id'] == 'request'
    assert result['validation_report']['task_conformance'] == 'not_evaluated'
    assert result['validation_report']['task_fix_required'] is None
    item = result['validation_report']['blocking_items'][0]
    assert item['stage'] == 'template_qualification' and item['owner'] == 'anvil'
    assert item['task_change_requested'] is False and item['fix']
    assert 'validation_report' not in source


def test_private_requirement_details_are_not_copied_to_public_report():
    result = report({'status': 'validation_blocked', 'valid': None, 'anvil_requirements': [
        {'code': 'AV_UNKNOWN', 'owner': 'anvil', 'status': 'blocked',
         'private_reference': 'secret', 'message': 'private case', 'receipt': {'hidden': True}}]}, 'r')
    text = str(result['validation_report'])
    assert 'secret' not in text and 'private case' not in text and 'hidden' not in text


def test_invalid_and_valid_keep_original_verdict_and_review_gates():
    for valid, verdict, task_fix in [(False, 'invalid', True), (True, 'valid', False)]:
        gates = [{'code': 'REVIEW_DATA_RIGHTS', 'status': 'pending'}]
        result = report({'status': 'export_invalid' if not valid else 'export_valid',
                         'valid': valid, 'review_gates': gates}, 'r')
        assert result['valid'] is valid
        assert result['validation_report']['verdict'] == verdict
        assert result['validation_report']['task_fix_required'] is task_fix
        assert result['validation_report']['review_gates'] == gates
        assert result['validation_report']['run_authority'] == 'not_granted'


def test_gym_setup_waits_for_source_checks_without_touching_database():
    connection = Mock()
    result = binding_assessment(connection, 'project', {'valid': None})
    assert result['status'] == 'not_assessed' and not result['execution_setup_ready']
    connection.execute.assert_not_called()


def test_missing_gym_import_is_not_an_authoring_defect():
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = []
    result = binding_assessment(connection, 'project', {'valid': True, 'package_sha256': 'a' * 64})
    assert result['owner'] == 'anvil' and result['reason'] == 'gym_import_and_bindings_required'
    assert result['paid_dispatch_authorized'] is False
    assert connection.execute.call_args.args[1] == ('project', 'a' * 64)


def test_existing_binding_checks_are_used_without_private_details(monkeypatch):
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = [{'id': 'group'}]
    reader = Mock(return_value={'ready': False, 'gaps': [
        {'code': 'rights_pending', 'section': 'rights', 'dataset_id': 'hidden-holdout',
         'private_reference': 'hidden-reference'}]})
    monkeypatch.setattr('anvil.project_bindings.readiness', reader)
    result = binding_assessment(connection, 'project', {'valid': True, 'package_sha256': 'a' * 64})
    reader.assert_called_once_with(connection, 'project', 'group')
    assert result['status'] == 'blocked' and not result['execution_setup_ready']
    assert 'hidden' not in str(result)


def test_ready_setup_does_not_authorize_model_dispatch(monkeypatch):
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = [{'id': 'group'}]
    monkeypatch.setattr('anvil.project_bindings.readiness', lambda *a: {'ready': True, 'gaps': []})
    result = binding_assessment(connection, 'project', {'valid': True, 'package_sha256': 'a' * 64})
    assert result['execution_setup_ready'] and result['status'] == 'ready_for_run_configuration'
    assert result['paid_dispatch_authorized'] is False


def test_http_response_retains_request_id_exact_blocker_and_unknown_verdict(monkeypatch):
    from contextlib import contextmanager
    from uuid import uuid4

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from anvil.praxis_generic_api import routes

    connection = Mock()

    @contextmanager
    def access(request, project, *args):
        request.state.request_id = 'correlation-id'
        yield connection, uuid4(), ['admin']

    monkeypatch.setenv('ANVIL_PRAXIS_GENERIC_EXPORT_ENABLED', 'true')
    monkeypatch.setattr('anvil.praxis_generic_api.validate', lambda *args: (
        {'valid': None, 'status': 'validation_blocked', 'errors': [],
         'package_sha256': 'a' * 64,
         'anvil_requirements': [{'code': 'AV_TEMPLATE_NOT_QUALIFIED', 'owner': 'anvil',
                                 'status': 'blocked', 'task_id': 'task',
                                 'qualification': {'status': 'blocked',
                                                   'reason_codes': ['template_source_changed']}}]}, {}))
    app = FastAPI()
    app.include_router(routes(access, None, lambda d, r: {'data': d, 'meta': {'request_id': r.state.request_id}}, None))
    response = TestClient(app).post('/generic/validate?project=' + str(uuid4()),
                                    content=b'opaque-test-package', headers={'Content-Type': 'application/zip'})
    assert response.status_code == 409
    body = response.json()
    assert body['meta']['request_id'] == body['data']['request_id'] == 'correlation-id'
    report = body['data']['validation_report']
    assert report['verdict'] == 'blocked' and report['task_fix_required'] is None
    assert report['blocking_items'][0]['qualification']['reason_codes'] == ['template_source_changed']
    assert report['anvil_setup']['execution_setup_ready'] is False
    connection.execute.assert_not_called()


def test_registry_explains_source_changed_without_rehashing_twice(monkeypatch):
    import json
    from pathlib import Path

    from anvil import praxis_template_registry as registry
    from anvil.praxis_capabilities import catalogue
    from anvil.praxis_generic_contract import TemplateRef, digest

    root = Path(__file__).resolve().parents[4]
    spec = json.loads((root / 'fixtures/praxis-generic-v1/template-spec.json').read_bytes())
    row = {'id': 'stored', 'template_key': spec['template_id'], 'version': spec['version'],
           'spec': spec, 'spec_sha256': digest(spec),
           'part_hashes': {k: digest(spec[k]) for k in ('execution', 'authoring', 'skills')},
           'catalogue_sha256': catalogue(spec['execution']['catalogue_version'])['sha256']}
    receipt = {'source_sha256': 'a' * 64}
    qualification = {'id': 'old', 'status': 'qualified', 'receipt': receipt,
                     'receipt_sha256': digest(receipt)}
    connection = Mock()
    connection.execute.return_value.fetchone.side_effect = [row, qualification, None]
    source = Mock(return_value='b' * 64)
    monkeypatch.setattr(registry, 'source_hash', source)
    found = registry.lookup(connection, 'project', TemplateRef(id=spec['template_id'],
                            version=spec['version'], sha256=digest(spec)))
    assert found['integrity'] is True and found['qualified'] is False
    assert found['qualification_diagnostics']['reason_codes'] == ['template_source_changed']
    source.assert_called_once_with()


def test_shared_template_blocker_reports_each_task_but_reads_registry_once(monkeypatch):
    import hashlib
    import json
    from copy import deepcopy
    from pathlib import Path
    from uuid import uuid4

    from anvil.golden_kyc_v7_export import validate_registered

    root = Path(__file__).resolve().parents[4]
    source = json.loads((root / 'fixtures/praxis-generic-v1/single-agent/praxis-export.json').read_bytes())
    entry = source['tasks'][0]
    source['tasks'] = []
    for product in ('individual', 'adult_joint', 'teen_joint', 'custodial'):
        task = deepcopy(entry)
        task.update(task_id=str(uuid4()), revision_id=str(uuid4()),
                    case_selector={'field': 'product', 'value': product})
        source['tasks'].append(task)
    reader = Mock(return_value={'integrity': True, 'qualified': False, 'row': {'spec': {}},
                               'qualification_diagnostics': {'status': 'blocked',
                                                            'reason_codes': ['template_source_changed']}})
    monkeypatch.setattr('anvil.golden_kyc_v7_export.product_template', lambda spec: True)
    result, _ = validate_registered(b'original-zip-identity', {}, source, reader)
    assert result['valid'] is None and result['validation_coverage'] == 'incomplete'
    assert len(result['anvil_requirements']) == 4
    assert {item['task_id'] for item in result['anvil_requirements']} == {t['task_id'] for t in source['tasks']}
    assert result['package_sha256'] == hashlib.sha256(b'original-zip-identity').hexdigest()
    reader.assert_called_once()
