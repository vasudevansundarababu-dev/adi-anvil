from urllib.parse import urlsplit

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from test_api_security import USERS

from anvil import auth
from anvil.cli import ORG, PROJECT
from anvil.config import ROOT, setting
from anvil.db import transaction, uid

# Pre-028 legacy grants: (user, role, active). Migrations 028 and 033 must record them.
LEGACY_GRANTS = [
    ("admin-1", "admin", True),
    ("researcher", "researcher", True),
    ("researcher", "reviewer", True),
    ("data-engineer", "data-engineer", True),
    ("advisor", "advisor", True),
    ("reviewer-1", "reviewer", False),
]


@pytest.fixture
def legacy_migrated(monkeypatch):
    """A fresh, uniquely named database holding legacy grants, migrated through 028 and 033."""
    target = "anvil_migrationhistory_" + uid().replace("-", "")[:12]
    admin_url = setting("MIGRATION_DATABASE_URL")
    with psycopg.connect(admin_url, autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(target)))
    try:
        for name in ("MIGRATION_DATABASE_URL", "DATABASE_URL", "WORKER_DATABASE_URL"):
            monkeypatch.setenv(name, urlsplit(setting(name))._replace(path="/" + target).geturl())
        alembic = Config(str(ROOT / "services/backend/alembic.ini"))
        with psycopg.connect(setting("MIGRATION_DATABASE_URL")) as c:
            c.execute("CREATE SCHEMA anvil")
        command.upgrade(alembic, "027")
        with psycopg.connect(setting("MIGRATION_DATABASE_URL")) as c:
            c.execute("INSERT INTO anvil.organizations VALUES(%s,'Legacy fixture lab')", (ORG,))
            c.execute(
                "INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,'Legacy fixture')",
                (PROJECT, ORG),
            )
            for name in {user for user, _, _ in LEGACY_GRANTS}:
                c.execute(
                    "INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,'https://legacy-fixture.invalid',%s,%s)",
                    (USERS[name], ORG, USERS[name], name),
                )
            for name, role, active in LEGACY_GRANTS:
                c.execute(
                    "INSERT INTO anvil.memberships(project_id,user_id,role,active) VALUES(%s,%s,%s,%s)",
                    (PROJECT, USERS[name], role, active),
                )
        command.upgrade(alembic, "head")
        yield
    finally:
        with psycopg.connect(admin_url, autocommit=True) as c:
            c.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(target))
            )


def test_current_roles_are_exactly_two_and_historical_memberships_are_read_only(
    legacy_migrated,
):
    with transaction(PROJECT, USERS["admin-1"]) as c:
        roles = {
            r["role"]
            for r in c.execute("SELECT role FROM anvil.memberships WHERE active").fetchall()
        }
        assert roles == {"admin", "rl-engineer"}
        history = c.execute(
            "SELECT user_id,legacy_role,was_active FROM anvil.membership_role_history"
        ).fetchall()
        assert {(str(h["user_id"]), h["legacy_role"], h["was_active"]) for h in history} == {
            (USERS[name], role, active) for name, role, active in LEGACY_GRANTS
        }
        assert c.execute(
            "SELECT is_synthetic FROM anvil.users WHERE id=%s", (USERS["admin-1"],)
        ).fetchone()["is_synthetic"]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with transaction(PROJECT, USERS["admin-1"]) as c:
            c.execute("UPDATE anvil.membership_role_history SET was_active=false")


def test_new_task_cannot_self_assign_unowned_private_reference(client_factory, journey):
    from anvil.db import one, uid

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


def test_people_profiles_pagination_scope_and_unchanged_grants(client_factory, journey):
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


def test_recorded_mapping_is_read_only_scoped_and_audited(legacy_migrated):
    with transaction(PROJECT, USERS["admin-1"]) as c:
        rows = c.execute("SELECT * FROM anvil.workspace_profile_mappings").fetchall()
        # Migration 028 maps active admin, researcher and data-engineer grants only.
        assert {str(row["user_id"]): row["profile"] for row in rows} == {
            USERS["admin-1"]: "admin",
            USERS["researcher"]: "rl_engineer",
            USERS["data-engineer"]: "rl_engineer",
        }
        assert all(str(row["project_id"]) == str(PROJECT) for row in rows)
        assert c.execute(
            "SELECT count(*) count FROM anvil.audit_events WHERE action='workspace.profile_mapping_recorded'"
        ).fetchone()["count"] == len(rows)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with transaction(PROJECT, USERS["admin-1"]) as c:
            c.execute("UPDATE anvil.workspace_profile_mappings SET profile='admin'")
