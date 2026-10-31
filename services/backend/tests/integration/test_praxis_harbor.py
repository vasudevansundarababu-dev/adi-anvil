import hashlib
import json

import pytest

from anvil import harbor_worker
from anvil.cli import OUTSIDER_PROJECT, PROJECT
from anvil.config import ROOT
from anvil.db import one, transaction, uid

BASE = f"/api/v1/projects/{PROJECT}"


def imported(
    client_factory, fixture="synthetic-marketing.task.json", exact_payload=None, base=BASE
):
    client, _ = client_factory("researcher")
    po, _ = client_factory("product-owner")
    raw = json.loads((ROOT / "contracts/praxis" / fixture).read_text())
    raw["task_id"] += "-" + uid()[:8]
    payload = exact_payload if exact_payload is not None else json.dumps(raw, indent=2)
    response = client.post(
        base + "/praxis-sources", json={"payload": payload}, headers={"Idempotency-Key": uid()}
    )
    assert response.status_code == 200, response.text
    source = response.json()["data"]
    from anvil.praxis_export import parse_export

    exact_source, _ = parse_export(payload.encode())
    assert source["source_sha256"] == hashlib.sha256(exact_source).hexdigest()
    assert "PRIVATE-NORTHSTAR" not in response.text
    response = client.post(
        base + f"/praxis-sources/{source['id']}/build", headers={"Idempotency-Key": uid()}
    )
    assert response.status_code == 200, response.text
    return client, po, payload, source, response.json()["data"]


def approve(po, package, base=BASE):
    response = po.post(
        base + f"/harbor-packages/{package['id']}/approve",
        json={
            "package_sha256": package["package_sha256"],
            "scope": "synthetic_software_checks_only",
            "rationale": "Synthetic software test approval by test identity; not human rights clearance.",
        },
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 200, response.text


def test_import_immutable_idempotent_authorized_isolated(client_factory):
    client, po, payload, source, package = imported(client_factory)
    replay = client.post(
        BASE + "/praxis-sources", json={"payload": payload}, headers={"Idempotency-Key": uid()}
    )
    assert replay.status_code == 200 and replay.json()["data"]["id"] == source["id"]
    changed = client.post(
        BASE + "/praxis-sources",
        json={"payload": payload + "\n"},
        headers={"Idempotency-Key": uid()},
    )
    assert changed.status_code == 409
    denied = client.post(
        BASE + f"/harbor-packages/{package['id']}/checks",
        json={"candidate": "reference"},
        headers={"Idempotency-Key": uid()},
    )
    assert denied.status_code == 409
    denied = client.post(
        BASE + f"/harbor-packages/{package['id']}/approve",
        json={
            "package_sha256": package["package_sha256"],
            "scope": "synthetic_software_checks_only",
            "rationale": "Cannot approve as researcher",
        },
    )
    assert denied.status_code == 403
    foreign = client.get(f"/api/v1/projects/{OUTSIDER_PROJECT}/harbor-packages/{package['id']}")
    assert foreign.status_code in (403, 404)
    approve(po, package)
    key = uid()
    path = BASE + f"/harbor-packages/{package['id']}/checks"
    first = client.post(path, json={"candidate": "reference"}, headers={"Idempotency-Key": key})
    second = client.post(path, json={"candidate": "reference"}, headers={"Idempotency-Key": key})
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    hid = first.json()["data"]["id"]
    response = client.post(
        BASE + f"/harbor-checks/{hid}/cancel", headers={"Idempotency-Key": uid()}
    )
    assert response.status_code == 200 and response.json()["data"]["state"] == "cancelled"
    with transaction(PROJECT, worker=True) as c:
        with pytest.raises(Exception):
            c.execute("SELECT manifest FROM anvil.harbor_packages").fetchall()


def test_unsupported_binding_and_paid_agent_fail_closed(client_factory):
    client, _ = client_factory("researcher")
    raw = json.loads((ROOT / "contracts/praxis/synthetic-marketing.task.json").read_text())
    raw["environment"]["binding"] = "shell-anything"
    response = client.post(
        BASE + "/praxis-sources",
        json={"payload": json.dumps(raw)},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 422
    assert (
        client.post(
            BASE + f"/harbor-packages/{uid()}/checks", json={"candidate": "claude-code"}
        ).status_code
        == 422
    )


def test_recovery_never_redispatches(client_factory):
    client, po, _, _, package = imported(client_factory)
    approve(po, package)
    response = client.post(
        BASE + f"/harbor-packages/{package['id']}/checks",
        json={"candidate": "reference"},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 200, response.text
    hid = response.json()["data"]["id"]
    from test_api_security import USERS

    with transaction(PROJECT, USERS["researcher"]) as c:
        c.execute(
            "UPDATE anvil.harbor_checks SET state='running',invocation_count=1 WHERE id=%s", (hid,)
        )
        job = one(
            c,
            "UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds' WHERE target_id=%s RETURNING *",
            (hid,),
        )
    harbor_worker.process(job)
    response = client.get(BASE + f"/harbor-checks/{hid}")
    assert response.json()["data"]["state"] == "execution_unknown"
    assert response.json()["data"]["invocation_count"] == 1


@pytest.mark.parametrize(
    "candidate,expected", [("reference", 1.0), ("empty_output", 0.0), ("constraint_failure", 0.0)]
)
@pytest.mark.parametrize(
    "fixture", ["synthetic-marketing.task.json", "synthetic-marketing-staged.task.json"]
)
def test_real_harbor_software_check(client_factory, candidate, expected, fixture):
    import os

    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Opt-in real Docker Harbor test; not a model test")
    client, po, _, _, package = imported(client_factory, fixture)
    approve(po, package)
    response = client.post(
        BASE + f"/harbor-packages/{package['id']}/checks",
        json={"candidate": candidate},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 200, response.text
    hid = response.json()["data"]["id"]
    from test_api_security import USERS

    with transaction(PROJECT, USERS["researcher"]) as c:
        job = one(
            c,
            "UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds' WHERE target_id=%s RETURNING *",
            (hid,),
        )
    harbor_worker.process(job)
    response = client.get(BASE + f"/harbor-checks/{hid}")
    data = response.json()["data"]
    assert data["state"] == "succeeded", data
    assert data["result"]["diagnostics"]["reward"] == expected
    assert data["invocation_count"] == 1
    assert data["result"]["model_performance"] is False
    diagnostic = data["result"]["diagnostics"]
    if candidate == "constraint_failure":
        if fixture == "synthetic-marketing.task.json":
            assert diagnostic["diagnostic_score"] == 1
            assert diagnostic["hard_failures"] == ["rule-budget"]
        else:
            assert diagnostic["completed_stages"] == 2
            assert diagnostic["stages"][-1]["hard_failures"] == ["s2-rule-budget"]
            assert "final_task_diagnostics" in diagnostic["stages"][-1]
    if fixture == "synthetic-marketing-staged.task.json":
        assert diagnostic["completed_stages"] == (1 if candidate == "empty_output" else 2)
        if candidate == "reference":
            assert diagnostic["stages"][-1]["state_snapshot"]["committed_spend"] == 1000
            assert diagnostic["stages"][-1]["state_snapshot"]["final_spend"] == 600


@pytest.mark.parametrize("candidate,expected", [("reference", 1), ("constraint_failure", 0)])
def test_actual_praxis_api_export(client_factory, candidate, expected):
    import os
    from pathlib import Path

    source_path = os.environ.get("ANVIL_PRAXIS_EXPORT_PATH")
    if not source_path or os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Actual Praxis API export and Docker opt-in required")
    payload = Path(source_path).read_text()
    client, po, _, source, package = imported(client_factory, exact_payload=payload)
    approve(po, package)
    response = client.post(
        BASE + f"/harbor-packages/{package['id']}/checks",
        json={"candidate": candidate},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 200, response.text
    hid = response.json()["data"]["id"]
    from test_api_security import USERS

    with transaction(PROJECT, USERS["researcher"]) as c:
        job = one(
            c,
            "UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds' WHERE target_id=%s RETURNING *",
            (hid,),
        )
    harbor_worker.process(job)
    result = client.get(BASE + f"/harbor-checks/{hid}").json()["data"]
    assert result["state"] == "succeeded", result
    assert result["result"]["diagnostics"]["reward"] == expected
    evidence = {
        "verification": "actual_Praxis_API_export_with_automated_test_identities",
        "source_sha256": source["source_sha256"],
        "source_id": source["id"],
        "package_id": package["id"],
        "package_sha256": package["package_sha256"],
        "check_id": hid,
        "result": result["result"],
        "human_approval": False,
        "candidate": candidate,
    }
    (
        ROOT
        / "artifacts/test-runs"
        / ("praxis-harbor-" + source["source_sha256"][:12] + "-" + candidate + ".json")
    ).write_text(json.dumps(evidence, indent=2, default=str))


def test_real_staged_actor_cannot_tamper_or_read_future(tmp_path):
    import os
    import subprocess

    from anvil.harbor_package import compile_package, unpack

    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Real Docker isolation probe is opt-in")
    _, _, archive = compile_package(
        (ROOT / "contracts/praxis/synthetic-marketing-staged.task.json").read_bytes()
    )
    task_dir = tmp_path / "task"
    unpack(archive, task_dir, hashlib.sha256(archive).hexdigest())
    solve = task_dir / "steps/step-01/solution/solve.sh"
    original = solve.read_text()
    # Test-only execution overlay; not a published package or a candidate performance result.
    probe = """#!/bin/sh
set -eu
python3 - <<'ANVIL_ISOLATION_PROBE'
import os
from pathlib import Path
assert os.getuid() == 10001
state = Path('/workspace/state.json')
try:
    state.write_text('{"committed_spend":999999}')
except PermissionError:
    pass
else:
    raise AssertionError('Actor modified authoritative state')
for root in ('/workspace','/solution','/tests'):
    for path in Path(root).rglob('*'):
        if path.is_file():
            data = path.read_bytes()
            assert ('FUTURE-'+'NORTHSTAR-482').encode() not in data
            assert ('PRIVATE-'+'NORTHSTAR-739').encode() not in data
print('actor_uid_and_state_and_future_isolation_passed')
ANVIL_ISOLATION_PROBE
"""
    solve.write_text(probe + original)
    env = harbor_worker.child_environment(tmp_path)
    executable = ROOT / ".local/harbor-venv/bin/harbor"
    command = harbor_worker.argv(executable, task_dir, tmp_path / "results", "reference")
    completed = subprocess.run(command, env=env, capture_output=True, timeout=300)
    assert completed.returncode == 0
    trials = [p for p in (tmp_path / "results").rglob("result.json") if p.parent.name != "check"]
    assert len(trials) == 1
    trial = json.loads(trials[0].read_text())
    assert trial["exception_info"] is None
    assert trial["verifier_result"]["rewards"]["reward"] == 1
    assert len(trial["step_results"]) == 2
    assert "actor_uid_and_state_and_future_isolation_passed" in "".join(
        p.read_text() for p in (tmp_path / "results").rglob("oracle.txt")
    )


def test_real_staged_reset_replay(client_factory):
    import os

    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Real Docker replay is opt-in")
    from test_api_security import USERS

    client, po, _, _, package = imported(client_factory, "synthetic-marketing-staged.task.json")
    approve(po, package)
    runs = []
    for _ in range(2):
        response = client.post(
            BASE + f"/harbor-packages/{package['id']}/checks",
            json={"candidate": "reference"},
            headers={"Idempotency-Key": uid()},
        )
        assert response.status_code == 200, response.text
        hid = response.json()["data"]["id"]
        with transaction(PROJECT, USERS["researcher"]) as c:
            job = one(
                c,
                "UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds' WHERE target_id=%s RETURNING *",
                (hid,),
            )
        harbor_worker.process(job)
        row = client.get(BASE + f"/harbor-checks/{hid}").json()["data"]
        assert row["state"] == "succeeded", row
        runs.append(row)
    assert runs[0]["id"] != runs[1]["id"]
    assert runs[0]["result"]["diagnostics"] == runs[1]["result"]["diagnostics"]
    assert runs[0]["result"]["package_sha256"] == runs[1]["result"]["package_sha256"]
    assert all(r["invocation_count"] == 1 for r in runs)
    with pytest.raises(Exception, match="immutable Harbor execution binding"):
        with transaction(PROJECT, USERS["researcher"]) as c:
            c.execute(
                "UPDATE anvil.harbor_checks SET candidate='empty_output' WHERE id=%s",
                (runs[0]["id"],),
            )


def test_real_running_cancel_cleans_owned_sandbox(client_factory):
    import os
    import threading
    import time

    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Real Docker cancellation is opt-in")
    from test_api_security import USERS

    client, po, _, _, package = imported(client_factory, "synthetic-marketing-staged.task.json")
    approve(po, package)
    response = client.post(
        BASE + f"/harbor-packages/{package['id']}/checks",
        json={"candidate": "reference"},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 200, response.text
    hid = response.json()["data"]["id"]
    with transaction(PROJECT, USERS["researcher"]) as c:
        job = one(
            c,
            "UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds' WHERE target_id=%s RETURNING *",
            (hid,),
        )
    errors = []

    def dispatch():
        try:
            harbor_worker.process(job)
        except Exception as exc:
            errors.append(type(exc).__name__)

    thread = threading.Thread(target=dispatch)
    thread.start()
    for _ in range(100):
        row = client.get(BASE + f"/harbor-checks/{hid}").json()["data"]
        if row["state"] == "running":
            break
        time.sleep(0.1)
    assert row["state"] == "running", row
    response = client.post(
        BASE + f"/harbor-checks/{hid}/cancel", headers={"Idempotency-Key": uid()}
    )
    assert response.status_code == 200
    thread.join(timeout=45)
    assert not thread.is_alive() and not errors
    row = client.get(BASE + f"/harbor-checks/{hid}").json()["data"]
    assert row["state"] == "cancelled", row
    assert row["invocation_count"] == 1


def test_agent_plan_pins_model_and_blocks_unapproved_dispatch(client_factory, monkeypatch):
    client, po, _, _, package = imported(client_factory)
    admin, _ = client_factory("admin-1")
    response = admin.post(
        BASE + "/providers/openai/config",
        json={"model_id": "synthetic-model-for-adapter-test", "max_output_tokens": 2048},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 200, response.text
    connection = response.json()["data"]["id"]
    body = {
        "connection_id": connection,
        "agent": "anvil-structured-json-v1",
        "model": "synthetic-model-for-adapter-test",
        "max_total_micro_usd": 1000000,
        "trials": 1,
    }
    response = client.post(
        BASE + f"/harbor-packages/{package['id']}/agent-plans",
        json=body,
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 200, response.text
    record = response.json()["data"]
    assert record["ready"] is False
    assert (
        "exact_user_provider_model_budget_and_current_pricing_authority" in record["missing_gates"]
    )
    assert record["config"]["max_calls"] == 1
    assert record["config"]["max_output_tokens"] == 2048
    from anvil import config

    monkeypatch.setattr(config, "CLOUD", True)
    monkeypatch.setenv("ANVIL_LIVE_PROVIDERS_ENABLED", "false")
    for enabled in ("false", "true"):
        monkeypatch.setenv("ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", enabled)
        current = client.get(BASE + f"/harbor-agent-plans/{record['id']}").json()["data"]
        assert not current["ready"]
        assert ("live_dispatch_disabled_in_runtime" in current["missing_gates"]) == (
            enabled == "false"
        )
        assert (
            "exact_user_provider_model_budget_and_current_pricing_authority"
            in current["missing_gates"]
        )
        denied = client.post(
            BASE + f"/harbor-agent-plans/{record['id']}/launch",
            json={},
            headers={"Idempotency-Key": uid()},
        )
        assert denied.status_code == 409
    monkeypatch.setenv("ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", "false")
    response = client.post(
        BASE + f"/harbor-agent-plans/{record['id']}/launch",
        json={},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 409, response.text
    assert "no inference dispatched" in response.text
    response = client.post(
        BASE + f"/harbor-packages/{package['id']}/agent-plans",
        json={**body, "model": "different-model"},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 422
    second = client.post(
        BASE + f"/harbor-packages/{package['id']}/agent-plans",
        json=body,
        headers={"Idempotency-Key": uid()},
    ).json()["data"]
    assert second["subject_hash"] != record["subject_hash"]
    assert client.get(
        f"/api/v1/projects/{OUTSIDER_PROJECT}/harbor-agent-plans/{record['id']}"
    ).status_code in (403, 404)
    response = admin.post(
        BASE + f"/harbor-agent-plans/{record['id']}/admin-approvals",
        json={
            "purpose": "paid_scope",
            "subject_hash": record["subject_hash"],
            "authority_reference": "synthetic-not-authority",
            "expires_at": "2099-01-01T00:00:00Z",
        },
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 403


def test_real_harbor_agent_with_explicit_stub_gateway(tmp_path, monkeypatch):
    import os
    import subprocess

    from anvil import harbor_agents
    from anvil.harbor_package import compile_package, unpack

    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Real Harbor adapter with fixture-only gateway is opt-in")
    _, _, archive = compile_package(
        (ROOT / "contracts/praxis/synthetic-marketing-staged.task.json").read_bytes()
    )
    task_dir = tmp_path / "task"
    unpack(archive, task_dir, hashlib.sha256(archive).hexdigest())
    # Independent predetermined candidate fixture, never read from the task's reference.
    fixture_outputs = [
        {"channel": "search", "spend_usd": 1000, "evidence_id": "ev-channel-costs"},
        {
            "channel": "search",
            "spend_usd": 600,
            "evidence_id": "ev-budget-update",
            "prior_spend_usd": 1000,
        },
    ]
    observed = []

    def stub(project, user, plan_id, stage_index):
        assert stage_index == len(observed)
        observed.append(stage_index)
        return fixture_outputs[stage_index]

    monkeypatch.setattr(harbor_agents, "decision", stub)
    gateway = harbor_agents.Gateway(PROJECT, "synthetic-test-user", uid())
    try:
        env = harbor_worker.child_environment(tmp_path)
        env.update(
            {
                "PYTHONPATH": str(ROOT / "services/harbor/src"),
                "ANVIL_HARBOR_GATEWAY_SOCKET": gateway.path,
                "ANVIL_HARBOR_GATEWAY_TOKEN": gateway.token,
            }
        )
        completed = subprocess.run(
            harbor_worker.argv(
                ROOT / ".local/harbor-venv/bin/harbor",
                task_dir,
                tmp_path / "results",
                "agent",
                "synthetic-fixture-not-a-model",
            ),
            env=env,
            capture_output=True,
            timeout=300,
        )
        assert completed.returncode == 0
        trials = [
            p for p in (tmp_path / "results").rglob("result.json") if p.parent.name != "check"
        ]
        assert len(trials) == 1
        trial = json.loads(trials[0].read_text())
        assert trial["exception_info"] is None, trial["exception_info"]
        assert trial["verifier_result"]["rewards"]["reward"] == 1
        assert observed == [0, 1]
    finally:
        gateway.close()


def test_mediated_ledger_stub_holds_global_cap_and_never_retries(
    client_factory, monkeypatch, capsys
):
    from test_api_security import USERS

    from anvil import harbor_agents, providers
    from anvil.operations import new_demo

    new_demo("Synthetic Harbor ledger contract test — no model or human approvals")
    project = json.loads(capsys.readouterr().out)["project_id"]
    base = f"/api/v1/projects/{project}"
    client, po, _, _, package = imported(
        client_factory, "synthetic-marketing-staged.task.json", base=base
    )
    approve(po, package, base)
    admin, _ = client_factory("admin-1")
    connection = admin.post(
        base + "/providers/openai/config",
        json={"model_id": "synthetic-ledger-stub", "max_output_tokens": 2048},
        headers={"Idempotency-Key": uid()},
    ).json()["data"]["id"]
    policy = harbor_agents.Authority.model_validate(
        {
            "reference": "harbor:synthetic-ledger-" + uid(),
            "project_id": project,
            "provider": "openai",
            "model": "synthetic-ledger-stub",
            "total_cap_micro_usd": 1000000,
            "input_micro_usd_per_million_tokens": 2000000,
            "output_micro_usd_per_million_tokens": 8000000,
            "pricing_revision": "synthetic-pricing-not-real",
            "expires_at": "2099-01-01T00:00:00Z",
            "pricing_expires_at": "2099-01-01T00:00:00Z",
        }
    )
    # Explicit test admission seam; creates no provider/rights approval records and makes no SDK call.
    monkeypatch.setattr(harbor_agents, "authority", lambda: policy)
    monkeypatch.setattr(
        harbor_agents, "readiness", lambda c, r: {"ready": True, "missing_gates": []}
    )

    def create():
        response = client.post(
            base + f"/harbor-packages/{package['id']}/agent-plans",
            json={
                "connection_id": connection,
                "agent": "anvil-structured-json-v1",
                "model": "synthetic-ledger-stub",
                "max_total_micro_usd": 1000000,
                "trials": 1,
            },
            headers={"Idempotency-Key": uid()},
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]["id"]

    pid = create()
    response = client.post(
        base + f"/harbor-agent-plans/{pid}/launch", json={}, headers={"Idempotency-Key": uid()}
    )
    assert response.status_code == 200, response.text
    hid = response.json()["data"]["check_id"]
    with transaction(project, USERS["researcher"]) as c:
        c.execute(
            "UPDATE anvil.harbor_checks SET state='running',invocation_count=1 WHERE id=%s", (hid,)
        )
        c.execute(
            "UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds' WHERE target_id=%s",
            (hid,),
        )
    blocked = client.post(
        base + f"/harbor-agent-plans/{create()}/launch", json={}, headers={"Idempotency-Key": uid()}
    )
    assert blocked.status_code == 409 and "ceiling" in blocked.text
    observed = []
    first = '{"channel":"search","spend_usd":1000,"evidence_id":"ev-channel-costs"}'

    def transport(model, prompt):
        observed.append(prompt)
        if len(observed) == 2:
            raise RuntimeError("Synthetic ambiguous transport, not a real provider call")
        return providers.Result(
            "completed",
            text=first,
            model_returned=model,
            request_id="synthetic-stub-only",
            usage={"input_tokens": 20, "output_tokens": 10},
        )

    assert harbor_agents.decision(project, USERS["researcher"], pid, 0, transport) == first
    assert harbor_agents.decision(project, USERS["researcher"], pid, 0, transport) == first
    assert len(observed) == 1
    with pytest.raises(RuntimeError, match="unknown_no_retry"):
        harbor_agents.decision(project, USERS["researcher"], pid, 1, transport)
    with pytest.raises(RuntimeError, match="unknown_no_retry"):
        harbor_agents.decision(project, USERS["researcher"], pid, 1, transport)
    assert len(observed) == 2
    assert "FUTURE-NORTHSTAR" not in observed[0] and "FUTURE-NORTHSTAR" in observed[1]
    assert all("PRIVATE-NORTHSTAR" not in p and "reference_output" not in p for p in observed)
    with transaction(project, USERS["researcher"]) as c:
        calls = c.execute(
            "SELECT * FROM anvil.harbor_agent_calls WHERE plan_id=%s ORDER BY stage_index", (pid,)
        ).fetchall()
        assert [r["status"] for r in calls] == ["completed", "execution_unknown"]
        assert calls[0]["actual_micro_usd"] == 120
        window = one(
            c,
            "SELECT reserved_micro_usd,settled_micro_usd FROM anvil.evaluation_spend_windows WHERE authority_reference=%s",
            (policy.reference,),
        )
        assert window == {"reserved_micro_usd": 1000000, "settled_micro_usd": 0}
        assert c.execute("SELECT count(*) n FROM anvil.harbor_agent_reviews").fetchone()["n"] == 0
        c.execute(
            "UPDATE anvil.harbor_checks SET state='execution_unknown',error_code='synthetic_stub_mediation_test' WHERE id=%s",
            (hid,),
        )
        c.execute(
            "UPDATE anvil.jobs SET status='failed',error_code='synthetic_stub_mediation_test' WHERE target_id=%s",
            (hid,),
        )
