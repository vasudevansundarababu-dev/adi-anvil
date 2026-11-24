"""E-004: grader drafts, draft re-scores that never become the run's reported pass, and promotion by a second person.
Synthetic blocks shaped like golden-kyc v8's decision criterion; no database."""

import inspect

import pytest

from anvil.rlgym.common import GymError
from anvil.rlgym.plugins import service as plugins
from anvil.rlgym.scoring import service as scoring
from anvil.rlgym.scoring import workbench

JUDGE = {
    "id": "decision.rationale_quality",
    "plugin": {"id": "promptfoo"},
    "share_percent": 20,
    "settings": {"judge": "gemini-3.8-flash", "rubric": "States the reason.", "threshold": 0.7},
}
STATE = {"id": "decision.recommendation", "kind": "state", "op": "equals"}
VCTX = {
    "blocks": {"decision": [STATE, JUDGE]},
    "slots": {},
    "expected_values_from": "case_reference",
}
EV = [({"criterion_id": "decision"}, {"config": {"runner": "verifier_blocks"}})]


def test_draft_overrides_change_only_the_named_block():
    out = scoring.apply_overrides(
        VCTX,
        EV,
        {
            "decision": {
                "block_overrides": {
                    JUDGE["id"]: {
                        "settings": {"threshold": 0.9, "judge": "mock-judge"},
                        "share_percent": 40,
                    }
                }
            }
        },
    )
    b = out["blocks"]["decision"][1]
    assert b["settings"] == {
        "judge": "mock-judge",
        "rubric": "States the reason.",
        "threshold": 0.9,
    }
    assert b["share_percent"] == 40 and out["blocks"]["decision"][0] == STATE
    assert (
        VCTX["blocks"]["decision"][1]["settings"]["threshold"] == 0.7
    )  # the template's blocks are not changed
    off = scoring.apply_overrides(VCTX, EV, {"decision": {"disabled_blocks": [JUDGE["id"]]}})
    assert [b["id"] for b in off["blocks"]["decision"]] == [STATE["id"]]


def test_a_promoted_version_carries_its_overrides_in_the_configuration():
    promoted = [
        (
            {"criterion_id": "decision"},
            {
                "config": {
                    "runner": "verifier_blocks",
                    "block_overrides": {JUDGE["id"]: {"settings": {"threshold": 0.8}}},
                }
            },
        )
    ]
    assert (
        scoring.apply_overrides(VCTX, promoted)["blocks"]["decision"][1]["settings"]["threshold"]
        == 0.8
    )
    assert scoring.apply_overrides(VCTX, EV) == VCTX  # nothing to apply: unchanged


def test_draft_passes_are_never_the_reported_pass():
    assert "reason<>'draft'" in inspect.getsource(scoring.latest_pass)
    src = inspect.getsource(workbench.rescore_with_drafts)
    assert '"draft",' in src and "scoring.create_pass(" in src and "rescored=true" not in src


@pytest.fixture
def project(monkeypatch):
    monkeypatch.setattr(workbench, "_template_blocks", lambda c, ws, p, cid: [STATE, JUDGE])
    monkeypatch.setattr(plugins, "judge_choices", lambda c, ws: ["mock-judge", "gemini-3.8-flash"])
    return {"template_id": "t", "template_version": 8}


@pytest.mark.parametrize(
    "settings",
    [
        {"block_overrides": {JUDGE["id"]: {"settings": {"judge": "gpt-unapproved"}}}},
        {"block_overrides": {JUDGE["id"]: {"settings": {"threshold": 1.5}}}},
        {"block_overrides": {JUDGE["id"]: {"settings": {"rubric": "  "}}}},
        {"block_overrides": {JUDGE["id"]: {"share_percent": 140}}},
        {"block_overrides": {JUDGE["id"]: {"settings": {"target": "x", "mode": "y"}}}},
        {"block_overrides": {STATE["id"]: {"settings": {"threshold": 0.5}}}},
        {},
    ],
)
def test_draft_validation(project, settings):
    with pytest.raises(GymError):
        workbench.validate(None, None, project, "decision", settings)


def test_valid_draft(project):
    workbench.validate(
        None,
        None,
        project,
        "decision",
        {
            "block_overrides": {
                JUDGE["id"]: {
                    "settings": {
                        "judge": "mock-judge",
                        "threshold": 0.85,
                        "rubric": "Names the missing document.",
                    },
                    "share_percent": 30,
                }
            }
        },
    )
    workbench.validate(None, None, project, "decision", {"disabled_blocks": [JUDGE["id"]]})


def test_promotion_needs_a_second_person():
    src = inspect.getsource(workbench.decide)
    assert 'str(ctx.actor.id) != p["proposed_by"]' in src and "APPROVERS" in src
    assert "evaluators.create_fix_version(" in src
