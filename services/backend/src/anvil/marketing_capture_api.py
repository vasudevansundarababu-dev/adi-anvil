"""Fail-closed private native capture intake and qualified original acceptance.

HTTP verifies an original-operation operator-enrolled host attester signature.
No raw peer identity, OIDC fallback or self-enrollment is accepted. Actual host
isolation still needs qualification. Raw custody never qualifies whole-actor proof.
"""

import asyncio
import os
from datetime import datetime, timezone
from time import monotonic
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from anvil import pilot_environment
from anvil.marketing_capture_attestation import CHANNEL, PATH, matches_wire, verify
from anvil.marketing_capture_store import (
    AuthenticatedProducer,
)
from anvil.marketing_capture_submission import WIRE_CAP
from anvil.praxis_generic_contract import canonical


def gate():
    if (pilot_environment.current() != "qa" or os.environ.get("ANVIL_WORKER_BROKER_ROLE") != "api"
            or os.environ.get("ANVIL_MARKETING_NATIVE_CAPTURE_ENABLED") != "true"):
        raise HTTPException(503, "native_capture_intake_disabled")


async def read_wire(request, expires_at, wire_limit, *, absolute_deadline):
    """API's own original server expiry, never a host monotonic timestamp."""
    end = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if end.tzinfo is None:
        raise ValueError("capture_original_server_expiry_required")
    hard = min(absolute_deadline, monotonic() + max(0, (end - datetime.now(timezone.utc)).total_seconds()))
    wire = bytearray()
    stream = request.stream().__aiter__()
    try:
        while True:
            seconds = min(hard - monotonic(), (end - datetime.now(timezone.utc)).total_seconds())
            if seconds <= 0:
                raise TimeoutError("capture_original_server_deadline")
            try:
                chunk = await asyncio.wait_for(stream.__anext__(), timeout=seconds)
            except StopAsyncIteration:
                break
            if type(chunk) is not bytes or len(wire) + len(chunk) > min(WIRE_CAP, wire_limit):
                raise ValueError("capture_wire_bound")
            wire.extend(chunk)
        return bytes(wire), True
    except (Exception, asyncio.CancelledError):
        # Partial bytes are diagnostic evidence only. A lost/partial transport
        # never creates permission for another upload or fresh deadline.
        return bytes(wire), False


def routes():
    router = APIRouter()

    from anvil.marketing_capture_status import PATH as status_path

    @router.get(status_path)
    async def evidence_status(request: Request):
        """Read only. Never consume upload intent, reserve, materialize or repair."""
        from anvil.marketing_capture_database import transaction as capture_transaction
        from anvil.marketing_capture_intake_async import claimed_deadline
        from anvil.marketing_capture_status import Transport, validate_response
        from anvil.marketing_capture_status import verify as verify_status
        from anvil.praxis_generic_contract import canonical
        from anvil.praxis_template_registry import source_hash

        gate()
        authorization = request.headers.getlist("authorization")
        attestations = request.headers.getlist("x-anvil-capture-attestation")
        identifiers = request.headers.getlist("x-anvil-capture-enrollment")
        if (authorization or len(attestations) != 1 or len(identifiers) != 1 or request.url.query
                or request.headers.getlist("transfer-encoding")
                or request.headers.getlist("content-length") not in ([], ["0"])):
            raise HTTPException(401, "capture_status_authentication_rejected")
        try:
            identifier = identifiers[0]
            if str(UUID(identifier)) != identifier:
                raise ValueError("original identifier")
            # An unverified claimed expiry can ONLY shorten a small lookup
            # bound. No identity, key, scope or positive status comes from it.
            header = attestations[0]
            hard = min(monotonic() + 5, claimed_deadline(header))
            async with capture_transaction(absolute_deadline=hard) as connection:
                original = (await (await connection.execute(
                    "SELECT marketing_runtime.capture_attestation_key(%s) AS value", (UUID(identifier),),
                )).fetchone())["value"]
            if type(original) is not dict or original.get("enrollment_id") != identifier:
                raise ValueError("original enrollment")
            verified = verify_status(attestations[0], original, api_source_sha256=source_hash())
            remaining = ((datetime.fromisoformat(original["expires_at"].replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds()
                         - Transport.model_validate(original["status_transport"]).cleanup_reserve_seconds)
            hard = min(hard, monotonic() + remaining)
            async with asyncio.timeout(min(1.0, max(0, hard - monotonic()))):
                for _ in range(4):
                    message = await request.receive()
                    if message.get("type") != "http.request" or message.get("body", b"") != b"":
                        raise ValueError("fixed status GET has no body")
                    if not message.get("more_body", False):
                        break
                else:
                    raise ValueError("fixed bounded empty GET required")
            identity = AuthenticatedProducer(CHANNEL, verified.profile_sha256, None)
            async with capture_transaction(absolute_deadline=hard) as connection:
                owner = (await (await connection.execute(
                    "SELECT marketing_runtime.capture_enrollment_scope(%s,%s,%s,%s) AS value",
                    (UUID(identifier), identity.kind, identity.subject, identity.account_email),
                )).fetchone())["value"]
            if type(owner) is not dict or set(owner) != {"project_id", "actor_id"}:
                raise ValueError("original scope")
            async with capture_transaction(owner["project_id"], owner["actor_id"], absolute_deadline=hard) as connection:
                value = (await (await connection.execute(
                    "SELECT marketing_runtime.capture_evidence_enrollment_status(%s) AS value", (UUID(identifier),),
                )).fetchone())["value"]
            if type(value) is dict and value.get("state") in {"reserved_no_content", "materialization_unknown"}:
                from anvil.marketing_capture_evidence_async import await_original_completion

                # One HTTP observation may await only the original retained
                # process-owned attempt. No status-driven materialize/reclaim,
                # polling, second request or new time allowance is introduced.
                waited = await await_original_completion(original | {"manifest_id": value["manifest_id"]},
                                                          absolute_deadline=hard)
                if waited:
                    async with capture_transaction(owner["project_id"], owner["actor_id"], absolute_deadline=hard) as connection:
                        value = (await (await connection.execute(
                            "SELECT marketing_runtime.capture_evidence_enrollment_status(%s) AS value", (UUID(identifier),),
                        )).fetchone())["value"]
            raw = canonical(value)
            validate_response(raw, original)
            if monotonic() >= hard:
                raise TimeoutError("Original status database deadline reached")
        except Exception:
            raise HTTPException(401, "capture_status_authentication_rejected") from None
        return Response(content=raw, media_type="application/json", headers={"Cache-Control": "no-store"})

    @router.post(PATH)
    async def receive(request: Request):
        from anvil import marketing_capture_intake_async as custody
        from anvil.marketing_capture_database import transaction as capture_transaction

        gate()
        authorization = request.headers.getlist("authorization")
        attestations = request.headers.getlist("x-anvil-capture-attestation")
        enrollment_headers = request.headers.getlist("x-anvil-capture-enrollment")
        if authorization or len(attestations) != 1 or len(enrollment_headers) != 1:
            raise HTTPException(401, "capture_authentication_required")
        try:
            identifier = enrollment_headers[0]
            if str(UUID(identifier)) != identifier:
                raise ValueError("identifier")
            original_hard = custody.claimed_deadline(attestations[0])
            async with capture_transaction(absolute_deadline=min(monotonic() + 5, original_hard)) as connection:
                enrolled_key = await custody.key(connection, identifier)
            if type(enrolled_key) is not dict or enrolled_key.get("enrollment_id") != identifier:
                raise ValueError("original public key unavailable")
            attestation = verify(attestations[0], enrolled_key)
            # Signature verification binds claimed expiry to the actual original
            # enrollment. This preserves its elapsed time; no fresh upload timer.
            original_hard = min(original_hard, monotonic() + (
                datetime.fromisoformat(enrolled_key["expires_at"].replace("Z", "+00:00")) - datetime.now(timezone.utc)
            ).total_seconds())
            identity = AuthenticatedProducer(CHANNEL, attestation.profile_sha256, None)
        except Exception:
            raise HTTPException(401, "capture_authentication_rejected") from None
        # No body is read until actual independently enrolled scope is resolved
        # and the one-use intent transaction commits. No self-enrollment route.
        try:
            async with capture_transaction(absolute_deadline=original_hard) as connection:
                owner = await custody.scope(connection, identity, identifier)
            if type(owner) is not dict or set(owner) != {"project_id", "actor_id"}:
                raise RuntimeError("enrollment")
            async with capture_transaction(owner["project_id"], owner["actor_id"], absolute_deadline=original_hard) as connection:
                context = await custody.begin(connection, identity, identifier)
                if any(context[key] != owner[key] for key in ("project_id", "actor_id")):
                    raise ValueError("capture original owner changed")
                if any(context[key] != enrolled_key[key] for key in ("enrollment_id", "request_sha256", "operation_nonce",
                                                                     "body_schema", "wire_limit", "document_limits")):
                    raise ValueError("capture signed original operation changed")
        except Exception:
            raise HTTPException(409, "capture_enrollment_or_intent_unavailable_no_retry") from None
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            raw, complete = b"", False
        else:
            raw, complete = await read_wire(request, context["expires_at"], min(context["wire_limit"], attestation.wire_bytes),
                                            absolute_deadline=original_hard)
            complete = complete and matches_wire(attestation, raw)
        try:
            async with capture_transaction(owner["project_id"], owner["actor_id"], absolute_deadline=original_hard) as connection:
                raw_receipt = await custody.retain(connection, context, raw, transport_complete=complete, attestation=attestation)
        except Exception:
            # One storage attempt only, including ambiguous commit/response loss.
            raise HTTPException(409, "capture_raw_custody_unknown_no_retry") from None
        if not complete or context["body_schema"] != "anvil.marketing-native-capture-submission.v2":
            raise HTTPException(409, "capture_retained_unqualified_no_success_reference_no_retry")
        try:
            from anvil.marketing_private_capture_service import accept
            from anvil.praxis_template_registry import source_hash

            async with capture_transaction(owner["project_id"], owner["actor_id"], absolute_deadline=original_hard) as connection:
                accepted = await accept(connection, context, raw_receipt, raw, api_source_sha256=source_hash())
            # The actual durable acceptance must COMMIT and close before200.
            if monotonic() >= original_hard:
                raise TimeoutError("Original capture acceptance deadline reached")
        except Exception:
            raise HTTPException(409, "capture_physical_qualification_or_acceptance_unconfirmed_no_retry") from None
        return Response(canonical(accepted), media_type="application/json", headers={"Cache-Control": "no-store"})

    from anvil.marketing_private_actor_api import routes as actor_routes
    from anvil.marketing_private_grade_api import routes as grade_routes
    from anvil.marketing_private_result_api import routes as result_routes

    router.include_router(actor_routes())
    router.include_router(grade_routes())
    router.include_router(result_routes())
    return router
