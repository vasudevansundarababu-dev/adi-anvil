"""Separate signed read-only status contract. No signing or key generation.

Transport qualification must be an independently rooted original operator
record. Shape/hash checks do not establish actual TLS/image/egress/isolation.
The new path is a SOURCE contract, not a verified current serving URL.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import AwareDatetime, Field, field_validator, model_validator

from anvil.dataset_export_contract import Sha, json_object
from anvil.marketing_capture_attestation import AUDIENCE, STOP, _decode, _instant
from anvil.marketing_capture_evidence import READY_DESCRIPTOR_CAP, REFERENCE_BYTES_CAP, _counts
from anvil.marketing_native_wire_bounds import bounded_json
from anvil.marketing_world_quiescence import Scope
from anvil.praxis_generic_contract import canonical, digest
from anvil.schemas import Strict

PATH = "/api/v1/integrations/marketing/native-capture/evidence-status"
SCHEMA = "anvil.marketing-native-capture-status-attestation.v1"
DOMAIN = b"anvil.marketing.native-capture.status.v1\x00"
EMPTY_BODY_SHA256 = hashlib.sha256(b"").hexdigest()
RESPONSE_CAP = 8192
CONTROLS = {"trusted_enrollment_provenance", "current_external_TLS_route", "serving_API_image",
            "root_attester_isolation", "narrow_egress", "cleanup_reserve"}


class Control(Strict):
    status: Literal["passed"]
    evidence_sha256: Sha


class Transport(Strict):
    schema_version: Literal["anvil.marketing-status-transport-qualification.v1"]
    origin: Literal["https://anvil-qa.adi-labs.ai"]
    path: Literal["/api/v1/integrations/marketing/native-capture/evidence-status"]
    method: Literal["GET"]
    api_image_digest: str
    source_sha256: Sha
    ingress_evidence_sha256: Sha
    ca_bundle_sha256: Sha
    not_after: AwareDatetime
    cleanup_reserve_seconds: int = Field(strict=True, ge=1, le=600)
    controls: dict[str, Control]

    @model_validator(mode="after")
    def original_transport(self):
        if (not re.fullmatch(r"sha256:[a-f0-9]{64}", self.api_image_digest)
                or self.not_after > STOP or set(self.controls) != CONTROLS):
            raise ValueError("Original independently qualified status transport required")
        return self


@dataclass(frozen=True, slots=True)
class VerifiedStatus:
    enrollment_id: str
    profile_sha256: str
    public_key_fingerprint: str
    original_header: str = field(repr=False)


def claims(enrollment):
    """Fixed empty GET only; never an arbitrary-body signing oracle."""
    scope = Scope.model_validate(enrollment["scope"])
    expiry = _instant(enrollment["expires_at"]).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"schema_version": SCHEMA, "audience": AUDIENCE, "method": "GET", "path": PATH,
            **{key: enrollment[key] for key in ("enrollment_id", "request_sha256", "operation_nonce", "boot_id",
                                                "profile_sha256", "producer_qualification_sha256")},
            "scope_sha256": digest(scope.model_dump(mode="json")), "expires_at": expiry,
            "body_sha256": EMPTY_BODY_SHA256}


def verify(header, enrollment, *, now=None, api_source_sha256=None):
    try:
        binding = Transport.model_validate(enrollment["status_transport"])
        instant = datetime.now(timezone.utc) if now is None else now
        end = _instant(enrollment["expires_at"])
        before = end - timedelta(seconds=binding.cleanup_reserve_seconds)
        if (instant.tzinfo is None or not instant < min(before, binding.not_after, STOP)
                or end > binding.not_after or api_source_sha256 is not None and binding.source_sha256 != api_source_sha256):
            raise ValueError("original current transport/expiry")
        if type(header) is not str or not 1 <= len(header) <= 4096 or header.count(".") != 2:
            raise ValueError("header")
        version, payload, signature = header.split(".")
        if version != "v1":
            raise ValueError("version")
        raw, signature = _decode(payload, 4000), _decode(signature, 100)
        value = json_object(raw)
        if len(raw) > 2048 or len(signature) != 64 or canonical(value) != raw or value != claims(enrollment):
            raise ValueError("exact original fixed status claims")
        for key in ("enrollment_id", "boot_id"):
            if str(UUID(value[key])) != value[key]:
                raise ValueError("identifier")
        for key in ("request_sha256", "operation_nonce", "profile_sha256", "producer_qualification_sha256"):
            if type(value[key]) is not str or not re.fullmatch(r"[a-f0-9]{64}", value[key]):
                raise ValueError("original pin")
        public = enrollment["public_key_hex"]
        if type(public) is not str or not re.fullmatch(r"[a-f0-9]{64}", public):
            raise ValueError("original public key")
        public = bytes.fromhex(public)
        Ed25519PublicKey.from_public_bytes(public).verify(signature, DOMAIN + raw)
        return VerifiedStatus(value["enrollment_id"], value["profile_sha256"], hashlib.sha256(public).hexdigest(), header)
    except Exception:
        raise ValueError("capture_status_authentication_rejected") from None


READY_FIELDS = {"schema_version", "manifest_id", "enrollment_id", "request_sha256", "operation_nonce", "scope", "expires_at",
                "quiescence_id", "quiescence_receipt_sha256", "fence_epoch", "graph_ledger_sha256", "reconstruction_sha256",
                "category_counts", "entry_count", "raw_bytes_total", "capture_accepted", "model_performance_validated", "manifest_sha256"}


class Status(Strict):
    schema_version: Literal["anvil.marketing-api-evidence-status.v1"]
    scope: Scope
    manifest_id: UUID
    enrollment_id: UUID
    request_sha256: Sha
    operation_nonce: Sha
    state: Literal["reserved_no_content", "materialization_unknown", "ready"]
    descriptor: dict | None
    capture_accepted: Literal[False]
    native_qualified: Literal[False]

    @field_validator("capture_accepted", "native_qualified", mode="before")
    @classmethod
    def no_acceptance(cls, value):
        if value is not False:
            raise ValueError("Status cannot accept or qualify native capture")
        return value

    @model_validator(mode="after")
    def actual_content(self):
        if (self.state == "ready") != (type(self.descriptor) is dict):
            raise ValueError("Only actual issued complete API content has a descriptor")
        if self.descriptor is not None:
            d = self.descriptor
            bounded_json(d, READY_DESCRIPTOR_CAP, max_nodes=3000)
            _counts(d.get("category_counts"))
            if (set(d) != READY_FIELDS or d["schema_version"] != "anvil.marketing-api-evidence-ready.v1"
                    or d["manifest_id"] != str(self.manifest_id) or d["enrollment_id"] != str(self.enrollment_id)
                    or d["request_sha256"] != self.request_sha256 or d["operation_nonce"] != self.operation_nonce
                    or d["scope"] != self.scope.model_dump(mode="json") or d["capture_accepted"] is not False
                    or d["model_performance_validated"] is not False or type(d["entry_count"]) is not int
                    or d["entry_count"] != sum(d["category_counts"].values())
                    or type(d["raw_bytes_total"]) is not int or not 0 < d["raw_bytes_total"] <= REFERENCE_BYTES_CAP
                    or type(d["fence_epoch"]) is not int or d["fence_epoch"] != 1):
                raise ValueError("Exact original complete READY content descriptor required")
            for key in ("manifest_sha256", "quiescence_receipt_sha256", "graph_ledger_sha256", "reconstruction_sha256"):
                if type(d[key]) is not str or not re.fullmatch(r"[a-f0-9]{64}", d[key]):
                    raise ValueError("Actual READY content roots required")
            if str(UUID(d["quiescence_id"])) != d["quiescence_id"]:
                raise ValueError("Original quiescence identity required")
        return self


def validate_response(raw, enrollment, *, now=None):
    if type(raw) is not bytes or not 0 < len(raw) <= RESPONSE_CAP:
        raise ValueError("Bounded exact authenticated API status response required")
    value = json_object(raw)
    if canonical(value) != raw:
        raise ValueError("Exact canonical authenticated API response bytes required")
    status = Status.model_validate(value)
    instant = datetime.now(timezone.utc) if now is None else now
    binding = Transport.model_validate(enrollment["status_transport"])
    end = _instant(enrollment["expires_at"])
    before = end - timedelta(seconds=binding.cleanup_reserve_seconds)
    if instant.tzinfo is None or not instant < min(before, binding.not_after, STOP):
        raise ValueError("Original API status expiry reached")
    if (str(status.enrollment_id) != enrollment["enrollment_id"] or status.request_sha256 != enrollment["request_sha256"]
            or status.operation_nonce != enrollment["operation_nonce"]
            or status.scope.model_dump(mode="json") != Scope.model_validate(enrollment["scope"]).model_dump(mode="json")):
        raise ValueError("API status belongs to another original enrollment/scope")
    if status.descriptor is not None:
        end = _instant(status.descriptor["expires_at"])
        if end != _instant(enrollment["expires_at"]) or not instant < min(end, STOP):
            raise ValueError("Original API status expiry cannot be replaced or extended")
    return status
