"""Paid-admission contracts in fresh isolated databases; no external provider dispatch.

New contract identities simulate real flags only in those databases. Existing seeded
identities are never promoted. All provider requests use explicit MockTransport.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from urllib.parse import urlsplit

import httpx
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from test_api_security import USERS
from test_praxis_harbor import BASE, approve, imported
from test_workspace_adapter_contracts import response_body

from anvil import cli, harbor_agents, workspace_secrets
from anvil import workspace_execution as execution
from anvil.config import ROOT, setting
from anvil.db import one, transaction, uid


@pytest.fixture
def configured(client_factory, monkeypatch, tmp_path, request):
    target = "anvil_workspaceexec_" + uid().replace("-", "")[:12]
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(target)))
    for name in ("MIGRATION_DATABASE_URL", "DATABASE_URL", "WORKER_DATABASE_URL"):
        monkeypatch.setenv(name, urlsplit(setting(name))._replace(path="/" + target).geturl())
    with psycopg.connect(setting("MIGRATION_DATABASE_URL")) as c:
        c.execute("CREATE SCHEMA anvil")
    command.upgrade(Config(str(ROOT / "services/backend/alembic.ini")), "head")
    command.upgrade(Config(str(ROOT / "services/backend/alembic.ini")), "head")
    cli.seed()
    monkeypatch.setattr(workspace_secrets, "ROOT", tmp_path)
    monkeypatch.setattr(workspace_secrets, "CLOUD", False)
    monkeypatch.setattr(execution, "harbor_live_enabled", lambda: True)
    # Only fresh test identities in this retained isolated database have real flags.
    names = {
        "contract-admin-a": "admin",
        "contract-admin-b": "admin",
        "contract-engineer": "rl-engineer",
    }
    with psycopg.connect(setting("MIGRATION_DATABASE_URL")) as c:
        for name, role in names.items():
            identifier = uid()
            monkeypatch.setitem(USERS, name, identifier)
            c.execute(
                "INSERT INTO anvil.users(id,org_id,issuer,subject,name,is_synthetic) VALUES(%s,%s,%s,%s,%s,false)",
                (
                    identifier,
                    cli.ORG,
                    "https://isolated-contract.invalid",
                    identifier,
                    "Isolated contract " + name,
                ),
            )
            c.execute(
                "INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,%s)",
                (cli.PROJECT, identifier, role),
            )
            if role == "admin":
                c.execute(
                    "INSERT INTO anvil.project_assignments(project_id,user_id,capability) VALUES(%s,%s,'rights_reviewer')",
                    (cli.PROJECT, identifier),
                )
    clients = {
        name: client_factory(name)[0]
        for name in [*names, "admin-1", "researcher", "advisor", "outsider"]
    }
    admin = clients["admin-1"]
    managed_costs = getattr(request, "param", None) == "managed-costs"
    researcher, po, _, source, package = imported(
        client_factory,
        fixture="synthetic-marketing.task.json"
        if managed_costs
        else getattr(request, "param", "synthetic-marketing.task.json"),
    )
    approve(po, package)
    path = BASE + "/workspace"

    def post(endpoint, body=None, *, client=admin, expected=200, key=None):
        response = client.post(
            path + endpoint, json=body, headers={"Idempotency-Key": key or uid()}
        )
        assert response.status_code == expected, response.text
        return response.json().get("data")

    expiry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    framework = post("/frameworks", {"name": "Contract pinned runner", "framework": "harbor"})
    models = []
    credentials = []
    for provider in ("openai", "anthropic", "gemini"):
        credential = post(
            "/credentials",
            {
                "name": "Contract key " + provider,
                "provider": provider,
                "secret": "test-only-not-live-" + provider + "-" + uid(),
            },
        )
        credentials.append(credential)
        models.append(
            post(
                "/models",
                {
                    "name": "Contract " + provider,
                    "provider": provider,
                    "model_id": "gpt-6-luna"
                    if managed_costs and provider == "openai"
                    else "test-model",
                    "max_output_tokens": 1024,
                    "credential_id": credential["id"],
                    "processing_terms_reference": None
                    if managed_costs
                    else "https://contract.invalid/terms",
                    "pricing": None
                    if managed_costs and provider == "openai"
                    else {
                        "reference": "contract-rates-v1",
                        "source_url": "https://contract.invalid/rates",
                        "input_micro_usd_per_million_tokens": 1000000,
                        "output_micro_usd_per_million_tokens": 1000000,
                        "expires_at": expiry,
                    },
                },
            )
        )
    preset = post(
        "/presets",
        {
            "name": "Exact contract models",
            "runner_profile_id": framework["id"],
            "candidate_runtime": "anvil-structured-json-v1",
            "model_profile_ids": [m["id"] for m in models],
        },
    )
    prep = post(
        "/preparations",
        {
            "preset_id": preset["id"],
            "package_id": package["id"],
            "model_profile_ids": [m["id"] for m in models],
            "max_output_tokens": 1024,
            "episode_timeout_seconds": 300,
            "aggregate_cap_micro_usd": 1000000,
        },
    )
    group = post("/execution-groups", {"preparation_id": prep["id"]})
    policy = {"reference": "harbor:admin-run-" + group["id"], "expires_at": expiry}

    def approvals(group=group):
        return post(
            "/execution-groups/" + group["id"] + "/authorize",
            {
                "subject_hash": group["subject_hash"],
                "aggregate_cap_micro_usd": 1000000,
                "rights_confirmed": True,
            },
        )

    if not managed_costs:
        approvals()
    return {
        "post": post,
        "clients": clients,
        "group": group,
        "prep": prep,
        "policy": policy,
        "models": models,
        "credentials": credentials,
        "approvals": approvals,
        "path": path,
        "database": target,
    }


def test_atomic_group_reservation_sequential_claim_and_all_native_mediators(configured):
    data = configured
    post = data["post"]
    gid = data["group"]["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = [
            pool.submit(
                post,
                "/execution-groups/" + gid + "/launch",
                key="concurrent-" + str(index),
                client=data["clients"][name],
            )
            for index, name in enumerate(("contract-admin-a", "contract-admin-b"))
        ]
        results = [attempt.result() for attempt in attempts]
    launched = results[0]
    assert results[1]["models"] == launched["models"]
    assert launched["state"] == "launched" and len(launched["models"]) == 3
    replay = post("/execution-groups/" + gid + "/launch", key="different-idempotency-key")
    assert [m["check"]["id"] for m in replay["models"]] == [
        m["check"]["id"] for m in launched["models"]
    ]
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        window = one(
            c,
            "SELECT * FROM anvil.evaluation_spend_windows WHERE authority_reference=%s",
            (data["policy"]["reference"],),
        )
        assert window["reserved_micro_usd"] == 1000000
    observed = []
    for member in launched["models"]:
        with transaction(worker=True) as c:
            job = one(c, "SELECT * FROM anvil.claim_harbor_job()")
            assert str(job["target_id"]) == member["check"]["id"]
            assert one(c, "SELECT * FROM anvil.claim_harbor_job()") is None
        with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
            c.execute(
                "UPDATE anvil.harbor_checks SET state='running',invocation_count=1 WHERE id=%s",
                (member["check"]["id"],),
            )
        provider = member["model"]["provider"]

        def handle(req):
            observed.append(req)
            body = req.content.decode()
            assert (
                "PRIVATE-NORTHSTAR" not in body
                and "reference_output" not in body
                and '"reference_output"' not in body
            )
            return httpx.Response(
                200, json=response_body(provider, '{"decision":"unrepaired-output"}')
            )

        output = execution.decision(
            cli.PROJECT,
            USERS["contract-admin-a"],
            member["plan_id"],
            0,
            transport=httpx.MockTransport(handle),
        )
        assert json.loads(output) == {"decision": "unrepaired-output"}
        assert (
            execution.decision(
                cli.PROJECT,
                USERS["contract-admin-a"],
                member["plan_id"],
                0,
                transport=httpx.MockTransport(lambda r: pytest.fail("duplicate request")),
            )
            == output
        )
        with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
            c.execute(
                "UPDATE anvil.harbor_checks SET state='succeeded',finished_at=now() WHERE id=%s",
                (member["check"]["id"],),
            )
            c.execute("UPDATE anvil.jobs SET status='succeeded' WHERE id=%s", (job["id"],))
    assert len(observed) == 3
    result = (
        data["clients"]["contract-admin-a"]
        .get(data["path"] + "/execution-groups/" + gid)
        .json()["data"]
    )
    assert result["status"] == "succeeded" and result["reservation_retained"]
    run = (
        data["clients"]["contract-admin-a"]
        .get(BASE + "/workspace/runs/" + launched["models"][0]["check"]["id"])
        .json()["data"]
    )
    assert run["model"] == "test-model" and run["execution_group_id"] == gid
    assert run["metrics"]["known_cost_micro_usd"] == 15
    assert run["origin"] == "native_sdk_mock_verification"
    assert (
        run["calls"][0]["actor_context"]
        and run["calls"][0]["output_text"] == '{"decision":"unrepaired-output"}'
    )
    assert "reference_output" not in json.dumps(run) and "PRIVATE-NORTHSTAR" not in json.dumps(run)


def test_authority_changed_during_reservation_does_not_reserve(configured, monkeypatch):
    data = configured
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        original = execution.authority(c, execution.group(c, data["group"]["id"]))
    changed = original.model_copy(update={"reference": "harbor:different-unapproved-contract"})
    calls = []

    def read(*args):
        calls.append(1)
        return original if len(calls) == 1 else changed

    monkeypatch.setattr(execution, "authority", read)
    data["post"]("/execution-groups/" + data["group"]["id"] + "/launch", expected=409)
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        assert one(c, "SELECT count(*) n FROM anvil.evaluation_spend_windows")["n"] == 0


def test_worker_result_capture_fences_project_before_check_to_avoid_cancel_deadlock(
    configured, monkeypatch
):
    from anvil import harbor_worker

    data = configured
    gid = data["group"]["id"]
    launched = data["post"]("/execution-groups/" + gid + "/launch")
    first = launched["models"][0]
    with transaction(worker=True) as c:
        job = one(c, "SELECT * FROM anvil.claim_harbor_job()")
    entered = Event()
    original = harbor_worker.project_fence

    def observed(c, project):
        entered.set()
        return original(c, project)

    monkeypatch.setattr(harbor_worker, "project_fence", observed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        # Simulate an idempotent cancellation command already holding project FOR UPDATE.
        with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
            c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (cli.PROJECT,))
            future = pool.submit(
                harbor_worker.finish,
                job,
                USERS["contract-admin-a"],
                "failed",
                error="synthetic_fence_test",
                live=True,
            )
            assert entered.wait(5)
            assert not future.done()
            # Result capture must not hold check while waiting for that project fence.
            assert one(
                c,
                "SELECT id FROM anvil.harbor_checks WHERE id=%s FOR UPDATE NOWAIT",
                (first["check"]["id"],),
            )
        future.result(timeout=5)
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        audit = one(
            c,
            "SELECT metadata FROM anvil.audit_events WHERE target_id=%s AND action='harbor.check_failed'",
            (first["check"]["id"],),
        )
        assert audit["metadata"]["origin"] == "provider_dispatch_attempt_unverified"


def test_review_revocation_after_mock_dispatch_still_captures_usage(configured):
    data = configured
    gid = data["group"]["id"]
    launched = data["post"]("/execution-groups/" + gid + "/launch")
    first = launched["models"][0]
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        c.execute(
            "UPDATE anvil.harbor_checks SET state='running',invocation_count=1 WHERE id=%s",
            (first["check"]["id"],),
        )

    def handler(req):
        data["post"](
            "/execution-groups/" + gid + "/revoke-authorization",
            {"rationale": "Revoke after mock request was dispatched."},
            client=data["clients"]["contract-admin-a"],
        )
        return httpx.Response(200, json=response_body("openai", "{}"))

    execution.decision(
        cli.PROJECT,
        USERS["contract-admin-a"],
        first["plan_id"],
        0,
        transport=httpx.MockTransport(handler),
    )
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        call = one(
            c,
            "SELECT status,actual_micro_usd FROM anvil.harbor_agent_calls WHERE plan_id=%s",
            (first["plan_id"],),
        )
        assert call == {"status": "completed", "actual_micro_usd": 15}
        assert not execution.plan_readiness(c, harbor_agents.plan(c, first["plan_id"]))["ready"]


def test_cancelled_leased_job_with_revoked_rights_preserves_terminal_evidence(
    configured, monkeypatch
):
    from anvil import harbor_worker, workspace_dispatch

    data = configured
    gid = data["group"]["id"]
    launched = data["post"]("/execution-groups/" + gid + "/launch")
    first = launched["models"][0]
    with transaction(worker=True) as c:
        job = one(c, "SELECT * FROM anvil.claim_harbor_job()")
    data["post"]("/execution-groups/" + gid + "/cancel")
    data["post"](
        "/execution-groups/" + gid + "/revoke-authorization",
        {"rationale": "Contract cancellation and review revocation before start."},
        client=data["clients"]["contract-admin-a"],
    )
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        before = one(c, "SELECT * FROM anvil.harbor_checks WHERE id=%s", (first["check"]["id"],))
    monkeypatch.setattr(
        workspace_dispatch,
        "execute",
        lambda *args, **kwargs: pytest.fail("No broker invocation after cancellation"),
    )
    monkeypatch.setattr(
        harbor_worker,
        "argv",
        lambda *args, **kwargs: pytest.fail("No Harbor invocation after cancellation"),
    )
    harbor_worker.process(job)
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        assert (
            one(c, "SELECT * FROM anvil.harbor_checks WHERE id=%s", (first["check"]["id"],))
            == before
        )
        assert (
            one(c, "SELECT status FROM anvil.jobs WHERE id=%s", (job["id"],))["status"]
            == "cancelled"
        )
        assert one(c, "SELECT count(*) n FROM anvil.harbor_agent_calls")["n"] == 0
    with transaction(worker=True) as c:
        assert one(c, "SELECT * FROM anvil.claim_harbor_job()") is None
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with transaction(cli.PROJECT, worker=True) as c:
            c.execute("SELECT result FROM anvil.harbor_checks LIMIT 1")


@pytest.mark.parametrize("configured", ["synthetic-marketing-staged.task.json"], indirect=True)
def test_real_harbor_gateway_with_mocked_provider_has_observable_result_not_model_performance(
    configured, monkeypatch
):
    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Opt-in Docker Harbor gateway test; provider remains MockTransport")
    from anvil import harbor_worker, workspace_dispatch

    data = configured
    gid = data["group"]["id"]
    launched = data["post"]("/execution-groups/" + gid + "/launch")
    original = workspace_dispatch.execute
    requests = []

    def mocked(binding, secret, request, **kwargs):
        def handle(req):
            requests.append(req)
            # Scripted software fixture, never an actual model-performance result.
            text = (
                "{}"
                if "FUTURE-NORTHSTAR" in request.actor_text
                else '{"channel":"search","spend_usd":1000,"evidence_id":"ev-channel-costs"}'
            )
            return httpx.Response(200, json=response_body(binding["provider"], text))

        return original(binding, secret, request, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(workspace_dispatch, "execute", mocked)
    for member in launched["models"]:
        with transaction(worker=True) as c:
            job = one(c, "SELECT * FROM anvil.claim_harbor_job()")
            assert str(job["target_id"]) == member["check"]["id"]
        harbor_worker.process(job)
        response = data["clients"]["contract-admin-a"].get(
            BASE + "/harbor-checks/" + member["check"]["id"]
        )
        check = response.json()["data"]
        assert check["state"] == "succeeded", check
        assert check["result"]["model_performance"] is False
        assert check["result"]["origin"] == "native_sdk_mock_verification"
        assert check["result"]["diagnostics"]["reward"] == 0
        run = (
            data["clients"]["contract-admin-a"]
            .get(BASE + "/workspace/runs/" + member["check"]["id"])
            .json()["data"]
        )
        assert (
            run["evidence"]
            and run["model"] == "test-model"
            and run["origin"] == "native_sdk_mock_verification"
        )
        assert len(run["calls"]) == 2
        assert "FUTURE-NORTHSTAR" not in run["calls"][0]["actor_context"]
        assert "FUTURE-NORTHSTAR" in run["calls"][1]["actor_context"]
        assert "PRIVATE-NORTHSTAR" not in json.dumps(run)
    assert len(requests) == 6


@pytest.mark.parametrize(
    "outcome", ["timeout", "cancel", "rotation", "revoke", "individual_cancel"]
)
def test_uncertainty_cancellation_and_revocation_stop_remaining_models_and_retain_cap(
    configured, outcome
):
    data = configured
    post = data["post"]
    gid = data["group"]["id"]
    launched = post("/execution-groups/" + gid + "/launch")
    first = launched["models"][0]
    if outcome in ("cancel", "individual_cancel"):
        if outcome == "cancel":
            cancelled = post("/execution-groups/" + gid + "/cancel")
            assert cancelled["status"] == "cancelled"
        else:
            with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
                c.execute(
                    "UPDATE anvil.harbor_checks SET state='cancelled',cancel_requested=true WHERE id=%s",
                    (first["check"]["id"],),
                )
                c.execute(
                    "UPDATE anvil.jobs SET status='cancelled' WHERE target_id=%s",
                    (first["check"]["id"],),
                )
            assert (
                data["clients"]["contract-admin-a"]
                .get(data["path"] + "/execution-groups/" + gid)
                .json()["data"]["status"]
                == "blocked"
            )
    else:
        with transaction(worker=True) as c:
            assert one(c, "SELECT * FROM anvil.claim_harbor_job()")
        with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
            c.execute(
                "UPDATE anvil.harbor_checks SET state='running',invocation_count=1 WHERE id=%s",
                (first["check"]["id"],),
            )
        if outcome == "rotation":
            post(
                "/credentials/" + data["credentials"][0]["id"] + "/versions",
                {"secret": "test-only-rotated-" + uid()},
            )
        if outcome == "revoke":
            post(
                "/execution-groups/" + gid + "/revoke-authorization",
                {"rationale": "Contract revocation before dispatch."},
                client=data["clients"]["contract-admin-a"],
            )
        calls = []

        def handle(req):
            calls.append(req)
            raise httpx.ReadTimeout("synthetic timeout", request=req)

        with pytest.raises(RuntimeError):
            execution.decision(
                cli.PROJECT,
                USERS["contract-admin-a"],
                first["plan_id"],
                0,
                transport=httpx.MockTransport(handle),
            )
        assert len(calls) == int(outcome == "timeout")
        if outcome == "timeout":
            with pytest.raises(RuntimeError, match="unknown_no_retry"):
                execution.decision(
                    cli.PROJECT,
                    USERS["contract-admin-a"],
                    first["plan_id"],
                    0,
                    transport=httpx.MockTransport(lambda req: pytest.fail("retry")),
                )
            with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
                c.execute(
                    "UPDATE anvil.harbor_checks SET state='execution_unknown',finished_at=now() WHERE id=%s",
                    (first["check"]["id"],),
                )
            run = (
                data["clients"]["contract-admin-a"]
                .get(BASE + "/workspace/runs/" + first["check"]["id"])
                .json()["data"]
            )
            assert run["origin"] == "native_sdk_mock_verification"
            assert run["calls"][0]["output_text"] is None
            assert run["calls"][0]["usage"]["error_code"] == "ambiguous_dispatch"
    with transaction(worker=True) as c:
        assert one(c, "SELECT * FROM anvil.claim_harbor_job()") is None
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        assert (
            one(
                c,
                "SELECT reserved_micro_usd FROM anvil.evaluation_spend_windows WHERE authority_reference=%s",
                (data["policy"]["reference"],),
            )["reserved_micro_usd"]
            == 1000000
        )


def test_unknown_response_retains_safe_reconciliation_metadata_without_retry(configured):
    data = configured
    launched = data["post"]("/execution-groups/" + data["group"]["id"] + "/launch")
    first = launched["models"][0]
    with transaction(worker=True) as c:
        assert one(c, "SELECT * FROM anvil.claim_harbor_job()")
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        c.execute(
            "UPDATE anvil.harbor_checks SET state='running',invocation_count=1 WHERE id=%s",
            (first["check"]["id"],),
        )
    calls = []

    def handle(req):
        calls.append(req)
        body = response_body("openai", '{"untrusted":"PRIVATE-OUTPUT"}')
        body.update(
            id="resp_reconciliation",
            model="different-exact-model",
            usage={
                "input_tokens": 10,
                "output_tokens": 2,
                "total_tokens": 12,
                "input_tokens_details": {
                    "cached_tokens": 0,
                    "cache_write_tokens": 2,
                    "cache_write_tokens_details": {"ttl_30m_tokens": 2, "ttl_12h_tokens": 0},
                },
            },
        )
        return httpx.Response(200, json=body)

    with pytest.raises(RuntimeError, match="unknown_no_retry"):
        execution.decision(
            cli.PROJECT,
            USERS["contract-admin-a"],
            first["plan_id"],
            0,
            transport=httpx.MockTransport(handle),
        )
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        row = one(c, "SELECT * FROM anvil.harbor_agent_calls WHERE plan_id=%s", (first["plan_id"],))
        assert row["status"] == "execution_unknown" and row["actual_micro_usd"] is None
        assert row["reserved_micro_usd"] > 0 and row["request_id"] == "resp_reconciliation"
        evidence = row["usage"]["provider_evidence"]
        assert evidence["model_returned"] == "different-exact-model"
        assert evidence["token_usage"]["input_tokens"] == 10
        assert "PRIVATE-OUTPUT" not in json.dumps(row["usage"])
        assert row["output_json"] is None
    with pytest.raises(RuntimeError, match="unknown_no_retry"):
        execution.decision(
            cli.PROJECT,
            USERS["contract-admin-a"],
            first["plan_id"],
            0,
            transport=httpx.MockTransport(lambda req: pytest.fail("retry")),
        )
    assert len(calls) == 1


@pytest.mark.parametrize("revocation", ["user", "membership", "admin_role"])
def test_existing_admin_authority_requires_current_active_project_admin(configured, revocation):
    data = configured
    launched = data["post"]("/execution-groups/" + data["group"]["id"] + "/launch")
    first = launched["models"][0]
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        c.execute(
            "UPDATE anvil.harbor_checks SET state='running',invocation_count=1 WHERE id=%s",
            (first["check"]["id"],),
        )
    with psycopg.connect(setting("MIGRATION_DATABASE_URL")) as c:
        if revocation == "user":
            c.execute("UPDATE anvil.users SET active=false WHERE id=%s", (USERS["admin-1"],))
        elif revocation == "membership":
            c.execute(
                "UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s AND active",
                (cli.PROJECT, USERS["admin-1"]),
            )
        else:
            c.execute(
                "UPDATE anvil.memberships SET role='rl-engineer' WHERE project_id=%s AND user_id=%s AND active",
                (cli.PROJECT, USERS["admin-1"]),
            )
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        row = execution.group(c, data["group"]["id"])
        assert execution.authority(c, row) is None
        assert "admin_run_authorization_required" in execution.readiness(c, row)["missing"]
    with pytest.raises(RuntimeError, match="admission_revoked"):
        execution.decision(
            cli.PROJECT,
            USERS["contract-admin-a"],
            first["plan_id"],
            0,
            transport=httpx.MockTransport(
                lambda req: pytest.fail("Revoked Admin must not dispatch")
            ),
        )


def test_existing_admin_and_exact_budget_boundaries(configured):
    data = configured
    post = data["post"]
    gid = data["group"]["id"]
    assert (
        data["clients"]["advisor"].get(data["path"] + "/execution-groups/" + gid).status_code == 200
    )
    assert data["clients"]["outsider"].get(
        data["path"] + "/execution-groups/" + gid
    ).status_code in (403, 404)
    second = post("/execution-groups", {"preparation_id": data["prep"]["id"]})
    body = {
        "subject_hash": second["subject_hash"],
        "aggregate_cap_micro_usd": 1000000,
        "rights_confirmed": True,
    }
    for name in ("contract-engineer",):
        post(
            "/execution-groups/" + second["id"] + "/launch",
            body,
            client=data["clients"][name],
            expected=403,
        )
    post(
        "/execution-groups/" + second["id"] + "/launch",
        {**body, "aggregate_cap_micro_usd": 2000000},
        expected=409,
    )
    post(
        "/execution-groups/" + second["id"] + "/launch",
        {**body, "rights_confirmed": False},
        expected=409,
    )
    launched = post(
        "/execution-groups/" + second["id"] + "/launch", body, client=data["clients"]["admin-1"]
    )
    assert launched["state"] == "launched"
    with transaction(cli.PROJECT, USERS["contract-admin-a"]) as c:
        assert (
            one(c, "SELECT is_synthetic FROM anvil.users WHERE id=%s", (USERS["admin-1"],))[
                "is_synthetic"
            ]
            is True
        )
        authorization = one(
            c,
            "SELECT admin_id FROM anvil.workspace_admin_run_authorizations WHERE group_id=%s",
            (second["id"],),
        )
        assert str(authorization["admin_id"]) == USERS["admin-1"]
        event = one(
            c,
            "SELECT metadata FROM anvil.audit_events WHERE action='workspace.admin_run_authorized' AND target_id=%s ORDER BY occurred_at DESC LIMIT 1",
            (second["id"],),
        )
        assert event["metadata"]["authorization_policy"] == "active-project-admin-v2"
        assert event["metadata"]["actor_seeded_origin"] is True
        assert one(c, "SELECT count(*) n FROM anvil.harbor_agent_reviews")["n"] == 0
        assert one(c, "SELECT count(*) n FROM anvil.provider_approvals")["n"] == 0
        assert (
            one(
                c,
                "SELECT count(*) n FROM anvil.workspace_admin_run_authorizations WHERE group_id=%s",
                (second["id"],),
            )["n"]
            == 1
        )
