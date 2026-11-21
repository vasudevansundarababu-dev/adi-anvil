"""Hash-bound PO expectation review; private answers never enter API responses."""

from datetime import datetime
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException
from pydantic import AwareDatetime, Field, model_validator

from anvil.dataset_export_contract import Identifier, Model, Sha
from anvil.db import audit, digest, one, uid
from anvil.golden_kyc_data import DECISIONS
from anvil.praxis_generic_contract import canonical, load


class Expected(Model):
    intended_decision: str
    criterion_references: dict = Field(default_factory=dict)
    policy_rule_references: dict = Field(default_factory=dict)
    state_reference: dict | None = None
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def decision_supported(self):
        if self.intended_decision not in DECISIONS:
            raise ValueError("Supported expected KYC disposition required")
        from anvil.marketing_native_wire_bounds import bounded_json

        bounded_json(self.model_dump(mode="json"), 65536, max_nodes=5000, max_depth=12)
        return self


class PrivateCase(Model):
    application_id: Identifier
    snapshot_sha256: Sha
    # Public metadata hashes are salted to avoid revealing a four-way expected
    # disposition by enumerating its low-entropy unsalted hashes.
    salt: str = Field(pattern=r"^[a-f0-9]{64}$")
    expectation: Expected
    policy_subject_sha256: Sha | None = None


class Packet(Model):
    schema_version: Literal["anvil.kyc-private-expectation-packet.v1"]
    project_id: UUID
    pack_id: UUID
    cases: list[PrivateCase] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def unique_cases(self):
        if len({case.application_id for case in self.cases}) != len(self.cases):
            raise ValueError("Unique complete expectation population required")
        if len({case.salt for case in self.cases}) != len(self.cases):
            raise ValueError("Independent per-case review salts required")
        return self


class CaseRef(Model):
    application_id: Identifier
    snapshot_sha256: Sha
    expectation_sha256: Sha
    policy_subject_sha256: Sha | None = None


class Subject(Model):
    schema_version: Literal["anvil.kyc-expectation-review-subject.v1"]
    project_id: UUID
    pack_id: UUID
    private_packet_sha256: Sha
    population_sha256: Sha
    cases: list[CaseRef] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def exact_order(self):
        ids = [case.application_id for case in self.cases]
        if ids != sorted(set(ids)):
            raise ValueError("Sorted unique expectation population required")
        if self.population_sha256 != digest([
            {"id": case.application_id, "snapshot_sha256": case.snapshot_sha256} for case in self.cases
        ]):
            raise ValueError("Exact application/snapshot population hash required")
        return self


class Decision(Model):
    subject_sha256: Sha
    private_packet_sha256: Sha
    decision: Literal["approved", "rejected"]
    rationale: str = Field(min_length=10, max_length=2000)
    evidence_reference: str = Field(min_length=1, max_length=1000)
    expires_at: AwareDatetime


def reference(case):
    private = {"salt": case.salt, "expectation": case.expectation.model_dump(mode="json")}
    return CaseRef(application_id=case.application_id, snapshot_sha256=case.snapshot_sha256,
                   expectation_sha256=digest(private), policy_subject_sha256=case.policy_subject_sha256)


def subject_for(packet):
    cases = sorted((reference(case) for case in packet.cases), key=lambda case: case.application_id)
    return Subject(schema_version="anvil.kyc-expectation-review-subject.v1",
                   project_id=packet.project_id, pack_id=packet.pack_id,
                   private_packet_sha256=digest(packet.model_dump(mode="json")), cases=cases,
                   population_sha256=digest([{"id": c.application_id, "snapshot_sha256": c.snapshot_sha256} for c in cases]))


def population(c, project, pack):
    rows = c.execute("SELECT id,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id",
                     (project, pack)).fetchall()
    if not 0 < len(rows) <= 2000:
        raise ValueError("Exact bounded existing KYC population required")
    return [{"id": row["id"], "snapshot_sha256": row["snapshot_sha256"]} for row in rows]


def parse_subject(row):
    raw = row["body_canonical"].encode()
    if len(raw) > 2097152 or digest(load(raw)) != row["content_sha256"]:
        raise ValueError("Expectation subject integrity required")
    body = Subject.model_validate_json(raw)
    if body.project_id != row["project_id"] or body.pack_id != row["pack_id"]:
        raise ValueError("Expectation subject project/pack mismatch")
    return body


def stage_private(c, project, user, packet):
    """Dedicated enrolled private loader only; no approval is created."""
    if type(packet) is not Packet or packet.project_id != project:
        raise ValueError("Exact private expectation packet/project required")
    login = one(c, "SELECT current_user AS role,anvil.kyc_policy_operator_scope(%s) AS enrolled", (project,))
    if not login or login["role"] != "anvil_kyc_expectation_loader" or login["enrolled"] is not True:
        raise ValueError("Enrolled restricted private loader required")
    c.execute("SELECT anvil.lock_expectation_staging(%s)", (project,))
    c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("kyc-expectations:" + str(project) + ":" + str(packet.pack_id),))
    subject = subject_for(packet)
    expected = [{"id": item.application_id, "snapshot_sha256": item.snapshot_sha256} for item in subject.cases]
    if expected != population(c, project, packet.pack_id):
        raise ValueError("Every exact current application snapshot must have one expectation")
    value = subject.model_dump(mode="json")
    sha = digest(value)
    identifier = uuid5(NAMESPACE_URL, str(project) + ":expectations:" + sha)
    old = one(c, "SELECT * FROM anvil.kyc_expectation_subjects WHERE project_id=%s AND id=%s", (project, identifier))
    if old:
        if parse_subject(old) != subject:
            raise ValueError("Immutable expectation subject changed")
        private = c.execute("SELECT application_id,content_sha256 FROM banking_private.expectation_versions WHERE project_id=%s AND subject_id=%s", (project, identifier)).fetchall()
        if {r["application_id"]: r["content_sha256"] for r in private} != {r.application_id: r.expectation_sha256 for r in subject.cases}:
            raise ValueError("Complete immutable private expectation population required")
        stored_packet = one(c, "SELECT content_sha256 FROM banking_private.expectation_packets WHERE project_id=%s AND subject_id=%s", (project, identifier))
        if not stored_packet or stored_packet["content_sha256"] != subject.private_packet_sha256:
            raise ValueError("Exact immutable reviewed packet custody required")
    else:
        c.execute("INSERT INTO anvil.kyc_expectation_subjects(id,project_id,pack_id,created_by,body_canonical,content_sha256) VALUES(%s,%s,%s,%s,%s,%s)",
                  (identifier, project, packet.pack_id, user, canonical(value).decode(), sha))
        raw_packet = canonical(packet.model_dump(mode="json"))
        c.execute("INSERT INTO banking_private.expectation_packets(project_id,subject_id,body_canonical,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s)",
                  (project, identifier, raw_packet.decode(), subject.private_packet_sha256, user))
        for case in packet.cases:
            body = {"salt": case.salt, "expectation": case.expectation.model_dump(mode="json")}
            c.execute("INSERT INTO banking_private.expectation_versions(project_id,subject_id,pack_id,application_id,snapshot_sha256,body_canonical,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                      (project, identifier, packet.pack_id, case.application_id, case.snapshot_sha256,
                       canonical(body).decode(), digest(body), user))
    return {"id": str(identifier), "sha256": sha, "case_count": len(subject.cases),
            "private_packet_sha256": subject.private_packet_sha256, "review": "pending", "run_authority": "not_granted"}


def decide(c, project, user, subject_id, decision):
    if type(decision) is not Decision:
        raise ValueError("Explicit owner decision required")
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("kyc-expectation-review:" + str(project),))
    row = one(c, "SELECT * FROM anvil.kyc_expectation_subjects WHERE project_id=%s AND id=%s", (project, subject_id))
    if not row:
        raise HTTPException(404, "Expectation subject not found")
    subject = parse_subject(row)
    if decision.subject_sha256 != row["content_sha256"] or decision.private_packet_sha256 != subject.private_packet_sha256:
        raise HTTPException(409, "Review must name the exact subject and privately reviewed packet hashes")
    if digest(population(c, project, subject.pack_id)) != subject.population_sha256:
        raise HTTPException(409, "Expectation population changed")
    people = c.execute("SELECT m.user_id FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.active AND m.role='admin' AND u.active", (project,)).fetchall()
    if str(user) not in {str(p["user_id"]) for p in people}:
        raise HTTPException(403, "Current project owner required")
    self_approved = str(row["created_by"]) == str(user)
    if self_approved and len(people) != 1:
        raise HTTPException(409, "Self approval requires exactly one active project owner")
    now = one(c, "SELECT statement_timestamp() AS now")["now"]
    if decision.expires_at <= now:
        raise HTTPException(409, "Future review expiry required")
    identifier = uid()
    body = {"schema_version": "anvil.kyc-expectation-review-receipt.v1", "id": identifier,
            "project_id": str(project), "subject_id": str(subject_id), "reviewer_id": str(user),
            "reviewed_at": now.isoformat(), "self_approved": self_approved,
            **decision.model_dump(mode="json")}
    c.execute("INSERT INTO anvil.kyc_expectation_review_receipts(id,project_id,subject_id,created_by,expires_at,body_canonical,content_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s)",
              (identifier, project, subject_id, user, decision.expires_at, canonical(body).decode(), digest(body)))
    audit(c, project, user, "kyc.expectation_review.decided", identifier,
          {"subject_sha256": row["content_sha256"], "decision": decision.decision, "self_approved": self_approved})
    return {"id": identifier, "sha256": digest(body), "decision": decision.decision,
            "case_count": len(subject.cases), "self_approved": self_approved, "run_authority": "not_granted"}


def current(c, project, pack):
    """Public metadata only. New unreviewed subjects never fall back to old approval."""
    row = one(c, "SELECT * FROM anvil.kyc_expectation_subjects WHERE project_id=%s AND pack_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (project, pack))
    if not row:
        return {"ready": False, "code": "AV_KYC_EXPECTATION_POPULATION_REVIEW_REQUIRED"}
    subject = parse_subject(row)
    if subject.population_sha256 != digest(population(c, project, pack)):
        return {"ready": False, "code": "AV_KYC_EXPECTATION_POPULATION_CHANGED"}
    receipt = one(c, "SELECT r.*,EXISTS(SELECT 1 FROM anvil.kyc_expectation_review_revocations v WHERE v.project_id=r.project_id AND v.receipt_id=r.id) AS revoked,anvil.benchmark_is_admin(r.project_id,r.created_by) AS reviewer_active,statement_timestamp() AS checked_at FROM anvil.kyc_expectation_review_receipts r WHERE r.project_id=%s AND r.subject_id=%s ORDER BY r.created_at DESC,r.id DESC LIMIT 1", (project, row["id"]))
    if not receipt:
        return {"ready": False, "code": "AV_KYC_EXPECTATION_POPULATION_REVIEW_REQUIRED"}
    body = load(receipt["body_canonical"].encode())
    if (digest(body) != receipt["content_sha256"] or body.get("schema_version") != "anvil.kyc-expectation-review-receipt.v1"
            or body.get("subject_sha256") != row["content_sha256"]
            or body.get("private_packet_sha256") != subject.private_packet_sha256
            or body.get("project_id") != str(project) or body.get("subject_id") != str(row["id"])
            or body.get("id") != str(receipt["id"])
            or body.get("reviewer_id") != str(receipt["created_by"])
            or body.get("decision") != "approved" or receipt["revoked"] or not receipt["reviewer_active"]
            or datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00")) != receipt["expires_at"]
            or receipt["expires_at"] <= receipt["checked_at"]):
        return {"ready": False, "code": "AV_KYC_EXPECTATION_REVIEW_INVALID_EXPIRED_OR_REVOKED"}
    return {"ready": True, "subject_id": str(row["id"]), "subject_sha256": row["content_sha256"],
            "receipt_id": str(receipt["id"]), "receipt_sha256": receipt["content_sha256"],
            "population_sha256": subject.population_sha256, "private_packet_sha256": subject.private_packet_sha256,
            "case_count": len(subject.cases)}


def legal_current(c, project, policy_sha256, snapshot, resolved_task_id, *, trial_id=None, generation=None):
    """A case review never substitutes for the exact current domain decision."""
    if not policy_sha256 or not resolved_task_id:
        return False
    row = one(c, "SELECT * FROM anvil.kyc_policy_review_subjects WHERE project_id=%s AND content_sha256=%s",
              (project, policy_sha256))
    resolved = one(c, "SELECT task_key,revision,binding FROM anvil.praxis_resolved_tasks WHERE project_id=%s AND id=%s",
                   (project, resolved_task_id))
    if not row or not resolved:
        return False
    from datetime import date

    from anvil.golden_kyc_policy_registry import ReceiptReference
    from anvil.kyc_policy_reviews import DomainSubject, resolve

    subject = DomainSubject.model_validate_json(row["body_canonical"].encode())
    policy = subject.policy_set
    if (digest(subject.model_dump(mode="json")) != policy_sha256
            or subject.task_id != resolved["task_key"] or subject.revision_id != resolved["revision"]
            or subject.template.sha256 != resolved["binding"].get("template_sha256")
            or policy.product != snapshot["product"] or policy.governing_state != snapshot["governing_state"]
            or policy.charter_profile != snapshot.get("charter_applicability", {}).get("profile")
            or not policy.effective_from <= date.fromisoformat(snapshot["assessment_date"]) < policy.effective_until):
        return False
    receipt = one(c, "SELECT id,content_sha256,expires_at FROM anvil.kyc_policy_review_receipts WHERE project_id=%s AND subject_id=%s AND kind='domain' ORDER BY created_at DESC,id DESC LIMIT 1",
                  (project, row["id"]))
    if not receipt:
        return False
    try:
        resolve(c, project, ReceiptReference(id=receipt["id"], sha256=receipt["content_sha256"]),
                subject, expires_at=receipt["expires_at"])
    except ValueError:
        return False
    return materialization_current(c, project, subject, snapshot, trial_id, generation)


def materialization_current(c, project, subject, snapshot, trial_id, generation):
    if trial_id is None or type(generation) is not int or generation < 0:
        return False
    import os
    from datetime import date

    from anvil.golden_kyc_policy_delivery import load as delivery_load
    from anvil.golden_kyc_policy_registry import ProductRegistryScope
    from anvil.golden_kyc_policy_registry import load as registry_load
    from anvil.golden_kyc_source import source_hash
    from anvil.praxis_case_dataset import PolicyRef

    project = UUID(str(project))
    row = one(c, "SELECT banking.product_policy_grader_binding(%s,%s) AS value", (trial_id, generation))
    value = (row or {}).get("value")
    if not value:
        return False
    scope = ProductRegistryScope.model_validate_json(canonical(value["policy_scope"]))
    if (scope.project_id != project or scope.task_id != subject.task_id or scope.revision_id != subject.revision_id
            or scope.template != subject.template or scope.runtime_source_sha256 != source_hash()
            or scope.runtime_image_sha256 != os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST")
            or value["snapshot_sha256"] != digest(snapshot) or value["snapshot"] != snapshot):
        return False
    registry = registry_load(c, scope, product=snapshot["product"], governing_state=snapshot["governing_state"],
                             charter_profile=snapshot["charter_applicability"]["profile"],
                             assessment_date=date.fromisoformat(snapshot["assessment_date"]),
                             federal_refs=tuple(PolicyRef.model_validate(ref) for ref in value["federal_refs"]),
                             policy_set_constraint=digest(subject.policy_set.model_dump(mode="json")))
    if registry.requirement or len(registry.qualification_record_ids) != 1:
        return False
    delivery = delivery_load(c, scope, snapshot["id"], registry.qualification_record_ids[0])
    return not delivery.requirement and bool(delivery.public)


def policy_references(values, subject_sha256, legal):
    return {
        target: ({**value, "review_status": "approved"}
                 if legal and type(value) is dict and value.get("policy_subject_sha256") == subject_sha256
                 else {"review_status": "pending"})
        for target, value in values.items()
    }


def reviewed(c, project, pack, application, snapshot, *, resolved_task_id=None, frozen_reference=None, trial_id=None, generation=None):
    """Private grader consumer; approved strings inside a file confer no review."""
    result = current(c, project, pack)
    if not result["ready"]:
        return {"independent_expectation_review": "pending", "review_issue": result["code"]}
    if frozen_reference != public_reference(result):
        return {"independent_expectation_review": "pending", "review_issue": "AV_KYC_FROZEN_EXPECTATION_REVIEW_CHANGED"}
    row = one(c, "SELECT * FROM banking_private.expectation_versions WHERE project_id=%s AND subject_id=%s AND pack_id=%s AND application_id=%s", (project, result["subject_id"], pack, application))
    subject_row = one(c, "SELECT * FROM anvil.kyc_expectation_subjects WHERE project_id=%s AND id=%s", (project, result["subject_id"]))
    subject = parse_subject(subject_row)
    refs = [case for case in subject.cases if case.application_id == application]
    snapshot_sha256 = digest(snapshot)
    if not row or len(refs) != 1 or row["snapshot_sha256"] != snapshot_sha256 or refs[0].snapshot_sha256 != snapshot_sha256:
        raise ValueError("Exact reviewed private application expectation required")
    private = load(row["body_canonical"].encode())
    if digest(private) != row["content_sha256"] or row["content_sha256"] != refs[0].expectation_sha256:
        raise ValueError("Reviewed private expectation integrity required")
    expected = Expected.model_validate(private["expectation"]).model_dump(mode="json", exclude_none=True)
    legal = legal_current(c, project, refs[0].policy_subject_sha256, snapshot, resolved_task_id,
                          trial_id=trial_id, generation=generation)
    expected["policy_rule_references"] = policy_references(
        expected.get("policy_rule_references", {}), refs[0].policy_subject_sha256, legal
    )
    return expected | {"independent_expectation_review": "approved", "legal_qualification": "approved" if legal else "pending",
                       "expectation_review": result}


def revoke(c, project, user, receipt_id, reason):
    if not 10 <= len(reason) <= 2000:
        raise ValueError("Bounded revocation reason required")
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    if not one(c, "SELECT id FROM anvil.kyc_expectation_review_receipts WHERE project_id=%s AND id=%s", (project, receipt_id)):
        raise HTTPException(404, "Expectation review not found")
    c.execute("INSERT INTO anvil.kyc_expectation_review_revocations(id,project_id,receipt_id,created_by,reason) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(project_id,receipt_id) DO NOTHING",
              (uid(), project, receipt_id, user, reason))
    audit(c, project, user, "kyc.expectation_review.revoked", receipt_id, {"reason": reason})
    return {"revoked": True, "run_authority": "not_granted"}


def binding_pack(c, project, snapshot):
    if snapshot.get("execution_data"):
        from anvil.project_inputs import execution_overlay

        overlay = execution_overlay(c, project, snapshot["execution_data"])
        if overlay["family"] == "kyc":
            return overlay["pack_id"]
    packs = set()
    for ref in snapshot.get("workflow", []):
        if ref["kind"] != "package":
            continue
        row = one(c, "SELECT manifest,package_sha256 FROM anvil.harbor_packages WHERE project_id=%s AND id=%s",
                  (project, ref["id"]))
        if row and row["package_sha256"] == ref["sha256"]:
            native = row["manifest"].get("native_binding", {})
            if native.get("task_mode") == "reusable_application_workflow":
                packs.add(native["pack_id"])
    if len(packs) > 1:
        raise ValueError("One exact shared KYC expectation population required")
    return next(iter(packs), None)


def public_reference(review):
    return {key: review[key] for key in ("subject_id", "subject_sha256", "receipt_id", "receipt_sha256",
                                         "population_sha256", "private_packet_sha256", "case_count")}


def freeze(c, project, snapshot):
    # B0 must establish its input before packages. Never infer a new review
    # selection only after package creation and silently change B0 ancestry.
    if not snapshot.get("execution_data"):
        return {}
    pack = binding_pack(c, project, snapshot)
    if not pack:
        return {}
    review = current(c, project, pack)
    return {"kyc_expectation_review": public_reference(review)} if review["ready"] else {}


def binding_gaps(c, project, snapshot):
    pack = binding_pack(c, project, snapshot)
    if not pack:
        return []
    review = current(c, project, pack)
    if not review["ready"]:
        return [{"section": "data", "code": review["code"], "owner": "project_owner"}]
    if snapshot.get("kyc_expectation_review") != public_reference(review):
        return [{"section": "data", "code": "AV_KYC_EXPECTATION_REVIEW_FROZEN_BINDING_REQUIRED", "owner": "anvil"}]
    return []


def require_plan(c, project, plan):
    config = plan["config"]
    group = one(c, "SELECT id,created_by,snapshot,subject_hash FROM anvil.workspace_execution_groups WHERE project_id=%s AND id=%s",
                (project, config["workspace_execution_group"]))
    if not group or digest({"id": str(group["id"]), "created_by": str(group["created_by"]),
                            "snapshot": group["snapshot"]}) != str(group["subject_hash"]).strip():
        raise ValueError("Exact frozen execution group required before KYC dispatch")
    ref = group["snapshot"].get("preparation", {}).get("project_binding")
    if not ref:
        raise ValueError("Reviewed expectation selection must be frozen before KYC dispatch")
    binding = one(c, "SELECT snapshot,snapshot_sha256 FROM anvil.project_binding_versions WHERE project_id=%s AND id=%s AND task_group_id=%s",
                  (project, ref["id"], ref["task_group_id"]))
    if (not binding or digest(binding["snapshot"]) != binding["snapshot_sha256"]
            or binding["snapshot_sha256"] != ref["snapshot_sha256"]):
        raise ValueError("Frozen expectation selection changed")
    pack = binding_pack(c, project, binding["snapshot"])
    if not pack or str(pack) != str(config["golden_native_binding"]["pack_id"]) or binding_gaps(c, project, binding["snapshot"]):
        raise ValueError("Current complete owner-reviewed KYC expectations required before spending")
