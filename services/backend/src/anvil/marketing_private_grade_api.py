"""Protected fixed private-grade GET, separate from status and Authoring APIs."""

import asyncio
from datetime import datetime, timedelta, timezone
from time import monotonic
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from anvil.marketing_capture_attestation import CHANNEL
from anvil.marketing_capture_database import remaining, transaction
from anvil.marketing_capture_store import AuthenticatedProducer
from anvil.marketing_private_grade_auth import PATH, PrivateGradeTransport, verify
from anvil.praxis_generic_contract import canonical


def routes():
    router = APIRouter()

    @router.get(PATH)
    async def private_grade_input(request: Request):
        from anvil.marketing_capture_api import gate
        from anvil.marketing_capture_intake_async import claimed_deadline
        from anvil.marketing_private_grade_store import load as load_grade_frame
        from anvil.praxis_template_registry import source_hash

        gate()
        headers = request.headers.getlist("x-anvil-private-grade-attestation")
        identifiers = request.headers.getlist("x-anvil-capture-enrollment")
        if (request.headers.getlist("authorization") or len(headers) != 1 or len(identifiers) != 1
                or request.url.query or request.headers.getlist("transfer-encoding")
                or request.headers.getlist("content-length") not in ([], ["0"])):
            raise HTTPException(401, "private_grade_authentication_required")
        try:
            identifier = identifiers[0]
            if str(UUID(identifier)) != identifier:
                raise ValueError("original enrollment")
            original_hard = claimed_deadline(headers[0])
            async with transaction(absolute_deadline=min(monotonic() + 5, original_hard)) as connection:
                row = await (await connection.execute("SELECT marketing_runtime.private_actor_attestation_key(%s) AS value",
                                                      (UUID(identifier),))).fetchone()
                enrollment = row["value"] if row else None
            if type(enrollment) is not dict:
                raise ValueError("actual original private-grade verification key unavailable")
            source = source_hash()
            verified = verify(headers[0], enrollment, api_source_sha256=source)
            transport = PrivateGradeTransport.model_validate_json(canonical(enrollment["private_grade_transport"]))
            end = datetime.fromisoformat(enrollment["expires_at"].replace("Z", "+00:00"))
            hard = min(original_hard, monotonic() + (
                end - timedelta(seconds=transport.cleanup_reserve_seconds) - datetime.now(timezone.utc)
            ).total_seconds())
            async with asyncio.timeout(min(1, remaining(hard))):
                for _ in range(4):
                    event = await request.receive()
                    if event.get("type") != "http.request" or event.get("body", b"") != b"":
                        raise ValueError("fixed empty private-grade GET required")
                    if not event.get("more_body", False):
                        break
                else:
                    raise ValueError("bounded empty private-grade GET required")
            identity = AuthenticatedProducer(CHANNEL, verified.profile_sha256, None)
            async with transaction(absolute_deadline=hard) as connection:
                row = await (await connection.execute(
                    "SELECT marketing_runtime.capture_enrollment_scope(%s,%s,%s,%s) AS value",
                    (UUID(identifier), identity.kind, identity.subject, identity.account_email),
                )).fetchone()
                owner = row["value"] if row else None
            if type(owner) is not dict or set(owner) != {"project_id", "actor_id"}:
                raise ValueError("original private-grade owner unavailable")
        except Exception:
            raise HTTPException(401, "private_grade_authentication_rejected") from None
        try:
            async with transaction(owner["project_id"], owner["actor_id"], absolute_deadline=hard, read_only=True) as connection:
                # Actual frame was prepared and recorded by the original actor
                # POST. GET never materializes/replays it or accepts a binding
                # returned by an SDK as the API's original.
                allowed = await (await connection.execute(
                    "SELECT marketing_runtime.private_grade_read_authorized(%s,%s) AS allowed",
                    (UUID(identifier), UUID(verified.manifest_id)),
                )).fetchone()
                if not allowed or allowed["allowed"] is not True:
                    raise ValueError("Original current private grade scope required")
                frame = await load_grade_frame(connection, enrollment)
                raw = frame.raw
            remaining(hard)
        except Exception:
            raise HTTPException(409, "private_grade_originals_or_qualification_unavailable_no_retry") from None
        return Response(raw, media_type="application/json", headers={"Cache-Control": "no-store"})

    return router
