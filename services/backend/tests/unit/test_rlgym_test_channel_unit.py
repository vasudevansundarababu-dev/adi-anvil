"""Studio's test channel (56d80fd): versions recorded under a key ending -test with registry channel "test", never
qualified. In RL Gym only a test-only project may bind one; a run on one is never leaderboard-eligible; it's labelled
TEST. Versions without a channel (every release so far) are unchanged."""

import inspect
from pathlib import Path

from anvil.rlgym.catalog import registry
from anvil.rlgym.results import report
from anvil.rlgym.runs import service as runs
from anvil.rlgym.suites import service as suites

TEST_V = {"id": "kyc-judgment-openenv-test@1", "channel": "test", "state": "registered"}
REAL_V = {"id": "kyc-judgment-openenv@1", "state": "qualified"}


def test_only_a_test_only_project_may_bind_a_test_channel_version():
    assert suites.test_channel_problem(TEST_V, {"test_only": True}) is None
    why = suites.test_channel_problem(TEST_V, {"test_only": False})
    assert why and "test-only project" in why
    assert suites.test_channel_problem(REAL_V, {"test_only": False}) is None
    assert "test_channel_problem(" in inspect.getsource(suites.resolve_binding)


def test_the_channel_is_mirrored():
    sql = (Path(__file__).resolve().parents[2] / "migrations/070_rlgym_env_channel.sql").read_text()
    assert "ADD COLUMN channel text" in sql
    assert 'v.get("channel")' in inspect.getsource(registry._upsert_version)


def test_never_leaderboard_eligible_and_labelled():
    resolved = {
        "evaluator_versions": [{"x": 1}],
        "env_row": {**TEST_V, "state": "qualified"},
        "project": {"test_only": True},
    }
    out = runs.leaderboard_eligibility(resolved, [{"system_id": "m", "live": True}])
    assert out["eligible"] is False and any("test channel" in r for r in out["reasons"])
    assert '"channel"' in inspect.getsource(runs._manifest)
    assert "test_channel" in inspect.getsource(report.header)


class FakeC:
    def __init__(self):
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))

        class R:
            def fetchall(self_inner):
                return []

            def fetchone(self_inner):
                return None

        return R()


def test_a_test_only_project_can_select_test_candidates_and_a_real_one_cannot():
    from anvil.rlgym.catalog import selection

    c = FakeC()
    selection.selectable_environments(c, "kyc-judgment-openenv")
    sql, params = c.sql[-1]
    assert "v.channel='test'" not in sql and params == ("kyc-judgment-openenv",)
    selection.selectable_environments(c, "kyc-judgment-openenv", allow_test=True)
    sql, params = c.sql[-1]
    assert "v.channel='test'" in sql and "kyc-judgment-openenv-test" in params
    assert "allow_test=" in inspect.getsource(suites.resolve_binding)
