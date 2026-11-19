"""Local parser controls only; importing this module performs no cloud action."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('qa_service_retry', Path(__file__).with_name('qa_services_retry_20261119.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MountControls(unittest.TestCase):
    def test_exact_observed_legacy_groups_preserve_rw(self):
        for role, values in module.LEGACY.items():
            with self.subTest(role=role):
                result = module.bind_map(role, sorted(values))
                self.assertEqual(len(result), len(values))
                self.assertTrue(all(not value[1] for value in result.values()))

    def test_generated_readonly_binding_preserves_mode(self):
        value = {'type':'bind', 'source':'/var/lib/anvil-qa-v1/runtime-functional/harbor-proof/component-qualification',
                 'target':'/app/.data/component-qualification', 'read_only':True}
        self.assertEqual(module.bind_map('api',[value]), {value['target']:(value['source'],True)})

    def test_unsafe_or_unreviewed_representations_fail_closed(self):
        value = {'type':'bind', 'source':'/safe/source', 'target':'/safe/target', 'read_only':True}
        faults = [('api',['named:/target']), ('api',['/unknown:/target']),
            ('worker',sorted(module.LEGACY['api'])), ('api',[value,value]),
            ('api',[value|{'read_only':'true'}]), ('api',[value|{'type':'volume'}]),
            ('api',[value|{'target':'relative'}]), ('api',[value|{'source':'/a/../b'}]),
            ('api',[value|{'source':'/a/$BAD'}]), ('api',[value|{'source':'/a/~bad'}]),
            ('api',[value|{'source':'/a'+chr(0)+'b'}]), ('api',[value|{'target':'/app//duplicate'}]),
            ('api',[value|{'extra':True}]),
            ('api',[next(iter(module.LEGACY['api']))+':ro'])]
        for role, values in faults:
            with self.subTest(role=role, values=repr(values)):
                with self.assertRaises(AssertionError):
                    module.bind_map(role,values)


if __name__ == '__main__':
    unittest.main()
