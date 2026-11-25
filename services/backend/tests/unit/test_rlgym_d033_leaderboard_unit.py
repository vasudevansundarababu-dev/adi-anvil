"""D-033: only runs ticked "Count this run on the leaderboard" at New run are ranked. The tick is off by default, is
frozen in the run manifest (inside manifest_sha256), and runs admitted before D-033 are not counted (no backfill)."""

import inspect

from anvil.rlgym import routes
from anvil.rlgym.results import leaderboard
from anvil.rlgym.runs import service


class FakeConn:
    def __init__(self, results):
        self.results, self.sql = list(results), []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        rows = self.results.pop(0)

        class R:
            def fetchone(self):
                return rows

            def fetchall(self):
                return rows

        return R()


def test_leaderboard_reads_only_ticked_runs_and_says_how_to_add_one():
    c = FakeConn([{"project_id": "prj_1", "name": "KYC"}, []])
    out = leaderboard.leaderboard(c, "ws", "prj_1")
    assert leaderboard.ON_BOARD in c.sql[1]
    assert leaderboard.ON_BOARD.startswith("(m.manifest->'leaderboard')::boolean IS TRUE")
    assert "(m.manifest->'test_only') IS NULL" in leaderboard.ON_BOARD  # test-only runs never count
    assert out["rows"] == [] and out["run"] is None
    assert out["empty"] == (
        "No leaderboard runs yet. Tick 'Count this run on the leaderboard' when you start a run."
    )


def test_home_counts_only_ticked_runs_as_results():
    src = inspect.getsource(routes)
    assert "AND (m.manifest->'leaderboard')::boolean IS TRUE" in src


def test_tick_is_off_by_default_strict_and_frozen_in_the_manifest():
    check = inspect.getsource(service.admission_check)
    assert (
        '"leaderboard": body.get("leaderboard") is True' in check
    )  # "yes", 1 or absent → not counted
    manifest = inspect.getsource(service._manifest)
    assert '"leaderboard": bool(s.get("leaderboard"))' in manifest
    # The run's flag is read back from the frozen manifest, never from an editable column.
    assert 'm["manifest"].get("leaderboard") is True' in inspect.getsource(service.get_run)
    assert "(m.manifest->'leaderboard')::boolean leaderboard" in inspect.getsource(
        service.list_runs
    )
