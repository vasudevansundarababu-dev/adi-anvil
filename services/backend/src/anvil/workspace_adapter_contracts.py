"""Internal credential-bound SDK mock contracts, never a dispatch or HTTP entry point.

Only injected MockTransport is accepted. This is not Harbor/task/live qualification.
No jobs, approvals, artifacts, audit results or spending records are created here.
"""

import json
import os
from dataclasses import asdict
from typing import Literal
from urllib.parse import unquote
from uuid import UUID

import httpx
from pydantic import Field

from anvil import auth, providers, workspace_credentials
from anvil.db import one
from anvil.schemas import Strict
from anvil.workspace_preparation import model_snapshot


class ContractBlocked(ValueError):
    """Stable diagnostic only; never attach supplied bindings, key or SDK exception."""


class CredentialBinding(Strict):
    id: UUID
    version_id: UUID


class ModelBinding(Strict):
    id: UUID
    name: str = Field(min_length=1, max_length=100)
    provider: Literal["openai", "anthropic", "gemini"]
    model_id: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=500)
    config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    max_output_tokens: int = Field(ge=1, le=8192, strict=True)
    credential: CredentialBinding | None


ENV_OVERRIDES = (
    "OPENAI_CUSTOM_HEADERS",
    "ANTHROPIC_CUSTOM_HEADERS",
    "OPENAI_ORG_ID",
    "OPENAI_PROJECT_ID",
    "OPENAI_ADMIN_KEY",
    "OPENAI_LOG",
    "ANTHROPIC_LOG",
    "GOOGLE_SDK_PYTHON_LOGGING_SCOPE",
)


def contains_secret(value, key):
    if isinstance(value, str):
        return key in value or key in unquote(value)
    if isinstance(value, dict):
        return any(contains_secret(k, key) or contains_secret(v, key) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_secret(v, key) for v in value)
    return False


def bytes_echo(value, key):
    text = value.decode("utf-8", errors="replace")
    if key in text or json.dumps(key, ensure_ascii=False)[1:-1] in text:
        return True
    try:
        return contains_secret(json.loads(text), key)
    except RecursionError:
        return True
    except ValueError:
        return False


def execute_mock(c, project_id, binding, request: providers.ActorRequest, *, transport):
    """Admin-only internal contract over current exact metadata and scoped credentials.

    The caller owns the scoped transaction. Locks keep profile/key changes serialized
    while a local mock request is evaluated. Never call from a candidate process.
    """
    if type(transport) is not httpx.MockTransport:
        raise ContractBlocked("mock_transport_required")
    if any(os.environ.get(name) for name in ENV_OVERRIDES):
        raise ContractBlocked("sdk_environment_override")
    try:
        project = UUID(str(project_id))
        frozen = ModelBinding.model_validate(binding).model_dump(mode="json")
    except (ValueError, TypeError):
        raise ContractBlocked("invalid_model_binding") from None
    if not isinstance(request, providers.ActorRequest):
        raise ContractBlocked("invalid_actor_request")
    try:
        actor_bytes = (
            len(request.actor_text.encode("utf-8")) if type(request.actor_text) is str else -1
        )
    except UnicodeError:
        raise ContractBlocked("actor_or_output_limits_not_admitted") from None
    if (
        request.model != frozen["model_id"]
        or frozen["destination"] != providers.PROVIDERS[frozen["provider"]][2]
    ):
        raise ContractBlocked("model_or_destination_mismatch")
    if (
        type(request.actor_text) is not str
        or not request.actor_text
        or not 1 <= actor_bytes <= 32768
        or type(request.max_output_tokens) is not int
        or not 1 <= request.max_output_tokens <= min(frozen["max_output_tokens"], 2048)
        or type(request.timeout_seconds) is not int
        or not 1 <= request.timeout_seconds <= 600
    ):
        raise ContractBlocked("actor_or_output_limits_not_admitted")
    scope = one(
        c,
        "SELECT current_setting('anvil.project',true) project,current_setting('anvil.user',true) actor",
    )
    if not scope or scope["project"] != str(project) or not scope["actor"]:
        raise ContractBlocked("project_scope_mismatch")
    try:
        auth.require(auth.project_roles(c, project, scope["actor"]), "admin")
    except Exception:
        raise ContractBlocked("contract_admin_required") from None
    row = one(
        c,
        """SELECT d.* FROM anvil.connections d
        JOIN anvil.workspace_model_versions v ON v.connection_id=d.id AND v.project_id=d.project_id
        JOIN anvil.workspace_model_profiles p ON p.id=v.profile_id AND p.project_id=v.project_id
        WHERE d.project_id=%s AND d.id=%s AND p.current_connection_id=d.id AND p.disabled_at IS NULL
        FOR SHARE OF d,p""",
        (project, frozen["id"]),
    )
    if (
        not row
        or row["status"] == "revoked"
        or row["config"].get("workspace_profile_version") != 1
        or model_snapshot(row) != frozen
    ):
        raise ContractBlocked("model_binding_not_current_or_enabled")
    bound = frozen["credential"]
    if not bound:
        raise ContractBlocked("credential_missing")
    credential = one(
        c,
        """SELECT h.id FROM anvil.workspace_credentials h
        JOIN anvil.workspace_credential_versions v ON v.credential_id=h.id AND v.project_id=h.project_id
        WHERE h.project_id=%s AND h.id=%s AND h.provider=%s AND h.revoked_at IS NULL
        AND h.current_version_id=%s AND v.id=%s FOR SHARE OF h""",
        (project, bound["id"], frozen["provider"], bound["version_id"], bound["version_id"]),
    )
    if not credential:
        raise ContractBlocked("credential_binding_not_current_or_enabled")
    try:
        secret = workspace_credentials.resolve(c, bound["id"], bound["version_id"])
    except Exception:
        raise ContractBlocked("credential_unavailable") from None
    key = secret.get_secret_value()
    if contains_secret((request.actor_text, request.model), key):
        raise ContractBlocked("credential_in_actor_payload")
    provider = frozen["provider"]
    endpoint = httpx.URL(providers.PROVIDERS[provider][2])
    flags = {"echo": False, "oversized": False, "request_blocked": False, "attempts": 0}

    def guarded(req):
        flags["attempts"] += 1
        if flags["attempts"] > 1:
            raise httpx.TransportError("additional mock request suppressed", request=req) from None
        auth_header = {
            "openai": "authorization",
            "anthropic": "x-api-key",
            "gemini": "x-goog-api-key",
        }[provider]
        expected = "Bearer " + key if provider == "openai" else key
        allowed_path = (
            req.url.path == "/v1/responses"
            if provider == "openai"
            else req.url.path == "/v1/messages"
            if provider == "anthropic"
            else req.url.path.startswith("/v1beta/models/")
            and req.url.path.endswith(":generateContent")
        )
        other_auth = {"authorization", "x-api-key", "x-goog-api-key"} - {auth_header}
        if (
            req.method != "POST"
            or req.url.scheme != "https"
            or req.url.host != endpoint.host
            or req.url.port not in (None, 443)
            or not allowed_path
            or req.headers.get(auth_header) != expected
            or any(req.headers.get(h) for h in other_auth)
            or key in unquote(str(req.url))
            or bytes_echo(req.content, key)
        ):
            flags["request_blocked"] = True
            raise httpx.TransportError("mock request not admitted", request=req) from None
        try:
            response = transport.handle_request(req)
            body = response.read()
            flags["oversized"] = len(body) > 2000000
            unsafe = bytes_echo(body, key) or contains_secret(dict(response.headers), key)
        except httpx.TimeoutException:
            raise httpx.ReadTimeout("mock transport timeout", request=req) from None
        except Exception:
            raise httpx.TransportError("mock transport failure", request=req) from None
        if unsafe or flags["oversized"]:
            flags["echo"] = unsafe
            response.close()
            return httpx.Response(
                502, json={"error": {"message": "unsafe mock response suppressed"}}, request=req
            )
        return response

    result = providers.execute_contract(
        provider, request, httpx.MockTransport(guarded), credential=secret
    )
    if flags["attempts"] > 1:
        return providers.Result("execution_unknown", error_code="unexpected_mock_retry_suppressed")
    if flags["echo"] or contains_secret(asdict(result), key):
        return providers.Result("failed_operational", error_code="credential_echo_suppressed")
    if flags["request_blocked"]:
        return providers.Result("failed_operational", error_code="native_request_not_admitted")
    if flags["oversized"]:
        return providers.Result("failed_operational", error_code="mock_response_too_large")
    return result
