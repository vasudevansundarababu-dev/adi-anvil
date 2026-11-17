"""Bounded server-to-server Praxis template caller. No retries or secret discovery."""

import ipaddress
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import httpx
from pydantic import SecretStr

from anvil.praxis_generic_contract import canonical, digest, load

QA_ORIGIN = "https://praxis-api-742785092638.us-central1.run.app"
QA_PROJECT = "a7454c18-602e-4907-bdd9-277067c36233"
KEY_STOP = datetime(2026, 12, 11, 5, 48, 4, tzinfo=timezone.utc)


def runtime_client(project_id, *, now=None):
    """API-only attached service identity; no password-manager/file-key intake."""
    from anvil import pilot_environment
    from anvil.praxis_workload_identity import WorkloadIdentityError, metadata_token

    instant = datetime.now(timezone.utc) if now is None else now
    if (
        instant.tzinfo is None
        or str(project_id) != QA_PROJECT
        or instant >= KEY_STOP
        or pilot_environment.current() != "qa"
        or os.environ.get("ANVIL_WORKER_BROKER_ROLE") != "api"
        or os.environ.get("ANVIL_PRAXIS_TEMPLATE_CALLS_ENABLED") != "true"
        or os.environ.get("ANVIL_PRAXIS_WORKLOAD_IDENTITY_ENABLED") != "true"
        or os.environ.get("ANVIL_PRAXIS_TEMPLATE_ORIGIN") != QA_ORIGIN
    ):
        raise PraxisCallError("praxis_runtime_binding_unavailable")
    try:
        token = metadata_token()
    except WorkloadIdentityError:
        raise PraxisCallError("praxis_runtime_identity_unavailable") from None
    return PraxisTemplateClient(QA_ORIGIN, token, allowed_origins={QA_ORIGIN})


class PraxisCallError(RuntimeError):
    def __init__(self, code, *, ambiguous=False, remote_code=None, request_id=None):
        self.code, self.ambiguous = code, ambiguous
        self.remote_code, self.request_id = remote_code, request_id
        super().__init__(code)


def qualification_envelope(receipt):
    """Praxis stable lineage identity; hash the ORIGINAL receipt for revocation."""
    from uuid import UUID

    for key in ("template_id", "receipt_id"):
        UUID(receipt[key])
    if type(receipt["version"]) is not int or receipt["version"] < 1:
        raise ValueError("Positive published template version required")
    if receipt["status"] not in {"qualified", "blocked"}:
        raise ValueError("Known qualification status required")
    return {
        "template_id": receipt["template_id"],
        "version": receipt["version"],
        "template_version_hash": receipt["template_sha256"],
        "status": receipt["status"],
        "receipt_id": receipt["receipt_id"],
        "receipt": receipt,
    }


def publication_status(body):
    value = body.get("publication_status", body.get("status"))
    if "publication_status" in body and "status" in body and body["status"] != value:
        raise PraxisCallError("praxis_publication_status_conflict")
    return value


class PraxisTemplateClient:
    def __init__(self, origin, token: SecretStr, *, allowed_origins, transport=None):
        parts = urlsplit(origin)
        if (
            origin not in allowed_origins
            or parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.path
            or parts.query
            or parts.fragment
            or parts.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("Exact operator-approved HTTPS Praxis origin required")
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("Private/loopback Praxis endpoint rejected")
        self._token = token
        self._base = origin + "/api/v1/integrations/anvil/templates"
        self._transport = transport
        self.origin = (
            "offline_fixture"
            if isinstance(transport, httpx.MockTransport)
            else "praxis_authenticated_api"
        )

    def call(self, method, path, body=None, *, idempotency_key=None):
        if (
            self.origin != "offline_fixture"
            and os.environ.get("ANVIL_PRAXIS_TEMPLATE_CALLS_ENABLED") != "true"
        ):
            raise PraxisCallError("praxis_template_calls_disabled")
        if self.origin != "offline_fixture" and datetime.now(timezone.utc) >= KEY_STOP:
            raise PraxisCallError("praxis_runtime_credential_expired")
        if not (
            method == "GET"
            and (path == "/contracts" or re.fullmatch(r"/proposals/[A-Za-z0-9_.-]{1,100}", path))
            or method == "POST"
            and path in {"/validate", "/proposals", "/qualifications"}
        ):
            raise ValueError("Unsupported fixed Praxis template operation")
        headers = {
            "Authorization": "Bearer " + self._token.get_secret_value(),
            "Content-Type": "application/json",
        }
        if path in {"/proposals", "/qualifications"} and method == "POST":
            if not idempotency_key or len(idempotency_key) > 200:
                raise ValueError("Stable bounded Idempotency-Key required")
            headers["Idempotency-Key"] = idempotency_key
        payload = canonical(body) if body is not None else None
        if payload is not None and len(payload) > 1048576:
            raise ValueError("Template request exceeds1MiB")
        try:
            with httpx.Client(
                transport=self._transport, timeout=10, follow_redirects=False, trust_env=False
            ) as client:
                with client.stream(
                    method, self._base + path, content=payload, headers=headers
                ) as response:
                    status = response.status_code
                    data = bytearray()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        data.extend(chunk)
                        if len(data) > 1048576:
                            raise PraxisCallError(
                                "praxis_response_too_large", ambiguous=method == "POST"
                            )
        except httpx.HTTPError:
            raise PraxisCallError("praxis_transport_failed", ambiguous=method == "POST") from None
        if self._token.get_secret_value().encode() in data:
            raise PraxisCallError("praxis_sensitive_response_rejected", ambiguous=method == "POST")
        if status >= 300:
            # Praxis errors are {error:string,message,requestId}, not data/meta.
            # Keep only recognized codes and a bounded correlation identifier;
            # never relay arbitrary messages, private content or response bytes.
            safe_code = request_id = None
            try:
                failure = load(bytes(data))
                if isinstance(failure.get("error"), str) and failure["error"] in {
                    "DRAFT_EXISTS", "DOMAIN_RETIRED", "IDEMPOTENCY_CONFLICT", "CONFLICT",
                    "TP_FORM_ID_TAKEN", "INVALID_GOLDEN_PACK", "UNAUTHORIZED", "UNAUTHENTICATED",
                    "FORBIDDEN", "VALIDATION_FAILED", "ANVIL_STREAM_UNBOUND",
                }:
                    safe_code = failure["error"]
                identifier = failure.get("requestId")
                if isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", identifier):
                    request_id = identifier
            except (ValueError, UnicodeError):
                pass
            raise PraxisCallError(
                "praxis_http_" + str(status),
                ambiguous=method == "POST" and (status >= 500 or status == 408),
                remote_code=safe_code, request_id=request_id,
            )
        try:
            result = load(bytes(data))
        except (ValueError, UnicodeError):
            raise PraxisCallError(
                "praxis_response_contract_invalid", ambiguous=method == "POST"
            ) from None
        if not isinstance(result.get("data"), dict) or not isinstance(result.get("meta"), dict):
            raise PraxisCallError("praxis_response_contract_invalid", ambiguous=method == "POST")
        return result

    def contracts(self):
        return self.call("GET", "/contracts")

    def validate(self, spec):
        return self.call("POST", "/validate", spec)

    def propose(self, spec, *, idempotency_key):
        return self.call("POST", "/proposals", spec, idempotency_key=idempotency_key)

    def validate_and_propose(self, spec, *, idempotency_key):
        """No publication authority; invalid authorability never creates a proposal."""
        validation = self.validate(spec)["data"]
        if validation.get("valid") is not True:
            return {
                "status": "authoring_validation_blocked",
                "validation": validation,
                "proposal_created": False,
            }
        proposal = self.propose(spec, idempotency_key=idempotency_key)["data"]
        return {
            "status": "proposal_created",
            "validation": validation,
            "proposal": proposal,
            "proposal_created": True,
        }

    def proposal(self, identifier):
        if (
            not identifier
            or len(identifier) > 100
            or any(
                c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
                for c in identifier
            )
        ):
            raise ValueError("Invalid proposal ID")
        return self.call("GET", "/proposals/" + quote(identifier, safe=""))

    def qualification(self, receipt, *, idempotency_key):
        return self.call(
            "POST",
            "/qualifications",
            qualification_envelope(receipt),
            idempotency_key=idempotency_key,
        )

    def revocation(self, event, *, idempotency_key):
        from anvil.praxis_generic_contract import RevocationEvent

        RevocationEvent.model_validate(event)
        return self.call(
            "POST",
            "/qualifications",
            {"kind": "revocation", "event": event, "event_sha256": digest(event)},
            idempotency_key=idempotency_key,
        )


def accept_publication(c, project, user, client, proposal_id):
    """Authenticated counterparty response, never an author's approval assertion."""
    from anvil import praxis_template_registry as registry

    body = client.proposal(proposal_id)["data"]
    if publication_status(body) != "published" or not isinstance(body.get("template_spec"), dict):
        return {"status": "awaiting_praxis_publication", "published": False}
    spec = body["template_spec"]
    if (
        not all(key in spec for key in ("execution", "authoring", "skills"))
        or digest(spec) != body.get("template_sha256")
        or {key: digest(spec[key]) for key in ("execution", "authoring", "skills")}
        != body.get("part_hashes")
    ):
        raise PraxisCallError("praxis_publication_hash_invalid")
    stored = registry.register(c, project, user, spec)
    registry.publication(
        c, project, user, stored["id"], body | {"status": "published"}, origin=client.origin
    )
    return {
        "status": "publication_recorded",
        "template_id": stored["id"],
        "origin": client.origin,
        "publication_verified": client.origin == "praxis_authenticated_api",
    }
