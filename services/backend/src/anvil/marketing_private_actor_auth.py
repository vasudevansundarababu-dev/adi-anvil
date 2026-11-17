"""Fixed own captured-actor POST authentication; no signing/key API.

Only the independently isolated attester may sign its own immutable collector
file. Transport/source/OS qualification and actual artifact custody remain required.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import AwareDatetime, Field, model_validator

from anvil.dataset_export_contract import Model, Sha, json_object
from anvil.marketing_capture_attestation import STOP, _decode, _instant
from anvil.marketing_capture_status import Control
from anvil.marketing_native_wire_bounds import bounded_json
from anvil.marketing_private_grade_auth import CONTROLS as GRADE_CONTROLS
from anvil.marketing_private_grade_auth import PrivateGradeTransport
from anvil.marketing_private_grade_auth import claims as grade_claims
from anvil.praxis_generic_contract import canonical

PATH = "/api/v1/integrations/marketing/native-capture/private-grade-actor"
SCHEMA = "anvil.marketing-private-actor-attestation.v1"
DOMAIN = b"anvil.marketing.private-grade.actor.v1\x00"
CONTROLS = GRADE_CONTROLS | {"captured_actor_custody"}


class PrivateActorTransport(Model):
    schema_version: Literal["anvil.marketing-private-actor-transport-qualification.v1"]
    origin: Literal["https://anvil-qa.adi-labs.ai"]
    path: Literal[PATH]
    method: Literal["POST"]
    api_image_digest: str
    source_sha256: Sha
    ingress_evidence_sha256: Sha
    ca_bundle_sha256: Sha
    not_after: AwareDatetime
    cleanup_reserve_seconds: int = Field(ge=1, le=600)
    wire_limit: int = Field(ge=1, le=1048576)
    controls: dict[str, Control]

    @model_validator(mode="after")
    def original_transport(self):
        if (not re.fullmatch(r"sha256:[a-f0-9]{64}", self.api_image_digest)
                or self.not_after > STOP or set(self.controls) != CONTROLS):
            raise ValueError("Independently qualified original actor transport required")
        return self


class ActorClaims(Model):
    wire_bytes: int = Field(ge=1, le=1048576)
    wire_sha256: Sha
    actor_stop_sha256: Sha
    collection_receipt_sha256: Sha


@dataclass(frozen=True, slots=True)
class VerifiedActor:
    enrollment_id: str
    manifest_id: str
    profile_sha256: str
    wire_bytes: int
    wire_sha256: str
    actor_stop_sha256: str
    collection_receipt_sha256: str
    attestation_sha256: str
    original_header: str = field(repr=False)


def claims(enrollment, artifact):
    """artifact describes the worker's OWN immutable collector file, never arbitrary input."""
    bounded_json(artifact, 4096, max_nodes=100, max_depth=4)
    artifact = ActorClaims.model_validate_json(canonical(artifact)).model_dump(mode="json")
    return grade_claims(enrollment) | {"schema_version": SCHEMA, "method": "POST", "path": PATH,
                                      "purpose": "private_marketing_actor_original",
                                      "body_sha256": artifact["wire_sha256"], **artifact}


def verify(header, enrollment, *, now=None, api_source_sha256=None):
    try:
        bounded_json(enrollment["private_actor_transport"], 32768, max_nodes=1000, max_depth=8)
        transport = PrivateActorTransport.model_validate_json(canonical(enrollment["private_actor_transport"]))
        bounded_json(enrollment["private_grade_transport"], 32768, max_nodes=1000, max_depth=8)
        grade = PrivateGradeTransport.model_validate_json(canonical(enrollment["private_grade_transport"]))
        instant = datetime.now(timezone.utc) if now is None else now
        expiry = _instant(enrollment["expires_at"])
        if (instant.tzinfo is None or expiry > min(transport.not_after, grade.not_after)
                or transport.wire_limit > grade.file_limits["actor-output.json"]
                or any(getattr(grade, key) != getattr(transport, key) for key in
                       ("api_image_digest", "source_sha256", "ingress_evidence_sha256", "ca_bundle_sha256"))
                or not instant < min(expiry - timedelta(seconds=max(transport.cleanup_reserve_seconds, grade.cleanup_reserve_seconds)),
                                     transport.not_after, STOP)
                or api_source_sha256 is not None and transport.source_sha256 != api_source_sha256):
            raise ValueError("original expiry/source")
        if type(header) is not str or not 1 <= len(header) <= 4096 or header.count(".") != 2:
            raise ValueError("bounded original header")
        version, encoded, signature = header.split(".")
        raw, signature = _decode(encoded, 4000), _decode(signature, 100)
        value = json_object(raw)
        artifact = {key: value[key] for key in ActorClaims.model_fields}
        if (version != "v1" or len(raw) > 2048 or len(signature) != 64 or canonical(value) != raw
                or value != claims(enrollment, artifact) or artifact["wire_bytes"] > transport.wire_limit):
            raise ValueError("exact own original artifact claims")
        public = enrollment["public_key_hex"]
        if type(public) is not str or not re.fullmatch(r"[a-f0-9]{64}", public):
            raise ValueError("original verification key")
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(signature, DOMAIN + raw)
        return VerifiedActor(enrollment["enrollment_id"], enrollment["manifest_id"], enrollment["profile_sha256"],
                             artifact["wire_bytes"], artifact["wire_sha256"], artifact["actor_stop_sha256"],
                             artifact["collection_receipt_sha256"], hashlib.sha256(header.encode()).hexdigest(), header)
    except Exception:
        raise ValueError("private_actor_authentication_rejected") from None
