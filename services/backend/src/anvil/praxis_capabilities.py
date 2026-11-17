"""Anvil-owned catalogue; recognition is never a claim of runtime qualification."""

from anvil.praxis_generic_contract import FIELD_TYPES, SCHEMA_KEYS, digest

VERSION = "1.1.0"


def catalogue(version=VERSION):
    if version not in {"1.0.0", "1.1.0", "1.2.0", "1.3.0"}:
        raise ValueError("Unknown immutable catalogue version")
    value = {
        "schema_version": "anvil.capability-catalogue.v1",
        "version": version,
        "environment_adapters": [
            {
                "id": "structured-decision-v1",
                "version": "1",
                "status": "software_qualifiable",
                "network": "none",
                "reset": "new_episode",
                "isolation": "per_episode",
            },
            {
                "id": "recorded-tools-v1",
                "version": "1",
                "status": "qualification_required",
                "network": "none",
                "reset": "new_episode",
                "isolation": "per_episode",
            },
            {
                "id": "golden-kyc-postgres-v1",
                "version": "1",
                "status": "frozen_golden_profile_only",
            },
            {"id": "multi-agent-graph-v1", "version": "1", "status": "structural_only"},
        ],
        "evaluator_kinds": [
            {
                "id": "output-reference-v1",
                "version": "1",
                "status": "software_qualifiable",
                "evidence_source": "output",
            },
            {
                "id": "run-evidence-v1",
                "version": "1",
                "status": "normalizer_qualification_required",
                "evidence_source": "run_evidence",
            },
            {
                "id": "trace-v1",
                "version": "1",
                "status": "normalizer_qualification_required",
                "evidence_source": "trace",
            },
            {
                "id": "business-table-v1",
                "version": "1",
                "status": "table_qualification_required",
                "evidence_source": "business_table",
            },
            {
                "id": "human-judge-v1",
                "version": "1",
                "status": "independent_human_assignment_required",
                "evidence_source": "human",
            },
        ],
        "graph": {
            "schema": "praxis.workflow_graph.v1",
            "status": "structural_only",
            "node_types": [
                "input",
                "agent_step",
                "decision",
                "join",
                "human_step",
                "output",
                "escalation",
            ],
            "maximum_nodes": 100,
            "maximum_edges": 300,
        },
        "json_schema": {
            "dialect": "anvil-bounded-json-schema-v1",
            "keywords": sorted(SCHEMA_KEYS),
            "remote_refs": False,
        },
        "praxis_field_types": sorted(FIELD_TYPES),
        "run_admission": "separate_not_granted",
        "paid_calls": False,
    }
    if version in {"1.1.0", "1.2.0"}:
        value["environment_adapters"].append(
            {
                "id": "golden-kyc-openenv-v2",
                "version": "1",
                "status": "installed_qualification_required",
                "network": "none",
                "reset": "new_episode",
                "isolation": "per_episode",
            }
        )
        value["evaluator_kinds"].append(
            {
                "id": "golden-kyc-rubric-v1",
                "version": "1",
                "status": "installed_qualification_required",
                "evidence_source": "run_evidence",
            }
        )
    if version == "1.2.0":
        value["environment_adapters"].append(
            {
                "id": "golden-kyc-openenv-v2",
                "version": "2",
                "status": "installed_qualification_required",
                "network": "none",
                "reset": "new_episode",
                "isolation": "per_episode",
                "task_mode": "reusable_state_workflow",
                "case_dataset_schema": "anvil.application-case-dataset.v1",
                "case_assignment": "per_episode_not_authored_task",
                "policy_scopes": {"template": "federal", "task": "state"},
            }
        )
    if version == "1.3.0":
        value["environment_adapters"] = [
            {
                "id": "marketing-task2-us-v1",
                "version": "1",
                "status": "qualification_required",
                "task_mode": "reusable_five_role_campaign",
                "case_dataset_schema": "anvil.campaign-case-dataset.v1",
                "isolation": "per_campaign_episode",
                "network": "none",
            }
        ]
        value["evaluator_kinds"] = [
            {
                "id": "marketing-task2-evidence-v1",
                "version": "1",
                "status": "qualification_required",
                "evidence_source": "run_evidence",
                "scale": "zero_to_four",
            }
        ]
        value["graph"] = value["graph"] | {
            "schema": "praxis.workflow_graph.v1-proposed",
            "node_types": value["graph"]["node_types"] + ["external_system"],
            "role_count": 5,
            "campaign_weeks": 12,
            "maximum_revision_rounds": 2,
        }
        value["json_schema"] = value["json_schema"] | {
            "dialect": "anvil-bounded-marketing-json-schema-v1",
            "keywords": sorted(SCHEMA_KEYS | {"oneOf"}),
        }
    return value | {"sha256": digest(value)}


def requirements(spec):
    catalog = catalogue(spec.execution.catalogue_version)
    issues = []
    environment = next(
        (
            v
            for v in catalog["environment_adapters"]
            if v["id"] == spec.execution.environment.id
            and v["version"] == spec.execution.environment.version
        ),
        None,
    )
    if not environment:
        issues.append("AV_CAPABILITY_UNAVAILABLE")
    elif environment["status"] not in {"software_qualifiable", "installed_qualification_required"}:
        issues.append("AV_ENVIRONMENT_PROVISIONING_REQUIRED")
    for item in spec.execution.evaluators:
        entry = next(
            (
                v
                for v in catalog["evaluator_kinds"]
                if v["id"] == item.capability.id and v["version"] == item.capability.version
            ),
            None,
        )
        if (
            not entry
            or entry["status"] not in {"software_qualifiable", "installed_qualification_required"}
            or entry["evidence_source"] != item.evidence_source
        ):
            issues.append("AV_EVALUATOR_BINDING_REQUIRED")
        if not entry:
            issues.append("AV_CAPABILITY_UNAVAILABLE")
    if (
        getattr(spec.execution, "graph_node_types", None)
        or spec.execution.schema_version == "anvil.template-execution.v3"
    ):
        issues.append("AV_GRAPH_RUNTIME_UNQUALIFIED")
    if (
        getattr(spec.execution, "rules", None)
        and spec.execution.environment.id != "golden-kyc-openenv-v2"
    ):
        # A cited hash/reference is not proof that a policy runtime was installed.
        issues.append("AV_POLICY_BINDING_REQUIRED")
    return sorted(set(issues))
