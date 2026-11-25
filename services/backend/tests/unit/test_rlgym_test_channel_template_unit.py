"""A test-channel template activation (the KYC Judgment v1 end-to-end test, before Studio's release). Studio sends its
usual evaluator registrations (A-06) and template activation (A-03) with `channel: "test"`. RL Gym activates it with
the normal checks and known-case qualification, except that its environments may be Studio's test-channel versions;
its qualification record to ADI Forge says channel "test". It never satisfies a real project's export (only an export
with test_only: true), is never leaderboard-eligible, and is labelled TEST. The channel is not part of spec_sha256."""

import inspect
from pathlib import Path

import pytest

from anvil.rlgym.catalog import templates
from anvil.rlgym.common import GymError
from anvil.rlgym.projects import service as projects
from anvil.rlgym.runs import service as runs


def test_the_channel_is_not_part_of_the_content_hash():
    doc = {"template_id": "t", "key": "k", "version": 1, "criteria": []}
    assert templates.content_sha256(doc) == templates.content_sha256({**doc, "channel": "test"})


def test_only_test_or_none_is_accepted():
    assert templates.activation_channel({}) is None
    assert templates.activation_channel({"channel": "test"}) == "test"
    with pytest.raises(GymError):
        templates.activation_channel({"channel": "beta"})


def test_a_real_activation_cannot_take_a_version_a_test_activation_holds():
    with pytest.raises(GymError) as e:
        templates.check_existing(
            {"channel": "test", "spec_sha256": "a"}, {"spec_sha256": "a"}, None
        )
    assert e.value.code == "CONFLICT" and "new version" in e.value.message
    assert (
        templates.check_existing(
            {"channel": None, "spec_sha256": "a"}, {"spec_sha256": "a"}, "test"
        )
        is True
    )
    assert (
        templates.check_existing(
            {"channel": "test", "spec_sha256": "a"}, {"spec_sha256": "a"}, "test"
        )
        is True
    )


def test_activation_wiring():
    src = inspect.getsource(templates.activate)
    assert "allow_test=" in inspect.getsource(templates.validate)
    assert "activation_channel(" in src and "check_existing(" in src
    assert '"channel"' in inspect.getsource(templates.forge_qualification)
    sql = (
        Path(__file__).resolve().parents[2] / "migrations/071_rlgym_template_channel.sql"
    ).read_text()
    assert "ADD COLUMN channel text" in sql


def test_the_export_gate():
    assert projects.test_channel_export_problem({"channel": "test"}, {"test_only": True}) is None
    assert "test_only" in projects.test_channel_export_problem({"channel": "test"}, {})
    assert projects.test_channel_export_problem({"channel": None}, {}) is None
    assert "test_channel_export_problem(" in inspect.getsource(projects.receive_export)


def test_never_leaderboard_and_labelled():
    resolved = {
        "evaluator_versions": [{"x": 1}],
        "env_row": {"state": "qualified"},
        "activation": {"channel": "test"},
    }
    out = runs.leaderboard_eligibility(resolved, [{"system_id": "m", "live": True}])
    assert out["eligible"] is False and any(
        "template" in r and "test channel" in r for r in out["reasons"]
    )
    assert 'act.get("channel")' in inspect.getsource(runs._manifest)


def test_validate_reads_the_documents_channel_like_activation():
    src = inspect.getsource(templates.validate)
    assert "allow_test is None" in src and "activation_channel(doc)" in src
