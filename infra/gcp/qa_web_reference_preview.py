"""Retain one stopped web profile preview; never start a process or alter serving."""

import hashlib
import json
import os
import subprocess
from pathlib import Path


def run():
    assert os.geteuid() == 0 and os.uname().nodename == 'anvil-qa-v1'
    root = Path('/var/lib/anvil-qa-v1/backups/web-reference-06fdab4/profile-preview-v2')
    root.mkdir(mode=0o700)
    os.umask(0o077)
    old = json.loads(subprocess.check_output(['docker', 'inspect', 'a71c607c9378ea3f1cb3fc35513c25547c41b769e60496e4c6426b52d508464c'], timeout=15))[0]
    assert old['State']['Running'] and old['RestartCount'] == 0 and old['Mounts'] == []
    body = json.loads((root.parent / 'compose-new.json').read_bytes())
    service = body['services']['web']
    assert service['image'] == 'us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/web@sha256:6e5590587a4f1d222535ed321928832c0de4b5556c1919e88dda7cb56539f6fe'
    assert not service.get('ports') and not service.get('volumes')
    built = json.loads(subprocess.check_output(['docker', 'image', 'inspect', service['image']], timeout=15))[0]
    assert not built['Config'].get('Volumes')
    assert built['Config']['Labels']['org.opencontainers.image.revision'] == '06fdab43dc111515ffb7af1e8871c0b300a69515'
    service.pop('depends_on', None)
    service['container_name'] = 'forge-web-reference-profile-preview-06fdab4'
    observation = subprocess.run(['docker', 'inspect', service['container_name']], capture_output=True, timeout=15)
    assert observation.returncode == 1 and (b'no such object:' in observation.stderr.lower() or b'no such container:' in observation.stderr.lower())
    service.setdefault('labels', {})['io.adi.forge.profile_preview'] = 'web-reference-06fdab4-v2'
    service['restart'] = 'no'
    service['networks'] = ['default']
    config = {'services': {'web': service}, 'networks': {
        'default': {'external': True, 'name': old['HostConfig']['NetworkMode']}}}
    path = root / 'compose.json'
    path.write_text(json.dumps(config, sort_keys=True))
    subprocess.run(['docker', 'compose', '-p', 'forge-web-reference-profile-preview', '-f', str(path),
                    'create', '--no-build', '--pull', 'never', 'web'], check=True, capture_output=True, timeout=60)
    new = json.loads(subprocess.check_output(['docker', 'inspect', service['container_name']], timeout=15))[0]
    assert new['Name'] == '/' + service['container_name'] and new['Config']['Image'] == service['image']
    labels = new['Config']['Labels']
    assert labels['com.docker.compose.project'] == 'forge-web-reference-profile-preview'
    assert labels['com.docker.compose.service'] == 'web'
    assert labels['io.adi.forge.profile_preview'] == 'web-reference-06fdab4-v2'
    assert new['State']['Status'] == 'created' and new['State']['Pid'] == 0
    assert new['HostConfig']['RestartPolicy']['Name'] == 'no'

    def env(items):
        assert all('=' in item for item in items)
        pairs = [item.split('=', 1) for item in items]
        assert len({key for key, _ in pairs}) == len(pairs)
        return dict(pairs)

    old_env, new_env = env(old['Config']['Env']), env(new['Config']['Env'])
    result = {'preview_id': new['Id'], 'state': new['State']['Status'], 'pid': new['State']['Pid'],
              'not_started': True, 'environment_unique_keys': True,
              'environment_order_equal': old['Config']['Env'] == new['Config']['Env'],
              'environment_exact_mapping_equal': old_env == new_env,
              'environment_changed_keys': sorted(key for key in old_env.keys() | new_env.keys() if old_env.get(key) != new_env.get(key)),
              'command_equal': all(old['Config'][key] == new['Config'][key] for key in ('User', 'Entrypoint', 'Cmd')),
              'hostconfig_differences': {key: {'old': old['HostConfig'].get(key), 'preview': new['HostConfig'].get(key)}
                  for key in old['HostConfig'].keys() | new['HostConfig'].keys() if old['HostConfig'].get(key) != new['HostConfig'].get(key)},
              'mounts_equal': old['Mounts'] == new['Mounts'],
              'serving_web_id': old['Id'], 'image': service['image']}
    raw = json.dumps(result, sort_keys=True).encode()
    (root / 'result.json').write_bytes(raw)
    print(json.dumps({'result': result, 'sha256': hashlib.sha256(raw).hexdigest()}))


if __name__ == '__main__':
    run()
