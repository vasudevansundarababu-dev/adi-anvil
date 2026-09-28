"""Network-free marketing acceptance in a separate retained database, never live authority."""

import json
from urllib.parse import urlsplit

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import sql
from test_api_security import USERS, client_factory  # noqa: F401

from anvil import cli, marketing_runtime, providers, worker
from anvil.config import ROOT, setting
from anvil.db import one, transaction, uid
from anvil.marketing_authority import PRICING


def test_marketing_workflow_and_durable_dispatch(client_factory, monkeypatch):  # noqa: F811
    target = "anvil_marketingtest_" + uid().replace("-", "")[:12]
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(target)))
    for key in ("MIGRATION_DATABASE_URL", "DATABASE_URL", "WORKER_DATABASE_URL"):
        monkeypatch.setenv(key, urlsplit(setting(key))._replace(path="/" + target).geturl())
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), autocommit=True) as c:
        c.execute("CREATE SCHEMA anvil")
        command.upgrade(Config(str(ROOT / "services/backend/alembic.ini")), "head")
        command.upgrade(Config(str(ROOT / "services/backend/alembic.ini")), "head")
        c.execute("SET search_path TO anvil_checkpoints")
        PostgresSaver(c).setup()
        c.execute(
            "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA anvil_checkpoints TO anvil_worker"
        )
        c.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA anvil_checkpoints TO anvil_worker")
    cli.seed()
    project = cli.PROJECT
    base = f"/api/v1/projects/{project}"
    clients = {name: client_factory(name)[0] for name in USERS}

    def get(path, name="researcher"):
        response = clients[name].get(base + path)
        assert response.status_code == 200, response.text
        return response.json()["data"]

    def post(name, path, body=None, version=None, expected=200):
        response = clients[name].post(
            base + path,
            json=body or {},
            headers={"Idempotency-Key": uid(), **({"If-Match": str(version)} if version else {})},
        )
        assert response.status_code == expected, response.text
        return response.json().get("data")

    def submit(collection, row, author, reviews):
        row = post(author, f"/{collection}/{row['id']}/submit", version=row["row_version"])
        for reviewer, purpose in reviews:
            row = post(
                reviewer,
                f"/{collection}/{row['id']}/decisions",
                {
                    "purpose": purpose,
                    "decision": "approve",
                    "rationale": "Isolated synthetic software test only; not real scientific or paid authority.",
                },
                row["row_version"],
            )
        return row

    objective = post(
        "researcher",
        "/objectives",
        {
            "title": "MOCK marketing runtime acceptance",
            "origin": "adi_initiated",
            "entry_type": "capability",
            "hypothesis": "A bounded interactive episode preserves accounting.",
            "business_context": "Synthetic software testing only",
            "measurement_plan": "Validate thirteen responses and canonical state isolation; no model performance claim.",
            "researcher_id": USERS["researcher"],
            "advisor_id": USERS["advisor"],
            "product_owner_id": USERS["product-owner"],
        },
        expected=201,
    )
    objective = submit(
        "objectives",
        objective,
        "researcher",
        [("researcher", "research"), ("advisor", "advisor"), ("product-owner", "scope")],
    )
    body = {
        "case_ids": ["MKT-LH-001"],
        "reviewer_id": USERS["reviewer-1"],
        "advisor_id": USERS["advisor"],
    }
    source = post("data-engineer", "/fixtures/import", body)[0]
    assert post("data-engineer", "/fixtures/import", body)[0]["id"] == source["id"]
    for operation, destination in [
        ("managed_evaluation", "local_fixture"),
        ("external_processing", "openai"),
    ]:
        source = get("/cases/" + source["id"])
        post(
            "product-owner",
            f"/cases/{source['id']}/rights",
            {
                "operation": operation,
                "destination": destination,
                "status": "approved",
                "evidence": "Original fictional task; isolated MOCK transport qualification only.",
            },
            source["row_version"],
        )
    rubric = submit(
        "rubrics",
        get("/rubrics")[0],
        "data-engineer",
        [("reviewer-1", "content"), ("advisor", "calibration")],
    )
    task = submit(
        "tasks",
        get("/tasks")[0],
        "data-engineer",
        [("reviewer-1", "content"), ("advisor", "research")],
    )
    task = post("data-engineer", f"/tasks/{task['id']}/publish", version=task["row_version"])
    suite = post(
        "researcher",
        "/suites",
        {
            "title": "MOCK one marketing episode",
            "objective_revision_id": objective["current_revision_id"],
            "task_revision_ids": [task["current_revision_id"]],
            "selection_method": "Exact registered synthetic marketing task",
            "exposure_note": "Development task; not a protected benchmark",
            "advisor_id": USERS["advisor"],
            "planned_source_count": 1,
        },
        expected=201,
    )
    suite = submit("suites", suite, "researcher", [("advisor", "technical")])
    suite = post("researcher", f"/suites/{suite['id']}/freeze", version=suite["row_version"])
    connection = post(
        "admin-1",
        "/providers/openai/config",
        {
            "model_id": "gpt-6-sol",
            "max_output_tokens": 8192,
            "pricing_revision": PRICING,
            "bound_micro_usd": 1000000,
            "processing_terms_reviewed": True,
        },
    )
    protocol = post(
        "researcher",
        "/protocols",
        {
            "title": "MOCK thirteen-response protocol",
            "objective_revision_id": objective["current_revision_id"],
            "suite_revision_id": suite["current_revision_id"],
            "candidates": ["openai-marketing"],
            "reviewer_ids": [USERS["reviewer-1"], USERS["reviewer-2"]],
            "adjudicator_id": USERS["adjudicator"],
            "advisor_id": USERS["advisor"],
            "max_output_tokens": 8192,
            "episode_timeout_seconds": 600,
            "comparison_policy": "Isolated mock transport; no real model performance claim",
            "pass_policy": "Independent rubric reviews with evidence",
            "mode": "marketing_interactive_v1",
            "connection_id": connection["id"],
            "connection_hash": connection["content_hash"],
        },
        expected=201,
    )
    protocol = submit("protocols", protocol, "researcher", [("advisor", "technical")])

    def prepare():
        return post(
            "researcher",
            "/runs",
            {"protocol_revision_id": protocol["current_revision_id"]},
            expected=201,
        )

    run = prepare()
    ready = get(f"/runs/{run['id']}/marketing")["readiness"]
    assert not ready["ready"] and "two_real_admin_run_approvals" in ready["missing_gates"]
    post("researcher", f"/runs/{run['id']}/launch", version=run["row_version"], expected=409)
    post(
        "admin-1",
        f"/runs/{run['id']}/paid-approvals",
        {
            "purpose": "paid_scope",
            "subject_hash": ready["subject_hash"],
            "cap_micro_usd": 100000000,
            "authority_reference": "Synthetic identities must never activate live calls",
            "expires_at": "2026-10-04T00:00:00Z",
        },
        expected=403,
    )
    assert clients["outsider"].get(base + f"/runs/{run['id']}/marketing").status_code == 404
    assert clients["reviewer-1"].get(base + f"/runs/{run['id']}/marketing").status_code == 403
    with transaction(project, USERS["researcher"]) as c:
        assert not one(c, "SELECT 1 FROM anvil.interactive_calls")
        assert not one(c, "SELECT 1 FROM anvil.provider_approvals")

    # Isolated database + injected transport only. No approvals inserted, no secrets/network.
    monkeypatch.setattr(marketing_runtime, "require_ready", lambda c, run: {"ready": True})
    seen = []

    def mock_response(request):
        context = json.loads(
            request.actor_text.split("CURRENT OBSERVABLE CONTEXT\n")[1].split("\n\nReturn only")[0]
        )
        week = context["observation"]["week"]
        assert '"due"' not in request.actor_text and '"close_bps"' not in request.actor_text
        assert "Operator-only" not in request.actor_text
        if week < 8:
            assert "Webinar platform unavailable this week" not in request.actor_text
        seen.append(week)
        if week == 13:
            obj = {
                "board_memo": "MOCK memo with reconciled evidence; synthetic pipeline test only.",
                "ledger": [
                    {
                        "week": w,
                        "spend_usd": dict.fromkeys(("search", "social", "webinar", "email"), 0),
                        **dict.fromkeys(
                            (
                                "creative_cost_usd",
                                "leads",
                                "accepted_qualified_leads",
                                "new_customers",
                                "cumulative_customers",
                                "remaining_budget_usd",
                                "pending_qualified_leads",
                            ),
                            0,
                        ),
                    }
                    for w in range(1, 13)
                ],
            }
        else:
            obj = {
                "action": {
                    "week": week,
                    "spend_usd": {"search": 3000, "social": 0, "webinar": 0, "email": 0},
                    "message": "visibility",
                    "refresh_creative": False,
                    "rationale": "MOCK action; observe delayed conversions.",
                },
                "strategy": "MOCK plan for a bounded development test." if week == 1 else None,
                "creative": {
                    "headlines": ["See owners", "See due dates", "Export workflows"],
                    "landing_page": "Shared workflow boards with due-date reminders.",
                }
                if week in (1, 5, 9)
                else None,
                "decision_log": "MOCK decision log grounded in the current observation.",
            }
        return providers.Result(
            "completed",
            json.dumps(obj),
            model_returned="MOCK-NOT-A-MODEL",
            usage={"input_tokens": 100, "output_tokens": 100},
        )

    monkeypatch.setattr(providers, "execute_marketing", mock_response)

    def launch_job(row):
        post("researcher", f"/runs/{row['id']}/launch", version=row["row_version"])
        with transaction(project, USERS["researcher"]) as c:
            episode = one(c, "SELECT * FROM anvil.episodes WHERE run_id=%s", (row["id"],))
            job = one(
                c,
                "UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds' WHERE target_id=%s RETURNING *",
                (episode["id"],),
            )
            return episode, job

    episode, job = launch_job(run)
    with transaction(project, USERS["researcher"]) as c:
        c.execute("UPDATE anvil.jobs SET status='queued' WHERE id=%s", (job["id"],))
    assert worker.tick()
    with transaction(project, USERS["researcher"]) as c:
        job = one(c, "SELECT * FROM anvil.jobs WHERE id=%s", (job["id"],))
    assert seen == list(range(1, 14))
    detail = get(f"/runs/{run['id']}/marketing")
    assert detail["episode"]["step"] == 14
    assert detail["episode"]["state"] == "awaiting_review"
    assert detail["budget"]["reserved_micro_usd"] == 13000000
    assert "environment_state" not in detail["episode"]
    # Reclaimed job after checkpoint is durable must not re-invoke any response.
    with transaction(project, USERS["researcher"]) as c:
        c.execute(
            "UPDATE anvil.jobs SET status='leased',lease_until=now()+interval '60 seconds' WHERE id=%s",
            (job["id"],),
        )
    marketing_runtime.process(job)
    assert len(seen) == 13
    review = get(f"/reviews/{episode['id']}", "reviewer-1")
    assert "MOCK-NOT-A-MODEL" not in review["output"]
    assert len(json.loads(review["output"])["responses"]) == 13
    with transaction(project, worker=True) as c:
        assert not one(c, "SELECT 1 FROM anvil.artifacts WHERE classification='hidden_reference'")
        assert not one(
            c, "SELECT 1 FROM anvil.revisions WHERE id=%s", (rubric["current_revision_id"],)
        )
    for reviewer in ("reviewer-1", "reviewer-2"):
        current = get(f"/reviews/{episode['id']}", reviewer)
        criteria = [row["id"] for row in current["rubric"]["criteria"]]
        post(
            reviewer,
            f"/episodes/{episode['id']}/assessments",
            {
                "scores": dict.fromkeys(criteria, 2),
                "critical": [],
                "evidence": dict.fromkeys(criteria, "MOCK"),
                "rationale": "Isolated mocked output, exercising independent review and durable resume only.",
            },
            current["row_version"],
        )
    with transaction(project, USERS["researcher"]) as c:
        review_job = one(
            c,
            "UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds' WHERE target_id=%s AND kind='resume' RETURNING *",
            (episode["id"],),
        )
    marketing_runtime.process(review_job)
    assert get(f"/runs/{run['id']}")["state"] == "reviewed"
    assert len(seen) == 13

    # Crash immediately after committed dispatch intent: no second provider request.
    second = prepare()
    episode2, job2 = launch_job(second)

    def crash(_):
        raise RuntimeError("simulated_process_loss_after_intent")

    monkeypatch.setattr(providers, "execute_marketing", crash)
    try:
        marketing_runtime.advance(job2)
    except RuntimeError:
        pass
    monkeypatch.setattr(providers, "execute_marketing", mock_response)
    assert marketing_runtime.advance(job2) is False
    assert len(seen) == 13
    second_detail = get(f"/runs/{second['id']}/marketing")
    assert second_detail["episode"]["state"] == "execution_unknown"
    assert second_detail["budget"]["reserved_micro_usd"] == 1000000
    third = prepare()
    episode3, job3 = launch_job(third)
    parse = marketing_runtime.parse_response

    def crash_after_capture(*_):
        raise SystemExit("simulated_process_exit_after_capture")

    monkeypatch.setattr(marketing_runtime, "parse_response", crash_after_capture)
    with pytest.raises(SystemExit):
        marketing_runtime.advance(job3)
    assert len(seen) == 14
    monkeypatch.setattr(marketing_runtime, "parse_response", parse)
    assert marketing_runtime.advance(job3) is True
    assert len(seen) == 14
    with transaction(project, USERS["researcher"]) as c:
        state = one(
            c, "SELECT step FROM anvil.interactive_sessions WHERE episode_id=%s", (episode3["id"],)
        )
        assert state["step"] == 2
        with pytest.raises(psycopg.errors.RaiseException):
            with c.transaction():
                c.execute(
                    "UPDATE anvil.interactive_sessions SET harness_version='changed' WHERE episode_id=%s",
                    (episode3["id"],),
                )
        c.execute("UPDATE anvil.jobs SET lease_token=gen_random_uuid() WHERE id=%s", (job3["id"],))
    with pytest.raises(RuntimeError, match="lease_lost"):
        marketing_runtime.advance(job3)
    assert len(seen) == 14
    evidence = ROOT / "artifacts/test-runs/marketing-mock.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        json.dumps(
            {
                "database": target,
                "mode": "isolated_mock_not_model_performance",
                "completed_responses": 13,
                "independent_review_resume": "passed",
                "dispatch_intent_recovery": "unknown_without_retry",
                "captured_response_recovery": "applied_once_without_retry",
                "stale_lease": "denied",
                "provider_network_calls": 0,
                "real_paid_approvals_created": 0,
                "schema_version": 16,
            },
            indent=2,
        )
        + "\n"
    )
    print("Retained isolated MOCK marketing database:", target)
