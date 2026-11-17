"""Real producer encoder/API decoder parity, not real physical evidence fit."""

import hashlib
from pathlib import Path

import pytest
from test_marketing_capture_submission import packet

from anvil import marketing_native_capture_budget as producer
from anvil.marketing_capture_submission import parse, wire_budget
from anvil.praxis_generic_contract import canonical


def source():
    # Exact Harbor source primitive nomination; not an operating/native pin.
    assert hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest() == "e87b928e7750f13129e24a6beacbd20ef003f42bf242aec14abb9c15ed9aa8c8"
    enrollment, _ = packet()
    enrollment.update(body_schema=producer.SCHEMA, document_limits=dict(producer.KIND_LIMITS), wire_limit=110592)
    budget = producer.prepare_v2_metadata_budget(enrollment["enrollment_id"], enrollment["request_sha256"],
                                                enrollment["operation_nonce"], plan_receipt_bytes=enrollment["wire_limit"])
    return enrollment, budget


def test_real_encoder_and_decoder_preserve_six_original_metadata_documents_exactly():
    enrollment, budget = source()
    documents = {kind: canonical({"unqualified_software_fixture": kind, "native_qualified": False})
                 for kind, _ in producer.KIND_LIMITS}
    raw = producer.encode_v2_metadata(budget, documents)
    parsed = parse(raw, enrollment)
    assert dict(parsed.documents) == documents and parsed.body_schema == producer.SCHEMA
    assert len(raw) <= budget.wire_upper_bound == wire_budget(enrollment)["maximum_wire_bytes"] <= 110592


def test_real_v2_upper_bound_requires_original_plan_capacity_even_when_sample_is_small():
    enrollment, budget = source()
    enrollment["wire_limit"] = budget.wire_upper_bound - 1
    with pytest.raises(ValueError, match="cannot_fit_before_sdk"):
        wire_budget(enrollment)


def test_v1_documents_cannot_be_silently_reinterpreted_as_v2_metadata():
    enrollment, _ = source()
    _, old = packet()
    old.update(enrollment_id=enrollment["enrollment_id"], request_sha256=enrollment["request_sha256"], operation_nonce=enrollment["operation_nonce"])
    with pytest.raises(ValueError, match="capture_submission_invalid"):
        parse(canonical(old), enrollment)


def test_producer_refuses_missing_kind_and_oversized_complete_document_instead_of_truncating():
    _, budget = source()
    documents = {kind: b"{}" for kind, _ in producer.KIND_LIMITS}
    documents.pop("capture_seal")
    with pytest.raises(ValueError):
        producer.encode_v2_metadata(budget, documents)
    documents["capture_seal"] = canonical({"too_large": "x" * 8192})
    with pytest.raises(ValueError, match="kind_capacity"):
        producer.encode_v2_metadata(budget, documents)
