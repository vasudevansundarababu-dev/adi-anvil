"""Unregistered, private application-type compatibility planner.

Inputs must come from authenticated Anvil registries, never the authoring payload.
This pure planner checks their consistency, not their authenticity. Its results
grant no execution, publication, legal acceptance or paid-call authority.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime

from anvil.golden_kyc_type_index import derive
from anvil.praxis_case_dataset import PolicyRef, content_hash
from anvil.project_input_contract import Application


@dataclass(frozen=True, slots=True)
class Workflow:
    task_id: str
    revision_id: str
    product: str
    review_receipt_sha256: str
    federal_refs: tuple[PolicyRef, ...]
    # Optional exact constraint exported by Praxis, not another author field.
    state_policy_set_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class PolicyQualification:
    """Private registry projection; no boolean supplied by an author can create it."""

    governing_state: str
    product: str
    federal_refs: tuple[PolicyRef, ...]
    state_refs: tuple[PolicyRef, ...]
    effective_from: date
    effective_until: date
    valid_until: datetime
    receipt_sha256: str
    policy_set_sha256: str
    charter_profile: str
    revoked: bool = False
    state_applicability: str = "applicable"


@dataclass(frozen=True, slots=True)
class Outcome:
    application_id: str
    application_sha256: str
    task_id: str | None
    revision_id: str | None
    status: str
    policy_binding_sha256: str | None = None
    qualification_receipt_sha256: str | None = None
    # Exact evidence membership, including missing document categories, stays
    # available to the evaluator. Missing evidence is not a reason to omit a case.
    party_document_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()
    workflow_review_receipt_sha256: str | None = None


def _sha(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _refs(refs, *, allow_empty=False):
    if (type(refs) is not tuple or (not refs and not allow_empty) or len(refs) > 100
            or any(type(ref) is not PolicyRef for ref in refs)):
        raise ValueError("Exact nonempty policy reference tuples required")
    values = [ref.model_dump() for ref in refs]
    if len({ref.id for ref in refs}) != len(refs):
        raise ValueError("Duplicate policy identities in one scope")
    return sorted(values, key=lambda ref: ref["id"])


def plan(dataset, reference, snapshots, workflows, qualifications, *, now):
    """Conserve all original rows; no state coverage filters or legacy widening.

    Resolved means consistency of a supplied registry projection only. The caller
    must separately authenticate current reviews/receipts, qualify environment and
    evaluators, enforce admission/budget and recheck revocation before dispatch.
    """
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Explicit aware qualification-check time required")
    sources = []

    def retaining_sources():
        for source in snapshots:
            # derive enforces existing byte/member bounds while consuming, before
            # this population is used for evidence projection.
            yield source
            sources.append(deepcopy(source))

    index = derive(dataset, reference, retaining_sources())
    originals = {source["id"]: source["snapshot"] for source in sources}
    if (type(workflows) is not tuple or type(qualifications) is not tuple
            or len(workflows) > 100 or len(qualifications) > 10000):
        raise ValueError("Bounded registry projections required")
    for workflow in workflows:
        if (type(workflow) is not Workflow or not workflow.task_id or not workflow.revision_id
                or not _sha(workflow.review_receipt_sha256)
                or (workflow.state_policy_set_sha256 is not None
                    and not _sha(workflow.state_policy_set_sha256))):
            raise ValueError("Exact workflow revision and review reference required")
        _refs(workflow.federal_refs)
    for qualification in qualifications:
        if (type(qualification) is not PolicyQualification
                or not _sha(qualification.receipt_sha256)
                or not _sha(qualification.policy_set_sha256)
                or type(qualification.charter_profile) is not str
                or not 1 <= len(qualification.charter_profile) <= 200
                or type(qualification.revoked) is not bool
                or type(qualification.effective_from) is not date
                or type(qualification.effective_until) is not date
                or qualification.effective_from >= qualification.effective_until
                or type(qualification.valid_until) is not datetime
                or qualification.valid_until.tzinfo is None
                or qualification.valid_until.utcoffset() is None):
            raise ValueError("Exact dated policy qualification projection required")
        _refs(qualification.federal_refs)
        if (qualification.state_applicability not in {"applicable", "not_applicable"}
                or qualification.state_applicability == "not_applicable" and qualification.state_refs):
            raise ValueError("Explicit state applicability decision required")
        _refs(qualification.state_refs, allow_empty=qualification.state_applicability == "not_applicable")
    workflow_index, policy_index = {}, {}
    for workflow in workflows:
        workflow_index.setdefault(workflow.product, []).append(workflow)
    for qualification in qualifications:
        policy_index.setdefault((qualification.governing_state, qualification.product), []).append(qualification)
    outcomes = []
    for row in index.rows:
        args = (row.application_id, row.application_sha256)
        if row.blocked_reason:
            outcomes.append(Outcome(*args, None, None, row.blocked_reason))
            continue
        candidates = workflow_index.get(row.product, ())
        if len(candidates) != 1:
            outcomes.append(Outcome(*args, None, None,
                                    "missing_workflow" if not candidates else "ambiguous_workflow"))
            continue
        workflow = candidates[0]
        assigned = (*args, workflow.task_id, workflow.revision_id)
        review = {"workflow_review_receipt_sha256": workflow.review_receipt_sha256}
        try:
            application = Application.model_validate(originals[row.application_id])
        except ValueError:
            outcomes.append(Outcome(*assigned, "invalid_application_evidence", **review))
            continue
        evidence = tuple((party.id, tuple(sorted(document.id for document in application.documents
                                                if document.party_id == party.id)))
                         for party in application.parties)
        policies = [q for q in policy_index.get((row.governing_state, row.product), ())
                    if not q.revoked and now < q.valid_until
                    and q.charter_profile == application.charter_applicability.profile
                    and q.effective_from <= application.assessment_date < q.effective_until
                    and _refs(q.federal_refs) == _refs(workflow.federal_refs)
                    and (workflow.state_policy_set_sha256 is None
                         or workflow.state_policy_set_sha256 == q.policy_set_sha256)]
        if len(policies) != 1:
            outcomes.append(Outcome(*assigned,
                                    "missing_qualified_policy" if not policies else "ambiguous_qualified_policy",
                                    party_document_ids=evidence, **review))
            continue
        selected = policies[0]
        binding = {"federal": _refs(selected.federal_refs), "state": _refs(selected.state_refs,
                   allow_empty=selected.state_applicability == "not_applicable"),
                   "governing_state": row.governing_state, "product": row.product,
                   "assessment_date": application.assessment_date.isoformat(),
                   "charter_profile": selected.charter_profile,
                   "policy_set_sha256": selected.policy_set_sha256,
                   "qualification_receipt_sha256": selected.receipt_sha256}
        outcomes.append(Outcome(*assigned, "resolved_candidate_not_admitted", content_hash(binding),
                                selected.receipt_sha256, evidence, **review))
    expected = {member.id for member in dataset.cases}
    if len(outcomes) != len(expected) or {outcome.application_id for outcome in outcomes} != expected:
        raise ValueError("Original row conservation failed")
    return tuple(outcomes)
