"""The separate verifier shares the bounded task stage allowance."""

import tomllib

import pytest

from anvil.environment_harbor import layout_projection


@pytest.mark.parametrize("seconds", [1, 30, 90, 300])
def test_actor_and_separate_verifier_use_same_bounded_stage_budget(tmp_path, seconds):
    projection = layout_projection(tmp_path, {"synthetic": True}, actor_seconds=seconds, mediated_candidate=True)
    task = tomllib.loads(projection["task.toml"])
    assert task["agent"]["timeout_sec"] == seconds
    assert task["verifier"]["timeout_sec"] == seconds
    assert task["verifier"]["environment_mode"] == "separate"


@pytest.mark.parametrize("seconds", [0, 301, -1, True, 300.0])
def test_stage_allowance_cannot_extend_the_existing_five_minute_limit(tmp_path, seconds):
    with pytest.raises(ValueError):
        layout_projection(tmp_path, {}, actor_seconds=seconds, mediated_candidate=True)


def test_existing_legacy_actor_ceiling_does_not_expand_the_verifier_ceiling(tmp_path):
    task = tomllib.loads(layout_projection(tmp_path, {}, actor_seconds=900)["task.toml"])
    assert task["agent"]["timeout_sec"] == 900
    assert task["verifier"]["timeout_sec"] == 300
