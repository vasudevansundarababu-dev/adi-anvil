"""Task screens and repeated runs use scoped, immutable real records; no provider calls."""
# ruff: noqa: F811

import pytest
from fastapi import HTTPException
from test_api_security import USERS
from test_praxis_harbor import BASE, imported
from test_workspace_execution import configured  # noqa: F401

from anvil import artifacts
from anvil.cli import OUTSIDER_PROJECT, PROJECT
from anvil.db import one, transaction


def test_task_detail_search_and_environment_intake_remain_scoped_and_inert(client_factory):
    _, _, _, source, package = imported(client_factory)
    admin, _ = client_factory("admin-1")
    engineer, _ = client_factory("researcher")
    outsider, _ = client_factory("outsider")
    path = BASE + "/workspace/tasks/" + source["id"]
    detail = engineer.get(path)
    assert detail.status_code == 200, detail.text
    value = detail.json()["data"]
    assert value["packages"][0]["id"] == package["id"]
    assert value["actor"] == source["actor_spec"]
    assert "PRIVATE-NORTHSTAR" not in detail.text and "reference_output" not in detail.text
    assert 'binding": {' not in str(value["rubric"])
    assert outsider.get(path).status_code == 404
    assert admin.get(path.replace(str(PROJECT), str(OUTSIDER_PROJECT))).status_code == 404
    listing = admin.get(
        BASE + "/workspace/tasks",
        params={"search": source["task_id"], "status": "ready", "limit": 1},
    ).json()["data"]
    assert listing["items"][0]["id"] == source["id"] and listing["items"][0]["package_built"]
    assert not admin.get(BASE + "/workspace/tasks?search=unlikely-absent-task-9be3").json()["data"][
        "items"
    ]
    assert not admin.get(
        BASE + "/workspace/tasks", params={"search": source["task_id"], "status": "draft"}
    ).json()["data"]["items"]
    body = {
        "name": "Task environment test",
        "files": [
            {"path": "Dockerfile", "content": "FROM python:3.12-slim\nCOPY inputs/ /app/inputs/\n"},
            {"path": "inputs/facts.txt", "content": "Synthetic context"},
        ],
    }
    with transaction(PROJECT, USERS["admin-1"]) as c:
        before = {
            table: one(c, "SELECT count(*) n FROM anvil." + table)["n"]
            for table in ("jobs", "harbor_agent_calls", "budget_reservations")
        }
    saved = engineer.post(path + "/environments", json=body)
    assert saved.status_code == 200, saved.text
    env = saved.json()["data"]
    assert env["status"] == "quarantined" and not env["execution_available"]
    assert engineer.post(path + "/environments", json=body).json()["data"]["id"] == env["id"]
    assert outsider.post(path + "/environments", json=body).status_code == 404
    invalid = {**body, "files": [*body["files"], {"path": "../secret", "content": "invalid"}]}
    assert engineer.post(path + "/environments", json=invalid).status_code == 422
    with transaction(PROJECT, USERS["admin-1"]) as c:
        assert {
            table: one(c, "SELECT count(*) n FROM anvil." + table)["n"] for table in before
        } == before
        artifact = one(
            c,
            "SELECT a.id,a.scan_status FROM anvil.artifacts a JOIN anvil.workspace_task_environments e ON e.dockerfile_artifact_id=a.id WHERE e.id=%s",
            (env["id"],),
        )
        assert artifact["scan_status"] == "quarantined"
        with pytest.raises(HTTPException) as denied:
            artifacts.read(c, artifact["id"])
        assert denied.value.status_code == 403


@pytest.mark.parametrize("configured", ["managed-costs"], indirect=True)
def test_repetitions_bind_separate_trials_multiply_estimate_and_reserve_single_cap(configured):
    data = configured
    post = data["post"]
    snapshot = data["prep"]["snapshot"]
    body = {
        "preset_id": snapshot["preset_id"],
        "package_id": snapshot["package"]["id"],
        "model_profile_ids": [m["id"] for m in snapshot["models"]],
        "max_output_tokens": 1024,
        "episode_timeout_seconds": 300,
        "aggregate_cap_micro_usd": 1000000,
        "trials_per_model": 3,
        "environment": "package-docker",
    }
    post("/preparations", {**body, "trials_per_model": 11}, expected=422)
    post("/preparations", {**body, "environment": "arbitrary-host"}, expected=422)
    prep = post("/preparations", body)
    group = post("/execution-groups", {"preparation_id": prep["id"]})
    assert len(group["models"]) == 9
    assert [m["trial"] for m in group["models"]] == [1, 2, 3] * 3
    assert len({m["plan_id"] for m in group["models"]}) == 9
    assert (
        group["readiness"]["conservative_cost_micro_usd"]
        == 3 * data["group"]["readiness"]["conservative_cost_micro_usd"]
    )
    assert all(not state["missing"] for state in group["readiness"]["models"])
    assert (
        prep["snapshot"]["environment"]["package_sha256"] == snapshot["package"]["package_sha256"]
    )
    launched = post(
        "/execution-groups/" + group["id"] + "/launch",
        {
            "subject_hash": group["subject_hash"],
            "aggregate_cap_micro_usd": 1000000,
            "rights_confirmed": True,
        },
    )
    assert len([m for m in launched["models"] if m["check"]]) == 9
    client = data["clients"]["admin-1"]
    assert [
        client.get(data["path"] + "/runs/" + member["check"]["id"]).json()["data"]["trial"]
        for member in launched["models"]
    ] == [1, 2, 3] * 3
    with transaction(PROJECT, USERS["admin-1"]) as c:
        assert (
            one(
                c,
                "SELECT reserved_micro_usd FROM anvil.evaluation_spend_windows WHERE id=(SELECT window_id FROM anvil.workspace_execution_groups WHERE id=%s)",
                (group["id"],),
            )["reserved_micro_usd"]
            == 1000000
        )
    post("/execution-groups/" + group["id"] + "/cancel")
