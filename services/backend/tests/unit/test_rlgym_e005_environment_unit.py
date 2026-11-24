"""E-005 §2: environment versions a suite can use without re-authoring; experiments mark a suite not
leaderboard-eligible; existing pinned suites are left as they are."""

import inspect

from anvil.rlgym.runs import service as runs
from anvil.rlgym.suites import environment
from anvil.rlgym.suites import service as suites


def test_task_tools_come_from_s3_and_s5_with_follow_ups():
    actor = {
        "tools": ["x.read"],
        "sections": {
            "S3": {"tools": ["application.read", "recommend"]},
            "S5": {
                "steps": [
                    {
                        "tool": "identity.check",
                        "followUps": [{"tools": ["finding.write", "specialist.refer"]}],
                    },
                    "free text step",
                ]
            },
        },
    }
    assert environment.task_tools(actor) == {
        "x.read",
        "application.read",
        "recommend",
        "identity.check",
        "finding.write",
        "specialist.refer",
    }
    assert environment.task_tools(None) == set()


def test_grader_reference_fields():
    blocks = {
        "next_action": [{"value": {"case_reference": "reference_answers.request_type"}}],
        "screening": [
            {"settings": {"inputs": {"screening_issue": "case_reference.screening_issue"}}}
        ],
    }
    assert environment.grader_reference_fields(blocks) == {"request_type", "screening_issue"}


def test_an_experiment_pins_with_a_reason_and_blocks_the_leaderboard():
    src = inspect.getsource(suites.patch)
    assert 'source != "experiment" or (kind == "pinned" and (b.get("reason") or "").strip())' in src
    ok = runs.leaderboard_eligibility(
        {
            "evaluator_versions": [{}],
            "env_row": {"state": "qualified"},
            "prompts": [],
            "experiment": True,
        },
        [{"system_id": "m", "live": {"approval_id": "la"}}],
    )
    assert not ok["eligible"] and any("experiment" in r for r in ok["reasons"])
    assert (
        'resolved["experiment"] = any(b["source"] == "experiment" for b in bindings)'
        in inspect.getsource(runs.admission_check)
    )
