"""Immutable PO policy decisions; uploaded records never approve themselves."""

from typing import Literal

from fastapi import HTTPException
from pydantic import AwareDatetime, Field

from anvil.dataset_export_contract import Identifier, Model, Sha
from anvil.db import audit, one, uid
from anvil.golden_kyc_policy_registry import PolicySet, StateNotApplicablePolicySet
from anvil.praxis_generic_contract import TemplateRef, canonical, digest


class DomainSubject(Model):
    schema_version: Literal["anvil.kyc-policy-domain-subject.v1"]
    template: TemplateRef
    task_id: Identifier
    revision_id: Identifier
    policy_set: PolicySet | StateNotApplicablePolicySet


class RuntimeSubject(Model):
    schema_version: Literal["anvil.kyc-policy-runtime-subject.v1"]
    runtime_source_sha256: Sha
    runtime_image_sha256: Sha
    environment_binding_sha256: Sha
    evaluator_bindings_sha256: Sha


class Decision(Model):
    subject_sha256: Sha
    decision: Literal["approved", "rejected"]
    rationale: str = Field(min_length=10, max_length=2000)
    evidence_reference: str = Field(min_length=1, max_length=1000)
    evidence_sha256: Sha
    expires_at: AwareDatetime


def fence(c, project):
    c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
              ("anvil.kyc.policy.review:" + str(project),))


def domain_subject(scope, policy_set):
    return DomainSubject(schema_version="anvil.kyc-policy-domain-subject.v1",
                         template=scope.template, task_id=scope.task_id,
                         revision_id=scope.revision_id, policy_set=policy_set)


def runtime_subject(scope):
    return RuntimeSubject(schema_version="anvil.kyc-policy-runtime-subject.v1", **{
        name: getattr(scope, name) for name in RuntimeSubject.model_fields if name != "schema_version"
    })


def stage(c, project, user, subject):
    if type(subject) is not DomainSubject:
        raise ValueError("Typed public policy subject required")
    raw = canonical(subject.model_dump(mode="json"))
    if len(raw) > 131072:
        raise HTTPException(413, "Policy subject exceeds bound")
    fence(c, project)
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    from anvil.praxis_template_registry import lookup

    current = lookup(c, project, subject.template)
    if not current or not current.get("integrity"):
        raise HTTPException(409, "Exact registered template required before policy review")
    row = one(c, "SELECT * FROM anvil.kyc_policy_review_subjects WHERE project_id=%s AND content_sha256=%s",
              (project, digest(subject.model_dump(mode="json"))))
    if row:
        return {"id": row["id"], "sha256": row["content_sha256"], "status": "staged_not_approved"}
    identifier, fingerprint = uid(), digest(subject.model_dump(mode="json"))
    c.execute("INSERT INTO anvil.kyc_policy_review_subjects(id,project_id,created_by,body_canonical,content_sha256) "
              "VALUES(%s,%s,%s,%s,%s)", (identifier, project, user, raw.decode(), fingerprint))
    audit(c, project, user, "kyc.policy_review.stage", metadata={"id": str(identifier), "sha256": fingerprint})
    return {"id": identifier, "sha256": fingerprint, "status": "staged_not_approved"}


def decide(c, project, user, subject_id, decision):
    if type(decision) is not Decision:
        raise ValueError("Explicit PO decision required")
    fence(c, project)
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    subject = one(c, "SELECT * FROM anvil.kyc_policy_review_subjects WHERE project_id=%s AND id=%s",
                  (project, subject_id))
    if not subject:
        raise HTTPException(404, "Policy subject not found")
    parsed = DomainSubject.model_validate_json(subject["body_canonical"])
    if digest(parsed.model_dump(mode="json")) != subject["content_sha256"]:
        raise HTTPException(409, "Policy subject integrity failed")
    if decision.subject_sha256 != subject["content_sha256"]:
        raise HTTPException(409, "Decision must name the exact displayed policy subject hash")
    people = c.execute("SELECT m.user_id FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id "
                       "WHERE m.project_id=%s AND m.role='admin' AND m.active AND u.active", (project,)).fetchall()
    if str(user) not in {str(row["user_id"]) for row in people}:
        raise HTTPException(403, "Current project PO required")
    self_approved = str(subject["created_by"]) == str(user)
    if self_approved and len(people) != 1:
        raise HTTPException(409, "Self approval requires exactly one active project PO")
    now = one(c, "SELECT statement_timestamp() AS now", ())["now"]
    if not now < decision.expires_at:
        raise HTTPException(409, "Review expiry must be in the future")
    identifier = uid()
    body = {"schema_version": "anvil.kyc-policy-review-receipt.v1", "id": str(identifier),
            "project_id": str(project), "kind": "domain", "subject_id": str(subject_id),
            "subject_sha256": subject["content_sha256"], "subject": parsed.model_dump(mode="json"),
            "reviewer_id": str(user), "reviewed_at": now.isoformat(),
            "self_approved": self_approved, **decision.model_dump(mode="json")}
    c.execute("INSERT INTO anvil.kyc_policy_review_receipts(id,project_id,subject_id,kind,created_by,"
              "body_canonical,content_sha256,expires_at) VALUES(%s,%s,%s,'domain',%s,%s,%s,%s)",
              (identifier, project, subject_id, user, canonical(body).decode(), digest(body), decision.expires_at))
    audit(c, project, user, "kyc.policy_review.decide", metadata={"id": str(identifier),
          "subject_id": str(subject_id), "decision": decision.decision, "self_approved": self_approved})
    return {"id": identifier, "sha256": digest(body), "decision": decision.decision,
            "self_approved": self_approved, "qualification_granted": False}


def resolve(c, project, reference, expected, *, expires_at):
    fence(c, project)
    row = one(c, "SELECT r.*,statement_timestamp() AS checked_at FROM anvil.kyc_policy_review_receipts r "
              "WHERE r.project_id=%s AND r.id=%s AND r.content_sha256=%s "
              "AND NOT EXISTS(SELECT 1 FROM anvil.kyc_policy_review_revocations v "
              "WHERE v.project_id=r.project_id AND v.receipt_id=r.id) "
              "AND anvil.benchmark_is_admin(r.project_id,r.created_by)",
              (project, reference.id, reference.sha256))
    if not row:
        raise ValueError("Authenticated unrevoked review required")
    from anvil.praxis_generic_contract import load

    body = load(row["body_canonical"].encode())
    if (digest(body) != reference.sha256 or body.get("subject") != expected.model_dump(mode="json")
            or body.get("decision") != "approved" or body.get("reviewer_id") != str(row["created_by"])
            or body.get("project_id") != str(project) or body.get("id") != str(reference.id)
            or not row["checked_at"] < expires_at <= row["expires_at"]):
        raise ValueError("Exact current approved review subject required")
    return body


def revoke(c, project, user, receipt_id, reason):
    if not 10 <= len(reason) <= 2000:
        raise ValueError("Bounded revocation reason required")
    fence(c, project)
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    receipt = one(c, "SELECT id FROM anvil.kyc_policy_review_receipts WHERE project_id=%s AND id=%s",
                  (project, receipt_id))
    if not receipt:
        raise HTTPException(404, "Review not found")
    c.execute("INSERT INTO anvil.kyc_policy_review_revocations(id,project_id,receipt_id,created_by,reason) "
              "VALUES(%s,%s,%s,%s,%s) ON CONFLICT(project_id,receipt_id) DO NOTHING",
              (uid(), project, receipt_id, user, reason))
    audit(c, project, user, "kyc.policy_review.revoke", metadata={"receipt_id": str(receipt_id), "reason": reason})
    return {"revoked": True, "qualification_granted": False}
