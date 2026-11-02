"""Authored software candidate; only public observations are used to derive answers."""

import json

import httpx
from test_api_security import USERS
from test_praxis_harbor import BASE
from test_workspace_adapter_contracts import response_body

from anvil import cli, harbor_worker, workspace_dispatch
from anvil.db import one, transaction


def scripted_action(prompt):
    state = json.loads(prompt.split("\n", 1)[1])
    observations = state["observations"]
    if not observations:
        return {"tool": "read_data", "arguments": {}}
    if observations[-1]["tool"] == "save_result":
        return {"done": True}
    data = observations[0]["observation"]
    if "channels" in data:
        allocations = {
            c["id"]: data["budget_cents"] // len(data["channels"]) for c in data["channels"]
        }
        allocations[data["channels"][-1]["id"]] += data["budget_cents"] - sum(allocations.values())
        output = {
            "allocation_cents": allocations,
            "expected_leads": sum(
                allocations[c["id"]] / c["cpc_cents"] * c["lead_rate"] for c in data["channels"]
            ),
            "evidence_ids": [c["evidence_id"] for c in data["channels"]],
        }
    elif "entities" in data:
        owners = {}

        def walk(person, amount):
            if person in data["people"]:
                owners[person] = owners.get(person, 0) + amount
            else:
                for owner, share in data["entities"][person]["owners"].items():
                    walk(owner, amount * share / 10000)

        walk(data["applicant"], 10000)
        ubos = sorted(p for p, share in owners.items() if share > data["ubo_threshold_bps"])
        sanctioned = [p for p in ubos if data["people"][p]["sanctioned"]]
        output = {
            "owners_bps": {k: int(v) for k, v in owners.items()},
            "ubo_ids": ubos,
            "risk_high": bool(sanctioned),
            "sar": {
                "subject_ids": sanctioned,
                "reason_codes": ["SANCTIONS_MATCH"] if sanctioned else [],
                "evidence_ids": [e["evidence_id"] for e in data["entities"].values()],
            },
        }
    else:
        rows = [
            r
            for r in data["transactions"]
            if data["window_start"] <= r["time"] < data["window_end"]
        ]
        net = {}
        for row in rows:
            net[row["account"]] = (
                net.get(row["account"], 0)
                + (1 if row["direction"] == "in" else -1) * row["amount_cents"]
            )
        flagged = sorted(k for k, v in net.items() if v >= data["threshold_cents"])
        for account in flagged:
            for tool in ("freeze_account", "escalate_case"):
                if not any(
                    e["tool"] == tool and e["arguments"] == {"account": account}
                    for e in observations
                ):
                    return {"tool": tool, "arguments": {"account": account}}
        output = {
            "flagged_accounts": flagged,
            "net_inflow_cents": sum(net[k] for k in flagged),
            "action": "freeze_and_escalate",
            "evidence_ids": [r["id"] for r in rows if r["account"] in flagged],
        }
    return {"tool": "save_result", "arguments": {"output": output}}


def evaluate_ready(data, monkeypatch, package_id):
    original = workspace_dispatch.execute
    requests = []

    def mocked(binding, secret, request, **kwargs):
        def respond(req):
            requests.append(req)
            assert (
                "PRIVATE-GOLDEN" not in request.actor_text
                and "expected_reward" not in request.actor_text
            )
            return httpx.Response(
                200,
                json=response_body(
                    binding["provider"], json.dumps(scripted_action(request.actor_text))
                ),
            )

        return original(binding, secret, request, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(workspace_dispatch, "execute", mocked)
    create = data["post"]
    prep = create(
        "/preparations",
        {
            "preset_id": data["prep"]["snapshot"]["preset_id"],
            "package_id": package_id,
            "model_profile_ids": [m["id"] for m in data["models"][:2]],
            "max_output_tokens": 1024,
            "max_agent_steps": 12,
            "episode_timeout_seconds": 120,
            "aggregate_cap_micro_usd": 10000000,
            "trials_per_model": 3,
        },
    )
    group = create("/execution-groups", {"preparation_id": prep["id"]})
    create(
        "/execution-groups/" + group["id"] + "/authorize",
        {
            "subject_hash": group["subject_hash"],
            "aggregate_cap_micro_usd": 10000000,
            "rights_confirmed": True,
        },
    )
    launched = create("/execution-groups/" + group["id"] + "/launch")
    assert len(launched["models"]) == 6
    for member in launched["models"]:
        with transaction(worker=True) as c:
            job = one(c, "SELECT * FROM anvil.claim_harbor_job()")
        assert str(job["target_id"]) == member["check"]["id"]
        harbor_worker.process(job)
        response = data["clients"]["admin-1"].get(BASE + "/harbor-checks/" + member["check"]["id"])
        result = response.json()["data"]
        assert result["state"] == "succeeded", result
        assert result["result"]["diagnostics"]["reward"] == 1
        assert result["result"]["native_harbor_reward"] == result["result"]["diagnostics"]["reward"]
        assert result["result"]["mock_execution"] and not result["result"]["model_performance"]
        assert (
            result["result"]["observable_trajectory"] and result["result"]["generated_revision_id"]
        )
        run = data["clients"]["admin-1"].get(BASE + "/workspace/runs/" + member["check"]["id"])
        assert run.status_code == 200, run.text
        assert "PRIVATE-GOLDEN" not in run.text
    with transaction(cli.PROJECT, USERS["admin-1"]) as c:
        ledger = one(
            c,
            "SELECT * FROM anvil.evaluation_spend_windows WHERE id=(SELECT window_id FROM anvil.workspace_execution_groups WHERE id=%s)",
            (group["id"],),
        )
        assert ledger["reserved_micro_usd"] == 10000000
    monkeypatch.setattr(workspace_dispatch, "execute", original)
    return {
        "models": 2,
        "repetitions": 3,
        "trials": 6,
        "requests": len(requests),
        "model_performance": False,
    }
