"""Project runtime observations and inert candidate staging; never an installer.

Only an operator can insert allowlist/observation/revocation evidence. The API
appends Admin candidate selections, not serving changes or execution authority.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import AwareDatetime, Field, ValidationError

from anvil import auth
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.schemas import Strict
from anvil.workspace import READ_ROLES

ROLES = (
    "api",
    "business-worker",
    "golden-grader",
    "golden-scheduler",
    "golden-native-coordinator",
    "task-environment",
    "isolated-python-runner",
)
SHA = r"^[a-f0-9]{64}$"
IMAGE = r"^us-west1-docker\.pkg\.dev/adi-anvil-mvp-2026/anvil-qa-v1/[a-z0-9-]+@sha256:[a-f0-9]{64}$"


class Candidate(Strict):
    image_digest: str = Field(pattern=IMAGE, max_length=300)
    lock_digest: str = Field(pattern=SHA)
    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    expected_candidate_id: UUID | None = None


class Compatibility(Strict):
    compatible_source_commits: list[str] = Field(max_length=50)
    architecture: Literal["linux/amd64", "linux/arm64"]
    operator_spec_sha256: str = Field(pattern=SHA)
    scopes: list[Literal["local_control", "qa"]] = Field(min_length=1, max_length=2)


class UpdateRequest(Strict):
    candidate_id: UUID
    expected_observation_id: UUID | None = None
    scope: Literal["local_control", "qa"] = "local_control"


class OperationReceipt(Strict):
    job_id: UUID
    role: Literal[
        "api",
        "business-worker",
        "golden-grader",
        "golden-scheduler",
        "golden-native-coordinator",
        "task-environment",
        "isolated-python-runner",
    ]
    scope: Literal["local_control"]
    phase: Literal["installed", "local_qualified", "rolled_back", "outcome_unknown", "failed"]
    image_digest: str = Field(pattern=IMAGE, max_length=300)
    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    lock_digest: str = Field(pattern=SHA)
    physical_receipt_sha256: str = Field(pattern=SHA)
    operation: str = Field(pattern=r"^[a-z_]{1,80}$")
    container_id: str | None = Field(default=None, pattern=SHA)


def compatible(allow, observed, scope):
    try:
        spec = Compatibility.model_validate(allow["compatibility"])
    except ValidationError:
        return False
    if scope not in spec.scopes:
        return False
    if observed is None:
        return scope == "local_control" and not spec.compatible_source_commits
    try:
        evidence = Observation.model_validate(observed["evidence"])
    except ValidationError:
        return False
    return (
        observed["origin"] == "observed_deployed_role"
        and digest(observed["evidence"]) == observed["evidence_sha256"]
        and evidence.source_commit in spec.compatible_source_commits
        and evidence.architecture == spec.architecture
    )


def latest_observation(c, project, role):
    return one(
        c,
        "SELECT * FROM anvil.runtime_role_observations WHERE project_id=%s AND role=%s AND origin='observed_deployed_role' ORDER BY verified_at DESC,created_at DESC,id DESC LIMIT 1",
        (project, role),
    )


def release_discovery(c, project, role):
    check_role(role)
    observed = latest_observation(c, project, role)
    allowed = c.execute(
        "SELECT a.id,a.image_digest,a.source_commit,a.lock_digest,a.compatibility,a.review_receipt_sha256,a.expires_at FROM anvil.runtime_role_allowlist a WHERE a.project_id=%s AND a.role=%s AND a.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.runtime_role_allowlist_revocations r WHERE r.project_id=a.project_id AND r.allowlist_id=a.id) ORDER BY a.created_at DESC,a.id DESC LIMIT 50",
        (project, role),
    ).fetchall()
    return {
        "role": role,
        "releases": [
            dict(
                a,
                compatible_scopes=[
                    scope for scope in ("local_control", "qa") if compatible(a, observed, scope)
                ],
            )
            for a in allowed
        ],
        "discovery_origin": "operator_reviewed_pins",
        "automatic_latest_selection": False,
    }


def update_pin(c, project, candidate_id):
    row = one(
        c,
        "SELECT t.*,a.compatibility,a.expires_at,EXISTS(SELECT 1 FROM anvil.runtime_role_allowlist_revocations r WHERE r.project_id=t.project_id AND r.allowlist_id=t.allowlist_id) AS revoked FROM anvil.runtime_role_candidates t JOIN anvil.runtime_role_allowlist a ON a.project_id=t.project_id AND a.id=t.allowlist_id WHERE t.project_id=%s AND t.id=%s",
        (project, candidate_id),
    )
    now = datetime.now(timezone.utc)
    if not row or row["revoked"] or row["expires_at"] <= now:
        raise HTTPException(409, "Runtime pin expired, revoked or unavailable")
    return row


def queue_update(c, project, user, role, body):
    check_role(role)
    if body.scope != "local_control":
        raise HTTPException(
            409,
            "QA Update is unavailable until its operator adapter and release admission are qualified",
        )
    pin = update_pin(c, project, body.candidate_id)
    observed = latest_observation(c, project, role)
    if pin["role"] != role or (str(observed["id"]) if observed else None) != (
        str(body.expected_observation_id) if body.expected_observation_id else None
    ):
        raise HTTPException(409, "Runtime serving baseline changed")
    if not compatible(pin, observed, body.scope):
        raise HTTPException(409, "Pinned release has no compatible operator specification")
    if one(
        c,
        "SELECT id FROM anvil.runtime_update_jobs WHERE project_id=%s AND role=%s AND state IN('queued','claimed','installed','outcome_unknown')",
        (project, role),
    ):
        raise HTTPException(409, "An update exists; reconcile it before another attempt")
    request = {
        "candidate_id": str(body.candidate_id),
        "role": role,
        "scope": body.scope,
        "expected_observation_id": str(body.expected_observation_id)
        if body.expected_observation_id
        else None,
        "image_digest": pin["image_digest"],
        "source_commit": pin["source_commit"],
        "lock_digest": pin["lock_digest"],
        "operator_spec_sha256": pin["compatibility"]["operator_spec_sha256"],
    }
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.runtime_update_jobs(id,project_id,role,candidate_id,expected_observation_id,scope,request,request_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            role,
            body.candidate_id,
            body.expected_observation_id,
            body.scope,
            Jsonb(request),
            digest(request),
            user,
        ),
    )
    audit(c, project, user, "runtime.update_requested", identifier, request)
    return {
        "job_id": identifier,
        "state": "queued",
        "request_sha256": digest(request),
        "scope": body.scope,
        "serving_changed": False,
        "paid_dispatch_authorized": False,
        "blockers": ["existing_privileged_host_operator_required"]
        + (["QA_release_admission_and_serving_readback_required"] if body.scope == "qa" else []),
    }


def job_status(c, project, identifier):
    job = one(
        c,
        "SELECT id,role,scope,state,request,request_sha256,created_at,claimed_at,finished_at FROM anvil.runtime_update_jobs WHERE project_id=%s AND id=%s",
        (project, identifier),
    )
    if not job:
        raise HTTPException(404, "Runtime update not found")
    events = c.execute(
        "SELECT id,phase,receipt,receipt_sha256,created_at FROM anvil.runtime_update_events WHERE project_id=%s AND job_id=%s ORDER BY created_at,id",
        (project, identifier),
    ).fetchall()
    observation = latest_observation(c, project, job["role"])
    revoked = bool(
        observation
        and one(
            c,
            "SELECT id FROM anvil.runtime_role_revocations WHERE project_id=%s AND observation_id=%s",
            (project, observation["id"]),
        )
    )
    return {
        "job": job,
        "operation_receipts": events,
        "last_verified_serving_observation": role_view(job["role"], observation, revoked=revoked),
        "paid_dispatch_authorized": False,
        "automatic_retry": False,
    }


def recent_jobs(c, project, role, limit=10):
    check_role(role)
    if not 1 <= limit <= 20:
        raise HTTPException(422, "Recent runtime job limit must be 1–20")
    rows = c.execute(
        "SELECT id,state,scope,request->>'action' AS action,request->>'admission_id' AS admission_id,request->>'client_operation_id' AS client_operation_id,created_at FROM anvil.runtime_update_jobs WHERE project_id=%s AND role=%s ORDER BY CASE WHEN state IN('queued','claimed','installed','outcome_unknown') THEN 0 ELSE 1 END,created_at DESC,id DESC LIMIT %s",
        (project, role, limit + 1),
    ).fetchall()
    items = []
    for row in rows[:limit]:
        try:
            admission_id = str(UUID(row["admission_id"])) if row["admission_id"] else None
        except (ValueError, TypeError):
            admission_id = None
        try:
            client_operation_id = (
                str(UUID(row["client_operation_id"])) if row["client_operation_id"] else None
            )
        except (ValueError, TypeError):
            client_operation_id = None
        items.append(
            {
                "job_id": row["id"],
                "state": row["state"],
                "scope": row["scope"],
                "action": row["action"] if row["action"] in ("activate", "rollback") else "qualify",
                "admission_id": admission_id,
                "client_operation_id": client_operation_id,
                "created_at": row["created_at"],
            }
        )
    return {
        "role": role,
        "jobs": items,
        "has_more": len(rows) > limit,
        "active_and_unknown_first": True,
        "automatic_retry": False,
    }


def require_operator(c):
    trusted = one(
        c,
        "SELECT r.rolsuper OR current_user=pg_get_userbyid(d.datdba) AS allowed FROM pg_roles r CROSS JOIN pg_database d WHERE r.rolname=current_user AND d.datname=current_database()",
    )
    if not trusted or not trusted["allowed"]:
        raise HTTPException(403, "Existing privileged host operator required")


def operator_claim(c, project, identifier):
    """Commit this claim before any physical action; never reclaim an old claim."""
    require_operator(c)
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    job = one(
        c,
        "SELECT * FROM anvil.runtime_update_jobs WHERE project_id=%s AND id=%s FOR UPDATE",
        (project, identifier),
    )
    if not job or job["state"] != "queued":
        return None
    if job["scope"] != "local_control":
        raise HTTPException(
            409, "QA operator activation/rollback adapter requires independent release admission"
        )
    check_update_authority(c, project, job)
    token = uid()
    c.execute(
        "UPDATE anvil.runtime_update_jobs SET state='claimed',claim_token=%s,claimed_at=clock_timestamp() WHERE id=%s",
        (token, identifier),
    )
    return dict(job, state="claimed", claim_token=token)


def check_update_authority(c, project, job):
    pin = update_pin(c, project, job["candidate_id"])
    observed = latest_observation(c, project, job["role"])
    if (
        digest(job["request"]) != job["request_sha256"]
        or not compatible(pin, observed, job["scope"])
        or (str(observed["id"]) if observed else None)
        != (str(job["expected_observation_id"]) if job["expected_observation_id"] else None)
    ):
        raise HTTPException(409, "Runtime authority or serving baseline changed")
    if not one(
        c,
        "SELECT m.user_id FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.role='admin' AND m.active AND u.active",
        (project, job["created_by"]),
    ):
        raise HTTPException(409, "Requesting administrator no longer has authority")


def operator_assert_authority(c, project, identifier, claim_token):
    require_operator(c)
    job = one(
        c,
        "SELECT * FROM anvil.runtime_update_jobs WHERE project_id=%s AND id=%s FOR UPDATE",
        (project, identifier),
    )
    if (
        not job
        or str(job["claim_token"]) != str(claim_token)
        or job["scope"] != "local_control"
        or job["state"] not in ("claimed", "installed", "outcome_unknown")
    ):
        raise HTTPException(409, "Runtime operator claim is unavailable")
    check_update_authority(c, project, job)
    return job


def record_local_operation(c, project, identifier, claim_token, body):
    """Trusted host receipt, not an API route or deployment qualification grant."""
    require_operator(c)
    receipt = OperationReceipt.model_validate(body)
    job = one(
        c,
        "SELECT * FROM anvil.runtime_update_jobs WHERE project_id=%s AND id=%s FOR UPDATE",
        (project, identifier),
    )
    if not job or str(job["claim_token"]) != str(claim_token) or job["scope"] != "local_control":
        raise HTTPException(409, "Wrong runtime operation custody")
    pin = job["request"]
    if (
        str(receipt.job_id) != str(identifier)
        or receipt.role != job["role"]
        or any(
            getattr(receipt, k) != pin[k] for k in ("image_digest", "source_commit", "lock_digest")
        )
    ):
        raise HTTPException(409, "Operation receipt does not match the pinned job")
    value = receipt.model_dump(mode="json")
    if receipt.phase == "local_qualified":
        check_update_authority(c, project, job)
    old = one(
        c,
        "SELECT receipt_sha256 FROM anvil.runtime_update_events WHERE project_id=%s AND job_id=%s AND phase=%s AND (phase<>'outcome_unknown' OR receipt_sha256=%s)",
        (project, identifier, receipt.phase, digest(value)),
    )
    if old and old["receipt_sha256"] != digest(value):
        raise HTTPException(409, "Retained runtime operation differs from existing receipt")
    if old and job["state"] == receipt.phase:
        return {
            "job_id": str(identifier),
            "state": receipt.phase,
            "receipt_sha256": digest(value),
            "serving_changed": False,
            "scope": "local_control",
        }
    if not old:
        c.execute(
            "INSERT INTO anvil.runtime_update_events(id,project_id,job_id,phase,receipt,receipt_sha256) VALUES(%s,%s,%s,%s,%s,%s)",
            (uid(), project, identifier, receipt.phase, Jsonb(value), digest(value)),
        )
    if receipt.phase == "outcome_unknown" and job["state"] == "outcome_unknown":
        return {
            "job_id": str(identifier),
            "state": receipt.phase,
            "receipt_sha256": digest(value),
            "serving_changed": False,
            "scope": "local_control",
        }
    terminal = receipt.phase in ("local_qualified", "rolled_back", "failed")
    c.execute(
        "UPDATE anvil.runtime_update_jobs SET state=%s,finished_at=CASE WHEN %s THEN clock_timestamp() ELSE NULL END WHERE id=%s",
        (receipt.phase, terminal, identifier),
    )
    # Local controls deliberately do not insert serving observations, invalidate
    # production bindings, consume a cloud build, or mint full paid qualification.
    return {
        "job_id": str(identifier),
        "state": receipt.phase,
        "receipt_sha256": digest(value),
        "serving_changed": False,
        "scope": "local_control",
    }


class Adapter(Strict):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)


class Observation(Strict):
    """Safe metadata only; no raw worker logs, environment or filesystem reads."""

    image_digest: str = Field(pattern=IMAGE, max_length=300)
    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    architecture: Literal["linux/amd64", "linux/arm64"]
    interpreter: str = Field(pattern=r"^/[A-Za-z0-9_./-]+$", max_length=240)
    lock_digest: str | None = Field(default=None, pattern=SHA)
    installed_adapters: list[Adapter] = Field(default_factory=list, max_length=40)
    last_successful_operation: str | None = Field(default=None, max_length=100)
    operation_evidence_digest: str | None = Field(default=None, pattern=SHA)
    target_id: UUID | None = None
    binding_id: UUID | None = None
    qualification_state: Literal["observed_not_qualified", "qualified"] = "observed_not_qualified"
    qualification_evidence_digest: str | None = Field(default=None, pattern=SHA)
    expires_at: AwareDatetime | None = None
    rollback_digest: str | None = Field(default=None, pattern=IMAGE, max_length=300)


def check_role(role):
    if role not in ROLES:
        raise HTTPException(404, "Runtime role not found")


def role_view(role, observed=None, candidates=(), revoked=False, now=None):
    """Pure rendering: missing evidence stays null and staging cannot promote it."""
    now = now or datetime.now(timezone.utc)
    view = dict.fromkeys(
        (
            "current_image_digest",
            "source_commit",
            "lock_digest",
            "architecture",
            "interpreter",
            "last_successful_operation",
            "operation_evidence_digest",
            "target_id",
            "binding_id",
            "expires_at",
            "rollback_digest",
            "last_verified_at",
            "observation_id",
            "observation_evidence_digest",
            "provenance",
        )
    )
    view.update(
        role=role,
        installed_adapters=[],
        qualification_state="unavailable",
        revoked=None,
        blockers=["actual_role_observation_required"],
        serving_changed=False,
        dispatch_authorized=False,
    )
    if observed:
        try:
            if (
                digest(observed["evidence"]) != observed["evidence_sha256"]
                or observed["verified_at"] > now
            ):
                raise ValueError("Observation integrity or time mismatch")
            evidence = Observation.model_validate(observed["evidence"])
        except (ValidationError, TypeError, ValueError):
            view["blockers"] = ["invalid_operator_observation"]
        else:
            if observed["origin"] != "observed_deployed_role":
                view["blockers"] = ["deployed_role_observation_required"]
            else:
                data = evidence.model_dump(mode="json")
                view.update({k: data[k] for k in data if k != "image_digest"})
                view.update(
                    current_image_digest=evidence.image_digest,
                    last_verified_at=observed["verified_at"],
                    provenance=observed["origin"],
                    observation_id=observed["id"],
                    observation_evidence_digest=observed["evidence_sha256"],
                    revoked=revoked,
                )
                gaps = ["independent_runtime_qualification_required"]
                state = "observed_not_qualified"
                if evidence.qualification_state == "qualified":
                    if revoked:
                        state, gaps = "revoked", ["qualification_revoked"]
                    elif evidence.expires_at is None or evidence.expires_at <= now:
                        state, gaps = "expired", ["current_qualification_required"]
                    elif not all(
                        (
                            evidence.lock_digest,
                            evidence.last_successful_operation,
                            evidence.operation_evidence_digest,
                            evidence.qualification_evidence_digest,
                            evidence.target_id,
                            evidence.binding_id,
                        )
                    ):
                        state, gaps = (
                            "unavailable",
                            ["source_bound_operation_qualification_required"],
                        )
                    else:
                        # A read model reports operator evidence; Run still checks its
                        # actual admission authority. This route never grants dispatch.
                        state, gaps = "reported_qualified", []
                view.update(qualification_state=state, blockers=gaps)
    latest = candidates[0] if candidates else None
    candidate_blockers = (
        [
            "independent_exact_release_checks_required",
            "fresh_build_ledger_failure_chain_and_CAS_required",
            "Harbor_gated_rollout_required",
        ]
        if latest
        else []
    )
    if latest and (
        latest.get("allowlist_revoked")
        or latest.get("allowlist_expires_at") is None
        or latest["allowlist_expires_at"] <= now
    ):
        candidate_blockers.append("candidate_allowlist_expired_or_revoked")
    view.update(
        candidate_image_digest=latest["image_digest"] if latest else None,
        candidate=latest,
        candidate_history=list(candidates),
        candidate_blockers=candidate_blockers,
    )
    return view


def listing(c, project):
    from anvil.golden_component_qualification import installed as component_qualification
    from anvil.marketing_capture_database_target import readiness as capture_database_readiness
    from anvil.runtime_admin_qa import discover

    items = []
    for role in ROLES:
        observed = one(
            c,
            "SELECT * FROM anvil.runtime_role_observations WHERE project_id=%s AND role=%s AND origin='observed_deployed_role' ORDER BY verified_at DESC,created_at DESC,id DESC LIMIT 1",
            (project, role),
        )
        candidates = c.execute(
            "SELECT t.id,t.image_digest,t.source_commit,t.lock_digest,t.allowlist_id,t.created_by,t.created_at,a.expires_at AS allowlist_expires_at,EXISTS(SELECT 1 FROM anvil.runtime_role_allowlist_revocations r WHERE r.project_id=t.project_id AND r.allowlist_id=t.allowlist_id) AS allowlist_revoked FROM anvil.runtime_role_candidates t JOIN anvil.runtime_role_allowlist a ON a.project_id=t.project_id AND a.id=t.allowlist_id WHERE t.project_id=%s AND t.role=%s ORDER BY t.created_at DESC,t.id DESC LIMIT 20",
            (project, role),
        ).fetchall()
        revoked = bool(
            observed
            and one(
                c,
                "SELECT id FROM anvil.runtime_role_revocations WHERE project_id=%s AND observation_id=%s",
                (project, observed["id"]),
            )
        )
        item = role_view(role, observed, candidates, revoked)
        item["qa_operator"] = discover(c, project, role)
        items.append(item)
    technical = component_qualification()
    evidence = technical.get("evidence", {}) if technical.get("ready") is True else {}
    return {
        "roles": items,
        "technical_components": {
            "ready": technical.get("ready") is True,
            "scope": "technical_components_only", "spending_authority": False,
            "project_qualification_granted": False,
            "expires_at": evidence.get("expires_at"),
            "source_sha256": evidence.get("golden_source_sha256"),
            "runtime_image_sha256": evidence.get("runtime_image_sha256"),
            "missing": technical.get("missing", []),
        },
        "capture_database": capture_database_readiness(),
        "history_limit_per_role": 20,
        "candidate_staging_only": True,
        "local_operator_jobs_available": True,
        "qa_activation_available": any(i["qa_operator"]["qa_activation_available"] for i in items),
        "qa_rollback_available": any(i["qa_operator"]["qa_rollback_available"] for i in items),
        "deployment_available": False,
        "paid_dispatch_authorized": False,
    }


def stage(c, project, user, role, body):
    check_role(role)
    # Serialize selection versions with the existing project-scoped idempotency lock.
    current = one(
        c,
        "SELECT id FROM anvil.runtime_role_candidates WHERE project_id=%s AND role=%s ORDER BY created_at DESC,id DESC LIMIT 1",
        (project, role),
    )
    if (str(current["id"]) if current else None) != (
        str(body.expected_candidate_id) if body.expected_candidate_id else None
    ):
        raise HTTPException(409, "Runtime candidate changed; reload before staging")
    allowed = one(
        c,
        "SELECT a.id FROM anvil.runtime_role_allowlist a WHERE a.project_id=%s AND a.role=%s AND a.image_digest=%s AND a.lock_digest=%s AND a.source_commit=%s AND a.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.runtime_role_allowlist_revocations r WHERE r.project_id=a.project_id AND r.allowlist_id=a.id)",
        (project, role, body.image_digest, body.lock_digest, body.source_commit),
    )
    if not allowed:
        raise HTTPException(
            409, "Exact role/image/source/lock candidate is not currently allowlisted"
        )
    identifier = uid()
    receipt = {
        "role": role,
        "image_digest": body.image_digest,
        "source_commit": body.source_commit,
        "lock_digest": body.lock_digest,
        "allowlist_id": str(allowed["id"]),
        "serving_changed": False,
        "status": "staged_not_promoted",
        "dispatch_authorized": False,
    }
    c.execute(
        "INSERT INTO anvil.runtime_role_candidates(id,project_id,role,image_digest,source_commit,lock_digest,allowlist_id,created_by,receipt,receipt_sha256,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())",
        (
            identifier,
            project,
            role,
            body.image_digest,
            body.source_commit,
            body.lock_digest,
            allowed["id"],
            user,
            Jsonb(receipt),
            digest(receipt),
        ),
    )
    audit(c, project, user, "runtime.candidate_staged", identifier, receipt)
    return {"id": identifier, **receipt, "receipt_sha256": digest(receipt)}


def routes(context, wrap, idempotent):
    from anvil.runtime_admin_qa import QARequest

    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/runtime-admin")

    @router.get("/roles/{role}/updates")
    def get_recent_updates(
        project: UUID, role: str, request: Request, limit: int = Query(10, ge=1, le=20)
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            return wrap(recent_jobs(c, project, role, limit), request)

    @router.get("/roles/{role}/qa-admissions")
    def get_qa_admissions(project: UUID, role: str, request: Request):
        from anvil.runtime_admin_qa import discover

        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            return wrap(discover(c, project, role), request)

    @router.post("/roles/{role}/qa-updates")
    def post_qa_update(project: UUID, role: str, body: QARequest, request: Request):
        from anvil.runtime_admin_qa import queue

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body.model_dump(mode="json"),
                    lambda: queue(c, project, user, role, body),
                ),
                request,
            )

    @router.get("/roles/{role}/releases")
    def get_releases(project: UUID, role: str, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            return wrap(release_discovery(c, project, role), request)

    @router.post("/roles/{role}/updates")
    def post_update(project: UUID, role: str, body: UpdateRequest, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body.model_dump(mode="json"),
                    lambda: queue_update(c, project, user, role, body),
                ),
                request,
            )

    @router.get("/updates/{identifier}")
    def get_update(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            return wrap(job_status(c, project, identifier), request)

    @router.get("/roles")
    def get_roles(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            return wrap(listing(c, project), request)

    @router.post("/roles/{role}/candidates")
    def post_candidate(project: UUID, role: str, body: Candidate, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            check_role(role)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body.model_dump(mode="json"),
                    lambda: stage(c, project, user, role, body),
                ),
                request,
            )

    return router
