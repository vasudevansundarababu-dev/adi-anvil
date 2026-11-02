"""Provider-specific SDK contracts. No production dispatch without authority."""

import json
import os
import stat
from dataclasses import dataclass, replace

import httpx
from anthropic import Anthropic
from google import genai
from google.genai import types
from mistralai.client import Mistral
from openai import OpenAI
from pydantic import Field, SecretStr

from anvil.config import CLOUD, ROOT, private_file_owner
from anvil.schemas import Strict
from anvil.workspace_costs import RATES

PROVIDERS = {
    "openai": ("OpenAI Responses", "OPENAI_API_KEY", "https://api.openai.com/v1"),
    "anthropic": ("Claude Messages", "ANTHROPIC_API_KEY", "https://api.anthropic.com"),
    "gemini": (
        "Gemini generateContent",
        "GEMINI_API_KEY",
        "https://generativelanguage.googleapis.com",
    ),
    "mistral": ("Mistral chat", "MISTRAL_API_KEY", "https://api.mistral.ai"),
    "meta_muse": ("Meta Model API Responses", "META_MODEL_API_KEY", "https://api.meta.ai/v1"),
    "open_weight_compatible": (
        "Restricted compatible chat",
        "ANVIL_COMPATIBLE_API_KEY",
        "http://127.0.0.1:9000/v1",
    ),
}


class ActorRequest(Strict):
    model: str = Field(min_length=1, max_length=200)
    actor_text: str = Field(min_length=1, max_length=100000)
    max_output_tokens: int = Field(ge=1, le=8192)
    timeout_seconds: int = Field(default=60, ge=1, le=600)


@dataclass(frozen=True)
class Result:
    status: str
    text: str | None = None
    model_returned: str | None = None
    request_id: str | None = None
    usage: dict | None = None
    finish_reason: str | None = None
    error_code: str | None = None
    actual_cost_micro_usd: int | None = None


def secret_presence(provider):
    name = PROVIDERS[provider][1]
    value = os.environ.get(name)
    file = os.environ.get(name + "_FILE")
    if value and file:
        return False, "conflicting_secret_sources"
    if CLOUD and provider == "openai" and value:
        return False, "cloud_secret_requires_private_file"
    if value:
        return True, None
    if file:
        try:
            allowed = ROOT / ".secrets" / name.lower()
            candidate = ROOT / file
            if candidate.is_symlink() or candidate.resolve() != allowed.resolve():
                return False, "secret_path_not_allowlisted"
            if not candidate.is_file():
                return False, "secret_missing"
            info = candidate.stat()
            if stat.S_IMODE(info.st_mode) & 0o077 or not private_file_owner(info.st_uid):
                return False, "secret_file_permissions"
            return info.st_size > 0, None if info.st_size else "secret_empty"
        except OSError:
            return False, "secret_unreadable"
    return False, "secret_missing"


def normalized(provider, data):
    text = ""
    finish = None
    usage = None
    model = None
    request_id = None
    refusal = False
    if provider in ("openai", "meta_muse"):
        request_id = data.get("id")
        model = data.get("model")
        usage = data.get("usage")
        finish = data.get("status")
        for item in data.get("output") or []:
            if item.get("type") == "message":
                for part in item.get("content") or []:
                    if part.get("type") == "refusal":
                        refusal = True
                    elif part.get("type") == "output_text":
                        text += part.get("text", "")
        if finish == "incomplete":
            return Result("truncated", text or None, model, request_id, usage, finish)
    elif provider == "anthropic":
        request_id = data.get("id")
        model = data.get("model")
        usage = data.get("usage")
        finish = data.get("stop_reason")
        text = "".join(
            p.get("text", "") for p in data.get("content", []) if p.get("type") == "text"
        )
        refusal = finish == "refusal"
        if finish == "max_tokens":
            return Result("truncated", text or None, model, request_id, usage, finish)
    elif provider == "gemini":
        request_id = data.get("response_id")
        model = data.get("model_version")
        usage = data.get("usage_metadata")
        candidates = data.get("candidates") or []
        block = data.get("prompt_feedback") or {}
        refusal = bool(block.get("block_reason"))
        if candidates:
            first = candidates[0]
            finish = first.get("finish_reason")
            text = "".join(
                p.get("text", "")
                for p in (first.get("content") or {}).get("parts", [])
                if not p.get("thought")
            )
            refusal = refusal or finish in (
                "SAFETY",
                "RECITATION",
                "BLOCKLIST",
                "PROHIBITED_CONTENT",
            )
        if finish == "MAX_TOKENS":
            return Result("truncated", text or None, model, request_id, usage, finish)
    else:
        request_id = data.get("id")
        model = data.get("model")
        usage = data.get("usage")
        choices = data.get("choices") or []
        if choices:
            first = choices[0]
            finish = first.get("finish_reason")
            message = first.get("message") or {}
            refusal = bool(message.get("refusal")) or finish in ("content_filter", "model_length")
            content = message.get("content")
            text = (
                content
                if isinstance(content, str)
                else "".join(p.get("text", "") for p in content or [] if p.get("type") == "text")
            )
        if finish == "length":
            return Result("truncated", text or None, model, request_id, usage, finish)
    if refusal:
        return Result("refused", text or None, model, request_id, usage, finish)
    if not text.strip():
        return Result(
            "failed_operational",
            model_returned=model,
            request_id=request_id,
            usage=usage,
            finish_reason=finish,
            error_code="empty_or_malformed_output",
        )
    return Result("completed", text, model, request_id, usage, finish)


def execute_contract(
    provider: str,
    request: ActorRequest,
    transport: httpx.MockTransport,
    *,
    credential: SecretStr | None = None,
):
    """Network-free qualification entry point; refuses a real transport."""
    if provider not in PROVIDERS or not isinstance(transport, httpx.MockTransport):
        raise ValueError(
            "Mock transport required; live dispatch must use paid authorization service"
        )
    return _execute_native(provider, request, transport, credential=credential)


def _execute_native(provider, request, transport, *, credential, structured=False):
    """Internal SDK plumbing; live callers must supply the authorized guarded broker."""
    endpoint = PROVIDERS[provider][2]
    if credential is not None and (
        not isinstance(credential, SecretStr) or not credential.get_secret_value()
    ):
        raise ValueError("Explicit credentials must be a nonempty SecretStr")
    key = credential.get_secret_value() if credential is not None else "anvil-contract-test-only"
    observed = {}

    def capture(response):
        observed["status"] = response.status_code
        response.read()
        if len(response.content) <= 2_000_000:
            try:
                observed["body"] = response.json()
            except ValueError:
                pass

    # SDK retry defaults are disabled independently; transport redirects are never followed.
    with httpx.Client(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=request.timeout_seconds,
        event_hooks={"response": [capture]},
    ) as http:
        try:
            if provider in ("openai", "meta_muse"):
                sdk = OpenAI(
                    api_key=key,
                    base_url=endpoint,
                    http_client=http,
                    max_retries=0,
                )
                result = sdk.responses.create(
                    model=request.model,
                    input=[{"role": "user", "content": request.actor_text}],
                    max_output_tokens=request.max_output_tokens,
                    store=False,
                    **(
                        {
                            "service_tier": "default",
                            "text": {"format": {"type": "json_object"}},
                            **(
                                {"prompt_cache_options": {"ttl": "30m"}}
                                if request.model in RATES
                                else {}
                            ),
                        }
                        if structured
                        else {}
                    ),
                )
            elif provider == "anthropic":
                sdk = Anthropic(
                    api_key=key,
                    base_url=endpoint,
                    http_client=http,
                    max_retries=0,
                )
                result = sdk.messages.create(
                    model=request.model,
                    messages=[{"role": "user", "content": request.actor_text}],
                    max_tokens=request.max_output_tokens,
                    **(
                        {
                            "output_config": {
                                "format": {
                                    "type": "json_schema",
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "json": {
                                                "type": "string",
                                                "description": "Serialize the single JSON object requested by the user as this string. Preserve all nested fields and values. No prose or code fences.",
                                            }
                                        },
                                        "required": ["json"],
                                        "additionalProperties": False,
                                    },
                                }
                            }
                        }
                        if structured
                        else {}
                    ),
                )
            elif provider == "gemini":
                sdk = genai.Client(
                    api_key=key,
                    vertexai=False,
                    http_options=types.HttpOptions(
                        base_url=endpoint,
                        httpx_client=http,
                        retry_options=types.HttpRetryOptions(attempts=1),
                        timeout=request.timeout_seconds * 1000,
                    ),
                )
                result = sdk.models.generate_content(
                    model=request.model,
                    contents=request.actor_text,
                    config=types.GenerateContentConfig(
                        max_output_tokens=request.max_output_tokens,
                        **(
                            {
                                "response_mime_type": "application/json",
                                "thinking_config": (
                                    types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
                                    if request.model == "gemini-3.8-flash"
                                    else types.ThinkingConfig(thinking_budget=0)
                                ),
                            }
                            if structured
                            else {}
                        ),
                    ),
                )
            elif provider == "mistral":
                sdk = Mistral(
                    api_key=key,
                    server_url=endpoint,
                    client=http,
                    retry_config=None,
                    timeout_ms=request.timeout_seconds * 1000,
                )
                result = sdk.chat.complete(
                    model=request.model,
                    messages=[{"role": "user", "content": request.actor_text}],
                    max_tokens=request.max_output_tokens,
                    retries=None,
                )
            else:
                sdk = OpenAI(
                    api_key=key,
                    base_url=endpoint,
                    http_client=http,
                    max_retries=0,
                )
                result = sdk.chat.completions.create(
                    model=request.model,
                    messages=[{"role": "user", "content": request.actor_text}],
                    max_tokens=request.max_output_tokens,
                )
            outcome = normalized(provider, result.model_dump(mode="json", warnings=False))
            if structured and provider == "anthropic" and outcome.status == "completed":
                # A closed string envelope supports arbitrary caller JSON without
                # restricting task-specific dictionary keys or exposing private schemas.
                # Only decode exact valid JSON; never extract an action from prose.
                try:
                    envelope = json.loads(outcome.text)
                    if isinstance(envelope, dict) and set(envelope) == {"json"}:
                        payload = json.loads(envelope["json"])
                        if isinstance(payload, dict):
                            outcome = replace(outcome, text=json.dumps(payload, allow_nan=False))
                except (ValueError, TypeError):
                    pass  # Retain malformed output for the caller's existing failure handling.
            return outcome
        except Exception as exc:
            # Never expose exception strings: SDK errors may include credentials/raw body.
            name = type(exc).__name__
            status = observed.get("status") or getattr(exc, "status_code", None)
            if isinstance(exc, httpx.TransportError) or "Timeout" in name or "Connection" in name:
                return Result("execution_unknown", error_code="ambiguous_dispatch")
            if status in (401, 403):
                return Result("failed_operational", error_code="unauthorized")
            if status == 404:
                return Result("failed_operational", error_code="model_unavailable")
            if status == 429:
                return Result("failed_operational", error_code="rate_limited")
            if status and status >= 500:
                # Keep bounded protocol codes for diagnosis, never provider messages,
                # headers or raw error bodies (which can contain submitted secrets).
                diagnostic = {}
                if type(status) is int and 500 <= status <= 599:
                    diagnostic["provider_http_status"] = status
                raw = observed.get("body")
                error = raw.get("error") if isinstance(raw, dict) else None
                rpc_status = error.get("status") if isinstance(error, dict) else None
                if provider == "gemini" and rpc_status in (
                    "INTERNAL",
                    "UNAVAILABLE",
                    "DEADLINE_EXCEEDED",
                    "UNKNOWN",
                ):
                    diagnostic["provider_status"] = rpc_status
                return Result(
                    "execution_unknown",
                    usage=diagnostic or None,
                    error_code="provider_error_after_dispatch",
                )
            # Mistral's generated schema requires usage even when a transport omits it.
            # Preserve usable final text while explicitly retaining unknown usage/cost.
            raw = observed.get("body")
            if (
                provider == "mistral"
                and status == 200
                and isinstance(raw, dict)
                and "usage" not in raw
            ):
                return normalized(provider, raw)
            return Result("failed_operational", error_code="malformed_provider_response")


def execute_marketing(request: ActorRequest):
    """Server-only transport; caller must commit authorization, intent and reservation first."""
    if (
        request.model != "gpt-6-sol"
        or len(request.actor_text.encode("utf-8")) > 100000
        or request.max_output_tokens != 8192
    ):
        raise ValueError("Unqualified marketing request")
    present, _ = secret_presence("openai")
    if not present:
        return Result("failed_operational", error_code="secret_unavailable")
    name = PROVIDERS["openai"][1]
    key = os.environ.get(name)
    if not key:
        key = (ROOT / os.environ[name + "_FILE"]).read_text().strip()
    try:
        with httpx.Client(timeout=600, follow_redirects=False, trust_env=False) as http:
            sdk = OpenAI(
                api_key=key, base_url=PROVIDERS["openai"][2], http_client=http, max_retries=0
            )
            response = sdk.responses.create(
                model="gpt-6-sol",
                input=[{"role": "user", "content": request.actor_text}],
                max_output_tokens=8192,
                reasoning={"effort": "medium"},
                store=False,
                service_tier="default",
                text={"format": {"type": "json_object"}},
            )
            return normalized("openai", response.model_dump(mode="json", warnings=False))
    except Exception:
        # Retain the full reservation and never retry an ambiguous paid dispatch.
        return Result("execution_unknown", error_code="provider_dispatch_uncertain")
