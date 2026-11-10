from decimal import Decimal

import pytest
from fastapi import HTTPException

from anvil import benchmark_rehearsal as rehearsal
from anvil.db import digest


def test_real_public_execution_and_independent_evaluation():
    frozen = rehearsal.manifest()
    result = rehearsal.run(frozen)
    assert len(result["cells"]) == 18
    assert len({(c["profile_id"], c["task_id"], c["repetition"]) for c in result["cells"]}) == 18
    assert {t["id"]: t["possible_points"] for t in frozen["tasks"]} == {
        "FX-001": 24,
        "FX-002": 6,
        "FX-003": 51,
    }
    square = next(p for p in result["profiles"] if p["profile_id"] == "square-all-v1")
    assert Decimal(square["mean_points"]) == 81
    assert all(r["earned_points"] == "81" for r in square["repetitions"])
    assert result["official_primary"] is None and result["provider_calls"] == 0
    assert result["model_performance"] is False
    assert result["result_sha256"] == digest(
        {k: v for k, v in result.items() if k != "result_sha256"}
    )
    for cell in result["cells"]:
        assert cell["output_sha256"] == digest(cell["outputs"])
        assert cell["duration_ms"] >= 0
    assert any(c["failure_tags"] for c in result["cells"])
    assert result["ranking"]["observed_win_rate"]["pair_count"] == 18


def test_candidate_has_only_public_inputs_and_eval_detects_mutation():
    items = [{"id": "item-001", "n": 7}]
    output = rehearsal.candidate("square-all-v1", items)
    assert output["answers_json"] == {"item-001": 49}
    assert rehearsal.evaluate(items, output)[0]["earned_points"] == "1"
    output["answers_json"]["item-001"] = 7
    assert rehearsal.evaluate(items, output)[0]["earned_points"] == "0"
    with pytest.raises(ValueError):
        rehearsal.candidate("arbitrary-command", items)


def test_source_change_is_not_a_new_result(monkeypatch):
    frozen = rehearsal.manifest()
    original = rehearsal.candidate

    def changed(profile, items):
        monkeypatch.setattr(rehearsal, "manifest", lambda: frozen | {"repetitions": 99})
        return original(profile, items)

    monkeypatch.setattr(rehearsal, "candidate", changed)
    with pytest.raises(HTTPException, match="409"):
        rehearsal.run(frozen)


def test_feature_and_paid_flags_fail_closed(monkeypatch):
    monkeypatch.setenv("ANVIL_ENV", "local")
    monkeypatch.delenv("ANVIL_BENCHMARK_REHEARSAL_ENABLED", raising=False)
    with pytest.raises(HTTPException):
        rehearsal.enabled()
    monkeypatch.setenv("ANVIL_BENCHMARK_REHEARSAL_ENABLED", "true")
    monkeypatch.setenv("ANVIL_LOCAL_FIXTURE_ENABLED", "true")
    for flag in rehearsal.PAID_FLAGS:
        monkeypatch.setenv(flag, "false")
    rehearsal.enabled()
    for flag in rehearsal.PAID_FLAGS:
        monkeypatch.setenv(flag, "true")
        with pytest.raises(HTTPException):
            rehearsal.enabled()
        monkeypatch.setenv(flag, "false")
