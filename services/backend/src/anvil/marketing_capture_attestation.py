"""Verify original-operation operator-enrolled ephemeral public-key claims.

This authenticates a source-reviewed host attester, not physical shutdown. The
API contains no private-key generator, signer or enrollment issuer. Root host
operator trust and actual API/scheduler/candidate isolation require qualification.
"""

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from anvil.dataset_export_contract import json_object
from anvil.marketing_capture_submission import WIRE_CAP, wire_budget
from anvil.praxis_generic_contract import canonical

PATH = "/internal/v1/marketing/native-capture"
AUDIENCE = "https://anvil-qa.adi-labs.ai"
SCHEMA = "anvil.marketing-native-capture-attestation.v1"
CHANNEL = "operator_attested_root_peer_v1"
DOMAIN = b"anvil.marketing.native-capture.attestation.v1\x00"
STOP = datetime(2026, 12, 11, 5, 48, 4, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class VerifiedAttestation:
    enrollment_id: str
    profile_sha256: str
    public_key_fingerprint: str
    wire_bytes: int
    wire_sha256: str
    request_sha256: str
    operation_nonce: str
    original_header: str


def _decode(value, maximum):
    if type(value) is not str or not 1 <= len(value) <= maximum or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("encoding")
    raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode() != value:
        raise ValueError("noncanonical encoding")
    return raw


def _instant(value):
    if type(value) is not str:
        raise ValueError("expiry")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("expiry")
    return result


def verify(header, enrollment, *, now=None):
    """enrollment/public key must be loaded privately, never from HTTP claims."""
    try:
        if type(header) is not str or not 1 <= len(header) <= 4096 or header.count(".") != 2:
            raise ValueError("header")
        version, payload, signature = header.split(".")
        if version != "v1":
            raise ValueError("version")
        raw, signature = _decode(payload, 4000), _decode(signature, 100)
        claims = json_object(raw)
        if len(raw) > 2048 or len(signature) != 64 or canonical(claims) != raw:
            raise ValueError("canonical")
        fields = {"schema_version", "enrollment_id", "request_sha256", "operation_nonce", "audience", "method", "path",
                  "boot_id", "profile_sha256", "producer_qualification_sha256", "expires_at", "wire_bytes", "wire_sha256", "body_schema"}
        if (set(claims) != fields or claims["schema_version"] != SCHEMA
                or claims["audience"] != AUDIENCE or claims["method"] != "POST" or claims["path"] != PATH
                or str(UUID(claims["enrollment_id"])) != claims["enrollment_id"]
                or str(UUID(claims["boot_id"])) != claims["boot_id"]
                or any(claims[key] != enrollment[key] for key in ("enrollment_id", "request_sha256", "operation_nonce",
                                                                 "boot_id", "profile_sha256", "producer_qualification_sha256", "body_schema"))
                or any(type(claims[key]) is not str or not re.fullmatch(r"[a-f0-9]{64}", claims[key])
                       for key in ("request_sha256", "operation_nonce", "profile_sha256", "producer_qualification_sha256", "wire_sha256"))
                or type(claims["wire_bytes"]) is not int or not 1 <= claims["wire_bytes"] <= WIRE_CAP
                or claims["wire_bytes"] > wire_budget(enrollment)["maximum_wire_bytes"]):
            raise ValueError("scope")
        instant = datetime.now(timezone.utc) if now is None else now
        end = _instant(enrollment["expires_at"])
        canonical_end = end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if instant.tzinfo is None or not instant < min(end, STOP) or claims["expires_at"] != canonical_end:
            raise ValueError("original expiry")
        public = enrollment["public_key_hex"]
        if type(public) is not str or not re.fullmatch(r"[a-f0-9]{64}", public):
            raise ValueError("key")
        public = bytes.fromhex(public)
        Ed25519PublicKey.from_public_bytes(public).verify(signature, DOMAIN + raw)
        return VerifiedAttestation(claims["enrollment_id"], claims["profile_sha256"],
                                   hashlib.sha256(public).hexdigest(), claims["wire_bytes"], claims["wire_sha256"],
                                   claims["request_sha256"], claims["operation_nonce"], header)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, AttributeError, binascii.Error, InvalidSignature):
        raise ValueError("capture_operator_attestation_rejected") from None


def matches_wire(attestation, raw):
    if type(attestation) is not VerifiedAttestation or type(raw) is not bytes:
        return False
    return len(raw) == attestation.wire_bytes and hashlib.sha256(raw).hexdigest() == attestation.wire_sha256
