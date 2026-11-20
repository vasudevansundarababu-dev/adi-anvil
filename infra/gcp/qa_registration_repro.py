"""One fresh network-none synthetic cluster; exact API image, no serving data."""

import hashlib
import json
import os
import secrets
import subprocess
import time
from pathlib import Path

BACKEND = 'us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/backend@sha256:41e94e67b009582338415f1f791655902f1fe42e2c97350b7faf7afb8083bf9c'
POSTGRES = 'us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/core-postgres-security@sha256:2bb3e2ab0cea85749f75dd2751ae015075274e89fb3c04736c64d932693927a2'
BASE = Path('/var/lib/anvil-qa-v1/runtime-functional/registration-api41-http1')


def private(path, raw):
    with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    sync(path.parent)


def sync(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    assert os.geteuid() == 0 and os.uname().nodename == 'anvil-qa-v1'
    os.umask(0o077)
    BASE.mkdir(mode=0o700)
    sync(BASE.parent)
    for name in ('owner', 'control', 'scripts', 'data'):
        (BASE / name).mkdir(mode=0o700)
    socket = BASE / 'socket'
    socket.mkdir(mode=0o755)
    socket.chmod(0o755)
    os.chown(socket, 999, 999)
    release_raw = Path('/tmp/forge-qualification-release-39cb2d9.json').read_bytes()
    assert hashlib.sha256(release_raw).hexdigest() == '509abde53df86b2254b9b13994406196953fabfc40a4ab29de0c44507dcd8dbf'
    release = json.loads(release_raw)
    raw = Path('/var/lib/anvil-qa-v1/runtime-functional/controls-39cb2d9/runtime-checks/kyc_sql_fixture_setup.py').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == release['control_files']['runtime-checks/kyc_sql_fixture_setup.py']
    private(BASE / 'scripts/setup.py', raw)
    raw = Path('/tmp/qa_registration_http_worker.py').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '2703d97e4bdc202985984aa3bd98590acc959a4b8fdc86e06e42c1891539af18'
    private(BASE / 'scripts/repro.py', raw)
    (BASE / 'scripts').chmod(0o755)
    (BASE / 'scripts/repro.py').chmod(0o644)
    password = secrets.token_urlsafe(40)
    private(BASE / 'owner/postgres.env', ('POSTGRES_PASSWORD=' + password + '\nPOSTGRES_INITDB_ARGS=--auth-local=scram-sha-256\n').encode())
    private(BASE / 'owner/setup.json', json.dumps({'schema_version': 'anvil.synthetic-sql-fixture-setup.v2',
        'host': '/probe-socket', 'dbname': 'postgres', 'user': 'postgres', 'password': password,
        'new_database': 'anvil_golden_kyc_component_api41_http1', 'runtime_image_sha256': BACKEND.rsplit(':', 1)[1]}).encode())
    pgname = 'forge-registration-api41-http1-postgres'
    for image in (BACKEND, POSTGRES):
        subprocess.run(['docker', 'image', 'inspect', image], check=True, capture_output=True, timeout=15)
    names = {'postgres': pgname, 'setup': 'forge-registration-api41-http1-setup',
             'register': 'forge-registration-api41-http1-register'}
    for name in names.values():
        observed = subprocess.run(['docker', 'inspect', name], capture_output=True, timeout=15)
        assert observed.returncode == 1 and b'no such' in observed.stderr.lower(), 'Fresh diagnostic names must be absent'
    private(BASE / 'intent.json', json.dumps({'scope': 'isolated-registration-api41-http1',
        'containers': names, 'backend': BACKEND, 'postgres': POSTGRES, 'serving_database_used': False}).encode())
    observed = None
    failure = None
    cleanup = {}
    try:
        result = subprocess.run(['docker', 'create', '--pull=never', '--name', pgname,
        '--label', 'io.adi.forge.scope=isolated-registration-api41-http1', '--network', 'none',
        '--memory', '768m', '--pids-limit', '128', '--cpus', '2', '--env-file', str(BASE / 'owner/postgres.env'),
        '--mount', 'type=bind,src=' + str(BASE / 'data') + ',dst=/var/lib/postgresql/data',
        '--mount', 'type=bind,src=' + str(socket) + ',dst=/var/run/postgresql', POSTGRES],
            check=True, capture_output=True, timeout=60)
        pgid = result.stdout.decode().strip()
        private(BASE / 'postgres-id.json', json.dumps({'id': pgid, 'image': POSTGRES}).encode())
        subprocess.run(['docker', 'start', pgid], check=True, capture_output=True, timeout=30)
        for _ in range(60):
            if (socket / '.s.PGSQL.5432').is_socket():
                break
            time.sleep(.5)
        else:
            raise RuntimeError('Isolated cluster startup failed')
        # Verified in this exact cached image's public entrypoint, not guessed.
        assert socket.stat().st_mode & 0o7777 == 0o3775
        common = ['docker', 'create', '--pull=never', '--network', 'none', '--cap-drop', 'ALL',
                  '--security-opt', 'no-new-privileges', '--memory', '2g', '--pids-limit', '256', '--cpus', '2',
                  '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=128m',
                  '-e', 'ANVIL_ENV=local', '-e', 'WEB_ORIGIN=http://127.0.0.1:3202',
                  '-e', 'ANVIL_FIXTURE_MODE=true', '-e', 'ANVIL_GOLDEN_KYC_ENABLED=true',
                  '-e', 'ANVIL_SESSION_KEY=' + secrets.token_urlsafe(40),
                  '-e', 'ANVIL_LIVE_PROVIDERS_ENABLED=false', '-e', 'ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED=false',
                  '-e', 'ANVIL_PRAXIS_TEMPLATE_CALLS_ENABLED=false', '-e', 'ANVIL_REAL_EMAIL_ENABLED=false',
                  '-e', 'ANVIL_RUNTIME_IMAGE_DIGEST=' + BACKEND.rsplit(':', 1)[1],
                  '--mount', 'type=bind,src=' + str(socket) + ',dst=/probe-socket,readonly',
                  '--mount', 'type=bind,src=' + str(BASE / 'scripts') + ',dst=/probe-scripts,readonly',
                  '--mount', 'type=bind,src=' + str(BASE / 'control') + ',dst=/probe-control']
        def execute(phase, args):
            command = common + ['--name', 'forge-registration-api41-http1-' + phase,
                '--label', 'io.adi.forge.scope=isolated-registration-api41-http1', *args]
            created = subprocess.run(command, capture_output=True, check=True, timeout=60)
            identifier = created.stdout.decode().strip()
            private(BASE / (phase + '-id.json'), json.dumps({'id': identifier, 'image': BACKEND}).encode())
            result = subprocess.run(['docker', 'start', '-a', identifier], capture_output=True, timeout=330)
            private(BASE / (phase + '.private.stdout'), result.stdout)
            private(BASE / (phase + '.private.stderr'), result.stderr)
            state = json.loads(subprocess.check_output(['docker', 'inspect', identifier], timeout=15))[0]['State']
            assert result.returncode == 0 and not state['Running'] and state['Pid'] == 0 and state['ExitCode'] == 0, 'Isolated diagnostic failed; retain private evidence, no replay'
            return result.stdout
        execute('setup', ['--read-only', '--user', '0:0', '--mount',
            'type=bind,src=' + str(BASE / 'owner') + ',dst=/probe-owner,readonly',
            '--entrypoint', '/app/services/backend/.venv/bin/python', BACKEND,
            '-I', '-B', '/probe-scripts/setup.py', '--config', '/probe-owner/setup.json', '--output', '/probe-control/control.json'])
        os.chown(BASE / 'control', 10001, 10001)
        os.chown(BASE / 'control/control.json', 10001, 10001)
        # Normal Python settings and writable image match API behavior; no -I/-B.
        output = execute('register', ['--user', '10001:10001', '--entrypoint',
            '/app/services/backend/.venv/bin/python', BACKEND, '/probe-scripts/repro.py'])
        observed = json.loads(output)
    except BaseException as error:
        failure = {'error_type': type(error).__name__}
    finally:
        for phase in ('register', 'setup', 'postgres'):
            try:
                response = subprocess.run(['docker', 'inspect', names[phase]], capture_output=True, timeout=15)
                if response.returncode == 1 and b'no such' in response.stderr.lower():
                    cleanup[phase] = {'state': 'absent'}
                    continue
                assert response.returncode == 0
                info = json.loads(response.stdout)[0]
                image = POSTGRES if phase == 'postgres' else BACKEND
                assert (info['Name'] == '/' + names[phase] and info['Config']['Image'] == image
                        and info['Config']['Labels'].get('io.adi.forge.scope') == 'isolated-registration-api41-http1')
                if info['State']['Running']:
                    subprocess.run(['docker', 'stop', '--time', '5', info['Id']], check=True, capture_output=True, timeout=15)
                terminal = json.loads(subprocess.check_output(['docker', 'inspect', info['Id']], timeout=15))[0]
                assert (terminal['Id'] == info['Id'] and not terminal['State']['Running']
                        and not terminal['State']['Restarting'] and terminal['State']['Pid'] == 0)
                cleanup[phase] = {'id': info['Id'], 'state': terminal['State']['Status'],
                                  'pid': terminal['State']['Pid'], 'exit_code': terminal['State']['ExitCode']}
            except BaseException as error:
                cleanup[phase] = {'state': 'unknown_retained', 'error_type': type(error).__name__}
    final = {'observation': observed, 'failure': failure, 'cleanup': cleanup,
             'qualification_granted': False, 'serving_database_used': False}
    private(BASE / 'result.json', json.dumps(final, sort_keys=True).encode())
    print(json.dumps(final, sort_keys=True))
    if failure or any(value['state'] == 'unknown_retained' for value in cleanup.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
