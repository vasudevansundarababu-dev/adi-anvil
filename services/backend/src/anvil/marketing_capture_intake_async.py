"""Private diagnostic raw custody, async only, never accepted native capture."""

from time import monotonic
from uuid import UUID

from anvil.dataset_export_contract import json_object
from anvil.marketing_capture_attestation import STOP, _decode, _instant
from anvil.marketing_capture_evidence_async import one
from anvil.marketing_capture_store import AuthenticatedProducer, prepare_retention, validate_begin


def claimed_deadline(header):
    """Denial-only claimed cutoff; actual key/signature/expiry must match later."""
    from datetime import datetime, timezone

    if type(header) is not str or len(header) > 4096 or header.count(".") != 2:
        raise ValueError("Bounded original capture signature required")
    claimed = json_object(_decode(header.split(".")[1], 4000))
    return monotonic() + (min(_instant(claimed["expires_at"]), STOP) - datetime.now(timezone.utc)).total_seconds()


async def key(connection, enrollment_id):
    return (await one(connection, "SELECT marketing_runtime.capture_attestation_key(%s) AS value",
                      (UUID(enrollment_id),)))["value"]


def _identity(identity):
    if type(identity) is not AuthenticatedProducer or identity.kind != "operator_attested_root_peer_v1":
        raise ValueError("capture_authenticated_server_transport_required")


async def scope(connection, identity, enrollment_id):
    _identity(identity)
    return (await one(connection, "SELECT marketing_runtime.capture_enrollment_scope(%s,%s,%s,%s) AS value",
                      (UUID(enrollment_id), identity.kind, identity.subject, identity.account_email)))["value"]


async def begin(connection, identity, enrollment_id):
    _identity(identity)
    from anvil.db import uid

    value = (await one(connection, "SELECT marketing_runtime.begin_capture_intake(%s,%s,%s,%s,%s) AS value",
                       (UUID(enrollment_id), identity.kind, identity.subject, identity.account_email, UUID(uid()))))["value"]
    return validate_begin(value, enrollment_id)


async def retain(connection, context, raw, *, transport_complete, attestation):
    parameters, result = prepare_retention(context, raw, transport_complete=transport_complete, attestation=attestation)
    stored = (await one(connection,
                        "SELECT marketing_runtime.store_capture_raw_intake(%s,%s,%s,%s,%s,%s,%s) AS allowed", parameters))["allowed"]
    if stored is not True:
        raise RuntimeError("capture_raw_store_unconfirmed_no_retry")
    return result
