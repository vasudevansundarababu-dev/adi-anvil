"""Constrained successor editing over canonical revisions; no approval or dispatch."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field

from anvil import auth, domain
from anvil.db import audit
from anvil.schemas import Strict

WRITE_ROLES = ("admin", "researcher", "data-engineer")
FIELDS = {
    "task": {"title", "capabilities", "rubric_revision_id"},
    "rubric": {"title", "threshold", "criteria"},
    "protocol": {
        "title",
        "comparison_policy",
        "pass_policy",
        "max_output_tokens",
        "episode_timeout_seconds",
    },
}


class CriterionPatch(Strict):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,30}$")
    label: str = Field(min_length=1, max_length=200)
    weight_bps: int = Field(ge=1, le=10000, strict=True)


class RevisionPatch(Strict):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    capabilities: list[str] | None = Field(default=None, min_length=1, max_length=30)
    rubric_revision_id: UUID | None = None
    threshold: float | None = Field(default=None, ge=0, le=100, strict=True)
    criteria: list[CriterionPatch] | None = Field(default=None, min_length=1, max_length=30)
    comparison_policy: str | None = Field(default=None, min_length=20, max_length=5000)
    pass_policy: str | None = Field(default=None, min_length=10, max_length=5000)
    max_output_tokens: int | None = Field(default=None, ge=1, le=8192, strict=True)
    episode_timeout_seconds: int | None = Field(default=None, ge=1, le=600, strict=True)


def public_content(kind, content):
    result = {k: content[k] for k in FIELDS[kind] if k in content}
    if kind == "rubric":
        result["criteria"] = [
            {k: x[k] for k in ("id", "label", "weight_bps")} for x in content["criteria"]
        ]
    return result


def merge(kind, content, patch):
    changes = patch.model_dump(mode="json", exclude_none=True)
    if not changes or set(changes) - FIELDS[kind]:
        raise HTTPException(422, "Only the editable fields for this revision kind are accepted")
    if "capabilities" in changes and any(
        not x.strip() or len(x) > 100 for x in changes["capabilities"]
    ):
        raise HTTPException(422, "Capability labels must be nonempty and at most 100 characters")
    if "criteria" in changes:
        old = {x["id"]: x for x in content["criteria"]}
        criteria = changes["criteria"]
        if len(criteria) != len(old) or {x["id"] for x in criteria} != set(old):
            raise HTTPException(
                422, "Keep the existing criterion IDs; private anchors are preserved server-side"
            )
        if sum(x["weight_bps"] for x in criteria) != 10000:
            raise HTTPException(422, "Criterion weights must total 100 percent")
        changes["criteria"] = [{**old[x["id"]], **x} for x in criteria]
    return {**content, **changes}


def project_editor(c, revision, user, roles):
    kind = revision["kind"]
    if kind not in FIELDS:
        raise HTTPException(
            422, "This editor supports diagnostic tasks, rubrics and evaluation protocols"
        )
    header = domain.get_resource(c, revision["resource_id"])
    current = str(header["current_revision_id"]) == str(revision["id"])
    author = str(revision["created_by"]) == str(user)
    retired = header["lifecycle"] in ("withdrawn", "revoked", "archived")
    options = []
    if kind == "task":
        options = c.execute(
            "SELECT v.id,v.content->>'title' title,v.revision,r.lifecycle FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE r.kind='rubric' ORDER BY r.created_at DESC LIMIT 100"
        ).fetchall()
        bound = domain.get_revision(c, revision["content"]["rubric_revision_id"], "rubric")
        bound_current = domain.get_revision(c, bound["current_revision_id"], "rubric")
        for candidate in (bound, bound_current):
            if not any(str(x["id"]) == str(candidate["id"]) for x in options):
                options.append(
                    {
                        "id": candidate["id"],
                        "title": candidate["content"]["title"],
                        "revision": candidate["revision"],
                        "lifecycle": candidate["lifecycle"]
                        if candidate["id"] == candidate["current_revision_id"]
                        else "historical binding",
                    }
                )
    return {
        "revision_id": revision["id"],
        "resource_id": revision["resource_id"],
        "kind": kind,
        "revision": revision["revision"],
        "content_hash": revision["content_hash"],
        "current_revision_id": header["current_revision_id"],
        "row_version": header["row_version"],
        "lifecycle": header["lifecycle"] if current else "historical",
        "can_save": current and not retired and (author or "admin" in roles),
        "blocked_reason": "Withdrawn or revoked resources cannot be reopened by this editor"
        if retired
        else "A newer version exists; open the current version before editing"
        if not current
        else "Only the revision author or a project Admin can append a version"
        if not (author or "admin" in roles)
        else None,
        "content": public_content(kind, revision["content"]),
        "rubric_options": options,
        "limitations": "Source actor assets, private references, assignments, calibration and execution bindings are preserved. Changing source instructions requires a new source import. Saving moves the resource's current version to an unapproved draft; future dependent launches may await renewed review. Existing run snapshots do not change.",
    }


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace")

    @router.get("/revisions/{vid}/editor")
    def editor(project: UUID, vid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *WRITE_ROLES)
            return wrap(project_editor(c, domain.get_revision(c, vid), user, roles), request)

    @router.post("/revisions/{vid}/successor")
    def successor(project: UUID, vid: UUID, body: RevisionPatch, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *WRITE_ROLES)

            def act():
                base = domain.get_revision(c, vid)
                if base["kind"] not in FIELDS:
                    raise HTTPException(422, "Unsupported editor kind")
                header = domain.get_resource(c, base["resource_id"], True)
                domain.etag(header, request.headers.get("if-match"))
                if header["lifecycle"] in ("withdrawn", "revoked", "archived"):
                    raise HTTPException(
                        409, "Withdrawn or revoked resources cannot be reopened by this editor"
                    )
                if str(header["current_revision_id"]) != str(vid):
                    raise HTTPException(409, "A newer version exists; reload before editing")
                if str(base["created_by"]) != str(user) and "admin" not in roles:
                    raise HTTPException(
                        403, "Only the revision author or a project Admin can append a version"
                    )
                content = merge(base["kind"], base["content"], body)
                if body.rubric_revision_id:
                    domain.get_revision(c, body.rubric_revision_id, "rubric")
                content = domain.validate_content(c, project, base["kind"], content)
                if content == base["content"]:
                    raise HTTPException(422, "No changes to save")
                updated = domain.revise(c, header, user, content)
                audit(
                    c,
                    project,
                    user,
                    "workspace.successor_created",
                    header["id"],
                    {
                        "base_revision_id": str(vid),
                        "new_revision_id": str(updated["current_revision_id"]),
                        "changed_fields": sorted(body.model_dump(exclude_none=True)),
                        "admin_author_override": str(base["created_by"]) != str(user),
                        "approval_carried_forward": False,
                        "calibration_revalidated": False,
                    },
                )
                return project_editor(
                    c, domain.get_revision(c, updated["current_revision_id"]), user, roles
                )

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.get("/resources/{rid}/versions")
    def versions(
        project: UUID,
        rid: UUID,
        request: Request,
        limit: int = Query(30, ge=1, le=100),
        after: int | None = Query(None, ge=1),
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *WRITE_ROLES)
            header = domain.get_resource(c, rid)
            if header["kind"] not in FIELDS:
                raise HTTPException(422, "Unsupported editor kind")
            rows = c.execute(
                "SELECT id,revision,content_hash,created_at FROM anvil.revisions WHERE resource_id=%s AND (%s::int IS NULL OR revision<%s) ORDER BY revision DESC LIMIT %s",
                (rid, after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": rows[:limit],
                    "next_cursor": rows[limit - 1]["revision"] if len(rows) > limit else None,
                },
                request,
            )

    return router
