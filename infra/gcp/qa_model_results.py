"""Read actual saved provider receipts and hash-checked observable evidence."""

import hashlib
import json

from overnight_qa_bind_staged_credentials import OPERATOR
from qa_team_client import client


def main():
    receipt = json.loads((OPERATOR / "real-model-smoke-repaired-public.json").read_text())
    project = receipt["project"]
    results = []
    with client() as api:
        for group in receipt["groups"]:
            identifier = group["results"][0]["check"]["id"]
            path = f"/api/v1/projects/{project}/workspace/runs/{identifier}"
            detail = api.request("GET", path)
            assert detail["model"] == group["model"]
            assert len(detail["calls"]) <= 1
            for call in detail["calls"]:
                assert call["usage"]["dispatch_origin"] == "provider"
            evidence = []
            for item in detail["evidence"]:
                document = api.request("GET", path + "/evidence/" + item["artifact_id"])
                raw = document["content"].encode()
                assert document["sha256"] == item["sha256"]
                assert hashlib.sha256(raw).hexdigest() == item["sha256"]
                target = OPERATOR / ("model-evidence-" + identifier + ".json")
                target.write_bytes(raw)
                evidence.append(item | {"download_sha256_verified": True})
            (OPERATOR / ("model-result-" + identifier + ".json")).write_text(json.dumps(detail))
            value = {"model": detail["model"], "provider": detail["provider"], "state": detail["state"], "error_code": detail["error_code"], "group_id": group["id"], "check_id": identifier, "metrics": detail["metrics"], "diagnostics": detail["diagnostics"], "calls": detail["calls"], "evidence": evidence, "source_sha256": detail["source_sha256"], "package_sha256": detail["package_sha256"], "origin": detail["origin"], "human_review": "pending", "task": detail["task_id"]}
            results.append(value)
    summary = {"project": project, "task": receipt["task"], "source_status": "fictional_draft_no_human_review", "results": results, "known_cost_micro_usd": sum(v["metrics"]["known_cost_micro_usd"] or 0 for v in results), "all_costs_known": all(v["metrics"]["cost_complete"] for v in results), "no_unknown_retry": True, "overall_smoke_allocated_caps_micro_usd": 9000000}
    (OPERATOR / "real-model-results-public.json").write_text(json.dumps(summary))
    print(json.dumps({"results": [{k: v[k] for k in ("model", "state", "check_id", "metrics")} for v in results], "known_cost_micro_usd": summary["known_cost_micro_usd"], "all_costs_known": summary["all_costs_known"]}))


if __name__ == "__main__":
    main()
