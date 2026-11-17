"""Fresh-process import/flag controls, never entry-main or native execution."""

import ast
import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / 'services/backend/src'
BASE = textwrap.dedent('''
    import importlib, os, sys
    class ConfigImportRequired(RuntimeError): pass
    def guard(event, args):
        if event == 'import' and args[0] == 'anvil.config':
            raise ConfigImportRequired('API configuration import forbidden in isolated worker')
        if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)) and os.fsdecode(args[0]).endswith('/.env'):
            raise AssertionError('dotenv read forbidden')
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'subprocess.Popen', 'os.fork', 'os.posix_spawn'}:
            raise AssertionError('runtime effect forbidden during import')
    sys.addaudithook(guard)
    import psycopg
    def forbidden(*args, **kwargs): raise AssertionError('database effect forbidden')
    psycopg.connect = forbidden
    psycopg.AsyncConnection.connect = forbidden
''')


class PrivateImportBoundary(unittest.TestCase):
    def run_child(self, code):
        with tempfile.TemporaryDirectory(prefix='anvil-private-import-') as folder:
            Path(folder, '.env').write_text('PRIVATE_IMPORT_DOTENV_CANARY=forbidden\n')
            result = subprocess.run([sys.executable, '-B', '-c', BASE + '\n' + textwrap.dedent(code)],
                env={'PATH': os.defpath, 'ANVIL_ROOT': folder, 'ANVIL_ENV': 'local',
                     'WEB_ORIGIN': 'http://127.0.0.1:3202', 'PYTHONPATH': str(SOURCE)},
                cwd=folder, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_private_entry_imports_never_load_api_config_or_dotenv(self):
        self.run_child('''
            for name in ('anvil.marketing_native_attester_worker', 'anvil.marketing_native_receiver_worker',
                         'anvil.marketing_native_private_control', 'anvil.marketing_native_private_pair',
                         'anvil.marketing_native_helper_process', 'anvil.marketing_paid_graph'):
                importlib.import_module(name)
                assert 'anvil.config' not in sys.modules
                assert 'PRIVATE_IMPORT_DOTENV_CANARY' not in os.environ
            assert 'ANVIL_SESSION_KEY' not in os.environ
            assert 'DATABASE_URL' not in os.environ
            assert 'OPENAI_API_KEY' not in os.environ
        ''')

    def test_api_route_construction_still_demands_original_configuration(self):
        self.run_child('''
            broker = importlib.import_module('anvil.worker_dispatch_broker')
            try:
                broker.routes()
            except ConfigImportRequired:
                pass
            else:
                raise AssertionError('API route construction bypassed full configuration')
        ''')

    def test_worker_flag_matches_original_predicate_for_valid_environments(self):
        path = SOURCE / 'anvil/marketing_native_worker_flags.py'
        spec = importlib.util.spec_from_file_location('isolated_worker_flags', path)
        flags = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(flags)
        original = next(n for n in ast.parse((SOURCE / 'anvil/config.py').read_bytes()).body
                        if isinstance(n, ast.FunctionDef) and n.name == 'harbor_live_enabled')
        for environment in ('local', 'cloud'):
            for value in (None, 'false', 'true', 'TRUE', ''):
                with self.subTest(environment=environment, value=value):
                    name = 'ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED' if environment == 'cloud' else 'ANVIL_LIVE_PROVIDERS_ENABLED'
                    supplied = {'ANVIL_ENV': environment}
                    if value is not None:
                        supplied[name] = value
                    with patch.dict(os.environ, supplied, clear=True):
                        namespace = {'os': os, 'CLOUD': environment == 'cloud'}
                        exec(compile(ast.fix_missing_locations(ast.Module(body=[original], type_ignores=[])),
                                     'original_flag_predicate_only', 'exec'), namespace)
                        self.assertEqual(flags.trusted_worker_live_enabled(), namespace['harbor_live_enabled']())
        for environment in (None, 'staging', 'invalid'):
            supplied = {} if environment is None else {'ANVIL_ENV': environment}
            with patch.dict(os.environ, supplied, clear=True):
                self.assertFalse(flags.trusted_worker_live_enabled())


if __name__ == '__main__':
    unittest.main()
