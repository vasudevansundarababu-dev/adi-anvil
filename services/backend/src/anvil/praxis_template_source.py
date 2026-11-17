"""Read exact source inventory without importing API configuration."""

import hashlib

from anvil.praxis_generic_contract import digest
from anvil.qualification_resources import PACKAGING_INPUTS, qualification_path, qualification_root


def source_hash():
    repository = qualification_root()
    root = repository / "services/backend/src/anvil"
    names = (
        [p.name for p in root.glob("praxis_generic*.py")]
        + [p.name for p in root.glob("golden_kyc_*.py")]
        + [p.name for p in root.glob("campaign_semantic_*.py")]
        + [p.name for p in root.glob("marketing_task2_*.py")]
        + [p.name for p in root.glob("marketing_native_*.py")]
        + [p.name for p in root.glob("marketing_world_*.py")]
        + [p.name for p in root.glob("marketing_capture_*.py")]
        + [p.name for p in root.glob("marketing_private_grade*.py")]
        + [p.name for p in root.glob("marketing_private_actor*.py")]
        + [p.name for p in root.glob("marketing_private_result*.py")]
        + [p.name for p in root.glob("marketing_private_capture*.py")]
        + [
            "praxis_capabilities.py",
            "qualification_resources.py",
            "praxis_template_registry.py",
            "praxis_template_source.py",
            "praxis_template_client.py",
            "praxis_template_delivery.py",
            "dataset_export_api.py",
            "api.py",
            "request_limits.py",
            "dataset_export_window.py",
            "dataset_export_contract.py",
            "benchmark_storage.py",
            "artifacts.py",
            "auth.py",
            "pilot_environment.py",
            "db.py",
            "harbor_agent_source.py",
            "task_safety_payload.py",
            "cloud_secrets.py",
            "workspace_secrets.py",
            "workspace_credentials.py",
            "workspace_dispatch.py",
            "workspace_execution.py",
            "pilot_budget.py",
            "providers.py",
            "worker_dispatch_broker.py",
            "praxis_golden_kyc.py",
            "praxis_case_dataset.py",
            "praxis_case_registry.py",
            "praxis_campaign_registry.py",
            "praxis_workload_identity.py",
            "praxis_project_intake.py",
            "project_input_contract.py",
            "project_inputs.py",
            "project_input_provisioning.py",
            "praxis_marketing_contract.py",
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
            "golden_targets.py",
            "diagnostic_measures.py",
            "golden_evaluator_register.json",
            "golden_skill_metadata.json",
            "golden_kyc_type_index.py",
            "golden_kyc_v7_candidate.py",
            "golden_kyc_v7_export.py",
            "golden_kyc_resolved_dataset.py",
            "golden_kyc_resolved_store.py",
            "golden_kyc_application_policy.py",
            "golden_kyc_binding_ancestry.py",
            "golden_kyc_input_binding.py",
            "golden_kyc_policy_delivery.py",
            "golden_kyc_product_context.py",
            "golden_kyc_product_policy.py",
            "golden_kyc_source.py",
            "golden_kyc_policy_runtime.py",
            "golden_kyc_application_plan.py",
            "golden_kyc_policy_registry.py",
            "kyc_registry_database.py",
            "marketing_attester_enrollment.py",
            "marketing_enrollment_read_database.py",
            "marketing_operator_database.py",
            "marketing_graph_checkpoint_database.py",
            "skill_step_bindings.py",
            "golden_kyc_criterion_support.py",
            "golden_component_qualification.py",
            "task_safety_sources.py",
            "task_safety_promptfoo.py",
        ]
    )
    def source_bytes(path):
        return qualification_path(
            repository, str(path.relative_to(repository))
        ).read_bytes()

    hashes = {n: hashlib.sha256(source_bytes(root / n)).hexdigest() for n in names}
    backend = root.parents[1]
    for relative in (
        "uv.lock",
        "pyproject.toml",
        "migrations/079_praxis_generic_contract.sql",
        "migrations/081_praxis_workload_identity.sql",
        "migrations/085_praxis_project_intakes.sql",
        "migrations/096_campaign_dataset_registry.sql",
        "migrations/105_marketing_paid_execution.sql",
        "migrations/106_campaign_semantic_judge.sql",
        "migrations/107_marketing_response_protocol.sql",
        "migrations/108_marketing_private_world.sql",
        "migrations/109_fixed_semantic_judge.sql",
        "migrations/110_marketing_world_quiescence.sql",
        "migrations/111_marketing_service_effects.sql",
        "migrations/112_marketing_campaign_effects.sql",
        "migrations/113_marketing_capture_intake.sql",
        "migrations/114_marketing_opening_program.sql",
        "migrations/115_marketing_source_population.sql",
        "migrations/116_marketing_api_evidence.sql",
        "migrations/117_marketing_cleanup_deadline.sql",
        "migrations/118_kyc_application_policy_registry.sql",
        "migrations/119_marketing_attester_enrollment.sql",
        "migrations/120_kyc_resolved_inputs.sql",
        "migrations/121_marketing_private_grade_evidence.sql",
        "migrations/122_marketing_private_actor_custody.sql",
        "migrations/123_marketing_private_result_custody.sql",
        "migrations/124_marketing_private_capture_acceptance.sql",
        "migrations/125_marketing_private_ordinal_context.sql",
        "migrations/126_marketing_private_capture_guards.sql",
        "migrations/127_kyc_application_policy_materializations.sql",
    ):
        hashes[relative] = hashlib.sha256(source_bytes(backend / relative)).hexdigest()
    hashes["safety-source-migration"] = hashlib.sha256(
        source_bytes(backend / "migrations/104_task_safety_sources.sql")
    ).hexdigest()
    hashes["promptfoo-generation-worker"] = hashlib.sha256(
        source_bytes(repository / "integrations/evaluators/promptfoo/redteam-worker.mjs")
    ).hexdigest()
    for relative in (
        *PACKAGING_INPUTS,
        "integrations/evaluators/local_worker.py",
        "integrations/evaluators/nemo/uv.lock",
        "integrations/evaluators/promptfoo/worker.mjs",
        "integrations/evaluators/promptfoo/package-lock.json",
    ):
        hashes[relative] = hashlib.sha256(source_bytes(repository / relative)).hexdigest()
    for filename in sorted((repository / "services/harbor/src/anvil_harbor").glob("marketing_private_*.py")):
        hashes[filename.relative_to(repository).as_posix()] = hashlib.sha256(source_bytes(filename)).hexdigest()
    return digest(hashes)
