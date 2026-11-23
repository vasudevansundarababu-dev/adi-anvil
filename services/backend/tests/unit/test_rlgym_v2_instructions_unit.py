"""D-007: the agent's instructions come from the task's actor payload (assignment, or ADI Forge's S1–S8 sections),
never from a generic fallback, and never from the private part. Synthetic payloads only."""

import json

import pytest

from anvil.rlgym.common import GymError
from anvil.rlgym.live.agent import live_agent
from anvil.rlgym.runs import instructions

SECTIONS = {
    "S1": {
        "title": "Joint KYC",
        "scope": "Joint account applications.",
        "trigger": "A new joint application",
        "deliverable": "A structured review with a recommendation.",
        "applicationType": "adult_joint",
        "businessContext": "Customer identification for each co-applicant.",
    },
    "S2": {"inputContract": "One application snapshot per episode."},
    "S3": {
        "tools": ["application.read", "recommend"],
        "environment": "golden_kyc_openenv",
        "failureBehaviour": "Do not invent missing data.",
    },
    "S4": {
        "statePolicies": [
            {
                "ruleId": "r-1",
                "locator": "project rule set v1",
                "ruleVersion": "rs1.d1",
                "contentSha256": "ab",
            }
        ]
    },
    "S5": {
        "steps": [
            {
                "tool": "finding.write",
                "action": "Check each party's identity.",
                "failureBehaviour": "Record the gap.",
            },
            {"tool": "specialist.refer", "action": "Screen every party."},
        ]
    },
    "S6": {"outputContract": "Executive summary, applicant breakdown, findings, next steps."},
    "S8": {"sourcesUsed": "31 CFR 1020.220"},
    "S9": {"extra": "kept, not dropped"},
}


def test_sections_render_every_part_in_a_fixed_order():
    out = instructions.build({"sections": SECTIONS})
    t = out["text"]
    assert out["source"] == "sections" and len(out["sha256"]) == 64
    order = [
        "## Task",
        "## Input",
        "## Tools and failure behaviour",
        "## Policy rules",
        "## Steps",
        "## Output contract",
        "## Sources",
        "## S9",
    ]
    assert [t.index(h) for h in order] == sorted(t.index(h) for h in order)
    for want in (
        "Title: Joint KYC",
        "Deliverable: A structured review with a recommendation.",
        "Input contract: One application snapshot per episode.",
        "If a tool fails: Do not invent missing data.",
        "Rule r-1 (project rule set v1, version rs1.d1",
        "1. Check each party's identity. (record with finding.write)",
        "   If this fails: Record the gap.",
        "2. Screen every party. (record with specialist.refer)",
        "Output contract: Executive summary, applicant breakdown, findings, next steps.",
        "extra: kept, not dropped",
    ):
        assert want in t, want
    assert "application.read" not in t  # the operation list comes from the environment, not from S3


def test_same_payload_same_text_and_hash_whatever_the_key_order():
    shuffled = {k: SECTIONS[k] for k in reversed(list(SECTIONS))}
    assert instructions.build({"sections": SECTIONS}) == instructions.build({"sections": shuffled})


def test_assignment_wins_when_present_so_existing_projects_do_not_change():
    out = instructions.build({"assignment": "  Review it.  ", "sections": SECTIONS})
    assert out["text"] == "Review it." and out["source"] == "assignment"


@pytest.mark.parametrize(
    "actor", [None, {}, {"assignment": "  "}, {"sections": {}}, {"title": "x", "tools": []}]
)
def test_no_instructions_is_an_error_never_a_fallback(actor):
    with pytest.raises(GymError) as e:
        instructions.build(actor)
    assert e.value.code == "TASK_NO_INSTRUCTIONS"
    assert instructions.problem(actor)


def test_only_the_actor_part_is_read():
    # The builder takes the actor payload alone; a private part handed alongside never reaches the text.
    actor = {"sections": SECTIONS}
    package = {
        "actor": actor,
        "private": {"reference": {"recommendation": "SECRET-REF"}, "rubric": "SECRET-RUBRIC"},
    }
    text = instructions.build(package["actor"])["text"]
    assert "SECRET" not in text
    import inspect

    from anvil.rlgym.runs import worker

    assert "instructions.build(actor)" in inspect.getsource(worker.execute)
    assert "private" not in json.dumps(actor)


def test_live_agent_refuses_empty_instructions_and_sends_the_built_text():
    with pytest.raises(GymError) as e:
        next(live_agent(lambda m: None, "", []))
    assert e.value.code == "TASK_NO_INSTRUCTIONS"

    sent = []

    class R:
        text = '{"final": {"decision": "x"}}'

    def call(messages):
        sent.append(messages)
        return R()

    text = instructions.build({"sections": SECTIONS})["text"]
    assert next(live_agent(call, text, [], application_id="kyc-1")) == {"final": {"decision": "x"}}
    user = sent[0][1]["content"]
    assert user.startswith(text) and "Application under review: kyc-1" in user
    assert "Review the application and return a decision with findings." not in user


def test_worker_builds_instructions_and_records_them():
    import inspect

    from anvil.rlgym.runs import worker

    src = inspect.getsource(worker.execute)
    assert "instructions.build(actor)" in src and '"instructions": instr' in src
    assert '.get("assignment"' not in src


def test_d016_follow_ups_render_after_the_step_and_before_its_failure_line():
    steps = {
        "steps": [
            {
                "action": "Screen both joint applicants.",
                "tool": "screening.check",
                "failureBehaviour": "Record the gap.",
                "followUps": [
                    {
                        "if": "either has an unresolved match",
                        "tools": ["finding.write", "specialist.refer"],
                    }
                ],
            },
            {
                "action": "List the documents.",
                "tool": "documents.list",
                "followUps": [{"tools": ["document.read"]}],
            },
            {"action": "Submit the recommendation.", "tool": "recommend", "priority": "last"},
        ]
    }
    t = instructions.build({"sections": {"S5": steps}})["text"]
    assert (
        "1. Screen both joint applicants. (record with screening.check)\n"
        "   If either has an unresolved match: finding.write then specialist.refer\n"
        "   If this fails: Record the gap.\n"
        "2. List the documents. (record with documents.list)\n"
        "   Then: document.read\n"
        "3. Submit the recommendation. (record with recommend)\n"
        "   priority: last"
    ) in t


def test_d016_steps_without_follow_ups_render_exactly_as_before():
    # The text (and so the hash) for steps without followUps is unchanged by D-016.
    s5 = {
        "steps": [
            {
                "action": "Check identity.",
                "tool": "identity.check",
                "failureBehaviour": "Record it.",
            }
        ]
    }
    t = instructions.build({"sections": {"S5": s5}})["text"]
    assert (
        t
        == "## Steps\n1. Check identity. (record with identity.check)\n   If this fails: Record it."
    )
