"""Authorized Praxis intake and explicit synthetic Harbor software verification."""

import hashlib
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from anvil import artifacts, auth
from anvil.db import Jsonb, audit, one, uid
from anvil.harbor_package import compile_package
from anvil.praxis_contract import actor_view
from anvil.praxis_export import parse_export
from anvil.schemas import Strict


class Import(Strict):
    payload: str = Field(min_length=1, max_length=1048576)


class Approve(Strict):
    package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rationale: str = Field(min_length=10, max_length=2000)
    scope: Literal["synthetic_software_checks_only"]


class Check(Strict):
    candidate: Literal["reference", "empty_output", "constraint_failure"]


def get(c, table, identifier):
    if table not in {"praxis_sources", "harbor_packages", "harbor_checks"}:
        raise ValueError("Unsupported record")
    row = one(c, f"SELECT * FROM anvil.{table} WHERE id=%s", (identifier,))
    if not row:
        raise HTTPException(404, "Record not found in this project")
    return row


def source_public(row, c=None):
    result = {
        k: row[k]
        for k in (
            "id",
            "task_id",
            "task_version",
            "revision_id",
            "source_sha256",
            "actor_spec",
            "created_at",
        )
    }
    if c is not None:
        result["export_receipts"] = [
            {
                "id": r["id"],
                "envelope_sha256": r["envelope_sha256"],
                "record_id": r["lineage"]["record_id"],
                "record_hash": r["lineage"]["record_hash"],
                "attestation": "unverified_source_metadata",
            }
            for r in c.execute(
                "SELECT id,envelope_sha256,lineage FROM anvil.praxis_export_receipts WHERE source_id=%s ORDER BY created_at",
                (row["id"],),
            ).fetchall()
        ]
    return result


def store_receipt(c, project, user, sid, raw, envelope):
    if envelope is None:
        return
    checksum = hashlib.sha256(raw).hexdigest()
    if one(c, "SELECT 1 FROM anvil.praxis_export_receipts WHERE envelope_sha256=%s", (checksum,)):
        return
    aid = artifacts.store(c, project, raw, "hidden_reference")
    c.execute(
        "INSERT INTO anvil.praxis_export_receipts(id,project_id,source_id,envelope_sha256,envelope_artifact_id,lineage,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (uid(), project, sid, checksum, aid, Jsonb(envelope.source.model_dump()), user),
    )
    audit(
        c,
        project,
        user,
        "praxis.export_receipt_recorded",
        sid,
        {"envelope_sha256": checksum, "source_metadata_verified": False},
    )


def package_public(c, row):
    approval = one(
        c,
        "SELECT approved_by,scope,self_approved FROM anvil.harbor_approvals WHERE package_id=%s",
        (row["id"],),
    )
    # Source review is retained privately and never exposed as Anvil approval.
    manifest = {k: v for k, v in row["manifest"].items() if k != "source_review"}
    return {
        "id": row["id"],
        "source_id": row["source_id"],
        "package_sha256": row["package_sha256"],
        "manifest": manifest,
        "approval": approval,
        "live_execution": "blocked_unmetered_agent_adapter",
        "qualification": "software_checks_only; not model performance or rights clearance",
    }


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}")

    @router.get("/praxis-sources")
    def listing(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "data-engineer", "product-owner")
            return wrap(
                [
                    source_public(r, c)
                    for r in c.execute(
                        "SELECT * FROM anvil.praxis_sources ORDER BY created_at DESC LIMIT 100"
                    ).fetchall()
                ],
                request,
            )

    @router.post("/praxis-sources")
    def intake(project: UUID, body: Import, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "data-engineer", "product-owner")

            def act():
                received = body.payload.encode("utf-8")
                if len(received) > 1024 * 1024:
                    raise HTTPException(422, "Praxis export exceeds 1 MiB")
                try:
                    raw, envelope = parse_export(received)
                    task, _, _ = compile_package(raw)
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from None
                checksum = hashlib.sha256(raw).hexdigest()
                old = one(
                    c,
                    "SELECT * FROM anvil.praxis_sources WHERE task_id=%s AND revision_id=%s",
                    (task.task_id, task.revision_id),
                )
                if old:
                    if old["source_sha256"] != checksum:
                        raise HTTPException(409, "Immutable source revision has conflicting bytes")
                    store_receipt(c, project, user, old["id"], received, envelope)
                    return source_public(old, c)
                if one(
                    c,
                    "SELECT 1 FROM anvil.praxis_sources WHERE task_id=%s AND task_version=%s",
                    (task.task_id, task.task_version),
                ):
                    raise HTTPException(
                        409,
                        "task_version already binds another immutable revision; export a new task_version",
                    )
                aid = artifacts.store(c, project, raw, "hidden_reference", origin="illustrative")
                sid = uid()
                c.execute(
                    """INSERT INTO anvil.praxis_sources(id,project_id,task_id,task_version,revision_id,
                    source_sha256,source_artifact_id,actor_spec,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        sid,
                        project,
                        task.task_id,
                        task.task_version,
                        task.revision_id,
                        checksum,
                        aid,
                        Jsonb(actor_view(task)),
                        user,
                    ),
                )
                audit(
                    c,
                    project,
                    user,
                    "praxis.imported",
                    sid,
                    {"source_sha256": checksum, "source_review_is_local_approval": False},
                )
                store_receipt(c, project, user, sid, received, envelope)
                return source_public(get(c, "praxis_sources", sid), c)

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/praxis-sources/{sid}/build")
    def build(project: UUID, sid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "data-engineer", "product-owner")

            def act():
                source = get(c, "praxis_sources", sid)
                raw = artifacts.read(c, source["source_artifact_id"])
                _, manifest, package = compile_package(raw)
                checksum = hashlib.sha256(package).hexdigest()
                old = one(
                    c,
                    "SELECT * FROM anvil.harbor_packages WHERE source_id=%s AND package_sha256=%s",
                    (sid, checksum),
                )
                if old:
                    return package_public(c, old)
                aid = artifacts.store(
                    c, project, package, "hidden_reference", mime="application/zip"
                )
                pid = uid()
                c.execute(
                    """INSERT INTO anvil.harbor_packages(id,project_id,source_id,package_sha256,
                    package_artifact_id,manifest,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                    (pid, project, sid, checksum, aid, Jsonb(manifest), user),
                )
                audit(c, project, user, "harbor.package_built", pid, {"package_sha256": checksum})
                return package_public(c, get(c, "harbor_packages", pid))

            return wrap(idempotent(c, project, user, request, {}, act), request)

    @router.get("/harbor-packages/{pid}")
    def inspect(project: UUID, pid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "data-engineer", "product-owner")
            return wrap(package_public(c, get(c, "harbor_packages", pid)), request)

    @router.get("/praxis-sources/{sid}/packages")
    def packages(project: UUID, sid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "data-engineer", "product-owner")
            get(c, "praxis_sources", sid)
            return wrap(
                [
                    package_public(c, p)
                    for p in c.execute(
                        "SELECT * FROM anvil.harbor_packages WHERE source_id=%s ORDER BY created_at DESC LIMIT 100",
                        (sid,),
                    ).fetchall()
                ],
                request,
            )

    @router.get("/harbor-packages/{pid}/checks")
    def checks(project: UUID, pid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "data-engineer", "product-owner")
            get(c, "harbor_packages", pid)
            return wrap(
                c.execute(
                    "SELECT * FROM anvil.harbor_checks WHERE package_id=%s ORDER BY created_at DESC LIMIT 100",
                    (pid,),
                ).fetchall(),
                request,
            )

    @router.post("/harbor-packages/{pid}/approve")
    def approve(project: UUID, pid: UUID, body: Approve, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "product-owner")

            def act():
                package = get(c, "harbor_packages", pid)
                if package["package_sha256"] != body.package_sha256:
                    raise HTTPException(409, "Approval must bind the exact package hash")
                self_approved = str(package["created_by"]) == str(user)
                c.execute(
                    """INSERT INTO anvil.harbor_approvals(id,project_id,package_id,approved_by,rationale,self_approved,scope)
                    VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(project_id,package_id) DO NOTHING""",
                    (uid(), project, pid, user, body.rationale, self_approved, body.scope),
                )
                audit(
                    c,
                    project,
                    user,
                    "harbor.software_checks_approved",
                    pid,
                    {
                        "self_approved": self_approved,
                        "package_sha256": body.package_sha256,
                        "scope": body.scope,
                    },
                )
                return package_public(c, package)

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/harbor-packages/{pid}/checks")
    def check(project: UUID, pid: UUID, body: Check, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "product-owner")

            def act():
                package = get(c, "harbor_packages", pid)
                if body.candidate == "constraint_failure" and not package["manifest"].get(
                    "constraint_failure_supported"
                ):
                    raise HTTPException(
                        409, "No supported numeric hard-failure check in this package"
                    )
                if not one(c, "SELECT 1 FROM anvil.harbor_approvals WHERE package_id=%s", (pid,)):
                    if "admin" not in roles:
                        raise HTTPException(
                            409,
                            "Admin authorization for exact synthetic software checks is required",
                        )
                    c.execute(
                        """INSERT INTO anvil.harbor_approvals(id,project_id,package_id,approved_by,rationale,self_approved,scope)
                        VALUES(%s,%s,%s,%s,'Admin Run authorizes this exact software check',%s,'synthetic_software_checks_only') ON CONFLICT(project_id,package_id) DO NOTHING""",
                        (uid(), project, pid, user, str(package["created_by"]) == str(user)),
                    )
                    audit(
                        c,
                        project,
                        user,
                        "harbor.admin_run_authorized",
                        pid,
                        {
                            "package_sha256": package["package_sha256"],
                            "scope": "synthetic_software_checks_only",
                        },
                    )
                if one(
                    c,
                    "SELECT 1 FROM anvil.harbor_checks WHERE state IN ('queued','running') LIMIT 1",
                ):
                    raise HTTPException(
                        409, "Finish or cancel the active project software check first"
                    )
                hid = uid()
                c.execute(
                    "INSERT INTO anvil.harbor_checks(id,project_id,package_id,created_by,candidate) VALUES(%s,%s,%s,%s,%s)",
                    (hid, project, pid, user, body.candidate),
                )
                c.execute(
                    "INSERT INTO anvil.jobs(id,project_id,kind,target_id,operation_key) VALUES(%s,%s,'harbor_check',%s,%s)",
                    (uid(), project, hid, "harbor-check:" + hid),
                )
                audit(
                    c,
                    project,
                    user,
                    "harbor.check_queued",
                    hid,
                    {
                        "candidate": body.candidate,
                        "origin": "synthetic_software_verification",
                        "model_performance": False,
                    },
                )
                return get(c, "harbor_checks", hid)

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.get("/harbor-checks/{hid}")
    def status(project: UUID, hid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "data-engineer", "product-owner")
            return wrap(get(c, "harbor_checks", hid), request)

    @router.post("/harbor-checks/{hid}/cancel")
    def cancel(project: UUID, hid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "researcher", "product-owner")

            def act():
                row = get(c, "harbor_checks", hid)
                if row["state"] in ("queued", "running"):
                    c.execute(
                        "UPDATE anvil.harbor_checks SET cancel_requested=true,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END WHERE id=%s",
                        (hid,),
                    )
                    c.execute(
                        "UPDATE anvil.jobs SET status='cancelled' WHERE target_id=%s AND kind='harbor_check' AND status='queued'",
                        (hid,),
                    )
                    audit(c, project, user, "harbor.cancel_requested", hid)
                return get(c, "harbor_checks", hid)

            return wrap(idempotent(c, project, user, request, {}, act), request)

    return router
