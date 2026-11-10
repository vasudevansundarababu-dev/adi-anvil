"""ATIF software serialization against installed pinned Harbor, no native trial."""

import pytest

from anvil.benchmark_atif import project, validate


def conversation():
    return {
        "provider": "openai",
        "model_id": "fictional-software-only",
        "turns": [
            {
                "text": "",
                "calls": [{"call_id": "call-1", "name": "square", "arguments": {"n": 2}}],
                "observations": [{"call_id": "call-1", "value": 4, "error": None}],
            },
            {"text": "Offline software conformance complete", "calls": [], "observations": []},
        ],
    }


def test_redacted_projection_validates_in_actual_harbor_025(tmp_path):
    value = project(conversation(), "fictional-serialization-only")
    checked = validate(value, tmp_path)
    assert checked["schema_version"] == "ATIF-v1.8"
    assert len(checked["steps"]) == 2
    assert checked["steps"][0]["observation"]["results"][0]["source_call_id"] == "call-1"
    assert checked["steps"][0]["llm_call_count"] == 0
    assert all(
        "reasoning_content" not in step and "metrics" not in step for step in checked["steps"]
    )
    assert checked["agent"]["extra"]["measured_model_performance"] is False


def test_bad_call_reference_is_rejected_by_actual_harbor(tmp_path):
    value = project(conversation(), "fictional-serialization-only")
    value["steps"][0]["observation"]["results"][0]["source_call_id"] = "not-a-real-call"
    with pytest.raises(ValueError, match="Harbor ATIF validation failed"):
        validate(value, tmp_path)
