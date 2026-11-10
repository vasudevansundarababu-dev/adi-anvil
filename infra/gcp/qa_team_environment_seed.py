"""Six materialized QA worlds, real reset receipts and unscored technical Run."""

import json

from overnight_qa_bind_staged_credentials import OPERATOR
from qa_team_client import client


def main():
    metadata = json.loads((OPERATOR / "qa-team-records-public.json").read_text())
    project = metadata["project"]
    prefix = f"/api/v1/projects/{project}/workspace"
    target = OPERATOR / "qa-team-environments-public.json"
    assert not target.exists(), "Existing QA worlds must not be duplicated"
    result = {"project": project, "environments": [], "bindings_status": "published_reviewed_Praxis_revision_required", "provider_calls": 0, "cloud_resources_created": 0}
    with client(qa_team=True) as api:
        catalog = api.request("GET", prefix + "/environments")["templates"]
        assert len(catalog) == 6
        for item in catalog:
            base = prefix + "/environments"
            pack = api.request("POST", base + "/packs/generate", body={"template": item["id"], "scenario": item["scenarios"][0], "seed": 20261110})
            version = api.request("POST", base + "/versions", body={"pack_id": pack["id"], "name": "QA acceptance " + item["id"]})
            validation = api.request("POST", base + "/versions/" + version["id"] + "/validate")
            registration = api.request("POST", base + "/versions/" + version["id"] + "/register")
            instance = api.request("POST", base + "/versions/" + version["id"] + "/instances")
            observed = api.request("GET", base + "/instances/" + instance["id"])
            api.request("POST", base + "/instances/" + instance["id"] + "/tools", body={"expected_generation": observed["instance"]["generation"], "operation": "list_records", "arguments": {"collection": item["collections"][0]}})
            before = observed["instance"]["generation"]
            reset = api.request("POST", base + "/instances/" + instance["id"] + "/reset", body={"expected_generation": before})
            restored = api.request("GET", base + "/instances/" + instance["id"])
            assert restored["instance"]["generation"] == before + 1
            assert restored["instance"]["initial_sha256"] == instance["initial_sha256"]
            stale_status = api.status("POST", base + "/instances/" + instance["id"] + "/reset", body={"expected_generation": before})
            assert stale_status == 409
            options = api.request("GET", base + "/versions/" + version["id"] + "/binding-options")["tasks"]
            assert len(options) >= 10 and not any(v["supported"] for v in options)
            result["environments"].append({"template": item["id"], "scenario": item["scenarios"][0], "pack_id": pack["id"], "pack_sha256": version["manifest"]["pack_sha256"], "environment_id": version["id"], "manifest_sha256": version["manifest_sha256"], "validation_receipt_id": validation["id"], "registration_receipt_id": registration["id"], "instance_id": instance["id"], "reset_receipt_id": reset["id"], "generation": restored["instance"]["generation"], "baseline_sha256": instance["initial_sha256"], "stale_reset_http": stale_status, "source_task_binding": "blocked_draft_source", "record_collections": item["collections"]})
            target.write_text(json.dumps(result))
        group = metadata["control_task_group"]
        task = group["tasks"][0]
        plan = api.request("POST", prefix + "/environments/execution-plans", body={"name": "QA six-world technical rehearsal, no Task score", "task_group_id": group["id"], "members": [{"environment_id": item["environment_id"], "task_id": task["task_id"], "source_environment_id": task["environment_ids"][0], "actions": [{"operation": "list_records", "arguments": {"collection": item["record_collections"][0]}}]} for item in result["environments"]], "candidates": ["configured-tools-v1", "empty-tools-v1"], "purpose": "technical_rehearsal", "harness": "local-components-v1"})
        run = api.request("POST", prefix + "/benchmark/runs", body={"plan_id": plan["id"], "expected_plan_sha256": plan["snapshot_sha256"]})
        result["technical_run"] = {"id": run["id"], "plan_id": plan["id"], "expected_cells": 12, "task_score": "Not evaluated", "model_performance": False}
        target.write_text(json.dumps(result))
    print(json.dumps({"project": project, "worlds": len(result["environments"]), "technical_run": result["technical_run"], "reviewed_task_bindings": "blocked_draft_sources"}))


if __name__ == "__main__":
    main()
