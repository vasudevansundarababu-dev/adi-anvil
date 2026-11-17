"""Golden actor-only prompts and broker-driven tool turns; no provider/key access."""

import json

from anvil.db import Jsonb, one
from anvil.golden_kyc_policy import ASSIGNMENT
from anvil.praxis_generic_contract import digest, load

TOOLS = (
    "application.read",
    "policy.read",
    "documents.list",
    "document.read",
    "document.compare",
    "identity.check",
    "document.check",
    "address.check",
    "screening.check",
    "authority.check",
    "operation.lookup",
    "operation.read",
    "information.request",
    "information.read",
    "finding.write",
    "finding.resolve",
    "specialist.refer",
    "specialist.read",
    "search",
    "search.read",
    "recommend",
)


def task_context(c, project, resolved_id, application, *, execution_data=None, resolved_input=None, require_policy=False,
                 policy_scope=None, policy_user=None, absolute_deadline=None):
    """Recheck the genuine immutable Praxis resolution before every model turn."""
    from anvil.praxis_generic_contract import TemplateRef
    from anvil.praxis_template_registry import lookup, source_hash

    if require_policy and policy_scope is not None:
        from anvil.golden_kyc_policy_registry import ProductRegistryScope
        from anvil.golden_kyc_policy_runtime import application as current_application
        from anvil.praxis_generic_contract import canonical

        scope = ProductRegistryScope.model_validate_json(canonical(policy_scope))
        if (str(scope.project_id) != str(project)
                or resolved_input != {"id": str(scope.resolved_input_id), "sha256": scope.resolved_input_sha256}
                or not policy_user or execution_data):
            raise RuntimeError("Exact original product policy admission scope required")
        checked, delivered = current_application(scope, policy_user, application, absolute_deadline=absolute_deadline)
        if not checked.public_actor or checked.resolved_task_id != str(resolved_id):
            raise RuntimeError("Actual bounded original product task required")
        return checked.public_actor | {"execution_input": {"resolved_input": resolved_input,
            "case_selector": {"field": "product", "value": scope.workflow_product},
            "execution_assignment": {"application_id": application, "application_sha256": checked.application_sha256,
                "product": scope.workflow_product, "governing_state": delivered.public["governing_state"],
                "run_authority": "not_granted", "legal_acceptance": "not_established"}}}
    resolved = one(
        c,
        "SELECT r.*,t.template_key,t.version,t.spec_sha256 FROM anvil.praxis_resolved_tasks r JOIN anvil.praxis_template_versions t ON t.id=r.template_id AND t.project_id=r.project_id WHERE r.project_id=%s AND r.id=%s",
        (project, resolved_id),
    )
    if not resolved or (
        digest(resolved["actor"]) != resolved["actor_sha256"]
        or digest(resolved["binding"]) != resolved["binding_sha256"]
        or resolved["binding"].get("actor_sha256") != resolved["actor_sha256"]
        or resolved["binding"].get("source_sha256") != source_hash()
        or (
            not resolved["binding"].get("case_context")
            and not (resolved["binding"].get("task_mode") == "reusable_application_workflow" and resolved_input)
            and resolved["actor"].get("sections", {}).get("S1", {}).get("applicationId")
            != application
        )
    ):
        raise RuntimeError("golden_resolved_task_context_missing_or_changed")
    current = lookup(
        c,
        project,
        TemplateRef(
            id=resolved["template_key"], version=resolved["version"], sha256=resolved["spec_sha256"]
        ),
    )
    if (
        not current
        or not current["qualified"]
        or (
            current["row"]["spec"]["execution"]["environment"]["id"] != "golden-kyc-openenv-v2"
            or str(current["qualification"]["id"]) != resolved["binding"]["qualification_id"]
            or current["qualification"]["receipt_sha256"]
            != resolved["binding"]["qualification_sha256"]
        )
    ):
        raise RuntimeError("golden_praxis_task_qualification_revoked_or_changed")
    if resolved["binding"].get("task_mode") == "reusable_application_workflow":
        if require_policy:
            raise RuntimeError("Original product policy scope and deadline required")
        from anvil.golden_kyc_product_context import actor_context
        from anvil.golden_kyc_product_context import load as product_context

        if execution_data:
            raise RuntimeError("Product tasks require the exact resolved input; bind changed data before preparing packages")
        context = product_context(c, project, resolved, resolved_input)
        return actor_context(context, resolved["actor"], application)
    if resolved["binding"].get("case_context"):
        from anvil.praxis_case_dataset import CaseDataset, StateTaskContext
        from anvil.praxis_case_registry import lookup as dataset_lookup

        context = StateTaskContext.model_validate(resolved["binding"]["case_context"])
        dataset = dataset_lookup(c, project, context.caseDataset)
        if (
            not dataset
            or not dataset["qualified"]
            or (
                digest(context.model_dump()) != resolved["binding"].get("case_context_sha256")
                or context.task_id != resolved["task_key"]
                or context.revision_id != resolved["revision"]
                or context.caseSelector.value
                != resolved["actor"].get("sections", {}).get("S1", {}).get("governingState")
                or str(dataset["import"]["id"]) != resolved["binding"].get("case_import_id")
                or dataset["import"]["manifest_sha256"]
                != resolved["binding"].get("case_import_sha256")
            )
        ):
            raise RuntimeError("golden_state_task_dataset_binding_changed")
        if execution_data:
            from anvil.project_inputs import actor_overlay, execution_overlay, overlay_assignment

            overlay = execution_overlay(c, project, execution_data)
            source_group = one(
                c,
                "SELECT content FROM anvil.benchmark_task_groups WHERE project_id=%s AND id=%s",
                (project, overlay["task_group_id"]),
            )
            if overlay["family"] != "kyc" or not any(
                task["task_id"] == resolved["task_key"]
                and task.get("revision_id") == resolved["revision"]
                and task.get("payload_sha256") == resolved["private_reference_sha256"]
                for task in source_group["content"]["tasks"]
            ):
                raise RuntimeError("golden_execution_input_task_source_mismatch")
            assignment = overlay_assignment(context, overlay, application)
            return resolved["actor"] | {
                "execution_data": actor_overlay(overlay, context.caseSelector.value),
                "execution_assignment": assignment,
                "execution_scope_note": "Authored caseDataset is default provenance; use the frozen execution_data population and assigned application for this run.",
            }
        context.assignment(CaseDataset.model_validate(dataset["manifest"]), application)
    elif execution_data:
        raise RuntimeError("Execution data requires a reusable state task")
    return resolved["actor"]


def actor_prompt(c, plan, stage, *, absolute_deadline=None):
    binding = one(
        c,
        "SELECT * FROM banking.paid_agent_bindings WHERE plan_id=%s AND project_id=%s",
        (plan["id"], plan["project_id"]),
    )
    if not binding or str(binding["group_id"]) != plan["config"].get("workspace_execution_group"):
        raise RuntimeError("golden_actor_binding_missing")
    native = plan["config"].get("golden_native_binding") or {}
    if (
        str(binding["resolved_task_id"]) != native.get("resolved_task_id")
        or binding["application_id"] != native.get("application_id")
        or binding["runtime_sha256"] != native.get("runtime_sha256")
        or str(binding["import_id"]) != native.get("import_id")
    ):
        raise RuntimeError("golden_actor_plan_binding_changed")
    context = task_context(
        c,
        plan["project_id"],
        binding["resolved_task_id"],
        binding["application_id"],
        execution_data=native.get("execution_data"),
        resolved_input=native.get("resolved_input"),
        require_policy=True,
        policy_scope=native.get("policy_scope"), policy_user=plan["created_by"], absolute_deadline=absolute_deadline,
    )
    observations = c.execute(
        "SELECT * FROM banking.paid_agent_observations WHERE plan_id=%s AND stage_index<%s ORDER BY stage_index",
        (plan["id"], stage),
    ).fetchall()
    if len(observations) != stage or any(
        digest(o["observation"]) != o["observation_sha256"] for o in observations
    ):
        raise RuntimeError("golden_tool_transcript_changed_or_incomplete")
    value = {
        "assignment": ASSIGNMENT,
        "praxis_task": context,
        "application_id": binding["application_id"],
        "tools": list(TOOLS),
        "step": stage,
        "max_steps": plan["config"]["max_calls"],
        "observations": [o["observation"] for o in observations],
    }
    from anvil.golden_kyc_tool_contract import tools

    value["tool_contracts"] = tools()
    prompt = (
        'Return only JSON {"actions":[{"operation":"declared tool","arguments":{}}]}. '
        "At most8 sequential actions per turn. Use application.read, policy.read and documents.list first. "
        "recommend must be the only action in its turn, after you have received the needed tool observations in prior turns. "
        "Never invent IDs or outputs. Tool refusals/uncertainty are observations, not success. "
        "Submit supported recommendation through recommend; no real account is opened. "
        "No shell, clock, database, private evaluator or approval access.\n"
        + json.dumps(value, ensure_ascii=False)
    )
    if len(prompt.encode()) > 32768:
        raise RuntimeError("golden_actor_input_bound")
    return prompt


def actions(text):
    value = load(text.encode())
    if (
        set(value) != {"actions"}
        or not isinstance(value["actions"], list)
        or not 1 <= len(value["actions"]) <= 8
    ):
        raise ValueError("Bounded declared Golden actions required")
    from anvil.golden_kyc_tool_contract import tools
    from anvil.praxis_generic_contract import schema_errors

    schemas = {tool["id"]: tool["input_schema"] for tool in tools()}
    for action in value["actions"]:
        if (
            not isinstance(action, dict)
            or set(action) != {"operation", "arguments"}
            or type(action["operation"]) is not str
            or action["operation"] not in TOOLS
            or type(action["arguments"]) is not dict
        ):
            raise ValueError("Unknown Golden action or untyped arguments")
        if schema_errors(action["arguments"], schemas[action["operation"]]):
            raise ValueError("Golden arguments violate the published native tool schema")
    if len(value["actions"]) != 1 and any(
        action["operation"] == "recommend" for action in value["actions"]
    ):
        raise ValueError(
            "Final recommendation needs a separate turn after actual tool observations"
        )
    return value["actions"]


def tool_turn(episode, text):
    """Trusted scheduler only. The episode's credential never enters prompt/output."""
    from anvil.golden_kyc_openenv import GoldenAction

    observations = []
    for action in actions(text):
        observed = episode.step(
            GoldenAction(
                operation=action["operation"],
                arguments=action["arguments"],
                expected_generation=episode.credentials["generation"],
            )
        )
        observations.append({"operation": action["operation"], "result": observed.result})
        if observed.done:
            break
    return {"actions": observations, "closed": observed.done}


def record_turn(c, project, plan_id, stage, text, observation):
    # Each recorded turn corresponds to one completed, budget-fenced SDK response.
    call = one(
        c,
        "SELECT * FROM anvil.harbor_agent_calls WHERE project_id=%s AND plan_id=%s AND stage_index=%s AND status='completed'",
        (project, plan_id, stage),
    )
    if not call or call["output_json"]["text"] != text:
        raise RuntimeError("Golden turn requires exact completed broker response")
    c.execute(
        "INSERT INTO banking.paid_agent_observations(project_id,plan_id,stage_index,action_sha256,observation,observation_sha256) VALUES(%s,%s,%s,%s,%s,%s)",
        (
            project,
            plan_id,
            stage,
            digest(load(text.encode())),
            Jsonb(observation),
            digest(observation),
        ),
    )
