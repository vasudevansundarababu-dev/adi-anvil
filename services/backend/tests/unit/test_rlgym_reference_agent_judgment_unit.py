"""The reference agent on KYC Judgment v1 must earn full marks from the graders that judge models:
- on a rule-change case whose bulletin it never saw, it decides from reference_if_not_fired (as the grader does);
- it screens every party (tool_calls requires screening.check per party);
- its audit trail marks every mandatory SOP step done, in order, with the reference's missing facts (process_adherence,
  missing_facts); its rationale names the recommendation and cites a rule (rationale)."""

from anvil.rlgym.scoring import judgment
from anvil.rlgym.verification import reference

TOOLS = [
    "application.read",
    "parties.list",
    "notices.read",
    "identity.check",
    "screening.check",
    "information.request",
    "specialist.refer",
    "recommend",
]
ACTOR = {
    "sections": {
        "S3": {"tools": TOOLS},
        "S5": {
            "steps": [
                {"tool": "application.read"},
                {"tool": "parties.list"},
                {"tool": "identity.check"},
                {"tool": "recommend"},
            ]
        },
    }
}
AFTER = {
    "status": "complete",
    "gradable": True,
    "conditions_approved": True,
    "recommendation": "ready_for_approval",
    "officer_verification": False,
    "parties": [{"party_id": "p1", "outcome": "clear", "requests": []}],
    "rules_applied": [{"rule_id": "R-A", "version": 2, "governs": None}],
    "mandatory_steps": ["1", "2"],
    "facts_missing": [],
}
BEFORE = {
    **AFTER,
    "recommendation": "request_information",
    "parties": [{"party_id": "p1", "outcome": "needs_info", "requests": ["tin"]}],
    "rules_applied": [{"rule_id": "R-A", "version": 1, "governs": None}],
    "mandatory_steps": ["1", "3"],
    "facts_missing": [{"party_id": "p1", "fact": "tin"}],
}
REF = {**AFTER, "reference_if_not_fired": BEFORE}


def drive(ref, notices):
    obs = {
        "application.read": {"ok": True, "output": {"records": [{"revision": 1}]}},
        "parties.list": {"ok": True, "output": {"records": [{"party_id": "p1"}]}},
        "notices.read": {"ok": True, "output": {"records": notices}},
    }
    gen = reference.agent(ACTOR, ref, "app-1", [], operations=[])
    events, transcript, action = [], [], next(gen)
    while "final" not in action:
        o = obs.get(action["tool"], {"ok": True, "state": "done", "output": {"records": []}})
        events.append({"tool": action["tool"], "args": action.get("args") or {}, "ok": True})
        transcript.append({"tool": action["tool"], "observation": {**o, "sequence": len(events)}})
        action = gen.send(o)
    return events, transcript, action["final"]


def grade(ref, fired, events, transcript, final):
    x = {
        "reference": ref,
        "final": final,
        "tool_events": events,
        "transcript": transcript,
        "fired": fired,
    }
    return {
        c: judgment.evaluate(c, x)["verdict"]
        for c in ("tool_calls", "process_adherence", "rationale", "missing_facts", "decision")
    }


def test_a_bulletin_it_never_saw_means_the_starting_rules():
    events, transcript, final = drive(REF, [])
    assert final["recommendation"] == "request_information"
    assert ("information.request", "p1", "tin") in {
        (e["tool"], e["args"].get("party_id"), e["args"].get("type")) for e in events
    }
    rec = next(e for e in events if e["tool"] == "recommend")
    assert rec["args"]["decision"] == "request_information"
    assert set(grade(REF, [], events, transcript, final).values()) == {"pass"}


def test_a_bulletin_it_read_means_the_changed_rules():
    events, transcript, final = drive(REF, [{"notice_id": "n1"}])
    assert final["recommendation"] == "ready_for_approval"
    assert not any(e["tool"] == "information.request" for e in events)
    fired = [{"rule_id": "R-A", "to_version": 2, "published_at_sequence": 0}]
    assert set(grade(REF, fired, events, transcript, final).values()) == {"pass"}


def test_every_party_is_screened_before_the_recommendation():
    events, _, _ = drive(AFTER, [])
    tools = [e["tool"] for e in events]
    assert ("screening.check", "p1") in {(e["tool"], e["args"].get("party_id")) for e in events}
    assert tools.index("screening.check") < tools.index("recommend")


def test_the_audit_trail_and_rationale():
    _, _, final = drive(REF, [])
    trail = final["audit_trail"]
    assert [e["sop_step"] for e in trail] == ["1", "3"] and {e["status"] for e in trail} == {"done"}
    assert {"party_id": "p1", "fact": "tin"} in [m for e in trail for m in e["facts_missing"]]
    assert "request_information" in final["rationale"] and "R-A" in final["rationale"]


def test_a_not_eligible_reference_is_recorded_as_not_eligible():
    r = {
        **AFTER,
        "recommendation": "not_eligible",
        "parties": [{"party_id": "p1", "outcome": "not_eligible", "requests": []}],
    }
    events, transcript, final = drive(r, [])
    assert final["recommendation"] == "not_eligible"
    assert next(e for e in events if e["tool"] == "recommend")["args"]["decision"] == "not_eligible"
    assert "not_eligible" in final["rationale"]
    assert judgment.evaluate("decision", {"reference": r, "final": final})["verdict"] == "pass"


def test_the_recommend_call_carries_the_offered_policy_bundle():
    """test@3 fixes policy_bundle to kyc-judgment.library@1; the reference agent reads it from the offered schema."""
    ops = [
        {
            "operation_id": "recommend",
            "input_schema": {"properties": {"policy_bundle": {"const": "kyc-judgment.library@1"}}},
        }
    ]
    gen = reference.agent(ACTOR, AFTER, "app-1", [], operations=ops)
    action, obs = (
        next(gen),
        {"ok": True, "output": {"records": [{"party_id": "p1", "revision": 1}]}},
    )
    while "final" not in action:
        if action["tool"] == "recommend":
            assert action["args"]["policy_bundle"] == "kyc-judgment.library@1"
        action = gen.send(obs)
