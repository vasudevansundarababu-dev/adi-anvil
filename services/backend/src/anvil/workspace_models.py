"""Versioned model configuration metadata; no qualification, secret reads or paid effects."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import AwareDatetime, Field, HttpUrl, field_validator, model_validator

from anvil import auth, domain
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.providers import PROVIDERS, secret_presence
from anvil.schemas import Strict


class Pricing(Strict):
    reference: str = Field(min_length=5, max_length=200, pattern=r".*\S.*")
    source_url: HttpUrl = Field(max_length=500)
    input_micro_usd_per_million_tokens: int = Field(ge=0, le=1000000000000, strict=True)
    output_micro_usd_per_million_tokens: int = Field(ge=0, le=1000000000000, strict=True)
    expires_at: AwareDatetime

    @field_validator("source_url")
    @classmethod
    def safe_source(cls, value):
        if value.scheme != "https" or value.username or value.password:
            raise ValueError("Use an HTTPS pricing reference without embedded credentials")
        return value


class ModelProfile(Strict):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    provider: Literal["openai", "anthropic", "gemini"]
    model_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/@-]*$")
    max_output_tokens: int = Field(default=4096, ge=1, le=8192, strict=True)
    credential_id: UUID | None = None
    credential_version_id: UUID | None = None
    pricing: Pricing | None = None
    processing_terms_reviewed: bool = Field(default=False, strict=True)
    processing_terms_reference: str | None = Field(
        default=None, min_length=5, max_length=500, pattern=r".*\S.*"
    )

    @model_validator(mode="after")
    def references(self):
        if self.credential_version_id and not self.credential_id:
            raise ValueError("Credential version requires a credential")
        if self.processing_terms_reviewed and not self.processing_terms_reference:
            raise ValueError("Reviewed terms require an explicit reference")
        return self


def version_header(c, connection, lock=False):
    return one(
        c,
        """SELECT p.*,v.version_no FROM anvil.workspace_model_versions v
        JOIN anvil.workspace_model_profiles p ON p.id=v.profile_id AND p.project_id=v.project_id
        WHERE v.connection_id=%s"""
        + (" FOR UPDATE OF p" if lock else ""),
        (connection,),
    )


def selection_issues(c, connection):
    header = version_header(c, connection)
    if not header:
        return ["model_version_mapping_missing"]
    if header["disabled_at"]:
        return ["model_profile_disabled"]
    if str(header["current_connection_id"]) != str(connection):
        return ["model_version_superseded"]
    return []


def pricing_state(config):
    pricing = config.get("workspace_pricing")
    if not pricing:
        return "missing"
    try:
        expiry = datetime.fromisoformat(pricing["expires_at"].replace("Z", "+00:00"))
        return "current_metadata" if expiry > datetime.now(timezone.utc) else "expired"
    except (ValueError, TypeError, KeyError, AttributeError):
        return "invalid"


def model_public(c, row):
    workspace_profile = row["config"].get("workspace_profile_version") == 1
    present = False
    if "workspace_profile_version" not in row["config"]:
        present, _ = secret_presence(row["provider_key"])
    credential_state = "server_configured" if present else "missing"
    binding = row["config"].get("workspace_credential")
    credential_name = None
    if binding:
        credential = one(
            c, "SELECT * FROM anvil.workspace_credentials WHERE id=%s", (binding["id"],)
        )
        present = False
        credential_state = "missing"
        if credential:
            credential_name = credential["name"]
            credential_state = (
                "revoked"
                if credential["revoked_at"]
                else "rotated"
                if str(credential["current_version_id"]) != binding["version_id"]
                else "configured"
            )
            present = credential_state == "configured"
    header = version_header(c, row["id"]) if c is not None and workspace_profile else None
    disabled = bool(header and header["disabled_at"])
    return {
        "id": row["id"],
        "name": row["config"].get("profile_name") or row["model_id"] or row["provider_key"],
        "provider": row["provider_key"],
        "model_id": row["model_id"],
        "config_hash": row["config_hash"],
        "workspace_profile": workspace_profile,
        "created_at": row["created_at"],
        "credential_present": present,
        "credential_state": credential_state,
        "credential_name": credential_name,
        "credential_binding": {"id": binding["id"], "version_id": binding["version_id"]}
        if binding
        else None,
        "status": "disabled"
        if disabled
        else "revoked"
        if row["status"] == "revoked"
        else "planning_only",
        "max_output_tokens": row["config"].get("max_output_tokens"),
        "launch_available": False,
        "missing": ["exact_execution_group_admission_required"],
        "profile_id": header["id"] if header else None,
        "version": header["version_no"] if header else None,
        "profile_row_version": header["row_version"] if header else None,
        "is_current": bool(header and str(header["current_connection_id"]) == str(row["id"])),
        "pricing": row["config"].get("workspace_pricing"),
        "pricing_state": pricing_state(row["config"]),
        "processing_terms": row["config"].get("workspace_terms"),
    }


def save_model(c, project, user, body, header=None):
    if body.pricing and body.pricing.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "Pricing metadata must have a future expiry when saved")
    connection, profile = uid(), str(header["id"]) if header else uid()
    previous = str(header["current_connection_id"]) if header else None
    version = header["version_no"] + 1 if header else 1
    if header:
        old = one(c, "SELECT provider_key FROM anvil.connections WHERE id=%s", (previous,))
        if old["provider_key"] != body.provider:
            raise HTTPException(422, "A provider change requires a new profile")
    else:
        c.execute(
            "INSERT INTO anvil.workspace_model_profiles(id,project_id,created_by) VALUES(%s,%s,%s)",
            (profile, project, user),
        )
    config = {
        "profile_name": body.name.strip(),
        "max_output_tokens": body.max_output_tokens,
        "workspace_profile_version": 1,
        "workspace_model_profile_id": profile,
        "workspace_model_revision": version,
        "workspace_pricing": body.pricing.model_dump(mode="json") if body.pricing else None,
        "workspace_terms": {
            "reviewed": body.processing_terms_reviewed,
            "reference": body.processing_terms_reference,
        },
        "pricing_revision": None,
        "bound_micro_usd": None,
        "processing_terms_reviewed": False,
    }
    if body.credential_id:
        credential = one(
            c,
            "SELECT * FROM anvil.workspace_credentials WHERE id=%s FOR SHARE",
            (body.credential_id,),
        )
        if not credential or credential["provider"] != body.provider:
            raise HTTPException(404, "Matching provider credential not found in this project")
        if credential["revoked_at"] or not credential["current_version_id"]:
            raise HTTPException(409, "Credential is revoked or has no saved version")
        if body.credential_version_id and str(body.credential_version_id) != str(
            credential["current_version_id"]
        ):
            raise HTTPException(409, "Credential rotated; explicitly choose its current version")
        config["workspace_credential"] = {
            "id": str(body.credential_id),
            "version_id": str(credential["current_version_id"]),
        }
    checksum = digest(
        {
            "provider": body.provider,
            "model_id": body.model_id,
            "destination": PROVIDERS[body.provider][2],
            "config": config,
            "adapter": "workspace-planning-v1",
        }
    )
    c.execute(
        """INSERT INTO anvil.connections(id,project_id,provider_key,model_id,destination,secret_reference,config,config_hash,created_by)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            connection,
            project,
            body.provider,
            body.model_id,
            PROVIDERS[body.provider][2],
            PROVIDERS[body.provider][1],
            Jsonb(config),
            checksum,
            user,
        ),
    )
    c.execute(
        "INSERT INTO anvil.workspace_model_versions VALUES(%s,%s,%s,%s,%s)",
        (project, profile, connection, version, previous),
    )
    c.execute(
        "UPDATE anvil.workspace_model_profiles SET current_connection_id=%s,row_version=row_version+%s WHERE id=%s",
        (connection, 1 if header else 0, profile),
    )
    audit(
        c,
        project,
        user,
        "workspace.model_version_created",
        connection,
        {
            "profile_id": profile,
            "version": version,
            "previous_connection_id": previous,
            "config_hash": checksum,
            "live_enabled": False,
        },
    )
    return model_public(c, one(c, "SELECT * FROM anvil.connections WHERE id=%s", (connection,)))


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/models")

    @router.get("/{cid}/configuration")
    def configuration(project: UUID, cid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            if not version_header(c, cid):
                raise HTTPException(404, "Workspace model version not found in this project")
            return wrap(
                model_public(c, one(c, "SELECT * FROM anvil.connections WHERE id=%s", (cid,))),
                request,
            )

    @router.post("/{cid}/versions")
    def successor(project: UUID, cid: UUID, body: ModelProfile, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def act():
                header = version_header(c, cid, True)
                if not header:
                    raise HTTPException(404, "Workspace model version not found in this project")
                domain.etag(header, request.headers.get("if-match"))
                if header["disabled_at"]:
                    raise HTTPException(409, "Disabled profiles cannot be reopened")
                if str(header["current_connection_id"]) != str(cid):
                    raise HTTPException(409, "A newer model version exists; reload before editing")
                return save_model(c, project, user, body, header)

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/{cid}/disable")
    def disable(project: UUID, cid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def act():
                header = version_header(c, cid, True)
                if not header:
                    raise HTTPException(404, "Workspace model version not found in this project")
                domain.etag(header, request.headers.get("if-match"))
                if str(header["current_connection_id"]) != str(cid):
                    raise HTTPException(
                        409, "Open the current version before disabling its profile"
                    )
                if not header["disabled_at"]:
                    c.execute(
                        "UPDATE anvil.workspace_model_profiles SET disabled_at=now(),row_version=row_version+1 WHERE id=%s",
                        (header["id"],),
                    )
                    audit(
                        c,
                        project,
                        user,
                        "workspace.model_profile_disabled",
                        header["id"],
                        {"all_versions": True, "historical_bindings_preserved": True},
                    )
                return model_public(
                    c, one(c, "SELECT * FROM anvil.connections WHERE id=%s", (cid,))
                )

            return wrap(idempotent(c, project, user, request, {}, act), request)

    @router.get("/{cid}/versions")
    def history(
        project: UUID,
        cid: UUID,
        request: Request,
        limit: int = Query(30, ge=1, le=100),
        after: int | None = Query(None, ge=1),
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            header = version_header(c, cid)
            if not header:
                raise HTTPException(404, "Workspace model version not found in this project")
            rows = c.execute(
                """SELECT c.*,v.version_no FROM anvil.workspace_model_versions v JOIN anvil.connections c ON c.id=v.connection_id
                WHERE v.profile_id=%s AND (%s::int IS NULL OR v.version_no<%s) ORDER BY v.version_no DESC LIMIT %s""",
                (header["id"], after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": [model_public(c, row) for row in rows[:limit]],
                    "next_cursor": rows[limit - 1]["version_no"] if len(rows) > limit else None,
                },
                request,
            )

    return router
