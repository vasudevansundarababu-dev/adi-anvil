"""Actual published fixture contract, manufactured role inputs; no SDK authority."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from anvil.marketing_paid_contract import campaign_output, check_schema, phase, role_prompt, turn


def execution():
    return json.loads(
        (Path(__file__).parents[1] / "fixtures/veyra-template-execution-v3.json").read_text()
    )


@pytest.mark.parametrize(
    "node_id,role",
    [
        ("intake", "orchestrator"),
        ("intent_step", "intent"),
        ("performance_step", "performance"),
        ("brief_step", "brief"),
        ("policy_step", "policy"),
    ],
)
def test_five_roles_use_exact_published_node_inputs_and_only_role_tools(node_id, role):
    contract = execution()
    node = next(node for node in contract["workflow_graph"]["nodes"] if node["id"] == node_id)
    inputs = {key: {"software_control": True} for key in node["inputRefs"]}
    context = phase(contract, node_id, inputs, 1, 1)
    assert context["role"] == role
    rendered = role_prompt({"task_id": "manufactured-shared-campaign"}, contract, context, [])
    payload = json.loads(rendered.split("\n", 1)[1])
    assert {tool["id"] for tool in payload["tools"]} == set(context["role_definition"]["tools"])
    assert len(rendered.encode()) <= 32768
    assert payload["phase"]["inputs"] == inputs
    assert turn('{"artifact":{"candidate_claim":"not authority"}}', contract, role)["artifact"]


def test_role_switch_extra_input_and_out_of_window_phase_rejected():
    contract = execution()
    context = phase(contract, "intent_step", {"assignments": {}, "released_evidence": {}}, 1, 1)
    changed = context | {"role": "policy"}
    with pytest.raises(ValueError, match="Exact role phase"):
        role_prompt({}, contract, changed, [])
    with pytest.raises(ValueError, match="no extra role context"):
        phase(contract, "intent_step", context["inputs"] | {"foreign_artifact": {}}, 1, 1)
    with pytest.raises(ValueError, match="window"):
        phase(contract, "intent_step", context["inputs"], 13, 1)
    with pytest.raises(ValueError, match="agent node"):
        phase(contract, "start", {}, 1, 1)


def test_tools_and_node_completion_cannot_share_unseen_results_or_override_role():
    contract = execution()
    assert turn('{"actions":[{"operation":"context.read","arguments":{}}]}', contract, "intent")
    for value in (
        {"actions": [{"operation": "campaign_findings.write", "arguments": {}}]},
        {"actions": [], "artifact": {}},
        {"artifact": {}, "role": "policy"},
        {"actions": []},
    ):
        with pytest.raises(ValueError):
            turn(json.dumps(value), contract, "intent")


def test_context_limit_never_silently_drops_task_or_observations():
    contract = execution()
    context = phase(contract, "intent_step", {"assignments": {}, "released_evidence": {}}, 1, 1)
    with pytest.raises(ValueError, match="silently dropped"):
        role_prompt({"authored_instructions": "x" * 32768}, contract, context, [])
    changed = deepcopy(context)
    changed["node"]["instruction"] = "different task"
    with pytest.raises(ValueError, match="Exact role phase"):
        role_prompt({}, contract, changed, [])


def test_final_output_uses_unchanged_authored_campaign_schema():
    contract = execution()
    assert campaign_output(
        contract,
        status="awaiting_authority",
        weekly_review_refs=[],
        evidence_refs=[],
        hold_reason="A justified recorded host limit",
    ) == {
        "outcome": "awaiting_authority",
        "weekly_review_refs": [],
        "evidence_refs": [],
        "hold_reason": "A justified recorded host limit",
    }
    with pytest.raises(ValueError):
        campaign_output(contract, status="campaign_closed", weekly_review_refs=[], evidence_refs=[])
    closed = campaign_output(
        contract,
        status="campaign_closed",
        weekly_review_refs=["host-effect:week" + str(week) for week in range(1, 13)],
        evidence_refs=[],
        closeout_report_ref="host-effect:closeout",
        workflow_state={
            "terminal": "done",
            "week": 12,
            "completed": {"weekly": list(range(1, 13))},
            "artifacts": {"closeout_report": {}},
        },
    )
    assert closed["outcome"] == "campaign_closed"
    with pytest.raises(ValueError, match="twelve-window"):
        campaign_output(
            contract,
            status="campaign_closed",
            weekly_review_refs=["week1"],
            evidence_refs=[],
            closeout_report_ref="unproved",
        )
    with pytest.raises(ValueError, match="oneOf"):
        check_schema("x", {"oneOf": [{"type": "string"}, {"const": "x"}]})
    with pytest.raises(ValueError, match="value mismatch"):
        check_schema(True, {"const": 1})
