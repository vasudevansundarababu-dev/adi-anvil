"""G3 (E-011 §2-§3) skill tags and the skill profile; G5 the v8 vs KYC Judgment v1 comparison by skill.

- A criterion's skill: the template's tag (C4 `skill`), else the task's S7 `skill`, else E-011 §4's first-pass
  mapping for golden KYC v8 (labelled provisional).
- Reasoning and decisioning count only on discriminating cases (those the G4 lookup gets wrong); with fewer than 10
  such episodes per model the profile says "not measured", never a number. Tool calling and instruction following
  count on every case.
- The comparison joins two runs' profiles by model (same system and version)."""

import inspect

from anvil.rlgym.results import report, skills
from anvil.rlgym.scoring import s7

S7 = {
    "criteria": [
        {"id": "tool_calls", "weight": 5, "skill": "tool_calling"},
        {"id": "rules_applied", "weight": 5, "critical": True, "skill": "reasoning"},
    ],
    "scoringRule": "5 points for pass, 2 for partial, 0 for fail. Maximum 10. Pass threshold 8.",
}


def test_s7_profile_carries_skills_only_when_tagged():
    prof, why = s7.profile(S7)
    assert why is None and prof["skills"] == {
        "tool_calls": "tool_calling",
        "rules_applied": "reasoning",
    }
    plain = {
        **S7,
        "criteria": [{k: v for k, v in c.items() if k != "skill"} for c in S7["criteria"]],
    }
    assert "skills" not in s7.profile(plain)[0]


def test_skill_of_a_criterion():
    assert skills.skill_of("x", {"skill": "decisioning"}, {"x": "reasoning"}) == (
        "decisioning",
        "template",
    )
    assert skills.skill_of("x", {}, {"x": "reasoning"}) == ("reasoning", "task S7")
    assert skills.skill_of("screening", {}, {}) == ("tool_calling", "provisional (E-011 §4)")
    assert skills.skill_of("next_action", {}, {}) == ("decisioning", "provisional (E-011 §4)")
    assert skills.skill_of("unknown_criterion", {}, {}) == (None, None)


def rows(model, n, skill, value, prefix="c"):
    return [
        {
            "system_id": model,
            "case_id": f"{prefix}{i}",
            "criterion_id": f"crit-{skill}",
            "skill": skill,
            "fraction": value,
        }
        for i in range(n)
    ]


def test_reasoning_counts_only_on_discriminating_cases_and_needs_ten():
    data = rows("m", 12, "reasoning", 1.0) + rows("m", 12, "tool_calling", 0.5)
    disc = {f"c{i}" for i in range(4)}
    out = skills.profile(data, disc)["m"]
    assert out["tool_calling"] == {"value": 50.0, "n": 12, "measured": True}
    assert out["reasoning"]["measured"] is False and out["reasoning"]["n"] == 4
    assert "too few discriminating cases (4 of the 10 needed)" in out["reasoning"]["note"]
    disc = {f"c{i}" for i in range(10)}
    assert skills.profile(data, disc)["m"]["reasoning"] == {
        "value": 100.0,
        "n": 10,
        "measured": True,
    }


def test_without_a_lookup_run_reasoning_and_decisioning_are_not_measured():
    out = skills.profile(rows("m", 12, "decisioning", 1.0), None)["m"]["decisioning"]
    assert out["measured"] is False and "no lookup baseline" in out["note"]


def test_compare_joins_models_by_system_and_version():
    a = {"m@1": {"reasoning": {"value": 90.0, "n": 12, "measured": True}}, "x@1": {}}
    b = {"m@1": {"reasoning": {"value": 40.0, "n": 15, "measured": True}}, "y@2": {}}
    out = skills.compare(a, b)
    assert (
        out["models"] == ["m@1"]
        and out["only_in_first"] == ["x@1"]
        and out["only_in_second"] == ["y@2"]
    )
    cell = out["by_model"]["m@1"]["reasoning"]
    assert (
        cell["first"]["value"] == 90.0
        and cell["second"]["value"] == 40.0
        and cell["delta"] == -50.0
    )
    unmeasured = skills.compare(
        {"m@1": {"reasoning": {"value": None, "n": 2, "measured": False}}},
        {"m@1": {"reasoning": {"value": 40.0, "n": 15, "measured": True}}},
    )
    assert unmeasured["by_model"]["m@1"]["reasoning"]["delta"] is None


def test_wired_read_only():
    assert '"skills"' in inspect.getsource(report.drill)
    from anvil.rlgym.results import routes

    assert "skill-compare" in inspect.getsource(routes)
    for word in ("INSERT", "UPDATE ", "DELETE"):
        assert word not in inspect.getsource(skills)


# --- spec §16: skills by account type, N/A per criterion, comparison per account type ------------------------------


def typed(model, t, n, skill, value):
    return [
        {**r, "application_type": t, "case_id": f"{t}-{r['case_id']}"}
        for r in rows(model, n, skill, value)
    ]


def test_skills_by_account_type():
    data = typed("m", "custodial", 3, "tool_calling", 1.0) + typed(
        "m", "individual", 2, "tool_calling", 0.0
    )
    out = skills.profile_by_type(data, None)
    assert out["custodial"]["m"]["tool_calling"]["value"] == 100.0
    assert out["individual"]["m"]["tool_calling"] == {"value": 0.0, "n": 2, "measured": True}


def test_outcomes_per_criterion_show_not_applicable():
    receipts = [
        {"criterion_id": "risk_rating", "verdict": v}
        for v in ("pass", "not_applicable", "not_applicable", "fail")
    ]
    out = skills.criteria_outcomes(receipts)
    assert out["risk_rating"] == {
        "pass": 1,
        "partial": 0,
        "fail": 1,
        "not_applicable": 2,
        "blocked": 0,
        "applicable": 2,
    }


def test_compare_per_account_type():
    a = {"custodial": {"m@1": {"reasoning": {"value": 80.0, "n": 10, "measured": True}}}}
    b = {
        "custodial": {"m@1": {"reasoning": {"value": 50.0, "n": 12, "measured": True}}},
        "individual": {"m@1": {}},
    }
    out = skills.compare_by_type(a, b)
    assert list(out) == ["custodial"]
    assert out["custodial"]["by_model"]["m@1"]["reasoning"]["delta"] == -30.0
