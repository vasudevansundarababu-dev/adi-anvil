"""Readiness software controls: no DB, providers or cloud access."""

import importlib.util
import io
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

SPEC = importlib.util.spec_from_file_location('deployment_readiness_test_target',
    Path(__file__).resolve().parents[2] / 'src/anvil/deployment_readiness.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReadinessControls(unittest.TestCase):
    def setUp(self):
        MODULE._slot = threading.BoundedSemaphore(1)

    def test_unauthenticated_or_wrong_header_never_starts_worker(self):
        app = FastAPI()
        app.include_router(MODULE.routes())
        config = SimpleNamespace(setting=lambda key: 'synthetic-session-secret-32-bytes-long')
        with patch.dict(sys.modules, {'anvil.config': config}), patch.object(MODULE, 'bounded_check') as check:
            client = TestClient(app)
            for headers in ({}, {'x-anvil-readiness': '0' * 64}):
                response = client.get('/api/v1/internal/deployment-ready', headers=headers)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {'detail': 'Not found'})
            check.assert_not_called()

    def test_status_only_failure_and_exact_both_database_success(self):
        secret = 'synthetic-session-secret-32-bytes-long'
        app = FastAPI()
        app.include_router(MODULE.routes())
        config = SimpleNamespace(setting=lambda key: secret)
        with patch.dict(sys.modules, {'anvil.config': config}), patch.object(MODULE, 'bounded_check', side_effect=[False, True]):
            client = TestClient(app)
            headers = {'x-anvil-readiness': MODULE.token(secret)}
            failed = client.get('/api/v1/internal/deployment-ready', headers=headers)
            self.assertEqual((failed.status_code, failed.json()), (503, {'data': {'status': 'unready'}}))
            ready = client.get('/api/v1/internal/deployment-ready', headers=headers)
            self.assertEqual((ready.status_code, ready.json()), (200, {'data': {'postgres': 'ready', 'neo4j': 'ready'}}))

    def test_partial_or_nonzero_child_cannot_qualify(self):
        for output, code in [(b'{"postgres":"ready"}', 0), (MODULE.READY, 1), (MODULE.READY, 0)]:
            child = SimpleNamespace(returncode=code, stdout=SimpleNamespace(close=lambda: None),
                communicate=lambda timeout: (output, None), poll=lambda: code, wait=lambda timeout: code)
            with patch.object(MODULE.subprocess, 'Popen', return_value=child):
                self.assertEqual(MODULE.bounded_check(), output == MODULE.READY and code == 0)

    def test_concurrent_request_does_not_spawn_another_process(self):
        MODULE._slot.acquire()
        with patch.object(MODULE.subprocess, 'Popen') as spawn:
            self.assertFalse(MODULE.bounded_check())
            spawn.assert_not_called()
        MODULE._slot.release()

    def test_worker_rejects_bad_neo_credentials_wrong_result_and_pg_only_success(self):
        for neo_value in (RuntimeError('synthetic-private-credential'), {'anvil_neo_ready': True},
                          {'wrong_column': 1}, {'anvil_neo_ready': 1}):
            events = []

            class Context:
                def __init__(self, name):
                    self.name = name

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    events.append('close_' + self.name)

                def execute(self, query):
                    self.query = query
                    return self

                def fetchone(self):
                    return (1,)

                def session(self, **kwargs):
                    self_kwargs = kwargs
                    self_test.assertEqual(self_kwargs, {'default_access_mode': 'READ'})
                    return Context('session')

                def run(self, query):
                    self_test.assertEqual(query, ('RETURN 1 AS anvil_neo_ready', 2))
                    if isinstance(neo_value, Exception):
                        raise neo_value
                    return self

                def single(self, strict):
                    self_test.assertTrue(strict)
                    return SimpleNamespace(data=lambda: neo_value)

                def consume(self):
                    events.append('consume')

            self_test = self
            output = io.BytesIO()
            modules = {'psycopg': SimpleNamespace(connect=lambda *a, **k: Context('pg')),
                'neo4j': SimpleNamespace(READ_ACCESS='READ', Query=lambda text, timeout: (text, timeout)),
                'anvil.config': SimpleNamespace(setting=lambda key: 'synthetic-only'),
                'anvil.graph': SimpleNamespace(driver=lambda: Context('driver'))}
            with patch.dict(sys.modules, modules), patch.object(MODULE.sys, 'stdout', SimpleNamespace(buffer=output)):
                exit_code = MODULE.worker()
            is_ready = type(neo_value) is dict and neo_value == {'anvil_neo_ready': 1} and type(neo_value.get('anvil_neo_ready')) is int
            self.assertEqual(exit_code, 0 if is_ready else 1)
            self.assertEqual(output.getvalue(), MODULE.READY if is_ready else b'')
            self.assertTrue({'close_pg', 'close_session', 'close_driver'} <= set(events))

    def test_unreaped_child_locks_further_requests_closed(self):
        def fail_kill():
            raise OSError('synthetic kill uncertainty')

        child = SimpleNamespace(returncode=None, stdout=SimpleNamespace(close=lambda: None),
            communicate=lambda timeout: (_ for _ in ()).throw(subprocess.TimeoutExpired('synthetic', timeout)),
            poll=lambda: None, kill=fail_kill)
        with patch.object(MODULE.subprocess, 'Popen', return_value=child) as spawn:
            self.assertFalse(MODULE.bounded_check())
            self.assertFalse(MODULE.bounded_check())
            self.assertEqual(spawn.call_count, 1)

    def test_actual_stuck_python_child_is_killed_and_reaped_within_original_bound(self):
        # Real local software process, no database/network/vendor executable.
        original = subprocess.Popen
        children = []

        def spawn(*args, **kwargs):
            child = original([sys.executable, '-I', '-B', '-c', 'import time; time.sleep(60)'],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                start_new_session=True)
            children.append(child)
            return child

        started = time.monotonic()
        with patch.object(MODULE.subprocess, 'Popen', side_effect=spawn):
            self.assertFalse(MODULE.bounded_check())
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(MODULE._slot.acquire(blocking=False))
        MODULE._slot.release()


if __name__ == '__main__':
    unittest.main()
