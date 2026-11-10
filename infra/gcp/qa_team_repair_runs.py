"""Fresh unpaid Runs after the observed worker-entry configuration repair."""

import json

from overnight_qa_bind_staged_credentials import OPERATOR
from qa_team_client import client


def main():
    path = OPERATOR / "qa-team-records-public.json"
    value = json.loads(path.read_text())
    assert not value.get("worker_repair_runs_created")
    base = f"/api/v1/projects/{value['project']}/workspace/benchmark"
    with client(qa_team=True) as api:
        for run in value["runs"]:
            before = api.request("GET", base + "/runs/" + run["id"])
            assert before["run"]["state"] == "failed" and before["run"]["executed_by"] is None
            (OPERATOR / ("qa-setup-failure-" + run["id"] + ".json")).write_text(json.dumps(before))
    previous = value["runs"]
    value["retained_setup_failures"] = previous
    value["runs"] = []
    value["worker_repair_runs_created"] = True
    path.write_text(json.dumps(value))
    for old in previous:
        with client(old["role"], qa_team=True) as api:
            listing = api.request("GET", base)
            plan = next(p for p in listing["plans"] if p["id"] == old["plan_id"])
            run = api.request("POST", base + "/runs", body={"plan_id": plan["id"], "expected_plan_sha256": plan["snapshot_sha256"]})
            value["runs"].append(old | {"id": run["id"], "previous_setup_failure": old["id"]})
            path.write_text(json.dumps(value))
    print(json.dumps({"project": value["project"], "fresh_runs": value["runs"], "old_setup_failures_retained": len(previous)}))


if __name__ == "__main__":
    main()
