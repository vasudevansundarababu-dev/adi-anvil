import pytest

from anvil.workspace import ModelProfile, metrics


def test_task_failure_is_not_execution_error_and_missing_cost_is_unknown():
    row = {"state": "succeeded", "candidate": "agent", "result": {"diagnostics": {"reward": 0}}}
    result = metrics(
        row, [{"status": "execution_unknown", "actual_micro_usd": None, "reserved_micro_usd": 900}]
    )
    assert result["score"] == 0
    assert result["task_failed"] == 1 and result["execution_errors"] == 0
    assert result["unknown"] == 1
    assert result["known_cost_micro_usd"] is None
    assert result["reserved_micro_usd"] == 900 and not result["cost_complete"]


@pytest.mark.parametrize("state", ["queued", "running", "failed", "cancelled", "execution_unknown"])
def test_unscored_state_never_becomes_zero_score(state):
    result = metrics({"state": state, "candidate": "reference", "result": None}, [])
    assert result["score"] is None and result["scored"] == 0
    assert result["passed"] == result["task_failed"] == 0


def test_partial_cost_keeps_known_amount_without_claiming_complete():
    calls = [
        {"status": "completed", "actual_micro_usd": 100, "reserved_micro_usd": 200},
        {"status": "execution_unknown", "actual_micro_usd": None, "reserved_micro_usd": 300},
    ]
    result = metrics({"state": "execution_unknown", "candidate": "agent"}, calls)
    assert result["known_cost_micro_usd"] == 100
    assert not result["cost_complete"] and result["reserved_micro_usd"] == 500


def test_model_profile_cannot_smuggle_secret_or_endpoint_fields():
    with pytest.raises(ValueError):
        ModelProfile(name="Baseline", provider="openai", model_id="example", api_key="secret")
    with pytest.raises(ValueError):
        ModelProfile(name="Baseline", provider="openai", model_id="https://evil.test?q=secret")
