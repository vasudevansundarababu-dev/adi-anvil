"""Public-only operator handshake. No key generation, signing or self-enrollment.

Public pipe data is not OS identity. The SQL issuer independently requires the
original qualified private peer-binding record; this parser cannot create it.
"""

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from anvil.dataset_export_contract import Sha, json_object
from anvil.marketing_capture_attestation import STOP
from anvil.marketing_capture_status import Transport
from anvil.marketing_capture_submission import wire_budget
from anvil.marketing_native_wire_bounds import bounded_json, remaining
from anvil.marketing_world_quiescence import Scope
from anvil.praxis_generic_contract import canonical, digest
from anvil.schemas import Strict

PUBLIC_READY_CAP = 2048
ENROLL_SQL = "SELECT marketing_runtime.enroll_attester_public_key(%s,%s) AS value"
COMMITTED_SQL = "SELECT marketing_runtime.committed_attester_enrollment(%s,%s,%s) AS value"
PRIVATE_ACTOR_SQL = "SELECT marketing_runtime.private_actor_slot_preflight(%s,%s,%s) AS value"


class PublicReady(Strict):
    schema_version: Literal["anvil.marketing-attester-public-ready.v1"]
    peer_binding_id: UUID
    request_sha256: Sha
    operation_nonce: Sha
    boot_id: UUID
    profile_sha256: Sha
    public_key_hex: Sha
    public_key_fingerprint_sha256: Sha

    @model_validator(mode="after")
    def public_fingerprint(self):
        if hashlib.sha256(bytes.fromhex(self.public_key_hex)).hexdigest() != self.public_key_fingerprint_sha256:
            raise ValueError("Exact independent public-key fingerprint required")
        return self


class OriginalBinding(Strict):
    """Original operator facts, never a decoded child approval/identity claim."""

    peer_binding_id: UUID
    enrollment_id: UUID
    request_sha256: Sha
    operation_nonce: Sha
    boot_id: UUID
    profile_sha256: Sha
    producer_qualification_sha256: Sha
    status_transport_sha256: Sha
    scope: Scope
    expires_at: AwareDatetime


class EnrollmentReceipt(Strict):
    enrollment_id: UUID
    manifest_id: UUID
    request_sha256: Sha
    operation_nonce: Sha
    public_key_hex: Sha
    boot_id: UUID
    profile_sha256: Sha
    producer_qualification_sha256: Sha
    scope: Scope
    expires_at: AwareDatetime
    body_schema: Literal["anvil.marketing-native-capture-submission.v2"]
    document_limits: dict[str, int]
    wire_limit: int = Field(strict=True, ge=1, le=1048576)
    status_transport: Transport
    capture_accepted: Literal[False]
    run_authority: Literal["not_granted"]


class PrivateActorCapacity(Strict):
    schema_version: Literal["anvil.marketing-private-actor-capacity.v1"]
    id: UUID
    enrollment_id: UUID
    scope: Scope
    maximum_bytes: int = Field(strict=True, ge=1, le=1048576)
    producer_qualification_sha256: Sha
    expires_at: AwareDatetime
    capture_accepted: Literal[False]
    run_authority: Literal["not_granted"]


class CommittedEnrollment(Strict):
    schema_version: Literal["anvil.marketing-committed-attester-enrollment.v1"]
    peer_binding_id: UUID
    peer_receipt_sha256: Sha
    enrollment: EnrollmentReceipt
    observation: Literal["committed_registry_state_only"]
    capture_accepted: Literal[False]
    run_authority: Literal["not_granted"]
    private_actor_slot: PrivateActorCapacity | None = None


def freeze_original(original):
    """Snapshot retained operator facts before awaits; no authenticity by type."""
    if type(original) is not OriginalBinding:
        raise ValueError("Original independent operator binding required")
    value = original.model_dump(mode="json")
    bounded_json(value, 16384, max_nodes=1000, max_depth=8)
    return OriginalBinding.model_validate_json(canonical(value))


def parse_public_ready(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= PUBLIC_READY_CAP:
        raise ValueError("Bounded original public-ready bytes required")
    try:
        value = json_object(raw)
        if canonical(value) != raw:
            raise ValueError("canonical")
        ready = PublicReady.model_validate_json(raw)
        if canonical(ready.model_dump(mode="json")) != raw:
            raise ValueError("representation")
        return ready
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("Original public-ready message rejected") from None


def check_original(ready, original):
    if type(ready) is not PublicReady or type(original) is not OriginalBinding:
        raise ValueError("Original operator binding and public-ready types required")
    if any(getattr(ready, key) != getattr(original, key) for key in
           ("peer_binding_id", "request_sha256", "operation_nonce", "boot_id", "profile_sha256")):
        raise ValueError("Public-ready original operation binding changed")


def validate_receipt(value, original, ready, *, now=None):
    check_original(ready, original)
    if type(value) is not dict:
        raise RuntimeError("Original independently qualified peer enrollment unavailable; no retry")
    try:
        if value.get("capture_accepted") is not False:
            raise ValueError("flags")
        receipt = EnrollmentReceipt.model_validate_json(canonical(value))
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("Original enrollment receipt rejected") from None
    if (any(getattr(receipt, key) != getattr(original, key) for key in
            ("enrollment_id", "request_sha256", "operation_nonce", "boot_id", "profile_sha256",
             "producer_qualification_sha256", "scope", "expires_at"))
            or receipt.public_key_hex != ready.public_key_hex
            or digest(value["status_transport"]) != original.status_transport_sha256):
        raise ValueError("Original public-key enrollment readback changed")
    instant = datetime.now(timezone.utc) if now is None else now
    if (instant.tzinfo is None or receipt.expires_at > min(STOP, receipt.status_transport.not_after)
            or (receipt.expires_at - instant).total_seconds() <= receipt.status_transport.cleanup_reserve_seconds):
        raise ValueError("Original enrollment expiry or cleanup reserve reached")
    wire_budget(value)
    return receipt


async def register_public_ready(connection, raw, original, *, absolute_deadline):
    """One SQL call in caller's original bounded OPERATOR transaction.

    The caller must commit only after this readback succeeds; any exception means
    rollback/Unknown, no same-operation repair or retry. The ordinary API/SDK roles
    cannot execute this SQL function. No connection/credential is created here.
    """
    ready = parse_public_ready(raw)
    original = freeze_original(original)
    check_original(ready, original)
    remaining(absolute_deadline)
    remaining(connection.capture_deadline)
    hard = min(absolute_deadline, connection.capture_deadline)
    connection.capture_deadline = hard
    async with asyncio.timeout(remaining(hard)):
        cursor = await connection.execute(ENROLL_SQL, (ready.peer_binding_id, ready.public_key_hex))
        row = await cursor.fetchone()
        receipt = validate_receipt(row["value"] if row else None, original, ready)
        remaining(hard)
        return receipt


async def observe_committed(original, ready, peer_receipt_sha256, job, *, absolute_deadline,
                            private_actor_maximum_bytes=None):
    """Original graph child's separate read, never registrar response/flag repair.

    Call only in the original enrollment phase. A registrar Unknown/cancel/failed
    state aborts that operation; this is not an ambiguous-write recovery loop.
    The caller retains the same QualifiedWorld and all normal SDK admission gates.
    """
    from pydantic import TypeAdapter

    from anvil.marketing_enrollment_read_database import transaction

    check_original(ready, original)
    if (private_actor_maximum_bytes is not None
            and (type(private_actor_maximum_bytes) is not int or not 0 < private_actor_maximum_bytes <= 1048576)):
        raise ValueError("Original qualified private actor storage bound required")
    original = freeze_original(original)
    ready_value = ready.model_dump(mode="json")
    bounded_json(ready_value, PUBLIC_READY_CAP, max_nodes=100, max_depth=4)
    ready = parse_public_ready(canonical(ready_value))
    check_original(ready, original)
    TypeAdapter(Sha).validate_python(peer_receipt_sha256, strict=True)
    expected = original.scope
    job_id, plan_id, project_id = (str(job[key]) for key in ("id", "plan_id", "project_id"))
    lease, actor = UUID(str(job["lease_token"])), UUID(str(job["actor_id"]))
    if ((job_id, plan_id, project_id) != (str(expected.job_id), str(expected.plan_id), str(expected.project_id))
            or hashlib.sha256(str(lease).encode()).hexdigest() != expected.lease_sha256):
        raise ValueError("Committed enrollment original job/lease/scope changed")
    remaining(absolute_deadline)
    async with transaction(expected.project_id, actor, absolute_deadline=absolute_deadline) as connection:
        row = await (await connection.execute(COMMITTED_SQL,
                                              (expected.job_id, lease, expected.plan_id))).fetchone()
        value = row["value"] if row else None
        if type(value) is not dict:
            raise RuntimeError("Original committed attester enrollment unavailable; no retry")
        bounded_json(value, 32768, max_nodes=4000, max_depth=8)
        if value.get("capture_accepted") is not False:
            raise ValueError("Committed lookup grants no capture authority")
        try:
            observed = CommittedEnrollment.model_validate_json(canonical(value))
        except (ValueError, TypeError, UnicodeError):
            raise ValueError("Original committed enrollment receipt rejected") from None
        if (observed.peer_binding_id != original.peer_binding_id
                or observed.peer_receipt_sha256 != peer_receipt_sha256):
            raise ValueError("Independent original peer binding changed")
        validate_receipt(value["enrollment"], original, ready)
        if private_actor_maximum_bytes is not None:
            slot_row = await (await connection.execute(PRIVATE_ACTOR_SQL, (expected.job_id, lease, expected.plan_id))).fetchone()
            slot_value = slot_row["value"] if slot_row else None
            if type(slot_value) is not dict or slot_value.get("capture_accepted") is not False:
                raise RuntimeError("Original private actor capacity unavailable before provider work")
            bounded_json(slot_value, 8192, max_nodes=1000, max_depth=8)
            slot = PrivateActorCapacity.model_validate_json(canonical(slot_value))
            if (slot.enrollment_id != original.enrollment_id or slot.scope != expected
                    or slot.maximum_bytes != private_actor_maximum_bytes
                    or slot.producer_qualification_sha256 != original.producer_qualification_sha256
                    or slot.expires_at != original.expires_at):
                raise ValueError("Original private actor reservation changed")
            observed.private_actor_slot = slot
        remaining(absolute_deadline)
    # Return only after the separate read transaction/connection closes within
    # the SAME original cutoff. A read is still not future dispatch authority.
    remaining(absolute_deadline)
    return observed
