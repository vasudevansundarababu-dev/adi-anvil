"""Workspaces, members and the local seed.

Profiles are Admin, RL Engineer and Viewer (labels, no RBAC); the binding-approver flag is the one rule the server
enforces. Members are the existing local Keycloak identities (distinct people, never a role switcher). SMEs have no
accounts here: SME review happens in ADI Forge.
"""

import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from anvil.config import ROOT, setting
from anvil.rlgym.common import GymError, audit, emit, require

WORKSPACE_ID = "b0000000-0000-4000-8000-0000000000a1"
WORKSPACE_SLUG = "adi-labs-research"
OUTSIDER_WORKSPACE_ID = "b0000000-0000-4000-8000-0000000000a2"
OUTSIDER_WORKSPACE_SLUG = "isolation-control"

PROFILES = {
    "admin-1": ("admin", True),
    "admin-2": ("admin", True),
    "reviewer-1": ("rl_engineer", True),
    "researcher": ("rl_engineer", False),
    "data-engineer": ("rl_engineer", False),
    "advisor": ("rl_engineer", False),
    "product-owner": ("rl_engineer", False),
    "reviewer-2": ("rl_engineer", False),
    "adjudicator": ("rl_engineer", False),
    "sales": ("viewer", False),
}

PYTHON_RUNNER = Path(__file__).resolve().parents[1] / "scoring" / "sandbox_runner.py"


def framework_seed():
    import hashlib

    digest = "sha256:" + hashlib.sha256(PYTHON_RUNNER.read_bytes()).hexdigest()
    return [
        (
            "fw-python-1.0.0",
            "python",
            "1.0.0",
            digest,
            ["tool_events", "final_output", "state_diff"],
            True,
            "Sandboxed Python evaluator: isolated interpreter subprocess, empty environment, CPU and time limits. "
            "Image digest is the runner source hash (no container image locally).",
            "qualified",
        ),
        (
            "fw-zen-2.4.1",
            "zen",
            "2.4.1",
            "sha256:" + "0" * 64,
            ["tool_events", "final_output"],
            False,
            "Not installed locally: the ZEN image is not available on this machine, so no configuration can run on it.",
            "registered",
        ),
        (
            "fw-promptfoo-0.121.0",
            "promptfoo",
            "0.121.0",
            "sha256:" + "0" * 64,
            ["transcript"],
            False,
            "Not installed locally (Trust & Safety generation is work package 2.6).",
            "registered",
        ),
        (
            "fw-pramaana-1.3.0",
            "pramaana",
            "1.3.0",
            "sha256:" + "0" * 64,
            ["documents"],
            False,
            "Not installed locally: no Pramaana image on this machine.",
            "registered",
        ),
    ]


def seed():
    """Idempotent local seed: two workspaces, members from the Keycloak identities, framework versions."""
    ids = json.loads((ROOT / ".local/demo-identities.json").read_text())
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        c.execute(
            "INSERT INTO admin.workspaces(id,slug,name,tier) VALUES(%s,%s,%s,'dev'),(%s,%s,%s,'dev') ON CONFLICT DO NOTHING",
            (
                WORKSPACE_ID,
                WORKSPACE_SLUG,
                "ADI Labs research",
                OUTSIDER_WORKSPACE_ID,
                OUTSIDER_WORKSPACE_SLUG,
                "Isolation control",
            ),
        )
        for name, user in ids.items():
            ws, (profile, approver) = (
                (OUTSIDER_WORKSPACE_ID, ("rl_engineer", False))
                if name == "outsider"
                else (WORKSPACE_ID, PROFILES.get(name, ("viewer", False)))
            )
            c.execute(
                """INSERT INTO admin.users(id,workspace_id,email,name,profile,binding_approver,status)
                   VALUES(%s,%s,%s,%s,%s,%s,'active') ON CONFLICT DO NOTHING""",
                (user, ws, f"{name}@anvil.invalid", name, profile, approver),
            )
        for row in framework_seed():
            fid, runtime, version, digest, evidence, installed, note, state = row
            c.execute(
                """INSERT INTO catalog.framework_versions(id,runtime_id,version,image_digest,evidence_types,installed_locally,
                     install_note,state,state_changed_by,state_changed_at,created_by)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'platform-admin:local-seed',now(),'platform-admin:local-seed')
                   ON CONFLICT (id) DO UPDATE SET image_digest=EXCLUDED.image_digest
                   WHERE catalog.framework_versions.installed_locally""",
                (fid, runtime, version, digest, evidence, installed, note, state),
            )
        from anvil.rlgym.common import Actor, Ctx
        from anvil.rlgym.systems.service import seed_mock_lineup

        seed_mock_lineup(
            Ctx(
                c,
                {"id": WORKSPACE_ID, "slug": WORKSPACE_SLUG},
                Actor("local-seed", "system", "Local seed"),
            )
        )
        # Default suites for projects exported before suites existed (2.6); idempotent.
        from anvil.rlgym.suites.service import ensure_default

        for ws_row in c.execute("SELECT id, slug FROM admin.workspaces").fetchall():
            c.execute("SELECT set_config('rlgym.workspace', %s, true)", (str(ws_row["id"]),))
            for proj in c.execute(
                "SELECT project_id, name FROM projects.projects WHERE workspace_id=%s",
                (ws_row["id"],),
            ).fetchall():
                ensure_default(
                    c,
                    ws_row["id"],
                    Actor("rlgym", "system", "RL Gym"),
                    proj["project_id"],
                    proj["name"],
                )
        if not c.execute(
            "SELECT 1 FROM admin.audit_events WHERE workspace_id=%s AND action='rlgym_local_seed'",
            (WORKSPACE_ID,),
        ).fetchone():
            c.execute(
                "INSERT INTO admin.audit_events(workspace_id,actor,actor_kind,action,subject,details) VALUES(%s,'local-seed','system','rlgym_local_seed',%s,%s)",
                (
                    WORKSPACE_ID,
                    WORKSPACE_SLUG,
                    json.dumps(
                        {
                            "synthetic": True,
                            "note": "Local identities only; no approvals or runs seeded",
                        }
                    ),
                ),
            )
    print(
        f"RL Gym v2 workspace {WORKSPACE_SLUG} and members seeded idempotently (synthetic local identities)."
    )


def list_users(ctx):
    return ctx.c.execute(
        "SELECT id,email,name,profile,binding_approver,status,last_seen_at FROM admin.users WHERE workspace_id=%s ORDER BY name",
        (ctx.ws,),
    ).fetchall()


def update_user(ctx, user_id, body):
    ctx.actor.require_person()
    require(
        ctx.actor.profile == "admin",
        "FORBIDDEN",
        "Only an Admin changes profiles or the binding-approver flag",
    )
    row = ctx.c.execute(
        "SELECT * FROM admin.users WHERE workspace_id=%s AND id=%s", (ctx.ws, user_id)
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "User not found")
    profile = body.get("profile", row["profile"])
    approver = body.get("binding_approver", row["binding_approver"])
    require(
        profile in ("admin", "rl_engineer", "viewer"),
        "VALIDATION_FAILED",
        "Unknown profile",
        field="profile",
    )
    require(
        isinstance(approver, bool), "VALIDATION_FAILED", "binding_approver must be true or false"
    )
    if row["profile"] == "admin" and profile != "admin":
        admins = ctx.c.execute(
            "SELECT count(*) n FROM admin.users WHERE workspace_id=%s AND profile='admin' AND status='active'",
            (ctx.ws,),
        ).fetchone()["n"]
        require(admins > 1, "VALIDATION_FAILED", "A workspace keeps at least one Admin")
    ctx.c.execute(
        "UPDATE admin.users SET profile=%s, binding_approver=%s WHERE workspace_id=%s AND id=%s",
        (profile, approver, ctx.ws, user_id),
    )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "user.updated",
        str(user_id),
        details={"profile": profile, "binding_approver": approver},
    )
    emit(
        ctx.c,
        ctx.ws,
        "user.updated",
        str(user_id),
        {"user_id": str(user_id), "profile": profile, "binding_approver": approver},
    )
    return {**row, "profile": profile, "binding_approver": approver}


def my_workspaces(user_id):
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as c:
        return c.execute("SELECT * FROM admin.workspaces_of(%s)", (user_id,)).fetchall()


# --- invite and remove access (SPEC 07.8) -------------------------------------------------------------------------

LOCAL_ORG = "a0000000-0000-4000-8000-000000000001"


def _keycloak_admin():
    """Admin endpoint of the identity provider. Locally only the loopback Keycloak of this checkout is allowed."""
    from urllib.parse import urlsplit

    from anvil.config import CLOUD, setting

    issuer = setting("OIDC_ISSUER")
    parts = urlsplit(issuer)
    base = os.environ.get("KEYCLOAK_ADMIN_URL") or f"{parts.scheme}://{parts.netloc}"
    if not CLOUD and urlsplit(base).hostname not in ("127.0.0.1", "localhost", "::1"):
        raise GymError("VALIDATION_FAILED", "Local invites go only to the local Keycloak")
    user = os.environ.get("KEYCLOAK_ADMIN_USER") or (
        "anvil-bootstrap" if not CLOUD else setting("KEYCLOAK_ADMIN_USER")
    )
    return (
        base.rstrip("/"),
        issuer.rsplit("/realms/", 1)[1],
        user,
        setting("ANVIL_OIDC_ADMIN_PASSWORD"),
    )


def _create_identity(username, email, name, transport=None):
    """Create the person's sign-in with a temporary password changed at first sign-in (UPDATE_PASSWORD). Returns
    (subject, temporary password or None when the identity already existed with the same email)."""
    import secrets as _secrets

    import httpx

    base, realm, admin, password = _keycloak_admin()
    with httpx.Client(timeout=10, transport=transport, trust_env=False) as client:
        r = client.post(
            base + "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": admin,
                "password": password,
            },
        )
        if r.status_code != 200:
            raise GymError(
                "VALIDATION_FAILED", "The identity provider refused the administrator sign-in"
            )
        headers = {"Authorization": "Bearer " + r.json()["access_token"]}
        users_url = base + f"/admin/realms/{realm}/users"
        temporary = _secrets.token_urlsafe(18)
        first, _, last = name.strip().partition(" ")
        r = client.post(
            users_url,
            headers=headers,
            json={
                "username": username,
                "email": email,
                "firstName": first,
                "lastName": last.strip() or "-",
                "enabled": True,
                "emailVerified": True,
                "requiredActions": ["UPDATE_PASSWORD"],
                "credentials": [{"type": "password", "value": temporary, "temporary": True}],
            },
        )
        if r.status_code == 409:
            found = client.get(
                users_url, headers=headers, params={"username": username, "exact": "true"}
            ).json()
            match = [u for u in found if (u.get("email") or "").lower() == email.lower()]
            if not match:
                raise GymError("CONFLICT", "That username or email belongs to a different person")
            return match[0]["id"], None
        if r.status_code >= 300:
            raise GymError("VALIDATION_FAILED", f"The identity provider answered {r.status_code}")
        return r.headers["Location"].rsplit("/", 1)[1], temporary


def invite_user(ctx, body, transport=None):
    """Admin only. Creates the sign-in in the identity provider and this workspace's access; the temporary password is
    returned once (never stored) and must be changed at first sign-in."""
    import re
    import uuid as _uuid

    from anvil.config import setting

    ctx.actor.require_person()
    require(ctx.actor.profile == "admin", "FORBIDDEN", "Only an Admin invites people")
    username = (body.get("username") or "").strip().lower()
    email = (body.get("email") or "").strip()
    name = (body.get("name") or "").strip()
    profile = body.get("profile", "viewer")
    approver = bool(body.get("binding_approver", False))
    require(
        re.match(r"^[a-z0-9][a-z0-9._-]{2,62}$", username),
        "VALIDATION_FAILED",
        "Username: 3-63 lowercase letters, digits, '.', '_' or '-'",
        field="username",
    )
    require(
        re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email),
        "VALIDATION_FAILED",
        "A valid email is required",
        field="email",
    )
    require(name, "VALIDATION_FAILED", "Full name is required", field="name")
    require(
        profile in ("admin", "rl_engineer", "viewer"),
        "VALIDATION_FAILED",
        "Unknown profile",
        field="profile",
    )
    require(
        not (approver and profile == "viewer"),
        "VALIDATION_FAILED",
        "Binding approvers are Admins or RL Engineers",
        field="binding_approver",
    )
    subject, temporary = _create_identity(username, email, name, transport)
    user_id = str(_uuid.UUID(subject))
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        c.execute(
            "INSERT INTO anvil.organizations VALUES(%s,%s) ON CONFLICT DO NOTHING",
            (LOCAL_ORG, "Anvil local synthetic lab"),
        )
        c.execute(
            "INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (user_id, LOCAL_ORG, setting("OIDC_ISSUER"), subject, name),
        )
    existing = ctx.c.execute(
        "SELECT * FROM admin.users WHERE workspace_id=%s AND id=%s", (ctx.ws, user_id)
    ).fetchone()
    if existing and existing["status"] == "active":
        raise GymError("CONFLICT", "This person already has access to the workspace")
    if existing:
        ctx.c.execute(
            "UPDATE admin.users SET profile=%s, binding_approver=%s, status='active' WHERE workspace_id=%s AND id=%s",
            (profile, approver, ctx.ws, user_id),
        )
    else:
        ctx.c.execute(
            "INSERT INTO admin.users(id,workspace_id,email,name,profile,binding_approver,status) VALUES(%s,%s,%s,%s,%s,%s,'active')",
            (user_id, ctx.ws, email, name, profile, approver),
        )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "user.invited",
        user_id,
        details={"username": username, "profile": profile, "binding_approver": approver},
    )
    emit(ctx.c, ctx.ws, "user.invited", user_id, {"user_id": user_id, "profile": profile})
    return {
        "id": user_id,
        "username": username,
        "profile": profile,
        "binding_approver": approver,
        "temporary_password": temporary,
        "note": "Shown once: give it to the person privately; they change it at first sign-in."
        if temporary
        else "The sign-in already existed; access to this workspace was added.",
    }


def remove_access(ctx, user_id, body):
    """Removing access keeps the account and its history."""
    ctx.actor.require_person()
    require(ctx.actor.profile == "admin", "FORBIDDEN", "Only an Admin removes access")
    row = ctx.c.execute(
        "SELECT * FROM admin.users WHERE workspace_id=%s AND id=%s", (ctx.ws, user_id)
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "User not found")
    require(
        str(user_id) != str(ctx.actor.id), "VALIDATION_FAILED", "You cannot remove your own access"
    )
    if row["profile"] == "admin":
        admins = ctx.c.execute(
            "SELECT count(*) n FROM admin.users WHERE workspace_id=%s AND profile='admin' AND status='active'",
            (ctx.ws,),
        ).fetchone()["n"]
        require(admins > 1, "VALIDATION_FAILED", "A workspace keeps at least one Admin")
    ctx.c.execute(
        "UPDATE admin.users SET status='removed', binding_approver=false WHERE workspace_id=%s AND id=%s",
        (ctx.ws, user_id),
    )
    audit(ctx.c, ctx.ws, ctx.actor, "user.removed", str(user_id), reason=body.get("reason"))
    emit(ctx.c, ctx.ws, "user.removed", str(user_id), {"user_id": str(user_id)})
    return {"id": str(user_id), "status": "removed"}


def access_history(ctx, user_id):
    return ctx.c.execute(
        """SELECT action, actor, reason, details, at AS created_at FROM admin.audit_events
           WHERE workspace_id=%s AND (subject=%s OR actor=%s) AND action LIKE 'user.%%' ORDER BY at DESC, id DESC LIMIT 50""",
        (ctx.ws, str(user_id), str(user_id)),
    ).fetchall()
