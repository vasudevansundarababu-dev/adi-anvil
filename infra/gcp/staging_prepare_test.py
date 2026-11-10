"""Offline safety checks for the staging contract; no cloud or credential access."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from staging_prepare import validate


class StagingSafety(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(Path(__file__).with_name("staging-plan.json").read_text())
        self.old = {"vm": "anvil-mvp-v1", "web_origin": "https://current.example.test"}
        self.plan["target"].update(web_hostname="stage.example.test", auth_hostname="auth-stage.example.test", oidc_issuer="https://auth-stage.example.test/realms/anvil-staging", allocated_public_ip="8.8.4.4")
        self.plan["proposed_resources"]["deployment_principal"] = "reviewed-staging-operator"
        self.plan["proposed_resources"]["subnet"]["cidr"] = "10.240.0.0/24"
        self.plan["release"].update(source_sha="a" * 40, image_digests={"web": "example/web@sha256:" + "b" * 64})
        self.plan["unresolved"] = []

    def inventory(self, plan):
        return {"project_id": "adi-anvil-mvp-2026", "complete": True, "observed_at_utc": "2026-11-08T00:00:00Z", "reviewed_plan_sha256": hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest(), "resource_names": ["anvil-mvp-v1"], "subnet_cidrs": ["10.0.0.0/24"], "reserved_staging_ipv4": ["8.8.4.4"]}

    def test_complete_manufactured_contract(self):
        self.assertEqual(validate(self.plan, self.old, self.inventory(self.plan)), [])

    def test_safety_mutations(self):
        mutations = [
            lambda p: p["proposed_resources"]["load_balancer"].update(backend_service="anvil-current"),
            lambda p: p["proposed_resources"].update(runtime_service_account="other@adi-anvil-mvp-2026.iam.gserviceaccount.com"),
            lambda p: p["proposed_resources"]["snapshot_policy"].update(name="anvil-daily"),
            lambda p: p["application_isolation"].update(artifact_root="/var/lib/anvil-staging/../anvil/artifacts"),
            lambda p: p["application_isolation"].update(benchmark_vault_root="/outside/vault"),
            lambda p: p["application_isolation"].update(private_root_policy="allow_symlinks"),
            lambda p: p["application_isolation"].update(database_roles=["anvil_app"]),
            lambda p: p["application_isolation"].update(keycloak_realm="anvil"),
            lambda p: p["secret_reference_proposals"].__setitem__(0, "projects/praxis/secrets/anvil-staging-db"),
            lambda p: p["target"].update(allocated_public_ip="10.1.1.1"),
            lambda p: p["target"].update(allocated_public_ip="2606:4700:4700::1111"),
            lambda p: p["target"].update(web_hostname="current.example.test"),
            lambda p: p.update(disabled_features=[]),
            lambda p: p["release"].update(image_digests={"web": "mutable:latest"}),
        ]
        for mutate in mutations:
            plan = copy.deepcopy(self.plan)
            mutate(plan)
            with self.subTest(plan=plan):
                self.assertTrue(validate(plan, self.old, self.inventory(plan)))

    def test_inventory_overlap_stale_and_name_collision(self):
        for key, value in (("subnet_cidrs", ["10.240.0.0/16"]), ("resource_names", ["anvil-staging-backend"]), ("reviewed_plan_sha256", "stale"), ("reserved_staging_ipv4", [])):
            inventory = self.inventory(self.plan)
            inventory[key] = value
            self.assertTrue(validate(self.plan, self.old, inventory))
        self.assertTrue(validate(self.plan, self.old))

    def test_missing_and_malformed_fail_cleanly(self):
        for value in ({}, None, [], {"target": None}):
            self.assertTrue(validate(value, self.old))
        for key in self.plan:
            plan = copy.deepcopy(self.plan)
            del plan[key]
            self.assertTrue(validate(plan, self.old, self.inventory(plan)))


if __name__ == "__main__":
    unittest.main()
