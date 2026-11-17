import json
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from anvil.db import digest
from anvil.marketing_task2_workflow import advance, compile_graph, initial


def execution():
    return json.loads(
        (Path(__file__).parents[1] / "fixtures/veyra-template-execution-v3.json").read_text()
    )


def candidate(node, inputs, week, visit):
    artifacts = {
        "campaign_plan": {
            "action": "creative" if week == 1 else "hold",
            "reason": "Manufactured software control",
        },
        "campaign_findings": {"outcome": "clear"},
        "approval_status": {"decision": "approved"},
        "weekly_review": {"campaign_complete": week == 12},
    }
    return {
        "artifact": artifacts.get(node.get("outputArtifact"), {"week": week, "node": node["id"]}),
        "receipt": {"input_sha256": digest(inputs), "origin": "manufactured_software_control"},
        "port": "responded" if node["type"] == "human_step" else None,
    }


def test_real_langgraph_executes_five_role_graph_join_and_twelve_windows_without_model_calls():
    seen = []

    def effect(node, inputs, week, visit):
        seen.append((node["id"], node.get("roleId"), week, set(inputs)))
        return candidate(node, inputs, week, visit)

    graph = compile_graph(execution(), effect, lambda week: {"week": week}, MemorySaver())
    result = graph.invoke(
        initial({"case": "synthetic"}, {"week": 1}),
        {
            "configurable": {"thread_id": "software-only"},
            "recursion_limit": 410,
        },
    )
    assert result["terminal"] == "done"
    assert result["completed"]["weekly"] == list(range(1, 13))
    assert result["transitions"] < 400
    assert {role for _, role, _, _ in seen if role} == {
        "orchestrator",
        "intent",
        "performance",
        "brief",
        "policy",
    }
    for week in range(1, 13):
        cycle = [row[0] for row in seen if row[2] == week]
        assert cycle.index("intent_step") < cycle.index("decide")
        assert cycle.index("performance_step") < cycle.index("decide")
    assert all(
        inputs == {"intent_assessment", "performance_assessment"}
        for node, role, week, inputs in seen
        if node == "decide"
    )
    assert "private_reference" not in str(result)


def test_actor_cannot_finish_early_or_reuse_previous_cycle_artifacts():
    contract = execution()
    state = initial({}, {"week": 1})
    state.update(
        pending=["campaign_over"], artifacts={"weekly_review": {"campaign_complete": True}}
    )
    assert (
        advance(contract, state, candidate, None)["reason"]
        == "candidate_cannot_end_campaign_before_window_twelve"
    )
    state.update(
        pending=["campaign_over"],
        artifacts={
            "weekly_review": {"campaign_complete": False},
            "campaign_context": {},
            "campaign_plan": {"old": True},
        },
    )
    result = advance(contract, state, candidate, lambda week: {"week": week})
    assert result["week"] == 2
    assert set(result["artifacts"]) == {"campaign_context", "released_evidence"}


def test_unknown_decision_missing_join_and_loop_exhaustion_escalate():
    contract = execution()
    state = initial({}, {})
    state["pending"] = ["analyses"]
    assert advance(contract, state, candidate, None)["reason"] == "missing_required_join_producer"
    state["pending"] = ["findings"]
    state["artifacts"] = {"campaign_findings": {"outcome": "creative_finding"}}
    state["loops"] = {"creative_revision:1": 2}
    assert advance(contract, state, candidate, None)["reason"] == "loop_limit:creative_revision"
    state.update(pending=["route"], artifacts={})
    assert advance(contract, state, candidate, None)["pending"] == ["awaiting_authority"]


def test_graph_enforces_transition_limit_and_boolean_wire_type():
    state = initial({}, {})
    state["transitions"] = 400
    assert advance(execution(), state, candidate, None)["reason"] == "transition_limit"
    state.update(
        transitions=0,
        pending=["campaign_over"],
        artifacts={"weekly_review": {"campaign_complete": 0}},
    )
    assert advance(execution(), state, candidate, None)["pending"] == ["awaiting_authority"]
