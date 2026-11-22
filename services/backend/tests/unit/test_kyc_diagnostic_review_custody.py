"""Manufactured private-reference custody tests; no model execution or approval."""

import json
from copy import deepcopy
from uuid import uuid4

import pytest

from anvil import diagnostic_producers as producer
from anvil import kyc_expectation_reviews as reviews
from anvil.db import digest


@pytest.fixture
def episode(monkeypatch):
    ids = {key: uuid4() for key in ("project", "trial", "pack", "resolved", "plan")}
    snapshot = {"snapshot": {"id": "synthetic-case", "product": "individual"}}
    snapshot["snapshot_sha256"] = digest(snapshot["snapshot"])
    sealed = {"pack_id": ids["pack"], "application_id": "synthetic-case", "state_sha256": "a" * 64}
    capture = {"trial_id": ids["trial"], "generation": 3}
    task = {"task_id": "synthetic-task", "task_version": "synthetic-revision"}
    paid = {"resolved_task_id": ids["resolved"], "plan_id": ids["plan"]}
    scope = {"task_id": task["task_id"], "revision_id": task["task_version"],
             "resolved_task_id": str(ids["resolved"]), "application_id": sealed["application_id"],
             "snapshot_sha256": snapshot["snapshot_sha256"]}
    frozen = {"subject_id": str(uuid4()), "subject_sha256": "b" * 64,
              "receipt_id": str(uuid4()), "receipt_sha256": "c" * 64,
              "population_sha256": "d" * 64, "private_packet_sha256": "e" * 64, "case_count": 1}
    state = {"paid": paid, "scope": scope, "capture": {"plan_id": ids["plan"]},
             "expected": {"independent_expectation_review": "approved", "expectation_review": frozen,
                          "diagnostic_references": {"K.FILE": {"private_synthetic_sentinel": "hidden-reference"}}}}
    queries, observed = [], []

    class Connection:
        def execute(self, sql, args):
            queries.append((sql, args))
            if "paid_agent_bindings" in sql:
                result = state["paid"]
            elif "product_policy_grader_binding" in sql:
                result = {"value": state["scope"]}
            elif "paid_agent_captures" in sql:
                result = state["capture"]
            else:
                raise AssertionError("A real task must never query legacy expectations")
            return type("Result", (), {"fetchone": lambda self: result})()

    def reviewed(*args, **kwargs):
        observed.append((args, kwargs))
        return state["expected"]

    monkeypatch.setattr("anvil.golden_kyc_native_program.frozen_expectation_review", lambda *_: frozen)
    monkeypatch.setattr(reviews, "reviewed", reviewed)
    return Connection(), ids, sealed, capture, task, snapshot, state, queries, observed, frozen


def read(episode):
    c, ids, sealed, capture, task, snapshot, *_ = episode
    return producer.kyc_reference(c, ids["project"], sealed, capture, task, snapshot)


def test_real_diagnostics_use_exact_frozen_review_and_public_metadata_only(episode):
    references, metadata = read(episode)
    _, ids, sealed, capture, _, snapshot, _, queries, observed, frozen = episode
    assert references["K.FILE"]["private_synthetic_sentinel"] == "hidden-reference"
    assert metadata["status"] == "reviewed" and metadata["review"] == frozen
    assert "hidden-reference" not in json.dumps(metadata)
    assert metadata["sha256"] == digest(frozen)
    args, kwargs = observed[0]
    assert args[1:] == (ids["project"], ids["pack"], sealed["application_id"], snapshot["snapshot"])
    assert kwargs == {"resolved_task_id": ids["resolved"], "frozen_reference": frozen,
                      "trial_id": ids["trial"], "generation": capture["generation"]}
    assert all("banking_private.expectations" not in sql for sql, _ in queries)


@pytest.mark.parametrize("issue", ["review_revoked", "review_expired", "population_changed",
                                    "AV_KYC_FROZEN_EXPECTATION_REVIEW_CHANGED"])
def test_pending_or_changed_review_never_falls_back_to_legacy_answers(episode, issue):
    episode[6]["expected"] = {"independent_expectation_review": "pending", "review_issue": issue,
                              "diagnostic_references": {"K.FILE": {"untrusted": True}}}
    references, metadata = read(episode)
    assert references == {} and metadata["status"] == "pending" and metadata["sha256"] is None
    assert metadata["review_issue"] == issue and metadata["review"] is None


@pytest.mark.parametrize("field", ["task_id", "revision_id", "resolved_task_id", "application_id", "snapshot_sha256"])
def test_wrong_task_case_or_snapshot_is_rejected_before_private_review(episode, field):
    episode[6]["scope"][field] = "foreign"
    with pytest.raises(ValueError, match="task identity"):
        read(episode)
    assert episode[8] == []


def test_unfinalized_capture_cannot_read_reviewed_diagnostic_reference(episode):
    episode[6]["capture"] = None
    with pytest.raises(ValueError, match="finalized"):
        read(episode)
    assert episode[8] == []


def test_optional_diagnostic_references_preserve_old_packet_serialization():
    old = {"intended_decision": "request_information", "criterion_references": {},
           "policy_rule_references": {}, "state_reference": None, "notes": ""}
    assert reviews.Expected.model_validate(old).model_dump(mode="json") == old
    new = old | {"diagnostic_references": {"K.FILE": {"required_documents": ["synthetic-id"]}}}
    assert reviews.Expected.model_validate(new).model_dump(mode="json") == new
    assert digest(new) != digest(old)


def test_changing_diagnostics_changes_salted_private_review_subject():
    from anvil.kyc_expectation_reviews import Packet, PrivateCase, Expected, subject_for

    packet = Packet(schema_version="anvil.kyc-private-expectation-packet.v1", project_id=uuid4(), pack_id=uuid4(),
                    cases=[PrivateCase(application_id="synthetic-case", snapshot_sha256="a" * 64,
                                       salt="b" * 64, expectation=Expected(intended_decision="request_information"))])
    old = subject_for(packet)
    changed = deepcopy(packet)
    changed.cases[0].expectation.diagnostic_references = {"K.FILE": {"private_synthetic_sentinel": "hidden"}}
    new = subject_for(changed)
    assert old.private_packet_sha256 != new.private_packet_sha256
    assert old.cases[0].expectation_sha256 != new.cases[0].expectation_sha256
    assert "hidden" not in json.dumps(new.model_dump(mode="json"))


@pytest.mark.parametrize("legal,subject", [(False, "a" * 64), (True, None), (True, "b" * 64)])
def test_policy_diagnostics_need_exact_current_subject_while_mechanical_references_remain(legal, subject):
    values = {"K.FILE": {"required_documents": ["synthetic-id"]},
              "K.RULEAPPLY": {"policy_subject_sha256": "a" * 64, "private_rule": "synthetic"},
              "K.PURPOSE": {"policy_dependent": True, "policy_subject_sha256": "a" * 64}}
    selected, missing = reviews.diagnostic_references(values, subject, legal)
    assert selected == {"K.FILE": values["K.FILE"]}
    assert missing == ["K.PURPOSE", "K.RULEAPPLY"]


def test_normative_reference_cannot_omit_policy_identity_or_supply_approval_flag():
    values = {"K.CLAUSE": {"approved": True},
              "K.RULEAPPLY": {"policy_subject_sha256": "a" * 64},
              "K.EXTRACT": {"policy_dependent": "false"}}
    selected, missing = reviews.diagnostic_references(values, "a" * 64, True)
    assert selected == {"K.RULEAPPLY": values["K.RULEAPPLY"]}
    assert missing == ["K.CLAUSE", "K.EXTRACT"]


def test_private_unknown_reference_keys_cannot_leak_through_gap_metadata():
    sentinel = "private synthetic answer must never appear in a public target id"
    selected, missing = reviews.diagnostic_references({sentinel: {"policy_dependent": True}}, None, False)
    assert selected == {} and missing == []
    with pytest.raises(ValueError, match="registered KYC diagnostic"):
        reviews.Expected(intended_decision="request_information", diagnostic_references={sentinel: {}})
