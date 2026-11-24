"""D-036 (E-007 §7.1): episodes are scored with the task's published S7: 5/2/0 anchors, weights, 22.5 of 25 to pass,
and a fail on a critical criterion fails the task. The four rule texts are the 23 Nov v8 tasks' own wording."""

import inspect

import pytest

from anvil.rlgym.results import report
from anvil.rlgym.runs import service as runs
from anvil.rlgym.scoring import s7
from anvil.rlgym.scoring import service as scoring

RULES = [
    "Score the five template criteria using recorded run evidence. Each criterian earns 5 points for complete, correct "
    "work supported by evidence , 2 for substantially correct but incomplete work , or 0 for incorrect or omitted work. "
    "The maximum is 25 points and pass threshold is 22.5. Apply the template's existing critical-failure override.",
    "Score each criterion once for the custodial application. Award 5 for complete and supported by cited evidence, 2 "
    "for substantially correct but incomplete, and 0 for wrong or omitted. Maximum 25 points. The pass threshold is "
    "22.5 points, subject to the whole-task failure override.",
    "Score each of the five criteria once across both adult applicants. Award 5 Point for pass , 2 for partial and 0 "
    "for fail. The max is 25 points. The task passes with at least 22.5 point and no whole task failure.",
]
CRITERIA = [
    {"id": "identification_verification", "weight": 5, "critical": True},
    {"id": "screening", "weight": 5, "critical": True},
    {"id": "decision", "weight": 5, "critical": True},
    {"id": "next_action", "weight": 5, "critical": False},
    {"id": "evidence", "weight": 5, "critical": False},
]
ALL = [c["id"] for c in CRITERIA]


@pytest.mark.parametrize("rule", RULES)
def test_the_published_rules_read_as_5_2_0_and_22_5_of_25(rule):
    prof, why = s7.profile({"criteria": CRITERIA, "scoringRule": rule})
    assert why is None
    assert prof["anchors"] == {"pass": 5, "partial": 2, "fail": 0}
    assert (prof["max_points"], prof["threshold_points"]) == (25, 22.5)
    assert prof["critical"] == ["decision", "identification_verification", "screening"]
    assert (
        len(prof["rule_sha256"]) == 64 and "scoringRule" not in prof
    )  # the private text is not frozen


def _prof():
    return s7.profile({"criteria": CRITERIA, "scoringRule": RULES[1]})[0]


def test_only_25_of_25_passes_and_a_partial_scores_2_of_5():
    p = _prof()
    assert s7.outcome(p, dict.fromkeys(ALL, "pass"), p["weights"])["passed"]
    one_partial = {**dict.fromkeys(ALL, "pass"), "next_action": "partial"}
    out = s7.outcome(p, one_partial, p["weights"])
    assert (out["points"], out["passed"]) == (
        22.0,
        False,
    )  # 24/25 passed under the old scale; 22/25 doesn't here
    assert s7.fraction(p, "partial") == pytest.approx(0.4)


def test_a_critical_fail_fails_the_task_and_a_blocked_criterion_earns_nothing():
    p = _prof()
    out = s7.outcome(p, {**dict.fromkeys(ALL, "pass"), "screening": "fail"}, p["weights"])
    assert out["critical_failed"] == ["screening"] and not out["passed"]
    blocked = s7.outcome(p, {**dict.fromkeys(ALL, "pass"), "evidence": "blocked"}, p["weights"])
    assert (blocked["points"], blocked["passed"]) == (20.0, False)
    # A criterion taken out by a clause (not passed in) lowers the threshold in proportion: 4 of 4 pass.
    four = s7.outcome(p, {k: "pass" for k in ALL if k != "evidence"}, p["weights"])
    assert (four["max_points"], four["threshold_points"], four["passed"]) == (20.0, 18.0, True)


@pytest.mark.parametrize(
    ("section", "reason"),
    [
        (None, "no S7"),
        ({"criteria": CRITERIA}, "no scoring rule"),
        (
            {"criteria": CRITERIA, "scoringRule": "Score fairly."},
            "expected pass/partial/fail points",
        ),
        (
            {
                "criteria": CRITERIA,
                "scoringRule": "5 for pass, 2 for partial, 0 for fail. Threshold 22.5.",
            },
            "no maximum",
        ),
        (
            {
                "criteria": [*CRITERIA[:4], {"id": "evidence", "weight": 10}],
                "scoringRule": RULES[1],
            },
            "weight differs",
        ),
    ],
)
def test_an_unreadable_s7_is_refused_never_guessed(section, reason):
    prof, why = s7.profile(section)
    assert prof is None and reason in why


def test_admission_scoring_and_report_use_the_frozen_profile():
    check = inspect.getsource(runs.admission_check)
    assert "s7.profile(s7_section)" in check and '"scoring_rule"' in check
    assert '**({"scoring": t["scoring"]} if t.get("scoring") else {})' in inspect.getsource(
        runs._manifest
    )
    src = inspect.getsource(scoring.score_case)
    assert "s7.fraction(prof, verdict)" in src and "s7.outcome(prof" in src
    m = {"tasks": [{"scoring": _prof()}], "template": {"pass_mark": 90}}
    assert report.scoring_note(m).startswith(
        "S7 as published: 5/2/0 points for pass/partial/fail, pass at 22.5 of 25"
    )
    assert report.scoring_note({"tasks": [{}], "template": {"pass_mark": 90.0}}).startswith(
        "RL Gym scale"
    )


def test_a_task_whose_s7_is_not_in_points_keeps_the_rl_gym_scale_and_says_so():
    # v6's S7 allocates 100 points across dimensions (no 5/2/0 anchors): not readable as S7 points.
    v6 = "Total score is calculated across a 100-point denominator allocated across key KYC evaluation dimensions"
    prof, why = s7.profile({"criteria": CRITERIA, "scoringRule": v6})
    assert prof is None and why
    src = inspect.getsource(runs.admission_check)
    assert 't["scoring_unreadable"] = why' in src  # labelled per task, the run is not refused
    m = {"tasks": [{"scoring_unreadable": why}], "template": {"pass_mark": 90.0}}
    assert report.scoring_note(m) == (
        "RL Gym scale: pass 1, fail 0 per criterion; pass mark 90% (S7 couldn't be read as points for 1 task(s))"
    )
