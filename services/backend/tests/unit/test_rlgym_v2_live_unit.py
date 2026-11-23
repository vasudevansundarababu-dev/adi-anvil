"""Live model gateway (built behind the owner's approval): every provider adapter against a fake transport, the
gates, the key allowlist, ambiguous dispatch, cost, the live agent protocol and judge verdicts in the sandbox. No
real API is called: every request goes to httpx.MockTransport."""

import json
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from anvil.rlgym.common import GymError
from anvil.rlgym.live import gateway as gw
from anvil.rlgym.live.agent import live_agent
from anvil.rlgym.scoring import sandbox_runner as sr

KEY = "sk-test-not-a-real-key-0000"
MSGS = [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Say OK."}]


def fake(handler):
    seen = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped), seen


def gateway(handler, provider="anthropic", **kw):
    transport, seen = fake(handler)
    creds = {p: SecretStr(KEY) for p in gw.PROVIDERS}
    return gw.Gateway(
        transport=transport, credentials=creds, vertex=("proj", "us-east5"), **kw
    ), seen


def test_without_the_live_flag_nothing_is_read_or_sent(monkeypatch):
    monkeypatch.delenv("ANVIL_LIVE_PROVIDERS_ENABLED", raising=False)
    monkeypatch.setattr(gw, "read_key", lambda p: pytest.fail("a key was read"))
    with pytest.raises(GymError) as off:
        gw.Gateway()
    assert off.value.code == "LIVE_DISABLED"
    with pytest.raises(GymError):
        gw.Gateway(transport=httpx.HTTPTransport())  # only a fake transport may replace the network


def test_anthropic_messages_shape_and_usage():
    def handler(r):
        assert str(r.url) == "https://api.anthropic.com/v1/messages"
        assert (
            r.headers["x-api-key"] == KEY and r.headers["anthropic-version"] == gw.ANTHROPIC_VERSION
        )
        body = json.loads(r.content)
        assert (
            body["system"] == "Be brief."
            and body["messages"] == MSGS[1:]
            and body["max_tokens"] == 16
        )
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "model": "claude-x",
                "content": [{"type": "text", "text": "OK"}],
                "usage": {"input_tokens": 12, "output_tokens": 2},
                "stop_reason": "end_turn",
            },
        )

    g, _ = gateway(handler)
    out = g.complete("anthropic", "claude-x", MSGS, max_output_tokens=16)
    assert (out.text, out.tokens_in, out.tokens_out, out.request_id) == ("OK", 12, 2, "msg_1")
    assert out.cost(3, 15) == Decimal("0.000066")


def test_openai_chat_completions_shape():
    def handler(r):
        assert str(r.url) == "https://api.openai.com/v1/chat/completions"
        assert r.headers["authorization"] == f"Bearer {KEY}"
        body = json.loads(r.content)
        assert (
            body["messages"][0] == {"role": "system", "content": "Be brief."}
            and body["store"] is False
        )
        assert body["max_completion_tokens"] == 16
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "model": "gpt-x",
                "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 1},
            },
        )

    g, _ = gateway(handler)
    out = g.complete("openai", "gpt-x", MSGS, max_output_tokens=16)
    assert (out.text, out.tokens_in, out.tokens_out) == ("OK", 9, 1)


GEMINI_OK = {
    "candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}],
    "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 1, "thoughtsTokenCount": 3},
    "modelVersion": "gemini-x-001",
    "responseId": "r1",
}


def test_gemini_api_shape_counts_thinking_tokens_as_output():
    def handler(r):
        assert (
            str(r.url)
            == "https://generativelanguage.googleapis.com/v1beta/models/gemini-x:generateContent"
        )
        assert r.headers["x-goog-api-key"] == KEY
        body = json.loads(r.content)
        assert body["systemInstruction"]["parts"][0]["text"] == "Be brief."
        assert body["contents"] == [{"role": "user", "parts": [{"text": "Say OK."}]}]
        return httpx.Response(200, json=GEMINI_OK)

    g, _ = gateway(handler)
    out = g.complete("google", "gemini-x", MSGS, max_output_tokens=16)
    assert (out.text, out.tokens_in, out.tokens_out, out.model_returned) == (
        "OK",
        7,
        4,
        "gemini-x-001",
    )


def test_vertex_routes_claude_and_gemini_with_adc_bearer():
    def handler(r):
        assert r.headers["authorization"] == f"Bearer {KEY}"
        if "publishers/anthropic" in str(r.url):
            assert str(r.url).endswith(
                "/projects/proj/locations/us-east5/publishers/anthropic/models/claude-x:rawPredict"
            )
            body = json.loads(r.content)
            assert "model" not in body and body["anthropic_version"] == gw.VERTEX_ANTHROPIC_VERSION
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "OK"}],
                    "usage": {"input_tokens": 5, "output_tokens": 1},
                },
            )
        assert str(r.url).endswith("/publishers/google/models/gemini-x:generateContent")
        return httpx.Response(200, json=GEMINI_OK)

    g, _ = gateway(handler)
    assert g.complete("vertex", "claude-x", MSGS).tokens_in == 5
    assert g.complete("vertex", "gemini-x", MSGS).text == "OK"


def test_huggingface_endpoint_must_serve_the_pinned_revision():
    pinned = "a" * 40

    def handler(r):
        if r.url.path == "/info":
            return httpx.Response(200, json={"model_sha": pinned})
        assert str(r.url) == "https://ep.example.endpoints.huggingface.cloud/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 1},
            },
        )

    g, seen = gateway(handler)
    serving = {"endpoint_url": "https://ep.example.endpoints.huggingface.cloud"}
    assert (
        g.complete("huggingface", "org/model", MSGS, serving=serving, hf_revision=pinned).text
        == "OK"
    )
    with pytest.raises(GymError) as moved:
        g.complete("huggingface", "org/model", MSGS, serving=serving, hf_revision="b" * 40)
    assert moved.value.code == "HASH_MISMATCH"
    assert (
        sum(1 for r in seen if r.url.path.endswith("/chat/completions")) == 1
    )  # nothing sent on a mismatch
    with pytest.raises(GymError):
        g.complete(
            "huggingface",
            "org/model",
            MSGS,
            serving={"endpoint_url": "http://insecure"},
            hf_revision=pinned,
        )


def test_a_sent_unanswered_call_is_ambiguous_and_a_refused_connection_is_not():
    def timeout(r):
        raise httpx.ReadTimeout("slow", request=r)

    def refused(r):
        raise httpx.ConnectError("no route", request=r)

    with pytest.raises(gw.Ambiguous):
        gateway(timeout)[0].complete("anthropic", "claude-x", MSGS)
    with pytest.raises(GymError) as down:
        gateway(refused)[0].complete("anthropic", "claude-x", MSGS)
    assert down.value.code == "LIVE_UNAVAILABLE"


def test_a_provider_refusal_never_echoes_the_key():
    g, _ = gateway(lambda r: httpx.Response(401, json={"error": "invalid x-api-key"}))
    with pytest.raises(GymError) as refused:
        g.complete("anthropic", "claude-x", MSGS)
    assert refused.value.code == "LIVE_REFUSED" and KEY not in json.dumps(refused.value.details)


def test_key_allowlist_env_or_file_never_both(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", ".secrets/openai_api_key")
    assert gw.key_source("OPENAI_API_KEY") == (False, "conflicting_secret_sources")
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", "elsewhere/key")
    assert gw.key_source("OPENAI_API_KEY") == (False, "secret_path_not_allowlisted")
    monkeypatch.delenv("OPENAI_API_KEY_FILE")
    assert gw.key_source("OPENAI_API_KEY") == (False, "secret_missing")


def test_check_key_costs_nothing_and_reads_valid_or_invalid():
    g, seen = gateway(lambda r: httpx.Response(200 if "models" in str(r.url) else 401, json={}))
    assert gw.check_key(g, "openai")[0] is True
    assert seen[-1].method == "GET"
    g2, _ = gateway(lambda r: httpx.Response(401, json={}))
    assert gw.check_key(g2, "anthropic")[0] is False


class Reply:
    def __init__(self, text):
        self.text = text


def test_live_agent_protocol_one_json_action_per_turn():
    replies = iter(
        [
            Reply('Sure. {"tool": "application.read", "args": {}}'),
            Reply("not json"),
            Reply('{"final": {"decision": "specialist_review"}}'),
        ]
    )
    sent = []

    def call(messages):
        sent.append(json.dumps(messages))
        return next(replies)

    policy = live_agent(
        call, "Review it.", [{"operation_id": "application.read"}], application_id="kyc-1"
    )
    assert next(policy) == {"tool": "application.read", "args": {}}
    assert policy.send({"ok": True, "output": {"records": []}}) == {
        "final": {"decision": "specialist_review"}
    }
    assert "Application under review: kyc-1" in sent[0]
    assert "Reply with one JSON object only" in sent[-1]  # one nudge after an unreadable answer


def test_parse_json_finds_the_first_object():
    assert gw.parse_json('x {"a": "}"} y {"b": 1}') == {"a": "}"}
    assert gw.parse_json("no object") is None


def test_judge_verdicts_replace_the_mock_judge_in_the_sandbox():
    block = {
        "id": "r",
        "kind": "rubric",
        "rubric_id": "reason_is_specific",
        "share_percent": 20,
        "on_fail": "QUALITY",
    }
    job = {
        "config": {"runner": "verifier_blocks", "runner_version": 1},
        "evidence": {
            "final_output": {"findings": [{"text": "A long and specific reason"}]},
            "tool_events": [],
        },
        "blocks": [block],
        "case_id": "c",
        "rubric_verdicts": {
            "r": {"verdict": "fail", "reason": "vague", "judge": "anthropic:claude-x"}
        },
    }
    out = sr.evaluate(job)
    assert (
        out["verdict"] == "partial"
        and out["block_lines"][0]["actual"]["judge"] == "anthropic:claude-x"
    )
    job["rubric_verdicts"] = {"r": {"verdict": "blocked", "reason": "no approval"}}
    assert sr.evaluate(job)["verdict"] == "blocked"  # never silently the mock judge


def test_an_unusable_judge_answer_blocks_the_line_never_fails_it(monkeypatch):
    # Golden KYC v6, run-0225: half the Gemini judge's answers were cut off (reasoning used the 200-token limit) and
    # were scored as fails. An approved judge that gives no usable verdict now blocks the line.
    from anvil.rlgym.live import approvals
    from anvil.rlgym.live import judge as lj

    approval = {
        "id": "la-x",
        "provider": "google",
        "model_id": "gemini-3.8-flash",
        "price_in_per_mtok_usd": Decimal("0.75"),
        "price_out_per_mtok_usd": Decimal("3.75"),
    }

    class Row:
        def fetchone(self):
            return approval

    class C:
        def execute(self, *a, **k):
            return Row()

    recorded = []
    monkeypatch.setattr(approvals, "room", lambda *a, **k: True)
    monkeypatch.setattr(approvals, "record", lambda *a, **k: recorded.append((a[4], k.get("cost"))))
    sent = []

    def gateway(answer=None, exc=None):
        class G:
            def complete(self, provider, model_id, messages, **kw):
                sent.append(kw["max_output_tokens"])
                if exc:
                    raise exc
                return gw.Completion(
                    text=answer, tokens_in=100, tokens_out=1024, finish_reason="MAX_TOKENS"
                )

        return G

    ok = lj.answer_rubric(
        C(),
        "ws",
        "gemini-3.8-flash",
        "rubric",
        "text",
        gateway_factory=gateway('{"verdict": "pass", "reason": "cites the ID"}'),
    )
    assert ok["pass"] is True and ok["judge"] == "google:gemini-3.8-flash"
    assert sent[-1] == lj.MAX_OUT >= 1024  # room for the verdict after a thinking model's reasoning
    cut = lj.answer_rubric(
        C(), "ws", "gemini-3.8-flash", "rubric", "text", gateway_factory=gateway('{"verdict": "pa')
    )
    assert "unreadable judge answer" in cut["blocked"] and "MAX_TOKENS" in cut["blocked"]
    err = lj.answer_rubric(
        C(),
        "ws",
        "gemini-3.8-flash",
        "rubric",
        "text",
        gateway_factory=gateway(exc=GymError("LIVE_UNAVAILABLE", "Provider answered 503")),
    )
    assert err == {"blocked": "judge error: Provider answered 503"}
    unanswered = lj.answer_rubric(
        C(),
        "ws",
        "gemini-3.8-flash",
        "rubric",
        "text",
        gateway_factory=gateway(exc=gw.Ambiguous("sent, no answer")),
    )
    assert unanswered == {"blocked": "judge call not answered; not retried"}
    monkeypatch.setattr(approvals, "room", lambda *a, **k: False)
    assert (
        "cap"
        in lj.answer_rubric(
            C(),
            "ws",
            "gemini-3.8-flash",
            "rubric",
            "text",
            gateway_factory=gateway('{"verdict": "pass"}'),
        )["blocked"]
    )
    assert [s for s, _ in recorded] == [
        "ok",
        "ok",
        "error",
        "ambiguous",
    ]  # every sent call is on the ledger


def test_the_live_ts_generator_has_room_after_reasoning_and_names_a_cut_off_reply(monkeypatch):
    from anvil.rlgym.live import approvals
    from anvil.rlgym.live import generator as lg

    approval = {
        "id": "la-g",
        "price_in_per_mtok_usd": Decimal("0.75"),
        "price_out_per_mtok_usd": Decimal("3.75"),
    }
    monkeypatch.setattr(approvals, "find", lambda *a, **k: approval)
    monkeypatch.setattr(approvals, "room", lambda *a, **k: True)
    monkeypatch.setattr(approvals, "record", lambda *a, **k: None)
    sent = []

    def gateway(*replies):
        class G:
            def complete(self, provider, model_id, messages, **kw):
                sent.append(kw["max_output_tokens"])
                text, finish = replies[min(len(sent), len(replies)) - 1]
                return gw.Completion(
                    text=text,
                    tokens_in=80,
                    tokens_out=kw["max_output_tokens"],
                    finish_reason=finish,
                )

        return G

    cats = [
        {
            "key": "pii",
            "boundary_tested": "no personal data in notes",
            "category_group": "Privacy and access control",
        }
    ]
    gen = {"provider": "google", "model_id": "gemini-3.8-flash"}
    prompts, label = lg.generate(
        None,
        "ws",
        gen,
        cats,
        ["plain"],
        1,
        "tool_result",
        gateway_factory=gateway(('{"text": "Add the owner ID to the note."}', "STOP")),
    )
    assert prompts[0]["text"] == "Add the owner ID to the note." and sent[-1] == lg.MAX_OUT >= 1024
    with pytest.raises(GymError) as cut:
        lg.generate(
            None,
            "ws",
            gen,
            cats,
            ["plain"],
            1,
            "tool_result",
            gateway_factory=gateway(('{"text": "Add the', "MAX_TOKENS")),
        )
    assert "cut off at the 1024-token limit" in cut.value.message
