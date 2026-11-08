"""Original fictional arithmetic, never a benchmark/model performance result."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from anvil.benchmark_protocol import Protocol
from anvil.benchmark_scores import criterion_totals, exact, percent, scorecard

HASH = "a" * 64


def test_exact_typed_absence_is_zero_without_invented_file_hash():
    observation = {
        "criterion_id": "required",
        "earned_points": "0",
        "possible_points": "1",
        "absence_event_id": str(uuid4()),
        "evidence_sha256": None,
    }
    assert criterion_totals([observation], {"required": "1"}) == (0, 1)
    with pytest.raises(ValueError):
        criterion_totals([{**observation, "earned_points": "1"}], {"required": "1"})
    with pytest.raises(ValueError):
        criterion_totals([{**observation, "evidence_sha256": HASH}], {"required": "1"})


def protocol():
    return Protocol.model_validate(
        {
            "benchmark_revision_id": str(uuid4()),
            "benchmark_subject_sha256": HASH,
            "tasks": [
                {
                    "task_revision_id": str(uuid4()),
                    "source_id": str(uuid4()),
                    "package_id": str(uuid4()),
                    "qualification_id": str(uuid4()),
                    "package_sha256": HASH,
                    "environment_digest": "sha256:" + HASH,
                    "tool_schema_sha256": HASH,
                    "evaluator_binding_id": str(uuid4()),
                    "possible_points": n,
                    "criterion_count": n,
                }
                for n in (24, 6, 51)
            ],
            "slots": [
                {
                    "connection_id": str(uuid4()),
                    "binding": {
                        "provider": p,
                        "model_id": "fictional-conformance",
                        "destination": d,
                    },
                    "configuration_sha256": HASH,
                    "transport": "offline_contract",
                }
                for p, d in (
                    ("openai", "https://api.openai.com/v1/responses"),
                    ("anthropic", "https://api.anthropic.com/v1/messages"),
                    ("gemini", "https://generativelanguage.googleapis.com"),
                )
            ],
            "scoring_policy_sha256": HASH,
            "evaluator_policy_sha256": HASH,
            "runtime_sha256": HASH,
            "origin": "original_synthetic_fixture",
            "spend": {
                "currency": "USD",
                "candidate_cap_micro_usd": 0,
                "judge_cap_micro_usd": 0,
                "pricing_sha256": HASH,
                "authority_sha256": HASH,
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            },
        }
    )


def cells(p, *, zero=False):
    points = {str(t.task_revision_id): str(t.possible_points) for t in p.tasks}
    return [
        {
            **item,
            "attempt_no": 1,
            "validity": "valid",
            "state": "completed",
            "evidence_sha256": HASH,
            "duration_ms": 7,
            "expected_criteria": {
                "fictional-C" + str(i): "1" for i in range(int(points[item["task_revision_id"]]))
            },
            "criteria": [
                {
                    "criterion_id": "fictional-C" + str(i),
                    "earned_points": "0" if zero else "1",
                    "possible_points": "1",
                    "evidence_sha256": HASH,
                }
                for i in range(int(points[item["task_revision_id"]]))
            ],
        }
        for item in p.cells()
    ]


def test_exact_matrix_complete_and_two_repetition_denominator():
    p = protocol()
    assert len(p.cells()) == 18
    result, hash_ = scorecard(p, cells(p))
    assert len(hash_) == 64 and result["execution_complete"] and not result["complete"]
    assert all(m["primary"] is None for m in result["models"])
    assert all(
        m["diagnostic"]["complete_repetition_mean"]
        == {"earned_points": "81", "possible_points": "81", "percent": "100.00"}
        for m in result["models"]
    )
    assert result["models"][0]["cost"]["combined_micro_usd"] is None


def test_only_explicit_frozen_hard_failure_zeroes_official_reward():
    p = protocol()
    rows = cells(p)
    rows[0].update(state="model_failed", hard_constraint_ids=["declared-safety"])
    result, _ = scorecard(p, rows)
    observed = next(
        item
        for item in result["models"][0]["diagnostic"]["included"]
        if item["task_revision_id"] == rows[0]["task_revision_id"]
        and item["repetition"] == rows[0]["repetition"]
    )
    assert observed["earned_points"] == "0"
    assert int(observed["raw_earned_points"]) > 0
    rows[0].update(hard_constraint_ids=[], validity="unresolved")
    result, _ = scorecard(p, rows)
    assert result["models"][0]["primary"] is None
    assert not result["models"][0]["score_complete"]


def test_operational_failure_and_missing_cell_make_primary_null():
    p = protocol()
    rows = cells(p)
    rows[0].update(validity="invalid", state="operational_failed")
    rows.pop()
    result, _ = scorecard(p, rows)
    assert result["models"][0]["primary"] is None
    assert result["models"][2]["primary"] is None
    assert result["models"][1]["diagnostic"]["complete_repetition_mean"] is not None
    assert not result["complete"]


def test_valid_zero_is_a_score_not_missing_or_invalid():
    p = protocol()
    result, _ = scorecard(p, cells(p, zero=True))
    assert result["execution_complete"] and not result["complete"]
    assert result["models"][0]["diagnostic"]["complete_repetition_mean"]["percent"] == "0.00"


def test_replacement_and_duplicate_never_win():
    p = protocol()
    rows = cells(p)
    with pytest.raises(ValueError, match="duplicate"):
        scorecard(p, rows + [rows[0]])
    rows[0]["attempt_no"] = 2
    with pytest.raises(ValueError, match="replacement"):
        scorecard(p, rows)


@pytest.mark.parametrize("value", [True, 1, "NaN", "Infinity", "-1", "1e2", "0.000000001"])
def test_non_exact_or_non_finite_points_are_rejected(value):
    with pytest.raises(ValueError):
        exact(value)


def test_missing_duplicate_or_changed_criterion_denominator_rejected():
    row = {
        "criterion_id": "a",
        "earned_points": "1",
        "possible_points": "2",
        "evidence_sha256": HASH,
    }
    for observed, expected in (
        ([], {"a": "2"}),
        ([row, row], {"a": "2"}),
        ([row], {"a": "3"}),
        ([row], {"a": "2", "b": "1"}),
    ):
        with pytest.raises(ValueError):
            criterion_totals(observed, expected)


def test_rounding_uses_exact_decimal_and_display_only():
    assert percent(exact("64"), exact("81")) == "79.01"


def test_offline_transport_cannot_carry_paid_spend_or_authentic_origin():
    p = protocol().model_dump(mode="json")
    p["spend"]["candidate_cap_micro_usd"] = 1
    with pytest.raises(ValueError, match="no paid"):
        Protocol.model_validate(p)


def test_expired_authority_blocks_readiness_without_mutation():
    p = protocol()
    assert p.authority_blockers(now=datetime.now(timezone.utc) + timedelta(days=1)) == [
        "protocol_authority_expired"
    ]
