"""New real crypto checks over TEST-ONLY in-memory keys and fake enrollments.

No operational key, operator enrollment, kernel observation or capture is made.
"""

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_marketing_capture_submission import packet

from anvil.marketing_capture_attestation import AUDIENCE, DOMAIN, PATH, SCHEMA, matches_wire, verify
from anvil.praxis_generic_contract import canonical


def encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def signing_packet(*, now=None):
    now = datetime(2026, 11, 14, 18, tzinfo=timezone.utc) if now is None else now
    enrollment, value = packet()
    # A synthetic unit-test key only. No private bytes are persisted or logged.
    private = Ed25519PrivateKey.generate()
    enrollment.update(public_key_hex=private.public_key().public_bytes_raw().hex(), boot_id=str(uuid4()),
                      profile_sha256="c" * 64, producer_qualification_sha256="d" * 64,
                      expires_at=(now + timedelta(seconds=60)).isoformat())
    raw = canonical(value)
    claims = {"schema_version": SCHEMA, "audience": AUDIENCE, "method": "POST", "path": PATH,
              **{key: enrollment[key] for key in ("enrollment_id", "request_sha256", "operation_nonce", "boot_id",
                                                  "profile_sha256", "producer_qualification_sha256", "body_schema")},
              "expires_at": (now + timedelta(seconds=60)).isoformat().replace("+00:00", "Z"),
              "wire_bytes": len(raw), "wire_sha256": hashlib.sha256(raw).hexdigest()}
    return enrollment, value, raw, claims, private, now


def header(claims, private, *, domain=DOMAIN):
    raw = canonical(claims)
    return "v1." + encode(raw) + "." + encode(private.sign(domain + raw))


def test_signature_authenticates_exact_original_scope_and_actual_wire_only():
    enrollment, _, raw, claims, private, now = signing_packet()
    result = verify(header(claims, private), enrollment, now=now)
    assert result.enrollment_id == enrollment["enrollment_id"] and matches_wire(result, raw)
    assert not matches_wire(result, raw + b" ")
    assert not matches_wire(result, b"x" + raw[1:])


@pytest.mark.parametrize("field,value", [
    ("audience", "https://other.invalid"), ("method", "GET"), ("path", "/other"),
    ("operation_nonce", "f" * 64), ("request_sha256", "f" * 64), ("profile_sha256", "f" * 64),
    ("producer_qualification_sha256", "f" * 64), ("body_schema", "anvil.marketing-native-capture-submission.v2"),
    ("wire_bytes", True), ("alg", "none"), ("public_key_hex", "f" * 64),
])
def test_valid_signature_cannot_change_binding_or_negotiate_keys_or_algorithm(field, value):
    enrollment, _, _, claims, private, now = signing_packet()
    claims[field] = value
    with pytest.raises(ValueError, match="^capture_operator_attestation_rejected$"):
        verify(header(claims, private), enrollment, now=now)


def test_other_key_and_wrong_signature_domain_cannot_impersonate_enrolled_attester():
    enrollment, _, _, claims, private, now = signing_packet()
    other = Ed25519PrivateKey.generate()
    for signed in (header(claims, other), header(claims, private, domain=b"")):
        with pytest.raises(ValueError, match="attestation_rejected"):
            verify(signed, enrollment, now=now)


def test_original_server_expiry_cannot_be_extended_or_reformatted_as_freshness():
    enrollment, _, _, claims, private, now = signing_packet()
    with pytest.raises(ValueError):
        verify(header(claims, private), enrollment, now=now + timedelta(seconds=60))
    claims["expires_at"] = (now + timedelta(seconds=61)).isoformat().replace("+00:00", "Z")
    with pytest.raises(ValueError):
        verify(header(claims, private), enrollment, now=now)
    claims["expires_at"] = enrollment["expires_at"]  # Same instant, noncanonical representation.
    with pytest.raises(ValueError):
        verify(header(claims, private), enrollment, now=now)


def test_header_version_padding_and_unsigned_input_cannot_select_another_protocol():
    enrollment, _, _, claims, private, now = signing_packet()
    valid = header(claims, private)
    for invalid in (valid.replace("v1.", "v2.", 1), valid + "=", canonical(claims).decode()):
        with pytest.raises(ValueError):
            verify(invalid, enrollment, now=now)
