import json

from test_api_security import USERS

from anvil import artifacts
from anvil.config import ROOT
from anvil.db import transaction, uid


def test_diagnostic_history_snapshots_pagination_and_finalized_output_only(client_factory):
    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    project = journey["project_id"]
    base = f"/api/v1/projects/{project}"
    admin, _ = client_factory("admin-1")
    researcher, _ = client_factory("researcher")
    tasks = admin.get(base + "/workspace/diagnostic-tasks?limit=1")
    assert tasks.status_code == 200, tasks.text
    assert tasks.json()["data"]["items"] and tasks.json()["data"]["next_cursor"]
    run = admin.get(base + "/workspace/diagnostic-runs/" + journey["run_id"])
    assert run.status_code == 200, run.text
    record = run.json()["data"]
    assert record["metrics"]["attempts"] == 6 and record["metrics"]["scored"] == 6
    assert "reference_artifact_ids" not in run.text and '"anchors"' not in run.text
    assert "reviewer_ids" not in run.text
    assert (
        record["evaluation_snapshot"]["protocol_revision_id"]
        == journey["protocol"]["current_revision_id"]
    )
    results = admin.get(
        base + "/workspace/diagnostic-runs/" + journey["run_id"] + "/results?limit=1"
    ).json()["data"]
    assert results["next_cursor"] and results["items"][0]["output_available"]
    eid = results["items"][0]["id"]
    output = admin.get(
        base + f"/workspace/diagnostic-runs/{journey['run_id']}/results/{eid}/output"
    )
    assert output.status_code == 200 and output.json()["data"]["sha256"]
    pending = researcher.post(
        base + "/runs",
        json={"protocol_revision_id": journey["protocol"]["current_revision_id"]},
        headers={"Idempotency-Key": uid()},
    )
    assert pending.status_code == 201, pending.text
    rid = pending.json()["data"]["id"]
    task_id = journey["suite"]["content"]["task_revision_ids"][0]
    with transaction(project, USERS["researcher"]) as c:
        aid = artifacts.store(c, project, b"BLINDED-WORKSPACE-OUTPUT", "internal")
        candidate = "BLINDED-CANDIDATE-IDENTITY"
        pid = uid()
        c.execute(
            """INSERT INTO anvil.episodes(id,project_id,run_id,task_revision_id,candidate_key,state,output_artifact_id,score,thread_id,graph_version)
        VALUES(%s,%s,%s,%s,%s,'awaiting_review',%s,99,%s,'test-only')""",
            (pid, project, rid, task_id, candidate, aid, uid()),
        )
        c.execute("UPDATE anvil.episodes SET outcome='pass' WHERE id=%s", (pid,))
    blinded = admin.get(base + f"/workspace/diagnostic-runs/{rid}/results")
    assert blinded.json()["data"]["items"][0]["outcome"] == "not_finalized"
    assert (
        "BLINDED" not in blinded.text and not blinded.json()["data"]["items"][0]["output_available"]
    )
    assert (
        admin.get(base + f"/workspace/diagnostic-runs/{rid}/results/{pid}/output").status_code
        == 409
    )
    resource = record["actor_snapshot"]["tasks"][0]["revision_id"]
    with transaction(project, USERS["researcher"]) as c:
        stable = c.execute(
            "SELECT resource_id FROM anvil.revisions WHERE id=%s", (resource,)
        ).fetchone()["resource_id"]
    # Retained nightly projects can exceed one history page; verify the cursor contract.
    params = {"task_id": str(stable)}
    seen = set()
    while True:
        history = admin.get(base + "/workspace/diagnostic-runs", params=params)
        assert history.status_code == 200
        page = history.json()["data"]
        if any(r["id"] == journey["run_id"] for r in page["items"]):
            break
        cursor = page["next_cursor"]
        assert cursor and cursor not in seen, "Original bound run must remain reachable in history"
        seen.add(cursor)
        params["after"] = cursor
    outsider, _ = client_factory("outsider")
    assert outsider.get(base + "/workspace/diagnostic-runs/" + journey["run_id"]).status_code == 404
    sales, _ = client_factory("sales")
    assert sales.get(base + "/workspace/diagnostic-runs").status_code == 200
