import json

import psycopg
import pytest
from test_api_security import USERS

from anvil import auth
from anvil.cli import PROJECT
from anvil.config import ROOT
from anvil.db import transaction


def test_current_roles_are_exactly_two_and_historical_memberships_are_read_only():
    with transaction(PROJECT, USERS["admin-1"]) as c:
        roles = {
            r["role"]
            for r in c.execute("SELECT role FROM anvil.memberships WHERE active").fetchall()
        }
        assert roles == {"admin", "rl-engineer"}
        assert c.execute("SELECT count(*) n FROM anvil.membership_role_history").fetchone()["n"] > 0
        assert c.execute(
            "SELECT is_synthetic FROM anvil.users WHERE id=%s", (USERS["admin-1"],)
        ).fetchone()["is_synthetic"]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with transaction(PROJECT, USERS["admin-1"]) as c:
            c.execute("UPDATE anvil.membership_role_history SET was_active=false")


def test_new_task_cannot_self_assign_unowned_private_reference(client_factory):
    from anvil.db import one, uid

    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    project = journey["project_id"]
    base = f"/api/v1/projects/{project}"
    with transaction(project, USERS["researcher"]) as c:
        task = (
            one(
                c,
                "SELECT v.content FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE r.id=%s",
                (journey["tasks"][0]["id"],),
            )
            if "tasks" in journey
            else None
        )
        if not task:
            protocol = one(
                c,
                "SELECT content FROM anvil.revisions WHERE id=%s",
                (journey["protocol"]["current_revision_id"],),
            )
            suite = one(
                c,
                "SELECT content FROM anvil.revisions WHERE id=%s",
                (protocol["content"]["suite_revision_id"],),
            )
            task = one(
                c,
                "SELECT content FROM anvil.revisions WHERE id=%s",
                (suite["content"]["task_revision_ids"][0],),
            )
        content = task["content"]
        private_id = content["reference_artifact_ids"][0]
    for name in ("sales", "admin-1"):
        client = client_factory(name)[0]
        assert client.get(base + f"/artifacts/{private_id}/content").status_code == 403
        body = {
            **content,
            "title": "Self-assignment must not reveal a private reference",
            "reviewer_id": USERS[name],
            "advisor_id": USERS[name],
        }
        response = client.post(base + "/tasks", json=body, headers={"Idempotency-Key": uid()})
        assert response.status_code == 403, response.text
        # Mislabeling a hidden reference as an actor input must not bypass the guard.
        body["actor_artifact_ids"] = [private_id, content["actor_artifact_ids"][0]]
        body["reference_artifact_ids"] = [content["actor_artifact_ids"][1]]
        response = client.post(base + "/tasks", json=body, headers={"Idempotency-Key": uid()})
        assert response.status_code == 403, response.text
        assert client.get(base + f"/artifacts/{private_id}/content").status_code == 403


def test_people_profiles_pagination_scope_and_unchanged_grants(client_factory):
    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    project = journey["project_id"]
    base = f"/api/v1/projects/{project}"
    admin, _ = client_factory("admin-1")
    researcher, _ = client_factory("researcher")
    outsider, _ = client_factory("outsider")
    with transaction(project, USERS["admin-1"]) as c:
        before = c.execute(
            "SELECT user_id,role,active FROM anvil.memberships WHERE project_id=%s ORDER BY user_id,role",
            (project,),
        ).fetchall()
        reviews_before = c.execute("SELECT count(*) count FROM anvil.review_decisions").fetchone()[
            "count"
        ]
    assert researcher.get(base + "/workspace/people").status_code == 403
    assert outsider.get(base + "/workspace/people").status_code == 404
    people = []
    cursor = ""
    while True:
        result = admin.get(
            base + "/workspace/people?limit=2" + ("&after=" + cursor if cursor else "")
        )
        assert result.status_code == 200, result.text
        data = result.json()["data"]
        assert data["management_available"] is False
        people.extend(data["items"])
        if not data["next_cursor"]:
            break
        assert data["next_cursor"] != cursor
        cursor = data["next_cursor"]
    assert len(people) == len({p["id"] for p in people})
    by_id = {p["id"]: p for p in people}
    assert by_id[USERS["admin-1"]]["access"]["profile"] == "admin"
    assert by_id[USERS["researcher"]]["access"]["profile"] == "rl_engineer"
    assert by_id[USERS["product-owner"]]["access"]["profile"] == "rl_engineer"
    assert "review.approve" not in by_id[USERS["admin-1"]]["access"]["capabilities"]
    assert admin.get(base + "/workspace/people?after=invalid").status_code == 422
    assert admin.post(base + "/workspace/people", json={"profile": "admin"}).status_code == 405
    me = admin.get("/api/v1/me").json()["data"]
    own_project = next(p for p in me["projects"] if p["id"] == project)
    assert own_project["roles"] == ["admin"]
    assert own_project["workspace_access"]["profile"] == "admin"
    # Explicitly prove the product label did not add private-reference access.
    with transaction(project, USERS["admin-1"]) as c:
        assert auth.project_roles(c, project, USERS["admin-1"]) == {"admin"}
        private = c.execute(
            "SELECT id FROM anvil.artifacts WHERE classification='hidden_reference' LIMIT 1"
        ).fetchone()
        assert private
        after = c.execute(
            "SELECT user_id,role,active FROM anvil.memberships WHERE project_id=%s ORDER BY user_id,role",
            (project,),
        ).fetchall()
        assert before == after
        assert (
            c.execute("SELECT count(*) count FROM anvil.review_decisions").fetchone()["count"]
            == reviews_before
        )
    assert admin.get(base + f"/artifacts/{private['id']}/content").status_code == 403


def test_recorded_mapping_is_read_only_scoped_and_audited():
    with transaction(PROJECT, USERS["admin-1"]) as c:
        rows = c.execute("SELECT * FROM anvil.workspace_profile_mappings").fetchall()
        assert rows
        assert all(str(row["project_id"]) == str(PROJECT) for row in rows)
        assert c.execute(
            "SELECT count(*) count FROM anvil.audit_events WHERE action='workspace.profile_mapping_recorded'"
        ).fetchone()["count"] == len(rows)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with transaction(PROJECT, USERS["admin-1"]) as c:
            c.execute("UPDATE anvil.workspace_profile_mappings SET profile='admin'")
