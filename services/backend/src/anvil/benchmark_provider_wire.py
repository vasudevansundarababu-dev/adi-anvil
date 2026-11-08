"""Isolated real-SDK wire profile for offline SME contracts; no live entry point."""

import json
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from anthropic import Anthropic
from google import genai
from google.genai import types
from openai import OpenAI

from anvil.providers import PROVIDERS
from anvil.workspace_adapter_contracts import bytes_echo, contains_secret

CONTRACT_KEY = "anvil-offline-contract-only"
PROFILE = "anvil-sme-native-tools-offline-v1"


@dataclass(frozen=True)
class WireReply:
    data: dict | None = None
    status: str = "completed"
    error_code: str | None = None


def extend_history(provider, history, replay, observations):
    values = [o.model_dump() for o in observations]
    if provider == "openai":
        history.extend(replay)
        history.extend(
            {
                "type": "function_call_output",
                "call_id": o["call_id"],
                "output": json.dumps(o, allow_nan=False),
            }
            for o in values
        )
    elif provider == "anthropic":
        history.append({"role": "assistant", "content": replay})
        history.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": o["call_id"],
                        "is_error": o["error"] is not None,
                        "content": json.dumps(o, allow_nan=False),
                    }
                    for o in values
                ],
            }
        )
    else:
        history.append(replay)
        history.append(
            {
                "role": "user",
                "parts": [
                    {"function_response": {"id": o["call_id"], "name": o["name"], "response": o}}
                    for o in values
                ],
            }
        )


def request_turn(binding, history, tools, limits, transport, timeout):
    if type(transport) is not httpx.MockTransport:
        raise ValueError("mock_transport_required")
    provider = binding.provider
    flags = {"attempts": 0, "sent": False, "blocked": False, "unsafe": False}
    status = None
    endpoint = PROVIDERS[provider][2]
    expected_path = {
        "openai": "/v1/responses",
        "anthropic": "/v1/messages",
        "gemini": "/v1beta/models/" + quote(binding.model_id, safe="") + ":generateContent",
    }[provider]

    class Guard(httpx.BaseTransport):
        def handle_request(self, req):
            flags["attempts"] += 1
            header = {
                "openai": "authorization",
                "anthropic": "x-api-key",
                "gemini": "x-goog-api-key",
            }[provider]
            expected = "Bearer " + CONTRACT_KEY if provider == "openai" else CONTRACT_KEY
            if (
                flags["attempts"] != 1
                or req.method != "POST"
                or req.url.scheme != "https"
                or req.url.host != httpx.URL(endpoint).host
                or req.url.port not in (None, 443)
                or req.url.path != expected_path
                or req.url.query
                or req.url.fragment
                or req.headers.get(header) != expected
                or any(
                    req.headers.get(h)
                    for h in {"authorization", "x-api-key", "x-goog-api-key"} - {header}
                )
                or len(req.content) > limits.max_input_bytes
                or bytes_echo(req.content, CONTRACT_KEY)
            ):
                flags["blocked"] = True
                raise httpx.TransportError("offline_contract_request_blocked", request=req)
            flags["sent"] = True
            response = transport.handle_request(req)
            data = bytearray()
            try:
                for chunk in response.iter_bytes():
                    if len(data) + len(chunk) > 2_000_000:
                        flags["unsafe"] = True
                        raise httpx.TransportError("offline_response_bound", request=req)
                    data.extend(chunk)
                if bytes_echo(bytes(data), CONTRACT_KEY) or contains_secret(
                    dict(response.headers), CONTRACT_KEY
                ):
                    flags["unsafe"] = True
                    raise httpx.TransportError("offline_credential_echo", request=req)
                return httpx.Response(
                    response.status_code, headers=response.headers, content=bytes(data), request=req
                )
            finally:
                response.close()

    def observe(response):
        nonlocal status
        status = response.status_code

    try:
        with httpx.Client(
            transport=Guard(),
            trust_env=False,
            follow_redirects=False,
            timeout=timeout,
            event_hooks={"response": [observe]},
        ) as http:
            if provider == "openai":
                sdk = OpenAI(
                    api_key=CONTRACT_KEY, base_url=endpoint, http_client=http, max_retries=0
                )
                reply = sdk.responses.create(
                    model=binding.model_id,
                    input=history,
                    max_output_tokens=binding.max_output_tokens,
                    store=False,
                    tools=[
                        {
                            "type": "function",
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                            "strict": False,
                        }
                        for t in tools
                    ],
                )
            elif provider == "anthropic":
                sdk = Anthropic(
                    api_key=CONTRACT_KEY, base_url=endpoint, http_client=http, max_retries=0
                )
                reply = sdk.messages.create(
                    model=binding.model_id,
                    messages=history,
                    max_tokens=binding.max_output_tokens,
                    tools=[
                        {"name": t.name, "description": t.description, "input_schema": t.parameters}
                        for t in tools
                    ],
                )
            else:
                sdk = genai.Client(
                    api_key=CONTRACT_KEY,
                    vertexai=False,
                    http_options=types.HttpOptions(
                        base_url=endpoint,
                        httpx_client=http,
                        timeout=int(timeout * 1000),
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                )
                reply = sdk.models.generate_content(
                    model=binding.model_id,
                    contents=history,
                    config=types.GenerateContentConfig(
                        max_output_tokens=binding.max_output_tokens,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True
                        ),
                        tools=[
                            types.Tool(
                                function_declarations=[
                                    types.FunctionDeclaration(
                                        name=t.name,
                                        description=t.description,
                                        parameters_json_schema=t.parameters,
                                    )
                                    for t in tools
                                ]
                            )
                        ],
                    ),
                )
            data = reply.model_dump(mode="json", exclude_none=True, warnings=False)
            if (
                not flags["sent"]
                or flags["attempts"] != 1
                or flags["blocked"]
                or flags["unsafe"]
                or contains_secret(data, CONTRACT_KEY)
            ):
                return WireReply(status="execution_unknown", error_code="unsafe_response")
            return WireReply(data=data)
    except Exception:
        if flags["unsafe"]:
            return WireReply(status="execution_unknown", error_code="unsafe_response")
        if not flags["sent"]:
            return WireReply(status="failed_operational", error_code="request_not_dispatched")
        if status in (401, 403, 404, 429) or status and 300 <= status < 400:
            return WireReply(status="failed_operational", error_code="provider_rejected")
        return WireReply(status="execution_unknown", error_code="ambiguous_dispatch_no_retry")
