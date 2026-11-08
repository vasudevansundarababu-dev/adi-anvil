"""Original scripted software-conformance transport, never model performance.

Only the vendor HTTP boundary is controlled. SDK serialization, native stdio
tools, bounded output writes, capture and the separate evaluator remain real.
The transport sees actor items and actual tool observations, never private rules.
"""

import json

import httpx

from anvil.benchmark_bundle import canonical_path
from anvil.benchmark_conversation import Tool, run_contract


def reply(provider, model, calls):
    if provider == "openai":
        return {
            "id": "offline-conformance",
            "object": "response",
            "created_at": 1,
            "model": model,
            "status": "completed",
            "output": [
                {
                    "id": "fc-" + key,
                    "type": "function_call",
                    "call_id": key,
                    "name": name,
                    "arguments": json.dumps(args),
                    "status": "completed",
                }
                for key, name, args in calls
            ]
            or [
                {
                    "id": "offline-final",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Offline software conformance complete",
                            "annotations": [],
                        }
                    ],
                }
            ],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }
    if provider == "anthropic":
        return {
            "id": "offline-conformance",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [
                {"type": "tool_use", "id": key, "name": name, "input": args}
                for key, name, args in calls
            ]
            or [{"type": "text", "text": "Offline software conformance complete"}],
            "stop_reason": "tool_use" if calls else "end_turn",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
    return {
        "responseId": "offline-conformance",
        "modelVersion": model,
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {"id": key, "name": name, "args": args},
                            "thoughtSignature": "AQID",
                        }
                        for key, name, args in calls
                    ]
                    or [{"text": "Offline software conformance complete"}],
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0, "totalTokenCount": 0},
    }


WRITE = """import json,sys
from pathlib import Path
request=json.load(sys.stdin)
path=Path('/workspace/output')/request['path']
with path.open('x') as stream:stream.write(request['text'])
print(json.dumps({'written':request['path']}))
"""


def driver(binding, limits, *, dispatch_check):
    def execute(docker, container, task, native_tools, items):
        if not 1 <= len(items) <= 100 or any(set(item) != {"id", "n"} for item in items):
            raise ValueError("Unsupported fictional actor item profile")
        declarations = {output.path: output.max_bytes for output in task.outputs}
        schema = json.loads(docker.execute(container, ["cat", "/workspace/inputs/tools.json"]))
        tools = [
            Tool(name=t["name"], description=t["description"], parameters=t["inputSchema"])
            for t in schema["tools"]
        ]
        tools.append(
            Tool(
                name="write_artifact",
                description="Write a declared actor output once",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["path", "text"],
                    "additionalProperties": False,
                },
            )
        )
        values, offset, written, turns = {}, 0, False, 0

        class Mediator:
            def call(self, name, arguments, *, timeout):
                if name == "square":
                    result = native_tools.call(name, arguments)
                    # Match only the actor-visible inputs, not evaluator oracles.
                    for item in items:
                        if item["n"] == arguments["n"]:
                            values[item["id"]] = result
                    return result
                if name != "write_artifact" or set(arguments) != {"path", "text"}:
                    raise ValueError("Undeclared actor tool")
                path = canonical_path(arguments["path"])
                if (
                    path not in declarations
                    or "/" in path
                    or type(arguments["text"]) is not str
                    or len(arguments["text"].encode()) > declarations[path]
                ):
                    raise ValueError("Output exceeds frozen declaration")
                return json.loads(
                    docker.execute(
                        container,
                        ["python", "-c", WRITE],
                        data=json.dumps(arguments, allow_nan=False).encode(),
                    )
                )

        def transport(request):
            nonlocal offset, written, turns
            dispatch_check()
            if (
                request.method != "POST"
                or request.url.scheme != "https"
                or request.url.host != httpx.URL(binding.destination).host
            ):
                raise ValueError("Offline SDK destination mismatch")
            turns += 1
            if offset < len(items):
                batch = items[offset : offset + limits.max_tool_calls]
                calls = [
                    ("square-" + str(offset + i), "square", {"n": item["n"]})
                    for i, item in enumerate(batch)
                ]
                offset += len(batch)
            elif not written:
                calls = [
                    (
                        "write-answers",
                        "write_artifact",
                        {"path": "answers.json", "text": json.dumps(values, allow_nan=False)},
                    ),
                    (
                        "write-report",
                        "write_artifact",
                        {
                            "path": "report.md",
                            "text": "Original scripted offline conformance. Not model performance.",
                        },
                    ),
                ]
                written = True
            else:
                calls = []
            return httpx.Response(200, json=reply(binding.provider, binding.model_id, calls))

        actor_text = (
            "Original fictional arithmetic software conformance. Use declared tools on these actor inputs: "
            + json.dumps(items)
        )
        result = run_contract(
            binding, actor_text, tools, Mediator(), httpx.MockTransport(transport), limits=limits
        )
        return {
            "status": result.status,
            "error_code": result.error_code,
            "provider": binding.provider,
            "model_id": binding.model_id,
            "turn_count": turns,
            "origin": "original_synthetic_fixture",
            "transport": "offline_contract",
            "measured_model_performance": False,
            "turns": [
                {
                    "text": turn.text,
                    "calls": [c.model_dump(mode="json") for c in turn.calls],
                    "observations": [o.model_dump(mode="json") for o in turn.observations],
                }
                for turn in result.turns
            ],
        }

    return execute
