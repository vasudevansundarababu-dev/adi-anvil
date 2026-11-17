"""New opening-source/workflow controls; no SQL, native run or model call."""

from copy import deepcopy

import pytest
from test_marketing_activation_definition import proposal
from test_marketing_task2_workflow import candidate, execution

from anvil.marketing_paid_contract import phase
from anvil.marketing_task2_workflow import advance, initial_opening
from anvil.marketing_world_definition import definition
from anvil.marketing_world_opening_definition import with_opening


def artifact():
    return {"week": 0, "phase": "opening", "operator_program_id": "marketing-opening0-and-twelve-reviews-v1",
            "world_receipt_ref": "manufactured-opening-receipt-not-authority"}


def test_original_opening_runs_actual_published_roles_then_twelve_review_cycles():
    seen = []
    releases = []

    def effect(node, inputs, week, visit):
        seen.append((week, node["id"], deepcopy(inputs)))
        result = candidate(node, inputs, week, visit)
        if node["id"] == "decide" and week == 0:
            result["artifact"]["action"] = "creative"
        return result

    def release(week):
        releases.append(week)
        assert any(w == 0 and node == "weekly" for w, node, _ in seen)
        return {"week": week, "evidence_refs": ["review:" + str(week)]}

    state = initial_opening({"case_id": "synthetic"}, artifact())
    for _ in range(execution()["workflow_graph"]["limits"]["maxTransitions"] + 1):
        if state["terminal"]:
            break
        state = advance(execution(), state, effect, release)
    assert state["terminal"] == "done"
    assert state["completed"]["weekly"] == list(range(13))
    assert state["loops"]["weekly_cycle"] == 12
    assert releases == list(range(1, 13))
    opening = [(node, inputs) for week, node, inputs in seen if week == 0]
    assert {node for node, _ in opening} >= {"intake", "intent_step", "performance_step", "decide", "brief_step", "policy_step"}
    assert all("review:" not in str(inputs) for _, inputs in opening)


@pytest.mark.parametrize("field,value", [("week", True), ("week", 1), ("phase", "review"),
                                          ("world_receipt_ref", ""), ("operator_program_id", "legacy")])
def test_opening_cannot_be_relabelled_from_an_ordinary_window(field, value):
    released = artifact() | {field: value}
    with pytest.raises(ValueError, match="explicit opening"):
        initial_opening({}, released)


def test_opening_role_phase_is_explicit_and_legacy_phase_does_not_accept_zero():
    contract = execution()
    node = next(n for n in contract["workflow_graph"]["nodes"] if n["type"] == "agent_step")
    inputs = {key: {} for key in node["inputRefs"]}
    with pytest.raises(ValueError, match="bounded Marketing window"):
        phase(contract, node["id"], inputs, 0, 1)
    assert phase(contract, node["id"], inputs, 0, 1, opening=True)["schema_version"] == "anvil.marketing-opening-role-phase.v1"


def test_explicit_v5_binds_original_january4_opening_and_preserves_twelve_report_dates():
    _, previous = proposal()
    before = deepcopy(previous)
    value = with_opening(previous)
    world = definition(value)
    assert world.start.isoformat() == "2027-01-04T00:00:00+00:00"
    assert world.opening.week == 0 and len(world.windows) == 12
    assert value["windows"] == previous["windows"] and previous == before
    assert world.windows[-1].instant.isoformat() == "2027-03-31T00:00:00+00:00"
    assert world.controller(0)._clock == "2027-01-04T00:00:00+00:00"


def test_v5_opening_cannot_be_shifted_to_feedback_date():
    _, previous = proposal()
    value = with_opening(previous)
    value["start"] = value["opening"]["instant"] = value["windows"][0]["instant"]
    with pytest.raises(ValueError):
        definition(value)
