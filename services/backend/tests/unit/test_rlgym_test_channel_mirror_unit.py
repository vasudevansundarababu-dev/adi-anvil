"""Studio's version.registered for kyc-judgment-openenv-test@1 (seq 34) went out without `channel`; the live record
says "test". The mirror never trusts a missing channel on a -test key: it reads the live record, mirrors only when that
says "test", and otherwise refuses (an identity conflict, never a real version). A -test key is always channel test.
Real projects' selection also excludes anything on the test channel or under a -test key."""

import inspect

from anvil.rlgym.catalog import registry, selection

V = {"id": "kyc-judgment-openenv-test@1", "contract_id": "kyc-judgment-openenv-test"}


def test_a_test_key_without_channel_takes_it_from_the_live_record():
    assert registry.resolve_channel(V, lambda vid: {"channel": "test"}) == ("test", None)


def test_a_test_key_the_record_does_not_call_test_is_refused():
    ch, problem = registry.resolve_channel(V, lambda vid: {})
    assert ch is None and "not mirrored" in problem
    ch, problem = registry.resolve_channel(
        {**V, "channel": "release"}, lambda vid: {"channel": "test"}
    )
    assert ch is None and "not mirrored" in problem


def test_an_unreadable_record_is_refused_never_guessed():
    def boom(vid):
        raise RuntimeError("registry down")

    ch, problem = registry.resolve_channel(V, boom)
    assert ch is None and "couldn't read" in problem


def test_releases_are_untouched_and_never_fetched():
    def never(vid):
        raise AssertionError("no fetch for a release")

    assert registry.resolve_channel(
        {"id": "kyc-judgment-openenv@1", "contract_id": "kyc-judgment-openenv"}, never
    ) == (None, None)
    assert registry.resolve_channel(
        {"id": "golden-kyc-openenv@12", "contract_id": "golden-kyc-openenv", "channel": "test"},
        never,
    ) == ("test", None)


def test_the_mirror_and_the_backfill_use_it():
    src = inspect.getsource(registry.apply_event)
    assert "resolve_channel(" in src
    assert "resolve_channel(" in inspect.getsource(registry.backfill_test_channels)


class FakeC:
    def __init__(self):
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))

        class R:
            def fetchall(self_inner):
                return []

        return R()


def test_real_projects_never_select_test_versions():
    c = FakeC()
    selection.selectable_environments(c, "kyc-judgment-openenv")
    sql = c.sql[-1][0]
    assert "v.channel IS NULL" in sql and "NOT LIKE '%%-test'" in sql


def test_admission_checks_the_libraries_hash_the_version_pins():
    from anvil.rlgym.runs import service as runs

    assert "env_judgment_part(" in inspect.getsource(runs.admission_check)
    assert "_scorer_pins(vid, base)" in inspect.getsource(runs.env_judgment_part)
