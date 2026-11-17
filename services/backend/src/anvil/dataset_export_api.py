"""Praxis validation and Anvil-owned Golden provisioning; no paid dispatch."""

import os
import secrets
from contextlib import contextmanager
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field, model_validator

from anvil import auth
from anvil.dataset_export_contract import (
    ASSETS,
    PROFILE_ID,
    VERSION,
    Manifest,
    Model,
    sha,
    trusted_profile,
    validate_archive,
)
from anvil.dataset_export_window import permits as window_permits
from anvil.dataset_export_window import policy as window_policy
from anvil.db import Jsonb, audit, digest, transaction, uid

MAX_UPLOAD = 1024 * 1024


class ClientGrant(Model):
    name: str = Field(min_length=1, max_length=120)
    can_resolve: bool = False
    lifetime_mode: Literal["hours", "testing_window"] = "hours"
    expires_in_hours: int | None = Field(default=None, ge=1, le=168)

    @model_validator(mode="after")
    def lifetime(self):
        if self.lifetime_mode == "testing_window" and self.expires_in_hours is not None:
            raise ValueError("Testing-window access uses the approved pilot end, not an hour value")
        return self


class WorkloadPrincipal(Model):
    subject: str = Field(pattern=r"^[0-9]{6,30}$")
    account_email: str = Field(
        max_length=200,
        pattern=r"^[a-z0-9][a-z0-9._-]*@[a-z0-9][a-z0-9.-]*\.iam\.gserviceaccount\.com$",
    )


class WorkloadGrant(WorkloadPrincipal):
    name: str = Field(min_length=1, max_length=120)
    can_resolve: bool = False


ZIP_REQUEST = {
    "requestBody": {
        "required": True,
        "content": {
            "application/zip": {
                "schema": {"type": "string", "format": "binary", "maxLength": MAX_UPLOAD}
            }
        },
    }
}


def requirement(code, status="blocked"):
    return {"code": code, "owner": "anvil", "status": status}


def decode(raw):
    return validate_archive(raw)


def inspect(c, project, result):
    if not result["valid"]:
        return
    from anvil.golden_kyc_anvil import source_hash

    if source_hash() != trusted_profile()["environment"]["source_sha256"]:
        result["anvil_requirements"].append(requirement("AV_SOURCE_QUALIFICATION_REQUIRED"))
    if os.environ.get("ANVIL_GOLDEN_KYC_ENABLED") != "true":
        result["anvil_requirements"].append(requirement("AV_GOLDEN_RUNTIME_DISABLED"))
    result["review_gates"] = [
        {"code": "REVIEW_CASE_EXPECTATIONS", "owner": "human_review", "status": "pending"},
        {"code": "REVIEW_STATE_CHARTER", "owner": "legal_review", "status": "pending"},
    ]
    pack = c.execute(
        "SELECT id FROM banking.packs WHERE project_id=%s AND manifest->>'public_sha256'=%s AND manifest->>'policy_sha256'=%s ORDER BY created_at,id LIMIT 2",
        (
            project,
            trusted_profile()["environment"]["data_sha256"],
            trusted_profile()["environment"]["policy_sha256"],
        ),
    ).fetchall()
    if not pack:
        result["anvil_requirements"].append(
            requirement("AV_PACK_PROVISIONING_REQUIRED", "required")
        )
    elif len(pack) != 1:
        result["anvil_requirements"].append(requirement("AV_PACK_AMBIGUOUS"))
    else:
        result["anvil_requirements"].append(
            requirement("AV_BINDINGS_RESOLUTION_REQUIRED", "required")
        )


def resolve(c, project, user, raw, result, manifest, client_id=None):
    from anvil.golden_kyc_anvil import register, validate

    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    old = c.execute(
        "SELECT id,package_sha256,resolution,resolution_sha256 FROM anvil.dataset_export_receipts WHERE project_id=%s AND package_id=%s AND package_version=%s",
        (project, manifest.package_id, manifest.package_version),
    ).fetchone()
    if old and old["package_sha256"] != result["package_sha256"]:
        result.update(valid=False, status="export_invalid", error_count=1)
        result["errors"] = [
            {
                "code": "PX_VERSION_CONFLICT",
                "owner": "praxis",
                "file": "anvil-export.json",
                "pointer": "/package_version",
                "message": "This immutable package version already names different content.",
                "fix": "Use the original bytes, or publish corrected content under a new package version.",
                "retryable": False,
            }
        ]
        return result
    blocked = [x for x in result["anvil_requirements"] if x["status"] == "blocked"]
    if blocked:
        return result | {"status": "anvil_blocked"}
    packs = c.execute(
        "SELECT id FROM banking.packs WHERE project_id=%s AND manifest->>'public_sha256'=%s AND manifest->>'policy_sha256'=%s ORDER BY created_at,id LIMIT 2",
        (project, manifest.environment.data_sha256, manifest.environment.policy_sha256),
    ).fetchall()
    if not packs:
        # The separate scheduler owns population and private service controls.
        key = "dataset-export-seed:" + result["package_sha256"][:40]
        command = c.execute(
            "SELECT id,status FROM banking.commands WHERE project_id=%s AND requested_by=%s AND idempotency_key=%s",
            (project, user, key),
        ).fetchone()
        if not command:
            command = c.execute(
                "INSERT INTO banking.commands(id,project_id,requested_by,kind,arguments,idempotency_key,body_sha256) VALUES(%s,%s,%s,'seed','{}',%s,%s) RETURNING id,status",
                (uid(), project, user, key, digest({"kind": "seed", "args": {}})),
            ).fetchone()
        return result | {
            "status": "anvil_provisioning"
            if command["status"] in ("queued", "running")
            else "anvil_blocked",
            "provisioning": {"command_id": str(command["id"]), "state": command["status"]},
        }
    if len(packs) != 1:
        return result | {"status": "anvil_blocked"}
    try:
        # Failure rolls back partial registry creation, but preserves a valid export.
        with c.transaction():
            imported = register(c, project, user, packs[0]["id"])
            row = c.execute(
                "SELECT * FROM banking.anvil_imports WHERE project_id=%s AND id=%s",
                (project, imported["id"]),
            ).fetchone()
            validate(c, row)
            requirements = [
                {k: e[k] for k in ("kind", "requirement", "adapter", "runtime_version")}
                for e in imported["manifest"]["evaluators"]
            ]
            if requirements != trusted_profile()["evaluator_requirements"]:
                raise HTTPException(409, "evaluator requirement differs")
            for binding in imported["manifest"]["bindings"]:
                if binding["task_id"] not in {t.task_id for t in manifest.tasks}:
                    continue
                target = c.execute(
                    "SELECT environment_id,task_id,task_version,snapshot,snapshot_sha256 FROM anvil.environment_task_bindings WHERE project_id=%s AND id=%s",
                    (project, binding["binding_id"]),
                ).fetchone()
                if (
                    not target
                    or str(target["environment_id"]) != imported["environment_id"]
                    or target["task_id"] != binding["task_id"]
                    or digest(target["snapshot"]) != binding["binding_sha256"]
                    or target["snapshot_sha256"] != binding["binding_sha256"]
                    or target["snapshot"]["source_sha256"] != manifest.environment.source_sha256
                ):
                    raise HTTPException(409, "task binding differs")
            if old:
                if (
                    digest(old["resolution"]) != old["resolution_sha256"]
                    or old["resolution"]["import_id"] != imported["id"]
                ):
                    raise HTTPException(409, "resolution changed")
                return result | {
                    "status": "import_resolved",
                    "resolution": old["resolution"],
                    "receipt_id": str(old["id"]),
                    "anvil_requirements": [],
                }
            selected = {t.task_id: t for t in manifest.tasks}
            group = c.execute(
                "SELECT content FROM anvil.benchmark_task_groups WHERE id=%s",
                (row["task_group_id"],),
            ).fetchone()["content"]
            actual = {t["task_id"]: t for t in group["tasks"]}
            for tid, task in selected.items():
                if actual[tid]["payload_sha256"] != task.task_payload_sha256:
                    raise HTTPException(409, "catalog source differs")
            environment = c.execute(
                "SELECT manifest FROM anvil.environment_versions WHERE id=%s",
                (row["environment_id"],),
            ).fetchone()["manifest"]
            if (
                environment["logical_environment_sha256"]
                != manifest.environment.logical_environment_sha256
            ):
                raise HTTPException(409, "environment differs")
            resolution = {
                "schema_version": "anvil.dataset-export-resolution.v1",
                "package_sha256": result["package_sha256"],
                "profile_id": PROFILE_ID,
                "profile_sha256": manifest.profile.sha256,
                "source_sha256": manifest.environment.source_sha256,
                "import_id": imported["id"],
                "import_sha256": imported["manifest_sha256"],
                "task_group_id": imported["task_group_id"],
                "environment_id": imported["environment_id"],
                "environment_manifest_sha256": imported["manifest"]["environment_manifest_sha256"],
                "bindings": [
                    b for b in imported["manifest"]["bindings"] if b["task_id"] in selected
                ],
                "evaluators": imported["manifest"]["evaluators"],
                "run_scope": "full_200_case_software_pack",
                "review_gates": result["review_gates"],
                "paid_calls": False,
                "model_performance": False,
                "authenticated_actor": {
                    "kind": "project_export_client" if client_id else "user_session",
                    "client_id": client_id,
                    "sponsor_user_id": str(user),
                },
            }
            rid = uid()
            c.execute(
                "INSERT INTO anvil.dataset_export_receipts(id,project_id,package_id,package_version,package_sha256,original_zip,resolution,resolution_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    rid,
                    project,
                    manifest.package_id,
                    manifest.package_version,
                    result["package_sha256"],
                    raw,
                    Jsonb(resolution),
                    digest(resolution),
                    user,
                ),
            )
            audit(
                c,
                project,
                user,
                "dataset_export.resolved",
                rid,
                {"package_sha256": result["package_sha256"], "export_client_id": client_id},
            )
            return result | {
                "status": "import_resolved",
                "receipt_id": rid,
                "resolution": resolution,
                "anvil_requirements": [],
            }
    except (HTTPException, ValueError, RuntimeError):
        return result | {
            "status": "anvil_blocked",
            "anvil_requirements": [requirement("AV_BINDING_QUALIFICATION_REQUIRED")],
        }


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/dataset-exports")

    @contextmanager
    def access(request, project, resolving=False):
        values = request.headers.getlist("authorization")
        if not values:
            with context(request, project) as scoped:
                yield scoped
            return
        if len(values) != 1 or request.cookies.get("anvil_session"):
            raise HTTPException(401, "Use one export credential without a browser session")
        scheme, _, token = values[0].partition(" ")
        workload = os.environ.get("ANVIL_PRAXIS_WORKLOAD_IDENTITY_ENABLED") == "true"
        principal = None
        if workload:
            from anvil import pilot_environment
            from anvil.praxis_workload_identity import WorkloadIdentityError, verify

            if scheme.lower() != "bearer" or pilot_environment.current() != "qa":
                raise HTTPException(401, "Valid project-scoped service identity required")
            try:
                principal = verify(token)
            except WorkloadIdentityError:
                raise HTTPException(401, "Valid project-scoped service identity required") from None
        elif (
            scheme.lower() != "bearer" or not token.startswith("anvil_export_") or len(token) > 128
        ):
            raise HTTPException(401, "Valid project-scoped export credential required")
        with transaction(project) as c:
            if principal:
                client = c.execute(
                    "SELECT x.id,x.created_by,x.can_resolve,x.lifetime_mode,x.pilot_environment,x.pilot_end_at FROM anvil.dataset_export_workload_principals p JOIN anvil.dataset_export_clients x ON x.id=p.client_id AND x.project_id=p.project_id JOIN anvil.users u ON u.id=x.created_by AND u.active WHERE p.project_id=%s AND p.issuer=%s AND p.subject=%s AND p.account_email=%s AND p.audience=%s AND x.expires_at>now() AND x.pilot_environment='qa' AND x.lifetime_mode='testing_window' AND NOT EXISTS(SELECT 1 FROM anvil.dataset_export_client_revocations r WHERE r.client_id=x.id) ORDER BY x.created_at DESC LIMIT 1",
                    (
                        project,
                        principal["issuer"],
                        principal["subject"],
                        principal["account_email"],
                        principal["audience"],
                    ),
                ).fetchone()
            else:
                client = c.execute(
                    "SELECT x.id,x.created_by,x.can_resolve,x.lifetime_mode,x.pilot_environment,x.pilot_end_at FROM anvil.dataset_export_clients x JOIN anvil.users u ON u.id=x.created_by AND u.active WHERE x.project_id=%s AND x.token_hash=%s AND x.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.dataset_export_client_revocations r WHERE r.client_id=x.id)",
                    (project, auth.hashed(token)),
                ).fetchone()
            if not client or not window_permits(c, client):
                raise HTTPException(401, "Valid project-scoped export credential required")
            if resolving and not client["can_resolve"]:
                raise HTTPException(403, "Export credential is validation-only")
            c.execute("SELECT set_config('anvil.user',%s,true)", (str(client["created_by"]),))
            roles = auth.project_roles(c, project, client["created_by"])
            auth.require(roles, "admin")
            request.state.export_client_id = str(client["id"])
            request.state.export_auth_kind = (
                "workload_identity" if principal else "project_export_client"
            )
            yield c, client["created_by"], roles

    @router.post("/workload-clients", status_code=201)
    def grant_workload(project: UUID, request: Request, body: WorkloadGrant):
        from anvil import pilot_environment
        from anvil.praxis_workload_identity import ANVIL_AUDIENCE, ISSUER

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            if (
                pilot_environment.current() != "qa"
                or os.environ.get("ANVIL_PRAXIS_WORKLOAD_IDENTITY_ENABLED") != "true"
            ):
                raise HTTPException(503, "QA workload identity is not enabled")
            window = window_policy(c)
            if not window["available"] or window["environment"] != "qa":
                raise HTTPException(409, "Active QA pilot window required")
            identifier = uid()
            # The legacy column remains for immutable grant compatibility. This
            # value is a non-issued grant identifier, never an API credential.
            row = c.execute(
                "INSERT INTO anvil.dataset_export_clients(id,project_id,name,token_hash,can_resolve,created_by,expires_at,lifetime_mode,pilot_environment,pilot_end_at) VALUES(%s,%s,%s,%s,%s,%s,%s::timestamptz,'testing_window','qa',%s::timestamptz) RETURNING expires_at",
                (
                    identifier,
                    project,
                    body.name,
                    auth.hashed("workload-grant:" + identifier),
                    body.can_resolve,
                    user,
                    window["expires_at"],
                    window["expires_at"],
                ),
            ).fetchone()
            c.execute(
                "INSERT INTO anvil.dataset_export_workload_principals(id,project_id,client_id,issuer,subject,account_email,audience,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    uid(),
                    project,
                    identifier,
                    ISSUER,
                    body.subject,
                    body.account_email,
                    ANVIL_AUDIENCE,
                    user,
                ),
            )
            audit(
                c,
                project,
                user,
                "dataset_export.workload_granted",
                identifier,
                {"subject": body.subject, "can_resolve": body.can_resolve},
            )
            return wrap(
                {
                    "client_id": identifier,
                    "authentication": "workload_identity",
                    "subject": body.subject,
                    "audience": ANVIL_AUDIENCE,
                    "expires_at": row["expires_at"].isoformat(),
                    "can_resolve": body.can_resolve,
                    "credential_issued": False,
                },
                request,
            )

    @router.post("/workload-clients/{client}/adopt")
    def adopt_workload(project: UUID, client: UUID, request: Request, body: WorkloadPrincipal):
        """Map a current grant without issuing a key or expanding its authority."""
        from anvil import pilot_environment
        from anvil.praxis_workload_identity import ANVIL_AUDIENCE, ISSUER

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            if (
                pilot_environment.current() != "qa"
                or os.environ.get("ANVIL_PRAXIS_WORKLOAD_IDENTITY_ENABLED") != "true"
            ):
                raise HTTPException(503, "QA workload identity is not enabled")
            window = window_policy(c)
            if not window["available"] or window["environment"] != "qa":
                raise HTTPException(409, "Active QA pilot window required")
            # Use the same project lock as revocation; immutable grant tables
            # deliberately grant no UPDATE privilege (even for a row lock).
            c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
            row = c.execute(
                "SELECT x.* FROM anvil.dataset_export_clients x WHERE x.project_id=%s AND x.id=%s",
                (project, client),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Export grant not found in this project")
            usable = c.execute(
                "SELECT x.id FROM anvil.dataset_export_clients x JOIN anvil.users u ON u.id=x.created_by AND u.active WHERE x.project_id=%s AND x.id=%s AND x.expires_at>now() AND x.expires_at<=%s::timestamptz AND x.pilot_end_at=%s::timestamptz AND x.lifetime_mode='testing_window' AND x.pilot_environment='qa' AND anvil.benchmark_is_admin(x.project_id,x.created_by) AND NOT EXISTS(SELECT 1 FROM anvil.dataset_export_client_revocations r WHERE r.client_id=x.id)",
                (project, client, window["expires_at"], window["expires_at"]),
            ).fetchone()
            if not usable:
                raise HTTPException(
                    409,
                    "Only a current unrevoked QA grant with a live Admin sponsor can be adopted",
                )
            old = c.execute(
                "SELECT * FROM anvil.dataset_export_workload_principals WHERE project_id=%s AND client_id=%s",
                (project, client),
            ).fetchone()
            expected = {
                "issuer": ISSUER,
                "subject": body.subject,
                "account_email": body.account_email,
                "audience": ANVIL_AUDIENCE,
            }
            if old and any(old[key] != value for key, value in expected.items()):
                raise HTTPException(409, "Immutable workload mapping differs; no grant was changed")
            if not old:
                c.execute(
                    "INSERT INTO anvil.dataset_export_workload_principals(id,project_id,client_id,issuer,subject,account_email,audience,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        uid(),
                        project,
                        client,
                        ISSUER,
                        body.subject,
                        body.account_email,
                        ANVIL_AUDIENCE,
                        user,
                    ),
                )
                audit(
                    c,
                    project,
                    user,
                    "dataset_export.workload_adopted",
                    str(client),
                    {
                        "subject": body.subject,
                        "original_sponsor": str(row["created_by"]),
                        "can_resolve": row["can_resolve"],
                        "expires_at": row["expires_at"].isoformat(),
                    },
                )
            return wrap(
                {
                    "client_id": str(client),
                    "authentication": "workload_identity",
                    "subject": body.subject,
                    "audience": ANVIL_AUDIENCE,
                    "expires_at": row["expires_at"].isoformat(),
                    "can_resolve": row["can_resolve"],
                    "credential_issued": False,
                    "existing_grant_preserved": True,
                },
                request,
            )

    @router.post("/clients", status_code=201)
    def grant(project: UUID, request: Request, body: ClientGrant):
        # Only a real authenticated project Admin session can grant capabilities.
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            if os.environ.get("ANVIL_PRAXIS_WORKLOAD_IDENTITY_ENABLED") == "true":
                raise HTTPException(
                    409,
                    "This installation uses workload identity; no integration API key is issued",
                )
            if os.environ.get("ANVIL_EVALUATOR_EXPORT_ENABLED") != "true":
                raise HTTPException(503, "Evaluator export API is disabled")
            token, identifier = "anvil_export_" + secrets.token_urlsafe(32), uid()
            window = window_policy(c) if body.lifetime_mode == "testing_window" else None
            if window is not None and not window["available"]:
                raise HTTPException(
                    409, "Approved testing window is unavailable; Anvil operator action required"
                )
            row = c.execute(
                "INSERT INTO anvil.dataset_export_clients(id,project_id,name,token_hash,can_resolve,created_by,expires_at,lifetime_mode,pilot_environment,pilot_end_at) VALUES(%s,%s,%s,%s,%s,%s,COALESCE(%s::timestamptz,now()+(%s*interval '1 hour')),%s,%s,%s::timestamptz) RETURNING expires_at",
                (
                    identifier,
                    project,
                    body.name,
                    auth.hashed(token),
                    body.can_resolve,
                    user,
                    window["expires_at"] if window else None,
                    body.expires_in_hours or 24,
                    body.lifetime_mode,
                    window["environment"] if window else None,
                    window["expires_at"] if window else None,
                ),
            ).fetchone()
            audit(
                c,
                project,
                user,
                "dataset_export.client_created",
                identifier,
                {
                    "can_resolve": body.can_resolve,
                    "lifetime_mode": body.lifetime_mode,
                    "expires_at": row["expires_at"].isoformat(),
                },
            )
            return wrap(
                {
                    "client_id": identifier,
                    "token": token,
                    "expires_at": row["expires_at"].isoformat(),
                    "can_resolve": body.can_resolve,
                    "lifetime_mode": body.lifetime_mode,
                    "token_display": "once_only_store_on_praxis_server",
                },
                request,
            )

    @router.post("/clients/{client}/revoke")
    def revoke(project: UUID, client: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
            if not c.execute(
                "SELECT id FROM anvil.dataset_export_clients WHERE project_id=%s AND id=%s",
                (project, client),
            ).fetchone():
                raise HTTPException(404, "Export client not found")
            c.execute(
                "INSERT INTO anvil.dataset_export_client_revocations(id,project_id,client_id,created_by) VALUES(%s,%s,%s,%s) ON CONFLICT(client_id) DO NOTHING",
                (uid(), project, client, user),
            )
            audit(c, project, user, "dataset_export.client_revoked", str(client))
            return wrap({"client_id": str(client), "revoked": True}, request)

    @router.get("/clients")
    def clients(project: UUID, request: Request):
        with context(request, project) as (c, _, roles):
            auth.require(roles, "admin")
            rows = c.execute(
                "SELECT x.id,x.name,x.can_resolve,x.expires_at,x.created_at,x.lifetime_mode,x.pilot_environment,EXISTS(SELECT 1 FROM anvil.dataset_export_client_revocations r WHERE r.client_id=x.id) AS revoked,EXISTS(SELECT 1 FROM anvil.dataset_export_workload_principals p WHERE p.client_id=x.id AND p.project_id=x.project_id) AS workload_identity FROM anvil.dataset_export_clients x WHERE x.project_id=%s ORDER BY x.created_at DESC,x.id LIMIT 100",
                (project,),
            ).fetchall()
            from fastapi.encoders import jsonable_encoder

            return wrap(jsonable_encoder(rows), request)

    @router.get("/contracts")
    def contracts(project: UUID, request: Request):
        with access(request, project) as (c, _, roles):
            auth.require(roles, "admin", "rl-engineer")
            return wrap(
                {
                    "contract": VERSION,
                    "generic_discovery": {
                        "path": f"/api/v1/projects/{project}/dataset-exports/generic/contracts",
                        "enabled": os.environ.get("ANVIL_PRAXIS_GENERIC_EXPORT_ENABLED") == "true",
                    },
                    "enabled": os.environ.get("ANVIL_EVALUATOR_EXPORT_ENABLED") == "true",
                    "profile": trusted_profile(),
                    "profile_utf8": (ASSETS / "evaluation-profile.json").read_text(
                        encoding="utf-8"
                    ),
                    "profile_sha256": sha((ASSETS / "evaluation-profile.json").read_bytes()),
                    "manifest_schema": Manifest.model_json_schema(),
                    "media_type": "application/zip",
                    "authentication": {
                        "mode": "workload_identity"
                        if os.environ.get("ANVIL_PRAXIS_WORKLOAD_IDENTITY_ENABLED") == "true"
                        else "not_enabled",
                        "credential_issued": False,
                        "setup_owner": "anvil_operator",
                        "human_key_step_required": False,
                    },
                    "maximum_upload_bytes": MAX_UPLOAD,
                    "paid_calls": False,
                    "credential_policy": {
                        "hours_maximum": 168,
                        "hours_default": 24,
                        "testing_window": window_policy(c),
                    },
                },
                request,
            )

    async def process(project, request, do_resolve=False):
        with access(request, project, do_resolve) as (c, user, roles):
            auth.require(roles, *(("admin",) if do_resolve else ("admin", "rl-engineer")))
            if os.environ.get("ANVIL_EVALUATOR_EXPORT_ENABLED") != "true":
                raise HTTPException(
                    503, "Evaluator export API is disabled; Anvil operator action required"
                )
            if (
                request.headers.get("content-type", "").split(";")[0].strip().lower()
                != "application/zip"
            ):
                raise HTTPException(415, "Use application/zip with raw package bytes")
            raw = await request.body()
            if len(raw) > MAX_UPLOAD:
                raise HTTPException(413, "Dataset export upload exceeds1MiB")
            result, manifest = decode(raw)
            inspect(c, project, result)
            if do_resolve and result["valid"]:
                # Waiting/blocked results are re-evaluated, not cached permanently.
                if (
                    not request.headers.get("Idempotency-Key")
                    or len(request.headers["Idempotency-Key"]) > 200
                ):
                    raise HTTPException(428, "Bounded Idempotency-Key required")
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    {"package_sha256": result["package_sha256"]},
                    lambda: {"accepted": True},
                )
                result = resolve(
                    c,
                    project,
                    user,
                    raw,
                    result,
                    manifest,
                    getattr(request.state, "export_client_id", None),
                )
            status = (
                422
                if not result["valid"]
                else 202
                if result["status"] == "anvil_provisioning"
                else 409
                if result["status"] == "anvil_blocked"
                else 200
            )
            return JSONResponse(wrap(result, request), status_code=status)

    @router.post(
        "/validate",
        openapi_extra=ZIP_REQUEST,
        responses={
            422: {"description": "All detected Praxis-fixable package errors"},
            503: {"description": "Anvil export feature disabled"},
        },
    )
    async def validation(project: UUID, request: Request):
        return await process(project, request)

    @router.post(
        "/resolve",
        openapi_extra=ZIP_REQUEST,
        responses={
            202: {"description": "Anvil provisioning queued"},
            409: {"description": "Anvil qualification blocker or idempotency conflict"},
            422: {"description": "Praxis-fixable package errors"},
        },
    )
    async def resolution(project: UUID, request: Request):
        return await process(project, request, True)

    from anvil.praxis_generic_api import routes as generic_routes

    router.include_router(generic_routes(access, context, wrap, idempotent))

    return router
