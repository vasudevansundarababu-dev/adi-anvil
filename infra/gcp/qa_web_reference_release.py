"""One exact QA web-only replacement; no backend/runtime/data operations."""

import argparse
import copy
import hashlib
import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/var/lib/anvil-qa-v1')
REVISION = '06fdab43dc111515ffb7af1e8871c0b300a69515'
INTENT = 'web-reference-06fdab4-v2'
BASELINE_WEB_ID = 'a71c607c9378ea3f1cb3fc35513c25547c41b769e60496e4c6426b52d508464c'
CONFIG_SHA = '2c2046ee44311b9478f008e5dbe75cbd1b6676082b386d9c6c11b761f9d1dcbc'
COMPONENT_SHA = '3b2ae3bee8c472ec627a212c24350576ead069bbc09353c6d1106fb1bccbad0d'
CAPTURE_SHA = 'be7bb48642cb448877635a93d4900cd6e586fe3f0685877c142e20104203553a'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ServiceAbsent(Exception):
    pass


def inspect(identifier):
    result = subprocess.run(['docker', 'inspect', identifier], capture_output=True, timeout=15)
    if result.returncode:
        if result.returncode == 1 and (b'no such object:' in result.stderr.lower() or b'no such container:' in result.stderr.lower()):
            raise ServiceAbsent(identifier)
        raise RuntimeError('Docker identity observation failed; absence not established')
    return json.loads(result.stdout)[0]


def schema():
    command = 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -A -t -c "SELECT max(version) FROM anvil.schema_versions; SELECT version_num FROM anvil.alembic_version"'
    rows = subprocess.check_output(['docker', 'exec', 'anvil-qa-v1-postgres-1', 'sh', '-c', command], timeout=15).decode().strip().splitlines()
    if rows != ['133', '133']:
        raise ValueError('Exact schema/Alembic133 required; never run migrate')


def owned_candidate(info, image):
    labels = info['Config']['Labels']
    return (info['Name'] == '/anvil-qa-v1-web-1' and info['Config']['Image'] == image
            and labels.get('com.docker.compose.project') == 'anvil-qa-v1'
            and labels.get('com.docker.compose.service') == 'web'
            and labels.get('org.opencontainers.image.revision') == REVISION
            and labels.get('io.adi.forge.release_intent') == INTENT)


def environment(items):
    if any('=' not in item for item in items):
        raise ValueError('Malformed web environment')
    pairs = [item.split('=', 1) for item in items]
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError('Duplicate web environment key')
    return dict(pairs)


def profile(info):
    """Retain complete security profile without exporting environment values."""
    return {'Id': info['Id'], 'Name': info['Name'], 'State': info['State'],
            'RestartCount': info['RestartCount'], 'HostConfig': info['HostConfig'],
            'Mounts': info['Mounts'], 'Path': info['Path'], 'Args': info['Args'],
            'Config': {key: info['Config'][key] for key in ('Image', 'User', 'Entrypoint', 'Cmd', 'Labels')},
            'environment_map_sha256': sha(json.dumps(environment(info['Config']['Env']), sort_keys=True).encode()),
            'environment_order_sha256': sha(json.dumps(info['Config']['Env']).encode())}


def write(path, raw):
    with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600), 'wb') as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    sync(path.parent)


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def main(image):
    if os.geteuid() != 0 or os.uname().nodename != 'anvil-qa-v1':
        raise ValueError('Existing QA root operator only')
    if not image.startswith('us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/web@sha256:') or len(image.rsplit(':', 1)[1]) != 64:
        raise ValueError('Exact immutable QA web digest required')
    os.umask(0o077)
    config = ROOT / 'config/compose-app.json'
    old_raw = config.read_bytes()
    if sha(old_raw) != CONFIG_SHA:
        raise ValueError('Exact reviewed config baseline required')
    baseline = json.loads((ROOT / 'backups/qualification-39cb2d9/rollout-summary.json').read_bytes())
    rollback_raw = (ROOT / 'backups/web-reference-06fdab4/rollback.json').read_bytes()
    prior_rollback = json.loads(rollback_raw)
    if (prior_rollback.get('old_config_restored') is not True
            or prior_rollback.get('owned_web_restored') is not True
            or prior_rollback.get('restored_id') != BASELINE_WEB_ID or prior_rollback.get('failures')):
        raise ValueError('Exact terminal first-attempt rollback reconciliation required')
    baseline['services']['web']['id'] = BASELINE_WEB_ID
    before = {}
    for name, expected in baseline['services'].items():
        info = inspect('anvil-qa-v1-' + name + '-1')
        if (info['Id'] != expected['id'] or info['Config']['Image'] != expected['image']
                or not info['State']['Running'] or info['RestartCount']):
            raise ValueError('Exact eight-service baseline required')
        before[name] = info
    receipts = {
        ROOT / 'runtime-functional/harbor-proof/component-qualification/current.json': COMPONENT_SHA,
        ROOT / 'runtime-functional/capture-database-qualification/current.json': CAPTURE_SHA,
    }
    for path, pin in receipts.items():
        raw = path.read_bytes()
        if sha(raw) != pin or datetime.fromisoformat(json.loads(raw)['expires_at'].replace('Z', '+00:00')) <= datetime.now(timezone.utc):
            raise ValueError('Exact current unexpired qualification required')
    schema()
    subprocess.run(['docker', 'pull', image], check=True, capture_output=True, timeout=180)
    built = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image], timeout=15))[0]
    if built['Config']['Labels']['org.opencontainers.image.revision'] != REVISION:
        raise ValueError('Actual web revision mismatch')
    new = copy.deepcopy(json.loads(old_raw))
    new['services']['web']['image'] = image
    new['services']['web'].setdefault('labels', {})['io.adi.forge.release_intent'] = INTENT
    new_raw = json.dumps(new, sort_keys=True).encode()
    backup = ROOT / 'backups/web-reference-06fdab4-v2'
    backup.mkdir(mode=0o700)
    sync(backup.parent)
    write(backup / 'compose-old.json', old_raw)
    write(backup / 'compose-new.json', new_raw)
    write(backup / 'old-web-profile.json', json.dumps(profile(before['web']), sort_keys=True).encode())
    subprocess.run(['docker', 'compose', '-p', 'anvil-qa-v1', '-f', str(backup / 'compose-new.json'), 'config', '--quiet'],
                   check=True, capture_output=True, timeout=30)
    if sha(config.read_bytes()) != CONFIG_SHA:
        raise ValueError('Serving config changed before intent')
    write(backup / 'intent.json', json.dumps({'revision': REVISION, 'scope': 'web_only', 'image': image,
        'old_id': before['web']['Id'], 'old_config_sha256': CONFIG_SHA, 'new_config_sha256': sha(new_raw),
        'previous_rollback_sha256': sha(rollback_raw),
        'other_services': baseline['services'], 'migration_replayed': False}).encode())

    def activate(raw, suffix):
        temporary = config.with_name('web-reference-' + suffix + '.json')
        write(temporary, raw)
        os.replace(temporary, config)
        sync(config.parent)

    def up():
        subprocess.run(['docker', 'compose', '-p', 'anvil-qa-v1', '-f', str(config), 'up', '-d',
                        '--no-deps', '--force-recreate', '--no-build', 'web'],
                       check=True, capture_output=True, timeout=180)

    terminal_operation = False
    phase = 'activate-config'
    try:
        activate(new_raw, 'candidate')
        phase = 'compose-up-web'
        try:
            up()
        except subprocess.CalledProcessError:
            terminal_operation = True
            raise
        terminal_operation = True
        phase = 'candidate-identity'
        candidate = inspect('anvil-qa-v1-web-1')
        write(backup / 'candidate-web-profile.json', json.dumps(profile(candidate), sort_keys=True).encode())
        if not owned_candidate(candidate, image) or not candidate['State']['Running'] or candidate['RestartCount']:
            raise ValueError('Actual owned healthy web candidate required')
        old = before['web']
        # No runtime identity/security/resource/mount change accompanies this UI.
        phase = 'runtime-command-configuration'
        for field in ('User', 'Entrypoint', 'Cmd'):
            if candidate['Config'][field] != old['Config'][field]:
                raise ValueError('Web runtime configuration changed')
        if candidate['Path'] != old['Path'] or candidate['Args'] != old['Args']:
            raise ValueError('Web ordered runtime command changed')
        phase = 'environment-exact-mapping'
        if environment(candidate['Config']['Env']) != environment(old['Config']['Env']):
            raise ValueError('Web environment key/value changed')
        phase = 'host-security-resource-profile'
        if candidate['HostConfig'] != old['HostConfig']:
            # Docker sets container-specific runtime bookkeeping independently.
            ignored = {'ContainerIDFile'}
            if {k: v for k, v in candidate['HostConfig'].items() if k not in ignored} != {k: v for k, v in old['HostConfig'].items() if k not in ignored}:
                raise ValueError('Web HostConfig changed')
        phase = 'mount-profile'
        if candidate['Mounts'] != old['Mounts']:
            raise ValueError('Web mounts changed')
        until = time.monotonic() + 120
        phase = 'workspace-http-health'
        while True:
            try:
                with urllib.request.urlopen('https://anvil-qa.adi-labs.ai/workspace', timeout=5) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
            if time.monotonic() >= until:
                raise ValueError('Workspace health failed')
            time.sleep(2)
        phase = 'preserved-seven-services'
        for name, info in before.items():
            if name == 'web':
                continue
            actual = inspect('anvil-qa-v1-' + name + '-1')
            if actual['Id'] != info['Id'] or actual['RestartCount'] != info['RestartCount'] or not actual['State']['Running']:
                raise ValueError('A preserved service changed')
        phase = 'qualification-receipt-pins'
        for path, pin in receipts.items():
            if sha(path.read_bytes()) != pin:
                raise ValueError('Qualification changed during web-only release')
        phase = 'schema-readback'
        schema()
        result = {'status': 'web_only_deployed_requires_ui_acceptance', 'revision': REVISION,
                  'web_id': candidate['Id'], 'web_image': image, 'config_sha256': sha(config.read_bytes()),
                  'other_seven_ids_unchanged': True, 'qualification_receipts_unchanged': True,
                  'schema': 133, 'alembic': '133', 'migration_replayed': False, 'paid_calls': False}
        write(backup / 'result.json', json.dumps(result).encode())
        print(json.dumps(result))
    except BaseException as failure:
        # Restore the durable config even when Docker identity inspection fails.
        # An unknown service/daemon outcome never authorizes recreation.
        result = {'old_config_restored': False, 'owned_web_restored': False,
                  'no_other_services_touched': True, 'failures': [],
                  'primary': {'phase': phase, 'error_type': type(failure).__name__,
                              'returncode': failure.returncode if isinstance(failure, subprocess.CalledProcessError) else None,
                              'timeout': isinstance(failure, subprocess.TimeoutExpired)}}
        for name, raw in (('stdout', getattr(failure, 'stdout', None)), ('stderr', getattr(failure, 'stderr', None))):
            if type(raw) is bytes:
                try:
                    write(backup / ('primary.private.' + name), raw)
                except OSError as error:
                    result['failures'].append({'phase': 'retain-private-diagnostic', 'error_type': type(error).__name__})
        try:
            activate(old_raw, 'rollback')
            result['old_config_restored'] = sha(config.read_bytes()) == CONFIG_SHA
        except BaseException as error:
            result['failures'].append({'phase': 'restore-config', 'error_type': type(error).__name__})
        safe = False
        try:
            actual = inspect('anvil-qa-v1-web-1')
            safe = actual['Id'] == before['web']['Id'] or owned_candidate(actual, image)
            result['observed_id'] = actual['Id']
        except ServiceAbsent:
            result['absence_proven'] = True
            safe = terminal_operation
        except BaseException as error:
            result['failures'].append({'phase': 'observe-web', 'error_type': type(error).__name__})
        if safe and result['old_config_restored']:
            try:
                up()
                restored = inspect('anvil-qa-v1-web-1')
                labels = restored['Config']['Labels']
                if (restored['Config']['Image'] != before['web']['Config']['Image']
                        or labels.get('org.opencontainers.image.revision') != '39cb2d96418fd029f7c87274941b00639d12d87a'
                        or labels.get('com.docker.compose.project') != 'anvil-qa-v1'
                        or labels.get('com.docker.compose.service') != 'web'
                        or not restored['State']['Running'] or restored['State']['Pid'] <= 0):
                    raise ValueError('Actual restored old web identity/state not verified')
                result['owned_web_restored'] = True
                result['restored_id'] = restored['Id']
            except BaseException as error:
                result['failures'].append({'phase': 'restore-web', 'error_type': type(error).__name__})
        write(backup / 'rollback.json', json.dumps(result).encode())
        raise RuntimeError('Web candidate failed; retained evidence requires reconciliation, never blind replay') from None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    main(parser.parse_args().image)
