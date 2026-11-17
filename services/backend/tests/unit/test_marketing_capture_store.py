"""New raw-store handler controls with fake SQL, no accepted native proof."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_marketing_capture_attestation import header, signing_packet

from anvil.marketing_capture_attestation import verify
from anvil.marketing_capture_store import AuthenticatedProducer, begin, retain, scope
from anvil.praxis_generic_contract import canonical


class Connection:
    def __init__(self, value=None, allowed=True):
        self.value, self.allowed, self.calls = value, allowed, []

    def execute(self, sql, args):
        self.calls.append((sql, args))
        return SimpleNamespace(fetchone=lambda: {"value": self.value, "allowed": self.allowed})


def retained_packet():
    context, value, _, claims, key, now = signing_packet()
    return context, value, verify(header(claims, key), context, now=now)


def test_private_store_retains_wire_and_exact_decoded_strings_without_issuing_capture_reference():
    context, value, attestation = retained_packet()
    context["intent_id"] = str(uuid4())
    wire = canonical(value)
    connection = Connection()
    result = retain(connection, context, wire, transport_complete=True, attestation=attestation)
    args = connection.calls[0][1]
    assert args[2] == wire and json.loads(args[4]) == value["documents"]
    assert result["classification"] == "raw_received_unqualified"
    assert result["accepted_capture_reference"] is None and result["native_qualified"] is False
    assert len(connection.calls) == 1
    assert args[6] == attestation.original_header


@pytest.mark.parametrize("complete,expected", [(True, "invalid_submission"), (False, "transport_unknown")])
def test_invalid_or_partial_original_bytes_remain_private_unqualified_custody(complete, expected):
    context, _, attestation = retained_packet()
    context["intent_id"] = str(uuid4())
    connection = Connection()
    result = retain(connection, context, b'{"incomplete":', transport_complete=complete, attestation=attestation)
    assert connection.calls[0][1][2] == b'{"incomplete":'
    assert json.loads(connection.calls[0][1][4]) == {}
    assert result["classification"] == expected and result["accepted_capture_reference"] is None


def test_unconfirmed_raw_storage_never_retries_or_returns_an_identifier():
    context, value, attestation = retained_packet()
    context["intent_id"] = str(uuid4())
    connection = Connection(allowed=False)
    with pytest.raises(RuntimeError, match="unconfirmed_no_retry"):
        retain(connection, context, canonical(value), transport_complete=True, attestation=attestation)
    assert len(connection.calls) == 1


def test_retained_header_can_be_verified_independently_without_the_api_verdict():
    context, value, attestation = retained_packet()
    context["intent_id"] = str(uuid4())
    connection = Connection()
    retain(connection, context, canonical(value), transport_complete=True, attestation=attestation)
    signed = connection.calls[0][1][6]
    from datetime import datetime, timezone

    independently_verified = verify(signed, context, now=datetime(2026, 11, 14, 18, tzinfo=timezone.utc))
    assert independently_verified.public_key_fingerprint == attestation.public_key_fingerprint


@pytest.mark.parametrize("field", ["enrollment_id", "request_sha256", "operation_nonce"])
def test_other_operation_attestation_is_denied_before_storage(field):
    context, value, attestation = retained_packet()
    context[field] = str(uuid4()) if field == "enrollment_id" else "f" * 64
    connection = Connection()
    with pytest.raises(ValueError, match="original_verified_attestation"):
        retain(connection, context, canonical(value), transport_complete=False, attestation=attestation)
    assert not connection.calls


def test_transport_identity_object_and_actual_enrollment_are_required_before_intake():
    identifier = str(uuid4())
    connection = Connection()
    with pytest.raises(ValueError, match="authenticated_server_transport"):
        scope(connection, {"kind": "linux_peer", "subject": "fake"}, identifier)
    assert connection.calls == []
    identity = AuthenticatedProducer("operator_attested_root_peer_v1", "c" * 64, None)
    assert scope(connection, identity, identifier) is None
    with pytest.raises(RuntimeError, match="exclusive_intent_unavailable"):
        begin(connection, identity, identifier)
