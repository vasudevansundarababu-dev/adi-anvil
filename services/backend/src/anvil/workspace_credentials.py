"""Scoped credential lifecycle. Responses and audit never contain credential material."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field, SecretStr, field_validator

from anvil import auth, cloud_secrets, workspace_secrets
from anvil.config import CLOUD
from anvil.db import audit, one, uid
from anvil.schemas import Strict


class SecretValue(Strict):
    secret: SecretStr = Field(min_length=1, max_length=8192)

    @field_validator("secret")
    @classmethod
    def non_whitespace(cls, value):
        raw = value.get_secret_value()
        if not raw.isascii() or any(not 33 <= ord(c) <= 126 for c in raw) or not raw:
            raise ValueError("Credential must use printable ASCII without whitespace")
        return value


class Credential(SecretValue):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    provider: Literal["openai", "anthropic", "gemini", "langsmith"]


def public(row):
    return {
        k: row[k]
        for k in ("id", "name", "provider", "current_version_id", "revoked_at", "created_at")
    }


def resolve(c, identifier, version):
    """Internal future broker boundary only. Never mount as a credential read endpoint."""
    record = one(
        c,
        """SELECT v.secret_reference,h.provider,h.project_id FROM anvil.workspace_credentials h
        JOIN anvil.workspace_credential_versions v ON v.credential_id=h.id
        WHERE h.id=%s AND h.current_version_id=%s AND v.id=%s AND h.revoked_at IS NULL""",
        (identifier, version, version),
    )
    if not record:
        raise workspace_secrets.StoreUnavailable(
            "Credential revoked, rotated or outside project scope"
        )
    binding = {
        "project_id": str(record["project_id"]),
        "credential_id": str(identifier),
        "version_id": str(version),
        "provider": record["provider"],
    }
    return SecretStr(workspace_secrets.load(record["secret_reference"], binding))


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/credentials")

    def write_access(request, roles):
        auth.require(roles, "admin")
        if CLOUD and not cloud_secrets.available():
            raise HTTPException(409, "Managed cloud credential storage is not configured")
        identity = auth.identity(request)
        if (datetime.now(timezone.utc) - identity["issued_at"]).total_seconds() > 600:
            raise HTTPException(403, "Reauthentication required for credential changes")

    def save_version(c, project, user, identifier, body):
        vid = uid()
        header = one(
            c, "SELECT provider FROM anvil.workspace_credentials WHERE id=%s", (identifier,)
        )
        binding = {
            "project_id": str(project),
            "credential_id": str(identifier),
            "version_id": vid,
            "provider": header["provider"],
        }
        try:
            reference = workspace_secrets.save(body.secret.get_secret_value(), binding)
        except workspace_secrets.StoreUnavailable:
            raise HTTPException(503, "Credential store unavailable") from None
        c.execute(
            "INSERT INTO anvil.workspace_credential_versions(id,project_id,credential_id,secret_reference,created_by) VALUES(%s,%s,%s,%s,%s)",
            (vid, project, identifier, reference, user),
        )
        c.execute(
            "UPDATE anvil.workspace_credentials SET current_version_id=%s WHERE id=%s",
            (vid, identifier),
        )
        audit(
            c,
            project,
            user,
            "workspace.credential_version_created",
            identifier,
            {"version_id": vid},
        )
        return public(
            one(c, "SELECT * FROM anvil.workspace_credentials WHERE id=%s", (identifier,))
        )

    @router.get("")
    def listing(
        project: UUID,
        request: Request,
        limit: int = Query(50, ge=1, le=100),
        after: UUID | None = None,
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            rows = c.execute(
                "SELECT * FROM anvil.workspace_credentials WHERE (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
                (after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": [public(r) for r in rows[:limit]],
                    "entry_available": not CLOUD or cloud_secrets.available(),
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                },
                request,
            )

    @router.post("")
    def create(project: UUID, body: Credential, request: Request):
        with context(request, project) as (c, user, roles):
            write_access(request, roles)

            def act():
                cid = uid()
                c.execute(
                    "INSERT INTO anvil.workspace_credentials(id,project_id,name,provider,created_by) VALUES(%s,%s,%s,%s,%s)",
                    (cid, project, body.name.strip(), body.provider, user),
                )
                return save_version(c, project, user, cid, body)

            # Never serialize the raw SecretStr into an idempotency response or audit event.
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {
                        "name": body.name,
                        "provider": body.provider,
                        "secret_digest": auth.hashed(body.secret.get_secret_value()),
                    },
                    act,
                ),
                request,
            )

    @router.post("/{cid}/versions")
    def rotate(project: UUID, cid: UUID, body: SecretValue, request: Request):
        with context(request, project) as (c, user, roles):
            write_access(request, roles)

            def act():
                record = one(
                    c, "SELECT * FROM anvil.workspace_credentials WHERE id=%s FOR UPDATE", (cid,)
                )
                if not record:
                    raise HTTPException(404, "Credential not found in this project")
                if record["revoked_at"]:
                    raise HTTPException(409, "Create a new credential after revocation")
                return save_version(c, project, user, cid, body)

            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"secret_digest": auth.hashed(body.secret.get_secret_value())},
                    act,
                ),
                request,
            )

    @router.post("/{cid}/revoke")
    def revoke(project: UUID, cid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            write_access(request, roles)

            def act():
                record = one(
                    c, "SELECT * FROM anvil.workspace_credentials WHERE id=%s FOR UPDATE", (cid,)
                )
                if not record:
                    raise HTTPException(404, "Credential not found in this project")
                if not record["revoked_at"]:
                    c.execute(
                        "UPDATE anvil.workspace_credentials SET revoked_at=now() WHERE id=%s",
                        (cid,),
                    )
                    audit(c, project, user, "workspace.credential_revoked", cid)
                return public(
                    one(c, "SELECT * FROM anvil.workspace_credentials WHERE id=%s", (cid,))
                )

            return wrap(idempotent(c, project, user, request, {}, act), request)

    return router
