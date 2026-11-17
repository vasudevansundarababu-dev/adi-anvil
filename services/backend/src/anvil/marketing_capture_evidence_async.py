"""API capture scheduling/custody with no synchronous DB connection fallback."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from uuid import UUID

from anvil.marketing_capture_database import remaining, transaction
from anvil.marketing_capture_evidence import PreparedEvidence, prepare_async
from anvil.marketing_capture_evidence_store import _normal_context, checked_status
from anvil.praxis_generic_contract import canonical


@dataclass(slots=True)
class Scheduled:
    context: dict = field(repr=False)
    absolute_deadline: float
    lock: object = field(default_factory=Lock, repr=False)
    started: bool = False
    completed: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    completion: str = "pending_original_attempt"


# Process-owned original handles only. Never reconstruct from durable unknown
# status, replace an unexpired handle or infer that another worker owns it.
_LIVE_LIMIT = 128
_live: dict[tuple[str, str], Scheduled] = {}
_live_lock = Lock()


def _register(scheduled):
    now = monotonic()
    with _live_lock:
        for key, handle in tuple(_live.items()):
            if handle.absolute_deadline <= now:
                del _live[key]
        key = (scheduled.context["enrollment_id"], scheduled.context["manifest_id"])
        if key in _live or len(_live) >= _LIVE_LIMIT:
            raise RuntimeError("Original materialization completion custody unavailable; no replacement")
        _live[key] = scheduled


def _finish(scheduled, state):
    scheduled.completion = state
    scheduled.completed.set()


async def await_original_completion(enrollment, *, absolute_deadline):
    """Wait only on the SAME owned attempt, never poll/reclaim/materialize.

    False means no locally retained handle; SQL status remains the authority.
    It does not mean pending or ready. A lost/failed/cancelled attempt is Unknown.
    A wakeup is not committed content: the caller must re-read actual SQL status.
    """
    from anvil.marketing_world_quiescence import Scope

    scope = Scope.model_validate(enrollment["scope"]).model_dump(mode="json")
    with _live_lock:
        handle = _live.get((enrollment["enrollment_id"], enrollment["manifest_id"]))
    if handle is None:
        return False
    context = handle.context
    if (context["scope"] != scope or context["request_sha256"] != enrollment["request_sha256"]
            or context["operation_nonce"] != enrollment["operation_nonce"]):
        raise ValueError("Original materialization completion scope changed")
    hard = min(absolute_deadline, handle.absolute_deadline)
    async with asyncio.timeout(remaining(hard)):
        await handle.completed.wait()
    remaining(hard)
    if handle.completion != "verified_committed_content":
        raise RuntimeError("Original materialization outcome unknown; no retry")
    return True


async def one(connection, sql, args):
    return await (await connection.execute(sql, args)).fetchone()


async def status(connection, claim):
    row = await one(connection, "SELECT marketing_runtime.capture_evidence_status(%s,%s,%s) AS value",
                    (claim.job_id, claim.lease_token, claim.plan_id))
    return checked_status(row["value"], claim)


async def schedule(claim, *, absolute_deadline):
    remaining(absolute_deadline)
    scheduled = None
    try:
        async with transaction(claim.project_id, claim.actor_id, absolute_deadline=absolute_deadline) as connection:
            observed = await status(connection, claim)
            if observed["state"] == "ready":
                return None
            if observed["state"] != "reserved_no_content":
                raise RuntimeError("API evidence materialization already consumed_unknown_no_retry")
            from anvil.db import uid

            intent = uid()
            context = _normal_context((await one(
                connection, "SELECT marketing_runtime.begin_capture_evidence(%s,%s,%s,%s,%s) AS value",
                (claim.job_id, claim.lease_token, claim.plan_id, UUID(observed["enrollment_id"]), UUID(intent)),
            ))["value"])
            # A previously supplied deadline can only narrow the stored original
            # cutoff; it cannot extend server enrollment or cleanup reservation.
            before = datetime.fromisoformat(context["materialize_before"].replace("Z", "+00:00"))
            absolute_deadline = min(absolute_deadline, monotonic() + (before - datetime.now(timezone.utc)).total_seconds())
            remaining(absolute_deadline)
            connection.capture_deadline = min(connection.capture_deadline, absolute_deadline)
            scheduled = Scheduled(context, absolute_deadline)
            # Reserve bounded completion custody BEFORE original intent COMMIT.
            _register(scheduled)
        remaining(absolute_deadline)
        return scheduled
    except BaseException:
        if scheduled is not None:
            _finish(scheduled, "unknown_no_retry")
        raise


async def _materialize(claim, scheduled):
    if type(scheduled) is not Scheduled:
        raise ValueError("Original one-use async materialization handle required")
    with scheduled.lock:
        if scheduled.started:
            raise RuntimeError("API evidence callback already consumed_unknown_no_retry")
        scheduled.started = True
    context, hard = scheduled.context, scheduled.absolute_deadline
    remaining(hard)
    from anvil.db import uid

    async with transaction(claim.project_id, claim.actor_id, absolute_deadline=hard) as connection:
        async with connection.cursor(name="anvil_evidence_" + uid().replace("-", "")) as cursor:
            cursor.itersize = 1
            await cursor.execute("SELECT marketing_runtime.capture_evidence_rows(%s,%s,%s,%s,%s) AS value",
                                 (claim.job_id, claim.lease_token, claim.plan_id, UUID(context["enrollment_id"]), UUID(context["intent_id"])))

            async def rows():
                while True:
                    remaining(hard)
                    row = await cursor.fetchone()
                    if row is None:
                        break
                    yield row["value"]

            async def retain(category, identifier, raw):
                remaining(hard)
                row = await one(connection,
                                "SELECT marketing_runtime.retain_capture_evidence_snapshot(%s,%s,%s,%s,%s) AS allowed",
                                (UUID(context["intent_id"]), category, identifier, raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()))
                if row["allowed"] is not True:
                    raise RuntimeError("API evidence snapshot custody unconfirmed_no_retry")

            prepared = await prepare_async(context, rows(), retain_snapshot=retain)
        if type(prepared) is not PreparedEvidence:
            raise RuntimeError("Actual API evidence compilation required")
        remaining(hard)
        row = await one(connection,
                        "SELECT marketing_runtime.commit_capture_evidence(%s,%s,%s,%s,%s,%s,%s,%s) AS allowed",
                        (claim.job_id, claim.lease_token, claim.plan_id, UUID(context["enrollment_id"]), UUID(context["intent_id"]),
                         prepared.manifest.decode("utf-8"), prepared.sha256, canonical(prepared.descriptor).decode("utf-8")))
        if row["allowed"] is not True:
            raise RuntimeError("API evidence materialization commit unconfirmed_unknown_no_retry")
    async with transaction(claim.project_id, claim.actor_id, absolute_deadline=hard) as connection:
        observed = await status(connection, claim)
    remaining(hard)
    if observed["state"] != "ready" or observed["descriptor"] != prepared.descriptor:
        raise RuntimeError("Actual retained API evidence readback differs_unknown_no_retry")
    return observed


async def materialize(claim, scheduled):
    try:
        observed = await _materialize(claim, scheduled)
    except BaseException:
        if type(scheduled) is Scheduled:
            _finish(scheduled, "unknown_no_retry")
        raise
    _finish(scheduled, "verified_committed_content")
    return observed


async def after_response(claim, scheduled):
    try:
        await materialize(claim, scheduled)
    except Exception as error:
        logging.getLogger("anvil.capture").warning(
            "API evidence remains unqualified job=%s plan=%s failure=%s",
            str(claim.job_id), str(claim.plan_id), type(error).__name__,
        )
