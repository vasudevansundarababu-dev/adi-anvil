"""Studio ab1f684: every reference rests on placeholder rules (gradable=false, conditions_approved=false). Real projects
grade ONLY gradable references. For the end-to-end integration test only, a test-only project grades non-gradable
references as if the placeholders were approved: the run manifest records placeholder_graded: true and every report
header says "TEST — graded on placeholder rules, not valid as a result". awaiting_sme cases stay ungraded even then."""

import inspect

from anvil.rlgym.results import report, skills
from anvil.rlgym.runs import service as runs
from anvil.rlgym.scoring import judgment
from anvil.rlgym.scoring import service as scoring
from anvil.rlgym.verification import lookup, reference_run

PM = {
    "status": "awaiting_pm",
    "awaiting_pm": ["R-CIP placeholder"],
    "gradable": False,
    "conditions_approved": False,
}
SME = {"status": "awaiting_sme", "awaiting_sme": ["precedence"], "gradable": False}
COMPLETE_BUT_NOT_GRADABLE = {"status": "complete", "gradable": False, "conditions_approved": False}
REAL = {"status": "complete", "gradable": True, "conditions_approved": True}


def test_real_projects_grade_only_gradable_references():
    assert judgment.awaiting(PM)[0] == "awaiting_pm"
    assert judgment.awaiting(SME)[0] == "awaiting_sme"
    # Not gradable for any reason (the conditions aren't approved) is never graded in a real project.
    assert judgment.awaiting(COMPLETE_BUT_NOT_GRADABLE)[0] == "awaiting_pm"
    assert judgment.awaiting(REAL) is None
    assert judgment.awaiting({"status": "complete"}) is None  # before the flag existed: as before


def test_a_test_only_run_grades_placeholders_but_never_awaiting_sme():
    assert judgment.awaiting(PM, placeholder_ok=True) is None
    assert judgment.awaiting(COMPLETE_BUT_NOT_GRADABLE, placeholder_ok=True) is None
    assert judgment.awaiting(SME, placeholder_ok=True)[0] == "awaiting_sme"


def test_evaluate_follows_the_run_switch():
    ref = {
        **PM,
        "recommendation": "ready_for_approval",
        "parties": [],
        "officer_verification": False,
    }
    final = {
        "recommendation": "ready_for_approval",
        "assessments": [],
        "officer_verification": False,
    }
    base = {"reference": ref, "final": final, "transcript": []}
    assert judgment.evaluate("decision", base)["verdict"] == "not_applicable"
    assert judgment.evaluate("decision", {**base, "placeholder_ok": True})["verdict"] == "pass"


def test_only_test_only_projects_set_the_switch_and_it_is_frozen():
    assert runs.placeholder_graded({"test_only": True}) is True
    assert runs.placeholder_graded({"test_only": False}) is False
    assert runs.placeholder_graded({}) is False
    assert '"placeholder_graded"' in inspect.getsource(runs._manifest)
    assert 'manifest.get("placeholder_graded")' in inspect.getsource(scoring.judgment_results)


def test_reference_and_lookup_runs_follow_the_projects_flag():
    assert "placeholder_ok=" in inspect.getsource(reference_run.run)
    assert "placeholder_ok=" in inspect.getsource(lookup.run)


def test_every_report_header_says_so():
    assert report.PLACEHOLDER_NOTE == "TEST — graded on placeholder rules, not valid as a result"
    assert "PLACEHOLDER_NOTE" in inspect.getsource(report.header)
    assert "placeholder_ok" in inspect.getsource(skills.run_profile)


def test_known_case_qualification_grades_placeholders_but_not_awaiting_sme():
    from anvil.rlgym.catalog import judgment_configs

    ref = {
        **PM,
        "recommendation": "ready_for_approval",
        "parties": [],
        "officer_verification": False,
        "rules_applied": [{"rule_id": "R", "version": 1, "governs": None}],
    }
    case = {
        "evidence": {
            "final_output": {
                "recommendation": "ready_for_approval",
                "rules_applied": [{"rule_id": "R", "version": 1}],
                "assessments": [],
                "officer_verification": False,
            }
        },
        "reference": ref,
    }
    lines = judgment_configs.known_case_lines("rules_applied", case)
    assert lines["rules_applied.rules_applied"]["verdict"] == "pass"
    lines = judgment_configs.known_case_lines(
        "rules_applied", {**case, "reference": {**ref, **SME}}
    )
    assert lines["rules_applied.rules_applied"]["verdict"] == "not_applicable"
