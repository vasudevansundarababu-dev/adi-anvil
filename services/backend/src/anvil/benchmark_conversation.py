"""Typed, bounded offline native-tool conversation. Never creates paid authority."""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx
from pydantic import ConfigDict, Field, field_validator

from anvil.benchmark_provider_wire import CONTRACT_KEY, PROFILE, extend_history, request_turn
from anvil.import_sandbox import schema_check
from anvil.providers import PROVIDERS
from anvil.schemas import Strict
from anvil.task_parser import json_value
from anvil.workspace_adapter_contracts import ENV_OVERRIDES, contains_secret


class Frozen(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Binding(Frozen):
    provider: Literal["openai", "anthropic", "gemini"]
    model_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$")
    destination: str = Field(min_length=1, max_length=500)
    max_output_tokens: int = Field(default=2048, ge=1, le=8192, strict=True)


class Limits(Frozen):
    max_turns: int = Field(default=15, ge=1, le=15, strict=True)
    max_tool_calls: int = Field(default=8, ge=1, le=8, strict=True)
    max_argument_bytes: int = Field(default=65536, ge=1, le=65536, strict=True)
    max_result_bytes: int = Field(default=65536, ge=256, le=65536, strict=True)
    max_input_bytes: int = Field(default=100000, ge=1, le=1000000, strict=True)
    max_final_bytes: int = Field(default=65536, ge=1, le=65536, strict=True)
    task_timeout_seconds: int = Field(default=600, ge=1, le=1800, strict=True)
    provider_timeout_seconds: int = Field(default=60, ge=1, le=120, strict=True)
    tool_timeout_seconds: int = Field(default=60, ge=1, le=60, strict=True)


class Tool(Frozen):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    description: str = Field(max_length=2000)
    parameters: dict

    @field_validator("parameters")
    @classmethod
    def supported_schema(cls, value):
        json_value(encoded(value))
        allowed = {
            "type",
            "properties",
            "required",
            "additionalProperties",
            "items",
            "enum",
            "const",
            "minimum",
            "maximum",
            "minItems",
            "maxItems",
            "minLength",
            "maxLength",
            "description",
            "title",
        }

        def check(node):
            if not isinstance(node, dict) or set(node) - allowed:
                raise ValueError("Unsupported tool schema")
            if node.get("type") not in {
                None,
                "object",
                "array",
                "string",
                "integer",
                "number",
                "boolean",
                "null",
            }:
                raise ValueError("Unsupported schema type")
            properties = node.get("properties", {})
            required = node.get("required", [])
            if (
                not isinstance(properties, dict)
                or not isinstance(required, list)
                or any(type(x) is not str for x in required)
                or len(set(required)) != len(required)
                or not set(required) <= set(properties)
            ):
                raise ValueError("Invalid schema properties")
            for item in properties.values():
                check(item)
            if "items" in node:
                check(node["items"])
            extra = node.get("additionalProperties", True)
            if isinstance(extra, dict):
                check(extra)
            elif type(extra) is not bool:
                raise ValueError("Invalid additional properties")
            for key in ("minItems", "maxItems", "minLength", "maxLength"):
                if key in node and (type(node[key]) is not int or node[key] < 0):
                    raise ValueError("Invalid schema bound")
            for key in ("minimum", "maximum"):
                if key in node and type(node[key]) not in (int, float):
                    raise ValueError("Invalid numeric bound")

        if value.get("type") != "object":
            raise ValueError("Tool arguments must be an object")
        check(value)
        return value


class Call(Frozen):
    call_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    arguments: dict | None
    argument_bytes: int = Field(ge=0, strict=True)


class Observation(Frozen):
    call_id: str
    name: str
    value: object = None
    error: str | None = None


class Usage(Frozen):
    input_tokens: int | None = Field(default=None, ge=0, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, strict=True)
    total_tokens: int | None = Field(default=None, ge=0, strict=True)
    cached_tokens: int | None = Field(default=None, ge=0, strict=True)
    reasoning_tokens: int | None = Field(default=None, ge=0, strict=True)


class Content(Frozen):
    type: Literal["text", "tool_call"]
    text: str | None = None
    call_id: str | None = None


@dataclass
class Turn:
    response_id: str
    model_returned: str
    finish_reason: str
    text: str
    calls: list[Call]
    usage: Usage | None
    observations: list[Observation] = field(default_factory=list)
    content: list[Content] = field(default_factory=list)


@dataclass
class ConversationResult:
    status: str
    turns: list[Turn]
    text: str | None = None
    error_code: str | None = None
    origin: str = "sdk_mock"
    profile: str = PROFILE
    actual_cost_micro_usd: None = None


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def _arguments(value):
    try:
        if isinstance(value, str):
            value = json_value(value)
        return value if isinstance(value, dict) and encoded(value) else None
    except (ValueError, TypeError, RecursionError):
        return None


def _call(identifier, name, value):
    size = len(value.encode()) if isinstance(value, str) else len(encoded(value))
    return Call(call_id=identifier, name=name, arguments=_arguments(value), argument_bytes=size)


def _normalize(provider, data, number):
    text, calls, refusal = "", [], False
    content = []
    if provider == "openai":
        identifier, model, finish = data.get("id"), data.get("model"), data.get("status")
        replay = data.get("output", [])
        for part in replay:
            if part.get("type") == "function_call":
                calls.append(_call(part["call_id"], part["name"], part.get("arguments")))
                content.append(Content(type="tool_call", call_id=calls[-1].call_id))
            elif part.get("type") == "message":
                for block in part.get("content", []):
                    refusal |= block.get("type") == "refusal"
                    if block.get("type") == "output_text":
                        text += block["text"]
                        content.append(Content(type="text", text=block["text"]))
            elif part.get("type") != "reasoning":
                raise ValueError("unsupported_content")
        raw = data.get("usage")
        usage = (
            Usage(
                input_tokens=raw.get("input_tokens"),
                output_tokens=raw.get("output_tokens"),
                total_tokens=raw.get("total_tokens"),
                cached_tokens=(raw.get("input_tokens_details") or {}).get("cached_tokens"),
                reasoning_tokens=(raw.get("output_tokens_details") or {}).get("reasoning_tokens"),
            )
            if raw is not None
            else None
        )
        terminal = (
            "refused"
            if refusal
            else "truncated"
            if finish == "incomplete"
            else "completed"
            if finish == "completed"
            else "execution_unknown"
        )
    elif provider == "anthropic":
        identifier, model, finish = data.get("id"), data.get("model"), data.get("stop_reason")
        replay = data.get("content", [])
        for part in replay:
            if part.get("type") == "tool_use":
                calls.append(_call(part["id"], part["name"], part.get("input")))
                content.append(Content(type="tool_call", call_id=calls[-1].call_id))
            elif part.get("type") == "text":
                text += part["text"]
                content.append(Content(type="text", text=part["text"]))
            elif part.get("type") not in {"thinking", "redacted_thinking"}:
                raise ValueError("unsupported_content")
        raw = data.get("usage")
        usage = (
            Usage(
                input_tokens=raw.get("input_tokens"),
                output_tokens=raw.get("output_tokens"),
                cached_tokens=raw.get("cache_read_input_tokens"),
            )
            if raw is not None
            else None
        )
        terminal = (
            "refused"
            if finish == "refusal"
            else "truncated"
            if finish in {"max_tokens", "model_context_window_exceeded"}
            else "completed"
            if finish in {"end_turn", "tool_use"}
            else "execution_unknown"
        )
        if bool(calls) != (finish == "tool_use") and terminal == "completed":
            raise ValueError("finish_call_mismatch")
    else:
        identifier, model = data.get("response_id"), data.get("model_version")
        candidates = data.get("candidates", [])
        if len(candidates) != 1:
            raise ValueError("candidate_count")
        candidate = candidates[0]
        finish, replay = candidate.get("finish_reason"), candidate.get("content", {})
        for index, part in enumerate(replay.get("parts", [])):
            if "function_call" in part:
                call = part["function_call"]
                # Gemini may omit IDs; synthesize stable turn/part correlation only.
                identifier_call = call.get("id") or f"anvil-{number}-{index}"
                calls.append(_call(identifier_call, call["name"], call.get("args")))
                content.append(Content(type="tool_call", call_id=calls[-1].call_id))
            elif "text" in part and not part.get("thought"):
                text += part["text"]
                content.append(Content(type="text", text=part["text"]))
            elif set(part) - {"thought", "text", "thought_signature"}:
                raise ValueError("unsupported_content")
        raw = data.get("usage_metadata")
        usage = (
            Usage(
                input_tokens=raw.get("prompt_token_count"),
                output_tokens=raw.get("candidates_token_count"),
                total_tokens=raw.get("total_token_count"),
                cached_tokens=raw.get("cached_content_token_count"),
                reasoning_tokens=raw.get("thoughts_token_count"),
            )
            if raw is not None
            else None
        )
        terminal = (
            "refused"
            if finish in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"}
            or (data.get("prompt_feedback") or {}).get("block_reason")
            else "truncated"
            if finish == "MAX_TOKENS"
            else "completed"
            if finish == "STOP"
            else "execution_unknown"
        )
    if (
        not isinstance(identifier, str)
        or not identifier
        or len(identifier) > 200
        or not isinstance(model, str)
        or not model
    ):
        raise ValueError("missing_response_binding")
    return (
        Turn(identifier, model, str(finish), text, calls, usage, content=content),
        replay,
        terminal,
    )


def run_contract(binding, actor_text, tools, mediator, transport, *, limits=None):
    """Host-only offline qualification; no DB, credential lookup, network or admission."""
    if type(transport) is not httpx.MockTransport:
        raise ValueError("mock_transport_required")
    binding = Binding.model_validate(
        binding.model_dump() if isinstance(binding, Binding) else binding
    )
    limits = Limits.model_validate((limits or Limits()).model_dump())
    tools = [Tool.model_validate(t.model_dump()) for t in tools]
    turns = []

    def outcome(status, code=None, text=None):
        return ConversationResult(status, turns, text, code)

    if any(os.environ.get(k) for k in ENV_OVERRIDES):
        return outcome("failed_operational", "sdk_environment_override")
    if (
        binding.destination != PROVIDERS[binding.provider][2]
        or not isinstance(actor_text, str)
        or not actor_text.strip()
        or len(actor_text.encode()) > limits.max_input_bytes
        or not 1 <= len(tools) <= 32
        or len({t.name for t in tools}) != len(tools)
        or contains_secret((actor_text, [t.model_dump() for t in tools]), CONTRACT_KEY)
    ):
        return outcome("failed_operational", "actor_or_binding_blocked")
    declared = {t.name: t for t in tools}
    history = (
        [{"role": "user", "parts": [{"text": actor_text}]}]
        if binding.provider == "gemini"
        else [{"role": "user", "content": actor_text}]
    )
    deadline, seen = time.monotonic() + limits.task_timeout_seconds, set()
    for number in range(1, limits.max_turns + 1):
        if any(os.environ.get(k) for k in ENV_OVERRIDES):
            return outcome("failed_operational", "sdk_environment_override")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return outcome("deadline", "task_deadline")
        reply = request_turn(
            binding,
            history,
            tools,
            limits,
            transport,
            min(limits.provider_timeout_seconds, remaining),
        )
        if reply.data is None:
            return outcome(reply.status, reply.error_code)
        try:
            turn, replay, state = _normalize(binding.provider, reply.data, number)
            if turn.model_returned != binding.model_id:
                return outcome("execution_unknown", "model_mismatch")
            if time.monotonic() >= deadline:
                return outcome("deadline", "task_deadline")
            if len(encoded(turn.text)) > limits.max_final_bytes:
                return outcome("execution_unknown", "response_text_bound")
            if len(turn.calls) > limits.max_tool_calls:
                return outcome("execution_unknown", "tool_call_limit")
            ids = [c.call_id for c in turn.calls]
            if len(set(ids)) != len(ids):
                return outcome("execution_unknown", "duplicate_tool_call_id")
            if seen.intersection(ids):
                return outcome("execution_unknown", "reused_tool_call_id")
            if any(c.argument_bytes > limits.max_argument_bytes for c in turn.calls):
                return outcome("execution_unknown", "argument_bound")
        except (ValueError, TypeError, KeyError, RecursionError):
            return outcome("execution_unknown", "malformed_provider_response")
        turns.append(turn)
        if state != "completed":
            return outcome(state, "provider_" + state)
        if not turn.calls:
            return (
                outcome("completed", text=turn.text)
                if turn.text.strip()
                else outcome("execution_unknown", "empty_provider_response")
            )
        seen.update(ids)
        for call in turn.calls:
            error, value = None, None
            if call.name not in declared:
                error = "undeclared_tool"
            elif call.arguments is None:
                error = "invalid_arguments"
            else:
                try:
                    schema_check(call.arguments, declared[call.name].parameters)
                except (ValueError, TypeError, RecursionError):
                    error = "invalid_arguments"
            if error is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return outcome("deadline", "task_deadline")
                try:
                    value = mediator.call(
                        call.name,
                        call.arguments,
                        timeout=min(remaining, limits.tool_timeout_seconds),
                    )
                    if contains_secret(value, CONTRACT_KEY):
                        return outcome("execution_unknown", "unsafe_tool_response")
                    if len(encoded(value)) > limits.max_result_bytes:
                        return outcome("failed_operational", "tool_result_bound")
                except TimeoutError:
                    return outcome("failed_operational", "tool_timeout_no_retry")
                except Exception:
                    value = None
                    error = "tool_execution_error"
                if time.monotonic() >= deadline:
                    return outcome("deadline", "task_deadline")
            observation = Observation(
                call_id=call.call_id, name=call.name, value=value, error=error
            )
            if len(encoded(observation.model_dump())) > limits.max_result_bytes:
                return outcome("failed_operational", "tool_result_bound")
            turn.observations.append(observation)
        extend_history(binding.provider, history, replay, turn.observations)
    return outcome("turn_limit", "inference_turn_limit")
