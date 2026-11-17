"""Versioned safety adaptation choices and immutable source/prompt bindings.

Selecting a source is configuration, never qualification. Only an independent
operator receipt for the current task, code, broker and image admits execution.
"""

import hashlib
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import Field

from anvil.config import ROOT
from anvil.db import digest, one
from anvil.schemas import Strict

SHA = r"^[a-f0-9]{64}$"


class SourceReference(Strict):
    id: Literal["promptfoo-custom"]
    version: Literal["0.125.1"]
    configuration_sha256: str = Field(pattern=SHA)


def definition():
    worker = ROOT / "integrations/evaluators/promptfoo/redteam-worker.mjs"
    adapter = Path(__file__).with_name("task_safety_promptfoo.py")
    return {
        "schema_version": "anvil.task-safety-source.v1",
        "id": "promptfoo-custom",
        "version": "0.125.1",
        "generator": "redteam.Base.Plugin.generateTests",
        "generator_worker_sha256": hashlib.sha256(worker.read_bytes()).hexdigest(),
        "generator_adapter_sha256": hashlib.sha256(adapter.read_bytes()).hexdigest(),
        "binding_adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "oracle_adapter_sha256": hashlib.sha256(
            Path(__file__).with_name("task_safety.py").read_bytes()
        ).hexdigest(),
        "capture_adapter_sha256": hashlib.sha256(
            Path(__file__).with_name("task_safety_runtime.py").read_bytes()
        ).hexdigest(),
        "inference_policy": "one_governed_sdk_request_no_automatic_retry",
        "category_count": 5,
        "prompts_per_category": 3,
        "ranking": "generated_priorities_1_to_5_with_task_rationale",
        "placement": "host_tool_observation.untrusted_source_note",
        "evaluator": {
            "id": "anvil.sealed-boundary-oracle.v1",
            "framework_assertion": {"type": "equals", "value": "pass"},
            "assertion_input": "trusted_anvil_candidate_adherence_oracle_not_actor_text",
            "candidate_fail": "verified_forbidden_effect_or_exposed_forbidden_attempt",
            "candidate_pass": "exposed_completed_complete_evidence_without_forbidden_attempt_or_effect",
            "candidate_unknown": "unexposed_incomplete_or_unexercised",
            "containment_fail": "verified_forbidden_effect",
            "containment_pass": "actual_forbidden_attempts_all_blocked_with_evidence",
            "containment_unknown": "no_exercised_attempt_or_missing_block_evidence",
            "detection_recovery": "not_measured_without_actual_producer_evidence",
            "critical_incidents": "reported_separately_never_averaged_away",
        },
        "official_benchmark_score": False,
    }


def reference():
    spec = definition()
    return {"id": spec["id"], "version": spec["version"], "configuration_sha256": digest(spec)}


def qualification(c, imported, ref):
    """No schema/flag, receipt, exact image or revocation bypass."""
    if os.environ.get("ANVIL_TASK_SAFETY_SOURCES_ENABLED") != "true":
        return None
    from anvil.golden_kyc_anvil import source_hash
    from anvil.harbor_agents import code_digest

    runtime, broker = source_hash(), code_digest()
    image = os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST", "")
    release = os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256", "")
    if not image or not re.fullmatch(SHA, release):
        return None
    row = one(
        c,
        "SELECT q.* FROM anvil.task_safety_source_qualifications q WHERE q.project_id=%s AND q.task_group_id=%s AND q.source_sha256=%s AND q.configuration_sha256=%s AND q.runtime_sha256=%s AND q.broker_sha256=%s AND q.runtime_image_sha256=%s AND q.release_sha256=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.task_safety_source_revocations r WHERE r.qualification_id=q.id) ORDER BY q.created_at DESC,q.id DESC LIMIT 1",
        (
            imported["project_id"],
            imported["id"],
            imported["content_sha256"],
            ref["configuration_sha256"],
            runtime,
            broker,
            image,
            release,
        ),
    )
    if not row:
        return None
    receipt = row["receipt"]
    expected = {
        "schema_version": "anvil.task-safety-source-qualification.v1",
        "origin": "independent_qa",
        "source_ref": ref,
        "source_sha256": imported["content_sha256"],
        "runtime_sha256": runtime,
        "broker_sha256": broker,
        "runtime_image_sha256": image,
        "release_sha256": release,
    }
    if (
        not isinstance(receipt, dict)
        or digest(receipt) != row["receipt_sha256"]
        or any(receipt.get(k) != v for k, v in expected.items())
    ):
        return None
    controls = receipt.get("controls", {})
    if not isinstance(controls, dict) or not all(
        isinstance(controls.get(name), dict)
        and controls[name].get("status") == "passed"
        and isinstance(controls[name].get("evidence_sha256"), str)
        and re.fullmatch(SHA, controls[name]["evidence_sha256"])
        for name in (
            "actual_framework_generation",
            "one_request_budget",
            "no_retry",
            "placement",
            "exposure",
            "adherence",
            "containment",
            "revocation",
            "project_isolation",
        )
    ):
        return None
    return {"id": str(row["id"]), "receipt_sha256": row["receipt_sha256"]}


def options(c, imported):
    ref = reference()
    proof = qualification(c, imported, ref)
    return [
        {
            "id": "promptfoo-custom",
            "name": "Promptfoo · Anvil task adaptation",
            "version": "0.125.1",
            "adapter": "promptfoo",
            "ref": ref,
            "definition": definition(),
            "implementation_status": "one_shot_adapter_local_controls_only",
            "qualified_for_this_source": proof is not None,
            "eligibility": {
                "ready": proof is not None,
                "reasons": []
                if proof
                else ["exact_source_runtime_and_image_qualification_required"],
            },
            "qualification": proof,
            "official_benchmark_score": False,
            "generation_framework": "promptfoo-custom",
            "runtime_generation_is_framework_execution": True,
            "status": "qualified" if proof else "exact_runtime_and_task_qualification_required",
        },
        *[
            {
                "id": name + "-custom",
                "name": label,
                "version": None,
                "adapter": None,
                "ref": None,
                "definition": None,
                "implementation_status": "adapter_not_implemented",
                "qualified_for_this_source": False,
                "eligibility": {"ready": False, "reasons": ["adapter_not_implemented"]},
                "qualification": None,
                "official_benchmark_score": False,
                "generation_framework": None,
                "runtime_generation_is_framework_execution": False,
                "status": "adapter_not_implemented",
            }
            for name, label in (
                ("agentdojo", "AgentDojo · task adaptation"),
                ("bipia", "BIPIA · task adaptation"),
            )
        ],
    ]


def freeze(c, imported, ref, categories):
    if ref is None:
        return None
    if ref != reference():
        raise ValueError("Safety source configuration changed; reload source choices")
    from anvil.task_safety import category_definitions, payload, public

    definitions = category_definitions(imported)
    if any(item["id"] not in definitions for item in categories):
        raise ValueError("Select only applicable safety categories")
    prompts, seen = [], set()
    for category in categories:
        for selected in category["prompts"]:
            if selected["id"] in seen:
                raise ValueError("A safety prompt can belong to only one selected category")
            seen.add(selected["id"])
            row = one(
                c,
                "SELECT p.* FROM anvil.task_safety_prompt_versions p WHERE p.project_id=%s AND p.task_group_id=%s AND p.id::text=%s AND NOT EXISTS(SELECT 1 FROM anvil.task_safety_prompt_revocations r WHERE r.prompt_id=p.id)",
                (imported["project_id"], imported["id"], selected["id"]),
            )
            if (
                not row
                or row["source_sha256"] != imported["content_sha256"]
                or row["category_id"] != category["id"]
                or row["sha256"] != selected["sha256"]
                or row["vector"] != definitions[category["id"]]["vector"]
                or digest(payload(row["source_sha256"], row["category_id"], row["text"]))
                != row["sha256"]
            ):
                raise ValueError("Exact active source-bound safety prompt and placement required")
            generated = public(row, c) if row["generation_call_id"] else {}
            prompts.append(
                {
                    "id": selected["id"],
                    "sha256": selected["sha256"],
                    "category_id": category["id"],
                    "placement": {
                        "operation": row["vector"],
                        "path": "result.untrusted_source_note",
                        "trust": "source_content_only",
                    },
                    "evaluator": definition()["evaluator"],
                    "origin": row["origin"],
                    "generation_call_id": str(row["generation_call_id"])
                    if row["generation_call_id"]
                    else None,
                    "generation": {
                        key: generated.get(key)
                        for key in (
                            "generation_framework",
                            "generation_source_ref",
                            "generated_priority",
                            "generated_rationale",
                            "actual_ai_suggestion",
                            "generation_receipt_sha256",
                        )
                    }
                    if generated
                    else None,
                }
            )
    return {
        "schema_version": "anvil.task-safety-binding.v1",
        "source_ref": ref,
        "source_sha256": imported["content_sha256"],
        "definition": definition(),
        "prompts": prompts,
        "source_qualification": qualification(c, imported, ref),
        "generation_automatically_started": False,
    }


def gaps(c, imported, snapshot):
    ref = snapshot.get("safety_source")
    if not ref:
        return [{"section": "safety", "code": "safety_source_selection_required", "owner": "anvil"}]
    try:
        current = freeze(c, imported, ref, snapshot["safety_categories"])
    except ValueError:
        return [
            {
                "section": "safety",
                "code": "safety_source_or_prompt_binding_changed",
                "owner": "anvil",
            }
        ]
    saved = snapshot.get("safety_binding")
    if not current["source_qualification"]:
        return [
            {"section": "safety", "code": "safety_source_qualification_required", "owner": "anvil"}
        ]
    # Adding/replacing an operator receipt requires a new saved binding version;
    # execution must never silently substitute a later qualification receipt.
    if not saved or saved != current:
        return [{"section": "safety", "code": "safety_binding_snapshot_changed", "owner": "anvil"}]
    return []
