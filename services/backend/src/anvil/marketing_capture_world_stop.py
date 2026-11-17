"""Capture-specific async fence/drain. Physical shutdown remains independent."""

import hashlib
import logging
from datetime import datetime, timezone
from time import monotonic

from anvil.marketing_capture_attestation import STOP
from anvil.marketing_capture_database import remaining, transaction
from anvil.marketing_capture_evidence_async import one, schedule
from anvil.marketing_world_quiescence import Scope, dispatch_async


def original_cutoff(value, claim):
    if type(value) is not dict or set(value) != {"scope", "expires_at", "materialize_before"}:
        raise ValueError("Original private cleanup scope and timing required")
    scope = Scope.model_validate(value["scope"])
    if (any(str(getattr(scope, key)) != str(getattr(claim, key)) for key in ("project_id", "job_id", "plan_id"))
            or scope.lease_sha256 != hashlib.sha256(str(claim.lease_token).encode()).hexdigest()
            or any(str(getattr(scope, key)) != str(claim.value[key])
                   for key in ("world_binding_id", "world_binding_sha256", "episode_id", "generation"))):
        raise ValueError("Original private cleanup identity changed")
    expiry = datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00"))
    before = datetime.fromisoformat(value["materialize_before"].replace("Z", "+00:00"))
    if (expiry.tzinfo is None or before.tzinfo is None or expiry > STOP
            or not 1 <= (expiry - before).total_seconds() <= 600):
        raise ValueError("Original reserved cleanup interval required")
    hard = monotonic() + (before - datetime.now(timezone.utc)).total_seconds()
    remaining(hard)
    return hard


async def dispatch(claim):
    # A bounded read of immutable timing grants no work, model, membership or
    # receipt authority. Actual scope is revalidated in the stop transaction.
    async with transaction(claim.project_id, claim.actor_id, absolute_deadline=monotonic() + 5) as connection:
        value = (await one(connection, "SELECT marketing_runtime.capture_stop_deadline(%s,%s,%s) AS value",
                           (claim.job_id, claim.lease_token, claim.plan_id)))["value"]
        hard = original_cutoff(value, claim)
    async with transaction(claim.project_id, claim.actor_id, absolute_deadline=hard) as connection:
        if not await one(connection, "SELECT id FROM anvil.projects WHERE id=%s FOR KEY SHARE", (claim.project_id,)):
            raise RuntimeError("project_unavailable")
        result = await dispatch_async(connection, claim)
    # Fence/Q commits independently of positive capture qualification. An expired
    # source/membership/budget may deny capture without rolling back denial-only Q.
    scheduled = None
    if claim.operation in {"fence", "drain"} and result.get("quiescence") is not None:
        try:
            scheduled = await schedule(claim, absolute_deadline=hard)
        except Exception as error:
            logging.getLogger("anvil.capture").warning(
                "API capture scheduling remains unqualified job=%s plan=%s failure=%s",
                str(claim.job_id), str(claim.plan_id), type(error).__name__,
            )
    return result, scheduled
