"""Approved Golden design register projected onto exact imported source identities.

The register describes required measurements, not installed/qualified evaluators.
It does not add points, new tasks, policy approvals or scientific capability scores.
"""

import json
from pathlib import Path

from anvil.db import digest
from anvil.diagnostic_measures import measure_contract

REGISTER = json.loads(Path(__file__).with_name("golden_evaluator_register.json").read_text())
SKILL_METADATA = json.loads(Path(__file__).with_name("golden_skill_metadata.json").read_text())
DESIGN = {(row["domain"], row["id"]): row for row in SKILL_METADATA["targets"]}
DESIGN_ROLES = {
    "KYC agent": "kyc_analyst",
    "Intent Analyst": "intent_analyst",
    "Campaign Orchestrator": "campaign_orchestrator",
    "Creative Brief and Delivery Coordinator": "brief_delivery_coordinator",
    "Campaign Policy Reviewer": "campaign_policy_reviewer",
    "Performance and Budget Analyst": "performance_budget_analyst",
}


def design_metadata(domain, identifier):
    """Approved descriptive fields; never an authored node or runtime admission."""
    row = DESIGN[(domain, identifier)]
    return {
        key: row[key]
        for key in (
            "skill_name",
            "design_role",
            "design_step",
            "capability_association",
            "success_condition",
            "proposed_evaluator",
            "evidence_required",
            "counting_unit_or_trigger",
        )
    } | {
        "step_status": "exact_authored_step_mapping_required",
        "role_mapping_status": "approved_design_role_authored_mapping_required",
        "design_metadata_sha256": digest(SKILL_METADATA),
        "design_source_sha256": SKILL_METADATA["source_document_sha256"],
    }


def family(task):
    source = task.get("source", {})
    profile = source.get("template", {}).get("profile_id")
    if (
        profile == "golden-kyc-reusable-v1"
        or source.get("schema_version") == "anvil.golden-kyc.task.v1"
    ):
        return "kyc"
    if profile == "veyra-hush-one-launch-v1":
        return "marketing"
    return None


def definitions(domain):
    return [dict(row) for row in REGISTER["targets"] if row["domain"] == domain]


def requirements(task):
    domain = family(task)
    if domain is None:
        return []
    identity = {key: task.get(key) for key in ("task_id", "task_version", "payload_sha256")}
    result = []
    for row in definitions(domain):
        identifier = row["id"]
        metadata = design_metadata(domain, identifier)
        role = DESIGN_ROLES[metadata["design_role"]]
        conditional = identifier in {
            "K.TRANSLATE",
            "M.TRANSLATE",
            "M.LOCALE",
            "K.REPLY",
            "K.ASYNC",
            "M.DISAGREE",
        } or identifier.endswith("recovery")
        selector = {
            "design_target_id": identifier,
            "role": role,
            "register_sha256": digest(REGISTER),
        }
        target = (
            "criterion:" + digest(identity | {"criterion_id": identifier})
            if row["official"]
            else "skill:" + digest(identity | selector)
        )
        result.append(
            identity
            | row
            | metadata
            | {
                "target": target,
                "role": role,
                "step": None,
                "step_status": "exact_authored_step_mapping_required",
                "counting_unit": row["evidence_contract"].rsplit(";", 1)[-1].strip(),
                "skill_id": identifier,
                "skill": metadata["skill_name"],
                "criterion_id": identifier if row["official"] else None,
                "applicability": "conditional" if conditional else "required",
                "applicability_source": "Exact authored obligation and released episode evidence; conditional absence is not a pass",
                "scale": {
                    "kind": "native_points",
                    "levels": [0, 2, 5] if domain == "kyc" else [0, 1, 2, 3, 4],
                    "maximum": 5 if domain == "kyc" else 4,
                    "unit": "points",
                }
                if row["official"]
                else {
                    "kind": "diagnostic_measure",
                    "levels": [],
                    "maximum": None,
                    "unit": "evidence_contract_specific",
                    "measures": measure_contract(identifier),
                },
                "mapping_origin": "anvil_approved_golden_design_register",
                "register_sha256": digest(REGISTER),
                "register_source_sha256": REGISTER["source_sha256"],
                "qualified": False,
                "qualification_owner": "anvil",
                "capability_score": None,
                "status": "runtime_binding_and_evidence_required",
            }
        )
    return result


def counts(observations):
    """Counts retain units and missingness; no ordinal/capability composite."""
    result = {
        "required": 0,
        "ran": 0,
        "scored": 0,
        "passed": 0,
        "failed": 0,
        "unscored": 0,
        "inapplicable": 0,
        "operational_failures": 0,
    }
    for observation in observations:
        if observation["applicability"] == "not_applicable":
            result["inapplicable"] += 1
            continue
        result["required"] += 1
        if observation.get("ran") is True:
            result["ran"] += 1
        status = observation.get("status")
        if status in {"pass", "partial", "fail"}:
            result["scored"] += 1
            result["passed"] += status == "pass"
            result["failed"] += status == "fail"
        else:
            result["unscored"] += 1
        result["operational_failures"] += observation.get("failure_owner") == "environment_tool"
    result["pass_rate"] = (
        {"numerator": result["passed"], "denominator": result["scored"]}
        if result["scored"]
        else None
    )
    return result
