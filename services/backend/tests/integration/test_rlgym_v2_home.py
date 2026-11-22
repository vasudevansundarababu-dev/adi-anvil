# ruff: noqa: F811  (pytest fixtures shared from the run tests are parameters here)
"""RL Gym v2 work package 2.10: leaderboard by project and cohort, To do cards opened and closed by run and SME events,
and Users (invite through the local Keycloak, remove access, history). Own disposable workspace."""

import uuid

import pytest
from test_rlgym_v2 import PROJECT, activated, exported, person, post, service, ws  # noqa: F401
from test_rlgym_v2_runs import body, finished, lineup, small_suite  # noqa: F401

from anvil.rlgym import integrations
from anvil.rlgym.runs import images

pytestmark = pytest.mark.skipif(not images.docker_status()[0], reason="Docker is required for runs")


def _todo(client, base):
    groups = client.get(base + "/todo").json()["data"]["groups"]
    return {i["kind"]: i for g in groups for i in g["items"]}


def test_leaderboard_ranks_one_cohort(finished):
    base, viewer = finished["base"], person("sales")
    board = viewer.get(base + f"/projects/{PROJECT}/leaderboard").json()["data"]
    assert board["run"]["id"] == finished["run"]["id"]
    rows = board["rows"]
    assert [r["rank"] for r in rows] == [1, 2, 3]
    assert rows[0]["model"].startswith("diligent") and rows[0]["score"] == 100
    assert all(r["executed_cells"] == 8 for r in rows)
    assert (
        board["cohort"]["environment"] == "golden-kyc-openenv@v3"
        and board["cohort"]["evaluators"] == 20
    )
    assert len(board["cohorts"]) >= 1 and board["cohorts"][0]["key"] == board["cohort"]["key"]
    same = viewer.get(
        base + f"/projects/{PROJECT}/leaderboard?cohort={board['cohort']['key']}"
    ).json()["data"]
    assert same["run"]["id"] == board["run"]["id"]
    home = viewer.get(base + "/home").json()["data"]
    assert any(p["project_id"] == PROJECT and p["has_results"] for p in home["projects"])
    assert viewer.get(base + "/projects/prj_nosuch1/leaderboard").status_code == 404


def test_todo_cards_follow_run_and_sme_events(finished):
    base, admin = finished["base"], person("admin-1")
    items = _todo(admin, base)
    assert "send_for_sme" in items and items["send_for_sme"]["subject"] == finished["run"]["id"]
    failed = admin.get(
        base + f"/runs/{finished['run']['id']}/episodes?kind=case&verdict=failed&size=50"
    ).json()["data"]["items"]
    post(
        admin,
        base + f"/runs/{finished['run']['id']}/sme-review-batches",
        {"episode_ids": [failed[0]["id"]]},
        201,
    )
    integrations.dispatch_once()
    items = _todo(admin, base)
    assert "send_for_sme" not in items and "sme_waiting" in items
    batch = admin.get(base + f"/runs/{finished['run']['id']}/sme-review").json()["data"]["batches"][
        0
    ]
    post(
        service("forge"),
        base + f"/sme-review-batches/{batch['id']}/decisions",
        {
            "schema": "rlgym.sme-decisions.v1",
            "batch_id": batch["id"],
            "decisions": [
                {
                    "item_id": batch["items"][0]["id"],
                    "decision": "agent_failure",
                    "rationale": "confirmed (it)",
                    "decided_by": "SME",
                }
            ],
        },
        200,
    )
    assert "sme_waiting" not in _todo(admin, base)
    board = admin.get(base + f"/projects/{PROJECT}/leaderboard").json()["data"]
    assert any(
        r["reviewed"] for r in board["rows"]
    )  # a decided batch: the leaderboard shows reviewed scores


def test_invite_remove_and_history(ws):
    base, admin = ws["base"], person("admin-1")
    username = "it-" + uuid.uuid4().hex[:8]
    invite = {
        "username": username,
        "email": f"{username}@anvil.invalid",
        "name": "Integration Invitee",
        "profile": "viewer",
    }
    assert (
        post(person("researcher"), base + "/users/invitations", invite, expected=None).status_code
        == 403
    )
    bad = post(
        admin,
        base + "/users/invitations",
        {**invite, "profile": "viewer", "binding_approver": True},
        expected=None,
    )
    assert bad.status_code == 422  # binding approvers are Admins or RL Engineers
    out = post(admin, base + "/users/invitations", invite, 201).json()["data"]
    assert out["temporary_password"] and out["profile"] == "viewer"
    again = post(admin, base + "/users/invitations", invite, expected=None)
    assert again.status_code == 409
    users = {u["id"]: u for u in admin.get(base + "/users").json()["data"]["items"]}
    assert users[out["id"]]["status"] == "active" and users[out["id"]]["profile"] == "viewer"
    removed = post(
        admin, base + f"/users/{out['id']}/remove", {"reason": "integration test"}
    ).json()["data"]
    assert removed["status"] == "removed"
    me = admin.get("/api/v1/rlgym/me").json()["data"]["id"]
    assert post(admin, base + f"/users/{me}/remove", {}, expected=None).status_code == 422
    history = admin.get(base + f"/users/{out['id']}/history").json()["data"]["items"]
    assert [h["action"] for h in history][:2] == ["user.removed", "user.invited"]
    assert person("sales").get(base + f"/users/{out['id']}/history").status_code == 403
