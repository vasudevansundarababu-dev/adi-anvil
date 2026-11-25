"""Authoring's test-only marker (Project.testOnly, exported as top-level `test_only: true`). RL Gym:
- keeps it on the project (sticky: a later export can't silently unlabel it) and freezes it in every run's manifest;
- labels the project, its suites, runs and reports TEST;
- never lets a test-only run on the leaderboard (the tick is refused and the leaderboard queries exclude it);
- keeps test-only projects off the cross-project home board (listed apart, labelled); an explicit run-vs-run comparison
  still works and labels each side."""

import inspect
from pathlib import Path

from anvil.rlgym import routes
from anvil.rlgym.projects import service as projects
from anvil.rlgym.results import leaderboard, report, skills
from anvil.rlgym.runs import service as runs
from anvil.rlgym.suites import service as suites


def test_the_field_and_the_column():
    sql = (Path(__file__).resolve().parents[2] / "migrations/069_rlgym_test_only.sql").read_text()
    assert "ADD COLUMN test_only boolean NOT NULL DEFAULT false" in sql
    src = inspect.getsource(projects.receive_export)
    assert 'body.get("test_only")' in src and "SET test_only=true" in src
    assert "test_only must be true or false" in src


def test_a_test_only_run_is_never_leaderboard_eligible():
    resolved = {
        "evaluator_versions": [{"x": 1}],
        "env_row": {"state": "qualified", "id": "e"},
        "project": {"test_only": True},
    }
    lines = [{"system_id": "m", "live": True}]
    out = runs.leaderboard_eligibility(resolved, lines)
    assert out["eligible"] is False and any("test-only" in r for r in out["reasons"])
    assert (
        runs.leaderboard_eligibility({**resolved, "project": {"test_only": False}}, lines)[
            "eligible"
        ]
        is True
    )


def test_manifests_and_leaderboards_carry_and_exclude_it():
    assert '"test_only"' in inspect.getsource(runs._manifest)
    assert "test_only" in leaderboard.ON_BOARD
    home = inspect.getsource(routes)
    assert "test_projects" in home and "test_only" in home


def test_labels_everywhere():
    assert "test_only" in inspect.getsource(report.header)
    assert "test_only" in inspect.getsource(suites.view)
    assert "test_only" in inspect.getsource(runs.list_runs)
    assert '"test_only"' in inspect.getsource(skills.run_profile)
