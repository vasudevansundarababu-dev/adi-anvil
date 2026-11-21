"""Register a pinned prepared context against a real queued Admin input.

Uses only the existing dedicated scheduler login. Never uploads actor input,
impersonates an Admin, writes grading expectations or approves reviews.
The caller owns the transaction; any mismatch must roll back the whole call.
"""
import argparse
import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from check_kyc_context_bundle import verify
from psycopg.rows import dict_row

from anvil.db import Jsonb, digest
from anvil.golden_kyc_data import VERSION
from anvil.golden_kyc_identity import enter
from anvil.golden_kyc_policy import library
from anvil.praxis_generic_contract import canonical
from anvil.project_input_contract import INPUT

REGISTRATION_FILES = frozenset(('context.json', 'actor-input.json', 'private/scenarios.json', 'lineage.json'))


def read_bundle(root, pinned):
    if os.environ.get('ANVIL_GOLDEN_SCHEDULER_DATABASE_URL'):
        raise ValueError('Private bundle verification requires a process without scheduler credentials')
    root = Path(root).resolve()
    raw = (root / 'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != pinned:
        raise ValueError('Exact preparation manifest required')
    verify(root)
    files = {}
    for name, expected in json.loads(raw)['files'].items():
        path = root / name
        if path.resolve() != path or not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Exact regular prepared artifact required')
        body = path.read_bytes()
        if len(body) != expected['bytes'] or hashlib.sha256(body).hexdigest() != expected['sha256']:
            raise ValueError('Captured prepared artifact integrity changed')
        value = json.loads(body)
        if canonical(value) != body:
            raise ValueError('Canonical prepared artifact required')
        files[name] = value
    actor = files['actor-input.json']
    # Group content and queued input are immutable (migrations065/102).
    # Scheduler deliberately has no task-group read privilege. Rely on the
    # authenticated input's exact frozen source; later binding checks recheck it.
    if INPUT.validate_python(actor).model_dump(mode='json') != actor:
        raise ValueError('Actor input must already have wire-normalized defaults')
    context = files['context.json']
    if (context['rights_review'] != 'pending' or context['expectation_review'] != 'pending'
            or context['policy_approval'] != 'not_granted' or context['run_authority'] != 'not_granted'):
        raise ValueError('Registration cannot create or inherit review authority')
    return files


def registration_input(root, pinned):
    """Run only in a credential-free isolated validator, never the scheduler."""
    files = read_bundle(root, pinned)
    body = {'schema_version': 'anvil.kyc-context-registration-input.v1',
            'preparation_manifest_utf8': (Path(root) / 'manifest.json').read_text(),
            'files': {name: files[name] for name in sorted(REGISTRATION_FILES)}}
    raw = canonical(body)
    # Recheck the final captured manifest and every scheduler-visible byte.
    read_registration_input(raw, pinned)
    return raw


def read_registration_input(raw, pinned):
    if len(raw) > 16 * 1048576:
        raise ValueError('Bounded registration input required')
    body = json.loads(raw)
    if (set(body) != {'schema_version', 'preparation_manifest_utf8', 'files'}
            or body['schema_version'] != 'anvil.kyc-context-registration-input.v1'
            or canonical(body) != raw or set(body['files']) != REGISTRATION_FILES):
        raise ValueError('Only the four non-expectation registration artifacts are permitted')
    manifest_raw = body['preparation_manifest_utf8'].encode()
    if hashlib.sha256(manifest_raw).hexdigest() != pinned:
        raise ValueError('Exact original preparation manifest required')
    manifest = json.loads(manifest_raw)
    if manifest['registered'] is not False or manifest['run_authority'] != 'not_granted':
        raise ValueError('Registration input cannot supply review authority')
    for name, value in body['files'].items():
        encoded = canonical(value)
        expected = manifest['files'][name]
        if len(encoded) != expected['bytes'] or hashlib.sha256(encoded).hexdigest() != expected['sha256']:
            raise ValueError('Registration artifact differs from pinned preparation')
    return body['files']


def checked_parent(files, rows, manifest):
    context = files['context.json']
    if (digest([row['snapshot'] for row in rows]) != context['parent_population_sha256']
            or manifest['public_sha256'] != context['parent_population_sha256']):
        raise ValueError('Exact complete selected parent population required')
    apps, scenarios, lineage = (files[name] for name in
                               ('actor-input.json', 'private/scenarios.json', 'lineage.json'))
    for parent, app, scenario, relation in zip(rows, apps['applications'], scenarios, lineage, strict=True):
        sha = digest(parent['snapshot'])
        if (parent['id'] != app['id'] or relation['application_id'] != app['id']
                or parent['snapshot_sha256'] != sha or relation['parent_sha256'] != sha
                or relation['child_sha256'] != digest(app)):
            raise ValueError('Exact parent/child snapshot lineage required')
        controls = deepcopy(parent['controls'])
        controls['snapshot_sha256'] = digest(app)
        if controls != scenario:
            raise ValueError('Prepared private controls must equal the actual parent controls')


def register(c, project, group, input_id, source_sha256, files, pinned):
    """Call only inside a fresh transaction with a disjoint scheduler LOGIN."""
    if set(files) != REGISTRATION_FILES:
        raise ValueError('Scheduler may receive only non-expectation registration artifacts')
    project, group, input_id = map(lambda v: str(UUID(str(v))), (project, group, input_id))
    if str(files['context.json']['parent_project_id']) != project:
        raise ValueError('Prepared context belongs to another project')
    enter(c, 'anvil_golden_scheduler', project)
    c.execute("SET LOCAL statement_timeout='300000'")
    c.execute("SET LOCAL lock_timeout='5000'")
    job = c.execute('SELECT state FROM anvil.project_data_input_jobs WHERE project_id=%s AND input_id=%s FOR UPDATE',
                    (project, input_id)).fetchone()
    row = c.execute('SELECT * FROM anvil.project_data_inputs WHERE project_id=%s AND id=%s',
                    (project, input_id)).fetchone()
    if not job or not row or job['state'] != 'queued':
        raise ValueError('One genuine still-queued Admin input required; no automatic replay')
    actor = files['actor-input.json']
    if (str(row['task_group_id']) != group or row['source_sha256'] != source_sha256
            or row['family'] != 'kyc' or row['content'] != actor
            or row['content_sha256'] != digest(actor)
            or row['schema_version'] != actor['schema_version']
            or row['schema_sha256'] != digest(INPUT.json_schema())):
        raise ValueError('Exact imported task group and queued actor input required')
    if not c.execute("SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active AND m.role='admin'",
                     (project, row['created_by'])).fetchone():
        raise ValueError('Queued input submitter must remain an active project Admin')
    parent_id = str(UUID(files['context.json']['parent_pack_id']))
    parent = c.execute('SELECT manifest FROM banking.packs WHERE project_id=%s AND id=%s',
                       (project, parent_id)).fetchone()
    parents = c.execute('SELECT a.id,a.snapshot,a.snapshot_sha256,s.controls FROM banking.applications a JOIN banking_private.scenarios s ON s.project_id=a.project_id AND s.pack_id=a.pack_id AND s.application_id=a.id WHERE a.project_id=%s AND a.pack_id=%s ORDER BY a.id',
                        (project, parent_id)).fetchall()
    if not parent:
        raise ValueError('Selected parent pack unavailable')
    checked_parent(files, parents, parent['manifest'])
    pack = str(uuid5(NAMESPACE_URL, f'anvil.prepared-context:{project}:{input_id}:{pinned}'))
    applications = actor['applications']
    manifest = {'version': VERSION, 'seed': None, 'origin': 'prepared_context_unreviewed',
                'data_provenance': 'gym_prepared_context_unreviewed', 'input_id': input_id,
                'input_sha256': digest(actor), 'application_count': len(applications),
                'public_sha256': digest(applications), 'policy_sha256': digest(library()),
                'preparation_manifest_sha256': pinned, 'parent_pack_id': parent_id,
                'parent_population_sha256': files['context.json']['parent_population_sha256'],
                'private_scenarios_sha256': files['context.json']['private_scenarios_sha256'],
                'expectation_review': 'pending_not_installed', 'data_rights': 'pending',
                'paid_calls': False, 'model_performance': False}
    c.execute('INSERT INTO banking.packs(id,project_id,manifest,created_by) VALUES(%s,%s,%s,%s)',
              (pack, project, Jsonb(manifest), row['created_by']))
    for app, scenario in zip(applications, files['private/scenarios.json'], strict=True):
        c.execute('INSERT INTO banking.applications VALUES(%s,%s,%s,%s,%s)',
                  (app['id'], project, pack, Jsonb(app), digest(app)))
        c.execute('INSERT INTO banking_private.scenarios VALUES(%s,%s,%s,%s)',
                  (project, pack, app['id'], Jsonb(scenario)))
    result = {'schema_version': 'anvil.populated-project-input.v1', 'input_id': input_id,
              'content_sha256': digest(actor), 'family': 'kyc', 'pack_id': pack,
              'case_count': len(applications), 'cases': sorted([
                  {'id': app['id'], 'snapshot_sha256': digest(app), 'governing_state': app['governing_state']}
                  for app in applications], key=lambda item: item['id']),
              'qualification': 'not_runtime_or_reference_qualified',
              'private_expectations': 'pending_not_installed', 'preparation_manifest_sha256': pinned}
    c.execute('INSERT INTO anvil.project_data_provisions(input_id,project_id,pack_id,manifest,manifest_sha256) VALUES(%s,%s,%s,%s,%s)',
              (input_id, project, pack, Jsonb(result), digest(result)))
    changed = c.execute("UPDATE anvil.project_data_input_jobs SET state='completed' WHERE input_id=%s AND project_id=%s AND state='queued'",
                        (input_id, project))
    if changed.rowcount != 1:
        raise ValueError('Once-only input transition failed')
    return {'status': 'registered_unreviewed', 'pack_id': pack, 'input_id': input_id,
            'case_count': len(applications), 'preparation_manifest_sha256': pinned,
            'provision_sha256': digest(result), 'run_authority': 'not_granted'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-bundle', type=Path)
    mode.add_argument('--registration-input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--project')
    parser.add_argument('--group')
    parser.add_argument('--input')
    parser.add_argument('--source-sha256')
    args = parser.parse_args()
    if args.check_bundle:
        if not args.output or any((args.project, args.group, args.input, args.source_sha256)):
            parser.error('Credential-free validation requires only --output and the pinned manifest')
        encoded = registration_input(args.check_bundle, args.manifest_sha256)
        with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as out:
            out.write(encoded)
            out.flush()
            os.fsync(out.fileno())
        print(json.dumps({'status': 'validated_registration_input_without_expectations',
                          'sha256': hashlib.sha256(encoded).hexdigest(), 'database_writes': 0}))
    else:
        if args.output or not all((args.project, args.group, args.input, args.source_sha256)):
            parser.error('Registration requires exact project/group/input/source and no full bundle')
        prepared = read_registration_input(args.registration_input.read_bytes(), args.manifest_sha256)
        with psycopg.connect(os.environ['ANVIL_GOLDEN_SCHEDULER_DATABASE_URL'], row_factory=dict_row,
                             connect_timeout=5) as connection:
            receipt = register(connection, args.project, args.group, args.input, args.source_sha256,
                               prepared, args.manifest_sha256)
        print(json.dumps(receipt, sort_keys=True))
