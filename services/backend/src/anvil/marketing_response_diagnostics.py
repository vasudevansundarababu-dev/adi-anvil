"""Observed response-protocol findings, not model-internal causal diagnoses.

The caller must bind the actual completed broker response and persist the
finding under its own job/lease. This pure classifier grants no such authority,
does not call tools and never produces a rubric award or execution claim.
"""

import hashlib
import sys
from importlib.metadata import version
from pathlib import Path

from anvil.marketing_paid_contract import turn
from anvil.praxis_generic_contract import digest, load
from anvil.praxis_marketing_contract import MarketingExecution

VERSION = "anvil.marketing-response-protocol-finding.v1"


def source_hash():
    root = Path(__file__).parent
    return digest(
        {
            "files": {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in (
                    "marketing_response_diagnostics.py",
                    "marketing_paid_contract.py",
                    "praxis_generic_contract.py",
                    "praxis_marketing_contract.py",
                    "praxis_case_dataset.py",
                    "marketing_task2_contract.py",
                    "dataset_export_contract.py",
                    "schemas.py",
                    "golden_targets.py",
                    "golden_evaluator_register.json",
                    "golden_skill_metadata.json",
                    "diagnostic_measures.py",
                    "diagnostic_effects.py",
                    "db.py",
                )
            },
            "packages": {name: version(name) for name in ("pydantic", "rfc8785")},
            "python": sys.version,
        }
    )


def inspect(text, execution, role):
    contract = MarketingExecution.model_validate(execution)
    roles = {item["id"] for item in contract.workflow_graph["roles"]}
    if role not in roles:
        raise ValueError("Invalid host-bound role; no candidate failure finding")
    if type(text) is not str or len(text) > 65536:
        raise ValueError("Bounded completed response text required")
    raw = text.encode("utf-8")
    if len(raw) > 65536:
        raise ValueError("Bounded completed UTF-8 response required")
    before = digest(execution)
    all_tools = {tool.id for tool in contract.tools}
    allowed = {tool.id for tool in contract.tools if role in tool.role_ids}
    known_requests = []
    try:
        value = turn(text, execution, role)
        known_requests = [action["operation"] for action in value.get("actions", [])]
        failure = None
    except (ValueError, RecursionError):
        try:
            value = load(raw)
        except (ValueError, RecursionError):
            value = None
            failure = "invalid_json"
        else:
            failure = "invalid_control_envelope"
            if type(value) is dict and set(value) == {"artifact"}:
                failure = "invalid_node_artifact"
            if type(value) is dict and set(value) == {"actions"}:
                actions = value["actions"]
                if type(actions) is not list or not 1 <= len(actions) <= 8:
                    failure = "invalid_action_population"
                else:
                    failure = "invalid_tool_arguments"
                    for action in actions:
                        if (
                            type(action) is not dict
                            or set(action) != {"operation", "arguments"}
                            or type(action["operation"]) is not str
                        ):
                            failure = "invalid_action_envelope"
                            break
                        operation = action["operation"]
                        if operation in all_tools:
                            known_requests.append(operation)
                        if operation not in all_tools:
                            failure = "unoffered_tool_requested"
                            break
                        if operation not in allowed:
                            failure = "tool_requested_outside_assigned_role"
                            break
    if digest(execution) != before:
        raise RuntimeError("Host execution contract changed; no candidate finding")
    return {
        "schema_version": VERSION,
        "classifier_source_sha256": source_hash(),
        "execution_sha256": before,
        "role": role,
        "response_text_sha256": hashlib.sha256(raw).hexdigest(),
        "protocol_status": "valid" if failure is None else "invalid",
        "observed_failure": failure,
        "known_requested_tool_ids": known_requests,
        "tool_request_list_complete": failure is None,
        "effects_assessed": False,
        "model_performance_validated": False,
        "internal_reasoning_assessed": False,
        "provenance_limitation": "File and installed-version fingerprint; loaded origins and runtime image require independent qualification",
        "scope": "Completed response protocol only; source custody, case/lease, effects and rubric decisions require separate verified records",
    }
