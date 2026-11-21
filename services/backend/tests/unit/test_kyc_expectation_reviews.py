import json
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from anvil import kyc_expectation_reviews as reviews
from anvil.db import digest
from anvil.kyc_policy_expectation_loader import read_packet
from anvil.praxis_generic_contract import canonical


def packet():
    return reviews.Packet(schema_version="anvil.kyc-private-expectation-packet.v1",
        project_id=uuid4(), pack_id=uuid4(), cases=[reviews.PrivateCase(
            application_id=f"GB-{i:03}", snapshot_sha256=str(i) * 64, salt=secrets.token_hex(32),
            expectation=reviews.Expected(intended_decision="request_information")) for i in (1, 2)])


def test_review_metadata_hides_answers_and_uses_independent_salted_hashes():
    source = packet()
    subject = reviews.subject_for(source)
    raw = canonical(subject.model_dump(mode="json"))
    assert b"request_information" not in raw and b'"salt"' not in raw
    assert subject.cases[0].expectation_sha256 != subject.cases[1].expectation_sha256
    assert subject.private_packet_sha256 == digest(source.model_dump(mode="json"))
    assert [c.application_id for c in subject.cases] == ["GB-001", "GB-002"]
    assert reviews.subject_for(source.model_copy(update={"cases": list(reversed(source.cases))})).population_sha256 == subject.population_sha256


@pytest.mark.parametrize("field", ["independent_expectation_review", "legal_qualification", "approved", "reviewer_id"])
def test_private_writer_cannot_declare_an_owner_or_legal_approval(field):
    with pytest.raises(ValidationError):
        reviews.Expected.model_validate({"intended_decision": "request_information", field: "approved"})


def test_duplicate_cases_salts_and_incomplete_population_hash_are_rejected():
    source = packet()
    with pytest.raises(ValidationError):
        reviews.Packet.model_validate(source.model_dump() | {"cases": [source.cases[0], source.cases[0]]})
    same_salt = source.cases[1].model_copy(update={"salt": source.cases[0].salt})
    with pytest.raises(ValidationError):
        reviews.Packet.model_validate(source.model_dump() | {"cases": [source.cases[0], same_salt]})
    with pytest.raises(ValidationError):
        reviews.Subject.model_validate(reviews.subject_for(source).model_dump() | {"population_sha256": "a" * 64})


def test_loader_requires_exact_canonical_owner_only_packet(tmp_path):
    source = packet()
    path = tmp_path / "private-review.json"
    path.write_bytes(canonical(source.model_dump(mode="json")))
    path.chmod(0o600)
    assert read_packet(path) == source
    path.chmod(0o644)
    with pytest.raises(ValueError):
        read_packet(path)
    path.chmod(0o600)
    path.write_text(json.dumps(source.model_dump(mode="json"), indent=2))
    with pytest.raises(ValueError, match="canonical normalized"):
        read_packet(path)
    link = tmp_path / "alias.json"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        read_packet(link)


def approved_fixture(monkeypatch):
    source = packet()
    subject = reviews.subject_for(source)
    identifier, reviewer, receipt_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(hours=1)
    row = {"id": identifier, "project_id": source.project_id, "pack_id": source.pack_id,
           "body_canonical": canonical(subject.model_dump(mode="json")).decode(),
           "content_sha256": digest(subject.model_dump(mode="json"))}
    body = {"schema_version": "anvil.kyc-expectation-review-receipt.v1", "id": str(receipt_id),
            "project_id": str(source.project_id), "subject_id": str(identifier), "reviewer_id": str(reviewer),
            "subject_sha256": row["content_sha256"], "private_packet_sha256": subject.private_packet_sha256,
            "decision": "approved", "expires_at": expiry.isoformat()}
    receipt = {"id": receipt_id, "created_by": reviewer, "body_canonical": canonical(body).decode(),
               "content_sha256": digest(body), "expires_at": expiry, "checked_at": now,
               "reviewer_active": True, "revoked": False}
    def one(c, query, args=()):
        if "kyc_expectation_subjects" in query:
            return row
        if "kyc_expectation_review_receipts" in query:
            return receipt
        raise AssertionError("Unexpected review query")
    monkeypatch.setattr(reviews, "one", one)
    monkeypatch.setattr(reviews, "population", lambda *a: [
        {"id": case.application_id, "snapshot_sha256": case.snapshot_sha256} for case in subject.cases])
    return source, row, receipt, body


def test_current_review_is_bound_to_population_and_real_current_owner(monkeypatch):
    source, row, receipt, body = approved_fixture(monkeypatch)
    value = reviews.current(None, source.project_id, source.pack_id)
    assert value["ready"] and value["case_count"] == 2
    assert "request_information" not in str(value)
    monkeypatch.setattr(reviews, "population", lambda *a: [])
    assert reviews.current(None, source.project_id, source.pack_id)["code"] == "AV_KYC_EXPECTATION_POPULATION_CHANGED"


@pytest.mark.parametrize("mutation", ["revoked", "inactive", "expired", "rejected", "wrong_subject", "wrong_packet", "wrong_reviewer", "wrong_id", "corrupt_hash"])
def test_old_or_changed_approvals_never_become_current(monkeypatch, mutation):
    source, row, receipt, body = approved_fixture(monkeypatch)
    if mutation == "revoked":
        receipt["revoked"] = True
    elif mutation == "inactive":
        receipt["reviewer_active"] = False
    elif mutation == "expired":
        receipt["expires_at"] = receipt["checked_at"] - timedelta(seconds=1)
        body["expires_at"] = receipt["expires_at"].isoformat()
    elif mutation == "rejected":
        body["decision"] = "rejected"
    elif mutation == "wrong_subject":
        body["subject_sha256"] = "a" * 64
    elif mutation == "wrong_packet":
        body["private_packet_sha256"] = "a" * 64
    elif mutation == "wrong_reviewer":
        body["reviewer_id"] = str(uuid4())
    elif mutation == "wrong_id":
        body["id"] = str(uuid4())
    if mutation != "corrupt_hash":
        receipt["content_sha256"] = digest(body)
    else:
        receipt["content_sha256"] = "a" * 64
    receipt["body_canonical"] = canonical(body).decode()
    assert not reviews.current(None, source.project_id, source.pack_id)["ready"]


def test_frozen_review_changes_require_a_new_preparation(monkeypatch):
    source, _, _, _ = approved_fixture(monkeypatch)
    monkeypatch.setattr(reviews, "binding_pack", lambda *a: source.pack_id)
    snapshot = {"execution_data": {"id": "synthetic"}}
    selected = reviews.freeze(None, source.project_id, snapshot)
    assert reviews.binding_gaps(None, source.project_id, snapshot)[0]["code"] == "AV_KYC_EXPECTATION_REVIEW_FROZEN_BINDING_REQUIRED"
    assert not reviews.binding_gaps(None, source.project_id, snapshot | selected)
    changed = deepcopy(selected)
    changed["kyc_expectation_review"]["receipt_id"] = str(uuid4())
    assert reviews.binding_gaps(None, source.project_id, snapshot | changed)


def test_expectation_decision_does_not_grant_legal_review():
    assert not reviews.legal_current(None, uuid4(), None, {}, uuid4())


def test_materialization_accepts_worker_project_shape_and_exact_grader_context(monkeypatch):
    from types import SimpleNamespace

    from anvil import golden_kyc_policy_delivery as delivery
    from anvil import golden_kyc_policy_registry as registry
    from anvil import golden_kyc_source

    project, trial, task = uuid4(), uuid4(), uuid4()
    template = object()
    scope = SimpleNamespace(project_id=project, task_id=str(task), revision_id="r1", template=template,
                            runtime_source_sha256="a" * 64, runtime_image_sha256="b" * 64)
    subject = SimpleNamespace(task_id=str(task), revision_id="r1", template=template,
                              policy_set=SimpleNamespace(model_dump=lambda **kw: {"id": "reviewed"}))
    snapshot = {"id": "GB-001", "product": "individual", "governing_state": "CA",
                "charter_applicability": {"profile": "national"}, "assessment_date": "2026-11-12"}
    value = {"policy_scope": {}, "snapshot": snapshot, "snapshot_sha256": digest(snapshot), "federal_refs": []}
    def one(c, query, args):
        assert "banking.product_policy_grader_binding" in query and args == (trial, 0)
        return {"value": value}
    monkeypatch.setattr(reviews, "one", one)
    monkeypatch.setattr(registry.ProductRegistryScope, "model_validate_json", lambda *args: scope)
    monkeypatch.setattr(golden_kyc_source, "source_hash", lambda: "a" * 64)
    monkeypatch.setenv("ANVIL_RUNTIME_IMAGE_DIGEST", "b" * 64)
    def loaded(c, actual, **request):
        assert actual is scope and request["policy_set_constraint"] == digest({"id": "reviewed"})
        return SimpleNamespace(requirement=None, qualification_record_ids=["qualification"])
    monkeypatch.setattr(registry, "load", loaded)
    monkeypatch.setattr(delivery, "load", lambda c, actual, app, qualification: SimpleNamespace(requirement=None, public={"verified": True}))
    assert reviews.materialization_current(None, str(project), subject, snapshot, trial, 0)
    monkeypatch.setattr(delivery, "load", lambda *args: SimpleNamespace(requirement="revoked", public={}))
    assert not reviews.materialization_current(None, str(project), subject, snapshot, trial, 0)
    assert not reviews.materialization_current(None, str(uuid4()), subject, snapshot, trial, 0)


def test_missing_or_revoked_domain_review_blocks_even_nonstate_policy_override(monkeypatch):
    from anvil import custom_python_grading as grading

    target, source = "policy:synthetic", "b" * 64
    supplied = {target: {"review_status": "approved", "policy_subject_sha256": "a" * 64,
                         "target": target, "source_sha256": source}}
    refs = reviews.policy_references(supplied, "a" * 64, False)
    assert refs[target] == {"review_status": "pending"}
    program = {"criterion": target, "target": target, "policy": {"id": "synthetic"}}
    monkeypatch.setattr(grading, "programs", lambda *args: ({"snapshot": {"source_sha256": source}}, [program]))
    monkeypatch.setenv("ANVIL_CUSTOM_PYTHON_SCORING_ENABLED", "true")
    result = grading.collect_or_queue(None, uuid4(), {}, uuid4(), 0, {}, {
        "independent_expectation_review": "approved", "legal_qualification": "pending",
        "policy_rule_references": refs}, {})
    assert not result["pending"]
    assert result["receipts"][0]["status"] == "unscored"
    assert result["receipts"][0]["reason"] == "source_review_pending"
    assert reviews.policy_references(supplied, "c" * 64, True)[target]["review_status"] == "pending"


def test_paid_admission_uses_actual_execution_group_hash_contract(monkeypatch):
    project, group_id, creator, binding_id, task_group = [uuid4() for _ in range(5)]
    review = {"subject_id": "subject", "receipt_id": "receipt"}
    snapshot = {"kyc_expectation_review": review}
    frozen = {"id": str(binding_id), "task_group_id": str(task_group), "snapshot_sha256": digest(snapshot)}
    group_snapshot = {"preparation": {"project_binding": frozen}}
    group = {"id": group_id, "created_by": creator, "snapshot": group_snapshot,
             "subject_hash": digest({"id": str(group_id), "created_by": str(creator), "snapshot": group_snapshot})}
    def one(c, query, args):
        return group if "workspace_execution_groups" in query else {"snapshot": snapshot, "snapshot_sha256": digest(snapshot)}
    monkeypatch.setattr(reviews, "one", one)
    monkeypatch.setattr(reviews, "binding_pack", lambda *args: "pack")
    monkeypatch.setattr(reviews, "binding_gaps", lambda *args: [])
    plan = {"config": {"workspace_execution_group": str(group_id), "golden_native_binding": {"pack_id": "pack"}}}
    reviews.require_plan(None, project, plan)
    group["subject_hash"] = digest(group_snapshot)
    with pytest.raises(ValueError, match="Exact frozen execution"):
        reviews.require_plan(None, project, plan)
