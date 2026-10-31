import pytest

from anvil import workspace_models as workspace
from anvil import workspace_preparation as planning


def test_package_planning_snapshot_excludes_private_files_review_and_future_content():
    row = {
        "id": "package",
        "source_id": "source",
        "package_sha256": "hash",
        "manifest": {
            "binding": "staged-decision-v1",
            "revision_id": "text-revision",
            "files": {"anvil-agent/admission.json": "PRIVATE-GRADING"},
            "source_review": "PRIVATE-REVIEW",
            "future_observation": "PRIVATE-FUTURE",
        },
    }
    public = planning.package_snapshot(row)
    assert public["agent_admission_present"] is True
    assert public["manifest"]["revision_id"] == "text-revision"
    assert "PRIVATE" not in str(public) and "files" not in public["manifest"]


def test_preparation_has_no_budget_default_and_rejects_dispatch_parameters():
    fields = {
        "preset_id": "00000000-0000-4000-8000-000000000001",
        "package_id": "00000000-0000-4000-8000-000000000002",
        "model_profile_ids": ["00000000-0000-4000-8000-000000000003"],
        "max_output_tokens": 2048,
        "episode_timeout_seconds": 300,
    }
    assert planning.Preparation(**fields).aggregate_cap_micro_usd is None
    for changes in (
        {"aggregate_cap_micro_usd": 0},
        {"max_output_tokens": 4096},
        {"dispatch_enabled": True},
        {"aggregate_cap_micro_usd": True},
    ):
        with pytest.raises(ValueError):
            planning.Preparation(**{**fields, **changes})


def test_workspace_model_does_not_inherit_global_secret_presence(monkeypatch):
    def forbidden(*args):
        raise AssertionError("Global provider key must not be consulted for workspace profiles")

    monkeypatch.setattr(workspace, "secret_presence", forbidden)
    row = {
        "id": "profile",
        "provider_key": "openai",
        "model_id": "test-model",
        "status": "draft",
        "config_hash": "hash",
        "created_at": None,
        "config": {
            "workspace_profile_version": 1,
            "profile_name": "Local profile",
            "max_output_tokens": 2048,
        },
    }
    result = workspace.model_public(None, row)
    assert result["workspace_profile"] and not result["credential_present"]
    assert result["credential_state"] == "missing" and not result["launch_available"]
