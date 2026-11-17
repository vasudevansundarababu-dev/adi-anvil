"""API-only, once-only private semantic dispatch under the parent run envelope.

The coordinator passes only a leased job capability. No caller prompt, model,
credential, private input or result travels through the worker HTTP response.
"""

import hashlib
import os

from anvil import providers, workspace_costs, workspace_credentials, workspace_dispatch
from anvil.campaign_semantic_contract import (
    Claim,
    FixedBlueprint,
    parse_batch,
    prompt,
    validate_result,
)
from anvil.db import Jsonb, digest, one, project_fence, transaction
from anvil.diagnostic_measures import valid_sha
from anvil.qualification_resources import qualification_path, qualification_root

VERSION = "anvil-native-semantic-v1"


def source_hash():
    root = qualification_root()
    return digest(
        {
            name: hashlib.sha256(
                qualification_path(root, "services/backend/src/anvil/" + name).read_bytes()
            ).hexdigest()
            for name in (
                "campaign_semantic_runtime.py",
                "qualification_resources.py",
                "campaign_semantic_contract.py",
                "campaign_semantic_budget.py",
                "campaign_semantic_worker.py",
                "native_semantic.py",
                "worker_dispatch_broker.py",
                "pilot_budget.py",
                "campaign_semantic_custody.py",
                "workspace_preparation.py",
                "workspace_costs.py",
                "evaluator_configurations.py",
            )
        }
        | {
            "106_campaign_semantic_judge.sql": hashlib.sha256(
                qualification_path(
                    root, "services/backend/migrations/106_campaign_semantic_judge.sql"
                ).read_bytes()
            ).hexdigest(),
            "109_fixed_semantic_judge.sql": hashlib.sha256(
                qualification_path(
                    root, "services/backend/migrations/109_fixed_semantic_judge.sql"
                ).read_bytes()
            ).hexdigest(),
        }
    )


def enabled():
    from anvil import pilot_environment
    from anvil.config import harbor_live_enabled
    from anvil.worker_dispatch_broker import api_enabled

    return (
        api_enabled()
        and harbor_live_enabled()
        and pilot_environment.current() == "qa"
        and os.environ.get("ANVIL_CAMPAIGN_JUDGE_ENABLED") == "true"
    )


def purpose_control(batch, evidence, role_mapping_sha256):
    """Independent release evidence, not a model's assertion of its own trust."""
    controls = evidence.get("native_semantic", []) if isinstance(evidence, dict) else []
    expected = {
        key: getattr(batch, key)
        for key in (
            "configuration_sha256",
            "calibration_sha256",
            "source_reference_binding_sha256",
            "evaluator_source_sha256",
            "evaluator_version",
            "deployment_release_sha256",
            "model_binding_sha256",
            "validation_receipt_sha256",
            "criterion_ids",
            "task_id",
            "task_version",
            "payload_sha256",
            "case_id",
            "case_snapshot_sha256",
        )
    }
    expected.update(
        configuration_id=str(batch.configuration_id),
        validation_receipt_id=str(batch.validation_receipt_id),
        kind="private_native_semantic_qualification",
        status="passed",
        dispatcher_source_sha256=source_hash(),
        role_mapping_sha256=role_mapping_sha256,
    )
    return (
        any(
            isinstance(item, dict)
            and all(item.get(k) == v for k, v in expected.items())
            and all(
                valid_sha(item.get(k))
                for k in (
                    "rights_review_receipt_sha256",
                    "source_qualification_receipt_sha256",
                    "evidence_sha256",
                )
            )
            for item in controls
        )
        if isinstance(controls, list)
        else False
    )


def context(c, claim):
    from anvil import harbor_agents, workspace_execution
    from anvil.evaluator_configurations import get as evaluator
    from anvil.workspace_preparation import model_snapshot

    project_fence(c, claim.project_id)
    row = one(
        c,
        "SELECT marketing_runtime.semantic_job_context(%s,%s) AS context",
        (claim.job_id, claim.lease_token),
    )["context"]
    if not row:
        raise RuntimeError("semantic_current_job_capability_required")
    batch = parse_batch(row["batch"])
    quote, binding = row["quote"], row["model_binding"]
    plan = harbor_agents.plan(c, row["plan_id"])
    if isinstance(batch, FixedBlueprint) and (
        batch.candidate_model_binding_sha256 != digest(plan["config"]["workspace_model"])
    ):
        raise RuntimeError("semantic_exact_separate_candidate_binding_required")
    group = workspace_execution.group(c, quote["group_id"], True)
    if not workspace_execution.plan_readiness(c, plan)["ready"]:
        raise RuntimeError("semantic_parent_run_authority_required")
    prepared = group["snapshot"]["preparation"]
    frozen = prepared.get("project_binding") or {}
    from anvil.campaign_reference_bindings import bound as bound_reference
    from anvil.golden_targets import requirements

    task_identity = {
        key: getattr(batch, key) for key in ("task_id", "task_version", "payload_sha256")
    }
    reference_binding = bound_reference(
        prepared, task_identity, batch.case_id, batch.case_snapshot_sha256
    )
    if (
        str(batch.binding_id) != frozen.get("id")
        or batch.binding_snapshot_sha256 != frozen.get("snapshot_sha256")
        or batch.source_reference_binding_sha256 != digest(reference_binding)
        or row["projection"].get("custody") != row.get("custody")
        or row["custody"]["case_id"] != batch.case_id
        or row["custody"]["case_snapshot_sha256"] != batch.case_snapshot_sha256
    ):
        raise RuntimeError("semantic_exact_parent_case_seal_reference_custody_required")
    imported = one(
        c,
        "SELECT content,content_sha256 FROM anvil.benchmark_task_groups WHERE id=%s",
        (frozen.get("task_group_id"),),
    )
    if not imported or digest(imported["content"]) != imported["content_sha256"]:
        raise RuntimeError("semantic_exact_imported_task_required")
    task = next(
        (
            item
            for item in imported["content"].get("tasks", [])
            if all(item.get(key) == value for key, value in task_identity.items())
        ),
        None,
    )
    descriptors = (
        [
            item
            for item in requirements(task)
            if item["official"] and item["id"] in batch.criterion_ids
        ]
        if task
        else []
    )
    mappings = {item["target"]: item for item in prepared.get("skill_mapping_bindings", [])}
    if len(descriptors) != len(batch.criterion_ids) or any(
        item["target"] not in mappings for item in descriptors
    ):
        raise RuntimeError("semantic_exact_native_role_mapping_required")
    role_mapping_sha256 = digest(
        [mappings[item["target"]] for item in sorted(descriptors, key=lambda row: row["id"])]
    )
    if (
        batch.model_binding_sha256 != digest(binding)
        or quote["model_binding_sha256"] != digest(binding)
        or quote["pricing_sha256"] != digest(row["pricing"])
        or not workspace_costs.current(row["pricing"])
        or batch.deployment_release_sha256
        != os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256")
        or batch.evaluator_source_sha256 != source_hash()
        or batch.evaluator_version != VERSION
    ):
        raise RuntimeError("semantic_exact_source_release_model_price_required")
    current = one(c, "SELECT * FROM anvil.connections WHERE id=%s FOR SHARE", (binding["id"],))
    if not current or current["status"] == "revoked" or model_snapshot(current) != binding:
        raise RuntimeError("semantic_model_binding_changed")
    config = evaluator(c, batch.configuration_id)
    program = config["configuration"].get("native_semantic")
    from anvil.native_semantic import profile_matches

    validation = config["validation"]
    if (
        config["status"] != "ready"
        or config["adapter"] != "builtin"
        or not isinstance(program, dict)
        or config["configuration_sha256"] != batch.configuration_sha256
        or not validation
        or str(validation["id"]) != str(batch.validation_receipt_id)
        or validation["evidence_sha256"] != batch.validation_receipt_sha256
        or digest(validation["evidence"]) != batch.validation_receipt_sha256
        or any(
            program.get(key) != getattr(batch, key)
            for key in ("criterion_ids", "max_input_bytes", "max_output_tokens", "max_calls")
        )
        or not profile_matches(program, config["configuration"], batch)
        or validation["evidence"].get("native_semantic_version") != VERSION
        or validation["evidence"].get("native_program_sha256") != digest(program)
        or batch.model_binding_sha256
        not in validation["evidence"].get("supported_model_binding_sha256", [])
    ):
        raise RuntimeError("semantic_exact_qualified_saved_profile_required")
    qualification = one(
        c,
        "SELECT q.* FROM anvil.project_binding_qualifications q WHERE q.project_id=%s AND q.binding_id=%s AND q.release_sha256=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id) ORDER BY q.created_at DESC,q.id DESC LIMIT 1",
        (claim.project_id, batch.binding_id, batch.deployment_release_sha256),
    )
    if (
        not qualification
        or digest(qualification["evidence"]) != qualification["evidence_sha256"]
        or not purpose_control(batch, qualification["evidence"], role_mapping_sha256)
    ):
        raise RuntimeError(
            "semantic_reviewed_calibration_rights_and_purpose_qualification_required"
        )
    return row, batch


def claim_allowed(binding, ticket, request):
    """Last committed SDK fence, including shared money/slots/current revocation."""
    if (
        not enabled()
        or not isinstance(ticket, dict)
        or set(ticket) != {"purpose", "project", "actor", "job", "lease", "dispatch"}
        or ticket["purpose"] != "campaign_semantic"
    ):
        return False
    try:
        claim = Claim(
            project_id=ticket["project"],
            actor_id=ticket["actor"],
            job_id=ticket["job"],
            lease_token=ticket["lease"],
        )
        with transaction(claim.project_id, claim.actor_id) as c:
            row, batch = context(c, claim)
            text = prompt(batch, row["projection"], claim.job_id)
            request_hash = hashlib.sha256(text.encode()).hexdigest()
            if (
                row["state"] != "dispatching"
                or row["broker_claimed"]
                or row["dispatch_token"] != ticket["dispatch"]
                or binding != row["model_binding"]
                or request.model != binding["model_id"]
                or request.actor_text != text
                or row["request_sha256"] != request_hash
                or request.max_output_tokens != batch.max_output_tokens
                or not 1 <= request.timeout_seconds <= row["request_timeout_seconds"]
            ):
                return False
            return one(
                c,
                "SELECT marketing_runtime.claim_semantic_sdk(%s,%s,%s,%s,%s) AS allowed",
                (claim.job_id, claim.lease_token, ticket["dispatch"], request_hash, Jsonb(binding)),
            )["allowed"]
    except (ValueError, RuntimeError, KeyError, TypeError):
        return False


def dispatch(claim, *, transport=None):
    """Exactly one provider attempt; lost/invalid replies retain the full bound."""
    from anvil.workspace_execution import billed_usage, provider_evidence

    if not enabled():
        raise RuntimeError("private_semantic_dispatch_disabled")
    with transaction(claim.project_id, claim.actor_id) as c:
        row, batch = context(c, claim)
        if row["state"] != "queued":
            raise RuntimeError("semantic_attempt_not_replayable")
        text = prompt(batch, row["projection"], claim.job_id)
        binding = row["model_binding"]
        secret = workspace_credentials.resolve(
            c, binding["credential"]["id"], binding["credential"]["version_id"]
        )
        token = one(
            c,
            "SELECT marketing_runtime.start_semantic_job(%s,%s,%s) AS token",
            (claim.job_id, claim.lease_token, hashlib.sha256(text.encode()).hexdigest()),
        )["token"]
        if not token:
            raise RuntimeError("semantic_once_only_intent_required")
    request = providers.ActorRequest(
        model=binding["model_id"],
        actor_text=text,
        max_output_tokens=batch.max_output_tokens,
        timeout_seconds=row["request_timeout_seconds"],
    )
    ticket = {
        "purpose": "campaign_semantic",
        "project": str(claim.project_id),
        "actor": str(claim.actor_id),
        "job": str(claim.job_id),
        "lease": str(claim.lease_token),
        "dispatch": str(token),
    }
    result, actual = None, None
    state = "execution_unknown"
    receipt = {
        "status": "unscored",
        "reason": "semantic_dispatch_outcome_unknown_no_retry",
        "model_performance_validated": False,
    }
    try:
        result = workspace_dispatch.execute(
            binding, secret, request, transport=transport, pilot_ticket=ticket
        )
        inputs, outputs = billed_usage(binding["provider"], result.usage or {})
        if (
            result.status != "completed"
            or result.model_returned != binding["model_id"]
            or type(inputs) is not int
            or type(outputs) is not int
            or not 0 <= inputs <= batch.max_input_bytes + 1024
            or not 0 <= outputs <= batch.max_output_tokens
        ):
            raise ValueError("semantic_provider_usage_or_output_not_admitted")
        actual = workspace_costs.billed_cost(row["pricing"], result.usage or {}, inputs, outputs)
        if actual > row["quote"]["bound_micro_usd"]:
            actual = None
            raise ValueError("semantic_bound_exceeded")
        try:
            accepted = validate_result(result.text, batch, row["projection"], claim.job_id)
            state = "completed"
            receipt = {
                "status": "completed",
                "result": accepted,
                "model_performance_validated": False,
            }
        except (ValueError, TypeError, KeyError):
            state = "error"
            receipt = {
                "status": "unscored",
                "reason": "invalid_private_semantic_reply",
                "model_performance_validated": False,
            }
    except Exception:
        # No provider exception or private reply is sent to workers or public logs.
        pass
    receipt |= {
        "provider_evidence": provider_evidence(result),
        "dispatch_origin": (result.usage or {}).get("dispatch_origin", "provider")
        if result
        else "provider",
        "bound_retained_micro_usd": row["quote"]["bound_micro_usd"],
        "raw_response_sha256": hashlib.sha256(result.text.encode()).hexdigest()
        if result and isinstance(result.text, str)
        else None,
    }
    with transaction(claim.project_id, claim.actor_id) as c:
        if not one(
            c,
            "SELECT marketing_runtime.finish_semantic_job(%s,%s,%s,%s,%s,%s) AS allowed",
            (claim.job_id, token, state, Jsonb(receipt), digest(receipt), actual),
        )["allowed"]:
            raise RuntimeError("semantic_private_terminal_receipt_not_confirmed_no_retry")
    # The private grader reads the result under its own role. No private content
    # or judge rationale crosses this response, even on successful evaluation.
    return {"status": state, "result_sha256": digest(receipt), "private_result": True}
