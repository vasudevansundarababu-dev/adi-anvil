"""Run-3 (25 Nov 2026): admission accepted a test-only run on kyc-judgment-openenv-test@3 (registry channel "test",
never qualified), but the worker refused to start it ("only qualified versions run"), so all 40 episodes errored.
The worker now starts the same versions selection allows: qualified ones, and, for a run whose frozen manifest is
test_only, a test-channel version that isn't revoked, deleted or failed."""

import inspect

from anvil.rlgym.runs import worker

TEST_ENV = {"id": "kyc-judgment-openenv-test@3", "state": "registered", "channel": "test"}
TEST_RUN = {"test_only": True, "environment": {"version_id": TEST_ENV["id"], "channel": "test"}}


def test_a_qualified_version_starts_for_any_run():
    assert worker.startable({"state": "qualified"}, {}) is None


def test_a_test_only_run_starts_a_test_channel_version():
    assert worker.startable(TEST_ENV, TEST_RUN) is None


def test_a_real_run_never_starts_a_test_channel_version():
    why = worker.startable(TEST_ENV, {"environment": TEST_RUN["environment"]})
    assert why and "only qualified versions run" in why


def test_a_withdrawn_test_version_never_starts():
    for state in ("revoked", "deleted", "failed"):
        assert worker.startable({**TEST_ENV, "state": state}, TEST_RUN)


def test_an_unqualified_real_version_never_starts():
    assert worker.startable({"id": "x@1", "state": "registered"}, TEST_RUN)


def test_the_worker_uses_it():
    assert 'startable(env, run["manifest"])' in inspect.getsource(worker.prepare_runs)


def test_a_mock_on_studios_image_gets_the_offered_operations():
    """The Judgment mocks take recommend's policy_bundle from the offered schema (run-0238: refused otherwise)."""
    src = inspect.getsource(worker)
    i = src.index("policy = mock_provider.agent(")
    assert "operations=" in src[i : i + 900]
