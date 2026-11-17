"""Privileged QA cutover protocol. APIs request work; they never execute it.

All physical actions belong to the existing host operator. Local deterministic
receipts remain isolated controls and never become serving observations.
"""

import os
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import AwareDatetime, Field, ValidationError, model_validator

from anvil.db import Jsonb, audit, digest, one, uid
from anvil.runtime_admin import (
    IMAGE,
    SHA,
    Adapter,
    Observation,
    check_role,
    compatible,
    latest_observation,
    require_operator,
    update_pin,
)
from anvil.schemas import Strict

Hash = Annotated[str, Field(pattern=SHA)]
Commit = Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
Image = Annotated[str, Field(pattern=IMAGE, max_length=300)]
STOP = datetime(2026, 12, 11, 5, 48, 4, tzinfo=timezone.utc)
CHECKS = {
    "image_source_locks",
    "role_isolation",
    "native_mcp_reset_checkpoint",
    "scoring_safety_report",
    "code_schema_rollback_compatibility",
    "private_mounts_metadata",
    "no_model_calls",
}


class QARequest(Strict):
    candidate_id: UUID
    expected_observation_id: UUID
    admission_id: UUID
    action: Literal["activate", "rollback"] = "activate"
    client_operation_id: UUID | None = None


class Admission(Strict):
    origin: Literal["independent_qa"]
    deployment_id: Literal["anvil-qa-v1"]
    host_id: Literal["8748412716380175314"]
    role: str
    service: Literal[
        "api", "business-worker", "golden-grader", "golden-scheduler", "golden-native-coordinator"
    ]
    action: Literal["activate", "rollback"]
    rollback_of_job_id: UUID | None = None
    source_commit: Commit
    image_digest: Image
    lock_digest: Hash
    archive_sha256: Hash
    recipe_sha256: Hash
    operator_spec_sha256: Hash
    independent_review_sha256: Hash
    qualification_sha256: Hash
    checks: dict[str, Hash]
    baseline_observation_id: UUID
    baseline_image_digest: Image
    baseline_source_commit: Commit
    baseline_lock_digest: Hash
    baseline_interpreter: str = Field(pattern=r"^/[A-Za-z0-9_./-]+$", max_length=240)
    baseline_adapters: list[Adapter] = Field(default_factory=list, max_length=40)
    database_schema: str = Field(pattern=r"^[0-9]{3}$")
    storage_identity_sha256: Hash
    rollback_compatibility_sha256: Hash
    affected_projects: list[UUID] = Field(min_length=1, max_length=1000)
    deployment_projects_sha256: Hash
    interpreter: str = Field(pattern=r"^/[A-Za-z0-9_./-]+$", max_length=240)
    installed_adapters: list[Adapter] = Field(default_factory=list, max_length=40)
    ledger_generation: str = Field(pattern=r"^[0-9]+$")
    expires_at: AwareDatetime
    stop_at: AwareDatetime
    build_limit: Literal[31]
    infrastructure_usd_month: Literal[550]
    qa_pilot_usd: Literal[100]
    qa_aggregate_run_usd: Literal[2]
    model_calls: Literal[0]
    schema_changes: Literal[False]
    new_services: Literal[False]

    @model_validator(mode="after")
    def exact_contract(self):
        check_role(self.role)
        if self.role != self.service or set(self.checks) != CHECKS or self.stop_at != STOP:
            raise ValueError("Exact role checks and original pilot stop required")
        if len(set(self.affected_projects)) != len(self.affected_projects):
            raise ValueError("Duplicate affected project")
        if (
            digest(sorted(str(p) for p in self.affected_projects))
            != self.deployment_projects_sha256
        ):
            raise ValueError("Affected deployment project mapping hash mismatch")
        if (self.action == "rollback") != (self.rollback_of_job_id is not None):
            raise ValueError("Rollback must reference its prior cutover")
        return self


class Reservation(Strict):
    job_id: UUID
    admission_id: UUID
    admission_sha256: Hash
    token_sha256: Hash
    generation: str = Field(pattern=r"^[0-9]+$")
    admitted_generation: str = Field(pattern=r"^[0-9]+$")
    attempts: int = Field(ge=0, le=31, strict=True)
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    purpose: Literal["runtime_update_no_build"]


class HostReceipt(Strict):
    job_id: UUID
    role: str
    action: Literal["activate", "rollback"]
    recovery_of_job_id: UUID | None = None
    phase: Literal[
        "installed", "qualified", "activated", "rolled_back", "outcome_unknown", "failed"
    ]
    provenance: Literal["observed_qa", "deterministic_fixture"]
    deployment_id: Literal["anvil-qa-v1"]
    host_id: Literal["8748412716380175314"]
    image_digest: Image
    source_commit: Commit
    lock_digest: Hash
    operator_spec_sha256: Hash
    qualification_sha256: Hash
    checks_sha256: Hash
    deployment_projects_sha256: Hash
    database_schema: str = Field(pattern=r"^[0-9]{3}$")
    storage_identity_sha256: Hash
    physical_receipt_sha256: Hash
    preservation_receipt_sha256: Hash
    rollback_compatibility_sha256: Hash
    running: bool
    serving_image_digest: Image | None = None
    pending_or_unknown_work: int = Field(ge=0, strict=True)
    model_calls: Literal[0]
    database_restored: Literal[False]
    schema_changed: Literal[False]
    post_cutover_writes: bool
    observed_at: AwareDatetime


def enabled():
    return os.environ.get("ANVIL_RUNTIME_QA_UPDATES_ENABLED", "false") == "true"


def load_admission(c, project, identifier):
    row = one(
        c,
        "SELECT a.*,EXISTS(SELECT 1 FROM anvil.runtime_qa_admission_revocations r WHERE r.admission_id=a.id) AS revoked FROM anvil.runtime_qa_admissions a WHERE a.project_id=%s AND a.id=%s",
        (project, identifier),
    )
    if not row or row["revoked"] or digest(row["envelope"]) != row["envelope_sha256"]:
        raise HTTPException(409, "QA admission is missing, changed or revoked")
    try:
        admission = Admission.model_validate(row["envelope"])
    except ValidationError:
        raise HTTPException(409, "QA admission contract is invalid") from None
    now = datetime.now(timezone.utc)
    if min(row["expires_at"], admission.expires_at, admission.stop_at) <= now:
        raise HTTPException(409, "QA admission or pilot expired")
    pin = update_pin(c, project, row["candidate_id"])
    if (
        row["role"] != admission.role
        or any(
            pin[k] != getattr(admission, k)
            for k in ("role", "image_digest", "source_commit", "lock_digest")
        )
        or pin["compatibility"].get("operator_spec_sha256") != admission.operator_spec_sha256
    ):
        raise HTTPException(409, "QA admission differs from immutable candidate pin")
    if str(project) not in {str(p) for p in admission.affected_projects} or str(
        row["expected_observation_id"]
    ) != str(admission.baseline_observation_id):
        raise HTTPException(409, "QA admission project or baseline mismatch")
    if admission.action == "rollback":
        prior = one(
            c,
            "SELECT request,state,role FROM anvil.runtime_update_jobs WHERE project_id=%s AND id=%s",
            (project, admission.rollback_of_job_id),
        )
        if not prior or prior["role"] != admission.role or prior["state"] != "activated":
            raise HTTPException(409, "Rollback must reference this project's completed cutover")
        original = one(
            c,
            "SELECT envelope FROM anvil.runtime_qa_admissions WHERE project_id=%s AND id=%s",
            (project, prior["request"]["admission_id"]),
        )
        if not original or any(
            getattr(admission, k) != original["envelope"]["baseline_" + k]
            for k in ("image_digest", "source_commit", "lock_digest")
        ):
            raise HTTPException(409, "Rollback target differs from preserved prior runtime")
    return row, admission


def validate_baseline(c, project, admission):
    observed = latest_observation(c, project, admission.role)
    if not observed or str(observed["id"]) != str(admission.baseline_observation_id):
        raise HTTPException(409, "QA serving baseline changed")
    if digest(observed["evidence"]) != observed["evidence_sha256"]:
        raise HTTPException(409, "QA serving baseline hash mismatch")
    baseline = Observation.model_validate(observed["evidence"])
    if (baseline.image_digest, baseline.source_commit, baseline.lock_digest) != (
        admission.baseline_image_digest,
        admission.baseline_source_commit,
        admission.baseline_lock_digest,
    ):
        raise HTTPException(409, "QA serving baseline tuple changed")


def queue(c, project, user, role, body):
    if not enabled():
        raise HTTPException(
            409,
            "QA Update is unavailable until its operator adapter and release admission are qualified",
        )
    if body.client_operation_id:
        prior = one(
            c,
            "SELECT id,state,request FROM anvil.runtime_update_jobs WHERE project_id=%s AND role=%s AND scope='qa' AND request->>'client_operation_id'=%s",
            (project, role, str(body.client_operation_id)),
        )
        if prior:
            if any(
                str(prior["request"].get(k)) != str(getattr(body, k))
                for k in ("candidate_id", "expected_observation_id", "admission_id", "action")
            ):
                raise HTTPException(
                    409, "Client operation identifier reused with a different immutable request"
                )
            return {
                "job_id": prior["id"],
                "state": prior["state"],
                "scope": "qa",
                "action": prior["request"]["action"],
                "client_operation_id": str(body.client_operation_id),
                "existing_operation": True,
                "automatic_retry": False,
                "paid_dispatch_authorized": False,
            }
    failed = one(
        c,
        "SELECT id FROM anvil.runtime_update_jobs WHERE project_id=%s AND role=%s AND scope='qa' AND request->>'admission_id'=%s AND (state='failed' OR (state='rolled_back' AND request->>'action'='activate')) ORDER BY created_at DESC,id DESC LIMIT 1",
        (project, role, str(body.admission_id)),
    )
    if failed:
        raise HTTPException(
            409,
            {"code": "qa_admission_failed_new_review_required", "failed_job_id": str(failed["id"])},
        )
    row, admission = load_admission(c, project, body.admission_id)
    if (
        role != admission.role
        or str(row["candidate_id"]) != str(body.candidate_id)
        or str(body.expected_observation_id) != str(admission.baseline_observation_id)
        or body.action != admission.action
    ):
        raise HTTPException(409, "QA request does not match its admission")
    validate_baseline(c, project, admission)
    pin = update_pin(c, project, body.candidate_id)
    if not compatible(pin, latest_observation(c, project, role), "qa"):
        raise HTTPException(409, "QA candidate compatibility is unavailable")
    if one(
        c,
        "SELECT id FROM anvil.runtime_update_jobs WHERE project_id=%s AND role=%s AND state IN('queued','claimed','installed','outcome_unknown')",
        (project, role),
    ):
        raise HTTPException(409, "Existing runtime operation requires reconciliation")
    identifier = uid()
    request = {
        "role": role,
        "scope": "qa",
        "candidate_id": str(body.candidate_id),
        "expected_observation_id": str(body.expected_observation_id),
        "admission_id": str(body.admission_id),
        "admission_sha256": row["envelope_sha256"],
        "action": body.action,
        "client_operation_id": str(body.client_operation_id) if body.client_operation_id else None,
        **{
            k: getattr(admission, k)
            for k in ("image_digest", "source_commit", "lock_digest", "operator_spec_sha256")
        },
    }
    c.execute(
        "INSERT INTO anvil.runtime_update_jobs(id,project_id,role,candidate_id,expected_observation_id,scope,request,request_sha256,created_by) VALUES(%s,%s,%s,%s,%s,'qa',%s,%s,%s)",
        (
            identifier,
            project,
            role,
            body.candidate_id,
            body.expected_observation_id,
            Jsonb(request),
            digest(request),
            user,
        ),
    )
    audit(
        c,
        project,
        user,
        "runtime.qa_update_requested",
        identifier,
        {"admission_id": str(body.admission_id), "action": body.action, "serving_changed": False},
    )
    return {
        "job_id": identifier,
        "state": "queued",
        "scope": "qa",
        "action": body.action,
        "client_operation_id": str(body.client_operation_id) if body.client_operation_id else None,
        "serving_changed": False,
        "paid_dispatch_authorized": False,
        "blockers": ["fresh_operator_ledger_CAS_and_readback_required"],
    }


def verify_reservation(job, row, reservation):
    value = Reservation.model_validate(reservation)
    now = datetime.now(timezone.utc)
    if (
        str(value.job_id) != str(job["id"])
        or str(value.admission_id) != str(row["id"])
        or value.admission_sha256 != row["envelope_sha256"]
        or not value.observed_at <= now < value.expires_at
        or (now - value.observed_at).total_seconds() > 30
    ):
        raise HTTPException(409, "Fresh owned ledger CAS reservation required")
    return value


def authority(c, project, identifier, reservation, *, claim_token=None, baseline=True):
    require_operator(c)
    if not enabled():
        raise HTTPException(409, "Qualified QA operator is not enabled")
    job = one(
        c,
        "SELECT * FROM anvil.runtime_update_jobs WHERE project_id=%s AND id=%s FOR UPDATE",
        (project, identifier),
    )
    if not job or job["scope"] != "qa" or digest(job["request"]) != job["request_sha256"]:
        raise HTTPException(409, "Invalid QA job custody")
    if claim_token is not None and str(job["claim_token"]) != str(claim_token):
        raise HTTPException(409, "Wrong QA operator claim")
    row, admission = load_admission(c, project, job["request"]["admission_id"])
    if row["envelope_sha256"] != job["request"]["admission_sha256"]:
        raise HTTPException(409, "QA admission changed")
    verified = verify_reservation(job, row, reservation)
    if verified.admitted_generation != admission.ledger_generation or verified.expires_at > min(
        admission.expires_at, admission.stop_at
    ):
        raise HTTPException(409, "Ledger reservation differs from approved admission/window")
    original = one(
        c,
        "SELECT reservation FROM anvil.runtime_qa_job_admissions WHERE project_id=%s AND job_id=%s",
        (project, identifier),
    )
    if original and (
        original["reservation"]["token_sha256"] != verified.token_sha256
        or original["reservation"]["attempts"] != verified.attempts
    ):
        raise HTTPException(409, "Ledger reservation ownership changed")
    if baseline:
        validate_baseline(c, project, admission)
    if not one(
        c,
        "SELECT m.user_id FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.role='admin' AND m.active AND u.active",
        (project, job["created_by"]),
    ):
        raise HTTPException(409, "QA requesting administrator no longer authorized")
    return job, row, admission, verified


def claim(c, project, identifier, reservation):
    job, row, admission, value = authority(c, project, identifier, reservation)
    if job["state"] != "queued":
        return None
    token = uid()
    c.execute(
        "UPDATE anvil.runtime_update_jobs SET state='claimed',claim_token=%s,claimed_at=clock_timestamp() WHERE id=%s",
        (token, identifier),
    )
    safe = value.model_dump(mode="json")
    c.execute(
        "INSERT INTO anvil.runtime_qa_job_admissions(job_id,project_id,admission_id,reservation,reservation_sha256) VALUES(%s,%s,%s,%s,%s)",
        (identifier, project, row["id"], Jsonb(safe), digest(safe)),
    )
    return dict(job, state="claimed", claim_token=token), admission


def event(c, project, job, phase, receipt):
    checksum = digest(receipt)
    old = one(
        c,
        "SELECT receipt_sha256 FROM anvil.runtime_update_events WHERE project_id=%s AND job_id=%s AND phase=%s AND (phase<>'outcome_unknown' OR receipt_sha256=%s)",
        (project, job, phase, checksum),
    )
    if old:
        if old["receipt_sha256"] != checksum:
            raise HTTPException(409, "QA receipt conflicts with immutable history")
        return checksum
    c.execute(
        "INSERT INTO anvil.runtime_update_events(id,project_id,job_id,phase,receipt,receipt_sha256) VALUES(%s,%s,%s,%s,%s,%s)",
        (uid(), project, job, phase, Jsonb(receipt), checksum),
    )
    return checksum


def invalidate(c, project, identifier, token, reservation):
    job, row, admission, _ = authority(c, project, identifier, reservation, claim_token=token)
    if not one(
        c,
        "SELECT id FROM anvil.runtime_update_events WHERE project_id=%s AND job_id=%s AND phase='qualified'",
        (project, identifier),
    ):
        raise HTTPException(409, "Exact role qualification required before cutover fence")
    c.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
        (f"runtime-qa-mapping:{admission.deployment_id}:{admission.role}",),
    )
    mapped = c.execute(
        "SELECT project_id FROM anvil.runtime_qa_deployment_projects WHERE deployment_id=%s AND role=%s ORDER BY project_id FOR SHARE",
        (admission.deployment_id, admission.role),
    ).fetchall()
    projects = sorted(str(r["project_id"]) for r in mapped)
    if (
        projects != sorted(str(p) for p in admission.affected_projects)
        or digest(projects) != admission.deployment_projects_sha256
    ):
        raise HTTPException(409, "Affected project deployment mapping changed")
    old = one(
        c,
        "SELECT receipt FROM anvil.runtime_update_events WHERE project_id=%s AND job_id=%s AND phase='invalidated'",
        (project, identifier),
    )
    if old:
        return old["receipt"]
    revoked = []
    for target in projects:
        c.execute(
            "INSERT INTO anvil.runtime_qa_project_fences(job_id,project_id,role) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
            (identifier, target, admission.role),
        )
        # FK KEY SHARE precedes the authority lock, matching API project locks.
        c.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            ("private-python-authority:" + target,),
        )
        rows = c.execute(
            "SELECT q.id FROM anvil.project_binding_qualifications q WHERE q.project_id=%s AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id) ORDER BY q.id FOR UPDATE",
            (target,),
        ).fetchall()
        for qualification in rows:
            c.execute(
                "INSERT INTO anvil.project_binding_qualification_revocations(id,project_id,qualification_id,reason) VALUES(%s,%s,%s,%s) ON CONFLICT(qualification_id) DO NOTHING",
                (
                    uid(),
                    target,
                    qualification["id"],
                    "Runtime QA cutover "
                    + str(identifier)
                    + " requires new exact-runtime qualification",
                ),
            )
            revoked.append(str(qualification["id"]))
    receipt = {
        "job_id": str(identifier),
        "affected_project_count": len(projects),
        "mapping_sha256": digest(projects),
        "revoked_qualification_count": len(revoked),
        "revoked_ids_sha256": digest(sorted(revoked)),
        "historical_bindings_preserved": True,
    }
    event(c, project, identifier, "invalidated", receipt)
    return receipt


def record(c, project, identifier, token, reservation, receipt):
    body = HostReceipt.model_validate(receipt)
    require_operator(c)
    if body.phase == "failed" or (
        body.phase == "rolled_back" and str(body.recovery_of_job_id) == str(identifier)
    ):
        # Same first lock as HTTP idempotency: a concurrent new operation ID
        # cannot pass the failed-admission guard while failure is committed.
        c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    existing = one(
        c,
        "SELECT * FROM anvil.runtime_update_jobs WHERE project_id=%s AND id=%s FOR UPDATE",
        (project, identifier),
    )
    if not existing or str(existing["claim_token"]) != str(token):
        raise HTTPException(409, "Wrong QA receipt custody")
    value = body.model_dump(mode="json")
    old = one(
        c,
        "SELECT receipt_sha256 FROM anvil.runtime_update_events WHERE project_id=%s AND job_id=%s AND phase=%s",
        (project, identifier, body.phase),
    )
    if (
        old
        and old["receipt_sha256"] == digest(value)
        and existing["state"] in (body.phase, "activated", "rolled_back", "failed")
    ):
        return {
            "job_id": str(identifier),
            "state": existing["state"],
            "receipt_sha256": old["receipt_sha256"],
            "exact_duplicate": True,
            "paid_dispatch_authorized": False,
        }
    if body.phase in ("outcome_unknown", "failed"):
        # Persist historical physical uncertainty even if its admission was revoked.
        # This grants no right to start/continue/activate or clear the ledger lock.
        pin = existing["request"]
        if (
            str(body.job_id) != str(identifier)
            or body.role != existing["role"]
            or any(
                getattr(body, k) != pin[k]
                for k in ("image_digest", "source_commit", "lock_digest", "operator_spec_sha256")
            )
        ):
            raise HTTPException(409, "Wrong uncertain operation pin")
        checksum = event(c, project, identifier, body.phase, value)
        if existing["state"] != body.phase:
            c.execute(
                "UPDATE anvil.runtime_update_jobs SET state=%s,finished_at=CASE WHEN %s THEN clock_timestamp() ELSE NULL END WHERE id=%s",
                (body.phase, body.phase == "failed", identifier),
            )
        return {
            "job_id": str(identifier),
            "state": body.phase,
            "receipt_sha256": checksum,
            "automatic_retry": False,
        }
    job, row, admission, _ = authority(c, project, identifier, reservation, claim_token=token)
    recovery = (
        body.phase == "rolled_back"
        and admission.action == "activate"
        and body.action == "rollback"
        and str(body.recovery_of_job_id) == str(identifier)
        and job["state"] in ("installed", "outcome_unknown")
    )
    target = {
        k: getattr(admission, ("baseline_" + k) if recovery else k)
        for k in ("image_digest", "source_commit", "lock_digest")
    }
    if (
        str(body.job_id) != str(identifier)
        or body.role != admission.role
        or (body.action != admission.action and not recovery)
        or any(getattr(body, k) != target[k] for k in target)
        or any(
            getattr(body, k) != getattr(admission, k)
            for k in (
                "operator_spec_sha256",
                "qualification_sha256",
                "rollback_compatibility_sha256",
                "deployment_projects_sha256",
                "database_schema",
                "storage_identity_sha256",
            )
        )
        or body.checks_sha256 != digest(admission.checks)
    ):
        raise HTTPException(409, "QA physical receipt differs from admitted source/role/storage")
    now = datetime.now(timezone.utc)
    if body.observed_at > now or (now - body.observed_at).total_seconds() > 30:
        raise HTTPException(409, "Fresh host operation readback required")
    if body.phase in ("activated", "rolled_back"):
        if (
            (
                not recovery
                and body.phase != ("activated" if admission.action == "activate" else "rolled_back")
            )
            or not body.running
            or body.pending_or_unknown_work
            or body.serving_image_digest != body.image_digest
        ):
            raise HTTPException(409, "Successful exact serving readback required")
        if not one(
            c,
            "SELECT id FROM anvil.runtime_update_events WHERE project_id=%s AND job_id=%s AND phase='invalidated'",
            (project, identifier),
        ):
            raise HTTPException(409, "Affected project qualification fence required")
    checksum = event(c, project, identifier, body.phase, value)
    if body.phase == "qualified":
        return {"job_id": str(identifier), "state": job["state"], "receipt_sha256": checksum}
    if job["state"] != body.phase:
        terminal = body.phase in ("activated", "rolled_back", "failed")
        c.execute(
            "UPDATE anvil.runtime_update_jobs SET state=%s,finished_at=CASE WHEN %s THEN clock_timestamp() ELSE NULL END WHERE id=%s",
            (body.phase, terminal, identifier),
        )
    if body.phase in ("activated", "rolled_back"):
        observation = Observation(
            image_digest=body.image_digest,
            source_commit=body.source_commit,
            lock_digest=body.lock_digest,
            architecture="linux/amd64",
            interpreter=admission.baseline_interpreter if recovery else admission.interpreter,
            installed_adapters=admission.baseline_adapters
            if recovery
            else admission.installed_adapters,
            last_successful_operation="QA_" + body.phase,
            operation_evidence_digest=body.physical_receipt_sha256,
            qualification_state="observed_not_qualified",
            rollback_digest=admission.baseline_image_digest if body.phase == "activated" else None,
        ).model_dump(mode="json")
        origin = (
            "observed_deployed_role"
            if body.provenance == "observed_qa"
            else "isolated_image_control"
        )
        # Only a real host observation changes the current serving read model.
        if not one(
            c,
            "SELECT id FROM anvil.runtime_update_events WHERE project_id=%s AND job_id=%s AND phase='reconciled'",
            (project, identifier),
        ):
            for target in admission.affected_projects:
                c.execute(
                    "INSERT INTO anvil.runtime_role_observations(id,project_id,role,origin,evidence,evidence_sha256,verified_at,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,clock_timestamp())",
                    (
                        uid(),
                        target,
                        admission.role,
                        origin,
                        Jsonb(observation),
                        digest(observation),
                        body.observed_at,
                    ),
                )
            event(
                c,
                project,
                identifier,
                "reconciled",
                {"terminal_receipt_sha256": checksum, "observation_origin": origin},
            )
    return {
        "job_id": str(identifier),
        "state": body.phase,
        "receipt_sha256": checksum,
        "qa_serving_verified": body.phase in ("activated", "rolled_back")
        and body.provenance == "observed_qa",
        "paid_dispatch_authorized": False,
        "automatic_retry": False,
    }


def discover(c, project, role):
    check_role(role)
    if not enabled():
        return {
            "role": role,
            "admissions": [],
            "qa_activation_available": False,
            "qa_rollback_available": False,
            "blockers": ["qualified_QA_operator_not_enabled"],
        }
    items = []
    rows = c.execute(
        "SELECT id FROM anvil.runtime_qa_admissions WHERE project_id=%s AND role=%s AND expires_at>clock_timestamp() ORDER BY created_at DESC,id DESC LIMIT 50",
        (project, role),
    ).fetchall()
    for entry in rows:
        try:
            row, a = load_admission(c, project, entry["id"])
            validate_baseline(c, project, a)
        except (HTTPException, ValidationError):
            continue
        items.append(
            {
                "id": row["id"],
                "candidate_id": row["candidate_id"],
                "expected_observation_id": a.baseline_observation_id,
                "action": a.action,
                "image_digest": a.image_digest,
                "source_commit": a.source_commit,
                "lock_digest": a.lock_digest,
                "admission_sha256": row["envelope_sha256"],
                "expires_at": a.expires_at,
                "blockers": ["fresh_operator_ledger_CAS_required", "exact_host_readback_required"],
            }
        )
    return {
        "role": role,
        "admissions": items,
        "qa_activation_available": any(i["action"] == "activate" for i in items),
        "qa_rollback_available": any(i["action"] == "rollback" for i in items),
        "paid_dispatch_authorized": False,
    }
