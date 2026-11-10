import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import overnight_qa_credentials as credentials
from overnight_qa_credentials import EMAIL, ROLES, SECRET, identity
from overnight_qa_lifecycle import DELETE, NAME, PROJECT, validate_vm


class CredentialBoundary(unittest.TestCase):
    def setUp(self):
        self.account = {"email": EMAIL, "uniqueId": "1234567"}
        self.secret = {
            "name": f"projects/123/secrets/{SECRET}",
            "createTime": "2026-11-10T10:00:00Z",
            "labels": {"purpose": "overnight-qa"},
            "replication": {"userManaged": {"replicas": [{"location": "us-west1"}]}},
        }
        self.policy = {
            "bindings": [{"role": r, "members": ["serviceAccount:" + EMAIL]} for r in sorted(ROLES)]
        }

    def check(self, **changes):
        values = {
            "account": self.account,
            "secret": self.secret,
            "policy": self.policy,
            "project_policy": {},
            "project_number": "123",
        }
        values.update(changes)
        return identity(**values)

    def test_exact_secret_scoped_identity(self):
        self.assertTrue(self.check()["secret_only_policy_verified"])

    def test_cleanup_before_retention_never_calls_cloud(self):
        with (
            patch.object(credentials, "datetime") as clock,
            patch.object(credentials, "call") as cloud,
        ):
            clock.now.return_value = datetime(2026, 11, 10, 10, tzinfo=timezone.utc)
            with self.assertRaises(ValueError, msg="retention deadline"):
                credentials.cleanup()
            cloud.assert_not_called()

    def test_partial_cleanup_checks_immutable_identity(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(credentials, "ROOT", Path("/unused")),
        ):
            credentials.ROOT = Path(folder)
            (credentials.ROOT / "credential-identity-public.json").write_text(
                json.dumps(self.check())
            )

            def respond(args):
                if args[:2] == ["compute", "instances"]:
                    return []
                if args[:3] == ["iam", "service-accounts", "list"]:
                    return [{"email": EMAIL, "uniqueId": "replacement"}]
                if args[:2] == ["secrets", "list"]:
                    return []
                self.fail("No deletion or other operation permitted")

            with (
                patch.object(credentials, "datetime") as clock,
                patch.object(credentials, "call", respond),
            ):
                clock.now.return_value = DELETE
                with self.assertRaisesRegex(ValueError, "replaced"):
                    credentials.cleanup()

    def test_partial_cleanup_resumes_only_exact_owned_service_account(self):
        deleted = []
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(credentials, "ROOT", Path(folder)),
        ):
            (credentials.ROOT / "credential-identity-public.json").write_text(
                json.dumps(self.check())
            )

            def respond(args):
                if args[:2] in (["compute", "instances"], ["secrets", "list"]):
                    return []
                if args[:3] == ["iam", "service-accounts", "list"]:
                    return [] if deleted else [self.account]
                if args[:2] == ["projects", "get-iam-policy"]:
                    return {}
                if args == ["iam", "service-accounts", "delete", EMAIL]:
                    deleted.append(EMAIL)
                    return None
                self.fail("Unexpected operation")

            with (
                patch.object(credentials, "datetime") as clock,
                patch.object(credentials, "call", respond),
            ):
                clock.now.return_value = DELETE
                credentials.cleanup()
            self.assertEqual(deleted, [EMAIL])

    def test_project_role_and_wrong_project_refused(self):
        with self.assertRaises(ValueError):
            self.check(
                project_policy={
                    "bindings": [{"role": "roles/editor", "members": ["serviceAccount:" + EMAIL]}]
                }
            )
        with self.assertRaises(ValueError):
            self.check(project_number="999")

    def test_foreign_principal_or_extra_role_refused(self):
        for changed in (
            self.policy["bindings"]
            + [{"role": "roles/owner", "members": ["serviceAccount:" + EMAIL]}],
            [{"role": r, "members": ["allAuthenticatedUsers"]} for r in ROLES],
        ):
            with self.assertRaises(ValueError):
                self.check(policy={"bindings": changed})

    def test_replication_and_replacement_identity_refused(self):
        changed = copy.deepcopy(self.secret)
        changed["replication"] = {"automatic": {}}
        with self.assertRaises(ValueError):
            self.check(secret=changed)
        with self.assertRaises(ValueError):
            self.check(account={"email": "other@example.invalid", "uniqueId": "1234567"})

    def test_vm_never_implicitly_adopts_workload_identity(self):
        prefix = f"https://www.googleapis.com/compute/v1/projects/{PROJECT}/"
        vm = {
            "name": NAME,
            "id": "123",
            "selfLink": prefix + "zones/us-west1-a/instances/" + NAME,
            "machineType": prefix + "zones/us-west1-a/machineTypes/e2-standard-8",
            "labels": {"purpose": "overnight-qa"},
            "scheduling": {
                "automaticRestart": False,
                "instanceTerminationAction": "STOP",
                "terminationTime": "2026-11-11T18:00:00Z",
            },
            "networkInterfaces": [
                {
                    "network": prefix + "global/networks/" + NAME + "-net",
                    "subnetwork": prefix + "regions/us-west1/subnetworks/" + NAME + "-subnet",
                }
            ],
            "disks": [{"source": prefix + "zones/us-west1-a/disks/" + NAME + "-boot"}],
            "serviceAccounts": [
                {"email": EMAIL, "scopes": ["https://www.googleapis.com/auth/cloud-platform"]}
            ],
        }
        now = datetime(2026, 11, 10, 10, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            validate_vm(vm, now=now)
        validate_vm(vm, now=now, credential_identity=self.check())
        vm["serviceAccounts"][0]["scopes"].append("unexpected")
        with self.assertRaises(ValueError):
            validate_vm(vm, now=now, credential_identity=self.check())


if __name__ == "__main__":
    unittest.main()
