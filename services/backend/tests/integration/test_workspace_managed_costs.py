"""Managed cost contracts reuse the isolated execution fixture."""
# ruff: noqa: F811

import json

import httpx
import pytest
from test_api_security import USERS
from test_workspace_adapter_contracts import response_body
from test_workspace_execution import configured  # noqa: F401

from anvil import cli, harbor_agents, workspace_costs
from anvil import workspace_execution as execution
from anvil.db import one, transaction


@pytest.mark.parametrize("configured", ["managed-costs"], indirect=True)
def test_no_manual_cost_or_terms_setup_and_refresh_preserves_history_and_budget(
    configured, monkeypatch
):
    data = configured
    post = data["post"]
    old = data["group"]
    admin = USERS["admin-1"]
    assert old["readiness"]["missing"] == ["admin_run_authorization_required"]
    assert all(not model["missing"] for model in old["readiness"]["models"])
    assert old["snapshot"]["pricing"][0]["source_kind"] == "anvil_managed"
    assert old["snapshot"]["processing_terms"][0] == {"reviewed": False, "reference": None}
    with transaction(cli.PROJECT, admin) as c:
        original_model = one(
            c, "SELECT config FROM anvil.connections WHERE id=%s", (data["models"][0]["id"],)
        )
        assert original_model["config"]["workspace_pricing"] is None
        before = {
            table: one(c, "SELECT count(*) n FROM anvil." + table)["n"]
            for table in (
                "jobs",
                "harbor_checks",
                "evaluation_spend_windows",
                "workspace_admin_run_authorizations",
            )
        }
    monkeypatch.setattr(workspace_costs, "REFERENCE", "contract-managed-rate-revision-two")
    monkeypatch.setattr(harbor_agents, "code_digest", lambda: "d" * 64)
    refreshed = post("/execution-groups", {"preparation_id": data["prep"]["id"]})
    assert refreshed["id"] != old["id"] and refreshed["subject_hash"] != old["subject_hash"]
    assert refreshed["preparation_id"] == old["preparation_id"]
    assert refreshed["snapshot"]["preparation"] == old["snapshot"]["preparation"]
    assert refreshed["snapshot"]["pricing"][0]["reference"] == "contract-managed-rate-revision-two"
    assert (
        refreshed["readiness"]["aggregate_cap_micro_usd"]
        == old["readiness"]["aggregate_cap_micro_usd"]
    )
    assert {m["plan_id"] for m in old["models"]}.isdisjoint(
        m["plan_id"] for m in refreshed["models"]
    )
    with transaction(cli.PROJECT, admin) as c:
        assert execution.group(c, old["id"])["snapshot"] == old["snapshot"]
        assert {
            table: one(c, "SELECT count(*) n FROM anvil." + table)["n"] for table in before
        } == before
        assert execution.authority(c, execution.group(c, refreshed["id"])) is None
    gid = refreshed["id"]
    post("/execution-groups/" + gid + "/launch", expected=409)
    body = {
        "subject_hash": refreshed["subject_hash"],
        "aggregate_cap_micro_usd": 1000000,
        "rights_confirmed": True,
    }
    post("/execution-groups/" + gid + "/launch", {**body, "rights_confirmed": False}, expected=409)
    launched = post("/execution-groups/" + gid + "/launch", body)
    member = launched["models"][0]
    with transaction(cli.PROJECT, admin) as c:
        c.execute(
            "UPDATE anvil.harbor_checks SET state='running',invocation_count=1 WHERE id=%s",
            (member["check"]["id"],),
        )
    calls = []

    def handle(request):
        calls.append(request)
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-6-luna" and payload["service_tier"] == "default"
        assert payload["prompt_cache_options"] == {"ttl": "30m"}
        assert "PRIVATE-NORTHSTAR" not in request.content.decode()
        value = response_body("openai", "{}")
        value["model"] = "gpt-6-luna"
        value["usage"] = {
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
            "input_tokens_details": {"cached_tokens": 3, "cache_write_tokens": 2},
            "output_tokens_details": {"reasoning_tokens": 0},
        }
        return httpx.Response(200, json=value)

    assert (
        execution.decision(
            cli.PROJECT, admin, member["plan_id"], 0, transport=httpx.MockTransport(handle)
        )
        == "{}"
    )
    assert len(calls) == 1
    with transaction(cli.PROJECT, admin) as c:
        call = one(
            c,
            "SELECT actual_micro_usd,reserved_micro_usd FROM anvil.harbor_agent_calls WHERE plan_id=%s",
            (member["plan_id"],),
        )
        assert call["actual_micro_usd"] == 11 and call["reserved_micro_usd"] >= 11
        assert (
            one(
                c,
                "SELECT reserved_micro_usd FROM anvil.evaluation_spend_windows WHERE id=%s",
                (execution.group(c, gid)["window_id"],),
            )["reserved_micro_usd"]
            == 1000000
        )
    monkeypatch.setattr(workspace_costs, "EXPIRES", "2020-01-01T00:00:00+00:00")
    with transaction(cli.PROJECT, admin) as c:
        assert (
            "model_cost_support_expired"
            in execution.readiness(c, execution.group(c, gid))["models"][0]["missing"]
        )


@pytest.mark.parametrize("configured", ["managed-costs"], indirect=True)
@pytest.mark.parametrize("cap", [None, 1])
def test_refresh_never_invents_or_raises_a_missing_or_small_cap(configured, cap):
    data = configured
    prep = data["prep"]["snapshot"]
    draft = data["post"](
        "/preparations",
        {
            "preset_id": prep["preset_id"],
            "package_id": prep["package"]["id"],
            "model_profile_ids": [data["models"][0]["id"]],
            "max_output_tokens": 1024,
            "episode_timeout_seconds": 300,
            "aggregate_cap_micro_usd": cap,
        },
    )
    for _ in range(2):
        group = data["post"]("/execution-groups", {"preparation_id": draft["id"]})
        assert group["readiness"]["aggregate_cap_micro_usd"] == cap
        assert (
            "aggregate_api_cap_missing" in group["readiness"]["missing"]
            if cap is None
            else "group_cap_below_conservative_cost_or_above_authority"
            in group["readiness"]["missing"]
        )
        assert all(not model["check"] for model in group["models"])
