"""Explicit local PO attestations; never authenticated Authoring API claims."""

import hashlib
import re
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from pydantic import AwareDatetime, Field

from anvil.dataset_export_contract import Model, Sha
from anvil.db import audit, one, uid
from anvil.marketing_native_wire_bounds import bounded_json
from anvil.praxis_generic_contract import canonical, digest, load


class Upload(Model):
    record_utf8: str = Field(min_length=2, max_length=131072)


class Attestation(Model):
    subject_sha256: Sha
    rationale: str = Field(min_length=10, max_length=2000)
    expires_at: AwareDatetime


class Revocation(Model):
    reason: str = Field(min_length=10, max_length=2000)


def template(c, project, identifier):
    row = one(c, "SELECT * FROM anvil.praxis_template_versions WHERE project_id=%s AND id=%s", (project, identifier))
    if not row:
        raise HTTPException(404, "Template not found")
    if (digest(row["spec"]) != row["spec_sha256"]
            or {part: digest(row["spec"][part]) for part in ("authoring", "execution", "skills")} != row["part_hashes"]):
        raise HTTPException(409, "Registered template integrity failed")
    return row


def stage(c, project, user, identifier, upload):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    row = template(c, project, identifier)
    raw = upload.record_utf8.encode()
    if not 2 <= len(raw) <= 131072:
        raise HTTPException(413, "Publication record exceeds bound")
    try:
        record = load(raw)
        bounded_json(record, 262144, max_nodes=20000, max_depth=24)
        pending = [record]
        while pending:
            value = pending.pop()
            if type(value) is dict:
                pending.extend(value.keys())
                pending.extend(value.values())
            elif type(value) is list:
                pending.extend(value)
            elif type(value) is str and "\x00" in value:
                raise ValueError("Publication record contains a PostgreSQL-incompatible string")
        if type(record.get("published_at")) is not str or not re.search(r"(Z|[+-][0-9]{2}:[0-9]{2})$", record["published_at"]):
            raise ValueError("Aware publication date required")
        published = datetime.fromisoformat(record["published_at"].replace("Z", "+00:00"))
        statuses = [record[key] for key in ("status", "publication_status") if key in record]
        if (not statuses or any(value not in ("published", "PUBLISHED") for value in statuses) or published.tzinfo is None
                or published > one(c, "SELECT statement_timestamp() AS now")["now"]
                or record.get("template_id") != row["template_key"]
                or type(record.get("version")) is not int or record["version"] != row["version"]
                or record.get("template_sha256") != row["spec_sha256"] or record.get("part_hashes") != row["part_hashes"]):
            raise ValueError("publication")
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise HTTPException(422, "Published record, aware publication date and exact registered template identity/version/parts required") from None
    subject = {"schema_version": "anvil.offline-publication-subject.v1", "template_id": str(identifier),
               "template_sha256": row["spec_sha256"], "part_hashes": row["part_hashes"],
               "raw_record_sha256": hashlib.sha256(raw).hexdigest(), "record": record}
    fingerprint = digest(subject)
    old = one(c, "SELECT id FROM anvil.praxis_offline_publication_subjects WHERE project_id=%s AND content_sha256=%s",
              (project, fingerprint))
    subject_id = old["id"] if old else uid()
    if not old:
        c.execute("INSERT INTO anvil.praxis_offline_publication_subjects(id,project_id,template_id,created_by,raw_record_utf8,body_canonical,content_sha256) "
                  "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                  (subject_id, project, identifier, user, upload.record_utf8, canonical(subject).decode(), fingerprint))
        audit(c, project, user, "praxis.offline_publication.staged", metadata={"subject_id": str(subject_id), "sha256": fingerprint})
    return {"id": str(subject_id), "sha256": fingerprint, "origin": "po_attested_offline",
            "publication_verified": False, "publication_accepted": False, "qualification_granted": False}


def attest(c, project, user, identifier, subject_id, decision):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    template(c, project, identifier)
    subject = one(c, "SELECT * FROM anvil.praxis_offline_publication_subjects WHERE project_id=%s AND template_id=%s AND id=%s",
                  (project, identifier, subject_id))
    if not subject:
        raise HTTPException(404, "Offline publication subject not found")
    if subject["content_sha256"] != decision.subject_sha256:
        raise HTTPException(409, "Attestation must name the exact displayed subject SHA")
    now = one(c, "SELECT statement_timestamp() AS now")["now"]
    if decision.expires_at <= now:
        raise HTTPException(409, "Future attestation expiry required")
    members = c.execute("SELECT m.user_id FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id "
                        "WHERE m.project_id=%s AND m.role='admin' AND m.active AND u.active", (project,)).fetchall()
    if str(user) not in {str(member["user_id"]) for member in members}:
        raise HTTPException(403, "Current project PO required")
    self_approved = str(user) == str(subject["created_by"])
    if self_approved and len(members) != 1:
        raise HTTPException(409, "Self approval requires exactly one active project PO")
    if one(c, "SELECT 1 FROM anvil.praxis_offline_publication_revocations WHERE project_id=%s AND subject_id=%s", (project, subject_id)):
        raise HTTPException(409, "Revoked publication subject cannot be reattested")
    receipt_id = uid()
    receipt = {"schema_version": "anvil.po-offline-publication-attestation.v1", "id": str(receipt_id),
               "project_id": str(project), "template_id": str(identifier), "subject_id": str(subject_id),
               "subject_sha256": subject["content_sha256"], "attested_by": str(user), "attested_at": now.isoformat(),
               "self_approved": self_approved, "origin": "po_attested_offline", "publication_verified": False,
               **decision.model_dump(mode="json")}
    c.execute("INSERT INTO anvil.praxis_offline_publication_attestations(id,project_id,subject_id,created_by,body_canonical,content_sha256,expires_at,self_approved) "
              "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
              (receipt_id, project, subject_id, user, canonical(receipt).decode(), digest(receipt), decision.expires_at, self_approved))
    audit(c, project, user, "praxis.offline_publication.attested", metadata={"attestation_id": str(receipt_id),
          "subject_id": str(subject_id), "self_approved": self_approved, "origin": "po_attested_offline"})
    return {"attestation_id": str(receipt_id), "sha256": digest(receipt), "self_approved": self_approved,
            "origin": "po_attested_offline", "publication_verified": False, "publication_accepted": True,
            "qualification_granted": False}


def revoke(c, project, user, identifier, subject_id, reason):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    if not one(c, "SELECT 1 FROM anvil.praxis_offline_publication_subjects WHERE project_id=%s AND template_id=%s AND id=%s",
               (project, identifier, subject_id)):
        raise HTTPException(404, "Offline publication subject not found")
    c.execute("INSERT INTO anvil.praxis_offline_publication_revocations(id,project_id,subject_id,created_by,reason) "
              "VALUES(%s,%s,%s,%s,%s) ON CONFLICT(project_id,subject_id) DO NOTHING", (uid(), project, subject_id, user, reason))
    audit(c, project, user, "praxis.offline_publication.revoked", metadata={"subject_id": str(subject_id), "reason": reason})
    return {"revoked": True, "qualification_granted": False}


def basis(c, project, template_id):
    row = one(c, "SELECT a.id,a.content_sha256,a.expires_at,s.id AS subject_id,s.content_sha256 AS subject_sha256 "
              "FROM anvil.praxis_offline_publication_attestations a JOIN anvil.praxis_offline_publication_subjects s "
              "ON s.project_id=a.project_id AND s.id=a.subject_id WHERE a.project_id=%s AND s.template_id=%s "
              "AND anvil.offline_publication_current(a.project_id,s.template_id,a.id,a.content_sha256) "
              "ORDER BY a.created_at DESC,a.id DESC LIMIT 1", (project, template_id))
    return ({"kind": "po_attested_offline", "attestation_id": str(row["id"]), "attestation_sha256": row["content_sha256"],
             "subject_id": str(row["subject_id"]), "subject_sha256": row["subject_sha256"],
             "expires_at": row["expires_at"].isoformat()} if row else None)
