"""D-056: one retry on a connect timeout (the connection never opened, nothing was sent); every other ambiguous case is
still never retried. D-055: the live agent's guide says checks return records, not a verdict."""

import contextlib
import datetime as dt
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from anvil.rlgym.common import GymError
from anvil.rlgym.live import agent, approvals
from anvil.rlgym.live import gateway as gw

KEY = "placeholder-credential-for-tests"
MSGS = [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Say OK."}]
OK = {
    "id": "msg_1",
    "model": "claude-x",
    "content": [{"type": "text", "text": '{"final": {"decision": "approve"}}'}],
    "usage": {"input_tokens": 10, "output_tokens": 5},
    "stop_reason": "end_turn",
}


def scripted(*steps):
    """A fake transport that raises or answers in order; returns (gateway, requests seen)."""
    seen, queue = [], list(steps)

    def handler(request):
        seen.append(request)
        step = queue.pop(0)
        if isinstance(step, type) and issubclass(step, Exception):
            raise step("synthetic", request=request)
        return httpx.Response(200, json=step)

    g = gw.Gateway(
        transport=httpx.MockTransport(handler),
        credentials={p: SecretStr(KEY) for p in gw.PROVIDERS},
        vertex=("proj", "us-east5"),
    )
    return g, seen


def test_a_connect_timeout_is_retried_once_and_the_retry_is_recorded():
    g, seen = scripted(httpx.ConnectTimeout, OK)
    out = g.complete("anthropic", "claude-x", MSGS)
    assert len(seen) == 2 and out.tokens_in == 10
    assert out.retries == (
        {
            "reason": "ConnectTimeout",
            "detail": "connection never opened; no request bytes sent",
            "cost_usd": 0,
        },
    )


def test_a_clean_call_has_no_retries():
    g, seen = scripted(OK)
    assert g.complete("anthropic", "claude-x", MSGS).retries == () and len(seen) == 1


def test_a_second_connect_timeout_is_ambiguous_and_not_retried_again():
    g, seen = scripted(httpx.ConnectTimeout, httpx.ConnectTimeout, OK)
    with pytest.raises(gw.Ambiguous) as amb:
        g.complete("anthropic", "claude-x", MSGS)
    assert len(seen) == 2 and amb.value.code == "LIVE_AMBIGUOUS"
    assert len(amb.value.details["retries"]) == 1


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.PoolTimeout,
        httpx.RemoteProtocolError,
        httpx.ReadError,
    ],
)
def test_every_other_ambiguous_case_is_still_never_retried(exc):
    g, seen = scripted(exc, OK)
    with pytest.raises(gw.Ambiguous):
        g.complete("anthropic", "claude-x", MSGS)
    assert len(seen) == 1


def test_a_read_timeout_after_a_connect_retry_keeps_the_retry_on_the_error():
    g, seen = scripted(httpx.ConnectTimeout, httpx.ReadTimeout)
    with pytest.raises(gw.Ambiguous) as amb:
        g.complete("anthropic", "claude-x", MSGS)
    assert len(seen) == 2 and amb.value.details["retries"][0]["reason"] == "ConnectTimeout"


def test_a_refused_connection_is_still_an_ordinary_error_with_no_retry():
    g, seen = scripted(httpx.ConnectError, OK)
    with pytest.raises(GymError) as down:
        g.complete("anthropic", "claude-x", MSGS)
    assert down.value.code == "LIVE_UNAVAILABLE" and len(seen) == 1


def _caller(monkeypatch, gateway):
    approval = {
        "id": "la-t",
        "revoked_at": None,
        "expires_at": dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
        "price_in_per_mtok_usd": Decimal("1"),
        "price_out_per_mtok_usd": Decimal("1"),
    }

    class C:
        def execute(self, *a, **k):
            class R:
                def fetchone(self):
                    return approval

            return R()

    rows = []
    monkeypatch.setattr(agent, "system_scope", lambda ws: contextlib.nullcontext(C()))
    monkeypatch.setattr(approvals, "room", lambda *a, **k: True)
    monkeypatch.setattr(approvals, "max_cost", lambda *a, **k: Decimal("0.01"))
    monkeypatch.setattr(
        approvals, "record", lambda c, ws, a, use, status, **k: rows.append((status, k))
    )
    model = {
        "provider": "anthropic",
        "model_id": "claude-x",
        "spend_per_episode_usd": 1,
        "live": {"approval_id": "la-t", "params": {}},
    }
    return agent.LiveCaller(gateway, "ws", "run-x", "e1", model), rows


def test_the_retry_is_in_the_call_ledger_at_no_cost_and_on_the_episode_turn(monkeypatch):
    g, _ = scripted(httpx.ConnectTimeout, OK)
    caller, rows = _caller(monkeypatch, g)
    log = {}
    policy = agent.live_agent(caller, "Review the application.", ["case.read"], log=log)
    assert "final" in next(policy)
    assert [r[0] for r in rows] == ["error", "ok"]
    retry = rows[0][1]
    assert retry["cost"] == 0 and "D-056 connect retry" in retry["note"]
    assert rows[1][1]["cost"] == Decimal("0.000015")  # the answered call is counted as before
    assert (
        log["connect_retries"] == 1 and log["turns"][0]["retries"][0]["reason"] == "ConnectTimeout"
    )


def test_a_failed_retry_is_in_the_ledger_and_the_ambiguous_call_at_its_maximum(monkeypatch):
    g, _ = scripted(httpx.ConnectTimeout, httpx.ConnectTimeout)
    caller, rows = _caller(monkeypatch, g)
    with pytest.raises(gw.Ambiguous):
        caller(MSGS)
    assert [r[0] for r in rows] == ["error", "ambiguous"]
    assert rows[0][1]["cost"] == 0 and rows[1][1]["cost"] == Decimal("0.01")


def test_d055_the_guide_says_checks_return_records_not_a_verdict():
    line = "Checks return the records they cover, not a verdict; decide from those records."
    assert line in agent.PROTOCOL
    log = {}
    policy = agent.live_agent(lambda m: None, "Task.", ["case.read"], log=log)
    with contextlib.suppress(Exception):
        next(policy)
    assert line in log["messages"][0]["content"]


def test_the_relabel_reuses_the_latest_pass_versions_and_only_appends():
    import inspect

    from anvil.rlgym.runs import service as runs

    src = inspect.getsource(runs.relabel)
    assert (
        'scoring.create_pass(\n        c, ws, run_id, "rescore", base["evaluator_versions"]' in src
    )
    assert "DELETE" not in src and "UPDATE scoring.episode_scores" not in src
    assert "UPDATE scoring.criterion_receipts" not in src
