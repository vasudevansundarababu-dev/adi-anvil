"""Network-free SDK/parser protocol qualification, never model evaluation.

All replies and case identities below are manufactured software controls.
Neither these awards nor these reference identities enter a campaign result.
"""

import hashlib
import json
import sys
from importlib.metadata import version
from uuid import UUID

import httpx
from pydantic import SecretStr

from anvil import providers
from anvil.campaign_semantic_contract import Batch, prompt, validate_result
from anvil.db import digest
from anvil.native_semantic import VERSION, FixedProgram, parse_program
from anvil.praxis_generic_contract import digest as wire_digest
from anvil.qualification_resources import qualification_path, qualification_root

SCOPE = "sdk_mock_software_protocol_only"
PACKAGES = (
    "openai",
    "anthropic",
    "google-genai",
    "mistralai",
    "httpx",
    "pydantic",
    "rfc8785",
    "fastapi",
)


def source_hash():
    root = qualification_root()
    return digest(
        {
            "files": {
                name: hashlib.sha256(
                    qualification_path(root, "services/backend/src/anvil/" + name).read_bytes()
                ).hexdigest()
                for name in (
                    "native_semantic_validation.py",
                    "qualification_resources.py",
                    "native_semantic.py",
                    "providers.py",
                    "campaign_semantic_contract.py",
                    "schemas.py",
                    "praxis_generic_contract.py",
                    "dataset_export_contract.py",
                    "golden_targets.py",
                    "golden_evaluator_register.json",
                    "golden_skill_metadata.json",
                    "diagnostic_measures.py",
                    "diagnostic_effects.py",
                    "praxis_case_dataset.py",
                    "praxis_marketing_contract.py",
                    "marketing_task2_contract.py",
                    "db.py",
                    "config.py",
                    "workspace_costs.py",
                )
            },
            "lock": hashlib.sha256(
                qualification_path(root, "services/backend/uv.lock").read_bytes()
            ).hexdigest(),
            "packages": {name: version(name) for name in PACKAGES},
            "python": sys.version,
        }
    )


def response(provider, model, text):
    usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    if provider in {"openai", "meta_muse"}:
        body = {
            "id": "resp_software_control",
            "object": "response",
            "created_at": 1,
            "model": model,
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "msg_software_control",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text, "annotations": []}],
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }
    elif provider == "anthropic":
        text = json.dumps({"json": text})
        body = {
            "id": "msg_software_control",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    elif provider == "gemini":
        body = {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": text}]},
                    "finishReason": "STOP",
                    "index": 0,
                }
            ],
            "modelVersion": model,
            "usageMetadata": {
                "promptTokenCount": 1,
                "candidatesTokenCount": 1,
                "totalTokenCount": 2,
            },
        }
    else:
        body = {
            "id": "chatcmpl_software_control",
            "object": "chat.completion",
            "created": 1,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage,
        }
    return httpx.Response(200, json=body)


def controls(program):
    """Fixed server-owned positive, null, binding and malformed controls."""
    projection = {"evidence_refs": ["software-control:observed:1"], "origin": SCOPE}
    job = UUID("10000000-0000-4000-8000-000000000001")
    batch = Batch.model_validate(
        {
            "schema_version": "anvil.campaign-semantic-judge-batch.v1",
            "task_id": "SOFTWARE-PROTOCOL-CONTROL",
            "task_version": "1",
            "case_id": "CONTROL-NOT-A-BENCHMARK",
            **{
                name: "1" * 64
                for name in (
                    "payload_sha256",
                    "case_snapshot_sha256",
                    "configuration_sha256",
                    "validation_receipt_sha256",
                    "calibration_sha256",
                    "source_reference_binding_sha256",
                    "evaluator_source_sha256",
                    "deployment_release_sha256",
                    "binding_snapshot_sha256",
                    "model_binding_sha256",
                )
            },
            **{
                name: str(job)
                for name in ("configuration_id", "validation_receipt_id", "binding_id")
            },
            "evaluator_version": VERSION,
            "criterion_ids": program.criterion_ids,
            "max_input_bytes": program.max_input_bytes,
            "max_output_tokens": program.max_output_tokens,
            "max_calls": 1,
            "input_projection_sha256": wire_digest(projection),
        }
    )
    base = {
        "schema_version": "anvil.campaign-semantic-judge-result.v1",
        "job_id": str(job),
        **{
            key: getattr(batch, key)
            for key in (
                "input_projection_sha256",
                "binding_snapshot_sha256",
                "configuration_sha256",
                "calibration_sha256",
            )
        },
    }
    cases = []
    for level in (0, 1, 2, 3, 4, None):
        body = base | {
            "criteria": [
                {
                    "criterion_id": key,
                    "level": level,
                    "evidence_refs": projection["evidence_refs"],
                    "private_reason": "Manufactured protocol control",
                    **(
                        {"unscored_reason": "Manufactured missing evidence"}
                        if level is None
                        else {}
                    ),
                }
                for key in program.criterion_ids
            ]
        }
        cases.append(("level_" + str(level), json.dumps(body), True, level))
    valid = json.loads(cases[0][1])
    cases += [
        ("malformed", "{", False, None),
        ("wrong_binding", json.dumps(valid | {"binding_snapshot_sha256": "2" * 64}), False, None),
        (
            "wrong_job",
            json.dumps(valid | {"job_id": "10000000-0000-4000-8000-000000000002"}),
            False,
            None,
        ),
        (
            "invented_evidence",
            json.dumps(
                valid
                | {
                    "criteria": [
                        item | {"evidence_refs": ["invented"]} for item in valid["criteria"]
                    ]
                }
            ),
            False,
            None,
        ),
    ]
    return batch, projection, job, cases


def validate(program, models):
    """One bounded, no-retry pass through real SDKs on explicit mock transport."""
    program = parse_program(program)
    if not 1 <= len(models) <= 8 or len({digest(model) for model in models}) != len(models):
        raise ValueError("Select one to eight distinct saved model protocol bindings")
    if isinstance(program, FixedProgram) and (
        len(models) != 1 or models[0].get("id") != str(program.judge_model_profile_id)
    ):
        raise ValueError("Validate only the exact independent fixed judge profile")
    before = source_hash()
    batch, projection, job, cases = controls(program)
    text = prompt(batch, projection, job)  # Reject insufficient declared bounds.
    reports = []
    for model in models:
        if model["provider"] not in providers.PROVIDERS:
            raise ValueError("Unsupported SDK protocol")
        checks, requests = [], 0
        for name, reply, accepted, level in cases:
            previous_requests = requests

            def handler(request):
                nonlocal requests
                requests += 1
                body = json.loads(request.content)
                if (
                    model["provider"] in {"openai", "meta_muse"}
                    and body.get("text", {}).get("format", {}).get("type") != "json_object"
                ):
                    raise ValueError("Actual structured Responses wire required")
                if (
                    model["provider"] == "anthropic"
                    and body.get("output_config", {}).get("format", {}).get("type") != "json_schema"
                ):
                    raise ValueError("Actual structured Messages wire required")
                if (
                    model["provider"] == "gemini"
                    and body.get("generationConfig", {}).get("responseMimeType")
                    != "application/json"
                ):
                    raise ValueError("Actual structured Gemini wire required")
                return response(model["provider"], model["model_id"], reply)

            outcome = providers.execute_contract(
                model["provider"],
                providers.ActorRequest(
                    model=model["model_id"],
                    actor_text=text,
                    max_output_tokens=program.max_output_tokens,
                    timeout_seconds=1,
                ),
                httpx.MockTransport(handler),
                credential=SecretStr("anvil-software-protocol-only"),
                structured=True,
            )
            if requests != previous_requests + 1:
                raise ValueError("Exactly one mock SDK request is required for each control")
            if outcome.status != "completed":
                raise ValueError("SDK protocol control did not return completed text")
            try:
                actual = validate_result(outcome.text, batch, projection, job)
                matched = accepted and all(item["level"] == level for item in actual["criteria"])
            except (ValueError, TypeError, KeyError):
                matched = not accepted
            checks.append({"control": name, "matched": matched})
        if requests != len(cases):
            raise ValueError("Protocol validation must make exactly one mock request per control")
        reports.append(
            {"model_binding_sha256": digest(model), "checks": checks, "mock_requests": requests}
        )
    if before != source_hash():
        raise ValueError("Protocol source or installed runtime changed during validation")
    return {
        "kind": "private_native_semantic_validation",
        "validation_scope": SCOPE,
        "dispatch_origin": "sdk_mock",
        "structured_request": True,
        "runtime_version": "anvil-evaluator-v1",
        "native_semantic_version": VERSION,
        "native_program_sha256": digest(program.model_dump(mode="json")),
        "validation_source_sha256": before,
        "supported_model_binding_sha256": [row["model_binding_sha256"] for row in reports],
        "models": reports,
        "passed": all(check["matched"] for row in reports for check in row["checks"]),
        "provider_calls": 0,
        "paid_calls": 0,
        "human_calibration_established": False,
        "model_performance_validated": False,
        "limitation": "Supported bindings passed software SDK/parser protocol controls only; model quality, human calibration, task rights and runtime-purpose qualification remain separate.",
    }
