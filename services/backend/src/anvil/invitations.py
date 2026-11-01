"""Cloud invitations: one real Keycloak identity per person, bound to explicit project roles.

Never creates synthetic demo identities. The temporary password is printed once and must be
changed at first sign-in (Keycloak UPDATE_PASSWORD).
"""

import re
import secrets
import uuid

import httpx
import psycopg
from psycopg.rows import dict_row

from anvil.config import CLOUD, setting
from anvil.db import audit

ROLES = {"admin", "rl-engineer"}
CAPABILITIES = {"rights_reviewer", "release_owner"}
CLOUD_ORG = "c0000000-0000-4000-8000-000000000001"
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,62}$")


def validate(username, email, roles, capabilities):
    if not USERNAME.match(username):
        raise ValueError("Username must be 3..63 lowercase letters, digits, '.', '_' or '-'")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ValueError("A valid email address is required")
    if len(roles) != 1 or not set(roles) <= ROLES:
        raise ValueError(f"Roles must be chosen from {sorted(ROLES)}")
    if not set(capabilities) <= CAPABILITIES:
        raise ValueError(f"Capabilities must be chosen from {sorted(CAPABILITIES)}")
    if capabilities and "admin" not in roles:
        raise ValueError("Only Admin can hold administrative permissions")


def admin_token(client, base):
    r = client.post(
        base + "/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": setting("KEYCLOAK_ADMIN_USER"),
            "password": setting("ANVIL_OIDC_ADMIN_PASSWORD"),
        },
    )
    r.raise_for_status()
    return r.json()["access_token"]


def keycloak_user(username, email, name, transport=None):
    """Create (or find) the realm user; returns (subject, temporary_password or None)."""
    base = setting("KEYCLOAK_ADMIN_URL").rstrip("/")
    realm = setting("OIDC_ISSUER").rsplit("/realms/", 1)[1]
    with httpx.Client(timeout=10, transport=transport) as client:
        headers = {"Authorization": "Bearer " + admin_token(client, base)}
        users = base + f"/admin/realms/{realm}/users"
        password = secrets.token_urlsafe(18)
        first, _, last = name.strip().partition(" ")
        r = client.post(
            users,
            headers=headers,
            json={
                "username": username,
                "email": email,
                # Keycloak's default user profile requires both names.
                "firstName": first,
                "lastName": last.strip() or "-",
                "enabled": True,
                "emailVerified": True,
                "requiredActions": ["UPDATE_PASSWORD"],
                "credentials": [{"type": "password", "value": password, "temporary": True}],
            },
        )
        if r.status_code == 409:
            found = client.get(
                users, headers=headers, params={"username": username, "exact": "true"}
            )
            found.raise_for_status()
            match = [u for u in found.json() if u.get("email", "").lower() == email.lower()]
            if not match:
                raise ValueError("Username or email already belongs to a different identity")
            return match[0]["id"], None
        r.raise_for_status()
        return r.headers["Location"].rsplit("/", 1)[1], password


def invite(username, email, name, project_name, roles, capabilities=(), transport=None):
    if not CLOUD:
        raise RuntimeError("Invitations are cloud-only; local uses synthetic seeded identities")
    validate(username, email, roles, capabilities)
    subject, password = keycloak_user(username, email, name, transport)
    user_id = str(uuid.UUID(subject))
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        c.execute(
            "INSERT INTO anvil.organizations VALUES(%s,%s) ON CONFLICT DO NOTHING",
            (CLOUD_ORG, "ADI Labs"),
        )
        project = c.execute(
            "SELECT id FROM anvil.projects WHERE org_id=%s AND name=%s ORDER BY created_at LIMIT 1",
            (CLOUD_ORG, project_name),
        ).fetchone()
        if project:
            project = project["id"]
        else:
            project = str(uuid.uuid4())
            c.execute(
                "INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,%s)",
                (project, CLOUD_ORG, project_name),
            )
        c.execute(
            "INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (user_id, CLOUD_ORG, setting("OIDC_ISSUER"), subject, name),
        )
        for role in roles:
            c.execute(
                "INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                (project, user_id, role),
            )
        for capability in CAPABILITIES if "admin" in roles else set():
            c.execute(
                "INSERT INTO anvil.project_assignments(project_id,user_id,capability) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                (project, user_id, capability),
            )
        audit(
            c,
            project,
            None,
            "cloud_invitation",
            user_id,
            {"username": username, "roles": sorted(roles)},
        )
    return {"project_id": str(project), "user_id": user_id, "temporary_password": password}
