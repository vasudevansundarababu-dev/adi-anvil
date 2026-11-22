# ruff: noqa: F811  (pytest fixtures shared from test_rlgym_v2 are parameters here)
"""Live models, built behind the owner's approval, with fake clients only (no real API is called): approval records,
admission (flag, key allowlist, approval, two people, caps), a live run whose agent is a scripted fake model, spend
per call and per run, the stop at the per-run cap, the live probe, a live judge and live generation."""

import datetime as dt
import json
import uuid
from decimal import Decimal

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row
from pydantic import SecretStr
from test_rlgym_v2 import PROJECT, exported, person, post, ws  # noqa: F401
from test_rlgym_v2_runs import lineup, small_suite  # noqa: F401

from anvil.config import setting
from anvil.rlgym.live import gateway as gw
from anvil.rlgym.runs import images, worker
from anvil.rlgym.systems import service as systems

pytestmark = pytest.mark.skipif(not images.docker_status()[0], reason="Docker is required for runs")
MODEL = "claude-test-model"


def scripted():
    """A fake Anthropic endpoint: each episode reads the application, then answers. 100 tokens in, 20 out per call."""

    def handler(request):
        body = json.loads(request.content)
        last = body["messages"][-1]["content"]
        text = (
            '{"final": {"decision": "escalate", "findings": [{"text": "Possible match; refer to compliance"}]}}'
            if last.startswith("Observation")
            else '{"tool": "application.read", "args": {}}'
        )
        return httpx.Response(
            200,
            json={
                "id": "msg_fake",
                "model": MODEL,
                "content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 100, "output_tokens": 20},
            },
        )

    return lambda: gw.Gateway(
        transport=httpx.MockTransport(handler), credentials={"anthropic": SecretStr("sk-fake-0000")}
    )


@pytest.fixture
def live_env(monkeypatch):
    monkeypatch.setenv("ANVIL_LIVE_PROVIDERS_ENABLED", "true")
    monkeypatch.setenv(
        "ANTHROPIC_API_KEY", "sk-fake-0000"
    )  # allowlist presence only; the fake transport is used
    monkeypatch.setattr(worker, "GATEWAY_FACTORY", scripted())
    monkeypatch.setattr(systems, "GATEWAY_FACTORY", scripted())


def approve(base, who, **over):
    body = {
        "provider": "anthropic",
        "model_id": MODEL,
        "uses": ["agent", "probe", "judge"],
        "per_run_cap_usd": 1,
        "total_cap_usd": 2,
        "price_in_per_mtok_usd": 3,
        "price_out_per_mtok_usd": 15,
        "prices_note": "Test prices (integration test), not real",
        "expires_at": (dt.datetime.now(dt.UTC) + dt.timedelta(days=2)).isoformat(),
        **over,
    }
    return post(person(who), base + "/live/approvals", body, expected=None)


def revoke_all(base):
    for a in person("admin-2").get(base + "/live/approvals").json()["data"]["items"]:
        if a["state"] == "active":
            post(
                person("admin-2"),
                base + f"/live/approvals/{a['id']}/revoke",
                {"reason": "test isolation"},
            )


@pytest.fixture
def live_model(small_suite, live_env):
    base, admin = small_suite["base"], person("admin-1")
    revoke_all(base)
    post(
        admin,
        base + "/keys",
        {"provider": "anthropic", "name": "Anthropic (allowlist)", "secret": "sk-label-only-0000"},
    )
    out = post(
        admin,
        base + "/systems",
        {
            "kind": "frontier",
            "provider": "anthropic",
            "model_id": MODEL,
            "name": f"claude-test-{uuid.uuid4().hex[:6]}",
            "params": {"max_output_tokens": 64, "timeout_s": 30},
            "limits": {"rpm": 60, "spend_per_episode_usd": 0.02},
        },
    ).json()["data"]
    sid = out["system"]["system_id"]
    ms = post(
        admin,
        base + "/model-sets",
        {
            "name": f"Live test {uuid.uuid4().hex[:6]}",
            "members": [{"system_id": sid, "system_version": 1}],
        },
    ).json()["data"]
    return {
        **small_suite,
        "system_id": sid,
        "model_set": {"id": ms["id"], "version": ms["version"]},
    }


def run_body(ctx):
    return {
        "name": "Live · fake model",
        "project_id": PROJECT,
        "suite_version_id": ctx["suite_version_id"],
        "model_set": ctx["model_set"],
        "attempts": 1,
        "episode_timeout_min": 2,
        "infra_retries": 1,
        "budget_usd": 5,
    }


def test_approvals_are_validated_admin_only_and_final(small_suite):
    base = small_suite["base"]
    assert approve(base, "researcher").status_code == 403
    assert approve(base, "admin-1", prices_note=" ").status_code == 422
    assert approve(base, "admin-1", per_run_cap_usd=5, total_cap_usd=2).status_code == 422
    far = (dt.datetime.now(dt.UTC) + dt.timedelta(days=60)).isoformat()
    assert approve(base, "admin-1", expires_at=far).status_code == 422
    assert (
        approve(base, "admin-1", provider="huggingface", model_id="org/m").status_code == 422
    )  # no revision
    a = approve(base, "admin-1").json()["data"]
    assert a["state"] == "active" and Decimal(str(a["spent_usd"])) == 0
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        with pytest.raises(psycopg.Error):
            c.execute("UPDATE systems.live_approvals SET total_cap_usd=100 WHERE id=%s", (a["id"],))
    revoked = post(
        person("admin-1"), base + f"/live/approvals/{a['id']}/revoke", {"reason": "test"}
    ).json()["data"]
    assert revoked["state"] == "revoked"


def test_admission_needs_the_flag_an_approval_and_a_second_person(live_model, monkeypatch):
    base, admin = live_model["base"], person("admin-1")

    def refused_detail():
        check = admin.post(base + "/runs/admission-check", json=run_body(live_model)).json()["data"]
        return " | ".join(f"{i['key']}: {i['detail']}" for i in check["items"] if not i["ok"])

    monkeypatch.setenv("ANVIL_LIVE_PROVIDERS_ENABLED", "false")
    assert "live provider calls are disabled locally" in refused_detail()
    monkeypatch.setenv("ANVIL_LIVE_PROVIDERS_ENABLED", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert "KEY_MISSING: ANTHROPIC_API_KEY" in refused_detail()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-0000")
    assert "no active live approval" in refused_detail()
    approve(base, "admin-1")  # admin-1 approves, so admin-1 may not start it
    assert "cannot also start this run" in refused_detail()


def test_a_live_run_records_spend_and_stops_at_its_cap(live_model):
    base = live_model["base"]
    # admin-2 approves with a per-run cap that fits the estimate but stops the run after a few calls.
    a = approve(base, "admin-2", per_run_cap_usd=0.01, total_cap_usd=1).json()["data"]
    starter = person("admin-1")
    check = starter.post(base + "/runs/admission-check", json=run_body(live_model)).json()["data"]
    over = next(i for i in check["items"] if i["key"] == "live_approval")
    assert (
        not over["ok"] and "above the per-run cap" in over["detail"]
    )  # 8 × $0.02 projected > $0.01
    post(
        person("admin-2"),
        base + f"/live/approvals/{a['id']}/revoke",
        {"reason": "cap too small for the estimate"},
    )
    a = approve(base, "admin-2", per_run_cap_usd=0.5, total_cap_usd=1).json()["data"]
    r = post(starter, base + "/runs", run_body(live_model), 201).json()["data"]
    assert not r["refused"], r["check"]
    run_id = r["run"]["id"]
    assert worker.drain(timeout=600)
    run = starter.get(base + f"/runs/{run_id}").json()["data"]
    assert (
        run["execution_mode"] == "live"
        and run["manifest"]["models"][0]["live"]["approval_id"] == a["id"]
    )
    spend = run["live_spend"][0]
    assert spend["calls"] >= 2 and spend["tokens_in"] == 100 * spend["calls"]
    assert (
        Decimal(str(spend["cost_usd"])) == Decimal("0.0006") * spend["calls"]
    )  # (100×3 + 20×15) / 1e6 per call
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        sealed = c.execute(
            "SELECT s.synthetic, s.cost_usd FROM runs.sealed_evidence s JOIN runs.episodes e ON e.id=s.episode_id WHERE e.run_id=%s",
            (run_id,),
        ).fetchall()
    assert sealed and not any(
        s["synthetic"] for s in sealed
    )  # real executions, labelled apart from mock results
    assert all(
        Decimal(str(s["cost_usd"])) == Decimal("0.0012") for s in sealed
    )  # two calls per episode


def test_admission_refuses_when_the_total_cap_has_too_little_left(live_model):
    base = live_model["base"]
    a = approve(base, "admin-2", per_run_cap_usd=0.16, total_cap_usd=0.16).json()["data"]
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        c.execute(
            """INSERT INTO systems.live_calls(workspace_id,approval_id,use,provider,model_id,status,cost_usd,note)
               VALUES(%s,%s,'probe','anthropic',%s,'ok',0.1,'earlier spend (test)')""",
            (live_model["id"], a["id"], MODEL),
        )
    check = (
        person("admin-1")
        .post(base + "/runs/admission-check", json=run_body(live_model))
        .json()["data"]
    )
    item = next(i for i in check["items"] if i["key"] == "live_approval")
    assert not item["ok"] and "left of the total cap" in item["detail"]


def test_the_run_stops_at_its_cap_and_starts_nothing_more(live_model):
    base, admin = live_model["base"], person("admin-1")
    out = post(
        admin,
        base + "/systems",
        {
            "kind": "frontier",
            "provider": "anthropic",
            "model_id": MODEL,
            "name": f"claude-tight-{uuid.uuid4().hex[:6]}",
            "params": {"max_output_tokens": 64, "timeout_s": 30},
            # Below one call's worst case: the first call would cross the episode limit, so nothing is sent.
            "limits": {"rpm": 60, "spend_per_episode_usd": 0.0001},
        },
    ).json()["data"]
    ms = post(
        admin,
        base + "/model-sets",
        {
            "name": f"Tight {uuid.uuid4().hex[:6]}",
            "members": [{"system_id": out["system"]["system_id"], "system_version": 1}],
        },
    ).json()["data"]
    approve(base, "admin-2", per_run_cap_usd=0.01, total_cap_usd=0.01)
    body = {**run_body(live_model), "model_set": {"id": ms["id"], "version": ms["version"]}}
    r = post(admin, base + "/runs", body, 201).json()["data"]
    assert not r["refused"], r["check"]
    assert worker.drain(timeout=600)
    run_id = r["run"]["id"]
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        eps = c.execute(
            "SELECT state, last_error FROM runs.episodes WHERE run_id=%s", (run_id,)
        ).fetchall()
        calls = c.execute(
            "SELECT count(*) n FROM systems.live_calls WHERE run_id=%s", (run_id,)
        ).fetchone()["n"]
    assert all(e["state"] == "errored" for e in eps)
    assert any("episode spend limit" in (e["last_error"] or "") for e in eps)
    assert sum(1 for e in eps if (e["last_error"] or "").startswith("not run:")) == len(eps) - 1
    assert calls == 0  # stopped before sending


def test_live_probe_and_key_test_only_with_flag_and_approval(live_model, monkeypatch):
    base, admin = live_model["base"], person("admin-1")
    sid = live_model["system_id"]
    probe = post(admin, base + f"/systems/{sid}/versions/1/probe", {}).json()["data"]
    assert (
        probe["result"] == "live_disabled" and "no active live approval" in probe["details"]["note"]
    )
    approve(base, "admin-2", uses=["probe"])
    probe = post(admin, base + f"/systems/{sid}/versions/1/probe", {}).json()["data"]
    assert probe["result"] == "ok" and probe["mode"] == "live" and float(probe["cost_usd"]) > 0
    monkeypatch.setenv("ANVIL_LIVE_PROVIDERS_ENABLED", "false")
    again = post(admin, base + f"/systems/{sid}/versions/1/probe", {}).json()["data"]
    assert again["result"] == "live_disabled"


def test_live_judge_and_generator_need_their_own_approval(live_model):
    from anvil.rlgym.common import system_scope
    from anvil.rlgym.live import generator, judge

    block = {
        "id": "r",
        "kind": "rubric",
        "rubric_id": "reason_is_specific",
        "share_percent": 20,
        "on_fail": "QUALITY",
    }
    evidence = {"final_output": {"findings": [{"text": "A specific reason"}]}, "tool_events": []}
    spec = {"provider": "anthropic", "model_id": MODEL}

    def judging():
        def handler(request):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": '{"verdict": "pass", "reason": "specific"}'}
                    ],
                    "usage": {"input_tokens": 50, "output_tokens": 10},
                },
            )

        return gw.Gateway(
            transport=httpx.MockTransport(handler),
            credentials={"anthropic": SecretStr("sk-fake-0000")},
        )

    with system_scope(live_model["id"]) as c:
        none = judge.rubric_verdicts(
            c, live_model["id"], spec, [block], evidence, gateway_factory=judging
        )
        assert (
            none["r"]["verdict"] == "blocked" and "no active live approval" in none["r"]["reason"]
        )
    approve(live_model["base"], "admin-2", uses=["judge"])
    with system_scope(live_model["id"]) as c:
        got = judge.rubric_verdicts(
            c, live_model["id"], spec, [block], evidence, gateway_factory=judging
        )
        assert got["r"] == {"verdict": "pass", "reason": "specific", "judge": f"anthropic:{MODEL}"}
        from anvil.rlgym.common import GymError

        with pytest.raises(GymError) as refused:
            generator.generate(
                c,
                live_model["id"],
                spec,
                [{"key": "k", "category_group": "x"}],
                ["plain"],
                1,
                "tool_result",
                gateway_factory=judging,
            )
        assert refused.value.code == "ADMISSION_REFUSED"
