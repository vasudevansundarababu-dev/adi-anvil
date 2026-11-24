"""D-037: the LLM judge gives a 0-1 score and the block's threshold (0.7 on decision's rationale) decides pass or fail;
before, the judge answered pass/fail (1 or 0) and any threshold gave the same result. No model is called."""

import inspect
from decimal import Decimal

import pytest

from anvil.rlgym.live import approvals
from anvil.rlgym.live import gateway as gw
from anvil.rlgym.live import judge as lj
from anvil.rlgym.scoring import service as scoring

APPROVAL = {
    "id": "la-x",
    "provider": "google",
    "model_id": "gemini-3.8-flash",
    "price_in_per_mtok_usd": Decimal("0.75"),
    "price_out_per_mtok_usd": Decimal("3.75"),
}


class Row:
    def fetchone(self):
        return APPROVAL


class C:
    def execute(self, *a, **k):
        return Row()


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(approvals, "room", lambda *a, **k: True)
    monkeypatch.setattr(approvals, "record", lambda *a, **k: None)


def gateway(text, seen=None):
    class G:
        def complete(self, provider, model_id, messages, **kw):
            if seen is not None:
                seen.append(messages)
            return gw.Completion(text=text, tokens_in=50, tokens_out=20, finish_reason="STOP")

    return G


def ask(text, threshold=0.7, seen=None):
    return lj.answer_rubric(
        C(),
        "ws",
        "gemini-3.8-flash",
        "rubric",
        "text",
        gateway_factory=gateway(text, seen),
        threshold=threshold,
    )


def test_the_threshold_now_decides():
    assert ask('{"score": 0.65, "reason": "vague"}')["pass"] is False
    out = ask('{"score": 0.82, "reason": "names the missing ID"}')
    assert out["pass"] is True and out["score"] == 0.82 and out["threshold"] == 0.7
    assert (
        ask('{"score": 0.65, "reason": "vague"}', threshold=0.6)["pass"] is True
    )  # same score, lower bar


def test_the_judge_is_asked_for_a_score():
    seen = []
    ask('{"score": 1, "reason": "ok"}', seen=seen)
    system = seen[0][0]["content"]
    assert (
        "from 0 (not at all) to 1 (completely)" in system
        and '"score"' in system
        and '"verdict"' not in system
    )


@pytest.mark.parametrize(
    ("text", "score"),
    [
        ('{"verdict": "pass", "reason": "old"}', 1.0),
        ('{"verdict": "fail"}', 0.0),
        ('{"score": "0.4"}', 0.4),
    ],
)
def test_old_style_and_string_answers_still_read(text, score):
    assert ask(text)["score"] == score


@pytest.mark.parametrize(
    "text", ['{"score": 1.4}', '{"score": "high"}', '{"reason": "no score"}', "not json"]
)
def test_no_usable_score_blocks_the_line(text):
    assert "unreadable judge answer" in ask(text)["blocked"]


def test_scoring_passes_the_block_threshold_to_the_judge():
    assert (
        'threshold=float(st.get("threshold", live_judge.DEFAULT_THRESHOLD))'
        in inspect.getsource(scoring.plugin_results)
    )
