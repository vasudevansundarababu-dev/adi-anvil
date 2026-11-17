"""Distinct fixed private-grade GET authentication, never a signing interface.

Original enrollment/manifest/transport come from protected API/qualified operator
custody, not unverified claims. Status-domain signatures do not authorize this
path. No signer, private key, login or live transport is created here.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import AwareDatetime, Field, model_validator

from anvil.dataset_export_contract import Model, Sha, json_object
from anvil.marketing_capture_attestation import AUDIENCE, STOP, _decode, _instant
from anvil.marketing_capture_status import CONTROLS as STATUS_CONTROLS
from anvil.marketing_capture_status import Control
from anvil.marketing_capture_verifier import Identity
from anvil.marketing_native_wire_bounds import bounded_json
from anvil.marketing_world_quiescence import Scope
from anvil.praxis_generic_contract import canonical, digest

PATH = "/api/v1/integrations/marketing/native-capture/private-grade-input"
SCHEMA = "anvil.marketing-private-grade-attestation.v1"
DOMAIN = b"anvil.marketing.private-grade.input.v1\x00"
EMPTY_BODY_SHA256 = hashlib.sha256(b"").hexdigest()
RESPONSE_CAP = 1048576
FILES = frozenset({"verifier-input.json", "actor-output.json", "private-evidence.json", "evaluation-profile.json"})
CONTROLS = STATUS_CONTROLS | {"protected_input_isolation", "private_mapping_profile",
                            "fixed_private_process", "actual_original_evidence"}


class PrivateGradeTransport(Model):
    schema_version: Literal["anvil.marketing-private-grade-transport-qualification.v1"]
    origin: Literal["https://anvil-qa.adi-labs.ai"]
    path: Literal[PATH]
    method: Literal["GET"]
    api_image_digest: str
    source_sha256: Sha
    ingress_evidence_sha256: Sha
    ca_bundle_sha256: Sha
    not_after: AwareDatetime
    cleanup_reserve_seconds: int = Field(ge=1, le=600)
    response_limit: Literal[RESPONSE_CAP]
    file_limits: dict[str, int] = Field(min_length=4, max_length=4)
    reply_metadata_limit: int = Field(ge=1, le=32768)
    controls: dict[str, Control]

    @model_validator(mode="after")
    def original_bounded_transport(self):
        if (not re.fullmatch(r"sha256:[a-f0-9]{64}", self.api_image_digest) or self.not_after > STOP
                or set(self.controls) != CONTROLS or set(self.file_limits) != FILES
                or any(type(n) is not int or not 0 < n <= 1048576 for n in self.file_limits.values())
                or 4096 + 2 * sum(self.file_limits.values()) + 2 * self.reply_metadata_limit > self.response_limit):
            raise ValueError("Original qualified private-grade transport and whole-frame bounds required")
        return self


@dataclass(frozen=True, slots=True)
class VerifiedPrivateGrade:
    enrollment_id: str
    profile_sha256: str
    manifest_id: str
    descriptor_sha256: str
    public_key_fingerprint: str
    original_header: str = field(repr=False)


def claims(enrollment):
    """Fixed own issued manifest/descriptor only; no caller-selected path/body."""
    scope = Scope.model_validate(enrollment["scope"])
    bounded_json(enrollment["identity"], 4096, max_nodes=100, max_depth=4)
    identity = Identity.model_validate_json(canonical(enrollment["identity"]))
    if (identity.model_dump(mode="json") != enrollment["identity"] or identity.job_id != scope.job_id
            or identity.request_sha256 != enrollment["request_sha256"]
            or identity.operation_nonce != enrollment["operation_nonce"]):
        raise ValueError("Original independently observed framework identity required")
    expiry = _instant(enrollment["expires_at"]).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"schema_version": SCHEMA, "audience": AUDIENCE, "method": "GET", "path": PATH,
            "purpose": "private_marketing_verifier_inputs",
            **{key: enrollment[key] for key in ("enrollment_id", "request_sha256", "operation_nonce", "boot_id",
                                                "profile_sha256", "producer_qualification_sha256", "manifest_id")},
            "scope_sha256": digest(scope.model_dump(mode="json")),
            "framework_identity_sha256": digest(enrollment["identity"]),
            "descriptor_sha256": digest(enrollment["descriptor"]), "expires_at": expiry,
            "body_sha256": EMPTY_BODY_SHA256}


def verify(header, enrollment, *, now=None, api_source_sha256=None):
    try:
        bounded_json(enrollment["private_grade_transport"], 32768, max_nodes=1000, max_depth=8)
        transport = PrivateGradeTransport.model_validate_json(canonical(enrollment["private_grade_transport"]))
        instant = datetime.now(timezone.utc) if now is None else now
        expiry = _instant(enrollment["expires_at"])
        if (instant.tzinfo is None or expiry > transport.not_after
                or not instant < min(expiry - timedelta(seconds=transport.cleanup_reserve_seconds), transport.not_after, STOP)
                or api_source_sha256 is not None and transport.source_sha256 != api_source_sha256):
            raise ValueError("original expiry/source")
        if type(header) is not str or not 1 <= len(header) <= 4096 or header.count(".") != 2:
            raise ValueError("bounded original header")
        version, encoded, signature = header.split(".")
        raw, signature = _decode(encoded, 4000), _decode(signature, 100)
        value = json_object(raw)
        if version != "v1" or len(raw) > 2048 or len(signature) != 64 or canonical(value) != raw or value != claims(enrollment):
            raise ValueError("exact own private-grade claims")
        for key in ("enrollment_id", "boot_id", "manifest_id"):
            if str(UUID(value[key])) != value[key]:
                raise ValueError("original UUID")
        for key in ("request_sha256", "operation_nonce", "profile_sha256", "producer_qualification_sha256"):
            if type(value[key]) is not str or not re.fullmatch(r"[a-f0-9]{64}", value[key]):
                raise ValueError("original pin")
        public = enrollment["public_key_hex"]
        if type(public) is not str or not re.fullmatch(r"[a-f0-9]{64}", public):
            raise ValueError("original public verification key")
        public = bytes.fromhex(public)
        Ed25519PublicKey.from_public_bytes(public).verify(signature, DOMAIN + raw)
        return VerifiedPrivateGrade(value["enrollment_id"], value["profile_sha256"], value["manifest_id"],
                                    value["descriptor_sha256"], hashlib.sha256(public).hexdigest(), header)
    except Exception:
        raise ValueError("private_grade_authentication_rejected") from None
