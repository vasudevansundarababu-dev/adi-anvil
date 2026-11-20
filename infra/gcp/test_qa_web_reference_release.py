"""Rollback must never recreate a service based only on its familiar name."""

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from infra.gcp import qa_web_reference_release as release
from infra.gcp.qa_web_reference_release import INTENT, REVISION, owned_candidate


class Ownership(unittest.TestCase):
    def setUp(self):
        self.image = 'registry.invalid/web@sha256:' + 'a' * 64
        self.info = {'Name': '/anvil-qa-v1-web-1', 'Config': {'Image': self.image, 'Labels': {
            'com.docker.compose.project': 'anvil-qa-v1', 'com.docker.compose.service': 'web',
            'org.opencontainers.image.revision': REVISION, 'io.adi.forge.release_intent': INTENT}}}

    def test_exact_release_identity_is_owned(self):
        self.assertTrue(owned_candidate(self.info, self.image))

    def test_same_name_and_revision_cannot_authorize_unknown_release(self):
        for key in ('com.docker.compose.project', 'com.docker.compose.service',
                    'org.opencontainers.image.revision', 'io.adi.forge.release_intent'):
            with self.subTest(key=key):
                value = copy.deepcopy(self.info)
                value['Config']['Labels'][key] = 'unrelated'
                self.assertFalse(owned_candidate(value, self.image))

    def test_different_image_or_name_is_never_owned(self):
        self.assertFalse(owned_candidate(self.info, self.image + 'b'))
        self.info['Name'] = '/other-web-1'
        self.assertFalse(owned_candidate(self.info, self.image))


class Environment(unittest.TestCase):
    def test_unique_environment_order_has_no_runtime_effect(self):
        self.assertEqual(release.environment(['A=one', 'B=two']), release.environment(['B=two', 'A=one']))

    def test_changed_values_are_not_equal(self):
        self.assertNotEqual(release.environment(['A=one']), release.environment(['A=two']))

    def test_duplicate_or_malformed_environment_is_rejected(self):
        for value in (['A=one', 'A=two'], ['A']):
            with self.subTest(value=value), self.assertRaises(ValueError):
                release.environment(value)


class Absence(unittest.TestCase):
    def test_both_installed_error_casings_prove_absence(self):
        for message in (b'error: no such object: fixture', b'Error: No such object: fixture'):
            with self.subTest(message=message), patch.object(release.subprocess, 'run', return_value=
                    subprocess.CompletedProcess([], 1, b'[]', message)), self.assertRaises(release.ServiceAbsent):
                release.inspect('fixture')

    def test_daemon_failure_is_not_absence(self):
        with patch.object(release.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [], 1, b'', b'Cannot connect to the Docker daemon')), self.assertRaises(RuntimeError):
            release.inspect('fixture')


class Rollback(unittest.TestCase):
    def check_failure(self, observation, restored=None):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as patches:
            root = Path(folder)
            (root / 'config').mkdir()
            (root / 'backups/qualification-39cb2d9').mkdir(parents=True)
            old_raw = json.dumps({'services': {'web': {'image': 'old-web'}}}).encode()
            config = root / 'config/compose-app.json'
            config.write_bytes(old_raw)
            old = {'Id': 'old-id', 'Name': '/anvil-qa-v1-web-1',
                   'Config': {'Image': 'old-web', 'User': 'node', 'Entrypoint': [],
                              'Cmd': [], 'Labels': {}, 'Env': []},
                   'HostConfig': {}, 'Mounts': [], 'Path': 'node', 'Args': [],
                   'State': {'Running': True, 'Pid': 1}, 'RestartCount': 0}
            baseline = {'services': {'web': {'id': 'old-id', 'image': 'old-web'}}}
            (root / 'backups/qualification-39cb2d9/rollout-summary.json').write_text(json.dumps(baseline))
            (root / 'backups/web-reference-06fdab4').mkdir()
            (root / 'backups/web-reference-06fdab4/rollback.json').write_text(json.dumps({
                'old_config_restored': True, 'owned_web_restored': True, 'restored_id': 'old-id', 'failures': []}))
            receipt = b'{"expires_at":"2099-01-01T00:00:00Z"}'
            for suffix in ('harbor-proof/component-qualification', 'capture-database-qualification'):
                path = root / 'runtime-functional' / suffix
                path.mkdir(parents=True)
                (path / 'current.json').write_bytes(receipt)
            for key, value in {'ROOT': root, 'CONFIG_SHA': hashlib.sha256(old_raw).hexdigest(),
                               'BASELINE_WEB_ID': 'old-id',
                               'COMPONENT_SHA': hashlib.sha256(receipt).hexdigest(),
                               'CAPTURE_SHA': hashlib.sha256(receipt).hexdigest()}.items():
                patches.enter_context(patch.object(release, key, value))
            patches.enter_context(patch.object(release.os, 'geteuid', return_value=0))
            patches.enter_context(patch.object(release.os, 'uname', return_value=SimpleNamespace(nodename='anvil-qa-v1')))
            patches.enter_context(patch.object(release, 'schema'))
            observations = [old, observation] + ([restored] if restored is not None else [])
            patches.enter_context(patch.object(release, 'inspect', side_effect=observations))
            patches.enter_context(patch.object(release.subprocess, 'check_output', return_value=json.dumps([
                {'Config': {'Labels': {'org.opencontainers.image.revision': REVISION}}}]).encode()))
            up_calls = []

            def run(command, **kwargs):
                if 'up' in command:
                    up_calls.append(command)
                    if len(up_calls) == 1:
                        raise subprocess.CalledProcessError(1, command)
                return subprocess.CompletedProcess(command, 0)

            patches.enter_context(patch.object(release.subprocess, 'run', side_effect=run))
            with self.assertRaisesRegex(RuntimeError, 'retained evidence'):
                release.main('us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/web@sha256:' + 'a' * 64)
            self.assertEqual(config.read_bytes(), old_raw)
            result = json.loads((root / 'backups/web-reference-06fdab4-v2/rollback.json').read_text())
            return result, up_calls

    def test_unknown_inspection_restores_config_without_recreating(self):
        result, calls = self.check_failure(RuntimeError('daemon outcome unknown'))
        self.assertTrue(result['old_config_restored'])
        self.assertFalse(result['owned_web_restored'])
        self.assertEqual(len(calls), 1)

    def test_terminal_failure_and_proven_absence_restore_verified_old_image(self):
        restored = {'Id': 'restored-id', 'Config': {'Image': 'old-web', 'Labels': {
            'org.opencontainers.image.revision': '39cb2d96418fd029f7c87274941b00639d12d87a',
            'com.docker.compose.project': 'anvil-qa-v1', 'com.docker.compose.service': 'web'}},
            'State': {'Running': True, 'Pid': 42}}
        result, calls = self.check_failure(release.ServiceAbsent(), restored)
        self.assertTrue(result['owned_web_restored'])
        self.assertEqual(result['restored_id'], 'restored-id')
        self.assertEqual(len(calls), 2)

    def test_recreation_ack_alone_does_not_claim_restoration(self):
        restored = {'Config': {'Image': 'wrong-image', 'Labels': {}}}
        result, _ = self.check_failure(release.ServiceAbsent(), restored)
        self.assertFalse(result['owned_web_restored'])


if __name__ == '__main__':
    unittest.main()
