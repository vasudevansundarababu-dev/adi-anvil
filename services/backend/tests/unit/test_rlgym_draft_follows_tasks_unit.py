"""A suite draft follows the project's ready tasks (run 2, 25 Nov 2026: the default draft was created while the only
task was blocked, stayed at 0 tasks after it turned ready, and could not be saved). Whenever the project's task states
are refreshed, each open draft gains the newly ready tasks and drops the ones no longer ready; rows of tasks that stay
are untouched (their captured policy_id_map, D-056). Saved versions are never touched."""

import inspect

from anvil.rlgym.projects import service as projects
from anvil.rlgym.suites import service as suites


def test_changes_are_the_difference():
    add, drop = suites.draft_task_changes({"a", "b"}, {"b", "c"})
    assert add == ["c"] and drop == ["a"]
    assert suites.draft_task_changes({"a"}, {"a"}) == ([], [])
    assert suites.draft_task_changes(set(), {"x"}) == (["x"], [])


def test_only_drafts_are_synced():
    src = inspect.getsource(suites.sync_drafts)
    assert "state='draft'" in src
    assert "INSERT INTO suites.suite_tasks" in src and "DELETE FROM suites.suite_tasks" in src
    assert "latest_map(" in src  # a newly added task captures its newest map, as a new draft does


def test_the_project_refresh_syncs_the_drafts():
    assert "sync_drafts(" in inspect.getsource(projects.refresh_state)
