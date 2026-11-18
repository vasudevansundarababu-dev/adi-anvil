from datetime import date

import pytest
from pydantic import ValidationError

from anvil.golden_kyc_policy_registry import PolicySet, StateNotApplicablePolicySet
from anvil.praxis_generic_contract import canonical


def policy():
    ref = {"id": "synthetic", "version": "test-v1", "publication_ref": "urn:synthetic:test-only",
           "content_sha256": "a" * 64}
    return {"id": "synthetic-set", "version": "test-v1", "product": "individual", "governing_state": "CA",
            "charter_profile": "synthetic-charter", "federal_refs": [ref], "state_refs": [ref],
            "effective_from": date(2026, 1, 1), "effective_until": date(2027, 1, 1)}


def test_legacy_policy_cannot_use_empty_state_sources_as_an_approval_fallback():
    body = policy() | {"state_refs": []}
    with pytest.raises(ValidationError):
        PolicySet.model_validate(body)


def test_explicit_not_applicable_subject_retains_decision_and_rationale():
    body = policy() | {"state_refs": [], "state_applicability": "not_applicable",
                       "not_applicable_rationale": "Synthetic reviewed scope, not a policy determination."}
    value = StateNotApplicablePolicySet.model_validate(body)
    assert value.state_applicability == "not_applicable" and value.state_refs == []
    from anvil.kyc_policy_reviews import DomainSubject

    subject = DomainSubject.model_validate_json(canonical({"schema_version": "anvil.kyc-policy-domain-subject.v1",
        "template": {"id": "synthetic-template", "version": 8, "sha256": "b" * 64},
        "task_id": "synthetic-task", "revision_id": "r8", "policy_set": value.model_dump(mode="json")}))
    assert subject.model_dump(mode="json")["policy_set"]["state_applicability"] == "not_applicable"


@pytest.mark.parametrize("fault", ["missing_rationale", "nonempty_sources", "wrong_status"])
def test_not_applicable_is_not_a_generic_bypass(fault):
    body = policy() | {"state_refs": [], "state_applicability": "not_applicable",
                       "not_applicable_rationale": "Synthetic reviewed scope only."}
    if fault == "missing_rationale":
        body.pop("not_applicable_rationale")
    elif fault == "nonempty_sources":
        body["state_refs"] = policy()["state_refs"]
    else:
        body["state_applicability"] = "pending"
    with pytest.raises(ValidationError):
        StateNotApplicablePolicySet.model_validate(body)
