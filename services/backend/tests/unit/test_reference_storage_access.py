from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from anvil.benchmark_run_api import routes


def client(roles=('admin',), old=None):
    connection = Mock()
    project, user, assignment = uuid4(), uuid4(), uuid4()
    expires = datetime.now(timezone.utc) + timedelta(hours=8)

    def execute(sql, params=()):
        result = Mock()
        if sql.startswith('SELECT id,expires_at'):
            result.fetchone.return_value = old
        elif sql.startswith('INSERT INTO anvil.benchmark_private_assignments'):
            assert params[1:4] == (project, user, user)
            assert params[-1] == timedelta(hours=8)
            result.fetchone.return_value = {'id': assignment, 'expires_at': expires}
        elif sql.startswith('SELECT id FROM anvil.benchmark_private_assignments'):
            result.fetchone.return_value = old
        else:
            result.fetchone.return_value = {'allowed': False}
        return result

    connection.execute.side_effect = execute

    @contextmanager
    def context(request, actual_project):
        assert actual_project == project
        request.state.request_id = 'storage-access-test-request'
        yield connection, user, set(roles)

    app = FastAPI()
    app.include_router(routes(context, lambda data, request: {'data': data},
                              lambda c, p, u, request, body, fn: fn()))
    return TestClient(app), connection, project, user, assignment


CONSENT = {'confirmation': 'allow_my_protected_reference_import_for_8_hours'}


def test_explicit_consent_grants_only_real_admin_self_source_scope_and_audits():
    api, c, project, user, assignment = client()
    response = api.post(f'/api/v1/projects/{project}/workspace/benchmark/reference-storage-access', json=CONSENT)
    assert response.status_code == 200
    result = response.json()['data']
    assert result['assignment_id'] == str(assignment)
    assert result['scope'] == 'source_review'
    assert not result['paid_calls'] and not result['review_approval']
    calls = c.execute.call_args_list
    inserts = [x for x in calls if x.args[0].startswith('INSERT INTO anvil.benchmark_private_assignments')]
    assert len(inserts) == 1 and "'source_review',NULL" in inserts[0].args[0]
    audit = [x for x in calls if x.args[0].startswith('INSERT INTO anvil.audit_events')]
    assert len(audit) == 1 and audit[0].args[1][1] == user


@pytest.mark.parametrize('roles', [('rl-engineer',), ('product-owner',), ('sme-reviewer',), ()])
def test_non_admin_cannot_grant_or_inspect(roles):
    api, c, project, _, _ = client(roles)
    path = f'/api/v1/projects/{project}/workspace/benchmark/reference-storage-access'
    assert api.post(path, json=CONSENT).status_code == 403
    assert api.get(path).status_code == 403
    c.execute.assert_not_called()


@pytest.mark.parametrize('body', [{}, {'confirmation': 'yes'}, CONSENT | {'user_id': str(uuid4())},
                                  CONSENT | {'scope': 'evaluation_review'}, CONSENT | {'hours': 999}])
def test_no_implicit_consent_or_recipient_scope_expiry_override(body):
    api, c, project, _, _ = client()
    assert api.post(f'/api/v1/projects/{project}/workspace/benchmark/reference-storage-access', json=body).status_code == 422
    c.execute.assert_not_called()


def test_existing_unexpired_self_assignment_is_returned_without_renewal():
    old = {'id': uuid4(), 'expires_at': datetime.now(timezone.utc) + timedelta(minutes=5)}
    api, c, project, _, _ = client(old=old)
    response = api.post(f'/api/v1/projects/{project}/workspace/benchmark/reference-storage-access', json=CONSENT)
    assert response.json()['data']['assignment_id'] == str(old['id'])
    assert not any(x.args[0].startswith('INSERT') for x in c.execute.call_args_list)


def test_revocation_cannot_target_other_users_duties():
    api, c, project, user, assignment = client()
    response = api.post(f'/api/v1/projects/{project}/workspace/benchmark/reference-storage-access/{assignment}/revoke', json={})
    assert response.status_code == 404
    query = c.execute.call_args
    assert query.args[1] == (project, assignment, user, user)
    assert "scope='source_review'" in query.args[0]
    assert not any(x.args[0].startswith('INSERT') for x in c.execute.call_args_list)


def test_import_returns_source_valid_and_exact_gym_storage_blocker_without_writing(monkeypatch):
    api, c, project, _, _ = client()
    monkeypatch.setenv('ANVIL_PRAXIS_GENERIC_EXPORT_ENABLED', 'true')
    monkeypatch.setattr('anvil.benchmark_project_import.archive_files', lambda raw: {'praxis-export.json': b'{}'})
    monkeypatch.setattr('anvil.praxis_generic_export.validate', lambda *args: (
        {'valid': True, 'status': 'export_valid', 'anvil_requirements': [],
         'package_sha256': 'a' * 64, 'errors': []}, {}))
    stage = Mock(side_effect=AssertionError('No private write before access grant'))
    monkeypatch.setattr('anvil.benchmark_storage.stage_private', stage)
    response = api.post(f'/api/v1/projects/{project}/workspace/benchmark/import', content=b'package')
    assert response.status_code == 409
    detail = response.json()['detail']
    assert detail['valid'] is True and detail['request_id'] == 'storage-access-test-request'
    report = detail['validation_report']
    assert report['task_fix_required'] is False
    assert report['blocking_items'][0]['code'] == 'AV_PRIVATE_STORAGE_ASSIGNMENT_REQUIRED'
    assert report['anvil_setup']['reason'] == 'protected_reference_import_access_required'
    assert not report['anvil_setup']['paid_dispatch_authorized']
    assert not any(x.args[0].startswith('INSERT') for x in c.execute.call_args_list)
    stage.assert_not_called()


def test_import_replay_refreshes_request_and_setup_without_reimport(monkeypatch):
    project, user = uuid4(), uuid4()
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = {'allowed': True}
    requests = []
    cache = {}

    @contextmanager
    def context(request, actual_project):
        assert actual_project == project
        request.state.request_id = f'request-{len(requests)}'
        requests.append(request.state.request_id)
        yield connection, user, {'admin'}

    def idempotent(c, p, u, request, body, fn):
        if not cache:
            cache.update(fn())
        return cache

    validation = {'valid': True, 'status': 'export_valid', 'anvil_requirements': [],
                  'package_sha256': 'a' * 64, 'errors': []}
    monkeypatch.setenv('ANVIL_PRAXIS_GENERIC_EXPORT_ENABLED', 'true')
    monkeypatch.setattr('anvil.benchmark_project_import.archive_files', lambda raw: {'praxis-export.json': b'{}'})
    monkeypatch.setattr('anvil.praxis_generic_export.validate', lambda *args: (validation, {}))
    monkeypatch.setattr('anvil.benchmark_storage.describe_private', lambda *args: {})
    monkeypatch.setattr('anvil.benchmark_storage.stage_private', lambda *args: None)
    store = Mock(return_value={'id': 'stored'})
    monkeypatch.setattr('anvil.praxis_project_intake.store', store)
    monkeypatch.setattr('anvil.praxis_generic_resolution.resolve', lambda *args: {'id': 'resolved'})
    assessment = Mock(side_effect=[{'status': 'blocked'}, {'status': 'ready_for_run_configuration'}])
    monkeypatch.setattr('anvil.praxis_validation_report.binding_assessment', assessment)
    app = FastAPI()
    app.include_router(routes(context, lambda data, request: {'data': data}, idempotent))
    api = TestClient(app)
    path = f'/api/v1/projects/{project}/workspace/benchmark/import'
    first = api.post(path, content=b'package').json()['data']['validation']
    second = api.post(path, content=b'package').json()['data']['validation']
    assert first['request_id'] != second['request_id']
    assert first['validation_report']['anvil_setup']['status'] == 'blocked'
    assert second['validation_report']['anvil_setup']['status'] == 'ready_for_run_configuration'
    assert 'request_id' not in cache['validation']
    assert store.call_count == 1 and assessment.call_count == 2
