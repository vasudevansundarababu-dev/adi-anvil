"""The audit trail is per Bank SOP step (sop_step), so the agent must see the SOP and its ids (incl. "8a").
Studio's bridge carries template.sop ({sop_id, version, steps: [{step, title, required_when, tools}]}); RL Gym keeps it
on the activation (filled from the same hash-verified document), freezes it in the run manifest and renders it under
"Bank SOP". process_adherence grades the trail's sop_step against reference.v2 mandatory_steps (SOP ids), never the
task's step numbers."""

import inspect
from pathlib import Path

from anvil.rlgym.catalog import templates
from anvil.rlgym.runs import instructions, worker
from anvil.rlgym.runs import service as runs
from anvil.rlgym.scoring import judgment
from anvil.rlgym.systems import mock_provider

SOP = {
    "sop_id": "kyc-retail-onboarding",
    "version": 1,
    "title": "KYC onboarding",
    "steps": [
        {
            "step": "1",
            "title": "Open the case",
            "required_when": "always",
            "tools": ["application.read", "parties.list"],
        },
        {
            "step": "8",
            "title": "Screen every party",
            "required_when": "always",
            "tools": ["screening.check"],
        },
        {
            "step": "8a",
            "title": "Escalate a possible match",
            "required_when": "a screening match",
            "tools": ["specialist.refer"],
        },
    ],
}
ACTOR = {"assignment": "Assess the application."}


def test_the_sop_is_rendered_with_its_ids():
    out = instructions.build(ACTOR, sop=SOP)["text"]
    assert "## Bank SOP" in out and "kyc-retail-onboarding" in out
    assert (
        "- 8a. Escalate a possible match (required: a screening match; tools: specialist.refer)"
        in out
    )
    assert "sop_step" in out  # told to use these ids in the audit trail


def test_without_a_sop_the_instructions_are_unchanged():
    assert instructions.build(ACTOR) == instructions.build(ACTOR, sop=None)
    assert "Bank SOP" not in instructions.build(ACTOR)["text"]


def test_the_activation_keeps_and_freezes_it():
    sql = (
        Path(__file__).resolve().parents[2] / "migrations/072_rlgym_template_sop.sql"
    ).read_text()
    assert "ADD COLUMN sop jsonb" in sql
    assert 'doc.get("sop")' in inspect.getsource(templates.activate)
    assert (
        templates.sop_fill(None, SOP) == SOP
    )  # a missing SOP is filled from the same verified document
    assert templates.sop_fill(SOP, {"steps": []}) is None  # never replaced
    assert templates.sop_fill(None, None) is None
    assert '"sop"' in inspect.getsource(runs._manifest)
    assert "sop=" in inspect.getsource(worker)


def test_process_adherence_grades_sop_ids():
    ref = {"status": "complete", "gradable": True, "mandatory_steps": ["1", "8", "8a"]}
    trail = [{"sop_step": s, "status": "done"} for s in ("1", "8", "8a")]
    assert (
        judgment.evaluate("process_adherence", {"final": {"audit_trail": trail}, "reference": ref})[
            "verdict"
        ]
        == "pass"
    )
    task_numbers = [{"sop_step": s, "status": "done"} for s in ("1", "2", "3")]
    assert (
        judgment.evaluate(
            "process_adherence", {"final": {"audit_trail": task_numbers}, "reference": ref}
        )["verdict"]
        == "fail"
    )


def test_the_mocks_number_their_trail_by_the_sop():
    text = instructions.build(ACTOR, sop=SOP)["text"]
    assert mock_provider.sop_steps(text) == {
        "application.read": "1",
        "parties.list": "1",
        "screening.check": "8",
        "specialist.refer": "8a",
    }
