"""Marketing-specific independent component proof, never spending authority."""

import os

from anvil.golden_component_qualification import installed as components
from anvil.golden_component_qualification import sha

CHECKS = (
    "case_membership",
    "five_role_consistency",
    "actual_sdk_mock_protocol",
    "twelve_window_graph",
    "role_openenv_mcp",
    "simulated_external_approval",
    "budget_admission_revocation",
    "claim_before_tool_effect",
    "unknown_no_replay",
    "source_actor_grader_isolation",
    "native_harbor_custody",
    "private_grading_and_report",
)


def installed(graph_sha256):
    common = components()
    if not common["ready"]:
        return {
            "ready": False,
            "missing": common["missing"] + ["marketing_runtime_qualification_required"],
        }
    section = common["evidence"].get("marketing_runtime")
    role_profiles = os.environ.get("ANVIL_RUNTIME_ROLE_PROFILES_SHA256")
    if (
        not isinstance(section, dict)
        or not sha(graph_sha256)
        or section.get("schema_version") != "anvil.marketing-runtime-component-qualification.v1"
        or section.get("origin") != "independent_qa"
        or section.get("scope") != "technical_marketing_runtime_only"
        or section.get("spending_authority") is not False
        or section.get("workflow_graph_sha256") != graph_sha256
        or not sha(role_profiles)
        or section.get("role_profiles_sha256") != role_profiles
    ):
        return {
            "ready": False,
            "missing": ["marketing_exact_graph_role_image_qualification_required"],
        }
    controls = section.get("checks")
    if not isinstance(controls, dict) or any(
        not isinstance(controls.get(name), dict)
        or controls[name].get("status") != "passed"
        or not sha(controls[name].get("evidence_sha256"))
        for name in CHECKS
    ):
        return {"ready": False, "missing": ["marketing_native_component_controls_required"]}
    return {
        "ready": True,
        "missing": [],
        "evidence": section,
        "scope": "technical_marketing_runtime_only",
        "spending_authority": False,
    }
