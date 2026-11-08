"""Independent real-SQL scheduler security contracts, NOT native qualification.

The fixture explicitly manufactures qualification metadata in a disposable lab.
No Docker/provider/judge is invoked; these rows must never be release evidence.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from fastapi import HTTPException
from test_benchmark_pipeline import queued_operation, review_and_build, sql_guard_artifact
from test_benchmark_pipeline import signed_lab as pipeline_lab
from test_private_storage import assign, connection
from test_private_storage import lab as storage_lab

from anvil import benchmark_execution as execution
from anvil import benchmark_scheduler as scheduler
from anvil import domain
from anvil.benchmark_evaluator_program import canonical, seal
from anvil.benchmark_pipeline import claim as qualification_claim
from anvil.benchmark_storage import bind_private, stage_private

lab = storage_lab
signed_lab = pipeline_lab


@pytest.fixture
def frozen(signed_lab, monkeypatch):
    case = signed_lab
    monkeypatch.setenv("ANVIL_BENCHMARK_OFFLINE_ENABLED", "true")
    build, _ = review_and_build(case)
    operation = queued_operation(case, build)
    assert qualification_claim(
        case["lab"]["project"], operation["operation_id"], case["lab"]["admin"]
    )
    _, report = sql_guard_artifact(case)
    with connection("anvil_app", case["lab"]["project"], case["lab"]["admin"]) as c:
        rows = c.execute(
            "SELECT t.*,p.package_sha256,b.dependencies FROM anvil.benchmark_build_tasks t JOIN anvil.harbor_packages p ON p.id=t.package_id JOIN anvil.benchmark_builds b ON b.id=t.build_id WHERE t.build_id=%s ORDER BY task_id",
            (build["build_id"],),
        ).fetchall()
        for row in rows:
            q = uuid4()
            c.execute(
                "INSERT INTO anvil.benchmark_qualifications(id,project_id,source_id,package_id,evaluator_binding_id,package_sha256,environment_digest,compiler_sha256,tool_schema_sha256,harbor_version,outcome,report_artifact_id,reviewed_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'0.25.0','passed',%s,%s)",
                (
                    q,
                    case["lab"]["project"],
                    row["source_id"],
                    row["package_id"],
                    build["evaluator_binding_id"],
                    row["package_sha256"],
                    row["environment_digest"],
                    row["dependencies"]["sources"][
                        "services/backend/src/anvil/benchmark_compiler.py"
                    ],
                    row["tool_schema_sha256"],
                    report,
                    case["lab"]["admin"],
                ),
            )
            c.execute(
                "INSERT INTO anvil.benchmark_operation_results(project_id,operation_id,build_id,task_id,source_id,package_id,qualification_id) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    case["lab"]["project"],
                    operation["operation_id"],
                    build["build_id"],
                    row["task_id"],
                    row["source_id"],
                    row["package_id"],
                    q,
                ),
            )
        c.execute(
            "UPDATE anvil.benchmark_qualification_operations SET state='passed',report_artifact_id=%s,finished_at=now() WHERE id=%s",
            (report, operation["operation_id"]),
        )
    response = case["admin"].post(
        case["base"] + "/builds/" + build["build_id"] + "/freeze",
        json={"expected_subject_sha256": build["subject_sha256"]},
    )
    assert response.status_code == 200, response.text
    version = response.json()["data"]
    workspace = case["base"].removesuffix("/benchmarks")
    runner = case["admin"].post(
        workspace + "/frameworks",
        json={"name": "Manufactured scheduler SQL fixture only", "framework": "harbor"},
    )
    assert runner.status_code == 200, runner.text
    models = []
    for provider in ("openai", "anthropic", "gemini"):
        result = case["admin"].post(
            workspace + "/models",
            headers={"idempotency-key": str(uuid4())},
            json={
                "name": "SQL fixture " + provider,
                "provider": provider,
                "model_id": "fictional-conformance",
                "max_output_tokens": 1024,
            },
        )
        assert result.status_code == 200, result.text
        models.append(result.json()["data"])
    # Declare only a fictional test review policy, with genuinely distinct lab
    # identities. This is not a Bodhium threshold or a human release approval.
    third = str(uuid4())
    with connection() as c:
        c.execute(
            "INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,'scheduler-fictional-fixture',%s,'Independent synthetic third reviewer')",
            (third, case["lab"]["org"], third),
        )
        c.execute(
            "INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,'rl-engineer')",
            (case["lab"]["project"], third),
        )
    case["lab"]["third"] = third
    assignments = [
        assign(case["lab"], who, scope="evaluation_review")
        for who in ("admin", "engineer", "third")
    ]
    body = {
        "benchmark_revision_id": version["benchmark_revision_id"],
        "expected_benchmark_sha256": version["subject_sha256"],
        "slots": [
            {
                "connection_id": m["id"],
                "configuration_sha256": m["config_hash"],
                "transport": "offline_contract",
            }
            for m in models
        ],
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "review_policy": {
            "tasks": [
                {
                    "task_revision_id": task["task_revision_id"],
                    "pass_threshold_percent": "50",
                    "critical_criterion_ids": [],
                }
                for task in version["tasks"]
            ],
            "calibration_sha256": version["calibration_sha256"],
            "first_assignment_id": assignments[0],
            "second_assignment_id": assignments[1],
            "adjudicator_assignment_id": assignments[2],
        },
    }
    response = case["admin"].post(
        case["base"] + "/protocols",
        json=body,
    )
    assert response.status_code == 200, response.text
    return {**case, "build": build, "protocol": response.json()["data"], "protocol_body": body}


def launch(case, key=None):
    return case["admin"].post(
        case["base"] + "/protocols/" + case["protocol"]["protocol_revision_id"] + "/launch",
        json={"expected_subject_sha256": case["protocol"]["subject_sha256"]},
        headers={"idempotency-key": key or str(uuid4())},
    )


def actor_connection(case):
    return connection("anvil_app", case["lab"]["project"], case["lab"]["admin"])


def test_exact_18_cell_admission_and_same_key_replay_are_atomic(frozen):
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, replay = list(pool.map(lambda _: launch(frozen, key), range(2)))
    assert first.status_code == replay.status_code == 200, first.text
    result = first.json()["data"]
    assert replay.json()["data"]["run_id"] == result["run_id"]
    assert len(result["cells"]) == 18
    with actor_connection(frozen) as c:
        for table, count in (
            ("benchmark_cells", 18),
            ("benchmark_offline_runtime", 18),
            ("benchmark_comparison_groups", 3),
            ("benchmark_spend_bindings", 2),
        ):
            assert (
                c.execute(
                    "SELECT count(*) AS n FROM anvil." + table + " WHERE run_id=%s",
                    (result["run_id"],),
                ).fetchone()["n"]
                == count
            )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_comparisons WHERE project_id=%s",
                (frozen["lab"]["project"],),
            ).fetchone()["n"]
            == 1
        )


def test_concurrent_claims_hold_at_most_three_distinct_provider_slots(frozen):
    result = launch(frozen)
    assert result.status_code == 200, result.text
    run = result.json()["data"]["run_id"]

    def claim():
        with actor_connection(frozen) as c:
            return scheduler.claim(c, frozen["lab"]["project"], run)

    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda _: claim(), range(6)))
    held = [row for row in claims if row is not None]
    assert len(held) == 3
    assert len({str(row["attempt_id"]) for row in held}) == 3
    with actor_connection(frozen) as c:
        rows = c.execute(
            "SELECT provider,slot FROM anvil.benchmark_capacity_claims WHERE run_id=%s AND state='held'",
            (run,),
        ).fetchall()
        assert len(rows) == 3 and len({row["provider"] for row in rows}) == 3


def test_stale_fence_and_cancel_before_intent_cannot_dispatch_or_requeue(frozen):
    response = launch(frozen)
    assert response.status_code == 200, response.text
    run = response.json()["data"]["run_id"]
    with actor_connection(frozen) as c:
        claim = scheduler.claim(c, frozen["lab"]["project"], run)
    with actor_connection(frozen) as c:
        with pytest.raises(HTTPException) as error:
            scheduler.current(
                c, frozen["lab"]["project"], run, claim["attempt_id"], uuid4(), {"claimed"}
            )
        assert error.value.status_code == 409
    with actor_connection(frozen) as c:
        execution.cancel(
            c,
            frozen["lab"]["project"],
            frozen["lab"]["admin"],
            run,
            frozen["protocol"]["subject_sha256"],
            "Manufactured local SQL cancellation test",
        )
    with actor_connection(frozen) as c:
        assert scheduler.claim(c, frozen["lab"]["project"], run) is None
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_offline_runtime WHERE run_id=%s AND state='cancelled'",
                (run,),
            ).fetchone()["n"]
            == 18
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_capacity_claims WHERE run_id=%s AND state<>'released'",
                (run,),
            ).fetchone()["n"]
            == 0
        )
        with pytest.raises(HTTPException) as error:
            scheduler.intent(c, frozen["lab"]["project"], claim)
        assert error.value.status_code == 409


def test_revoked_review_blocks_claim_without_side_effects(frozen):
    response = launch(frozen)
    assert response.status_code == 200, response.text
    run = response.json()["data"]["run_id"]
    with actor_connection(frozen) as c:
        c.execute(
            "INSERT INTO anvil.benchmark_review_revocations(id,project_id,review_id,target,actor_id,rationale) VALUES(%s,%s,%s,'review',%s,'Manufactured SQL review revocation test')",
            (
                uuid4(),
                frozen["lab"]["project"],
                frozen["build"]["review_id"],
                frozen["lab"]["admin"],
            ),
        )
    with actor_connection(frozen) as c:
        with pytest.raises(HTTPException) as error:
            scheduler.claim(c, frozen["lab"]["project"], run)
        assert error.value.status_code == 409
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_capacity_claims WHERE run_id=%s", (run,)
            ).fetchone()["n"]
            == 0
        )


def test_direct_sql_cannot_mark_uncaptured_output_completed(frozen):
    response = launch(frozen)
    assert response.status_code == 200, response.text
    run = response.json()["data"]["run_id"]
    with actor_connection(frozen) as c:
        claim = scheduler.claim(c, frozen["lab"]["project"], run)
    with actor_connection(frozen) as c:
        scheduler.intent(c, frozen["lab"]["project"], claim)
    with actor_connection(frozen) as c:
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute(
                "UPDATE anvil.benchmark_offline_runtime SET state='captured' WHERE attempt_id=%s",
                (claim["attempt_id"],),
            )


def test_late_admission_failure_rolls_back_all_parent_children_and_windows(frozen):
    class FailFifthCell:
        def __init__(self, connection):
            self.connection, self.cells = connection, 0

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def execute(self, statement, params=None):
            if statement.startswith("INSERT INTO anvil.benchmark_cells"):
                self.cells += 1
                if self.cells == 5:
                    raise RuntimeError("Injected local test failure after four actual cell inserts")
            return self.connection.execute(statement, params)

    with pytest.raises(RuntimeError, match="after four actual"):
        with actor_connection(frozen) as c:
            execution.admit_offline(
                FailFifthCell(c),
                frozen["lab"]["project"],
                frozen["lab"]["admin"],
                frozen["protocol"]["protocol_revision_id"],
                frozen["protocol"]["subject_sha256"],
            )
    with actor_connection(frozen) as c:
        for table in (
            "benchmark_comparisons",
            "benchmark_cells",
            "benchmark_offline_runtime",
            "benchmark_comparison_groups",
            "benchmark_spend_bindings",
            "evaluation_spend_windows",
            "workspace_execution_groups",
        ):
            assert (
                c.execute(
                    "SELECT count(*) AS n FROM anvil." + table + " WHERE project_id=%s",
                    (frozen["lab"]["project"],),
                ).fetchone()["n"]
                == 0
            )


@pytest.mark.parametrize("intent", [False, True])
def test_expired_claim_never_requeues_and_unknown_intent_retains_capacity(frozen, intent):
    response = launch(frozen)
    assert response.status_code == 200, response.text
    run = response.json()["data"]["run_id"]
    # Manufacture only an elapsed lease in the disposable SQL fixture. No clock,
    # permission or native runtime policy is changed to avoid waiting ten minutes.
    with actor_connection(frozen) as c:
        row = c.execute(
            "SELECT rt.*,cell.id cell_id,cell.slot FROM anvil.benchmark_offline_runtime rt JOIN anvil.benchmark_cell_attempts a ON a.id=rt.attempt_id JOIN anvil.benchmark_cells cell ON cell.id=a.cell_id WHERE rt.run_id=%s ORDER BY cell.slot,cell.id LIMIT 1",
            (run,),
        ).fetchone()
        c.execute(
            "UPDATE anvil.benchmark_offline_runtime SET state='claimed',lease_until=now()-interval '1 second' WHERE attempt_id=%s",
            (row["attempt_id"],),
        )
        c.execute(
            "INSERT INTO anvil.benchmark_capacity_claims(id,project_id,run_id,cell_id,attempt_id,provider,slot,fence,generation,lease_until,state) VALUES(%s,%s,%s,%s,%s,'openai',%s,%s,1,now()-interval '1 second','held')",
            (
                uuid4(),
                frozen["lab"]["project"],
                run,
                row["cell_id"],
                row["attempt_id"],
                row["slot"],
                row["fence"],
            ),
        )
        if intent:
            c.execute(
                "UPDATE anvil.benchmark_offline_runtime SET state='intent' WHERE attempt_id=%s",
                (row["attempt_id"],),
            )
    with actor_connection(frozen) as c:
        assert scheduler.expire(c, frozen["lab"]["project"], run) == 1
        observed = c.execute(
            "SELECT state FROM anvil.benchmark_offline_runtime WHERE attempt_id=%s",
            (row["attempt_id"],),
        ).fetchone()["state"]
        assert observed == ("dispatch_unknown" if intent else "operational_failed")
        capacity = c.execute(
            "SELECT state FROM anvil.benchmark_capacity_claims WHERE attempt_id=%s",
            (row["attempt_id"],),
        ).fetchone()["state"]
        assert capacity == ("dispatch_unknown" if intent else "released")
        with pytest.raises(psycopg.errors.RaiseException):
            with c.transaction():
                c.execute(
                    "UPDATE anvil.benchmark_capacity_claims SET state='held' WHERE attempt_id=%s",
                    (row["attempt_id"],),
                )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with c.transaction():
                c.execute(
                    "UPDATE anvil.benchmark_capacity_claims SET fence=%s WHERE attempt_id=%s",
                    (uuid4(), row["attempt_id"]),
                )
        assert scheduler.expire(c, frozen["lab"]["project"], run) == 0
        next_claim = scheduler.claim(c, frozen["lab"]["project"], run)
        assert next_claim is None or next_claim["attempt_id"] != row["attempt_id"]
        if intent and next_claim:
            assert next_claim["slot"] != row["slot"]


@pytest.mark.parametrize(
    "fault",
    [
        "missing_policy",
        "calibration",
        "task",
        "critical",
        "same_user",
        "revoked_assignment",
        "wrong_scope",
        "inactive_member",
        "expired",
    ],
)
def test_incomplete_or_stale_frozen_review_policy_cannot_create_protocol(frozen, fault):
    body = deepcopy(frozen["protocol_body"])
    if fault == "missing_policy":
        body.pop("review_policy")
    elif fault == "calibration":
        body["review_policy"]["calibration_sha256"] = "0" * 64
    elif fault == "task":
        body["review_policy"]["tasks"][0]["task_revision_id"] = str(uuid4())
    elif fault == "critical":
        body["review_policy"]["tasks"][0]["critical_criterion_ids"] = [
            "invented-critical-criterion"
        ]
    elif fault == "same_user":
        body["review_policy"]["second_assignment_id"] = assign(
            frozen["lab"], "admin", scope="evaluation_review"
        )
    elif fault == "revoked_assignment":
        with actor_connection(frozen) as c:
            c.execute(
                "INSERT INTO anvil.benchmark_private_revocations(project_id,assignment_id,revoked_by,rationale) VALUES(%s,%s,%s,'Explicit fictional reviewer duty revocation')",
                (
                    frozen["lab"]["project"],
                    body["review_policy"]["first_assignment_id"],
                    frozen["lab"]["admin"],
                ),
            )
    elif fault == "wrong_scope":
        body["review_policy"]["first_assignment_id"] = assign(
            frozen["lab"], "admin", scope="source_review"
        )
    elif fault == "inactive_member":
        with connection() as c:
            c.execute(
                "UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s",
                (frozen["lab"]["project"], frozen["lab"]["third"]),
            )
    elif fault == "expired":
        body["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with actor_connection(frozen) as c:
        before = c.execute(
            "SELECT count(*) AS n FROM anvil.revisions WHERE project_id=%s AND content->>'profile'='sme-comparison-v1'",
            (frozen["lab"]["project"],),
        ).fetchone()["n"]
    response = frozen["admin"].post(
        frozen["base"] + "/protocols", json=body, headers={"idempotency-key": str(uuid4())}
    )
    assert response.status_code == (404 if fault == "task" else 409), response.text
    with actor_connection(frozen) as c:
        after = c.execute(
            "SELECT count(*) AS n FROM anvil.revisions WHERE project_id=%s AND content->>'profile'='sme-comparison-v1'",
            (frozen["lab"]["project"],),
        ).fetchone()["n"]
        assert after == before


def test_generic_resource_api_cannot_forge_server_frozen_benchmark_protocol(frozen):
    generic = "/api/v1/projects/" + frozen["lab"]["project"] + "/protocols"
    body = deepcopy(frozen["protocol"]["protocol"])
    response = frozen["admin"].post(generic, json=body, headers={"idempotency-key": str(uuid4())})
    assert response.status_code == 422, response.text
    # Also manufacture an unreceipted raw revision in this disposable SQL lab.
    # It is not a legitimate API action or a qualification; downstream routes
    # must still refuse it even if another internal writer inserted its JSON.
    with actor_connection(frozen) as c:
        forged = domain.create(
            c, frozen["lab"]["project"], frozen["lab"]["admin"], "protocol", body
        )
    forged_id = forged["current_revision_id"]
    path = frozen["base"] + "/protocols/" + str(forged_id)
    assert frozen["admin"].get(path).status_code == 404
    launch_attempt = frozen["admin"].post(
        path + "/launch",
        json={"expected_subject_sha256": frozen["protocol"]["subject_sha256"]},
        headers={"idempotency-key": str(uuid4())},
    )
    assert launch_attempt.status_code == 404, launch_attempt.text
    with actor_connection(frozen) as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_comparisons WHERE project_id=%s",
                (frozen["lab"]["project"],),
            ).fetchone()["n"]
            == 0
        )


def test_static_catalog_remains_available_when_sme_benchmark_versions_exist(frozen):
    response = frozen["admin"].get("/api/v1/projects/" + frozen["lab"]["project"] + "/factory")
    assert response.status_code == 200, response.text
    assert isinstance(response.json()["data"], list)
    assert all(
        item.get("revision_id") != frozen["protocol"]["protocol"]["benchmark_revision_id"]
        for item in response.json()["data"]
    )


def manufactured_capture(case, creator="admin", files=None):
    """SQL custody fixture only; never invoke or claim a native evaluator."""
    response = launch(case)
    assert response.status_code == 200, response.text
    run = response.json()["data"]["run_id"]
    with actor_connection(case) as c:
        claimed = scheduler.claim(c, case["lab"]["project"], run)
    with actor_connection(case) as c:
        scheduler.intent(c, case["lab"]["project"], claimed)
    if files is None:
        files = {"answers.json": b"{}", "report.md": b"Manufactured SQL fixture, NOT native output"}
    output = stage_private(
        case["lab"]["project"],
        canonical(
            seal(files, sorted({"answers.json", "report.md"} - set(files)), task_id="SQL-ONLY")
        ),
        "benchmark_sealed",
    )
    report = stage_private(
        case["lab"]["project"],
        b"Manufactured SQL custody metadata, NOT native evidence",
        "benchmark_trace",
    )
    job = uuid4()
    with connection("anvil_app", case["lab"]["project"], case["lab"][creator]) as c:
        output_id = bind_private(c, output, created_by=case["lab"][creator])
        report_id = bind_private(c, report, created_by=case["lab"][creator])
        c.execute(
            "UPDATE anvil.benchmark_offline_runtime SET state='captured',output_artifact_id=%s,report_artifact_id=%s,duration_ms=1 WHERE attempt_id=%s",
            (output_id, report_id, claimed["attempt_id"]),
        )
        task = c.execute(
            "SELECT qualification_id FROM anvil.benchmark_version_tasks WHERE task_revision_id=%s",
            (claimed["task_revision_id"],),
        ).fetchone()
        q = c.execute(
            "SELECT evaluator_binding_id FROM anvil.benchmark_qualifications WHERE id=%s",
            (task["qualification_id"],),
        ).fetchone()
        c.execute(
            "INSERT INTO anvil.benchmark_evaluator_jobs(id,project_id,binding_id,sealed_output_artifact_id,created_by,state) VALUES(%s,%s,%s,%s,%s,'queued')",
            (
                job,
                case["lab"]["project"],
                q["evaluator_binding_id"],
                output_id,
                case["lab"][creator],
            ),
        )
        c.execute(
            "INSERT INTO anvil.benchmark_native_evaluator_custody(project_id,attempt_id,job_id,fence,output_sha256,report_sha256) VALUES(%s,%s,%s,%s,%s,%s)",
            (
                case["lab"]["project"],
                claimed["attempt_id"],
                job,
                claimed["fence"],
                output.sha256,
                report.sha256,
            ),
        )
    return {
        "claim": claimed,
        "job": job,
        "qualification": task["qualification_id"],
        "output": output.sha256,
        "report": report.sha256,
        "manifest_artifact_id": output_id,
        "report_artifact_id": report_id,
        "files": files,
    }


def finish(c, case, capture, *, fence=None, output=None, report=None):
    return c.execute(
        "SELECT anvil.finish_native_benchmark_capture(%s,%s,%s,%s,%s) AS job",
        (
            case["lab"]["project"],
            capture["claim"]["attempt_id"],
            fence or capture["claim"]["fence"],
            output or capture["output"],
            report or capture["report"],
        ),
    ).fetchone()["job"]


def test_native_completion_is_not_public_or_app_callable_and_definer_owner_is_not_caller(frozen):
    capture = manufactured_capture(frozen)
    signature = "anvil.finish_native_benchmark_capture(uuid,uuid,uuid,text,text)"
    with connection() as c:
        assert (
            c.execute(
                "SELECT has_function_privilege('anvil_app',%s,'EXECUTE') AS ok", (signature,)
            ).fetchone()["ok"]
            is False
        )
        assert (
            c.execute(
                "SELECT has_function_privilege('anvil_benchmark_evaluator',%s,'EXECUTE') AS ok",
                (signature,),
            ).fetchone()["ok"]
            is True
        )
        assert (
            c.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) acl WHERE p.oid=%s::regprocedure AND acl.grantee=0 AND acl.privilege_type='EXECUTE') AS ok",
                (signature,),
            ).fetchone()["ok"]
            is False
        )
    with actor_connection(frozen) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            finish(c, frozen, capture)
    internal = "anvil.finish_native_benchmark_capture_bound(uuid,uuid,uuid,text,text)"
    with connection() as c:
        assert (
            c.execute(
                "SELECT has_function_privilege('anvil_benchmark_evaluator',%s,'EXECUTE') AS ok",
                (internal,),
            ).fetchone()["ok"]
            is False
        )
        assert (
            c.execute(
                "SELECT has_function_privilege('anvil_app',%s,'EXECUTE') AS ok", (internal,)
            ).fetchone()["ok"]
            is False
        )
    with connection(
        "anvil_benchmark_evaluator", frozen["lab"]["project"], frozen["lab"]["admin"]
    ) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(
                "SELECT anvil.finish_native_benchmark_capture_bound(%s,%s,%s,%s,%s)",
                (
                    frozen["lab"]["project"],
                    capture["claim"]["attempt_id"],
                    capture["claim"]["fence"],
                    capture["output"],
                    capture["report"],
                ),
            )
    with connection(project=frozen["lab"]["project"], user=frozen["lab"]["admin"]) as c:
        assert finish(c, frozen, capture) is None
        assert (
            c.execute(
                "SELECT state FROM anvil.benchmark_evaluator_jobs WHERE id=%s", (capture["job"],)
            ).fetchone()["state"]
            == "queued"
        )


def test_downgraded_operator_cannot_finish_through_retained_evaluation_duty(frozen):
    capture = manufactured_capture(frozen, creator="engineer")
    with connection() as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            with c.transaction():
                c.execute(
                    "UPDATE anvil.memberships SET role='reviewer',active=true WHERE project_id=%s AND user_id=%s",
                    (frozen["lab"]["project"], frozen["lab"]["engineer"]),
                )
        c.execute(
            "UPDATE anvil.memberships SET role='reviewer',active=false WHERE project_id=%s AND user_id=%s",
            (frozen["lab"]["project"], frozen["lab"]["engineer"]),
        )
    with connection(
        "anvil_benchmark_evaluator", frozen["lab"]["project"], frozen["lab"]["admin"]
    ) as c:
        assert finish(c, frozen, capture) is None
    with connection() as c:
        assert (
            c.execute(
                "SELECT state FROM anvil.benchmark_evaluator_jobs WHERE id=%s", (capture["job"],)
            ).fetchone()["state"]
            == "queued"
        )


def test_exact_restricted_evaluator_custody_completion_is_scoped_and_idempotent(frozen):
    capture = manufactured_capture(frozen, creator="engineer")
    with connection(
        "anvil_benchmark_evaluator", frozen["lab"]["project"], frozen["lab"]["admin"]
    ) as c:
        assert finish(c, frozen, capture) == capture["job"]
        assert finish(c, frozen, capture) == capture["job"]
        assert c.execute("SELECT current_setting('anvil.benchmark_job') AS job").fetchone()[
            "job"
        ] == str(capture["job"])
    with connection() as c:
        observed = c.execute(
            "SELECT state,lease_until>now() AS live,lease_token IS NOT NULL AS fenced FROM anvil.benchmark_evaluator_jobs WHERE id=%s",
            (capture["job"],),
        ).fetchone()
        assert observed == {"state": "finished", "live": True, "fenced": True}
        assert (
            c.execute(
                "SELECT state FROM anvil.benchmark_offline_runtime WHERE attempt_id=%s",
                (capture["claim"]["attempt_id"],),
            ).fetchone()["state"]
            == "captured"
        )


@pytest.mark.parametrize(
    "fault",
    [
        "project_scope",
        "fence",
        "output_hash",
        "report_hash",
        "source_revoked",
        "qualification_revoked",
    ],
)
def test_restricted_evaluator_cannot_finish_mismatched_or_revoked_capture(frozen, fault):
    capture = manufactured_capture(frozen)
    if fault == "source_revoked":
        with actor_connection(frozen) as c:
            c.execute(
                "INSERT INTO anvil.benchmark_review_revocations(id,project_id,review_id,target,actor_id,rationale) VALUES(%s,%s,%s,'review',%s,'Manufactured SQL custody source revocation')",
                (
                    uuid4(),
                    frozen["lab"]["project"],
                    frozen["build"]["review_id"],
                    frozen["lab"]["admin"],
                ),
            )
    elif fault == "qualification_revoked":
        with actor_connection(frozen) as c:
            c.execute(
                "INSERT INTO anvil.benchmark_qualification_events(id,project_id,qualification_id,decision,rationale,actor_id) VALUES(%s,%s,%s,'revoked','Manufactured SQL qualification revocation',%s)",
                (
                    uuid4(),
                    frozen["lab"]["project"],
                    capture["qualification"],
                    frozen["lab"]["admin"],
                ),
            )
    scope = frozen["lab"]["other_project"] if fault == "project_scope" else frozen["lab"]["project"]
    with connection("anvil_benchmark_evaluator", scope, frozen["lab"]["admin"]) as c:
        assert (
            finish(
                c,
                frozen,
                capture,
                fence=uuid4() if fault == "fence" else None,
                output="0" * 64 if fault == "output_hash" else None,
                report="0" * 64 if fault == "report_hash" else None,
            )
            is None
        )
    with connection() as c:
        assert (
            c.execute(
                "SELECT state FROM anvil.benchmark_evaluator_jobs WHERE id=%s", (capture["job"],)
            ).fetchone()["state"]
            == "queued"
        )
