"""Trusted server-only native broker. Call only after durable admission/dispatch intent.

Never receives private task references; never exposes a credential read endpoint.
The contract-test entry point remains strictly mock-only.
"""

import os
from dataclasses import asdict, replace
from urllib.parse import unquote

import httpx

from anvil import providers
from anvil.workspace_adapter_contracts import ENV_OVERRIDES, bytes_echo, contains_secret


def execute(binding, secret, request, *, transport=None, generation=False):
    provider = binding["provider"]
    key = secret.get_secret_value()
    origin = "sdk_mock" if type(transport) is httpx.MockTransport else "provider"

    def outcome(status, code):
        return providers.Result(status, usage={"dispatch_origin": origin}, error_code=code)

    if provider not in ("openai", "anthropic", "gemini") or any(
        os.environ.get(k) for k in ENV_OVERRIDES
    ):
        return outcome("failed_operational", "broker_configuration_blocked")
    if transport is not None and type(transport) is not httpx.MockTransport:
        raise ValueError("Only a MockTransport test override is supported")
    if (
        request.model != binding["model_id"]
        or binding["destination"] != providers.PROVIDERS[provider][2]
        or not 1 <= len(request.actor_text.encode("utf-8")) <= (100000 if generation else 32768)
        or not 1
        <= request.max_output_tokens
        <= min(8192 if generation else 2048, binding["max_output_tokens"])
        or contains_secret((request.actor_text, request.model), key)
    ):
        return outcome("failed_operational", "broker_request_blocked")
    inner = transport or httpx.HTTPTransport(retries=0, trust_env=False)
    flags = {"attempts": 0, "unsafe": False, "blocked": False}

    class Guard(httpx.BaseTransport):
        def close(self):
            inner.close()

        def handle_request(self, req):
            flags["attempts"] += 1
            header = {
                "openai": "authorization",
                "anthropic": "x-api-key",
                "gemini": "x-goog-api-key",
            }[provider]
            expected = "Bearer " + key if provider == "openai" else key
            path_ok = (
                req.url.path == "/v1/responses"
                if provider == "openai"
                else req.url.path == "/v1/messages"
                if provider == "anthropic"
                else req.url.path.startswith("/v1beta/models/")
                and req.url.path.endswith(":generateContent")
            )
            if (
                flags["attempts"] != 1
                or req.method != "POST"
                or req.url.scheme != "https"
                or req.url.host != httpx.URL(binding["destination"]).host
                or req.url.port not in (None, 443)
                or not path_ok
                or req.headers.get(header) != expected
                or any(
                    req.headers.get(h)
                    for h in {"authorization", "x-api-key", "x-goog-api-key"} - {header}
                )
                or key in unquote(str(req.url))
                or bytes_echo(req.content, key)
            ):
                flags["blocked"] = True
                raise httpx.TransportError("broker request blocked", request=req) from None
            try:
                response = inner.handle_request(req)
                body = response.read()
                if (
                    len(body) > 2000000
                    or bytes_echo(body, key)
                    or contains_secret(dict(response.headers), key)
                ):
                    flags["unsafe"] = True
                    response.close()
                    return httpx.Response(
                        502,
                        json={"error": {"message": "unsafe provider response suppressed"}},
                        request=req,
                    )
                return response
            except httpx.TimeoutException:
                raise httpx.ReadTimeout("provider timeout", request=req) from None
            except Exception:
                raise httpx.TransportError("provider transport failure", request=req) from None

    result = providers._execute_native(
        provider, request, Guard(), credential=secret, structured=True
    )
    if flags["unsafe"] or contains_secret(asdict(result), key):
        return outcome("execution_unknown", "unsafe_response_suppressed")
    if flags["attempts"] != 1 or flags["blocked"]:
        return outcome("execution_unknown", "dispatch_not_confirmed_no_retry")
    result = replace(result, usage={**(result.usage or {}), "dispatch_origin": origin})
    return result
