"""Unregistered, read-only adapter for a proposed operator-owned registry.

No migration, writer, public registration or dispatch authority is provided here.
Absent registry/schema custody is a provisioning block, never a fallback to legacy
093 or an author-supplied qualification. Actual SQL/RLS acceptance is separate.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from anvil.dataset_export_contract import Identifier, Model, Sha
from anvil.golden_kyc_application_plan import PolicyQualification
from anvil.praxis_case_dataset import PolicyRef, content_hash
from anvil.praxis_generic_contract import TemplateRef, canonical

QUALIFICATIONS = "anvil.kyc_application_policy_qualifications"
REVOCATIONS = "anvil.kyc_application_policy_revocations"
MAX_RECORDS = 100
MAX_BODY_BYTES = 131072

# to_regclass allows a missing proposed schema to produce a blocked result
# without executing a statement against an absent relation. No caller SQL names.
CUSTODY_SQL = """
SELECT statement_timestamp() AS checked_at,
 current_setting('anvil.project',true) AS scoped_project,
 NOT role.rolsuper AND NOT role.rolbypassrls
 AND NOT role.rolcreaterole AND NOT role.rolreplication AS restricted_role,
 (SELECT count(*)=2 AND bool_and(c.relrowsecurity AND c.relforcerowsecurity
   AND NOT pg_has_role(current_user,c.relowner,'MEMBER')
   AND has_table_privilege(current_user,c.oid,'SELECT')
   AND NOT has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
   AND NOT has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE'))
  FROM pg_class c WHERE c.oid IN (to_regclass(%s),to_regclass(%s))) AS read_only_rls
FROM pg_roles role WHERE role.rolname=current_user
"""

# Select ALL current records in the exact immutable workflow/source scope. Product,
# state, charter and effective interval are validated from the hashed body below;
# SQL filtering on unvalidated body fields must not hide malformed/overlap records.
RECORDS_SQL = """
SELECT q.id,q.project_id,
 CASE WHEN octet_length(q.body::text)<=%s THEN q.body ELSE NULL END AS body,
 q.content_sha256,q.expires_at
FROM anvil.kyc_application_policy_qualifications q
WHERE q.project_id=%s AND q.scope_sha256=%s AND q.expires_at>statement_timestamp()
 AND NOT EXISTS(SELECT 1 FROM anvil.kyc_application_policy_revocations r
                WHERE r.project_id=q.project_id AND r.qualification_id=q.id)
LIMIT %s
"""


class _Scope(Model):
    """Loaded from original authenticated export and project binding, not a form."""

    project_id: UUID
    project_binding_id: UUID
    project_binding_sha256: Sha
    source_sha256: Sha
    export_sha256: Sha
    task_id: Identifier
    revision_id: Identifier
    workflow_product: Literal["individual", "adult_joint", "teen_joint", "custodial"]
    payload_sha256: Sha
    workflow_review_receipt_sha256: Sha
    runtime_source_sha256: Sha
    runtime_image_sha256: Sha
    environment_binding_sha256: Sha
    evaluator_bindings_sha256: Sha


class RegistryScope(_Scope):
    """Older private prototype, preserved with its exact disjoint scope."""

    execution_contract: Literal["anvil.template-execution.v4"]


class ProductRegistryScope(_Scope):
    """Additive unchanged-v1 scope; never reinterpret the older prototype."""

    export_contract: Literal["praxis.authored-task-export.v1"]
    selector_field: Literal["product"]
    template: TemplateRef
    template_qualification_receipt_sha256: Sha
    resolved_input_id: UUID
    resolved_input_sha256: Sha

    @model_validator(mode="after")
    def published_product_version(self):
        if self.template.version < 7:
            raise ValueError("Published v7-or-successor product task scope required")
        return self


class PolicySet(Model):
    id: Identifier
    version: Identifier
    product: Literal["individual", "adult_joint", "teen_joint", "custodial"]
    governing_state: Literal["CA", "NY", "TX", "FL", "IL"]
    charter_profile: str = Field(min_length=1, max_length=200)
    federal_refs: list[PolicyRef] = Field(min_length=1, max_length=100)
    state_refs: list[PolicyRef] = Field(min_length=1, max_length=100)
    effective_from: date
    effective_until: date

    @model_validator(mode="after")
    def unique_interval(self):
        if self.effective_from >= self.effective_until:
            raise ValueError("Inclusive start and exclusive end required")
        for refs in (self.federal_refs, self.state_refs):
            if len({ref.id for ref in refs}) != len(refs):
                raise ValueError("Unique policy identities within each scope required")
        return self


class ReceiptReference(Model):
    id: UUID
    sha256: Sha


class RegistryRecord(Model):
    schema_version: Literal["anvil.private-kyc-policy-qualification.v1"]
    id: UUID
    scope: RegistryScope | ProductRegistryScope
    policy_set: PolicySet
    policy_set_sha256: Sha
    domain_review_receipt: ReceiptReference
    runtime_control_receipt: ReceiptReference
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def exact_policy_set(self):
        if content_hash(self.policy_set.model_dump(mode="json")) != self.policy_set_sha256:
            raise ValueError("Policy set content identity changed")
        return self


@dataclass(frozen=True, slots=True)
class RegistryResult:
    status: str
    requirement: str | None
    checked_at: datetime | None = None
    qualifications: tuple[PolicyQualification, ...] = ()
    qualification_record_ids: tuple[str, ...] = ()
    # Even genuine reads cannot establish a future dispatch's current admission.
    run_authority: str = "not_granted"
    owner: str = "anvil_provisioning"


def _blocked(code, checked_at=None):
    return RegistryResult("blocked", code, checked_at)


def _steps(scope, *, product, governing_state, charter_profile, assessment_date,
           federal_refs, policy_set_constraint=None, check_deadline=lambda: None):
    """Read registry candidates only, using database time and existing RLS session.

    The caller must authenticate scope against the original source, not construct
    it from candidate inputs. This adapter never sets project/user/session roles,
    creates records, accepts approval booleans or opens its own connection.
    SQL errors intentionally propagate to the owning transaction, which must
    rollback; they are never reinterpreted as empty/qualified registry results.
    """
    if type(scope) not in (RegistryScope, ProductRegistryScope):
        raise ValueError("Original typed authenticated workflow scope required")
    if (product not in {"individual", "adult_joint", "teen_joint", "custodial"}
            or product != scope.workflow_product
            or governing_state not in {"CA", "NY", "TX", "FL", "IL"}
            or type(charter_profile) is not str or not 1 <= len(charter_profile) <= 200
            or type(assessment_date) is not date):
        raise ValueError("Exact application type/state/charter/date required")
    if (type(federal_refs) is not tuple or not federal_refs or len(federal_refs) > 100
            or any(type(ref) is not PolicyRef for ref in federal_refs)
            or len({ref.id for ref in federal_refs}) != len(federal_refs)):
        raise ValueError("Exact common policy references required")
    if policy_set_constraint is not None:
        # Reuse the declared strict hash field instead of accepting arbitrary text.
        from pydantic import TypeAdapter

        TypeAdapter(Sha).validate_python(policy_set_constraint, strict=True)
    check_deadline()
    custody = yield ("one", CUSTODY_SQL, (QUALIFICATIONS, REVOCATIONS))
    if (not custody or custody["scoped_project"] != str(scope.project_id)
            or custody["restricted_role"] is not True):
        return _blocked("AV_KYC_REGISTRY_SCOPE_REQUIRED")
    if custody["read_only_rls"] is not True:
        return _blocked("AV_KYC_SCOPED_REGISTRY_REQUIRED")
    checked = custody["checked_at"]
    if type(checked) is not datetime or checked.tzinfo is None or checked.utcoffset() is None:
        return _blocked("AV_KYC_REGISTRY_TIME_REQUIRED")
    scope_hash = content_hash(scope.model_dump(mode="json"))
    # Bound the driver's complete result buffer, not just fetchmany consumption.
    # The extra row is a denial sentinel; never choose among an incomplete set.
    check_deadline()
    rows = yield ("many", RECORDS_SQL, (MAX_BODY_BYTES, scope.project_id, scope_hash, MAX_RECORDS + 1))
    if len(rows) > MAX_RECORDS:
        return _blocked("AV_KYC_REGISTRY_BOUND_EXCEEDED", checked)
    candidates = []
    common = sorted((ref.model_dump() for ref in federal_refs), key=lambda ref: ref["id"])
    for row in rows:
        check_deadline()
        try:
            # Bound canonical body before parsing a privileged but corrupt record.
            from anvil.campaign_semantic_contract import bounded_json

            bounded_json(row["body"], MAX_BODY_BYTES, max_nodes=10000, max_depth=8)
            body = RegistryRecord.model_validate_json(canonical(row["body"]))
            if (str(body.id) != str(row["id"]) or body.scope != scope
                    or str(row["project_id"]) != str(scope.project_id)
                    or body.expires_at != row["expires_at"]
                    or body.expires_at <= checked
                    or content_hash(row["body"]) != row["content_sha256"]):
                return _blocked("AV_KYC_REGISTRY_INTEGRITY_REQUIRED", checked)
        except (KeyError, TypeError, ValueError):
            return _blocked("AV_KYC_REGISTRY_INTEGRITY_REQUIRED", checked)
        policy = body.policy_set
        if (policy.product == product and policy.governing_state == governing_state
                and policy.charter_profile == charter_profile
                and policy.effective_from <= assessment_date < policy.effective_until
                and sorted((ref.model_dump() for ref in policy.federal_refs), key=lambda ref: ref["id"]) == common
                and (policy_set_constraint is None or policy_set_constraint == body.policy_set_sha256)):
            candidates.append((body, row["content_sha256"]))
    if len(candidates) != 1:
        return _blocked("AV_KYC_POLICY_QUALIFICATION_REQUIRED" if not candidates
                        else "AV_KYC_POLICY_QUALIFICATION_AMBIGUOUS", checked)
    body, receipt_hash = candidates[0]
    policy = body.policy_set
    projection = PolicyQualification(policy.governing_state, policy.product, tuple(policy.federal_refs),
                                     tuple(policy.state_refs), policy.effective_from, policy.effective_until,
                                     body.expires_at, receipt_hash, body.policy_set_sha256, policy.charter_profile)
    return RegistryResult("registry_candidate_not_admitted", None, checked, (projection,), (str(body.id),))


def load(connection, scope, **request):
    """Synchronous consistency utility; not the bounded runtime query path."""
    steps = _steps(scope, **request)
    try:
        instruction = next(steps)
        while True:
            operation, sql, params = instruction
            cursor = connection.execute(sql, params)
            observed = cursor.fetchone() if operation == "one" else cursor.fetchmany(MAX_RECORDS + 1)
            instruction = steps.send(observed)
    except StopIteration as completed:
        return completed.value
    finally:
        steps.close()


async def load_async(connection, scope, *, absolute_deadline, **request):
    """Same checks/SQL, awaited under the connection's original bounded cutoff."""
    import asyncio

    from anvil.marketing_capture_database import remaining

    remaining(absolute_deadline)
    remaining(connection.capture_deadline)
    hard = min(absolute_deadline, connection.capture_deadline)
    connection.capture_deadline = hard  # Narrow only; never grant replacement time.
    steps = _steps(scope, check_deadline=lambda: remaining(hard), **request)
    try:
        async with asyncio.timeout(remaining(hard)):
            instruction = next(steps)
            while True:
                operation, sql, params = instruction
                remaining(hard)
                cursor = await connection.execute(sql, params)
                observed = await cursor.fetchone() if operation == "one" else await cursor.fetchmany(MAX_RECORDS + 1)
                instruction = steps.send(observed)
    except StopIteration as completed:
        remaining(hard)
        return completed.value
    finally:
        steps.close()


async def read(scope, user, *, absolute_deadline, **request):
    """Private runtime entry; no public contract registration or run admission."""
    from anvil.kyc_registry_database import transaction

    async with transaction(scope.project_id, user, absolute_deadline=absolute_deadline) as connection:
        return await load_async(connection, scope, absolute_deadline=absolute_deadline, **request)
