"""Real SDK requests and real local output files, controlled vendor boundary only."""

import json

import httpx
import pytest

from anvil.benchmark_conversation import Binding, Tool, run_contract
from anvil.benchmark_offline_actor import reply
from anvil.benchmark_tool_gateway import ArtifactTools
from anvil.providers import PROVIDERS


@pytest.mark.parametrize("provider", ("openai", "anthropic", "gemini"))
def test_offline_reply_survives_actual_sdk_tool_roundtrip(provider, tmp_path):
    root = tmp_path / "owned-output"
    root.mkdir(mode=0o700)
    mediator = ArtifactTools(root, {"report.md": 1024})
    tool = Tool(
        name="write_artifact",
        description="Write declared output once",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}, "text": {"type": "string"}},
            "required": ["path", "text"],
            "additionalProperties": False,
        },
    )
    requests = []
    binding = Binding(
        provider=provider, model_id="fictional-software-only", destination=PROVIDERS[provider][2]
    )

    def send(request):
        requests.append(request)
        assert request.url.host == httpx.URL(binding.destination).host
        assert json.loads(request.content)
        calls = (
            [
                (
                    "write-1",
                    "write_artifact",
                    {"path": "report.md", "text": "Clearly fictional SDK conformance"},
                )
            ]
            if len(requests) == 1
            else []
        )
        return httpx.Response(200, json=reply(provider, binding.model_id, calls))

    result = run_contract(
        binding,
        "Original fictional software inputs only",
        [tool],
        mediator,
        httpx.MockTransport(send),
    )
    assert result.status == "completed" and len(requests) == 2
    assert (root / "report.md").read_text() == "Clearly fictional SDK conformance"
