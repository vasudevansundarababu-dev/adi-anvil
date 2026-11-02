"""Installation-wide generation settings and project-bound immutable import workflow."""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import Field, model_validator

from anvil import artifacts, auth, workspace_secrets
from anvil.config import CLOUD
from anvil.db import Jsonb, audit, one, uid
from anvil.import_codegen import Bundle, notebook, notebook_code, validate_bundle
from anvil.praxis_executable import parse
from anvil.schemas import Strict
from anvil.workspace_credentials import SecretValue


class Settings(SecretValue):
    provider: Literal["openai", "anthropic", "gemini"]
    model_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:/-]+$")
    default_cap_micro_usd: int = Field(gt=0, le=1000000000, strict=True)
    max_output_tokens: int = Field(ge=1024, le=8192, strict=True)
    max_calls: int = Field(ge=1, le=20, strict=True)
    input_micro_usd_per_million_tokens: int | None = Field(
        default=None, gt=0, le=1000000000, strict=True
    )
    output_micro_usd_per_million_tokens: int | None = Field(
        default=None, gt=0, le=1000000000, strict=True
    )
    pricing_expires_at: datetime | None = None
    enable_paid_generation: bool


class Edit(Strict):
    base_revision_id: UUID
    code: str | None = Field(default=None, max_length=100000)
    notebook: dict | None = None
    artifacts: dict | None = None

    @model_validator(mode="after")
    def bounded_json(self):
        for value in (self.notebook, self.artifacts):
            if value is not None and len(json.dumps(value, allow_nan=False).encode()) > 524288:
                raise ValueError("Edited notebook/artifacts exceed 512 KiB")
        return self


class Generate(Strict):
    rights_confirmed: bool = False
    source_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    settings_id: UUID | None = None
    cap_micro_usd: int | None = Field(default=None, gt=0, le=1000000000, strict=True)


class Rebind(Strict):
    settings_id: UUID
    base_revision_id: UUID


def generation_setting_id(family):
    return family.get("active_settings_id") or family["settings_id"]


def processing_authorized(c, family, source_sha):
    """Exact Admin permission for external processing, independent of testing readiness."""
    event = one(
        c,
        "SELECT * FROM anvil.audit_events WHERE target_id=%s AND action IN ('import.processing_authorized','import.processing_revoked') ORDER BY event_seq DESC LIMIT 1",
        (family["id"],),
    )
    if not event or event["action"] != "import.processing_authorized":
        return False
    bound = event["metadata"]
    return bool(
        bound.get("source_sha256") == source_sha
        and bound.get("settings_id") == str(generation_setting_id(family))
        and bound.get("cap_micro_usd") == family["cap_micro_usd"]
        and datetime.fromisoformat(bound["expires_at"]) > datetime.now(timezone.utc)
        and one(
            c,
            "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id AND u.active WHERE m.project_id=%s AND m.user_id=%s AND m.active AND m.role='admin'",
            (event["project_id"], event["actor_id"]),
        )
    )


def installation_admin(user):
    """Operator-managed Admin scope; a project grant alone cannot administer global keys."""
    return str(user) in {
        v.strip()
        for v in os.environ.get("ANVIL_INSTALLATION_ADMIN_IDS", "").split(",")
        if v.strip()
    }


def settings_public(c, *, admin=False, project_admin=False):
    row = one(
        c,
        "SELECT id,config,revoked_at FROM anvil.import_generation_settings ORDER BY created_at DESC,id DESC LIMIT 1",
    )
    if not row:
        return {
            "configured": False,
            "can_configure": admin,
            "can_authorize_processing": project_admin,
            "missing": "Ask an installation Admin to configure the standard import model and cap.",
        }
    config = row["config"]
    return {
        "configured": not row["revoked_at"],
        "can_configure": admin,
        "can_authorize_processing": project_admin,
        "id": row["id"],
        "provider": config["provider"],
        "model_id": config["model_id"],
        "default_cap_micro_usd": config["default_cap_micro_usd"],
        "paid_generation_enabled": config["enable_paid_generation"],
        "max_calls": config["max_calls"],
        "max_output_tokens": config["max_output_tokens"],
        "credential_saved": not row["revoked_at"],
        "revoked": bool(row["revoked_at"]),
    }


def get_import(c, identifier):
    row = one(c, "SELECT * FROM anvil.executable_imports WHERE id=%s", (identifier,))
    if not row:
        raise HTTPException(404, "Import not found in this project")
    return row


def public(c, row):
    config = one(
        c,
        "SELECT config FROM anvil.import_generation_settings WHERE id=%s",
        (generation_setting_id(row),),
    )["config"]
    revisions = c.execute(
        """SELECT r.id,r.base_revision_id,r.settings_id,r.state,r.kind,r.package_id,r.report,r.cancel_requested,r.created_at,r.finished_at,
        g.config->>'provider' generation_provider,g.config->>'model_id' generation_model
        FROM anvil.executable_import_revisions r JOIN anvil.import_generation_settings g ON g.id=r.settings_id
        WHERE r.import_id=%s ORDER BY r.created_at DESC,r.id DESC LIMIT 100""",
        (row["id"],),
    ).fetchall()
    return {
        k: row[k]
        for k in (
            "id",
            "source_id",
            "settings_id",
            "cap_micro_usd",
            "charged_micro_usd",
            "reserved_micro_usd",
            "current_revision_id",
            "ready_revision_id",
        )
    } | {
        "settings_id": generation_setting_id(row),
        "initial_settings_id": row["settings_id"],
        "remaining_micro_usd": row["cap_micro_usd"]
        - row["charged_micro_usd"]
        - row["reserved_micro_usd"],
        "revisions": revisions,
        "generation_model": {
            "provider": config["provider"],
            "model_id": config["model_id"],
            "paid_generation_enabled": config["enable_paid_generation"],
        },
        "configuration_available": not one(
            c,
            "SELECT revoked_at FROM anvil.import_generation_settings WHERE id=%s",
            (generation_setting_id(row),),
        )["revoked_at"],
        "cost_basis": "configured_conservative_rates",
    }


def source_task(c, row):
    source = one(c, "SELECT * FROM anvil.praxis_sources WHERE id=%s", (row["source_id"],))
    if not source:
        raise HTTPException(404, "Source not found")
    return source, parse(artifacts.read(c, source["source_artifact_id"]))


def enqueue_revision(c, project, user, family, kind, *, bundle=None, base=None):
    from anvil.evaluation import enqueue

    if family["current_revision_id"]:
        current = one(
            c,
            "SELECT state FROM anvil.executable_import_revisions WHERE id=%s",
            (family["current_revision_id"],),
        )
        if current and current["state"] in {"queued", "generating", "validating"}:
            raise HTTPException(409, "This import already has active work; wait or cancel it first")
    rid = uid()
    aid = (
        artifacts.store(c, project, json.dumps(bundle.model_dump()).encode(), "hidden_reference")
        if bundle
        else None
    )
    binding_id = generation_setting_id(family)
    if bundle and base:
        binding_id = one(
            c,
            "SELECT settings_id FROM anvil.executable_import_revisions WHERE id=%s AND import_id=%s",
            (base, family["id"]),
        )["settings_id"]
    c.execute(
        "INSERT INTO anvil.executable_import_revisions(id,project_id,import_id,base_revision_id,settings_id,state,kind,bundle_artifact_id,created_by) VALUES(%s,%s,%s,%s,%s,'queued',%s,%s,%s)",
        (rid, project, family["id"], base, binding_id, kind, aid, user),
    )
    c.execute(
        "UPDATE anvil.executable_imports SET current_revision_id=%s WHERE id=%s",
        (rid, family["id"]),
    )
    enqueue(c, project, "executable_import", rid, "executable-import:" + rid)
    audit(
        c,
        project,
        user,
        "import.revision_queued",
        rid,
        {
            "kind": kind,
            "import_id": str(family["id"]),
            "base_revision_id": str(base) if base else None,
        },
    )
    return public(c, get_import(c, family["id"]))


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace")

    @router.get("/import-generation/settings")
    def settings(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            return wrap(
                settings_public(
                    c,
                    admin="admin" in roles and installation_admin(user),
                    project_admin="admin" in roles,
                ),
                request,
            )

    @router.post("/import-generation/settings")
    def configure(project: UUID, body: Settings, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            if not installation_admin(user):
                raise HTTPException(
                    403,
                    "Installation settings access must be assigned by the operator; project Admin does not grant global credential access",
                )
            if CLOUD:
                raise HTTPException(
                    409,
                    "Managed global secret storage must be configured before cloud credential entry",
                )
            if (
                datetime.now(timezone.utc) - auth.identity(request)["issued_at"]
            ).total_seconds() > 600:
                raise HTTPException(403, "Reauthentication required for credential changes")
            from anvil.workspace_costs import input_bound, managed

            price = managed(body.provider, body.model_id)
            expiry = body.pricing_expires_at or (
                datetime.fromisoformat(price["expires_at"]) if price else None
            )
            if expiry is None or expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise HTTPException(
                    422, "Generation pricing must have a future timezone-aware expiry"
                )

            def act():
                sid = uid()
                config = body.model_dump(mode="json", exclude={"secret"})
                config.update(
                    pricing_expires_at=expiry.isoformat(),
                    input_micro_usd_per_million_tokens=body.input_micro_usd_per_million_tokens
                    or (input_bound(price) if price else None),
                    output_micro_usd_per_million_tokens=body.output_micro_usd_per_million_tokens
                    or (price["output_micro_usd_per_million_tokens"] if price else None),
                )
                if (
                    not config["input_micro_usd_per_million_tokens"]
                    or not config["output_micro_usd_per_million_tokens"]
                ):
                    raise HTTPException(
                        409,
                        "Cost support for this generation model is unavailable; an operator must add verified rates",
                    )
                try:
                    reference = workspace_secrets.save(
                        body.secret.get_secret_value(),
                        {
                            "scope": "installation_import_generation",
                            "settings_id": sid,
                            "provider": body.provider,
                        },
                    )
                except workspace_secrets.StoreUnavailable:
                    raise HTTPException(503, "Generation credential storage unavailable") from None
                c.execute(
                    "INSERT INTO anvil.import_generation_settings(id,config,secret_reference,created_by) VALUES(%s,%s,%s,%s)",
                    (sid, Jsonb(config), reference, user),
                )
                audit(
                    c,
                    project,
                    user,
                    "import.settings_created",
                    sid,
                    {
                        "provider": body.provider,
                        "model_id": body.model_id,
                        "cap_micro_usd": body.default_cap_micro_usd,
                    },
                )
                return settings_public(c, admin=True, project_admin=True)

            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body.model_dump(mode="json", exclude={"secret"})
                    | {"secret_digest": auth.hashed(body.secret.get_secret_value())},
                    act,
                ),
                request,
            )

    @router.post("/import-generation/settings/{sid}/revoke")
    def revoke(project: UUID, sid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            if not installation_admin(user):
                raise HTTPException(403, "Installation settings access required")

            def act():
                c.execute(
                    "UPDATE anvil.import_generation_settings SET revoked_at=coalesce(revoked_at,now()) WHERE id=%s",
                    (sid,),
                )
                audit(c, project, user, "import.settings_revoked", sid)
                return {"revoked": True}

            return wrap(idempotent(c, project, user, request, {}, act), request)

    @router.get("/tasks/{sid}/executable-import")
    def inspect(project: UUID, sid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            if not one(c, "SELECT 1 FROM anvil.praxis_sources WHERE id=%s", (sid,)):
                raise HTTPException(404, "Task not found in this project")
            family = one(c, "SELECT * FROM anvil.executable_imports WHERE source_id=%s", (sid,))
            return wrap(public(c, family) if family else None, request)

    @router.post("/tasks/{sid}/generate")
    def generate(project: UUID, sid: UUID, body: Generate, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")

            def act():
                source, _ = source_task(c, {"source_id": sid})
                family = one(
                    c,
                    "SELECT * FROM anvil.executable_imports WHERE source_id=%s FOR UPDATE",
                    (sid,),
                )
                if not family:
                    settings = one(
                        c,
                        "SELECT * FROM anvil.import_generation_settings ORDER BY created_at DESC,id DESC LIMIT 1",
                    )
                    if not settings or settings["revoked_at"]:
                        raise HTTPException(
                            409,
                            "Configure the installation standard import model, saved key and whole-import cap in Models & keys first",
                        )
                    iid = uid()
                    c.execute(
                        "INSERT INTO anvil.executable_imports(id,project_id,source_id,settings_id,cap_micro_usd,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
                        (
                            iid,
                            project,
                            sid,
                            settings["id"],
                            settings["config"]["default_cap_micro_usd"],
                            user,
                        ),
                    )
                    family = get_import(c, iid)
                if body.rights_confirmed:
                    auth.require(roles, "admin")
                    if (
                        datetime.now(timezone.utc) - auth.identity(request)["issued_at"]
                    ).total_seconds() > 600:
                        raise HTTPException(
                            403,
                            "Please sign in again to confirm external processing for this source",
                        )
                    if (
                        body.source_sha256 != source["source_sha256"]
                        or str(body.settings_id) != str(generation_setting_id(family))
                        or body.cap_micro_usd != family["cap_micro_usd"]
                    ):
                        raise HTTPException(
                            409,
                            "Generation source, model configuration or cap changed; reload before confirming processing permission",
                        )
                    audit(
                        c,
                        project,
                        user,
                        "import.processing_authorized",
                        family["id"],
                        {
                            "source_sha256": source["source_sha256"],
                            "settings_id": str(generation_setting_id(family)),
                            "cap_micro_usd": family["cap_micro_usd"],
                            "expires_at": (
                                datetime.now(timezone.utc) + timedelta(hours=8)
                            ).isoformat(),
                            "policy": "exact-project-admin-generation-processing-v1",
                        },
                    )
                return enqueue_revision(
                    c, project, user, family, "generate", base=family["current_revision_id"]
                )

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/executable-imports/{iid}/processing-rights/revoke")
    def revoke_processing(project: UUID, iid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def act():
                get_import(c, iid)
                audit(c, project, user, "import.processing_revoked", iid)
                return {"revoked": True}

            return wrap(idempotent(c, project, user, request, {}, act), request)

    @router.post("/executable-imports/{iid}/rebind")
    def rebind(project: UUID, iid: UUID, body: Rebind, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def act():
                family = one(
                    c, "SELECT * FROM anvil.executable_imports WHERE id=%s FOR UPDATE", (iid,)
                )
                if not family:
                    raise HTTPException(404, "Import not found in this project")
                current = one(
                    c,
                    "SELECT state FROM anvil.executable_import_revisions WHERE id=%s",
                    (family["current_revision_id"],),
                )
                if str(family["current_revision_id"]) != str(body.base_revision_id) or current[
                    "state"
                ] in {"queued", "generating", "validating"}:
                    raise HTTPException(
                        409,
                        "Wait for current work to finish and reload the current revision before changing generation configuration",
                    )
                target = one(
                    c,
                    "SELECT id,revoked_at FROM anvil.import_generation_settings ORDER BY created_at DESC,id DESC LIMIT 1",
                )
                if not target or target["revoked_at"] or str(target["id"]) != str(body.settings_id):
                    raise HTTPException(
                        409, "Select the current available installation generation configuration"
                    )
                previous = generation_setting_id(family)
                c.execute(
                    "UPDATE anvil.executable_imports SET active_settings_id=%s WHERE id=%s",
                    (body.settings_id, iid),
                )
                audit(
                    c,
                    project,
                    user,
                    "import.generation_rebound",
                    iid,
                    {
                        "previous_settings_id": str(previous),
                        "settings_id": str(body.settings_id),
                        "cap_unchanged": family["cap_micro_usd"],
                        "charged_unchanged": family["charged_micro_usd"],
                        "reserved_unchanged": family["reserved_micro_usd"],
                    },
                )
                return public(c, get_import(c, iid))

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/executable-imports/{iid}/cancel")
    def cancel(project: UUID, iid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")

            def act():
                family = get_import(c, iid)
                c.execute(
                    "UPDATE anvil.executable_import_revisions SET cancel_requested=true WHERE id=%s AND state IN ('queued','generating','validating')",
                    (family["current_revision_id"],),
                )
                audit(c, project, user, "import.cancel_requested", iid)
                return public(c, family)

            return wrap(idempotent(c, project, user, request, {}, act), request)

    @router.get("/executable-imports/{iid}/revisions/{rid}/code")
    def code(project: UUID, iid: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            get_import(c, iid)
            revision = one(
                c,
                "SELECT * FROM anvil.executable_import_revisions WHERE id=%s AND import_id=%s",
                (rid, iid),
            )
            if not revision or not revision["bundle_artifact_id"]:
                raise HTTPException(404, "No generated code for this revision")
            bundle = Bundle.model_validate_json(artifacts.read(c, revision["bundle_artifact_id"]))
            audit(c, project, user, "import.generated_code_viewed", rid)
            # Generated consistency cases may be edited. Source QA oracle/private inputs
            # are never copied into this artifact set or read by this endpoint.
            return wrap(bundle.model_dump(), request)

    @router.get("/executable-imports/{iid}/revisions/{rid}/notebook")
    def download(project: UUID, iid: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            family = get_import(c, iid)
            source, task = source_task(c, family)
            revision = one(
                c,
                "SELECT * FROM anvil.executable_import_revisions WHERE id=%s AND import_id=%s",
                (rid, iid),
            )
            if not revision or not revision["bundle_artifact_id"]:
                raise HTTPException(404, "No generated notebook for this revision")
            bundle = Bundle.model_validate_json(artifacts.read(c, revision["bundle_artifact_id"]))
            audit(c, project, user, "import.notebook_downloaded", rid)
            return Response(
                json.dumps(
                    notebook(
                        bundle,
                        rid,
                        source["source_sha256"],
                        {
                            a.path: json.loads(a.content)
                            if a.media_type == "application/json"
                            else a.content
                            for a in task.inputs
                            if a.visibility == "actor"
                        },
                    )
                ),
                media_type="application/x-ipynb+json",
                headers={"Content-Disposition": 'attachment; filename="anvil-review.ipynb"'},
            )

    @router.post("/executable-imports/{iid}/edit")
    def edit(project: UUID, iid: UUID, body: Edit, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")

            def act():
                family = get_import(c, iid)
                c.execute("SELECT id FROM anvil.executable_imports WHERE id=%s FOR UPDATE", (iid,))
                if str(family["current_revision_id"]) != str(body.base_revision_id):
                    raise HTTPException(
                        409, "Base version changed; open the latest draft before saving"
                    )
                base = one(
                    c,
                    "SELECT * FROM anvil.executable_import_revisions WHERE id=%s AND import_id=%s",
                    (body.base_revision_id, iid),
                )
                if not base or not base["bundle_artifact_id"]:
                    raise HTTPException(409, "Generate a valid artifact set before editing")
                source, task = source_task(c, family)
                value = json.loads(artifacts.read(c, base["bundle_artifact_id"]))
                try:
                    if sum(v is not None for v in (body.code, body.notebook, body.artifacts)) != 1:
                        raise ValueError(
                            "Supply code, generated artifacts or an edited notebook, exactly one"
                        )
                    if body.artifacts is not None:
                        value = body.artifacts
                    else:
                        value["code"] = (
                            body.code
                            if body.code is not None
                            else notebook_code(
                                body.notebook, body.base_revision_id, source["source_sha256"]
                            )
                        )
                    bundle = validate_bundle(task, value)
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from None
                return enqueue_revision(
                    c, project, user, family, "edit", bundle=bundle, base=body.base_revision_id
                )

            return wrap(idempotent(c, project, user, request, body, act), request)

    return router
