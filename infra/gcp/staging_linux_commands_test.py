import copy
import json
from pathlib import Path
import unittest
from staging_linux_commands import commands


class NativePlan(unittest.TestCase):
    def test_review_commands_safe_before_approval(self):
        plan = json.loads(Path(__file__).with_name("staging-linux-test-host-plan.json").read_text())
        self.assertTrue(commands(plan))
        plan["bindings"].update(source_sha="a" * 40, source_archive_sha256="b" * 64)
        self.assertTrue(commands(plan))
        plan["approval_record"] = "manufactured-test-only"
        output = commands(plan)
        create = next(cmd for cmd in output if "instances" in cmd and "create" in cmd)
        for cmd in output:
            self.assertEqual(cmd[0], "env")
            self.assertIn("/Users/vasudevansundarababu/Documents/Codex/anvil-tools/google-cloud-sdk/bin/gcloud", cmd)
            self.assertIn("CLOUDSDK_CONFIG=/Users/vasudevansundarababu/Documents/Codex/anvil-tools/cloud-config", cmd)
            self.assertNotIn("gcloud", cmd)
        for flag in ("--no-address", "--no-service-account", "--no-scopes", "--termination-time=2026-11-15T19:30:00Z", "--instance-termination-action=STOP"):
            self.assertIn(flag, create)
        self.assertNotIn("--max-run-duration", " ".join(create))
        changed = copy.deepcopy(plan)
        changed["project"] = "praxis"
        with self.assertRaises(ValueError):
            commands(changed)


if __name__ == "__main__":
    unittest.main()
