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
