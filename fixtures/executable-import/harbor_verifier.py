"""Trusted fixture verifier entry point, injected after the scripted actor finishes."""

import json
from pathlib import Path

from reference_evaluator import evaluate

config = json.loads(Path("/tests/golden.json").read_text())
output = json.loads(Path("/workspace/output.json").read_text()) if Path("/workspace/output.json").exists() else None
if output is not None:
    observed_tools = json.loads(Path("/workspace/output/tool_interfaces.json").read_text())
    assert observed_tools == config["tools"], "Supplied MCP tool interface mismatch"
calls = [json.loads(line) for line in Path("/workspace/output/events.jsonl").read_text().splitlines()] if Path("/workspace/output/events.jsonl").exists() else []
result = evaluate(config["domain"], config["data"], output, calls)
Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
Path("/logs/verifier/reward.txt").write_text(str(result["reward_bps"] / 10000))
Path("/logs/verifier/diagnostics.json").write_text(json.dumps(result))
