"""One reconciled QA service-only retry. Migration133 is never replayed."""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path, PurePosixPath

REVISION = '08d45ff8eeb515561fbcd50916d6a7adb8fca42c'
MANIFEST_SHA = '44776b6f0535c4b38ec5e44614572bac5f8d6695a4a52ea04fc69c0ac4c91f00'
RECEIPT_SHA = '19ece673da61599de0bd74e787c67909e8929df41a3484c072c7442209b80284'
LEGACY = {'api': {'/var/lib/anvil-qa-v1/artifacts:/app/.data/artifacts',
    '/var/lib/anvil-qa-v1/benchmark-vault:/app/.data/benchmark-vault',
    '/var/lib/anvil-qa-v1/secret-index:/app/.data/secret-index'},
    'worker': {'/var/lib/anvil-qa-v1/artifacts:/app/.data/artifacts'},
    'business-worker': {'/var/lib/anvil-qa-v1/artifacts:/app/.data/artifacts'}}


def bind_map(role, volumes):
    result = {}
    for value in volumes:
        if isinstance(value, str):
            # Only the exact observed legacy defaults; no general mode parser.
            assert value in LEGACY.get(role, set()), 'Unreviewed short mount'
            source, target = value.split(':')
            readonly = False
        else:
            assert type(value) is dict and set(value) == {'type','source','target','read_only'}
            assert value['type'] == 'bind' and type(value['read_only']) is bool
            source, target, readonly = value['source'], value['target'], value['read_only']
        for path in (source, target):
            assert type(path) is str and path.startswith('/') and not any(c in path for c in ('$', '~', chr(0), ':'))
            assert '..' not in PurePosixPath(path).parts and str(PurePosixPath(path)) == path
        assert target not in result, 'Duplicate intended mount target'
        result[target] = (source, readonly)
    return result


def main():
    assert os.geteuid() == 0 and os.uname().nodename == 'anvil-qa-v1'
    root = Path('/var/lib/anvil-qa-v1')
    prior = root/'backups/qualification-08d45ff'
    config = root/'config/compose-app.json'
    assert json.loads((prior/'rollback-outcome.json').read_bytes()) == {'failures': [], 'schema133_retained': True}
    assert config.read_bytes() == (prior/config.name).read_bytes(), 'Serving config changed since owned rollback'
    assert (prior/'database-before.sql').stat().st_size > 1000
    raw = Path('/tmp/forge-qualification-release-08d45ff-2fad3bc.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MANIFEST_SHA
    manifest = json.loads(raw)
    assert manifest['revision'] == REVISION and manifest['schema'] == 133
    assert manifest['source_sha256'] == 'e8fade572ca204830402fd40fb75b6aaeda595bfecb57a6e40e4c09a13c05086'
    qualification = root/'runtime-functional/harbor-proof/component-qualification/current.json'
    assert hashlib.sha256(qualification.read_bytes()).hexdigest() == RECEIPT_SHA
    old = json.loads(config.read_bytes())
    new = json.loads(config.read_bytes())
    images = manifest['images']
    old_services = ('api','worker','business-worker','golden-scheduler','golden-grader','web')
    new_names = ('native-coordinator','private-scoring-coordinator')
    services = old_services + new_names
    for name in old_services:
        expected = ('e0a51d10e47019598127e8a9d3131ad7ca566bef93b014068753778979a515b2' if name.startswith('golden-')
            else '75d4116c83a36f3583380342fac2807cca6fb5878b111891b6d3038c387f0334' if name == 'web'
            else 'da7793db67a9c2587f45728e2a302bbf2b1bda00ddf74afd8ed29bdb73d87e3a')
        assert old['services'][name]['image'].endswith('sha256:'+expected)
        new['services'][name]['image'] = images['kyc-runtime' if name.startswith('golden-') else 'web' if name == 'web' else 'backend']
    new['services']['migrate']['image'] = images['backend']
    new['services']['migrate']['command'] = ['python','-m','alembic','-c','services/backend/alembic.ini','upgrade','133']
    for name in set(old['services']) - set(old_services) - {'migrate'}:
        assert new['services'][name] == old['services'][name]
    wiring_path = root/'runtime-functional/controls-2fad3bc/infra/gcp/qa_native_wiring.py'
    assert hashlib.sha256(wiring_path.read_bytes()).hexdigest() == manifest['operational_files']['infra/gcp/qa_native_wiring.py']
    spec = importlib.util.spec_from_file_location('qa_native_wiring',wiring_path)
    wiring = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wiring)
    new = wiring.apply(new,images['kyc-runtime'],images['kyc-runtime'].rsplit('sha256:',1)[1])
    for name in services:
        bind_map(name,new['services'][name].get('volumes',[]))
    backup = root/'backups/qualification-08d45ff-services-v2'
    backup.mkdir(mode=0o700)
    shutil.copy2(config,backup/config.name)

    def run(*arguments):
        path = backup/('command-'+str(time.monotonic_ns()))
        try:
            result = subprocess.run(arguments,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
        except subprocess.TimeoutExpired as error:
            for suffix,data in (('stdout',error.stdout or b''),('stderr',error.stderr or b'')):
                with os.fdopen(os.open(str(path)+'.partial.'+suffix,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as out:
                    out.write(data)
            raise RuntimeError('QA service operation outcome unknown; retained without replay') from error
        for suffix,data in (('stdout',result.stdout),('stderr',result.stderr)):
            with os.fdopen(os.open(str(path)+'.'+suffix,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as out:
                out.write(data)
        assert result.returncode == 0, 'QA service operation failed; private diagnostics retained'
        return result.stdout

    def versions():
        command = 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -A -t -c "SELECT max(version) FROM anvil.schema_versions; SELECT version_num FROM anvil.alembic_version"'
        return run('docker','exec','anvil-qa-v1-postgres-1','sh','-c',command).decode().strip().splitlines()

    def inspected(name):
        values = json.loads(run('docker','inspect','anvil-qa-v1-'+name+'-1'))
        assert len(values) == 1 and re.fullmatch('[a-f0-9]{64}',values[0]['Id'])
        info = values[0]
        assert info['Name'] == '/anvil-qa-v1-'+name+'-1'
        assert info['Config']['Labels']['com.docker.compose.project'] == 'anvil-qa-v1'
        assert info['Config']['Labels']['com.docker.compose.service'] == name
        return info

    def candidate(name, info, running):
        desired = new['services'][name]
        assert info['State']['Running'] is running and not info['State']['Restarting'] and info['RestartCount'] == 0
        assert not info['State'].get('OOMKilled') and not info['State'].get('Dead') and not info['State'].get('Error')
        if not running:
            assert info['State']['ExitCode'] in {0,137,143}, 'Reconcile a failed coordinator before service retry'
        assert (info['State']['Pid'] > 0) if running else (info['State']['Pid'] == 0)
        assert info['Config']['Image'] == desired['image'] and info['Config']['Labels']['org.opencontainers.image.revision'] == REVISION
        mounts = [item for item in info['Mounts'] if item['Type'] == 'bind']
        actual = {item['Destination']:(item['Source'],not item['RW']) for item in mounts}
        assert len(actual) == len(mounts) and actual == bind_map(name,desired.get('volumes',[]))
        expected_tmpfs = {item.split(':',1)[0] for item in desired.get('tmpfs',[])}
        assert set(info['HostConfig'].get('Tmpfs') or {}) == expected_tmpfs
        assert all(item['Type'] == 'bind' or item['Type'] == 'tmpfs' and item['Destination'] in expected_tmpfs for item in info['Mounts'])
        if name in new_names:
            host = info['HostConfig']
            assert info['Config']['User'] == '0:0' and host['NetworkMode'] == 'none' and host['ReadonlyRootfs'] and not host['Privileged']
            assert {item.removeprefix('CAP_') for item in host.get('CapAdd') or []} == set(desired['cap_add'])
            assert host['CapDrop'] == ['ALL'] and host.get('PidMode','') == ('host' if name == 'native-coordinator' else '')
            assert set(host['SecurityOpt']) in (set(desired['security_opt']),set(desired['security_opt'])|{'label=disable'})
        env = dict(item.split('=',1) for item in info['Config']['Env'] if '=' in item)
        for flag in ('ANVIL_LIVE_PROVIDERS_ENABLED','ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED','ANVIL_PRAXIS_TEMPLATE_CALLS_ENABLED','ANVIL_REAL_EMAIL_ENABLED'):
            assert env.get(flag,'false') == 'false'

    assert versions() == ['133','133'], 'Do not replay migration or accept another schema'
    assert shutil.disk_usage('/').free > 10*1024**3
    for name in old_services:
        info = inspected(name)
        assert info['State']['Running'] and info['Config']['Image'] == old['services'][name]['image']
        assert info['Config']['Labels']['org.opencontainers.image.revision'] == '151d6fbdea701be0d1f1c02bd869456c8dbad318'
    reconciled = {}
    for name in new_names:
        info = inspected(name)
        candidate(name,info,False)
        reconciled[name] = info['Id']
    temporary = config.with_name('compose-qualification-08d45ff-services-v2.json')
    with os.fdopen(os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as out:
        json.dump(new,out,indent=2)
    run('docker','compose','-p','anvil-qa-v1','-f',str(temporary),'config','--quiet')
    assert versions() == ['133','133']
    with os.fdopen(os.open(backup/'service-retry-intent.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as out:
        json.dump({'revision':REVISION,'migration_replayed':False,'schema':133,'prior_owned_stopped_ids':reconciled,'attempts':1},out)
        out.flush()
        os.fsync(out.fileno())
    compose = ['docker','compose','-p','anvil-qa-v1','-f',str(config)]
    try:
        os.replace(temporary,config)
        run(*compose,'up','-d','--no-deps',*services)
        for attempt in range(45):
            try:
                for url in ('https://anvil-qa.adi-labs.ai/api/v1/health','https://anvil-qa.adi-labs.ai/workspace'):
                    with urllib.request.urlopen(url,timeout=5) as response:
                        assert response.status == 200
                break
            except Exception:
                if attempt == 44:
                    raise
                time.sleep(1)
        observed = {}
        for name in services:
            info = inspected(name)
            candidate(name,info,True)
            observed[name] = {'id':info['Id'],'image':info['Config']['Image'],'running':True,'restarts':0}
        assert versions() == ['133','133'] and hashlib.sha256(qualification.read_bytes()).hexdigest() == RECEIPT_SHA
        result = {'revision':REVISION,'schema':133,'services':observed,'migration_replayed':False,
            'technical_component_receipt_sha256':RECEIPT_SHA,'project_qualification_granted':False,'live_calls_enabled':False}
        with os.fdopen(os.open(backup/'rollout-summary.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as out:
            json.dump(result,out,indent=2)
        print(json.dumps(result))
    except BaseException:
        shutil.copy2(backup/config.name,config)
        failures = []
        for name in new_names:
            try:
                info = inspected(name)
                assert info['Config']['Image'] == images['kyc-runtime'] and info['Config']['Labels']['org.opencontainers.image.revision'] == REVISION
                run('docker','stop','--time','6',info['Id'])
                after = inspected(name)
                assert after['Id'] == info['Id'] and not after['State']['Running'] and after['State']['Pid'] == 0 and not after['State']['Restarting']
            except Exception as error:
                failures.append({'service':name,'error_type':type(error).__name__})
        try:
            run(*compose,'up','-d','--no-deps',*old_services)
            for name in old_services:
                info = inspected(name)
                assert info['State']['Running'] and info['Config']['Image'] == old['services'][name]['image']
        except Exception as error:
            failures.append({'service':'old-service-restore','error_type':type(error).__name__})
        with os.fdopen(os.open(backup/'rollback-outcome.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as out:
            json.dump({'failures':failures,'schema133_retained':True},out)
        if failures:
            raise RuntimeError('QA rollback incomplete; reconcile owned state without replay') from None
        print('QA service-only retry rolled back; schema133 retained',flush=True)
        raise


if __name__ == '__main__':
    main()
