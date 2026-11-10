"""Historical observable facts, never qualification or model-performance authority.

The audit view uses current artifact-specific private read duties. It does not
reactivate revoked signers, edit source reviews, or make historical control
trials eligible for model leaderboards. Operational qualification endpoints
retain all of their stronger current qualification/trust checks unchanged.
"""

import hashlib
import json
from decimal import Decimal

import rfc8785
from fastapi import HTTPException

from anvil.benchmark_qualification_evidence import public_projection
from anvil.benchmark_storage import read_private_record
from anvil.db import one


def metadata(c, trace_id):
    row = one(
        c,
        "SELECT t.*,a.object_key,a.sha256,a.byte_size,a.classification,a.scan_status "
        "FROM anvil.benchmark_trace_audit t JOIN anvil.artifacts a "
        "ON a.project_id=t.project_id AND a.id=t.artifact_id WHERE t.id=%s",
        (trace_id,),
    )
    if row is None:
        raise HTTPException(404, "Trace not found or current evidence duty is unavailable")
    if row["classification"] != "benchmark_trace" or row["sha256"] != row["source_record_sha256"]:
        raise HTTPException(409, "Historical trace receipt binding changed")
    return row


def summary(row):
    value = row["metadata"]
    points = Decimal(str(value["points"]))
    possible = Decimal(str(value["possible_points"]))
    if (
        not points.is_finite()
        or not possible.is_finite()
        or not 0 <= points <= possible
        or possible <= 0
    ):
        raise ValueError("Invalid historical observations")
    mode = value["mode"]
    expected_negative = mode in {"empty", "guardrail"}
    return {
        "id": str(row["id"]),
        "kind": "historical_control",
        "label": value["task_id"] + " · " + mode.replace("_", " "),
        "task_key": value["task_key"],
        "task_label": value["task_id"],
        "model_key": None,
        "model_label": "Scripted offline control (not a model measurement)",
        "run_id": None,
        "state": "expected_negative_control" if expected_negative else "completed_control",
        "validity": "software_conformance_only",
        "origin": "original_synthetic_software_conformance",
        "environment": row["environment"],
        "recorded_at": row["recorded_at"].isoformat(),
        "duration_ms": value.get("duration_ms"),
        "points": {
            "earned_points": str(points),
            "possible_points": str(possible),
            "percent": format(points / possible * 100, ".4f"),
        },
        "official": False,
        "review_state": "historical_control_not_current_source_authority",
        "failure_tags": ["intentional_negative_control"] if expected_negative else [],
        "severity": "none",
        "severity_basis": "intentional software control; not a model failure or calibrated risk",
        "evidence_available": True,
        "source_sha256": row["source_record_sha256"],
    }


def read(row):
    if not 0 < row["byte_size"] <= 2097152:
        raise ValueError("Historical receipt exceeds read bound")
    record = {**row, "id": row["artifact_id"]}
    raw = read_private_record(record)
    if hashlib.sha256(raw).hexdigest() != row["source_record_sha256"]:
        raise ValueError("Historical receipt changed")
    value = json.loads(raw)
    expected = row["metadata"]
    for key in ("task_id", "mode", "points", "possible_points", "origin"):
        if value[key] != expected[key]:
            raise ValueError("Historical receipt observations changed")
    capture = public_projection(value.get("public_capture"))
    if capture is not None:
        sealed = {
            "files": [
                {key: item[key] for key in ("path", "sha256", "byte_size")}
                for item in capture["outputs"]
            ],
            "missing": capture["missing"],
        }
        if hashlib.sha256(rfc8785.dumps(sealed)).hexdigest() != value["seal_sha256"]:
            raise ValueError("Historical public capture seal changed")
    steps = [
        {
            "id": "context",
            "kind": "context",
            "label": "Recorded execution context",
            "status": "historical",
            "content": "Original fictional software control. Timestamp is the recorded baseline window start; individual trial wall-clock start was not persisted. No user prompt or hidden reasoning is reconstructed.",
        }
    ]
    atif = value.get("atif")
    if atif is not None:
        if atif.get("schema_version") != "ATIF-v1.8" or len(atif.get("steps", [])) > 15:
            raise ValueError("Unsupported stored trajectory")
        for number, step in enumerate(atif["steps"]):
            if (
                len(step.get("tool_calls") or []) > 8
                or len((step.get("observation") or {}).get("results", [])) > 8
            ):
                raise ValueError("Stored per-turn trajectory exceeds declared bound")
            message = step.get("message", "")
            if not isinstance(message, str) or len(message.encode()) > 65536:
                raise ValueError("Stored observable text exceeds bound")
            steps.append(
                {
                    "id": f"message-{number}",
                    "kind": "agent_output",
                    "label": f"Offline scripted response {number + 1}",
                    "status": "observed",
                    "content": message,
                }
            )
            for call in step.get("tool_calls") or []:
                content = json.dumps(
                    {"name": call["function_name"], "arguments": call["arguments"]},
                    ensure_ascii=False,
                    allow_nan=False,
                )
                if len(content.encode()) > 65536:
                    raise ValueError("Stored tool call exceeds bound")
                steps.append(
                    {
                        "id": f"tool-{number}-{len(steps)}",
                        "kind": "tool_call",
                        "label": "Actual declared tool invocation",
                        "status": "observed",
                        "content": content,
                    }
                )
            for result in (step.get("observation") or {}).get("results", []):
                content = result["content"]
                if not isinstance(content, str) or len(content.encode()) > 65536:
                    raise ValueError("Stored tool observation exceeds bound")
                steps.append(
                    {
                        "id": f"result-{number}-{len(steps)}",
                        "kind": "tool_result",
                        "label": "Actual tool response",
                        "status": "observed",
                        "content": content,
                    }
                )
    else:
        steps.append(
            {
                "id": "tools",
                "kind": "tool_call",
                "label": "Recorded tool activity",
                "status": "observed",
                "content": f"{value.get('tool_calls', 0)} declared calls; {value.get('denied_tool_calls', 0)} denied calls. Per-call arguments were not retained in this receipt.",
            }
        )
    steps.extend(
        [
            {
                "id": "seal",
                "kind": "output",
                "label": "Stopped actor and sealed output",
                "status": "observed",
                "content": "Seal SHA-256: " + value["seal_sha256"],
            },
            {
                "id": "evaluation",
                "kind": "evaluation",
                "label": "Separate deterministic evaluator",
                "status": "observed",
                "content": f"Control observation {value['points']} / {value['possible_points']}. This is not a candidate model or judge performance score.",
            },
        ]
    )
    return {
        "steps": steps,
        "outputs": capture["outputs"] if capture else [],
        "criteria": capture["criteria"] if capture else [],
        "limitations": [
            "Historical control; qualification currency and model-ranking eligibility are not granted.",
            "Current artifact-specific access is required; source review and signer history are not rewritten.",
            *(
                []
                if capture
                else [
                    "Public output bytes were not persisted for this trajectory; no reconstruction is attempted."
                ]
            ),
        ],
    }
