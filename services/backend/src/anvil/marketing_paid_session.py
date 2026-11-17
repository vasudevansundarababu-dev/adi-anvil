"""Current genuine Marketing task/template/dataset context, not Run authority.

Only the already public authored actor crosses into a candidate prompt. Source
identity, technical qualification and human/model scoring remain separate.
"""

from typing import Literal
from uuid import UUID

from anvil.dataset_export_contract import Sha
from anvil.db import digest, one
from anvil.marketing_task2_contract import CASES
from anvil.praxis_case_dataset import CaseDatasetRef
from anvil.praxis_generic_contract import TemplateRef
from anvil.praxis_generic_contract import digest as wire_digest
from anvil.praxis_marketing_contract import (
    CampaignDataset,
    CampaignSelector,
    Capability,
    MarketingExecution,
)
from anvil.schemas import Strict


class CampaignContext(Strict):
    schema_version: Literal["anvil.campaign-context.v1"]
    task_id: str
    revision_id: str
    caseDataset: CaseDatasetRef
    caseSelector: CampaignSelector
    environment: Capability
    workflow_graph_sha256: Sha
    evaluator_bindings_sha256: Sha


def task_context(c, project, resolved_id, task_group_id, *, case_id=None, execution_data=None):
    from anvil.golden_kyc_anvil import source_hash as runtime_hash
    from anvil.harbor_agents import code_digest
    from anvil.praxis_campaign_registry import lookup as dataset_lookup
    from anvil.praxis_template_registry import lookup, source_hash
    from anvil.project_bindings import group

    if execution_data is not None:
        raise RuntimeError("AV_CAMPAIGN_INPUT_ADAPTER_REQUIRED")
    resolved = one(
        c,
        "SELECT r.*,t.template_key,t.version AS template_version,t.spec_sha256,t.spec FROM anvil.praxis_resolved_tasks r JOIN anvil.praxis_template_versions t ON t.project_id=r.project_id AND t.id=r.template_id WHERE r.project_id=%s AND r.id=%s",
        (project, resolved_id),
    )
    if (
        not resolved
        or wire_digest(resolved["actor"]) != resolved["actor_sha256"]
        or wire_digest(resolved["binding"]) != resolved["binding_sha256"]
        or wire_digest(resolved["spec"]) != resolved["spec_sha256"]
    ):
        raise RuntimeError("marketing_resolved_source_integrity_required")
    binding = resolved["binding"]
    if (
        binding.get("task_mode") != "reusable_campaign_workflow"
        or binding.get("source_sha256") != source_hash()
        or binding.get("actor_sha256") != resolved["actor_sha256"]
        or binding.get("template_sha256") != resolved["spec_sha256"]
    ):
        raise RuntimeError("marketing_current_resolved_binding_required")
    imported = group(c, project, UUID(str(task_group_id)))
    tasks = imported["content"].get("tasks", [])
    if (
        digest(imported["content"]) != imported["content_sha256"]
        or imported["content"].get("source_origin", {}).get("kind") != "praxis_authored_batch"
        or len(tasks) != 1
    ):
        raise RuntimeError("marketing_one_genuine_authored_campaign_required")
    task = tasks[0]
    if (
        task.get("task_id") != resolved["task_key"]
        or task.get("revision_id") != resolved["revision"]
        or task.get("payload_sha256") != resolved["private_reference_sha256"]
        or task.get("source", {}).get("template", {}).get("profile_id")
        != "veyra-hush-one-launch-v1"
        or task["source"]["template"].get("sha256") != resolved["spec_sha256"]
    ):
        raise RuntimeError("marketing_imported_task_revision_binding_changed")
    current = lookup(
        c,
        project,
        TemplateRef(
            id=resolved["template_key"],
            version=resolved["template_version"],
            sha256=resolved["spec_sha256"],
        ),
    )
    if (
        not current
        or not current["qualified"]
        or str(current["qualification"]["id"]) != binding.get("qualification_id")
        or current["qualification"]["receipt_sha256"] != binding.get("qualification_sha256")
    ):
        raise RuntimeError("marketing_template_qualification_revoked_or_changed")
    execution = MarketingExecution.model_validate(resolved["spec"]["execution"])
    if (
        binding.get("execution_sha256") != wire_digest(resolved["spec"]["execution"])
        or binding.get("environment") != execution.environment.model_dump()
        or binding.get("evaluator_bindings") != execution.model_dump()["evaluators"]
    ):
        raise RuntimeError("marketing_published_execution_binding_changed")
    context = CampaignContext.model_validate(binding.get("case_context"))
    if (
        wire_digest(context.model_dump()) != binding.get("case_context_sha256")
        or context.task_id != resolved["task_key"]
        or context.revision_id != resolved["revision"]
        or context.environment != execution.environment
        or context.workflow_graph_sha256 != execution.workflow_graph_sha256
        or context.evaluator_bindings_sha256 != wire_digest(execution.model_dump()["evaluators"])
        or context.caseDataset.model_dump() != imported["content"].get("case_dataset")
    ):
        raise RuntimeError("marketing_campaign_context_changed")
    dataset = dataset_lookup(c, project, context.caseDataset)
    if (
        not dataset
        or not dataset["qualified"]
        or str(dataset["import"]["id"]) != binding.get("case_import_id")
        or dataset["import"]["manifest_sha256"] != binding.get("case_import_sha256")
    ):
        raise RuntimeError("marketing_current_dataset_qualification_required")
    members = CampaignDataset.model_validate(dataset["manifest"]).select(
        context.caseDataset, context.caseSelector
    )
    if any(member.id not in CASES or member.locale != "en-US" for member in members):
        raise RuntimeError("AV_CAMPAIGN_LOCALE_RUNTIME_QUALIFICATION_REQUIRED")
    if case_id is not None and case_id not in {member.id for member in members}:
        raise RuntimeError("marketing_case_outside_frozen_dataset")
    return {
        "actor": resolved["actor"],
        "execution": execution.model_dump(),
        "native_binding": {
            "task_mode": "reusable_campaign_workflow",
            "task_group_id": str(task_group_id),
            "task_id": resolved["task_key"],
            "revision_id": resolved["revision"],
            "payload_sha256": resolved["private_reference_sha256"],
            "resolved_task_id": str(resolved_id),
            "resolved_binding_sha256": resolved["binding_sha256"],
            "actor_sha256": resolved["actor_sha256"],
            "template_sha256": resolved["spec_sha256"],
            "template_qualification": {
                "id": str(current["qualification"]["id"]),
                "receipt_sha256": current["qualification"]["receipt_sha256"],
            },
            "task_group_sha256": imported["content_sha256"],
            "case_context": context.model_dump(),
            "dataset_import_id": str(dataset["import"]["id"]),
            "dataset_sha256": dataset["import"]["manifest_sha256"],
            "fixture_manifest_sha256": dataset["import"]["fixture_manifest_sha256"],
            "dataset_qualification": {
                "id": str(dataset["qualification"]["id"]),
                "receipt_sha256": dataset["qualification"]["receipt_sha256"],
            },
            "cases": [member.model_dump() for member in members],
            "execution_sha256": wire_digest(execution.model_dump()),
            "workflow_graph_sha256": execution.workflow_graph_sha256,
            "evaluator_bindings_sha256": wire_digest(execution.model_dump()["evaluators"]),
            "runtime_sha256": runtime_hash(),
            "broker_sha256": code_digest(),
        },
        "private_reference_to_actor": False,
        "run_authority": "not_granted",
    }


def require_frozen(c, project, native, *, case_id):
    """No substitution of a newer task, receipt, dataset, runtime or broker."""
    if not isinstance(case_id, str) or not case_id:
        raise RuntimeError("marketing_case_assignment_required")
    current = task_context(
        c,
        project,
        native["resolved_task_id"],
        native["task_group_id"],
        case_id=case_id,
        execution_data=native.get("execution_data"),
    )
    if current["native_binding"] != {
        key: value for key, value in native.items() if key not in {"case_assignment"}
    }:
        raise RuntimeError("marketing_frozen_native_source_or_qualification_changed")
    assignment = native.get("case_assignment")
    member = next(
        member for member in current["native_binding"]["cases"] if member["id"] == case_id
    )
    if assignment is not None and (
        assignment.get("case_id") != case_id
        or assignment.get("snapshot_sha256") != member["snapshot_sha256"]
        or assignment.get("locale") != member["locale"]
    ):
        raise RuntimeError("marketing_case_assignment_source_mismatch")
    return current


def actor_prompt(c, plan, stage):
    """API-only prompt reconstruction from one immutable current role intent."""
    from anvil.marketing_paid_contract import phase, role_prompt

    native = plan["config"].get("marketing_native_binding") or {}
    current = require_frozen(
        c, plan["project_id"], native, case_id=native["case_assignment"]["case_id"]
    )
    binding = one(
        c,
        "SELECT * FROM marketing_runtime.paid_agent_bindings WHERE project_id=%s AND plan_id=%s",
        (plan["project_id"], plan["id"]),
    )
    intent = one(
        c,
        "SELECT * FROM marketing_runtime.paid_turn_intents WHERE project_id=%s AND plan_id=%s AND stage_index=%s",
        (plan["project_id"], plan["id"], stage),
    )
    if (
        not binding
        or not intent
        or binding["native_binding"] != native
        or digest(binding["native_binding"]) != binding["native_binding_sha256"]
        or binding["execution"] != current["execution"]
        or wire_digest(binding["execution"]) != binding["execution_sha256"]
    ):
        raise RuntimeError("marketing_paid_role_intent_source_changed")
    context = intent["public_context"]
    if (
        digest(context) != intent["public_context_sha256"]
        or context
        != phase(
            current["execution"],
            intent["node_id"],
            context["inputs"],
            intent["week"],
            intent["visit"],
            opening=intent["week"] == 0,
        )
        or context["role"] != intent["role"]
    ):
        raise RuntimeError("marketing_paid_role_phase_custody_changed")
    rows = c.execute(
        "SELECT o.* FROM marketing_runtime.paid_turn_observations o JOIN marketing_runtime.paid_turn_intents t ON t.plan_id=o.plan_id AND t.stage_index=o.stage_index AND t.project_id=o.project_id WHERE o.project_id=%s AND o.plan_id=%s AND t.effect_id=%s AND t.role=%s AND o.stage_index<%s ORDER BY o.stage_index",
        (plan["project_id"], plan["id"], intent["effect_id"], intent["role"], stage),
    ).fetchall()
    if any(
        digest(row["observation"]) != row["observation_sha256"]
        or row["observation"].get("completed_node") is True
        for row in rows
    ):
        raise RuntimeError("marketing_paid_observation_changed_or_node_already_complete")
    prompt = role_prompt(
        current["actor"], current["execution"], context, [row["observation"] for row in rows]
    )
    from anvil.marketing_capture_evidence_store import retain_prompt

    retain_prompt(c, plan, intent, prompt)
    return prompt
