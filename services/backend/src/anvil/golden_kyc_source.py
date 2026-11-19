"""Read exact source inventory without importing API configuration."""

import hashlib

from anvil.db import digest
from anvil.qualification_resources import PACKAGING_INPUTS, qualification_path, qualification_root


def _source_paths(repository):
    root = repository / "services/backend/src/anvil"
    paths = (
        sorted(root.glob("golden_kyc_*.py"))
        + sorted(root.glob("kyc_policy_*.py"))
        + sorted(root.glob("marketing_task2_*.py"))
        + sorted(root.glob("marketing_paid_*.py"))
        + sorted(root.glob("marketing_native_*.py"))
        + sorted(root.glob("marketing_world_*.py"))
        + sorted(root.glob("marketing_capture_*.py"))
        + sorted(root.glob("marketing_private_grade*.py"))
        + sorted(root.glob("marketing_private_actor*.py"))
        + sorted(root.glob("marketing_private_result*.py"))
        + sorted(root.glob("marketing_private_capture*.py"))
        + sorted(root.glob("campaign_semantic_*.py"))
        + [
            root / "policy_rules.py",
            root.parents[1] / "migrations/129_kyc_scoped_policy_reviews.sql",
            root.parents[1] / "migrations/130_po_attested_offline_publication.sql",
            root.parents[1] / "migrations/131_offline_published_status_spelling.sql",
            root.parents[1] / "migrations/132_golden_scheduler_project_fence.sql",
            root / "praxis_offline_publication.py",
            root / "praxis_offline_publication_api.py",
            root / "qualification_resources.py",
            root / "software_resource_proof.py",
            root / "owned_process_group.py",
            root / "evaluator_runtimes.py",
            root / "evaluator_configurations.py",
            root / "benchmark_project_import.py",
            root / "benchmark_runs.py",
            root / "benchmark_run_api.py",
            root / "benchmark_run_views.py",
            root / "benchmark_run_pdf.py",
            root / "environment_runtime.py",
            root / "praxis_case_dataset.py",
            root / "project_bindings.py",
            root / "project_input_contract.py",
            root / "project_inputs.py",
            root / "project_input_provisioning.py",
            root.parents[1] / "migrations/102_project_execution_inputs.sql",
            root / "praxis_project_intake.py",
            root / "praxis_template_registry.py",
            root / "praxis_template_source.py",
            root / "db.py",
            root / "harbor_agent_source.py",
            root / "task_safety_payload.py",
            root / "cloud_secrets.py",
            root / "workspace_secrets.py",
            root / "workspace_credentials.py",
            root / "workspace_dispatch.py",
            root / "workspace_execution.py",
            root / "pilot_budget.py",
            root / "providers.py",
            root / "custom_evaluators.py",
            root / "custom_python_executor.py",
            root / "custom_python_worker.py",
            root / "custom_python_grading.py",
            root / "golden_component_qualification.py",
            root / "shared_execution_budget.py",
            root / "governed_ai_catalogue.py",
            root / "governed_ai_runtime.py",
            root / "golden_targets.py",
            root / "diagnostic_measures.py",
            root / "diagnostic_producers.py",
            root / "diagnostic_effects.py",
            root / "marketing_campaign_provisioning.py",
            root / "campaign_grader.py",
            root / "campaign_effects.py",
            root / "campaign_ordinal.py",
            root / "native_ordinal.py",
            root / "native_semantic.py",
            root / "native_semantic_validation.py",
            root / "diagnostic_projection.py",
            root / "marketing_response_diagnostics.py",
            root / "marketing_paid_reconstruction.py",
            root / "marketing_world_requests.py",
            root / "marketing_graph_result.py",
            root / "marketing_world_definition.py",
            root / "marketing_world_registry.py",
            root / "marketing_world_role.py",
            root / "marketing_world_api.py",
            root / "marketing_world_release.py",
            root / "marketing_world_quiescence.py",
            root / "worker_dispatch_broker.py",
            root / "api.py",
            root / "request_limits.py",
            root / "praxis_workload_identity.py",
            root / "native_diagnostic.py",
            root / "diagnostic_bindings.py",
            root / "campaign_reference_bindings.py",
            root / "golden_evaluator_register.json",
            root / "golden_skill_metadata.json",
            root / "kyc_registry_database.py",
            root / "marketing_attester_enrollment.py",
            root / "marketing_enrollment_read_database.py",
            root / "marketing_operator_database.py",
            root / "marketing_graph_checkpoint_database.py",
            root / "skill_step_bindings.py",
            root / "expert_reviews.py",
            root / "report_visuals.py",
            root / "task_safety.py",
            root / "task_safety_runtime.py",
            root / "task_safety_sources.py",
            root / "task_safety_promptfoo.py",
            root.parents[3] / "integrations/evaluators/promptfoo/redteam-worker.mjs",
            root.parents[1] / "migrations/104_task_safety_sources.sql",
            root.parents[1] / "migrations/105_marketing_paid_execution.sql",
            root.parents[1] / "migrations/106_campaign_semantic_judge.sql",
            root.parents[1] / "migrations/107_marketing_response_protocol.sql",
            root.parents[1] / "migrations/108_marketing_private_world.sql",
            root.parents[1] / "migrations/109_fixed_semantic_judge.sql",
            root.parents[1] / "migrations/110_marketing_world_quiescence.sql",
            root.parents[1] / "migrations/111_marketing_service_effects.sql",
            root.parents[1] / "migrations/112_marketing_campaign_effects.sql",
            root.parents[1] / "migrations/113_marketing_capture_intake.sql",
            root.parents[1] / "migrations/114_marketing_opening_program.sql",
            root.parents[1] / "migrations/115_marketing_source_population.sql",
            root.parents[1] / "migrations/116_marketing_api_evidence.sql",
            root.parents[1] / "migrations/117_marketing_cleanup_deadline.sql",
            root.parents[1] / "migrations/118_kyc_application_policy_registry.sql",
            root.parents[1] / "migrations/119_marketing_attester_enrollment.sql",
            root.parents[1] / "migrations/120_kyc_resolved_inputs.sql",
            root.parents[1] / "migrations/121_marketing_private_grade_evidence.sql",
            root.parents[1] / "migrations/122_marketing_private_actor_custody.sql",
            root.parents[1] / "migrations/123_marketing_private_result_custody.sql",
            root.parents[1] / "migrations/124_marketing_private_capture_acceptance.sql",
            root.parents[1] / "migrations/125_marketing_private_ordinal_context.sql",
            root.parents[1] / "migrations/126_marketing_private_capture_guards.sql",
            root.parents[1] / "migrations/127_kyc_application_policy_materializations.sql",
            root / "runtime_admin.py",
            root / "marketing_mcp.py",
            root / "praxis_marketing_contract.py",
            root / "task_method_compatibility.py",
            root / "workspace_preparation.py",
            root / "golden_native_bridge.py",
            root / "golden_phase_checkpoints.py",
            root / "golden_mcp_client.py",
            root / "golden_mcp_server.py",
            root / "environment_harbor.py",
            root.parents[2] / "harbor/src/anvil_harbor/sme.py",
            root.parents[2] / "harbor/src/anvil_harbor/environment.py",
            root.parents[1] / "migrations/075_golden_kyc.sql",
            root.parents[1] / "migrations/076_golden_kyc_anvil.sql",
            root.parents[1] / "migrations/080_golden_paid_calls.sql",
            root.parents[1] / "migrations/081_praxis_workload_identity.sql",
            root.parents[1] / "migrations/083_project_bindings.sql",
            root.parents[1] / "migrations/084_custom_python_evaluators.sql",
            root.parents[1] / "migrations/085_praxis_project_intakes.sql",
            root.parents[1] / "migrations/086_private_python_grading.sql",
            root.parents[1] / "migrations/087_private_grading_reconciliation.sql",
            root.parents[1] / "migrations/088_shared_execution_budgets.sql",
            root.parents[1] / "migrations/089_governed_ai_runtime.sql",
            root.parents[1] / "migrations/090_task_safety_evidence.sql",
            root.parents[1] / "migrations/091_expert_result_reviews.sql",
            root.parents[1] / "migrations/092_policy_python_scope.sql",
            root.parents[1] / "migrations/093_bound_state_policy_materializations.sql",
            root.parents[1] / "migrations/094_marketing_native_tool_receipts.sql",
            root.parents[1] / "migrations/095_marketing_workflow_effects.sql",
            root.parents[1] / "migrations/096_campaign_dataset_registry.sql",
            root.parents[1] / "migrations/097_runtime_admin.sql",
            root.parents[1] / "migrations/098_safety_prompt_qualification.sql",
            root.parents[1] / "migrations/099_campaign_private_grading.sql",
            root.parents[1] / "migrations/100_diagnostic_reference_custody.sql",
            root.parents[2] / "backend/uv.lock",
            root.parents[2] / "openenv/uv.lock",
        ]
    )
    paths.extend(sorted((repository / "services/harbor/src/anvil_harbor").glob("marketing_private_*.py")))
    paths.extend(repository / relative for relative in PACKAGING_INPUTS)
    paths.extend(
        repository / relative
        for relative in (
            "integrations/evaluators/local_worker.py",
            "integrations/evaluators/nemo/uv.lock",
            "integrations/evaluators/promptfoo/worker.mjs",
            "integrations/evaluators/promptfoo/package-lock.json",
        )
    )
    return paths


def source_hash(*, _resource_proof=None):
    from anvil.software_resource_proof import checked_root, checked_sha256

    repository = qualification_root() if _resource_proof is None else checked_root(_resource_proof)
    paths = _source_paths(repository)
    return digest(
        {
            str(p.relative_to(repository)): hashlib.sha256(
                qualification_path(repository, str(p.relative_to(repository))).read_bytes()
            ).hexdigest() if _resource_proof is None else checked_sha256(_resource_proof, str(p.relative_to(repository)))
            for p in paths
        }
    )
