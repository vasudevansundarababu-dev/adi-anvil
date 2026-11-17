"""Private SQL adapter for API-owned evidence. Never accepted native capture.

Materialization commits one intent before enumerating evidence. Unknown outcomes
are not retried or repaired; status reads never perform materialization.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from uuid import UUID

from anvil.db import transaction, uid
from anvil.marketing_capture_evidence import PreparedEvidence, prepare, verify_content
from anvil.marketing_world_quiescence import Quiescence, Scope
from anvil.praxis_generic_contract import canonical, digest


def require_reserved_manifest(connection, claim):
    from anvil.marketing_capture_status import Transport
    from anvil.praxis_template_registry import source_hash

    value = connection.execute(
        "SELECT marketing_runtime.capture_manifest_preflight(%s,%s,%s) AS value",
        (claim.job_id, claim.lease_token, claim.plan_id),
    ).fetchone()["value"]
    if type(value) is not dict or value.get("content_state") != "reserved_no_content":
        raise RuntimeError("marketing_original_api_evidence_slot_required_before_spending")
    original = Scope.model_validate(value["scope"])
    transport = Transport.model_validate(value["status_transport"])
    expiry = datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00"))
    before = expiry.timestamp() - transport.cleanup_reserve_seconds
    if (any(str(getattr(original, field)) != str(getattr(claim, field)) for field in ("project_id", "job_id", "plan_id"))
            or original.lease_sha256 != hashlib.sha256(str(claim.lease_token).encode()).hexdigest()
            or str(UUID(value["manifest_id"])) != value["manifest_id"]
            or transport.source_sha256 != source_hash() or expiry > transport.not_after
            or not datetime.now(timezone.utc).timestamp() < min(before, transport.not_after.timestamp())):
        raise ValueError("Original API evidence reservation scope changed")
    remaining = int(before - datetime.now(timezone.utc).timestamp())
    if remaining < 1:
        raise RuntimeError("Original cleanup reserve denies another SDK request")
    return {"manifest_id": value["manifest_id"], "remaining_seconds": remaining,
            "dispatch_before_utc": datetime.fromtimestamp(before, timezone.utc).isoformat().replace("+00:00", "Z"),
            "capture_accepted": False}


def retain_prompt(connection, plan, intent, text):
    if (type(text) is not str or not 0 < len(text.encode("utf-8")) <= 32768
            or str(intent["project_id"]) != str(plan["project_id"])
            or str(intent["plan_id"]) != str(plan["id"])
            or type(intent["stage_index"]) is not int or not 0 <= intent["stage_index"] < 1000):
        raise ValueError("Original exact bounded Marketing actor prompt required")
    allowed = connection.execute(
        "SELECT marketing_runtime.retain_capture_actor_prompt(%s,%s,%s,%s) AS allowed",
        (plan["id"], intent["stage_index"], text, hashlib.sha256(text.encode("utf-8")).hexdigest()),
    ).fetchone()["allowed"]
    if allowed is not True:
        raise RuntimeError("marketing_prompt_custody_unconfirmed_before_sdk_no_retry")


def require_dispatch_prompt(connection, plan_id, stage_index, call_id, actor_text):
    """Compare the ACTUAL ActorRequest input immediately before SDK execution.

    This denial-only check is in addition to, never a replacement for, existing
    model/key/rights/budget/native/source admission and actual SDK qualification.
    """
    if type(actor_text) is not str or not 0 < len(actor_text.encode("utf-8")) <= 32768:
        raise ValueError("Actual bounded dispatch prompt required")
    value = connection.execute(
        "SELECT marketing_runtime.capture_dispatch_prompt(%s,%s,%s) AS value", (plan_id, stage_index, call_id),
    ).fetchone()["value"]
    pin = hashlib.sha256(actor_text.encode("utf-8")).hexdigest()
    fields = {"plan_id", "call_id", "stage_index", "prompt_sha256", "request_sha256", "prompt_utf8", "dispatch_before_utc"}
    if (type(value) is not dict or set(value) != fields or value["plan_id"] != str(plan_id) or value["call_id"] != str(call_id)
            or type(value["stage_index"]) is not int or value["stage_index"] != stage_index
            or value["prompt_sha256"] != pin or value["request_sha256"] != pin
            or value["prompt_utf8"].encode("utf-8") != actor_text.encode("utf-8")):
        raise RuntimeError("Actual SDK prompt differs from retained original call_no_retry")
    before = datetime.fromisoformat(value["dispatch_before_utc"].replace("Z", "+00:00"))
    if before.tzinfo is None:
        raise ValueError("Original server dispatch deadline required")
    remaining = int((before - datetime.now(timezone.utc)).total_seconds())
    if remaining < 1:
        raise RuntimeError("Original cleanup reserve denies dispatch_no_retry")
    return {"remaining_seconds": remaining, "dispatch_before_utc": before.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "capture_accepted": False}


def _status(connection, claim):
    value = connection.execute(
        "SELECT marketing_runtime.capture_evidence_status(%s,%s,%s) AS value",
        (claim.job_id, claim.lease_token, claim.plan_id),
    ).fetchone()["value"]
    return checked_status(value, claim)


def checked_status(value, claim):
    from anvil.marketing_capture_status import Status

    if type(value) is not dict:
        raise RuntimeError("Original qualified API evidence status unavailable")
    value = Status.model_validate(value).model_dump(mode="json")
    scope = Scope.model_validate(value["scope"])
    if (any(str(getattr(scope, field)) != str(getattr(claim, field)) for field in ("project_id", "job_id", "plan_id"))
            or scope.lease_sha256 != hashlib.sha256(str(claim.lease_token).encode()).hexdigest()
            or value["state"] not in {"reserved_no_content", "materialization_unknown", "ready"}
            or (value["state"] == "ready") != (type(value.get("descriptor")) is dict)
            or value.get("capture_accepted") is not False or value.get("native_qualified") is not False):
        raise ValueError("Exact original API evidence status scope required")
    if hasattr(claim, "value") and any(str(getattr(scope, field)) != str(claim.value[field])
                                      for field in ("world_binding_id", "world_binding_sha256", "episode_id", "generation")):
        raise ValueError("Original world control evidence status scope changed")
    return value


def status(claim):
    with transaction(claim.project_id, claim.actor_id) as connection:
        return _status(connection, claim)


def _normal_context(value):
    if type(value) is not dict:
        raise RuntimeError("Original once-only API evidence context unavailable")
    result = dict(value)
    result["scope"] = Scope.model_validate(result["scope"]).model_dump(mode="json")
    result["quiescence"] = Quiescence.model_validate(result["quiescence"]).model_dump(mode="json")
    for key in ("expires_at", "materialize_before"):
        expiry = datetime.fromisoformat(result[key].replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            raise ValueError("Original server evidence expiry required")
        result[key] = expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return result


def _retain_snapshot(connection, intent, category, identifier, raw):
    allowed = connection.execute(
        "SELECT marketing_runtime.retain_capture_evidence_snapshot(%s,%s,%s,%s,%s) AS allowed",
        (UUID(intent), category, identifier, raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()),
    ).fetchone()["allowed"]
    if allowed is not True:
        raise RuntimeError("API evidence snapshot custody unconfirmed_no_retry")


def _statement_cutoff(connection, context):
    """Bound SQL waits by the original cutoff, never a fresh work allowance."""
    before = datetime.fromisoformat(context["materialize_before"].replace("Z", "+00:00"))
    if before.tzinfo is None:
        raise ValueError("Original server materialization cutoff required")
    remaining_ms = int((before - datetime.now(timezone.utc)).total_seconds() * 1000)
    if remaining_ms < 1:
        raise RuntimeError("Original API materialization cutoff reached_no_retry")
    connection.execute("SELECT set_config('statement_timeout',%s,true)", (str(remaining_ms) + "ms",))


@dataclass(slots=True)
class ScheduledMaterialization:
    """Process-local first-attempt handle, never reconstructed from SQL status."""

    context: dict = field(repr=False)
    lock: object = field(default_factory=Lock, repr=False)
    started: bool = False


def schedule_materialization(claim):
    """Commit only the small intent before acknowledgement; never bulk work."""
    with transaction(claim.project_id, claim.actor_id) as connection:
        observed = _status(connection, claim)
        if observed["state"] == "ready":
            return None  # Existing ready content never schedules more work.
        if observed["state"] != "reserved_no_content":
            raise RuntimeError("API evidence materialization already consumed_unknown_no_retry")
        intent = uid()
        context = _normal_context(connection.execute(
            "SELECT marketing_runtime.begin_capture_evidence(%s,%s,%s,%s,%s) AS value",
            (claim.job_id, claim.lease_token, claim.plan_id, UUID(observed["enrollment_id"]), UUID(intent)),
        ).fetchone()["value"])
    return ScheduledMaterialization(context)


def _materialize_scheduled(claim, scheduled):
    if type(scheduled) is not ScheduledMaterialization:
        raise ValueError("Original process-local scheduled materialization required")
    with scheduled.lock:
        if scheduled.started:
            raise RuntimeError("API evidence callback already consumed_unknown_no_retry")
        scheduled.started = True
    context = scheduled.context
    intent = context["intent_id"]
    # The durable intent above commits before reading/hash work. A failure below
    # leaves it consumed. No new deadline/slot/body/intent may replace it.
    with transaction(claim.project_id, claim.actor_id) as connection:
        _statement_cutoff(connection, context)
        with connection.cursor(name="anvil_evidence_" + uid().replace("-", "")) as cursor:
            cursor.itersize = 1
            cursor.execute("SELECT marketing_runtime.capture_evidence_rows(%s,%s,%s,%s,%s) AS value",
                           (claim.job_id, claim.lease_token, claim.plan_id, UUID(context["enrollment_id"]), UUID(intent)))

            def rows():
                while True:
                    _statement_cutoff(connection, context)
                    row = cursor.fetchone()
                    if row is None:
                        break
                    yield row["value"]

            def retain(*row):
                _statement_cutoff(connection, context)
                _retain_snapshot(connection, intent, *row)

            prepared = prepare(context, rows(), retain_snapshot=retain)
        if type(prepared) is not PreparedEvidence:
            raise RuntimeError("Actual API evidence compilation required")
        _statement_cutoff(connection, context)
        allowed = connection.execute(
            "SELECT marketing_runtime.commit_capture_evidence(%s,%s,%s,%s,%s,%s,%s,%s) AS allowed",
            (claim.job_id, claim.lease_token, claim.plan_id, UUID(context["enrollment_id"]), UUID(intent),
             prepared.manifest.decode("utf-8"), prepared.sha256, canonical(prepared.descriptor).decode("utf-8")),
        ).fetchone()["allowed"]
        if allowed is not True:
            raise RuntimeError("API evidence materialization commit unconfirmed_unknown_no_retry")
    with transaction(claim.project_id, claim.actor_id) as connection:
        _statement_cutoff(connection, context)
        observed = _status(connection, claim)
    if observed["state"] != "ready" or observed["descriptor"] != prepared.descriptor:
        raise RuntimeError("Actual retained API evidence readback differs_unknown_no_retry")
    return observed


def materialize(claim):
    """API-owned synchronous utility; never used in physical cleanup or GET."""
    scheduled = schedule_materialization(claim)
    return status(claim) if scheduled is None else _materialize_scheduled(claim, scheduled)


def materialize_after_response(claim, scheduled):
    """Trusted API background task: no wait/repair/retry in physical cleanup."""
    try:
        _materialize_scheduled(claim, scheduled)
    except Exception as error:
        # Raw rows/committed intent remain the diagnostic authority. Log only
        # bounded identifiers and exception type, never prompt/key/proof bytes.
        logging.getLogger("anvil.capture").warning(
            "API evidence remains unqualified job=%s plan=%s failure=%s",
            str(claim.job_id), str(claim.plan_id), type(error).__name__,
        )


def verify_reference(connection, intake, expected):
    """Only the already-authenticated original intake may reload private bulk.

    expected must come from the actual signed seal. Missing expected hashes are
    never filled from the database. This still cannot verify whole-actor capture.
    """
    if type(expected) is not dict or set(expected) != {"manifest_id", "manifest_sha256", "descriptor_sha256"}:
        raise ValueError("Actual signed seal API evidence reference required")
    value = connection.execute(
        "SELECT marketing_runtime.capture_evidence_for_intake(%s,%s) AS value",
        (UUID(intake["intent_id"]), UUID(expected["manifest_id"])),
    ).fetchone()["value"]
    if (type(value) is not dict or value["enrollment_id"] != intake["enrollment_id"]
            or value["manifest_sha256"] != expected["manifest_sha256"]
            or digest(value["descriptor"]) != expected["descriptor_sha256"]):
        raise ValueError("Signed seal differs from actual issued API evidence")
    actual_quiescence = Quiescence.model_validate(value["quiescence"])
    if (digest(value["quiescence"]) != value["quiescence_stored_sha256"]
            or value["descriptor"]["quiescence_receipt_sha256"] != actual_quiescence.receipt_sha256
            or value["descriptor"]["scope"] != {key: value["quiescence"][key] for key in Scope.model_fields}
            or value["descriptor"]["scope"] != Scope.model_validate(intake["scope"]).model_dump(mode="json")):
        raise ValueError("Actual retained quiescence body/root differs from API content")

    def load(category, identifier):
        original = connection.execute(
            "SELECT marketing_runtime.capture_evidence_original(%s,%s,%s,%s) AS value",
            (UUID(intake["intent_id"]), UUID(expected["manifest_id"]), category, identifier),
        ).fetchone()["value"]
        if type(original) is not dict:
            return None
        if original.get("encoding") == "retained_canonical_utf8":
            return original["canonical_body"].encode("utf-8")
        if original.get("encoding") == "original_immutable_record":
            return canonical(original["body"])
        return None

    return verify_content(value["canonical_body"].encode("utf-8"), value["descriptor"], load)
