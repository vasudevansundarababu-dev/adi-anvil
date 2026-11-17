"""Reusable state tasks reference shared cases; a case is never an authored task.

These pure contracts do not import data, provision an environment, approve legal
policies or authorize a model call. Public manifests contain membership hashes,
not applicant facts or protected expectations.
"""

import hashlib
from typing import Literal

import rfc8785
from pydantic import Field, model_validator

from anvil.dataset_export_contract import Identifier, Model, Sha

State = Literal["CA", "NY", "TX", "FL", "IL"]
STATES = ("CA", "NY", "TX", "FL", "IL")
NAMES = {
    "CA": "California KYC",
    "NY": "New York KYC",
    "TX": "Texas KYC",
    "FL": "Florida KYC",
    "IL": "Illinois KYC",
}


def content_hash(value):
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


class CaseDatasetRef(Model):
    id: Identifier
    version: Identifier
    sha256: Sha
    case_count: int = Field(ge=1, le=10000)


class CaseSelector(Model):
    field: Literal["governing_state"]
    value: State
    case_count: int = Field(ge=1, le=10000)


class CaseMember(Model):
    id: Identifier
    snapshot_sha256: Sha
    governing_state: State


class CaseDataset(Model):
    schema_version: Literal["anvil.application-case-dataset.v1"]
    id: Identifier
    version: Identifier
    case_count: int = Field(ge=5, le=10000)
    cases: list[CaseMember] = Field(min_length=5, max_length=10000)

    @model_validator(mode="after")
    def membership(self):
        ids = [item.id for item in self.cases]
        if len(ids) != self.case_count or ids != sorted(set(ids)):
            raise ValueError("Exact count and sorted unique case IDs required")
        if {item.governing_state for item in self.cases} != set(STATES):
            raise ValueError("The shared Golden dataset must cover all five states")
        return self

    def reference(self):
        return CaseDatasetRef(
            id=self.id,
            version=self.version,
            sha256=content_hash(self.model_dump()),
            case_count=self.case_count,
        )

    def select(self, reference, selector):
        """Verify immutable dataset identity before deriving a state partition."""
        if reference != self.reference():
            raise ValueError("Dataset identity, version, hash or count changed")
        members = [c for c in self.cases if c.governing_state == selector.value]
        if len(members) != selector.case_count:
            raise ValueError("Selector count does not match dataset membership")
        return members


class PolicyRef(Model):
    id: Identifier
    version: Identifier
    content_sha256: Sha
    publication_ref: str = Field(min_length=1, max_length=200)


class StatePolicyRef(PolicyRef):
    state: State


class StateTaskContext(Model):
    """Private-free execution binding derived from a reviewed authored task."""

    schema_version: Literal["anvil.state-kyc-context.v1"]
    task_id: Identifier
    revision_id: Identifier
    caseDataset: CaseDatasetRef
    caseSelector: CaseSelector
    federalPolicies: list[PolicyRef] = Field(min_length=1, max_length=100)
    statePolicies: list[StatePolicyRef] = Field(min_length=1, max_length=100)
    environment: dict
    evaluator_bindings_sha256: Sha

    @model_validator(mode="after")
    def scopes(self):
        if any(p.state != self.caseSelector.value for p in self.statePolicies):
            raise ValueError("Every task policy must match the task's state")
        for refs in (self.federalPolicies, self.statePolicies):
            ids = [p.id for p in refs]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate policy IDs within one scope")
        # Scope is part of identity: federal/state references may use the same
        # citation ID without silently replacing one another.
        if set(self.environment) != {"id", "version"} or any(
            type(v) is not str or not v for v in self.environment.values()
        ):
            raise ValueError("Explicit environment capability and version required")
        return self

    def assignment(self, dataset, application_id):
        members = dataset.select(self.caseDataset, self.caseSelector)
        member = next((m for m in members if m.id == application_id), None)
        if member is None:
            raise ValueError("Application is outside this state task's dataset partition")
        return {
            "schema_version": "anvil.state-kyc-case-assignment.v1",
            "task_id": self.task_id,
            "revision_id": self.revision_id,
            "task_context_sha256": content_hash(self.model_dump()),
            "case_dataset_sha256": self.caseDataset.sha256,
            "application_id": member.id,
            "application_sha256": member.snapshot_sha256,
            "governing_state": member.governing_state,
            "policy_binding_sha256": content_hash(
                {
                    "federal": [p.model_dump() for p in self.federalPolicies],
                    "state": [p.model_dump() for p in self.statePolicies],
                }
            ),
            "environment": self.environment,
            "evaluator_bindings_sha256": self.evaluator_bindings_sha256,
            "legal_acceptance": "requires_independent_review",
            "run_authority": "not_granted",
        }


def from_snapshots(identifier, version, rows):
    """Build only public membership from integrity-checked application snapshots."""
    cases = []
    for row in rows:
        # Existing banking snapshots use the frozen banking digest, distinct
        # from the new public manifest's RFC8785 digest. Do not rehash history.
        from anvil.db import digest

        if digest(row["snapshot"]) != row["snapshot_sha256"]:
            raise ValueError("Application snapshot integrity changed")
        cases.append(
            CaseMember(
                id=row["id"],
                snapshot_sha256=row["snapshot_sha256"],
                governing_state=row["snapshot"]["governing_state"],
            )
        )
    return CaseDataset(
        schema_version="anvil.application-case-dataset.v1",
        id=identifier,
        version=version,
        case_count=len(cases),
        cases=sorted(cases, key=lambda item: item.id),
    )
