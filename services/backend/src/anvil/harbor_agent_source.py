"""Exact broker source inventory without API settings or credentials."""

import hashlib

from anvil.db import digest
from anvil.qualification_resources import PACKAGING_INPUTS, qualification_path, qualification_root


def code_digest():
    ROOT = qualification_root()
    paths = [
        ROOT / "services/backend/src/anvil" / name
        for name in (
            "harbor_agents.py",
            "harbor_agent_source.py",
            "task_safety_payload.py",
            "qualification_resources.py",
            "harbor_worker.py",
            "pilot_native_api.py",
            "pilot_native_worker.py",
            "workflow_native.py",
            "workflow_native_execution.py",
            "workflow_registry.py",
            "workflow_runtime.py",
            "workflow_journal.py",
            "pilot_concurrency.py",
            "environment_structured_agent.py",
            "environment_harbor.py",
            "native_image_profile.py",
            "native_process_identity.py",
            "environment_collect.py",
            "environment_temp.py",
            "benchmark_qualification.py",
            "harbor_package.py",
            "praxis_contract.py",
            "praxis_executable.py",
            "task_parser.py",
            "praxis_staged.py",
            "providers.py",
            "db.py",
            "auth.py",
            "config.py",
            "domain.py",
            "artifacts.py",
            "marketing_authority.py",
            "workspace_execution.py",
            "workspace_costs.py",
            "workspace_dispatch.py",
            "workspace_adapter_contracts.py",
            "workspace_preparation.py",
            "project_bindings.py",
            "praxis_project_intake.py",
            "custom_evaluators.py",
            "custom_python_executor.py",
            "custom_python_worker.py",
            "custom_python_grading.py",
            "golden_component_qualification.py",
            "shared_execution_budget.py",
            "governed_ai_catalogue.py",
            "governed_ai_runtime.py",
            "golden_targets.py",
            "diagnostic_effects.py",
            "golden_evaluator_register.json",
            "expert_reviews.py",
            "report_visuals.py",
            "task_safety.py",
            "marketing_mcp.py",
            "marketing_task2_tools.py",
            "marketing_task2_openenv.py",
            "marketing_task2_store.py",
            "marketing_task2_runtime.py",
            "marketing_paid_contract.py",
            "marketing_paid_session.py",
            "marketing_paid_package.py",
            "marketing_paid_budget.py",
            "marketing_paid_qualification.py",
            "marketing_paid_turn.py",
            "marketing_paid_state.py",
            "marketing_paid_roles.py",
            "marketing_paid_graph.py",
            "marketing_paid_dispatch_transport.py",
            "marketing_paid_dispatch_rpc.py",
            "marketing_paid_world.py",
            "marketing_paid_world_rpc.py",
            "marketing_paid_world_transport.py",
            "marketing_paid_execution.py",
            "marketing_campaign_provisioning.py",
            "campaign_effects.py",
            "campaign_ordinal.py",
            "native_ordinal.py",
            "native_semantic.py",
            "native_semantic_validation.py",
            "diagnostic_projection.py",
            "marketing_response_diagnostics.py",
            "marketing_paid_reconstruction.py",
            "marketing_world_requests.py",
            "marketing_graph_result.py",
            "marketing_world_definition.py",
            "marketing_world_registry.py",
            "marketing_world_role.py",
            "marketing_world_api.py",
            "marketing_world_release.py",
            "marketing_world_quiescence.py",
            "native_diagnostic.py",
            "diagnostic_bindings.py",
            "praxis_marketing_contract.py",
            "task_method_compatibility.py",
            "workspace_models.py",
            "workspace_credentials.py",
            "workspace_secrets.py",
            "cloud_secrets.py",
            "pilot_environment.py",
            "pilot_budget.py",
            "worker_dispatch_broker.py",
            "environment_structured_agent.py",
            "harbor_worker.py",
            "import_codegen.py",
            "import_execution.py",
            "import_sandbox.py",
            "import_generation.py",
        )
    ]
    paths.append(ROOT / "services/harbor/src/anvil_harbor/agent.py")
    paths.append(ROOT / "services/harbor/src/anvil_harbor/tool_agent.py")
    paths.append(ROOT / "services/harbor/src/anvil_harbor/environment.py")
    paths.append(ROOT / "services/harbor/src/anvil_harbor/sme.py")
    paths.append(ROOT / "services/backend/migrations/083_project_bindings.sql")
    paths.append(ROOT / "services/backend/migrations/084_custom_python_evaluators.sql")
    paths.append(ROOT / "services/backend/migrations/085_praxis_project_intakes.sql")
    paths.append(ROOT / "services/backend/migrations/086_private_python_grading.sql")
    paths.append(ROOT / "services/backend/migrations/087_private_grading_reconciliation.sql")
    paths.append(ROOT / "services/backend/migrations/088_shared_execution_budgets.sql")
    paths.append(ROOT / "services/backend/migrations/089_governed_ai_runtime.sql")
    paths.append(ROOT / "services/backend/migrations/090_task_safety_evidence.sql")
    paths.append(ROOT / "services/backend/migrations/091_expert_result_reviews.sql")
    paths.append(ROOT / "services/backend/migrations/092_policy_python_scope.sql")
    paths.append(ROOT / "services/backend/migrations/093_bound_state_policy_materializations.sql")
    paths.append(ROOT / "services/backend/migrations/094_marketing_native_tool_receipts.sql")
    paths.append(ROOT / "services/backend/migrations/105_marketing_paid_execution.sql")
    paths.append(ROOT / "services/backend/migrations/106_campaign_semantic_judge.sql")
    paths.append(ROOT / "services/backend/migrations/107_marketing_response_protocol.sql")
    paths.append(ROOT / "services/backend/migrations/108_marketing_private_world.sql")
    paths.append(ROOT / "services/backend/migrations/109_fixed_semantic_judge.sql")
    paths.append(ROOT / "services/backend/migrations/110_marketing_world_quiescence.sql")
    paths.append(ROOT / "services/backend/migrations/111_marketing_service_effects.sql")
    paths.append(ROOT / "services/backend/migrations/112_marketing_campaign_effects.sql")
    paths.append(ROOT / "services/backend/migrations/113_marketing_capture_intake.sql")
    paths.append(ROOT / "services/backend/migrations/114_marketing_opening_program.sql")
    paths.append(ROOT / "services/backend/migrations/115_marketing_source_population.sql")
    paths.append(ROOT / "services/backend/migrations/116_marketing_api_evidence.sql")
    paths.append(ROOT / "services/backend/migrations/117_marketing_cleanup_deadline.sql")
    paths.extend(sorted((ROOT / "services/backend/src/anvil").glob("campaign_semantic_*.py")))
    paths.extend(sorted((ROOT / "services/backend/src/anvil").glob("golden_kyc_*.py")))
    paths.extend(sorted((ROOT / "services/backend/src/anvil").glob("marketing_task2_*.py")))
    paths.extend(sorted((ROOT / "services/backend/src/anvil").glob("marketing_native_*.py")))
    paths.extend(sorted((ROOT / "services/backend/src/anvil").glob("marketing_world_*.py")))
    paths.extend(sorted((ROOT / "services/backend/src/anvil").glob("marketing_capture_*.py")))
    paths.extend(sorted((ROOT / "services/backend/src/anvil").glob("marketing_private_grade*.py")))
    paths.extend(sorted((ROOT / "services/backend/src/anvil").glob("marketing_private_actor*.py")))
    paths.extend(sorted((ROOT / "services/backend/src/anvil").glob("marketing_private_result*.py")))
    paths.extend(sorted((ROOT / "services/backend/src/anvil").glob("marketing_private_capture*.py")))
    paths.extend(ROOT / "services/backend/src/anvil" / name for name in (
        "golden_kyc_type_index.py", "golden_kyc_application_plan.py", "golden_kyc_policy_registry.py",
        "golden_kyc_v7_candidate.py", "golden_kyc_v7_export.py", "golden_kyc_resolved_dataset.py",
        "golden_kyc_resolved_store.py",
        "golden_kyc_application_policy.py",
        "golden_kyc_binding_ancestry.py", "golden_kyc_input_binding.py", "golden_kyc_policy_delivery.py",
        "golden_kyc_product_context.py", "golden_kyc_product_policy.py",
        "golden_kyc_source.py", "praxis_template_source.py", "golden_kyc_policy_runtime.py",
        "kyc_registry_database.py", "marketing_attester_enrollment.py",
        "marketing_enrollment_read_database.py",
        "marketing_operator_database.py",
        "marketing_graph_checkpoint_database.py",
    ))
    paths.append(ROOT / "services/backend/migrations/118_kyc_application_policy_registry.sql")
    paths.append(ROOT / "services/backend/migrations/119_marketing_attester_enrollment.sql")
    paths.append(ROOT / "services/backend/migrations/120_kyc_resolved_inputs.sql")
    paths.append(ROOT / "services/backend/migrations/121_marketing_private_grade_evidence.sql")
    paths.append(ROOT / "services/backend/migrations/122_marketing_private_actor_custody.sql")
    paths.append(ROOT / "services/backend/migrations/123_marketing_private_result_custody.sql")
    paths.append(ROOT / "services/backend/migrations/124_marketing_private_capture_acceptance.sql")
    paths.append(ROOT / "services/backend/migrations/125_marketing_private_ordinal_context.sql")
    paths.append(ROOT / "services/backend/migrations/126_marketing_private_capture_guards.sql")
    paths.append(ROOT / "services/backend/migrations/127_kyc_application_policy_materializations.sql")
    paths.extend(ROOT / "services/backend/src/anvil" / name for name in ("api.py", "request_limits.py", "praxis_workload_identity.py"))
    paths.extend(sorted((ROOT / "services/harbor/src/anvil_harbor").glob("marketing_private_*.py")))
    paths.extend(ROOT / relative for relative in PACKAGING_INPUTS)
    paths.extend(
        ROOT / relative
        for relative in (
            "integrations/evaluators/local_worker.py",
            "integrations/evaluators/nemo/uv.lock",
            "integrations/evaluators/promptfoo/worker.mjs",
            "integrations/evaluators/promptfoo/package-lock.json",
        )
    )
    return digest(
        {
            str(p.relative_to(ROOT)): hashlib.sha256(
                qualification_path(ROOT, str(p.relative_to(ROOT))).read_bytes()
            ).hexdigest()
            for p in paths
        }
    )
