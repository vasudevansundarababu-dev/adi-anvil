"""Planning bounds only; never provider or Run authority."""

import pytest
from fastapi import HTTPException

from anvil.workspace_preparation import Preparation, turn_bound


@pytest.mark.parametrize("requested", [None, 108, 200])
def test_marketing_preserves_bounded_campaign_beyond_100_turns(requested):
    package = {
        "manifest": {"binding": "marketing-task2-five-role-v1", "stage_order": list(range(200))}
    }
    assert turn_bound(package, requested) == (200 if requested is None else requested)


@pytest.mark.parametrize(
    "binding,available,requested",
    [
        ("marketing-task2-five-role-v1", 200, 201),
        ("marketing-task2-five-role-v1", 1001, 1001),
        ("golden-kyc-openenv-tool-agent-v1", 200, 101),
        ("golden-kyc-openenv-tool-agent-v1", 20, 21),
    ],
)
def test_over_limit_selection_is_rejected_without_silent_truncation(binding, available, requested):
    with pytest.raises(HTTPException) as error:
        turn_bound(
            {"manifest": {"binding": binding, "stage_order": list(range(available))}}, requested
        )
    assert error.value.status_code == 422


def test_marketing_environment_and_global_ceiling_are_valid_preparation_fields():
    body = Preparation(
        preset_id="00000000-0000-4000-8000-000000000001",
        package_id="00000000-0000-4000-8000-000000000002",
        model_profile_ids=["00000000-0000-4000-8000-000000000003"],
        max_output_tokens=512,
        episode_timeout_seconds=600,
        max_agent_steps=1000,
        environment="marketing-task2-us-v1",
    )
    assert body.max_agent_steps == 1000
    assert body.aggregate_cap_micro_usd is None
