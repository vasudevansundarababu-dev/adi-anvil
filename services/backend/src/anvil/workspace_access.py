"""Product-profile projection over current grants; never adds legacy/private privileges."""

from uuid import UUID

from fastapi import APIRouter, Query, Request

from anvil import auth
from anvil.db import one

READ_ROLES = {"admin", "rl-engineer"}
ENGINEER_ROLES = {"rl-engineer"}


def profile_for(roles):
    if "admin" in roles:
        return "admin"
    if ENGINEER_ROLES.intersection(roles):
        return "rl_engineer"
    return None


def capabilities_for(roles):
    # These name implemented safe modern operations, not arbitrary legacy CRUD.
    capabilities = []
    if READ_ROLES.intersection(roles):
        capabilities.extend(["workspace.read", "tasks.read", "runs.read"])
    if {"admin", *ENGINEER_ROLES}.intersection(roles):
        capabilities.extend(["task_drafts.write", "harbor.import"])
    if {"admin", "rl-engineer"}.intersection(roles):
        capabilities.append("harbor.prepare")
    if "admin" in roles:
        capabilities.extend(
            [
                "models.manage",
                "credentials.manage",
                "frameworks.manage",
                "people.read",
                "limits.read",
            ]
        )
    return sorted(capabilities)


def access_projection(roles, mapping=None):
    roles = set(roles)
    profile = profile_for(roles)
    matches = bool(
        mapping and mapping["profile"] == profile and set(mapping["legacy_roles"]) == roles
    )
    return {
        "profile": profile,
        "label": {"admin": "Admin", "rl_engineer": "RL Engineer"}.get(profile, "No active access"),
        "capabilities": capabilities_for(roles),
        "mapping_state": "recorded"
        if matches
        else "current_grants_changed"
        if mapping
        else "not_recorded"
        if profile
        else "legacy_only",
        "mapping_policy": mapping["mapping_policy"] if mapping else None,
        "recorded_at": mapping["recorded_at"] if mapping else None,
        "grants_changed": False,
    }


def project_access(c, project, user, roles):
    mapping = one(
        c,
        "SELECT * FROM anvil.workspace_profile_mappings WHERE project_id=%s AND user_id=%s",
        (project, user),
    )
    return access_projection(roles, mapping)


def routes(context, wrap):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace")

    @router.get("/people")
    def people(
        project: UUID,
        request: Request,
        limit: int = Query(30, ge=1, le=100),
        after: UUID | None = None,
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            rows = c.execute(
                """SELECT u.id,u.name,array_agg(m.role ORDER BY m.role) roles,
                p.profile,p.legacy_roles,p.mapping_policy,p.recorded_at
                FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id
                LEFT JOIN anvil.workspace_profile_mappings p
                  ON p.project_id=m.project_id AND p.user_id=u.id
                WHERE m.project_id=%s AND m.active AND u.active
                AND (%s::uuid IS NULL OR u.id>%s)
                GROUP BY u.id,p.project_id,p.user_id
                ORDER BY u.id LIMIT %s""",
                (project, after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": [
                        {
                            "id": row["id"],
                            "name": row["name"],
                            "access": access_projection(
                                row["roles"], row if row["profile"] else None
                            ),
                            "preserved_duties": row["roles"],
                        }
                        for row in rows[:limit]
                    ],
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                    "management_available": False,
                    "management_reason": "Invitation, promotion and project-access revocation are not enabled in this local transition. Existing identities, project access and review duties are preserved.",
                },
                request,
            )

    return router
