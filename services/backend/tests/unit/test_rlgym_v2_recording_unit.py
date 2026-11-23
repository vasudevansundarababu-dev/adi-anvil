"""D-008: a cut observation is visible to the model and recorded; the conversation and the judge's prompt and raw
answer are kept with the evidence. Synthetic data, fake model replies, no calls."""

import inspect
import json

from anvil.rlgym.live import agent as la
from anvil.rlgym.live import judge as lj


class Reply:
    def __init__(self, text):
        self.text = text
        self.tokens_in, self.tokens_out = 10, 5
        self.finish_reason, self.request_id = "end_turn", "req-1"


def test_a_long_observation_is_cut_with_an_explicit_line():
    obs = {"records": ["x" * 50 for _ in range(100)]}
    shown, total = la.render_observation(obs, 1000)
    assert total == len(json.dumps(obs)) and total > 1000
    assert shown.startswith(json.dumps(obs)[:1000])
    assert shown.endswith(f"[cut: showing 1000 of {total} characters; narrow the request]")
    small, n = la.render_observation({"ok": True}, 1000)
    assert small == '{"ok": true}' and n == len(small)


def test_the_conversation_is_logged_turn_by_turn():
    replies = iter(
        [
            Reply('{"tool": "application.read", "args": {}}'),
            Reply("not json"),
            Reply('{"final": {"decision": "specialist_review"}}'),
        ]
    )
    log = {}
    policy = la.live_agent(
        lambda m: next(replies),
        "Review application kyc-1.",
        [{"operation_id": "application.read"}],
        application_id="kyc-1",
        user_message="Hello from reset",
        log=log,
        max_observation_chars=1000,
    )
    assert next(policy) == {"tool": "application.read", "args": {}}
    assert policy.send({"records": ["y" * 60 for _ in range(40)]}) == {
        "final": {"decision": "specialist_review"}
    }
    assert [m["role"] for m in log["messages"]] == ["system", "user"]
    assert "Hello from reset" in log["messages"][1]["content"] and len(log["messages_sha256"]) == 64
    t1, t2, t3 = log["turns"]
    assert (
        t1["parsed"] == "tool" and t1["raw"].startswith('{"tool"') and t1["request_id"] == "req-1"
    )
    assert (
        t1["observation_cut"]
        and t1["observation_chars"] > 1000
        and "[cut: showing 1000 of" in t1["observation_shown"]
    )
    assert t2["parsed"] == "unreadable" and t2["nudge"].startswith("Reply with one JSON")
    assert t3["parsed"] == "final" and t3["tokens_in"] == 10 and t3["finish_reason"] == "end_turn"


def test_no_log_requested_keeps_the_old_behaviour():
    replies = iter([Reply('{"final": {"decision": "x"}}')])
    assert next(la.live_agent(lambda m: next(replies), "Do it.", [])) == {
        "final": {"decision": "x"}
    }


def test_judge_record_keeps_prompt_and_raw_answer():
    rec = lj.record("Rubric: r\n\nText to grade:\nt", Reply('{"verdict": "pass", "reason": "ok"}'))
    assert rec["system"] == lj.JUDGE and rec["prompt"].startswith("Rubric: r")
    assert (
        rec["raw"].startswith('{"verdict"')
        and rec["tokens_out"] == 5
        and rec["request_id"] == "req-1"
    )
    assert lj.record("p", note="not answered") == {
        "system": lj.JUDGE,
        "prompt": "p",
        "note": "not answered",
    }
    src = inspect.getsource(lj.answer_rubric)
    assert (
        src.count('"record": record(prompt') >= 4
    )  # every outcome after the call carries its record


def test_worker_seals_the_log_reset_message_and_cut_counts():
    from anvil.rlgym.runs import worker
    from anvil.rlgym.scoring import service

    src = inspect.getsource(worker.execute)
    for want in (
        '"agent_log": agent_log',
        '"reset": {"user_message"',
        '"observations_cut"',
        'entry["shown_chars"]',
    ):
        assert want in src, want
    assert 'line["judge"] = rec' in inspect.getsource(service.score_case)
