"""Operator-only isolated QA fixtures; no approvals, credentials or model calls.

Reset creates a fresh named generation and preserves prior records/audit. The
actual approved Praxis export is a later normal intake, never forged by this seed.
"""

import argparse
import ast
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from anvil.dataset_export_contract import Model, Sha
from anvil.db import audit, digest
from anvil.qualification_resources import qualification_root

ORIGIN='qa_fixture_initial_testing_v1'
QA_ORIGIN='https://anvil-qa.adi-labs.ai'
QA_ISSUER='https://anvil-qa-auth.adi-labs.ai/realms/anvil-qa'
OFF_FLAGS=(
    'ANVIL_LIVE_PROVIDERS_ENABLED','ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED','ANVIL_GOLDEN_KYC_PAID_ENABLED',
    'ANVIL_GOLDEN_KYC_PAID_WORKER_ENABLED','ANVIL_MARKETING_PAID_ENABLED','ANVIL_MARKETING_JUDGE_ENABLED',
    'ANVIL_IMPORT_GENERATION_ENABLED','ANVIL_GENERATION_ENABLED','ANVIL_REAL_EMAIL_ENABLED',
    'ANVIL_GOVERNED_AI_ENABLED','ANVIL_CLOUD_PROVISIONING_ENABLED',
    'ANVIL_VERTEX_ENABLED','ANVIL_CAMPAIGN_JUDGE_ENABLED','ANVIL_WORKER_BROKER_ENABLED',
    'ANVIL_ENVIRONMENT_CLOUD_WORKER_ENABLED','ANVIL_ENVIRONMENT_NATIVE_ENABLED','ANVIL_ENVIRONMENT_OPENENV_ENABLED',
    'ANVIL_HARBOR_HOST_MEDIATED_STRUCTURED_ENABLED','ANVIL_HARBOR_WORKER_ENABLED','ANVIL_HARBOR_WORKFLOW_ENABLED',
    'ANVIL_GOLDEN_NATIVE_COORDINATOR_ENABLED','ANVIL_MARKETING_NATIVE_CAPTURE_ENABLED',
    'ANVIL_MARKETING_WORLD_ENABLED','ANVIL_MARKETING_WORLD_STOP_ENABLED','ANVIL_CAMPAIGN_GRADING_ENABLED',
    'ANVIL_TASK_SAFETY_HOST_ENABLED','ANVIL_CUSTOM_PYTHON_ENABLED','ANVIL_CUSTOM_PYTHON_SCORING_ENABLED',
    'ANVIL_BENCHMARK_ENABLED','ANVIL_BENCHMARK_EVALUATION_ENABLED','ANVIL_QA_MODEL_SMOKE_ENABLED',
)


class Project(Model):
    id: UUID
    purpose: Literal['lifecycle','approved-export-receiver']
    name: str = Field(min_length=10,max_length=160)


class Plan(Model):
    schema_version: Literal['anvil.initial-qa-fixtures.plan.v1']
    id: UUID
    generation: int = Field(ge=1,le=10000,strict=True)
    admin_user_id: UUID | None
    engineer_user_id: UUID | None
    projects: list[Project] = Field(min_length=2,max_length=2)
    previous_plan_sha256: Sha | None = None
    source_approvals: Literal[False] = False
    paid_calls: Literal[False] = False
    model_performance: Literal[False] = False
    staging: Literal['hold'] = 'hold'

    @model_validator(mode='after')
    def scope(self):
        if ({p.purpose for p in self.projects}!={'lifecycle','approved-export-receiver'}
                or len({p.id for p in self.projects})!=2 or any(not p.name.startswith('VS-QA- [QA FIXTURE]') for p in self.projects)
                or self.admin_user_id is not None and self.admin_user_id==self.engineer_user_id):
            raise ValueError('Two distinct isolated labelled QA projects and named roles required')
        return self


class Target(Model):
    schema_version: Literal['anvil.initial-qa-fixtures.target.v1']
    environment: Literal['qa']
    database: Literal['anvil']
    cluster_system_identifier: str = Field(pattern=r'^[0-9]{1,30}$')
    database_oid: int = Field(gt=0,strict=True)
    schema_head: Literal[127]
    seed_source_sha256: Sha
    release_commit: str = Field(pattern=r'^[0-9a-f]{40}$')
    release_manifest_sha256: Sha


def source_hash():
    root=qualification_root()
    names=['qa_initial_seed.py','benchmark_business_fixture.py','benchmark_project_import.py','benchmark_runs.py']
    paths=[root/'services/backend/src/anvil'/name for name in names]
    paths+=sorted((root/'services/backend/migrations').glob('*.sql'))
    paths+=sorted((root/'services/backend/alembic/versions').glob('*.py'))
    paths+=[root/'services/backend/alembic/env.py',root/'services/backend/alembic.ini']
    return digest({str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})


def release_members(*,backend_only=False):
    """Required application source, not an asserted clean Git commit."""
    root=qualification_root()
    folders=('services/backend/src/anvil','services/backend/migrations','services/backend/alembic')
    if not backend_only:
        folders+=('apps/web/src','apps/web/public','infra/docker')
    paths=[path for name in folders for path in (root/name).rglob('*')
           if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc']
    inputs=('services/backend/alembic.ini','services/backend/pyproject.toml','services/backend/uv.lock')
    if not backend_only:
        inputs+=('apps/web/package.json','pnpm-lock.yaml')
    paths += [root/name for name in inputs if (root/name).is_file()]
    if len(paths)>10000 or sum(path.stat().st_size for path in paths)>256*1024*1024:
        raise ValueError('Application release source inventory exceeds bounds')
    if any(path.is_symlink() or path.resolve()!=path for path in paths):
        raise ValueError('Application release source cannot use aliases')
    return {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}


def verify_release(target,manifest):
    if (not isinstance(manifest,dict) or set(manifest)!={'schema_version','release_commit','members'}
            or manifest['schema_version']!='anvil.initial-qa-release-manifest.v1'
            or manifest['release_commit']!=target.release_commit or digest(manifest)!=target.release_manifest_sha256):
        raise ValueError('Exact reviewed full release manifest required')
    members=manifest['members']
    if (not isinstance(members,dict) or len(members)>10000
            or any(not isinstance(k,str) or not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v)
                   for k,v in members.items())
            or not any(k.startswith('apps/web/src/') for k in members)):
        raise ValueError('Reviewed full application source inventory required')
    # The API image intentionally contains no web source. Verify its installed
    # backend, while the reviewed full manifest pins the separately built web.
    actual=release_members(backend_only=True)
    expected={k:v for k,v in members.items() if k.startswith('services/backend/')}
    if expected!=actual:
        raise ValueError('Installed backend differs from reviewed full source manifest')


def migration_order():
    root=qualification_root()/'services/backend'
    found={}
    for path in sorted((root/'alembic/versions').glob('*.py')):
        values={node.targets[0].id:ast.literal_eval(node.value) for node in ast.parse(path.read_bytes()).body
                if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)
                and node.targets[0].id in {'revision','down_revision'}}
        version=values.get('revision')
        if version is None:
            continue
        if version in found:
            raise ValueError('Duplicate application migration revision')
        sql_files=list((root/'migrations').glob(str(version)+'_*.sql'))
        inline=version=='032' and not sql_files
        if len(sql_files)!=1 and not inline:
            raise ValueError('One exact SQL member required except the reviewed inline032 migration')
        found[version]={'revision':version,'parent':values.get('down_revision'),
                        'alembic_file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'sql_file':None if inline else sql_files[0].name,
                        'sql_sha256':None if inline else hashlib.sha256(sql_files[0].read_bytes()).hexdigest(),
                        'execution':'inline_alembic' if inline else 'sql_member'}
    ordered=[]
    previous=None
    for number in range(1,128):
        key=f'{number:03}'
        if key not in found or found[key]['parent']!=previous:
            raise ValueError('Application migrations must form the exact additive001–127 chain')
        ordered.append(found[key])
        previous=key
    if set(found)!={f'{number:03}' for number in range(1,128)}:
        raise ValueError('Unexpected application migration head; review a new target')
    return ordered


def plan(admin=None,engineer=None,*,previous=None):
    old=(Plan.model_validate_json(json.dumps(previous)) if isinstance(previous,dict)
         else Plan.model_validate(previous)) if previous is not None else None
    generation=old.generation+1 if old else 1
    admin=admin or (old.admin_user_id if old else None)
    engineer=engineer or (old.engineer_user_id if old else None)
    return Plan(schema_version='anvil.initial-qa-fixtures.plan.v1',id=uuid4(),generation=generation,
                admin_user_id=admin,engineer_user_id=engineer,
                previous_plan_sha256=digest(old.model_dump(mode='json')) if old else None,
                projects=[Project(id=uuid4(),purpose=purpose,name=f'VS-QA- [QA FIXTURE] {label} • generation {generation}')
                          for purpose,label in (('lifecycle','Lifecycle testing'),('approved-export-receiver','Export receiver — awaits real approved Praxis tasks'))])


def guard(connection,target):
    from anvil import pilot_environment

    if pilot_environment.current()!='qa' or any(os.environ.get(name,'false')!='false' for name in OFF_FLAGS):
        raise ValueError('QA only; provider/judge/generation/provisioning/email flags must remain OFF')
    if target.seed_source_sha256!=source_hash():
        raise ValueError('Seed source changed; review an exact new QA target')
    row=connection.execute("SELECT current_database() AS database,(SELECT oid::integer FROM pg_database WHERE datname=current_database()) AS database_oid,"
        "(SELECT system_identifier::text FROM pg_control_system()) AS cluster_system_identifier,"
        "(SELECT max(version) FROM anvil.schema_versions) AS schema_head").fetchone()
    if not row or any(row[key]!=getattr(target,key) for key in ('database','database_oid','cluster_system_identifier','schema_head')):
        raise ValueError('Actual database identity/schema differs from the reviewed isolated QA target')


def apply(connection,target,body,*,release_manifest=None):
    """Caller commits; no user/login/terms/source-review/qualification is created."""
    target=Target.model_validate(target)
    body=Plan.model_validate(body)
    if connection.autocommit:
        raise ValueError('Both isolated QA projects must share one explicit transaction')
    guard(connection,target)
    verify_release(target,release_manifest)
    if body.admin_user_id is None or body.engineer_user_id is None:
        raise ValueError('Coordinator must supply verified existing QA Admin and RL Engineer user IDs')
    users=connection.execute('SELECT id,org_id,issuer,active,name FROM anvil.users WHERE id=ANY(%s)',
                             ([body.admin_user_id,body.engineer_user_id],)).fetchall()
    if (len(users)!=2 or len({row['org_id'] for row in users})!=1
            or any(row['issuer']!=QA_ISSUER or row['active'] is not True for row in users)):
        raise ValueError('Two existing active identities in the isolated QA issuer/organization required')
    fingerprint=digest(body.model_dump(mode='json'))
    output=[]
    for project in body.projects:
        existing=connection.execute('SELECT id,name,org_id FROM anvil.projects WHERE id=%s',(project.id,)).fetchone()
        if existing:
            marker=connection.execute("SELECT metadata FROM anvil.audit_events WHERE project_id=%s AND action='qa_initial.fixture_project_seeded' ORDER BY event_seq LIMIT 1",
                                      (project.id,)).fetchone()
            if (not marker or marker['metadata'].get('seed_manifest_sha256')!=fingerprint
                    or existing['name']!=project.name or existing['org_id']!=users[0]['org_id']):
                raise ValueError('Existing project is outside this exact seed; no records changed')
            members=connection.execute('SELECT user_id,role,active FROM anvil.memberships WHERE project_id=%s',
                                       (project.id,)).fetchall()
            if ({(str(row['user_id']),row['role'],row['active']) for row in members}
                    !={(str(body.admin_user_id),'admin',True),(str(body.engineer_user_id),'rl-engineer',True)}):
                raise ValueError('Seed membership changed; reconcile without restoring access automatically')
        else:
            connection.execute('INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,%s)',(project.id,users[0]['org_id'],project.name))
            for identifier,role in ((body.admin_user_id,'admin'),(body.engineer_user_id,'rl-engineer')):
                connection.execute('INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,%s)',(project.id,identifier,role))
            audit(connection,project.id,None,'qa_initial.fixture_project_seeded',project.id,
                  {'origin':ORIGIN,'seed_manifest_sha256':fingerprint,'purpose':project.purpose,'generation':body.generation,
                   'source_approvals':False,'provider_calls':0,'model_performance':False,'reset':'fresh_generation_preserves_history',
                   'release_commit':target.release_commit})
        output.append({'id':str(project.id),'name':project.name,'purpose':project.purpose,
                       'url':QA_ORIGIN+'/workspace?project='+str(project.id),'source_import':'awaiting_actual_human_approved_Praxis_QA_export'})
    return {'schema_version':'anvil.initial-qa-fixtures.receipt.v1','seed_manifest_sha256':fingerprint,
            'projects':output,'roles':{'admin_user_id':str(body.admin_user_id),'rl_engineer_user_id':str(body.engineer_user_id)},
            'release_manifest_sha256':target.release_manifest_sha256,
            'commit_observed':False,'source_approvals':False,'paid_calls':False,'model_performance':False,'staging':'hold'}


def queue_report_fixture(connection,project,user,seed_manifest_sha256):
    """Canonical software-control job; never directly seed an invented Run result."""
    from anvil import benchmark_business_fixture as fixture
    from anvil import benchmark_project_import as imports
    from anvil import benchmark_runs as runs

    # Bootstrap is finished: canonical writers use original application RLS.
    connection.execute('SET LOCAL ROLE anvil_app')
    connection.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",(str(project),str(user)))
    old=connection.execute("SELECT metadata FROM anvil.audit_events WHERE project_id=%s AND action='qa_initial.fixture_report_queued' "
                           "AND metadata->>'seed_manifest_sha256'=%s ORDER BY event_seq LIMIT 1",(project,seed_manifest_sha256)).fetchone()
    if old:
        receipt=old['metadata']['receipt']
        run=connection.execute('SELECT id,state FROM anvil.benchmark_runs WHERE project_id=%s AND id=%s',(project,receipt['run_id'])).fetchone()
        if not run:
            raise ValueError('Retained QA report receipt changed; reconcile instead of replaying')
        return receipt|{'state':run['state'],'existing_run_preserved':True}
    content,policies=imports.parse(fixture.bundle())
    # Keep the exact fixture source/hash: the worker denies altered fixtures.
    # Labelling belongs to the plan/audit, never forged authoring provenance.
    imported=imports.store(connection,project,user,content,policies)
    body=runs.Plan(name='VS-QA- [QA FIXTURE] Transparent software controls',task_group_id=imported['id'],
                   task_ids=[task['task_id'] for task in content['tasks']],models=['fictional-compliant-v1','fictional-permissive-v1','fictional-incomplete-v1'],
                   environment_ids=['enforced-v1'],method_ids=['task-rubric-v1','safety-observed-v1'],repetitions=1)
    planned=runs.create_plan(connection,project,user,body,qa_fixture=True)
    started=runs.start(connection,project,user,runs.Start(plan_id=planned['id'],expected_plan_sha256=planned['snapshot_sha256']))
    receipt={'run_id':str(started['id']),'plan_id':str(planned['id']),'status':'queued_software_fixture_not_completed',
             'group_id':str(imported['id']),'origin':ORIGIN,'provider_calls':0,'model_performance':False}
    audit(connection,project,None,'qa_initial.fixture_report_queued',started['id'],
          {'origin':ORIGIN,'seed_manifest_sha256':seed_manifest_sha256,'receipt':receipt,'source_approvals':False})
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['plan','apply','reset-plan','migration-manifest','release-manifest'])
    parser.add_argument('--plan',type=Path)
    parser.add_argument('--target',type=Path)
    parser.add_argument('--release-manifest',type=Path)
    parser.add_argument('--release-commit')
    parser.add_argument('--admin-user-id',type=UUID)
    parser.add_argument('--engineer-user-id',type=UUID)
    parser.add_argument('--with-report-fixtures',action='store_true')
    args=parser.parse_args()
    if args.action=='release-manifest':
        if not args.release_commit or not re.fullmatch('[0-9a-f]{40}',args.release_commit):
            raise ValueError('Exact release base commit required alongside dirty source inventory')
        print(json.dumps({'schema_version':'anvil.initial-qa-release-manifest.v1',
                          'release_commit':args.release_commit,'members':release_members()},indent=2))
        return
    if args.action=='migration-manifest':
        print(json.dumps({'head':'127','migrations':migration_order(),'seed_source_sha256':source_hash()},indent=2))
        return
    if args.action in {'plan','reset-plan'}:
        previous=json.loads(args.plan.read_bytes()) if args.action=='reset-plan' and args.plan else None
        if args.action=='reset-plan' and previous is None:
            raise ValueError('Exact previous plan required; reset never guesses project IDs')
        print(json.dumps(plan(args.admin_user_id,args.engineer_user_id,previous=previous).model_dump(mode='json'),indent=2))
        return
    if not args.plan or not args.target or not args.release_manifest:
        raise ValueError('Reviewed exact seed plan, isolated QA database target and full source manifest required')
    import psycopg
    from psycopg.rows import dict_row

    body=Plan.model_validate_json(args.plan.read_bytes())
    target=Target.model_validate_json(args.target.read_bytes())
    with psycopg.connect(os.environ['MIGRATION_DATABASE_URL'],row_factory=dict_row) as connection:
        receipt=apply(connection,target,body,release_manifest=json.loads(args.release_manifest.read_bytes()))
        if args.with_report_fixtures:
            receipt['fixture_reports']=[queue_report_fixture(connection,project.id,body.admin_user_id,receipt['seed_manifest_sha256']) for project in body.projects]
    receipt['commit_observed']=True
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    main()
