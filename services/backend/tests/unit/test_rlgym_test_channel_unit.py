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


class ProjectC(FakeC):
    """Answers the project lookup with a test_only flag; every other query returns nothing."""

    def __init__(self, test_only):
        super().__init__()
        self.test_only = test_only

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        flag = self.test_only

        class R:
            def fetchall(self_inner):
                return []

            def fetchone(self_inner):
                return {"test_only": flag} if "FROM projects.projects" in sql else None

        return R()


RULE = {
    "workspace_id": "ws",
    "project_id": "prj_t",
    "alias": "kyc",
    "contract_id": "kyc-judgment-openenv",
    "kind": "latest",
}


def test_a_project_rule_follows_its_projects_test_only_flag():
    """The import binding, reselection and project state all resolve a test-only project's rules with the test
    channel; a real project's rules never see it."""
    from anvil.rlgym.catalog import selection

    c = ProjectC(True)
    selection.resolve_environment(c, RULE)
    assert "v.channel='test'" in c.sql[-1][0]
    c = ProjectC(False)
    selection.resolve_environment(c, RULE)
    assert "v.channel='test'" not in c.sql[-1][0]
    c = ProjectC(True)  # an explicit flag wins and no project lookup is made
    selection.resolve_environment(c, RULE, allow_test=False)
    assert len(c.sql) == 1 and "v.channel='test'" not in c.sql[-1][0]
    c = ProjectC(
        True
    )  # a rule without a project (e.g. a template default) never sees the test channel
    selection.resolve_environment(c, {k: v for k, v in RULE.items() if k != "project_id"})
    assert len(c.sql) == 1 and "v.channel='test'" not in c.sql[-1][0]


def test_a_new_project_is_marked_test_only_before_its_first_rules_resolve():
    from anvil.rlgym.projects import service as projects

    src = inspect.getsource(projects.receive_export)
    assert src.index("SET test_only=true") < src.index(
        "_initial_rules(c, ws, project_id, activation)"
    )
    initial = inspect.getsource(projects._initial_rules)
    assert '"project_id": project_id' in initial and '"workspace_id": ws' in initial


def test_project_created_is_audited_once_for_every_new_project():
    from anvil.rlgym.projects import service as projects

    src = inspect.getsource(projects.receive_export)
    created = src.index('"project.created"')
    assert src.rindex("if not project:", 0, created) > src.index('"project.test_only"')
