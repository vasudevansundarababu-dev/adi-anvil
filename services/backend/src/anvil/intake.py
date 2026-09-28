"""Private manifest intake. Partner claims confer neither approval nor rights."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, ValidationError, model_validator

from anvil import artifacts, auth, domain
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.schemas import Strict


class Readiness(Strict):
    item_key: str = Field(min_length=1, max_length=100)
    status: Literal["missing", "partial", "available", "not_applicable"]
    explanation: str = Field(max_length=2000)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def explained_exception(self):
        if self.status == "not_applicable" and (
            len(self.explanation.strip()) < 10 or not self.evidence_ids
        ):
            raise ValueError("Not-applicable declarations require an explanation and evidence")
        return self


class Declaration(Strict):
    operation: str = Field(min_length=1, max_length=100)
    status: Literal["unknown", "approved", "denied", "revoked"]
    evidence_artifact_id: UUID | None = None


class Case(Strict):
    external_case_id: str = Field(min_length=1, max_length=100)
    source_version: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=3, max_length=300)
    subjects: list[str] = Field(min_length=1, max_length=30)
    source_family_key: str = Field(min_length=1, max_length=100)
    exposure: Literal["controlled", "known", "unknown"] = "unknown"
    information_cutoff: date | None = None
    artifact_ids: list[UUID] = Field(min_length=1, max_length=30)
    provenance: dict
    readiness: list[Readiness] = Field(default_factory=list, max_length=30)
    rights_declarations: list[Declaration] = Field(default_factory=list, max_length=30)


class Manifest(Strict):
    schema_version: Literal["anvil.case_import.v1"]
    partner_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    cases: list[dict] = Field(min_length=1, max_length=200)


class Commit(Strict):
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def validate(c, manifest):
    errors, seen = [], set()
    for index, raw in enumerate(manifest["cases"]):
        try:
            case = Case.model_validate(raw)
        except ValidationError as exc:
            errors.append(
                {
                    "row": index,
                    "code": "invalid_case",
                    "fields": [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()],
                }
            )
            continue
        if case.external_case_id in seen:
            errors.append({"row": index, "code": "duplicate_external_id"})
        seen.add(case.external_case_id)
        ids = set(case.artifact_ids)
        for item in case.readiness:
            ids.update(item.evidence_ids)
        ids.update(
            d.evidence_artifact_id for d in case.rights_declarations if d.evidence_artifact_id
        )
        for aid in ids:
            try:
                artifacts.read(c, aid)
            except (HTTPException, OSError):
                errors.append(
                    {"row": index, "code": "artifact_unavailable", "artifact_id": str(aid)}
                )
        prior = one(
            c,
            "SELECT content_hash FROM anvil.source_import_receipts WHERE partner_key=%s AND external_case_id=%s AND source_version=%s",
            (manifest["partner_key"], case.external_case_id, case.source_version),
        )
        if prior and prior["content_hash"] != digest(raw):
            errors.append({"row": index, "code": "source_version_conflict"})
    return errors


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}")

    @router.post("/imports/validate")
    def preview(project: UUID, body: Manifest, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "data-engineer")

            def act():
                manifest = body.model_dump(mode="json")
                errors = validate(c, manifest)
                bid, h = uid(), digest(manifest)
                status = "rejected" if errors else "validated"
                c.execute(
                    "INSERT INTO anvil.import_batches(id,project_id,created_by,manifest,manifest_hash,status,validation_errors) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (bid, project, user, Jsonb(manifest), h, status, Jsonb(errors)),
                )
                audit(
                    c,
                    project,
                    user,
                    "import.validated",
                    bid,
                    {"row_count": len(body.cases), "error_count": len(errors)},
                )
                return {
                    "id": bid,
                    "manifest_hash": h,
                    "status": status,
                    "errors": errors,
                    "case_count": len(body.cases),
                    "rights": "Declarations require independent review",
                }

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/imports/{bid}/commit")
    def commit(project: UUID, bid: UUID, body: Commit, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "data-engineer")

            def act():
                batch = one(c, "SELECT * FROM anvil.import_batches WHERE id=%s FOR UPDATE", (bid,))
                if not batch:
                    raise HTTPException(404, "Import batch not found")
                if batch["manifest_hash"] != body.manifest_hash:
                    raise HTTPException(409, "Manifest hash changed")
                if batch["manifest"].get("schema_version") != "anvil.case_import.v1":
                    raise HTTPException(409, "Case import manifest required")
                if batch["status"] == "committed":
                    return {
                        "id": str(bid),
                        "source_ids": batch["committed_source_ids"],
                        "source_revision_ids": batch["committed_revision_ids"],
                        "status": "committed",
                    }
                manifest = batch["manifest"]
                errors = validate(c, manifest)
                if errors or batch["status"] != "validated":
                    raise HTTPException(409, {"code": "import_not_ready", "errors": errors})
                sources, revisions = [], []
                for raw in manifest["cases"]:
                    case = Case.model_validate(raw)
                    prior = one(
                        c,
                        "SELECT resource_id,revision_id FROM anvil.source_import_receipts WHERE partner_key=%s AND external_case_id=%s AND source_version=%s",
                        (manifest["partner_key"], case.external_case_id, case.source_version),
                    )
                    if prior:
                        sources.append(str(prior["resource_id"]))
                        revisions.append(str(prior["revision_id"]))
                        continue
                    content = {
                        **raw,
                        "partner_key": manifest["partner_key"],
                        "source_origin": "partner_reported",
                        "faculty_validation": None,
                        "qualification": "not_reviewed",
                        "rights_status": "unknown",
                    }
                    identities = c.execute(
                        "SELECT DISTINCT resource_id FROM anvil.source_import_receipts WHERE partner_key=%s AND external_case_id=%s",
                        (manifest["partner_key"], case.external_case_id),
                    ).fetchall()
                    if len(identities) > 1:
                        raise HTTPException(
                            409,
                            "Historical source identity conflict requires explicit reconciliation",
                        )
                    if identities:
                        existing = domain.get_resource(c, identities[0]["resource_id"], True)
                        if existing["lifecycle"] in ("withdrawn", "revoked"):
                            raise HTTPException(
                                409, "Withdrawn source cannot receive an automatic successor"
                            )
                        source = domain.revise(c, existing, user, content)
                    else:
                        source = domain.create(c, project, user, "case", content)
                    for aid in case.artifact_ids:
                        c.execute(
                            "INSERT INTO anvil.artifact_links VALUES(%s,%s,%s,'original')",
                            (project, source["current_revision_id"], aid),
                        )
                    c.execute(
                        "INSERT INTO anvil.source_import_receipts(project_id,partner_key,external_case_id,source_version,content_hash,resource_id,revision_id) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                        (
                            project,
                            manifest["partner_key"],
                            case.external_case_id,
                            case.source_version,
                            digest(raw),
                            source["id"],
                            source["current_revision_id"],
                        ),
                    )
                    sources.append(str(source["id"]))
                    revisions.append(str(source["current_revision_id"]))
                c.execute(
                    "UPDATE anvil.import_batches SET status='committed',committed_source_ids=%s,committed_revision_ids=%s WHERE id=%s",
                    (Jsonb(sources), Jsonb(revisions), bid),
                )
                audit(c, project, user, "import.committed", bid, {"case_count": len(sources)})
                return {
                    "id": str(bid),
                    "source_ids": sources,
                    "source_revision_ids": revisions,
                    "status": "committed",
                }

            return wrap(idempotent(c, project, user, request, body, act), request)

    return router
