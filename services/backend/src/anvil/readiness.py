"""Version-bound gap annotations supplement, never replace, qualification evidence."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from anvil import auth, domain
from anvil.db import Jsonb, audit, one
from anvil.schemas import Strict

LABELS = {
    "source_identity": "Source identity",
    "evaluation_rights": "Local evaluation rights",
    "external_processing_rights": "External processing rights",
    "actor_inputs": "Actor inputs",
    "task_definition": "Task definition",
    "reference": "Private reference",
    "rubric": "Approved rubric",
    "execution_compatibility": "Static execution compatibility",
    "calibration": "Rubric calibration review",
}
EDITABLE = set(LABELS) - {"source_identity", "evaluation_rights", "external_processing_rights"}


class GapUpdate(Strict):
    source_revision_id: UUID
    status: Literal["available", "partial", "missing", "not_applicable"]
    explanation: str = Field(min_length=10, max_length=2000)
    owner_user_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=30)


def snapshot(c, source):
    revision = source["current_revision_id"]
    evidence = c.execute(
        """SELECT DISTINCT a.id,a.classification,a.sha256
        FROM anvil.artifact_links l JOIN anvil.artifacts a ON a.id=l.artifact_id
        WHERE l.revision_id=%s AND a.scan_status='clean' ORDER BY a.id""",
        (revision,),
    ).fetchall()
    tasks = c.execute(
        """SELECT v.content, r.lifecycle,
        EXISTS(SELECT 1 FROM anvil.resources rubric WHERE rubric.kind='rubric'
        AND rubric.current_revision_id=(v.content->>'rubric_revision_id')::uuid
        AND rubric.lifecycle='approved') rubric_approved
        FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id
        WHERE r.kind='task' AND r.lifecycle NOT IN ('withdrawn','revoked')
        AND v.content->>'source_revision_id'=%s""",
        (str(revision),),
    ).fetchall()
    derived = {
        "source_identity": bool(source["content"].get("external_case_id")),
        "evaluation_rights": domain.rights_ok(c, revision),
        "external_processing_rights": False,
        "actor_inputs": sum(x["classification"] == "actor" for x in evidence) >= 2,
        "task_definition": bool(tasks),
        "reference": any(x["classification"] == "hidden_reference" for x in evidence),
        "rubric": any(t["rubric_approved"] for t in tasks),
        "execution_compatibility": any(t["content"].get("mode") == "static" for t in tasks),
        "calibration": any(t["rubric_approved"] for t in tasks),
    }
    annotations = {
        row["item_key"]: row
        for row in c.execute(
            "SELECT * FROM anvil.readiness_items WHERE source_revision_id=%s", (revision,)
        ).fetchall()
    }
    items = []
    for key, label in LABELS.items():
        annotation = annotations.get(key)
        status = "available" if derived[key] else "missing"
        if annotation and annotation["status"] in ("missing", "partial"):
            status = annotation["status"] if derived[key] else "missing"
        items.append(
            {
                "item_key": key,
                "label": label,
                "status": status,
                "evidence_satisfied": derived[key],
                "editable": key in EDITABLE,
                "row_version": annotation["row_version"] if annotation else 0,
                "explanation": annotation["explanation"]
                if annotation
                else "No gap annotation recorded; status reflects current local evidence.",
                "owner_user_id": annotation["owner_user_id"] if annotation else None,
                "evidence_ids": annotation["evidence_ids"] if annotation else [],
                "declared_status": annotation["status"] if annotation else None,
                "blocks_operations": (
                    []
                    if status == "available"
                    else [
                        "live_evaluation"
                        if key == "external_processing_rights"
                        else "managed_evaluation"
                    ]
                ),
            }
        )
    return {
        "source_revision_id": str(revision),
        "items": items,
        "evidence_options": evidence,
        "local_blockers": [
            x["item_key"] for x in items if "managed_evaluation" in x["blocks_operations"]
        ],
        "boundary": "Readiness does not grant rights, content approval, faculty validation or live-call authority. Each task is qualified against its own exact evidence.",
    }


def require_no_declared_gaps(c, revision):
    gaps = c.execute(
        "SELECT item_key FROM anvil.readiness_items WHERE source_revision_id=%s AND status IN ('missing','partial')",
        (revision,),
    ).fetchall()
    if gaps:
        raise HTTPException(
            409,
            "Source has unresolved readiness gaps: " + ", ".join(row["item_key"] for row in gaps),
        )


def may_edit(c, user, roles, revision):
    return "data-engineer" in roles or (
        "reviewer" in roles
        and bool(
            one(
                c,
                """SELECT 1 FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id
        WHERE r.kind='task' AND r.lifecycle NOT IN ('withdrawn','revoked') AND v.content->>'source_revision_id'=%s AND v.content->>'reviewer_id'=%s""",
                (str(revision), str(user)),
            )
        )
    )


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}")

    @router.get("/cases/{rid}/readiness")
    def get(project: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *domain.CONTENT_ROLES)
            source = domain.get_resource(c, rid)
            if source["kind"] != "case":
                raise HTTPException(404, "Source not found")
            return wrap(
                snapshot(c, source)
                | {"can_edit": may_edit(c, user, roles, source["current_revision_id"])},
                request,
            )

    @router.patch("/cases/{rid}/readiness/{item}")
    def update(project: UUID, rid: UUID, item: str, body: GapUpdate, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "data-engineer", "reviewer")

            def act():
                source = domain.get_resource(c, rid, True)
                if source["kind"] != "case":
                    raise HTTPException(404, "Source not found")
                if str(source["current_revision_id"]) != str(body.source_revision_id):
                    raise HTTPException(409, "Source version changed; reload its gaps")
                domain.current_source(c, body.source_revision_id, ready=False)
                if item not in EDITABLE:
                    raise HTTPException(
                        422,
                        "This readiness item is derived from identity or independent rights review",
                    )
                if not may_edit(c, user, roles, body.source_revision_id):
                    raise HTTPException(403, "Assigned source reviewer required")
                if body.status == "not_applicable":
                    raise HTTPException(
                        422,
                        "All editable readiness items are required for this static diagnostic slice",
                    )
                if body.owner_user_id and not one(
                    c,
                    "SELECT 1 FROM anvil.memberships WHERE project_id=%s AND user_id=%s AND active",
                    (project, body.owner_user_id),
                ):
                    raise HTTPException(422, "Gap owner must be an active project member")
                for aid in body.evidence_ids:
                    if not one(
                        c,
                        "SELECT 1 FROM anvil.artifacts a JOIN anvil.artifact_links l ON l.artifact_id=a.id WHERE a.id=%s AND a.scan_status='clean' AND l.revision_id=%s",
                        (aid, body.source_revision_id),
                    ):
                        raise HTTPException(
                            422, "Gap evidence must be clean and bound to this source version"
                        )
                if body.status == "available" and not body.evidence_ids:
                    raise HTTPException(422, "Resolving a gap requires source evidence")
                prior = one(
                    c,
                    "SELECT row_version FROM anvil.readiness_items WHERE source_revision_id=%s AND item_key=%s FOR UPDATE",
                    (body.source_revision_id, item),
                )
                domain.etag(prior or {"row_version": 0}, request.headers.get("if-match"))
                c.execute(
                    """INSERT INTO anvil.readiness_items(project_id,source_revision_id,item_key,status,explanation,owner_user_id,evidence_ids,updated_by)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(project_id,source_revision_id,item_key)
                    DO UPDATE SET status=excluded.status,explanation=excluded.explanation,owner_user_id=excluded.owner_user_id,
                    evidence_ids=excluded.evidence_ids,updated_by=excluded.updated_by,updated_at=now(),row_version=anvil.readiness_items.row_version+1""",
                    (
                        project,
                        body.source_revision_id,
                        item,
                        body.status,
                        body.explanation,
                        body.owner_user_id,
                        Jsonb([str(x) for x in body.evidence_ids]),
                        user,
                    ),
                )
                audit(
                    c,
                    project,
                    user,
                    "readiness.updated",
                    rid,
                    body.model_dump(mode="json") | {"item_key": item},
                )
                return snapshot(c, source) | {"can_edit": True}

            return wrap(idempotent(c, project, user, request, body, act), request)

    return router
