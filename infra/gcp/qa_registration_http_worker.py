"""Full in-memory HTTPS/ASGI path in a disposable synthetic cloud-mode fixture."""

import hashlib
import inspect
import json
import logging
import os
import secrets
import signal
import sys
import traceback
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row


def run():
    signal.signal(signal.SIGALRM, lambda *args: (_ for _ in ()).throw(TimeoutError('Isolated HTTP diagnostic deadline')))
    signal.alarm(300)
    config = json.loads(Path('/probe-control/control.json').read_bytes())
    params = conninfo_to_dict(config['app_dsn'])
    assert params['host'] == '/probe-socket' and params['dbname'] == 'anvil_golden_kyc_component_api41_http1'
    origin = 'https://fixture.invalid'
    os.environ.update(ANVIL_ENV='cloud', WEB_ORIGIN=origin,
                      OIDC_ISSUER='https://fixture-auth.invalid/realms/fixture',
                      DATABASE_URL=config['app_dsn'], ANVIL_FIXTURE_MODE='false')
    from fastapi.testclient import TestClient

    from anvil.api import app
    from anvil.auth import hashed
    from anvil.golden_kyc_anvil import source_hash

    assert source_hash() == '896b9c2b39b33ff45f75c989a73f11437abe0b00daa0932d0b639c5336a0e088'
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    # Synthetic fixture session only, no OIDC/real account or approval spoofing.
    with psycopg.connect(**params, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                           (config['project_id'], config['user_id']))
        assert connection.execute('SELECT anvil.golden_engineer(%s) AS allowed', (config['project_id'],)).fetchone()['allowed'] is True
        connection.execute('INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)',
                           (hashed(token), config['user_id'], hashed(csrf)))
        for table in ('banking.anvil_imports', 'banking.execution_jobs', 'anvil.idempotency'):
            assert connection.execute('SELECT count(*) AS n FROM ' + table).fetchone()['n'] == 0
    caught = []

    class SafeExceptionCapture(logging.Handler):
        def emit(self, record):
            if record.msg != 'request=%s code=%s' or caught:
                return
            frame = inspect.currentframe()
            for _ in range(32):
                if frame is None:
                    break
                if frame.f_code.co_name == 'security_headers':
                    error = frame.f_locals.get('exc')
                    if isinstance(error, BaseException):
                        allowed = {'Software resource closure changed before commit',
                                   'Software resource digest changed before commit',
                                   'Inactive or foreign software resource operation',
                                   'Foreign software operation connection',
                                   'Resource outside software operation inventory',
                                   'Private KYC transaction cannot change scope or database role',
                                   'No response returned.', 'Unexpected message received: http.request'}
                        caught.append({'error_type': type(error).__name__,
                            'safe_message': str(error) if str(error) in allowed else '[redacted]',
                            'frames': [{'file': Path(item.filename).name, 'line': item.lineno,
                                        'function': item.name} for item in traceback.extract_tb(error.__traceback__)][-12:]})
                    break
                frame = frame.f_back
            del frame

    handler = SafeExceptionCapture()
    logger = logging.getLogger('anvil.api')
    logger.addHandler(handler)
    try:
        with TestClient(app, base_url=origin, raise_server_exceptions=False, follow_redirects=False) as client:
            client.cookies.set('anvil_session', token)
            response = client.post('/api/v1/projects/' + config['project_id'] + '/golden-banking/v1/anvil/import',
                headers={'Origin': origin, 'X-CSRF-Token': csrf, 'Idempotency-Key': 'synthetic-http-api41-1'},
                json={'pack_id': config['pack_id'], 'task_mode': 'reusable_application_workflow'})
            body = response.json()
    finally:
        logger.removeHandler(handler)
    with psycopg.connect(**params, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                           (config['project_id'], config['user_id']))
        assert connection.execute('SELECT anvil.golden_engineer(%s) AS allowed', (config['project_id'],)).fetchone()['allowed'] is True
        assert connection.execute('SELECT count(*) AS n FROM banking.applications WHERE pack_id=%s',
                                  (config['pack_id'],)).fetchone()['n'] == 200
        counts = {table: connection.execute('SELECT count(*) AS n FROM ' + table).fetchone()['n']
                  for table in ('banking.anvil_imports', 'banking.execution_jobs', 'anvil.idempotency')}
        assert counts['banking.execution_jobs'] == 0
    result = {'scope': 'synthetic_cloud_asgi_diagnostic_only', 'http_status': response.status_code,
              'response_request_id': body.get('error', {}).get('request_id') or body.get('meta', {}).get('request_id'),
              'error_code': body.get('error', {}).get('code'), 'captured': caught,
              'binding_count': body.get('data', {}).get('binding_count'),
              'evaluator_count': body.get('data', {}).get('evaluator_count'),
              'fixture_counts': counts, 'normal_bytecode_setting': not sys.dont_write_bytecode,
              'qualification_granted': False, 'serving_database_used': False, 'model_calls': False,
              'real_tls_proxy_or_oidc_test': False, 'fixture_commits_expected_on_http_success': True,
              'source_file_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    run()
