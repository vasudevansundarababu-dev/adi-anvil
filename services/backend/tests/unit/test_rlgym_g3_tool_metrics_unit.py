"""G3 (part; E-011 §2 tool calling): automatic tool-calling metrics from an episode's trajectory, its start records and
the case reference. Read-only: a report drill-down that works on past runs and never changes a stored report, score
or pass."""

import inspect

from anvil.rlgym.results import report
from anvil.rlgym.results import tool_metrics as tm

CASE = "kyc-adult-joint-012"
START = {
    "applications": [{"application_id": CASE, "submitted_at": "2026-10-15T14:00:00Z"}],
    "parties": [
        {"party_id": "p1", "application_id": CASE, "role": "primary", "full_name": "Ann Lee"},
        {"party_id": "p2", "application_id": CASE, "role": "joint", "full_name": "Bo Lee"},
    ],
    "documents": [
        {
            "document_id": "d1",
            "party_id": "p1",
            "kind": "government_id",
            "content": {"name_on_document": "Ann Lee", "expires_on": "2030-01-01"},
        },
        {
            "document_id": "d2",
            "party_id": "p2",
            "kind": "government_id",
            "content": {"name_on_document": "Bo Smith", "expires_on": "2030-01-01"},
        },
        {"document_id": "d3", "party_id": "p1", "kind": "proof_of_address", "content": {}},
        {"document_id": "d4", "party_id": "p2", "kind": "proof_of_address", "content": {}},
    ],
}
REQ = {"request_type": "id_document", "recommendation": "request_information", "referral": "none"}
CLEAN = {"request_type": "none", "recommendation": "ready_for_approval", "referral": "none"}


def ev(tool, ok=True, blocked=False, **args):
    return {"tool": tool, "args": args, "ok": ok, "blocked": blocked}


def good():
    return [
        ev("application.read", application_id=CASE),
        ev("identity.check", party_id="p1"),
        ev("identity.check", party_id="p2"),
        ev("screening.check", party_id="p1"),
        ev("screening.check", party_id="p2"),
        ev("information.request", party_id="p2", type="id_document"),
        ev("recommend", decision="request_information"),
    ]


def test_a_clean_trajectory_makes_every_required_call_and_no_wrong_one():
    m = tm.episode_metrics(good(), START, CASE, REQ)
    assert m["calls"] == 7 and m["valid"] == 7
    assert (
        m["required"] == 6 and m["required_made"] == 6
    )  # 2 identity + 2 screening + 1 request + recommend
    assert m["wrong"] == [] and m["polls"] == 0 and m["loop"] is False
    assert m["decision_bearing"] == 2
    assert m["missed"] == []


def test_missed_checks_and_checks_after_the_recommendation_do_not_count():
    events = good()
    events.remove(ev("screening.check", party_id="p2"))
    events.append(ev("screening.check", party_id="p2"))  # after recommend
    m = tm.episode_metrics(events, START, CASE, REQ)
    assert m["required_made"] == 5
    assert "screening.check for p2 before recommend" in m["missed"]


def test_wrong_calls_wrong_party_unneeded_referral_and_a_second_recommendation():
    events = good() + [
        ev("information.request", party_id="p1", type="id_document"),
        ev("specialist.refer", specialty="sanctions"),
        ev("recommend", decision="request_information"),
    ]
    m = tm.episode_metrics(events, START, CASE, REQ)
    kinds = sorted(w["kind"] for w in m["wrong"])
    assert kinds == ["request_to_party_with_item", "second_recommendation", "unneeded_referral"]


def test_a_request_on_a_clean_case_is_wrong_and_the_request_is_not_required():
    events = [e for e in good() if e["tool"] != "information.request"]
    events.insert(5, ev("information.request", party_id="p1", type="proof_of_address"))
    m = tm.episode_metrics(events, START, CASE, CLEAN)
    assert m["required"] == 5
    assert [w["kind"] for w in m["wrong"]] == ["unneeded_request"]


def test_invalid_calls_polls_and_loops():
    events = good()[:1] + [
        ev("identity.check", ok=False, party_id="zz"),
        ev("search", blocked=True),
    ]
    events += [ev("operation.read", id="op-1")] * 5
    m = tm.episode_metrics(events, START, CASE, REQ)
    assert m["calls"] == 8 and m["valid"] == 6
    assert m["polls"] == 5
    assert m["loop"] is True  # the same call 4+ times in a row


def test_the_party_is_not_guessed_when_the_records_show_none():
    start = {
        **START,
        "documents": [d for d in START["documents"] if d["document_id"] != "d2"]
        + [
            {
                "document_id": "d2",
                "party_id": "p2",
                "kind": "government_id",
                "content": {"name_on_document": "Bo Lee", "expires_on": "2030-01-01"},
            }
        ],
    }
    events = good()
    events[5] = ev("information.request", party_id="p1", type="id_document")
    m = tm.episode_metrics(events, start, CASE, REQ)
    assert m["required_made"] == m["required"]
    assert m["wrong"] == [] and m["party_determinable"] is False


def test_summary_per_model():
    rows = [
        {"system_id": "a", **tm.episode_metrics(good(), START, CASE, REQ)},
        {
            "system_id": "a",
            **tm.episode_metrics(
                good() + [ev("specialist.refer", specialty="x")], START, CASE, REQ
            ),
        },
    ]
    s = tm.summarize(rows)["a"]
    assert s["episodes"] == 2 and s["calls"] == 15
    assert s["valid_rate"] == 1.0
    assert s["required_made_rate"] == 1.0
    assert s["wrong_calls"] == 1 and s["episodes_with_wrong_call"] == 1
    assert s["decision_bearing_share"] == round(5 / 15, 4)


def test_it_is_a_read_only_drill_down_never_part_of_the_stored_report():
    assert "tool_calling" in inspect.getsource(report.drill)
    assert "tool_calling" not in inspect.getsource(report.build)
    src = inspect.getsource(tm)
    for word in ("INSERT", "UPDATE", "DELETE"):
        assert word not in src
