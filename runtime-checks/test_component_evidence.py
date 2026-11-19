"""Fail-closed evidence parser controls, not installed qualification."""

import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / "infra/gcp/qualify_native_components.py"
spec = importlib.util.spec_from_file_location("component_aggregation", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EvidenceControls(unittest.TestCase):
    def test_only_one_affirmative_no_new_privileges_spelling_is_accepted(self):
        for value in (["no-new-privileges"], ["no-new-privileges:true"]):
            self.assertTrue(module.no_new_privileges(value))
        for value in ([], ["no-new-privileges:false"], ["no-new-privileges=false"],
                      ["no-new-privileges", "no-new-privileges:false"],
                      ["no-new-privileges", "no-new-privileges:true"],
                      ["no-new-privileges", "no-new-privileges"], "no-new-privileges", [True]):
            self.assertFalse(module.no_new_privileges(value))

    def test_curator_hashes_exact_canonical_unicode_seal_without_host_reformatting(self):
        from anvil.praxis_generic_contract import canonical, digest

        spec = importlib.util.spec_from_file_location("evidence_curator", Path(__file__).with_name("curate_component_evidence.py"))
        curator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(curator)
        seal = {"components": {"backend": {"source": "/sealed/é/𝄞", "version": "3.12"}}}
        body = {"assets": {"runtime_seal": seal}, "request": {"original_deadline_monotonic": 123.5}}
        binding = curator.sealed_plan_binding(canonical(body))
        self.assertEqual(binding["seal_sha256"], digest(seal))
        self.assertEqual(binding["plan_sha256"], digest(body))
        self.assertEqual(binding["original_deadline_monotonic"], 123.5)
        with self.assertRaises(ValueError):
            curator.sealed_plan_binding(canonical(body | {"runtime_seal": seal}))

    def test_actor_time_consumes_verifier_allowance_under_original_cutoff(self):
        from anvil.environment_harbor import FixedDeadline

        with patch("anvil.environment_harbor.time.monotonic", return_value=100):
            deadline = FixedDeadline(390)
        deadline.ends = min(deadline.ends, 400)  # Original worker's five-minute cutoff.
        with patch("anvil.environment_harbor.time.monotonic", return_value=350):
            self.assertEqual(deadline.remaining(300), 50)
        with patch("anvil.environment_harbor.time.monotonic", return_value=400):
            with self.assertRaises(TimeoutError):
                deadline.remaining(300)

    def test_duplicate_environment_cannot_hide_a_secret_override(self):
        with self.assertRaises(ValueError):
            module.environment(["MODE=safe", "MODE=unsafe"])

    def test_duplicate_or_nonbind_mounts_cannot_hide_private_exposure(self):
        mount = {"Type": "bind", "Destination": "/bridge", "Source": "/bridge", "RW": True}
        for values in ([mount, mount | {"Source": "/private"}], [mount | {"Type": "volume"}]):
            with self.assertRaises(ValueError):
                module.mounts({"Mounts": values})

    def test_root_sdk_profile_rejects_extra_capabilities_and_wrong_namespaces(self):
        info = {"Config": {"User": "0:0", "Image": "synthetic-not-an-image"}, "Image": "synthetic",
            "Mounts": [], "HostConfig": {"CapDrop": ["ALL"], "CapAdd": ["CAP_SYS_PTRACE"],
                "PidMode": "host", "UTSMode": "host", "UsernsMode": "host", "CgroupnsMode": "host",
                "SecurityOpt": ["no-new-privileges", "apparmor=unconfined"], "Tmpfs": {}, "Memory": 1, "PidsLimit": 1, "NanoCpus": 1}}
        self.assertEqual(module.static_sdk_profile(info, {"SYS_PTRACE"})["capabilities"], ["SYS_PTRACE"])
        for key, value in (("CapAdd", ["SYS_PTRACE", "SYS_ADMIN"]), ("CapDrop", []), ("PidMode", ""),
                           ("SecurityOpt", ["no-new-privileges:false", "apparmor=unconfined"])):
            changed = deepcopy(info)
            changed["HostConfig"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                module.static_sdk_profile(changed, {"SYS_PTRACE"})


if __name__ == "__main__":
    unittest.main()
