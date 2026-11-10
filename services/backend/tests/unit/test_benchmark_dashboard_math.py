"""Mathematical/presentation contracts; not execution observations."""

import io
from decimal import Decimal

import pytest
from pypdf import PdfReader

from anvil.benchmark_dashboard import mean_score, selected_score
from anvil.benchmark_dashboard_api import render_pdf
from anvil.benchmark_rankings import paired_rankings


def pair(left, right, repeats=1):
    return [
        {"match_key": str(i), "model_key": model, "percent": value}
        for i in range(repeats)
        for model, value in (("A", left), ("B", right))
    ]


def test_observed_percentage_and_bt_are_distinct_estimands():
    observations = pair(90, 80, 3) + [
        {"match_key": "reverse", "model_key": "A", "percent": 70},
        {"match_key": "reverse", "model_key": "B", "percent": 80},
    ]
    value = paired_rankings(observations)
    assert value["observed_win_rate"]["rows"][0]["percent"] == "75.0000"
    bt = value["bradley_terry"]
    assert bt["status"] == "available"
    assert Decimal(bt["rows"][0]["relative_strength"]) == Decimal(".75")
    assert bt["rows"][0]["rank"] == 1 and bt["rows"][1]["rank"] == 2
    assert "percent" not in bt["rows"][0]


def test_ties_are_fractional_wins_not_fake_decisive_matches():
    result = paired_rankings(pair(0, 0))
    assert result["observed_win_rate"]["pair_count"] == 1
    assert all(
        x["ties"] == 1 and x["wins"] == 0 and x["percent"] == "50.0000"
        for x in result["observed_win_rate"]["rows"]
    )
    assert all(
        x["rank"] == 1 and x["relative_strength"] == "0.5000000000"
        for x in result["bradley_terry"]["rows"]
    )


def test_perfect_separation_has_no_invented_finite_bt_score():
    result = paired_rankings(pair(100, 0, 5))
    assert result["observed_win_rate"]["status"] == "available"
    assert result["bradley_terry"]["status"] == "not_estimable"
    assert result["bradley_terry"]["rows"] == []


def test_disconnected_cohorts_never_get_a_shared_rank():
    rows = pair(50, 50) + [
        {"match_key": "other", "model_key": m, "percent": 50} for m in ("C", "D")
    ]
    assert paired_rankings(rows)["bradley_terry"]["status"] == "not_estimable"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 101])
def test_invalid_numeric_measurements_are_rejected(bad):
    with pytest.raises(ValueError):
        paired_rankings(pair(bad, 50))


def test_duplicate_model_in_matched_cell_is_not_best_attempt_selection():
    with pytest.raises(ValueError):
        paired_rankings(pair(50, 50) + [{"match_key": "0", "model_key": "A", "percent": 100}])
    assert paired_rankings([])["observed_win_rate"]["rows"] == []


@pytest.fixture
def model():
    included = [
        {
            "task_revision_id": task,
            "repetition": rep,
            "earned_points": str(maximum),
            "possible_points": str(maximum),
        }
        for rep in range(2)
        for task, maximum in (("a", 24), ("b", 6), ("c", 51))
    ]
    return {
        "primary": {"earned_points": "81", "possible_points": "81", "percent": "100.0000"},
        "diagnostic": {
            "included": included,
            "complete_repetition_mean": {
                "earned_points": "81",
                "possible_points": "81",
                "percent": "100.0000",
            },
        },
    }


def test_task_slice_does_not_relabel_81_as_six(model):
    assert selected_score(model, "b", primary=True) == {
        "earned_points": "6",
        "possible_points": "6",
        "percent": "100.0000",
    }
    assert selected_score(model, "all", primary=True)["possible_points"] == "81"
    model["primary"] = None
    assert selected_score(model, "b", primary=True) is None
    assert selected_score(model, "b", primary=False)["earned_points"] == "6"


def test_period_slice_never_keeps_excluded_full_suite_primary(model):
    one_rep = {
        (x["task_revision_id"], x["repetition"])
        for x in model["diagnostic"]["included"]
        if x["repetition"] == 0
    }
    assert selected_score(model, "all", primary=True, allowed=one_rep) is None
    assert selected_score(model, "all", primary=False, allowed=one_rep)["possible_points"] == "81"
    assert selected_score(model, "all", primary=False, allowed={("a", 0)}) is None


def test_aggregate_never_mixes_task_denominators():
    assert mean_score([]) is None
    assert (
        mean_score(
            [
                {"earned_points": "6", "possible_points": "6"},
                {"earned_points": "24", "possible_points": "24"},
            ]
        )
        is None
    )


def empty_dashboard_fixture():
    return {
        "context": {
            "model": [],
            "task": "all",
            "period": "all",
            "environment": "all",
            "run_id": None,
            "score_revision_id": None,
            "trace_id": None,
            "cluster": None,
        },
        "origin_notice": "Fictional software controls; not live model performance.",
        "snapshot_sha256": "a" * 64,
        "overview": {
            "models": [],
            "total_traces": 0,
            "model_trace_count": 0,
            "control_trace_count": 0,
            "ranked_models": 0,
            "ranking": paired_rankings([]),
        },
        "failures": {
            "eligible_traces": 0,
            "failed_traces": 0,
            "infrastructure_events": 0,
            "error_rate_percent": None,
        },
        "traces": [],
        "limitations": ["Judge not run; no invented primary score."],
    }


@pytest.mark.parametrize("template", ["executive", "technical"])
def test_actual_pdf_templates_keep_fictional_unavailable_and_snapshot(template):
    raw = render_pdf(empty_dashboard_fixture(), template)
    assert raw.startswith(b"%PDF-")
    text = "\n".join(x.extract_text() for x in PdfReader(io.BytesIO(raw)).pages)
    assert "a" * 64 in text.replace("\n", "")
    assert "not live model performance" in text
    assert "Unavailable" in text and "Raw prompts: excluded" in text


def test_pdf_treats_untrusted_labels_as_text_not_markup_or_file_reads():
    data = empty_dashboard_fixture()
    data["overview"]["models"] = [
        {
            "model_id": "<img src='/etc/passwd'/>",
            "suite_key": "fictional",
            "primary": None,
            "diagnostic": None,
        }
    ]
    raw = render_pdf(data, "executive")
    assert raw.startswith(b"%PDF-")
    text = "\n".join(x.extract_text() for x in PdfReader(io.BytesIO(raw)).pages)
    assert "/etc/passwd" in text and "root:x:" not in text


def test_bradley_terry_fit_is_bounded_without_fabricating_a_rank():
    observations = [
        {"match_key": "shared", "model_key": str(i), "percent": "50"} for i in range(51)
    ]
    ranking = paired_rankings(observations)
    assert ranking["observed_win_rate"]["status"] == "available"
    assert ranking["bradley_terry"]["status"] == "cohort_too_broad"
    assert ranking["bradley_terry"]["rows"] == []
