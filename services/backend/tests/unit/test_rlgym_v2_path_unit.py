"""D-015: the episode path summary never names an unreached step as the failure point, lists each step once and
counts distinct steps (synthetic workflow, the shape of the run-0228 template)."""

import pytest

from anvil.rlgym.results.episodes import path_facts

WF = {
    "nodes": [
        {"id": n}
        for n in ("intake", "identify", "verify", "screen", "account", "state", "decide", "act")
    ]
}


def cr(cid, verdict, *nodes):
    return {"criterion_id": cid, "verdict": verdict, "nodes": list(nodes)}


def facts(criteria, path, state="scored", denied=None):
    timeline = [{"node": n, "status": "completed", "tool": f"{n}.op"} for n in path]
    if denied:
        timeline.append({"node": denied, "status": "denied", "tool": f"{denied}.op"})
    counts = {}
    for t in timeline:
        counts[t["node"]] = counts.get(t["node"], 0) + 1
    order = []
    for t in timeline:
        if not order or order[-1] != t["node"]:
            order.append(t["node"])
    return path_facts(WF, criteria, timeline, counts, state, order)


def no_step_twice(f):
    reached_part = f["summary"].split("; not reached:")[0]
    for n in f["summary"].split("; not reached: ")[-1].split(" (")[0].split(", "):
        if "not reached" in f["summary"]:
            assert f"failed at {n} " not in reached_part


def test_run_0228_shape_failing_criteria_on_unreached_steps_are_missing_not_failed_at():
    f = facts(
        [
            cr("account_agreements", "fail", "account"),
            cr("identification_verification", "fail", "identify"),
            cr("screening", "fail", "screen"),
            cr("state_rule_selection", "fail", "state"),
            cr("profile", "pass", "intake"),
        ],
        ["intake", "identify", "intake", "decide"],
    )
    assert f["reached"] == [
        "intake",
        "identify",
        "decide",
    ]  # distinct, in workflow order; the revisit is not counted
    assert (
        f["failed_node"] == "identify"
    )  # the first failing criterion whose step was reached, in workflow order
    assert f["summary"].startswith(
        "Reached 3 of 8 steps (intake, identify, decide); failed at identify"
    )
    assert "not reached: verify, screen, account, state, act" in f["summary"]
    assert (
        "needed by failed criteria: account_agreements, screening, state_rule_selection"
        in f["summary"]
    )
    assert "failed at account" not in f["summary"]
    assert f["missing_for"] == {
        "account": ["account_agreements"],
        "screen": ["screening"],
        "state": ["state_rule_selection"],
    }
    no_step_twice(f)


def test_only_unreached_failures_say_stopped_before():
    f = facts(
        [cr("screening", "fail", "screen"), cr("account_agreements", "fail", "account")],
        ["intake", "identify"],
    )
    assert f["failed_node"] is None
    assert (
        "; stopped before screen; not reached: verify, screen, account, state, decide, act"
        in f["summary"]
    )
    assert "failed at" not in f["summary"]


def test_a_reached_failure_is_named():
    f = facts([cr("decision", "fail", "decide")], ["intake", "decide"])
    assert (
        f["failed_node"] == "decide"
        and "failed at decide (criterion decision fail)" in f["summary"]
    )


@pytest.mark.parametrize(
    "state,denied,want",
    [
        ("scored", "screen", "failed at screen (screen.op was refused)"),
        ("timed_out", None, "failed at identify (timed out)"),
    ],
)
def test_refused_tool_and_timeout_fallbacks(state, denied, want):
    f = facts([], ["intake", "identify"], state=state, denied=denied)
    assert want in f["summary"]
    assert f["failed_node"] in f["reached"]


def test_everything_passed_has_no_failure_point():
    f = facts([cr("profile", "pass", "intake")], [n["id"] for n in WF["nodes"]])
    assert (
        f["summary"]
        == "Reached 8 of 8 steps (intake, identify, verify, screen, account, state, decide, act)"
    )
