"""Report release authority is separate from source, spend and human scoring facts."""

from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, StrictBool

from anvil.db import Jsonb, audit, digest, one, uid
from anvil.schemas import Strict


class Configure(Strict):
    required_reviewers: int = Field(strict=True, ge=0, le=10)
    rationale: str = Field(
        default="Authenticated Admin report policy configuration", min_length=10, max_length=2000
    )


class Approve(Strict):
    expected_result_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rationale: str = Field(min_length=10, max_length=2000)


class Review(Approve):
    assignment_id: UUID
    human_reviewed: StrictBool


def is_admin(c, project, user):
    return bool(
        one(
            c,
            "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id AND u.active WHERE m.project_id=%s AND m.user_id=%s AND m.active AND m.role='admin'",
            (project, user),
        )
    )


def current(c, project):
    row = one(
        c,
        "SELECT * FROM anvil.benchmark_report_policies WHERE project_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
        (project,),
    )
    policy = {
        "version": 2,
        "policy_id": str(row["id"]) if row else None,
        "required_reviewers": row["required_reviewers"] if row else 1,
        "admin_run_exempt": True,
        "admin_approval_exempt": True,
    }
    return policy | {
        "policy_sha256": digest(policy),
        "revision": str(row["id"]) if row else "default-v2",
    }


def configure(c, project, user, body):
    if not is_admin(c, project, user):
        raise HTTPException(403, "Only an authenticated project Admin may configure report review")
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_report_policies(id,project_id,required_reviewers,created_by,rationale) VALUES(%s,%s,%s,%s,%s)",
        (identifier, project, body.required_reviewers, user, body.rationale),
    )
    audit(
        c,
        project,
        user,
        "benchmark.report_policy_configured",
        identifier,
        {"required_reviewers": body.required_reviewers},
    )
    return current(c, project)


def snapshot(c, project, user, kind, target, policy=None, *, executing=True):
    frozen = policy or current(c, project)
    c.execute(
        "INSERT INTO anvil.benchmark_report_authorizations(id,project_id,target_kind,target_id,policy,policy_sha256,admin_run_exempt,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            uid(),
            project,
            kind,
            target,
            Jsonb(frozen),
            frozen["policy_sha256"],
            executing and is_admin(c, project, user),
            user,
        ),
    )


def record_execution(c, project, user, kind, target):
    if is_admin(c, project, user):
        c.execute(
            "INSERT INTO anvil.benchmark_report_admin_executions(id,project_id,target_kind,target_id,actor_id) VALUES(%s,%s,%s,%s,%s)",
            (uid(), project, kind, target, user),
        )
        audit(c, project, user, "benchmark.admin_report_execution", target, {"target_kind": kind})


def authorization(c, project, kind, target, result_sha256):
    row = one(
        c,
        "SELECT * FROM anvil.benchmark_report_authorizations WHERE project_id=%s AND target_kind=%s AND target_id=%s",
        (project, kind, target),
    )
    decisions = (
        c.execute(
            "SELECT d.* FROM anvil.benchmark_report_decisions d WHERE d.project_id=%s AND d.target_kind=%s AND d.target_id=%s AND d.result_sha256=%s ORDER BY d.created_at,d.id",
            (project, kind, target, result_sha256),
        ).fetchall()
        if result_sha256
        else []
    )
    admin = [d for d in decisions if d["decision"] == "admin_approved"]
    execution = one(
        c,
        "SELECT actor_id FROM anvil.benchmark_report_admin_executions WHERE project_id=%s AND target_kind=%s AND target_id=%s",
        (project, kind, target),
    )
    required = row["policy"]["required_reviewers"] if row else None
    reviewers = {str(d["actor_id"]) for d in decisions if d["decision"] == "reviewed"}
    state = "legacy_review_policy" if not row else "pending_review"
    if admin:
        state = "admin_approved"
    elif execution or (row and row["admin_run_exempt"]):
        state = "admin_run_exempt"
    elif required == 0:
        state = "policy_no_review"
    elif required is not None and len(reviewers) >= required:
        state = "reviewed"
    return {
        "state": state,
        "ready": bool(result_sha256)
        and state in {"admin_approved", "admin_run_exempt", "policy_no_review", "reviewed"},
        "required_reviewers": required,
        "completed_reviewers": len(reviewers),
        "policy_sha256": row["policy_sha256"] if row else None,
        "reviewer_verified": state == "reviewed",
        "policy": row["policy"] if row else None,
        "result_sha256": result_sha256,
        "admin_actor_id": str(admin[0]["actor_id"])
        if admin
        else str(execution["actor_id"])
        if execution
        else str(row["actor_id"])
        if row and row["admin_run_exempt"]
        else None,
    }


def decide(c, project, user, kind, target, result_sha256, body, *, admin=False):
    if body.expected_result_sha256 != result_sha256:
        raise HTTPException(409, "Exact immutable result hash required")
    if admin:
        if not is_admin(c, project, user):
            raise HTTPException(403, "Current authenticated project Admin required")
    else:
        if not body.human_reviewed:
            raise HTTPException(422, "Explicit human review confirmation required")
        duty = one(
            c,
            "SELECT 1 FROM anvil.benchmark_private_assignments a WHERE a.project_id=%s AND a.id=%s AND a.user_id=%s AND a.scope='evaluation_review' AND a.artifact_id IS NULL AND a.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r WHERE r.assignment_id=a.id)",
            (project, body.assignment_id, user),
        )
        if not duty:
            raise HTTPException(403, "Current individual evaluation duty required")
    existing = one(
        c,
        "SELECT decision FROM anvil.benchmark_report_decisions WHERE project_id=%s AND target_kind=%s AND target_id=%s AND result_sha256=%s AND actor_id=%s",
        (project, kind, target, result_sha256, user),
    )
    if existing:
        if existing["decision"] != ("admin_approved" if admin else "reviewed"):
            raise HTTPException(
                409, "This actor already recorded a different decision for this result"
            )
        return authorization(c, project, kind, target, result_sha256)
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_report_decisions(id,project_id,target_kind,target_id,result_sha256,actor_id,assignment_id,decision,rationale,human_reviewed) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,true)",
        (
            identifier,
            project,
            kind,
            target,
            result_sha256,
            user,
            None if admin else body.assignment_id,
            "admin_approved" if admin else "reviewed",
            body.rationale,
        ),
    )
    audit(
        c,
        project,
        user,
        "benchmark.report_authorized" if admin else "benchmark.report_human_reviewed",
        target,
        {"result_sha256": result_sha256, "decision_id": identifier},
    )
    return authorization(c, project, kind, target, result_sha256)
