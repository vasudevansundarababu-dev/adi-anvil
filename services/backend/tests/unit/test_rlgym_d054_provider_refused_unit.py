"""D-054 (owner: "Flag, exclude from score"): a refusal is recorded, gets its own retry, and two of them end the episode
as "provider refused", which no score, pass rate or leaderboard counts. Fake model replies; no calls, no database."""

import inspect

from anvil.rlgym.live import agent as la
from anvil.rlgym.scoring import service as scoring


class Reply:
    def __init__(self, text, finish="end_turn"):
        self.text, self.finish_reason = text, finish
        self.tokens_in, self.tokens_out, self.request_id = 10, 5, "req"


def drive(replies, observations=None):
    """Run the live agent on scripted replies; → (actions, log, messages sent on each call)."""
    replies, sent, log = iter(replies), [], {}

    def call(messages):
        sent.append([dict(m) for m in messages])
        return next(replies)

    policy = la.live_agent(call, "Review application kyc-1.", [], log=log)
    actions = [next(policy)]
    while "final" not in actions[-1]:
        actions.append(policy.send((observations or {}).get(len(actions), {"ok": True})))
    return actions, log, sent


TOOL = '{"tool": "application.read", "args": {}}'
FINAL = '{"final": {"decision": "approve"}}'


def test_a_refusal_mid_episode_then_a_good_turn_continues():
    actions, log, sent = drive([Reply(TOOL), Reply("", "refusal"), Reply(TOOL), Reply(FINAL)])
    assert actions == [
        {"tool": "application.read", "args": {}},
        {"tool": "application.read", "args": {}},
        {"final": {"decision": "approve"}},
    ]
    t = log["turns"]
    assert t[1]["parsed"] == "refusal" and t[1]["finish_reason"] == "refusal" and t[1]["retry"]
    assert log["refusals"] == 1 and "provider_refused" not in log
    # The retry sends the same conversation; the empty refusal is never kept in the history.
    assert sent[2] == sent[1]
    assert all(m["content"] for c in sent for m in c if m["role"] == "assistant")


def test_two_refusals_end_the_episode_as_provider_refused():
    actions, log, _ = drive(
        [Reply(TOOL), Reply("", "refusal"), Reply(TOOL), Reply("partial", "refusal")]
    )
    assert actions[-1] == {"final": None}
    assert log["provider_refused"]["refusals"] == 2 and log["provider_refused"]["turns"] == [2, 4]


def test_a_refusal_does_not_use_the_format_nudge_and_the_nudge_resets():
    # bad JSON → nudge; refusal → its own retry; readable; bad JSON again → nudged again (allowance reset); final.
    actions, log, _ = drive(
        [
            Reply("not json"),
            Reply("", "refusal"),
            Reply(TOOL),
            Reply("still not json"),
            Reply(FINAL),
        ]
    )
    assert actions[-1] == {"final": {"decision": "approve"}}
    nudges = [x["turn"] for x in log["turns"] if x.get("nudge")]
    assert nudges == [1, 4] and "provider_refused" not in log


def test_bad_json_twice_in_a_row_still_ends_as_before():
    actions, log, _ = drive([Reply("not json"), Reply("again not json")])
    assert actions == [{"final": None}] and "provider_refused" not in log


def test_provider_refusal_is_read_from_the_bundle_or_derived_for_older_bundles():
    recorded = {"live": True, "provider_refused": {"refusals": 2, "turns": [2, 4]}}
    assert scoring.provider_refusal(recorded)["source"] == "recorded"
    # Sealed before D-054 (run-0234 e0002's shape): the conversation ended on a refusal with no final output.
    old = {
        "live": True,
        "final_output": None,
        "agent_log": {
            "turns": [
                {"turn": 1, "finish_reason": "end_turn"},
                {"turn": 2, "finish_reason": "refusal"},
                {"turn": 3, "finish_reason": "end_turn"},
                {"turn": 4, "finish_reason": "refusal"},
            ]
        },
    }
    derived = scoring.provider_refusal(old)
    assert (
        derived["refusals"] == 2
        and derived["turns"] == [2, 4]
        and "sealed before" in derived["source"]
    )
    # Not flagged: a refusal the agent recovered from, a mock episode, or an episode that finished.
    recovered = {**old, "agent_log": {"turns": old["agent_log"]["turns"][:3]}}
    assert scoring.provider_refusal(recovered) is None
    assert scoring.provider_refusal({**old, "live": False}) is None
    assert scoring.provider_refusal({**old, "final_output": {"decision": "x"}}) is None


class FakeCursor:
    """Records SQL; score_case is replaced, so only the diversion's own statements are seen."""

    def __init__(self):
        self.sql = []

    def execute(self, sql, args=None):
        self.sql.append(" ".join(sql.split()))
        return self

    def fetchall(self):
        return [
            {
                "criterion_id": "screening",
                "verdict": "fail",
                "points": 0,
                "weight": 5,
                "detail": [],
                "receipt_sha256": "0" * 64,
            }
        ]


def test_a_refused_episode_is_graded_but_only_kept_apart_from_scores(monkeypatch):
    calls = []

    def fake_score_case(c, ws, episode, pass_row, manifest, sealed):
        calls.append(episode["id"])
        c.execute("INSERT INTO scoring.criterion_receipts ...")
        c.execute("INSERT INTO scoring.episode_scores ...")
        return {"score": 25.0, "passed": False, "failed": ["screening"], "blocked": []}

    monkeypatch.setattr(scoring, "score_case", fake_score_case)
    c = FakeCursor()
    out = scoring._score_refused(
        c, "ws", {"id": "e1"}, {"id": "p1"}, {}, {}, {"refusals": 2, "turns": [2, 4]}
    )
    assert calls == ["e1"] and out["provider_refused"]["refusals"] == 2
    sql = c.sql
    assert sql[0] == "SAVEPOINT d054_refused"
    # Whatever score_case wrote is rolled back before the refused record is written.
    assert sql.index("ROLLBACK TO SAVEPOINT d054_refused") > sql.index(
        "INSERT INTO scoring.episode_scores ..."
    )
    assert sql[-1].startswith("INSERT INTO scoring.refused_episodes")


def test_scores_and_statistics_leave_refused_episodes_out():
    src = inspect.getsource(scoring.score_episode)
    assert "provider_refusal(read_sealed(sealed))" in src and "_score_refused(" in src
    stats = inspect.getsource(scoring.run_statistics)
    assert "scoring.refused_episodes" in stats and 's["provider_refused"] += 1' in stats
    # Safety episodes are never flagged: a refusal there can be the model resisting.
    assert src.index('episode["kind"] == "safety"') < src.index("provider_refusal(")
