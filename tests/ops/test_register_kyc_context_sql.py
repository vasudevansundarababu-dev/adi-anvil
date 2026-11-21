"""Opt-in real PostgreSQL test; dedicated disposable synthetic cluster only."""
import os
from copy import deepcopy
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from anvil.db import Jsonb, digest
from anvil.golden_kyc_data import generate
from anvil.golden_kyc_runtime import seed
from anvil.project_input_contract import INPUT

pytestmark = pytest.mark.skipif(not os.environ.get('ANVIL_CONTEXT_TEST_DSN'),
                                reason='Explicit isolated synthetic PostgreSQL required')


@pytest.fixture
def setup(monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'scripts'))
    import prepare_kyc_context
    import register_kyc_context

    dsn = os.environ['ANVIL_CONTEXT_TEST_DSN']
    project, user, org, group, input_id = (str(uuid4()) for _ in range(5))
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        # Test setup deliberately requires the isolated cluster marker created
        # by the operator, never a production/QA connection or owner credential.
        marker = c.execute('SELECT label FROM public.context_registrar_test_marker').fetchone()
        assert marker == {'label': 'synthetic-context-registrar-only'}
        c.execute('GRANT anvil_golden_scheduler TO context_scheduler_test')
        c.execute('INSERT INTO anvil.organizations VALUES(%s,%s)', (org, 'synthetic-registrar-test'))
        c.execute('INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,%s)',
                  (project, org, 'synthetic-registrar-test'))
        c.execute("INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,'synthetic-test',%s,'synthetic-test')", (user, org, user))
        c.execute("INSERT INTO anvil.memberships VALUES(%s,%s,'admin',true)", (project, user))
        pack = seed(c, project, user)['pack_id']
        manifest, apps, _ = generate()
        actor, scenarios, expectations, lineage, _, context = prepare_kyc_context.prepare_dataset(
            {'project_id': project, 'pack_id': pack, 'manifest': manifest,
             'applications': [{'id': a['id'], 'snapshot': a, 'snapshot_sha256': digest(a)} for a in apps]},
            '2026-11-12', 'synthetic-national-occ-ny')
        normalized = INPUT.validate_python(actor).model_dump(mode='json')
        for app, scenario, line in zip(normalized['applications'], scenarios, lineage, strict=True):
            scenario['snapshot_sha256'] = line['child_sha256'] = digest(app)
        context['child_population_sha256'] = digest(normalized['applications'])
        source = digest({'synthetic': True})
        # Synthetic fixture identity only, in the dedicated disposable cluster.
        c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (project, user))
        c.execute('SET LOCAL ROLE anvil_app')
        c.execute('INSERT INTO anvil.benchmark_task_groups(id,project_id,source_project_id,source_version,name,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                  (group, project, 'synthetic', '1', 'synthetic', Jsonb({'synthetic': True}), source, user))
        c.execute('INSERT INTO anvil.project_data_inputs(id,project_id,task_group_id,source_sha256,family,filename,schema_version,schema_sha256,raw_sha256,content,content_sha256,byte_size,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                  (input_id, project, group, source, 'kyc', 'synthetic.json', normalized['schema_version'],
                   digest(INPUT.json_schema()), digest(normalized), Jsonb(normalized), digest(normalized), 100000, user))
        c.execute('INSERT INTO anvil.project_data_input_jobs(input_id,project_id) VALUES(%s,%s)', (input_id, project))
    files = {'context.json': context, 'actor-input.json': normalized,
             'private/scenarios.json': scenarios, 'lineage.json': lineage}
    return register_kyc_context, dsn, project, group, input_id, source, files


def run(setup, files=None, fail_after_write=False):
    module, dsn, project, group, input_id, source, original = setup
    with psycopg.connect(dsn, user='context_scheduler_test', row_factory=dict_row) as c:
        result = module.register(c, project, group, input_id, source,
                                 files or original, 'f' * 64)
        assert not c.execute("SELECT has_table_privilege(current_user,'banking_private.expectations','SELECT') AS permitted").fetchone()['permitted']
        if fail_after_write:
            raise RuntimeError('Synthetic post-write failure')
    return result


def test_existing_scheduler_can_register_without_approvals_and_replay_fails(setup):
    result = run(setup)
    assert result['case_count'] == 200 and result['run_authority'] == 'not_granted'
    _, dsn, project, _, input_id, _, files = setup
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        assert c.execute('SELECT state FROM anvil.project_data_input_jobs WHERE input_id=%s', (input_id,)).fetchone()['state'] == 'completed'
        rows = c.execute('SELECT controls FROM banking_private.scenarios WHERE project_id=%s AND pack_id=%s ORDER BY application_id', (project, result['pack_id'])).fetchall()
        assert [r['controls'] for r in rows] == files['private/scenarios.json']
        assert c.execute('SELECT count(*) AS n FROM banking_private.expectations WHERE project_id=%s AND pack_id=%s', (project, result['pack_id'])).fetchone()['n'] == 0
    with pytest.raises(ValueError, match='still-queued'):
        run(setup)


def test_post_write_failure_rolls_back_entire_registration(setup):
    with pytest.raises(RuntimeError, match='post-write'):
        run(setup, fail_after_write=True)
    _, dsn, project, _, input_id, _, _ = setup
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        assert c.execute('SELECT state FROM anvil.project_data_input_jobs WHERE input_id=%s', (input_id,)).fetchone()['state'] == 'queued'
        assert c.execute('SELECT count(*) AS n FROM anvil.project_data_provisions WHERE project_id=%s', (project,)).fetchone()['n'] == 0
        assert c.execute('SELECT count(*) AS n FROM banking.packs WHERE project_id=%s', (project,)).fetchone()['n'] == 1


def test_changed_private_control_is_refused_before_insert(setup):
    files = deepcopy(setup[-1])
    files['private/scenarios.json'][0]['future_documents'] = [{'fabricated': True}]
    with pytest.raises(ValueError, match='actual parent controls'):
        run(setup, files)


def test_revoked_submitter_cannot_register(setup):
    _, dsn, project, _, _, _, _ = setup
    with psycopg.connect(dsn) as c:
        c.execute('UPDATE anvil.memberships SET active=false WHERE project_id=%s', (project,))
    with pytest.raises(ValueError, match='active project Admin'):
        run(setup)


def test_database_owner_cannot_run_registration(setup):
    module, dsn, project, group, input_id, source, files = setup
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        with pytest.raises(RuntimeError, match='Dedicated non-owner'):
            module.register(c, project, group, input_id, source, files, 'f' * 64)
