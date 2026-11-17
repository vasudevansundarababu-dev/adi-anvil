"""Manufactured SQL-shaped records, not actual SQL/native/model evidence."""

from copy import deepcopy
from uuid import uuid4

import pytest
from test_marketing_paid_world import fixture
from test_marketing_task2_workflow import candidate

from anvil.db import digest
from anvil.marketing_paid_reconstruction import load_turns, reconstruct, release_artifact
from anvil.marketing_task2_workflow import advance, initial, initial_opening
from anvil.praxis_generic_contract import digest as wire_digest


def records(monkeypatch, *, opening=False):
    _, prepared, bound = fixture(monkeypatch)
    execution = prepared["execution"]
    releases = []
    for week in range(1, 13):
        releases.append(
            {
                "schema_version": "anvil.marketing-world-release.v1",
                **{
                    key: bound[key]
                    for key in (
                        "world_binding_id",
                        "world_binding_sha256",
                        "episode_id",
                        "generation",
                        "case_id",
                        "case_snapshot_sha256",
                    )
                },
                "week": week,
                "released_at": "2026-11-14T00:00:00Z",
                "window_ref": "manufactured-window:" + str(week),
                "evidence_refs": [],
                "receipt_id": str(uuid4()),
                "receipt_sha256": "a" * 64,
            }
        )
    if opening:
        releases.insert(0, {**deepcopy(releases[0]), "schema_version": "anvil.marketing-world-opening-release.v1",
                            "week": 0, "phase": "opening", "operator_program_id": "marketing-opening0-and-twelve-reviews-v1",
                            "baseline_delivery_manifest": None, "receipt_id": str(uuid4()),
                            "released_at": "2027-01-04T00:00:00Z", "window_ref": "manufactured-opening"})
    effects, turns = [], []

    def effect(node, inputs, week, visit):
        result = candidate(node, inputs, week, visit)
        identifier = str(uuid4())
        receipt = {"input_sha256": digest(inputs)}
        if node["type"] == "agent_step":
            observation = {"artifact": result["artifact"], "actions": [], "completed_node": True}
            turn = {
                **{
                    key: bound[key]
                    for key in ("project_id", "plan_id", "job_id", "episode_id", "generation")
                },
                "stage_index": len(turns),
                "effect_id": identifier,
                "call_id": str(uuid4()),
                "response_sha256": "e" * 64,
                "role": node["roleId"],
                "origin": "sdk_mock",
                "observation": observation,
                "observation_sha256": digest(observation),
            }
            turns.append(turn)
            receipt.update(
                role=node["roleId"],
                stage_index=turn["stage_index"],
                physical_call_id=turn["call_id"],
                observation_sha256=turn["observation_sha256"],
                origin="completed_broker_and_tool_receipts",
            )
        else:
            receipt.update(
                artifact_sha256=wire_digest(result["artifact"]),
                post_state_sha256="d" * 64,
                world_binding_sha256=bound["world_binding_sha256"],
                world_effect_id=str(uuid4()),
                world_receipt_sha256="e" * 64,
                episode_id=bound["episode_id"],
                generation=0,
                node_id=node["id"],
                week=week,
                visit=visit,
                origin="persisted_environment_effect",
                simulated_environment=True,
            )
        result["receipt"] = receipt
        effects.append(
            {
                "id": identifier,
                **{
                    key: bound[key]
                    for key in ("project_id", "episode_id", "generation", "execution_sha256")
                },
                "node_id": node["id"],
                "week": week,
                "visit": visit,
                "node_sha256": digest(node),
                "input_sha256": digest(inputs),
                "state": "completed",
                "result": result,
                "result_sha256": digest(result),
            }
        )
        return result

    def released(week):
        return release_artifact(releases[week if opening else week - 1])

    state = (initial_opening(bound["campaign_context"], released(0)) if opening
             else initial(bound["campaign_context"], released(1)))
    while not state["terminal"]:
        state = advance(execution, state, effect, released)
    assert state["terminal"] == "done"
    return execution, bound, releases, effects, turns, state


def test_explicit_opening_and_twelve_reviews_reconstruct_from_recorded_effects_without_adapters(monkeypatch):
    execution, bound, releases, effects, turns, original = records(monkeypatch, opening=True)
    result = reconstruct(execution, bound, releases, effects, turns, opening_required=True)
    assert result["state"] == original
    assert result["schema_version"] == "anvil.marketing-workflow-reconstruction.v2"
    assert result["state"]["completed"]["weekly"] == list(range(13))
    assert result["state"]["loops"]["weekly_cycle"] == 12
    assert any(effect["week"] == 0 and effect["node_id"] == "decide" for effect in effects)
    assert result["model_performance_validated"] is False


def test_opening_program_cannot_close_from_twelve_review_only_records(monkeypatch):
    execution, bound, releases, effects, turns, _ = records(monkeypatch)
    with pytest.raises(ValueError, match="outside the actual reconstructed path"):
        reconstruct(execution, bound, releases, effects, turns, opening_required=True)


def test_legacy_reconstruction_does_not_silently_accept_thirteen_observations(monkeypatch):
    execution, bound, releases, effects, turns, _ = records(monkeypatch, opening=True)
    with pytest.raises(ValueError, match="Bounded complete SQL"):
        reconstruct(execution, bound, releases, effects, turns)


def test_twelve_window_state_reconstructed_from_records_without_reexecution(monkeypatch):
    execution, bound, releases, effects, turns, original = records(monkeypatch)
    before = deepcopy((releases, effects, turns))
    result = reconstruct(execution, bound, releases, effects, turns)
    assert result["state"] == original
    assert result["workflow_status"] == "closed"
    assert set(result["role_status"].values()) == {"closed"}
    assert result["model_origins"] == ["sdk_mock"]
    assert result["native_collection_required"] is True
    assert result["model_performance_validated"] is False
    assert (releases, effects, turns) == before


def test_unknown_last_effect_preserves_partial_roles_not_false_omission(monkeypatch):
    execution, bound, releases, effects, turns, _ = records(monkeypatch)
    effects[-1]["state"] = "execution_unknown"
    result = reconstruct(execution, bound, releases, effects, turns)
    assert result["workflow_status"] == "partial"
    assert result["partial_reason"] == "workflow_effect_execution_unknown"
    assert set(result["role_status"].values()) == {"partial"}


def test_cross_episode_or_changed_input_is_rejected(monkeypatch):
    execution, bound, releases, effects, turns, _ = records(monkeypatch)
    effects[0]["episode_id"] = str(uuid4())
    with pytest.raises(ValueError, match="scope"):
        reconstruct(execution, bound, releases, effects, turns)
    effects[0]["episode_id"] = bound["episode_id"]
    effects[0]["input_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="input"):
        reconstruct(execution, bound, releases, effects, turns)


def test_completed_artifact_without_completed_call_custody_is_rejected(monkeypatch):
    execution, bound, releases, effects, turns, _ = records(monkeypatch)
    with pytest.raises(ValueError, match="completed turn custody"):
        reconstruct(
            execution,
            bound,
            releases,
            effects,
            [],
        )
    turns[0]["role"] = "policy"
    with pytest.raises(ValueError, match="assigned role"):
        reconstruct(execution, bound, releases, effects, turns)


def test_extra_effect_outside_actual_path_cannot_be_hidden(monkeypatch):
    execution, bound, releases, effects, turns, _ = records(monkeypatch)
    extra = deepcopy(effects[0])
    extra.update(id=str(uuid4()), visit=400)
    effects.append(extra)
    with pytest.raises(ValueError, match="outside the actual reconstructed path"):
        reconstruct(execution, bound, releases, effects, turns)


def test_broken_sql_projection_cannot_silently_shrink_completed_turn_population():
    class Cursor:
        def fetchall(self):
            return [{"value": {"manufactured": True}}, {"value": None}]

    class Connection:
        def execute(self, sql, parameters):
            assert parameters == ("project", "plan")
            return Cursor()

    with pytest.raises(ValueError, match="Complete actual turn custody"):
        load_turns(Connection(), "project", "plan")


def test_missing_interior_turn_stage_is_not_complete_role_capture(monkeypatch):
    execution, bound, releases, effects, turns, _ = records(monkeypatch)
    turns.pop(1)
    with pytest.raises(ValueError, match="contiguous"):
        reconstruct(execution, bound, releases, effects, turns)
