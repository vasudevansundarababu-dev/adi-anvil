"""Exact backend-image registration against a disposable synthetic DB; rollback."""

import hashlib
import json
import os
import signal
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import psycopg
from fastapi.encoders import jsonable_encoder
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from anvil.golden_kyc_anvil import register, source_hash
from anvil.golden_kyc_api import AnvilImport


class DiagnosticRollback(Exception):
    pass


def run():
    signal.signal(signal.SIGALRM, lambda *args: (_ for _ in ()).throw(TimeoutError('Isolated diagnostic deadline')))
    signal.alarm(300)
    config = json.loads(Path('/probe-control/control.json').read_bytes())
    params = conninfo_to_dict(config['app_dsn'])
    assert params['host'] == '/probe-socket' and params['dbname'] == 'anvil_golden_kyc_component_api41_repro2'
    # Any configuration lookup sees only this disposable restricted login.
    os.environ['DATABASE_URL'] = config['app_dsn']
    from anvil.api import idempotent, wrap

    assert source_hash() == '896b9c2b39b33ff45f75c989a73f11437abe0b00daa0932d0b639c5336a0e088'
    result = {'scope': 'isolated_synthetic_registration_diagnostic_only', 'qualification_granted': False,
              'model_calls': False, 'normal_bytecode_setting': not sys.dont_write_bytecode}
    phase = 'connect-fixture'
    try:
        with psycopg.connect(**params, row_factory=dict_row) as connection:
            connection.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                               (config['project_id'], config['user_id']))
            assert connection.execute('SELECT inet_server_addr() AS address').fetchone()['address'] is None
            phase = 'idempotent-real-register'
            request = SimpleNamespace(headers={'idempotency-key': 'isolated-api41-repro2'},
                url=SimpleNamespace(path='/api/v1/projects/' + config['project_id'] + '/golden-banking/v1/anvil/import'),
                state=SimpleNamespace(request_id='isolated-api41-repro2'))
            body = AnvilImport(pack_id=UUID(config['pack_id']), task_mode='reusable_application_workflow')
            response = idempotent(connection, config['project_id'], config['user_id'], request, body,
                                  lambda: register(connection, config['project_id'], config['user_id'],
                                                   body.pack_id, application_types=True))
            phase = 'response-encoding'
            jsonable_encoder(wrap(response, request))
            result.update(status='registration_completed_in_fixture_then_rolled_back',
                          binding_count=response['binding_count'], evaluator_count=response['evaluator_count'])
            raise DiagnosticRollback()
    except DiagnosticRollback:
        pass
    except Exception as error:
        allowed = {'Software resource closure changed before commit', 'Software resource digest changed before commit',
                   'Inactive or foreign software resource operation', 'Foreign software operation connection',
                   'Unexpected software resource type', 'Resource outside software operation inventory',
                   'Software resource proof supports deterministic Golden controls only'}
        result.update(status='registration_failure_reproduced_in_fixture', phase=phase,
                      error_type=type(error).__name__, safe_message=str(error) if str(error) in allowed else '[redacted]',
                      message_sha256=hashlib.sha256(str(error).encode()).hexdigest(),
                      frames=[{'file': Path(frame.filename).name, 'line': frame.lineno, 'function': frame.name}
                              for frame in traceback.extract_tb(error.__traceback__)][-12:])
    with psycopg.connect(**params, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                           (config['project_id'], config['user_id']))
        assert connection.execute('SELECT current_user AS login').fetchone()['login'] == params['user']
        assert connection.execute('SELECT anvil.golden_engineer(%s) AS allowed', (config['project_id'],)).fetchone()['allowed'] is True
        assert connection.execute('SELECT count(*) AS n FROM banking.applications WHERE pack_id=%s',
                                  (config['pack_id'],)).fetchone()['n'] == 200
        assert connection.execute('SELECT count(*) AS n FROM banking.anvil_imports').fetchone()['n'] == 0
        assert connection.execute('SELECT count(*) AS n FROM banking.execution_jobs').fetchone()['n'] == 0
        assert connection.execute('SELECT count(*) AS n FROM anvil.idempotency').fetchone()['n'] == 0
    result['fixture_registration_rows_after_rollback'] = 0
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    run()
