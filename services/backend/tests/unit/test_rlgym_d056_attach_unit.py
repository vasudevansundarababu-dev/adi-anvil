"""D-056 (attach maps additively): a re-export of the same revision and package may bring Authoring's policy_id_map. It
is appended to projects.task_policy_maps keyed to the import, never written to projects.task_imports. A new suite draft
captures each task's newest map; the suite hash includes the maps only when some task has one, so every existing suite
keeps its hash; admission and the manifest use the captured map, never a later attachment. The episode page, run page
and report show what the map did. Synthetic data only."""

import inspect

from anvil.rlgym.common import sha
from anvil.rlgym.projects import service as projects
from anvil.rlgym.results import episodes, report
from anvil.rlgym.runs import policy_ids
from anvil.rlgym.runs import service as runs
from anvil.rlgym.suites import service as suites

MAP = {"environment_version": "golden-kyc-openenv@12", "map": {"doc": ["KYC-01"]}, "policies": {}}


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Conn:
    """Answers the queries _attach_map / _content issue; records every statement."""

    def __init__(self, maps=(), suite_maps=()):
        self.maps, self.suite_maps, self.sql = list(maps), list(suite_maps), []

    def execute(self, sql, params=()):
        self.sql.append((sql, params))
        if sql.lstrip().startswith("INSERT INTO projects.task_policy_maps"):
            self.maps.insert(0, {"id": params[0], "map_sha256": params[5]})
            return Rows([])
        if "FROM projects.task_policy_maps WHERE task_import_id" in sql:
            return Rows(self.maps[:1])
        if "JOIN projects.task_policy_maps m" in sql:
            return Rows(self.suite_maps)
        if "SELECT t.package_sha256 FROM suites.suite_tasks" in sql:
            return Rows([{"package_sha256": "a" * 64}])
        if "FROM suites.data_plans" in sql or "FROM suites.ts_plans" in sql:
            return Rows([])
        return Rows([])

    def inserts(self):
        return [s for s, _ in self.sql if s.lstrip().startswith("INSERT")]

    def updates(self):
        return [s for s, _ in self.sql if s.lstrip().upper().startswith("UPDATE")]


def test_no_map_attaches_nothing():
    c = Conn()
    assert projects._attach_map(c, "ws", "imp-1", "exp-2", None) is False
    assert c.inserts() == []


def test_a_map_on_an_existing_import_is_appended_never_updated():
    c = Conn()
    assert projects._attach_map(c, "ws", "imp-1", "exp-2", MAP) is True
    (sql, params) = next((s, p) for s, p in c.sql if s.lstrip().startswith("INSERT"))
    assert "projects.task_policy_maps" in sql and "task_imports" not in sql
    assert params[2:6] == ("imp-1", "exp-2", params[4], sha(MAP))
    assert c.updates() == []


def test_the_same_map_again_is_not_attached_twice_and_a_different_one_is_appended():
    c = Conn()
    projects._attach_map(c, "ws", "imp-1", "exp-2", MAP)
    assert projects._attach_map(c, "ws", "imp-1", "exp-3", MAP) is False
    other = {**MAP, "map": {"doc": ["KYC-01", "KYC-02"]}}
    assert projects._attach_map(c, "ws", "imp-1", "exp-4", other) is True
    assert len(c.inserts()) == 2 and c.maps[0]["map_sha256"] == sha(other)  # newest first
    assert c.updates() == []


def test_the_newest_map_is_read_newest_first():
    src = inspect.getsource(projects.latest_map)
    assert "ORDER BY received_at DESC" in src and "LIMIT 1" in src


def test_import_counts_map_attached_instead_of_unchanged_and_never_writes_the_column():
    src = inspect.getsource(projects.receive_export)
    assert 'counts["map_attached"] += 1' in src
    assert (
        'if _attach_map(c, ws, same_rev["id"], body["export_id"], task.get("policy_id_map")):'
        in src
    )
    # The 064 column stays unused: the INSERT passes None for it.
    assert (
        "# D-056: the map is kept in projects.task_policy_maps (below), not in this column (left unused).\n                None,"
        in src
    )
    # Receipts keep their shape when nothing was attached.
    assert 'if k != "map_attached" or v' in src


def test_suite_hash_is_unchanged_without_maps():
    content = suites._content(Conn(), "sv-1")
    assert "policy_maps" not in content
    assert set(content) == {"bindings", "criteria", "tasks", "plan", "cells", "ts"}


def test_suite_hash_changes_when_a_task_carries_a_map():
    plain = suites._content(Conn(), "sv-1")
    mapped = suites._content(
        Conn(suite_maps=[{"package_sha256": "a" * 64, "map_sha256": sha(MAP)}]), "sv-1"
    )
    assert mapped["policy_maps"] == [["a" * 64, sha(MAP)]]
    assert {k: v for k, v in mapped.items() if k != "policy_maps"} == plain
    assert sha(mapped) != sha(plain)


def test_a_new_draft_captures_the_newest_map():
    src = inspect.getsource(suites._new_version_row)
    assert 'pm = latest_map(c, t["id"])' in src and "policy_map_id" in src


def test_admission_and_manifest_use_the_captured_map_only():
    src = inspect.getsource(runs.admission_check) + inspect.getsource(runs)
    assert "LEFT JOIN projects.task_policy_maps pm ON pm.id=s.policy_map_id" in src
    manifest = inspect.getsource(runs._manifest)
    assert '"policy_id_map": t["captured_policy_id_map"]' in manifest
    assert 't["policy_id_map"]' not in manifest  # never the import row's (unused) column


def test_summary_counts_applied_and_warned():
    applied = {
        "applied": True,
        "warning": None,
        "rules": [{"original": "doc", "shown": ["KYC-01"]}],
    }
    warned = {
        "applied": False,
        "warning": "policy_id_map is for @11, but this run uses @12; S4 left as authored",
        "rules": [],
    }
    out = policy_ids.summarize([applied, applied, warned, None])
    assert out["applied"] == 2 and out["warned"] == 1
    assert out["rules"] == [{"original": "doc", "shown": ["KYC-01"]}]
    assert out["warnings"] == [{"reason": warned["warning"], "episodes": 1}]


def test_episode_run_and_report_show_the_record():
    assert '"policy_map": (bundle or {}).get("policy_id_map")' in inspect.getsource(episodes.view)
    assert '"policy_maps": policy_map_outcomes(d)' in inspect.getsource(report.overview)
    assert '{"policy_maps": _policy_maps(ctx, run_id)}' in inspect.getsource(runs)
