"""Protected own-actor intake; no accepted capture and no automatic grading.

Native transport is disabled unless the existing API gate and exact independently
qualified actor profile are satisfied. No Authoring routes or credentials change.
"""

from datetime import datetime, timedelta, timezone
from time import monotonic
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from anvil.marketing_capture_attestation import CHANNEL
from anvil.marketing_capture_database import remaining, transaction
from anvil.marketing_capture_store import AuthenticatedProducer
from anvil.marketing_private_actor_auth import PATH, PrivateActorTransport, verify
from anvil.marketing_private_grade_auth import PrivateGradeTransport
from anvil.praxis_generic_contract import canonical


def routes():
    router = APIRouter()

    @router.post(PATH)
    async def receive_actor(request: Request):
        from anvil.marketing_capture_api import gate, read_wire
        from anvil.marketing_capture_intake_async import claimed_deadline
        from anvil.marketing_private_actor_store import begin, retain
        from anvil.marketing_private_grade_service import prepare_after_actor
        from anvil.marketing_private_grade_store import record as record_grade_frame
        from anvil.praxis_template_registry import source_hash

        gate()
        headers = request.headers.getlist("x-anvil-private-actor-attestation")
        enrollments = request.headers.getlist("x-anvil-capture-enrollment")
        if (request.headers.getlist("authorization") or len(headers) != 1 or len(enrollments) != 1
                or request.url.query or request.headers.getlist("transfer-encoding")
                or request.headers.getlist("content-type") != ["application/json"]):
            raise HTTPException(401, "private_actor_authentication_required")
        try:
            identifier = enrollments[0]
            if str(UUID(identifier)) != identifier:
                raise ValueError("original enrollment")
            # An unverified expiry can only shorten the original lookup bound;
            # no identity/profile/scope/data is accepted from it.
            original_hard = claimed_deadline(headers[0])
            async with transaction(absolute_deadline=min(monotonic() + 5, original_hard)) as connection:
                row = await (await connection.execute("SELECT marketing_runtime.private_actor_attestation_key(%s) AS value",
                                                      (UUID(identifier),))).fetchone()
                enrollment = row["value"] if row else None
            if type(enrollment) is not dict:
                raise ValueError("original public verification key unavailable")
            verified = verify(headers[0], enrollment, api_source_sha256=source_hash())
            transport = PrivateActorTransport.model_validate_json(canonical(enrollment["private_actor_transport"]))
            grade = PrivateGradeTransport.model_validate_json(canonical(enrollment["private_grade_transport"]))
            end = datetime.fromisoformat(enrollment["expires_at"].replace("Z", "+00:00"))
            before = end - timedelta(seconds=max(transport.cleanup_reserve_seconds, grade.cleanup_reserve_seconds))
            hard = min(original_hard, monotonic() + (before - datetime.now(timezone.utc)).total_seconds())
            if request.headers.getlist("content-length") != [str(verified.wire_bytes)]:
                raise ValueError("fixed original actor framing required")
            identity = AuthenticatedProducer(CHANNEL, verified.profile_sha256, None)
            async with transaction(absolute_deadline=hard) as connection:
                row = await (await connection.execute(
                    "SELECT marketing_runtime.capture_enrollment_scope(%s,%s,%s,%s) AS value",
                    (UUID(identifier), identity.kind, identity.subject, identity.account_email),
                )).fetchone()
                owner = row["value"] if row else None
            if type(owner) is not dict or set(owner) != {"project_id", "actor_id"}:
                raise ValueError("original actor API owner unavailable")
        except Exception:
            raise HTTPException(401, "private_actor_authentication_rejected") from None
        try:
            # Exclusive intent COMMIT precedes body read. Partial/lost outcomes
            # stay consumed; no duplicate upload/materialization is authorized.
            async with transaction(owner["project_id"], owner["actor_id"], absolute_deadline=hard) as connection:
                context = await begin(connection, enrollment, verified)
        except Exception:
            raise HTTPException(409, "private_actor_intent_unknown_or_consumed_no_retry") from None
        raw, complete = await read_wire(request, enrollment["expires_at"], verified.wire_bytes, absolute_deadline=hard)
        if not complete:
            raise HTTPException(409, "private_actor_partial_transport_no_retry")
        try:
            async with transaction(owner["project_id"], owner["actor_id"], absolute_deadline=hard) as connection:
                receipt = await retain(connection, context, raw, verified)
            async with transaction(owner["project_id"], owner["actor_id"], absolute_deadline=hard, read_only=True) as connection:
                frame = await prepare_after_actor(connection, enrollment, verified,
                                                  absolute_deadline=hard, api_source_sha256=source_hash())
            async with transaction(owner["project_id"], owner["actor_id"], absolute_deadline=hard) as connection:
                await record_grade_frame(connection, enrollment, frame, api_source_sha256=source_hash())
            # Return only after actual original write COMMIT+connection close.
            remaining(hard)
        except Exception:
            raise HTTPException(409, "private_actor_storage_unknown_no_retry") from None
        return Response(canonical(receipt), media_type="application/json", headers={"Cache-Control": "no-store"})

    return router
