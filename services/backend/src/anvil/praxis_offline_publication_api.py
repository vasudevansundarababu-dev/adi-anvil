"""Authenticated local PO attestations, separate from offline upload."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from anvil import auth
from anvil.praxis_generic_contract import canonical, load
from anvil import praxis_offline_publication as ledger


def routes(context, wrap, idempotent, enabled):
    router = APIRouter()

    async def parse(request, model):
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 1048576:
                raise HTTPException(413, "Offline publication request exceeds bound")
            raw.extend(chunk)
        try:
            return model.model_validate_json(canonical(load(bytes(raw))))
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(422, "Invalid offline publication request") from None

    @router.get("/templates/{template}/offline-publications")
    def subjects(project: UUID, template: UUID, request: Request):
        with context(request, project) as (c, _, roles):
            auth.require(roles, "admin", "rl-engineer")
            enabled()
            ledger.template(c, project, template)
            rows = c.execute("SELECT s.id,s.content_sha256,s.raw_record_utf8,s.body_canonical,s.created_by,s.created_at,"
                "EXISTS(SELECT 1 FROM anvil.praxis_offline_publication_revocations r WHERE r.project_id=s.project_id AND r.subject_id=s.id) AS revoked,"
                "a.id AS attestation_id,a.content_sha256 AS attestation_sha256,a.expires_at,a.self_approved,a.created_by AS attested_by,"
                "anvil.offline_publication_current(s.project_id,s.template_id,a.id,a.content_sha256) AS current "
                "FROM anvil.praxis_offline_publication_subjects s LEFT JOIN LATERAL "
                "(SELECT * FROM anvil.praxis_offline_publication_attestations a WHERE a.project_id=s.project_id AND a.subject_id=s.id "
                "ORDER BY a.created_at DESC,a.id DESC LIMIT 1) a ON true "
                "WHERE s.project_id=%s AND s.template_id=%s ORDER BY s.created_at DESC,s.id LIMIT 100", (project, template)).fetchall()
            result = []
            for row in rows:
                body = load(row["body_canonical"].encode())
                result.append({"id": str(row["id"]), "sha256": row["content_sha256"],
                    "raw_record_sha256": body["raw_record_sha256"], "record": body["record"],
                    "created_by": str(row["created_by"]), "created_at": row["created_at"], "revoked": row["revoked"],
                    "attestation": ({"id": str(row["attestation_id"]), "sha256": row["attestation_sha256"],
                         "expires_at": row["expires_at"], "self_approved": row["self_approved"],
                         "attested_by": str(row["attested_by"]), "current": row["current"]} if row["attestation_id"] else None)})
            return wrap({"subjects": result}, request)

    @router.post("/templates/{template}/offline-publications", status_code=201)
    async def stage(project: UUID, template: UUID, request: Request):
        body = await parse(request, ledger.Upload)
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            enabled()
            return wrap(idempotent(c, project, user, request, {"template_id": str(template), **body.model_dump()},
                        lambda: ledger.stage(c, project, user, template, body)), request)

    @router.post("/templates/{template}/offline-publications/{subject}/attest", status_code=201)
    async def attest(project: UUID, template: UUID, subject: UUID, request: Request):
        body = await parse(request, ledger.Attestation)
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            enabled()
            return wrap(idempotent(c, project, user, request,
                {"template_id": str(template), "subject_id": str(subject), **body.model_dump(mode="json")},
                lambda: ledger.attest(c, project, user, template, subject, body)), request)

    @router.post("/templates/{template}/offline-publications/{subject}/revoke")
    async def revoke(project: UUID, template: UUID, subject: UUID, request: Request):
        body = await parse(request, ledger.Revocation)
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            enabled()
            return wrap(idempotent(c, project, user, request,
                {"template_id": str(template), "subject_id": str(subject), **body.model_dump()},
                lambda: ledger.revoke(c, project, user, template, subject, body.reason)), request)

    return router
