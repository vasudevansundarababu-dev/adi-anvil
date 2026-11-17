"""Original opening API/facade/result source checks; private SQL is mocked."""

import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_marketing_activation_definition import proposal
from test_marketing_paid_reconstruction import records
from test_marketing_paid_world import fixture

from anvil import marketing_world_opening as opening_api
from anvil.marketing_graph_result import validate_graph_result
from anvil.marketing_paid_contract import campaign_output
from anvil.marketing_paid_world import OpeningRelease, QualifiedWorld, WorldCall
from anvil.marketing_task2_persistence import freeze
from anvil.marketing_world_definition import definition
from anvil.marketing_world_opening_definition import with_opening
from anvil.praxis_generic_contract import canonical, digest


def setup(monkeypatch, *, allowed=True, replay=False):
    _, previous = proposal()
    world = definition(with_opening(previous))
    controller = world.controller(0)
    job, prepared, bound = fixture(monkeypatch)
    bound.update(episode_id=controller.trial_id, generation=controller.generation)
    _, sha = freeze(controller)
    row = {"last_week": 0, "attachment": bound, "controller_state_sha256": sha}
    raw = {"operator_program_id": world.operator_program_id, "effects": [], "turns": [], "releases": ["old"] if replay else []}
    monkeypatch.setattr(opening_api, "recorded", lambda *_: ({}, raw))
    calls = []

    def execute(sql, args):
        calls.append((sql, args))
        return SimpleNamespace(fetchone=lambda: {"allowed": allowed})

    claim = SimpleNamespace(job_id=job["id"], lease_token=job["lease_token"], plan_id=job["plan_id"])
    return claim, row, controller, world, prepared["execution"], SimpleNamespace(execute=execute), calls


def test_opening_receipt_projects_only_original_clock_inventory_without_state_mutation(monkeypatch):
    claim, row, controller, world, execution, connection, calls = setup(monkeypatch)
    before = freeze(controller)
    reply = opening_api.opening(connection, claim, row, controller, world, execution)
    assert reply["week"] == 0 and reply["released_at"] == "2027-01-04T00:00:00Z"
    assert reply["receipt_sha256"] == digest({key: value for key, value in reply.items() if key != "receipt_sha256"})
    assert len(calls) == 1 and "commit_private_world_opening" in calls[0][0]
    inventory = json.loads(calls[0][1][6])
    assert next(item for item in inventory if item["collection"] == "reports")["record_count"] == 0
    assert freeze(controller) == before


def test_uncertain_opening_commit_never_returns_receipt_or_retries(monkeypatch):
    claim, row, controller, world, execution, connection, calls = setup(monkeypatch, allowed=False)
    with pytest.raises(RuntimeError, match="unconfirmed_no_replay"):
        opening_api.opening(connection, claim, row, controller, world, execution)
    assert len(calls) == 1


def test_preexisting_opening_record_blocks_replay_before_any_new_commit(monkeypatch):
    claim, row, controller, world, execution, connection, calls = setup(monkeypatch, replay=True)
    with pytest.raises(ValueError, match="Fresh opening"):
        opening_api.opening(connection, claim, row, controller, world, execution)
    assert not calls


def result_fixture(monkeypatch):
    execution, bound, _, effects, turns, state = records(monkeypatch, opening=True)
    job, prepared, _ = fixture(monkeypatch)
    job.update(project_id=bound["project_id"], actor_id=bound["actor_id"], id=bound["job_id"], plan_id=bound["plan_id"])
    prepared["world_attachment"] = bound
    prepared["world_attachment_sha256"] = digest(bound)
    prepared["max_calls"] = 200
    world = QualifiedWorld(job, prepared, bound, absolute_deadline=200)
    refs = {row["id"]: "marketing-effect:" + row["id"] + ":" + row["result_sha256"] for row in effects}
    weekly = [refs[row["id"]] for row in effects if row["node_id"] == "weekly" and row["week"] > 0]
    output = campaign_output(execution, status="campaign_closed", weekly_review_refs=weekly,
                             evidence_refs=list(refs.values()), closeout_report_ref=refs[effects[-1]["id"]], workflow_state=state)
    receipt = {"schema_version": "anvil.marketing-paid-graph-receipt.v2", "project_id": job["project_id"],
               "job_id": job["id"], "plan_id": job["plan_id"], "trial_id": world.episode_id, "generation": world.generation,
               "execution_sha256": digest(execution), "workflow_state_sha256": digest(state), "output_sha256": digest(output),
               "turns": len(turns), "closed": True, "completed_weeks": list(range(1, 13)),
               "opening_completed": True, "opening_effect_refs": [refs[row["id"]] for row in effects if row["week"] == 0],
               "opening_release_ref": str(uuid4()) + ":" + "a" * 64, "model_performance_validated": False}
    return (output, receipt), job, prepared, world, state


def test_v2_result_preserves_opening_evidence_separately_from_twelve_weekly_refs(monkeypatch):
    result, job, prepared, world, state = result_fixture(monkeypatch)
    validate_graph_result(result, job=job, prepared=prepared, world=world, workflow_state=state)
    assert len(result[0]["weekly_review_refs"]) == 12
    assert not set(result[1]["opening_effect_refs"]) & set(result[0]["weekly_review_refs"])


@pytest.mark.parametrize("field,value", [("opening_completed", False), ("opening_effect_refs", []), ("opening_release_ref", "invented")])
def test_v2_closed_result_requires_opening_receipt_and_effects(monkeypatch, field, value):
    result, job, prepared, world, state = result_fixture(monkeypatch)
    changed = deepcopy(result)
    changed[1][field] = value
    with pytest.raises(ValueError, match="opening"):
        validate_graph_result(changed, job=job, prepared=prepared, world=world, workflow_state=state)


def test_ordinary_release_cannot_be_misread_as_opening(monkeypatch):
    _, _, releases, _, _, _ = records(monkeypatch)
    with pytest.raises(ValueError):
        OpeningRelease.model_validate(releases[0])
    assert canonical(releases[0])


def test_opening_facade_uses_once_only_opening_operation_and_retains_bound_receipt(monkeypatch):
    _, bound, releases, _, _, _ = records(monkeypatch, opening=True)
    job, prepared, _ = fixture(monkeypatch)
    job.update(project_id=bound["project_id"], actor_id=bound["actor_id"], id=bound["job_id"], plan_id=bound["plan_id"])
    prepared.update(world_attachment=bound, world_attachment_sha256=digest(bound))
    world = QualifiedWorld(job, prepared, bound, absolute_deadline=200)
    opening = releases[0]
    opening["receipt_sha256"] = digest({key: value for key, value in opening.items() if key != "receipt_sha256"})
    calls = []

    def call(operation, value, **options):
        calls.append((operation, value, options))
        return deepcopy(opening)

    monkeypatch.setattr(world, "_call", call)
    result = world.opening(phase_deadline=190)
    assert result["week"] == 0 and result["phase"] == "opening"
    assert calls == [("opening", {}, {"phase_deadline": 190})]
    for key in ("world_binding_id", "world_binding_sha256", "episode_id", "generation"):
        assert key in opening


@pytest.mark.parametrize("index", [False, True, 1, -1])
def test_opening_wire_index_must_be_strict_integer_zero(monkeypatch, index):
    _, _, releases, _, _, _ = records(monkeypatch, opening=True)
    with pytest.raises(ValueError):
        OpeningRelease.model_validate(releases[0] | {"week": index})


def test_opening_operation_cannot_smuggle_an_actor_chosen_clock_or_ordinary_zero_review(monkeypatch):
    job, _, bound = fixture(monkeypatch)
    scope = {key: bound[key] for key in ("world_binding_id", "world_binding_sha256", "episode_id", "generation")}
    claim = {"project_id": job["project_id"], "actor_id": job["actor_id"], "job_id": job["id"],
             "lease_token": job["lease_token"], "plan_id": job["plan_id"], "operation": "opening", "value": scope}
    assert WorldCall.model_validate(claim).operation == "opening"
    for changes in ({"operation": "opening", "value": scope | {"instant": "2027-03-31T00:00:00Z"}},
                    {"operation": "release", "value": scope | {"week": 0}}):
        with pytest.raises(ValueError):
            WorldCall.model_validate(claim | changes)
