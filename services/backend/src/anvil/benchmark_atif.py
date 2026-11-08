"""Redacted actual tool trajectory; no hidden reasoning or evaluator inputs."""

import json
import subprocess

from anvil.config import ROOT
from anvil.harbor_worker import child_environment


def project(conversation, session):
    steps = []
    for number, turn in enumerate(conversation["turns"], 1):
        steps.append(
            {
                "step_id": number,
                "source": "agent",
                "message": turn["text"],
                "llm_call_count": 0,
                "tool_calls": [
                    {
                        "tool_call_id": c["call_id"],
                        "function_name": c["name"],
                        "arguments": c["arguments"] or {},
                    }
                    for c in turn["calls"]
                ]
                or None,
                "observation": {
                    "results": [
                        {
                            "source_call_id": o["call_id"],
                            "content": json.dumps(
                                {"value": o["value"], "error": o["error"]}, allow_nan=False
                            ),
                        }
                        for o in turn["observations"]
                    ]
                }
                if turn["observations"]
                else None,
            }
        )
    return {
        "schema_version": "ATIF-v1.8",
        "session_id": session,
        "agent": {
            "name": "anvil-offline-sdk-conformance",
            "version": "1.0.0",
            "model_name": conversation["model_id"],
            "extra": {
                "provider": conversation["provider"],
                "origin": "original_synthetic_fixture",
                "measured_model_performance": False,
            },
        },
        "steps": steps,
        "notes": "Original scripted offline SDK conformance. No paid inference; not model performance. User prompt and private evaluator content are omitted. No hidden reasoning is retained.",
    }


def validate(value, home):
    raw = json.dumps(value, allow_nan=False).encode()
    if len(raw) > 2_000_000:
        raise ValueError("ATIF bound")
    environment = child_environment(home)
    environment["PYTHONPATH"] = str(ROOT / "services/harbor/src")
    process = subprocess.run(
        [str(ROOT / ".local/harbor-venv/bin/python"), "-m", "anvil_harbor.atif"],
        input=raw,
        env=environment,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if process.returncode or len(process.stdout) > 2_000_000:
        raise ValueError("Pinned Harbor ATIF validation failed")
    return json.loads(process.stdout)
