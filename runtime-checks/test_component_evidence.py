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
