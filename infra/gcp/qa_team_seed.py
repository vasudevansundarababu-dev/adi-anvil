"""Populate the isolated acceptance project through actual existing QA APIs."""

import hashlib
import json
import zipfile
from pathlib import Path

from overnight_qa_bind_staged_credentials import OPERATOR
from qa_team_client import client

SOURCE = Path("/private/tmp/anvil-praxis-handoff-bef6f49ebf1a")


def main():
    public = json.loads((OPERATOR / "qa-team-project-public.json").read_text())
    project = public["project_id"]
    prefix = f"/api/v1/projects/{project}"
    destination = OPERATOR / "qa-team-records-public.json"
    from anvil.praxis_seed_handoff import verify

    manifest = (SOURCE / "MANIFEST.sha256").read_bytes()
    files = {}
    for line in manifest.decode().splitlines():
        _, name = line.split("  ")
        assert name.startswith("seed-export/") and ".." not in name.split("/")
        files[name] = (SOURCE / name).read_bytes()
    verify((SOURCE / "STATUS.md").read_bytes(), manifest, files)
    result = {"project": project, "source_commit": "bef6f49ebf1ad6c40f4fec0fea597cdc88c64743", "source_status": "fictional_draft_no_human_review", "source_manifest_sha256": hashlib.sha256(manifest).hexdigest(), "source_groups": [], "sources": [], "runs": [], "provider_calls": 0, "human_reviews_created": 0}
    if destination.exists():
        result = json.loads(destination.read_text())
        assert result["project"] == project and result["source_manifest_sha256"] == hashlib.sha256(manifest).hexdigest()

    def save():
        destination.write_text(json.dumps(result))

    with client() as api:
        for folder in ("phone-launch", "locale-compliance", "kyb-review", "aml-alerts", "kyc-onboarding"):
            if any(g["folder"] == folder for g in result["source_groups"]):
                assert len([s for s in result["sources"] if s["task"] in next(g["tasks"] for g in result["source_groups"] if g["folder"] == folder)]) == 2
                continue
            raw = (SOURCE / (folder + ".anvil.zip")).read_bytes()
            group = api.request("POST", prefix + "/workspace/benchmark/import", raw=raw)
            repeated = api.request("POST", prefix + "/workspace/benchmark/import", raw=raw)
            assert group["id"] == repeated["id"] and len(group["tasks"]) == 2
            result["source_groups"].append({"id": group["id"], "folder": folder, "tasks": [t["task_id"] for t in group["tasks"]], "idempotent_import": True})
            save()
            with zipfile.ZipFile(SOURCE / (folder + ".anvil.zip")) as archive:
                for name in archive.namelist():
                    if not (name.startswith("tasks/") and name.endswith(".json")):
                        continue
                    envelope = archive.read(name)
                    value = json.loads(envelope)
                    payload = value["payload_json"].encode()
                    assert hashlib.sha256(payload).hexdigest() == value["payload_sha256"]
                    task = json.loads(payload)
                    assert task["provenance"]["review"]["status"] == "draft"
                    source = api.request("POST", prefix + "/praxis-sources", body={"payload": envelope.decode()})
                    package = api.request("POST", prefix + "/praxis-sources/" + source["id"] + "/build")
                    assert package["approval"] is None
                    result["sources"].append({"task": task["task_id"], "source_id": source["id"], "source_sha256": source["source_sha256"], "package_id": package["id"], "package_sha256": package["package_sha256"], "binding": package["manifest"]["binding"], "review": "draft"})
                    save()
        group = api.request("POST", prefix + "/workspace/benchmark/sample", body=None)
        result["control_task_group"] = group
        api.request("POST", prefix + "/workspace/benchmark/groups/" + group["id"] + "/sample-verifiers?adapter=builtin", body=None)
        for label, model in (("completed", "fictional-compliant-v1"), ("genuine_zero", "fictional-zero-control-v1"), ("intentional_failure", "fictional-error-control-v1")):
            if any(r["case"] == label for r in result["runs"]):
                continue
            plan = api.request("POST", prefix + "/workspace/benchmark/plans", body={"name": "QA " + label + " software control", "task_group_id": group["id"], "task_ids": [t["task_id"] for t in group["tasks"]], "models": [model], "environment_ids": [e["id"] for e in group["environments"]], "method_ids": ["task-rubric-v1", "safety-observed-v1"], "repetitions": 1})
            run = api.request("POST", prefix + "/workspace/benchmark/runs", body={"plan_id": plan["id"], "expected_plan_sha256": plan["snapshot_sha256"]})
            result["runs"].append({"case": label, "id": run["id"], "plan_id": plan["id"], "model": model, "role": "admin"})
            save()
        result["api_openapi_sha256"] = hashlib.sha256(api.download("/openapi.json")).hexdigest()
        (OPERATOR / "qa-openapi.json").write_bytes(api.download("/openapi.json"))
    with client("rl-engineer") as api:
        listing = api.request("GET", prefix + "/workspace/benchmark")
        assert len(listing["groups"]) == 6
        if any(r["case"] == "pending_report_review" for r in result["runs"]):
            print("Existing isolated QA records retained")
            return
        plan = api.request("POST", prefix + "/workspace/benchmark/plans", body={"name": "QA pending report review, RL Engineer execution", "task_group_id": group["id"], "task_ids": [t["task_id"] for t in group["tasks"]], "models": ["fictional-compliant-v1"], "environment_ids": [e["id"] for e in group["environments"]], "method_ids": ["task-rubric-v1"], "repetitions": 1})
        run = api.request("POST", prefix + "/workspace/benchmark/runs", body={"plan_id": plan["id"], "expected_plan_sha256": plan["snapshot_sha256"]})
        result["runs"].append({"case": "pending_report_review", "id": run["id"], "plan_id": plan["id"], "model": "fictional-compliant-v1", "role": "rl-engineer"})
        save()
    print(json.dumps({"project": project, "groups": len(result["source_groups"]), "draft_sources": len(result["sources"]), "runs": result["runs"]}))


if __name__ == "__main__":
    main()
