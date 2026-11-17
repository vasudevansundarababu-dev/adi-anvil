"""New transport negatives; manufactured proof bytes confer NO native authority."""

from uuid import uuid4

import pytest

from anvil.marketing_capture_submission import KINDS, SCHEMA, WIRE_CAP, parse
from anvil.praxis_generic_contract import canonical


def packet():
    enrollment = {"enrollment_id": str(uuid4()), "request_sha256": "a" * 64, "operation_nonce": "b" * 64,
                  "body_schema": SCHEMA, "wire_limit": WIRE_CAP,
                  "document_limits": {kind: 4096 for kind in KINDS}}
    documents = {kind: canonical({"manufactured": kind}).decode() for kind in KINDS}
    value = {"schema_version": SCHEMA, **{k: enrollment[k] for k in ("enrollment_id", "request_sha256", "operation_nonce")},
             "documents": documents}
    return enrollment, value


def test_raw_wire_and_each_original_document_are_retained_without_repr_disclosure():
    enrollment, value = packet()
    value["documents"]["actor_output"] = canonical({"private_text": "Private résumé 🦉"}).decode()
    raw = canonical(value)
    parsed = parse(raw, enrollment)
    assert parsed.wire == raw
    assert dict(parsed.documents) == {kind: text.encode() for kind, text in value["documents"].items()}
    assert "Private" not in repr(parsed)


def test_wire_cap_applies_before_invalid_json_parse():
    enrollment, _ = packet()
    with pytest.raises(ValueError, match="capture_wire_bound"):
        parse(b"x" * (WIRE_CAP + 1), enrollment)


def test_per_kind_limit_is_independent_original_enrollment_not_payload_override():
    enrollment, value = packet()
    enrollment["document_limits"]["actor_output"] = 16
    value["documents"]["actor_output"] = canonical({"candidate": "x" * 30}).decode()
    with pytest.raises(ValueError, match="capture_submission_invalid"):
        parse(canonical(value), enrollment)


@pytest.mark.parametrize("change", ["nonce", "request", "enrollment", "missing_whole_actor", "unknown_kind"])
def test_changed_operation_or_incomplete_proof_kind_set_denies(change):
    enrollment, value = packet()
    if change == "nonce":
        value["operation_nonce"] = "c" * 64
    elif change == "request":
        value["request_sha256"] = "c" * 64
    elif change == "enrollment":
        value["enrollment_id"] = str(uuid4())
    elif change == "missing_whole_actor":
        value["documents"].pop("whole_actor_shutdown")
    else:
        value["documents"]["arbitrary_url"] = "{}"
    with pytest.raises(ValueError, match="capture_submission_invalid"):
        parse(canonical(value), enrollment)


def test_duplicate_outer_and_inner_keys_and_noncanonical_document_deny_without_echo():
    enrollment, value = packet()
    raw = canonical(value)
    duplicate = b'{"schema_version":"shadow",' + raw[1:]
    with pytest.raises(ValueError, match="capture_submission_invalid"):
        parse(duplicate, enrollment)
    for document in ['{"private":"one","private":"two"}', '{ "private": "one" }']:
        value["documents"]["actor_output"] = document
        with pytest.raises(ValueError, match="^capture_submission_invalid_or_scope_changed$"):
            parse(canonical(value), enrollment)
