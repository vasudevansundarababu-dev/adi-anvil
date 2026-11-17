"""Private original-operation raw intake. No accepted capture is issued here.

Authentication is supplied only by a reviewed server transport adapter, never
the submission. Actual qualification of whole-actor shutdown and sealed capture
is a separate missing boundary; consistency parsing cannot replace it.
"""

import hashlib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from anvil.db import uid
from anvil.marketing_capture_attestation import VerifiedAttestation
from anvil.marketing_capture_submission import WIRE_CAP, Submission, parse, wire_budget
from anvil.marketing_world_quiescence import Scope
from anvil.praxis_generic_contract import canonical


@dataclass(frozen=True, slots=True)
class AuthenticatedProducer:
    kind: Literal["operator_attested_root_peer_v1"]
    subject: str
    account_email: str | None


def scope(connection, identity, enrollment_id):
    if type(identity) is not AuthenticatedProducer or identity.kind != "operator_attested_root_peer_v1":
        raise ValueError("capture_authenticated_server_transport_required")
    return connection.execute(
        "SELECT marketing_runtime.capture_enrollment_scope(%s,%s,%s,%s) AS value",
        (UUID(enrollment_id), identity.kind, identity.subject, identity.account_email),
    ).fetchone()["value"]


def begin(connection, identity, enrollment_id):
    if type(identity) is not AuthenticatedProducer or identity.kind != "operator_attested_root_peer_v1":
        raise ValueError("capture_authenticated_server_transport_required")
    value = connection.execute(
        "SELECT marketing_runtime.begin_capture_intake(%s,%s,%s,%s,%s) AS value",
        (UUID(enrollment_id), identity.kind, identity.subject, identity.account_email, UUID(uid())),
    ).fetchone()["value"]
    return validate_begin(value, enrollment_id)


def validate_begin(value, enrollment_id):
    if type(value) is not dict:
        raise RuntimeError("capture_original_enrollment_or_exclusive_intent_unavailable")
    if value.get("enrollment_id") != enrollment_id:
        raise ValueError("capture_original_enrollment_scope_changed")
    original = Scope.model_validate(value["scope"])
    if (str(original.project_id) != value["project_id"] or str(original.job_id) != value["job_id"]
            or str(original.plan_id) != value["plan_id"]):
        raise ValueError("capture_original_world_scope_changed")
    wire_budget(value)
    return value


def attestation_key(connection, enrollment_id):
    return connection.execute(
        "SELECT marketing_runtime.capture_attestation_key(%s) AS value", (UUID(enrollment_id),),
    ).fetchone()["value"]


def require_sdk_capture_budget(connection, claim):
    """Deny an unretainable capture profile before a provider SDK claim.

    This is an additional denial gate, not native producer qualification.
    The existing exact-image/world/runtime/rights/provider gates still apply.
    """
    value = connection.execute(
        "SELECT marketing_runtime.capture_plan_preflight(%s,%s,%s) AS value",
        (claim.job_id, claim.lease_token, claim.plan_id),
    ).fetchone()["value"]
    if type(value) is not dict:
        raise RuntimeError("marketing_capture_original_profile_required_before_spending")
    original = Scope.model_validate(value["scope"])
    if (str(original.project_id) != str(claim.project_id) or str(original.job_id) != str(claim.job_id)
            or str(original.plan_id) != str(claim.plan_id)
            or original.lease_sha256 != hashlib.sha256(str(claim.lease_token).encode()).hexdigest()
            or any(str(getattr(original, key)) != value[key] for key in ("project_id", "job_id", "plan_id"))):
        raise ValueError("capture_original_sdk_scope_changed")
    return wire_budget(value)


def prepare_retention(context, raw, *, transport_complete, attestation):
    """Complete only the already-held intent; retain failures without repair.

    The private returned ID is diagnostic intake custody, not an opaque accepted
    capture reference and must not be given to the scheduler as successful proof.
    """
    if type(raw) is not bytes or len(raw) > WIRE_CAP or type(transport_complete) is not bool:
        raise ValueError("capture_bounded_original_wire_required")
    if (type(attestation) is not VerifiedAttestation
            or any(getattr(attestation, field) != context[field]
                   for field in ("enrollment_id", "request_sha256", "operation_nonce"))):
        raise ValueError("capture_original_verified_attestation_required")
    parsed: Submission | None = None
    classification = "transport_unknown"
    if transport_complete:
        try:
            parsed = parse(raw, context)
            classification = "raw_received_unqualified"
        except ValueError:
            classification = "invalid_submission"
    documents = {} if parsed is None else {kind: data.decode("utf-8") for kind, data in parsed.documents}
    identifier, pin = uid(), hashlib.sha256(raw).hexdigest()
    parameters = (UUID(context["intent_id"]), UUID(identifier), raw, pin, canonical(documents).decode(), classification,
                  attestation.original_header)
    result = {"private_intake_id": identifier, "raw_sha256": pin, "classification": classification,
              "accepted_capture_reference": None, "native_qualified": False}
    return parameters, result


def retain(connection, context, raw, *, transport_complete, attestation):
    parameters, result = prepare_retention(context, raw, transport_complete=transport_complete, attestation=attestation)
    stored = connection.execute(
        "SELECT marketing_runtime.store_capture_raw_intake(%s,%s,%s,%s,%s,%s,%s) AS allowed", parameters,
    ).fetchone()["allowed"]
    if stored is not True:
        raise RuntimeError("capture_raw_store_unconfirmed_no_retry")
    return result
