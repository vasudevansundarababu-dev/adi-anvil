import base64
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_benchmark_imports import archive, setting
from test_private_storage import assign, connection
from test_private_storage import lab as storage_lab

from anvil.api import app
from anvil.benchmark_pipeline import claim, expire_claim, process_operation
from anvil.benchmark_pipeline_worker import _finish
from anvil.benchmark_storage import bind_private, read_private, stage_private
from anvil.config import ROOT
from anvil.db import transaction

lab = storage_lab
PREFIX = "/api/v1/projects/{project}/workspace/benchmarks"


def login(lab, identity):
    token, csrf = uuid4().hex, uuid4().hex
    with connection() as c:
        c.execute(
            "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                lab[identity],
                hashlib.sha256(csrf.encode()).hexdigest(),
            ),
        )
    client = TestClient(app)
    client.cookies.set("anvil_session", token)
    client.headers.update(
        {"origin": os.environ["WEB_ORIGIN"], "x-csrf-token": csrf, "idempotency-key": uuid4().hex}
    )
    return client


@pytest.fixture
def signed_lab(lab, tmp_path):
    key = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    policy = {
        "schema_version": "anvil.benchmark.trust.v1",
        "keys": [
            {
                "key_id": "pipeline-test-only",
                "public_key_base64": base64.b64encode(key.public_key().public_bytes_raw()).decode(),
                "not_before": (now - timedelta(hours=1)).isoformat(),
                "not_after": (now + timedelta(hours=2)).isoformat(),
                "revoked": False,
            }
        ],
    }
    path = tmp_path / "public-trust.json"
    path.write_text(json.dumps(policy))
    path.chmod(0o600)
    manifest = json.loads(
        (ROOT / "fixtures/benchmark-bundle/fictional-points-v1/manifest.json").read_bytes()
    )
    signature = json.dumps(
        {
            "profile": "ed25519-jcs-v1",
            "algorithm": "Ed25519",
            "key_id": "pipeline-test-only",
            "signature_base64": base64.b64encode(key.sign(rfc8785.dumps(manifest))).decode(),
        }
    ).encode()
    assign(lab, "engineer")
    assign(lab, "admin", scope="evaluation_review")
    client = login(lab, "engineer")
    admin = login(lab, "admin")
    base = PREFIX.format(project=lab["project"])
    with setting("ANVIL_BENCHMARK_TRUST_POLICY", str(path)):
        response = client.post(
            base + "/imports",
            content=archive(signature),
            headers={"content-type": "application/gzip"},
        )
        assert response.status_code == 200, response.text
        receipt = response.json()["data"]
        prepared = stage_private(
            lab["project"],
            b"Synthetic explicit local rights/code review evidence; no paid authority",
            "benchmark_eval",
        )
        with transaction(lab["project"], lab["admin"]) as c:
            evidence = bind_private(c, prepared, created_by=lab["admin"])
        review_body = {
            "expected_manifest_sha256": receipt["manifest_sha256"],
            "evidence_artifact_id": evidence,
            "rights_confirmed": True,
            "expires_at": (now + timedelta(hours=1)).isoformat(),
        }
        yield {
            "lab": lab,
            "client": client,
            "admin": admin,
            "base": base,
            "receipt": receipt,
            "review_body": review_body,
            "trust_path": path,
            "trust": policy,
        }
    client.close()
    admin.close()


def review_and_build(case):
    review = case["admin"].post(
        case["base"] + "/imports/" + case["receipt"]["receipt_id"] + "/reviews",
        json=case["review_body"],
    )
    assert review.status_code == 200, review.text
    body = {
        "expected_manifest_sha256": case["receipt"]["manifest_sha256"],
        "review_id": review.json()["data"]["review_id"],
    }
    response = case["client"].post(
        case["base"] + "/imports/" + case["receipt"]["receipt_id"] + "/build", json=body
    )
    assert response.status_code == 200, response.text
    return response.json()["data"], body


def test_verified_intake_is_not_review_or_build_authority(signed_lab):
    case = signed_lab
    response = case["client"].post(
        case["base"] + "/imports/" + case["receipt"]["receipt_id"] + "/build",
        json={
            "expected_manifest_sha256": case["receipt"]["manifest_sha256"],
            "review_id": str(uuid4()),
        },
    )
    assert response.status_code == 404
    response = case["client"].post(
        case["base"] + "/imports/" + case["receipt"]["receipt_id"] + "/reviews",
        json=case["review_body"],
    )
    assert response.status_code == 403


def test_build_is_durable_deterministic_actor_only_and_not_execution_ready(signed_lab):
    case = signed_lab
    build, body = review_and_build(case)
    assert build["state"] == "built" and len(build["packages"]) == 3
    again = case["client"].post(
        case["base"] + "/imports/" + case["receipt"]["receipt_id"] + "/build", json=body
    )
    assert again.status_code == 200 and again.json()["data"] == build
    status = (
        case["client"]
        .get(case["base"] + "/builds/" + build["build_id"] + "/readiness")
        .json()["data"]
    )
    assert not status["ready"] and not status["software_qualified"]
    assert "qualification_missing" in {item["code"] for item in status["blockers"]}
    assert "eval_pack" not in json.dumps(build) and "private_files" not in json.dumps(build)
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_receipt_tasks WHERE receipt_id=%s",
                (case["receipt"]["receipt_id"],),
            ).fetchone()["n"]
            == 3
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.jobs WHERE project_id=%s",
                (case["lab"]["project"],),
            ).fetchone()["n"]
            == 0
        )
    for package in build["packages"]:
        legacy = case["admin"].post(
            f"/api/v1/projects/{case['lab']['project']}/harbor-packages/{package['package_id']}/checks",
            json={"candidate": "reference"},
        )
        assert legacy.status_code == 409


@pytest.mark.parametrize("change", ["trust", "review", "assignment", "evaluator", "disabled"])
def test_current_policy_change_blocks_readiness_and_qualification(signed_lab, change):
    case = signed_lab
    build, _ = review_and_build(case)
    if change == "trust":
        case["trust"]["keys"][0]["revoked"] = True
        case["trust_path"].write_text(json.dumps(case["trust"]))
    elif change in {"review", "evaluator"}:
        target = build["review_id"] if change == "review" else build["evaluator_binding_id"]
        response = case["admin"].post(
            case["base"] + "/reviews/" + build["review_id"] + "/revoke",
            json={"rationale": "Synthetic explicit revocation", "target": change},
        )
        assert response.status_code == 200, response.text
        assert target
    elif change == "assignment":
        with connection() as c:
            c.execute(
                "UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s",
                (case["lab"]["project"], case["lab"]["engineer"]),
            )
    else:
        os.environ["ANVIL_BENCHMARK_ENABLED"] = "false"
    try:
        response = case["admin"].get(case["base"] + "/builds/" + build["build_id"] + "/readiness")
        assert response.status_code == 200, response.text
        status = response.json()["data"]
        assert not status["ready"] and not status["software_qualified"]
        assert status["state"] in {"blocked", "stale"}
        queued = case["admin"].post(
            case["base"] + "/builds/" + build["build_id"] + "/qualify",
            json={"expected_subject_sha256": build["subject_sha256"]},
        )
        assert queued.status_code in {409, 503}
    finally:
        if change == "disabled":
            os.environ["ANVIL_BENCHMARK_ENABLED"] = "true"


def test_qualification_queue_is_idempotent_fenced_and_not_general_worker_work(signed_lab):
    case = signed_lab
    build, _ = review_and_build(case)
    endpoint = case["base"] + "/builds/" + build["build_id"] + "/qualify"
    body = {"expected_subject_sha256": build["subject_sha256"]}
    response = case["admin"].post(endpoint, json=body)
    assert response.status_code == 202, response.text
    assert case["admin"].post(endpoint, json=body).json()["data"] == response.json()["data"]
    operation = response.json()["data"]
    assert operation["state"] == "queued"
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(
                lambda _: claim(
                    case["lab"]["project"],
                    operation["operation_id"],
                    case["lab"]["admin"],
                    lease_seconds=1,
                ),
                range(2),
            )
        )
    owned = [item for item in claims if item is not None]
    assert len(owned) == 1
    time.sleep(1.1)
    assert expire_claim(case["lab"]["project"], operation["operation_id"], case["lab"]["admin"])
    assert claim(case["lab"]["project"], operation["operation_id"], case["lab"]["admin"]) is None
    status = (
        case["admin"]
        .get(case["base"] + "/qualification-operations/" + operation["operation_id"])
        .json()["data"]
    )
    assert status["state"] == "execution_unknown"
    assert "fence" not in status and "lease_token" not in status


def test_cross_project_and_unassigned_private_access_remain_denied(signed_lab):
    case = signed_lab
    build, _ = review_and_build(case)
    outsider = login(case["lab"], "outsider")
    wrong = PREFIX.format(project=case["lab"]["other_project"])
    assert outsider.get(wrong + "/builds/" + build["build_id"] + "/readiness").status_code == 404
    with connection("anvil_app", case["lab"]["other_project"], case["lab"]["outsider"]) as c:
        assert (
            c.execute(
                "SELECT * FROM anvil.benchmark_builds WHERE id=%s", (build["build_id"],)
            ).fetchall()
            == []
        )
    with connection() as c:
        for table in [
            "benchmark_builds",
            "benchmark_build_tasks",
            "benchmark_source_reviews",
            "benchmark_qualification_operations",
        ]:
            flags = c.execute(
                "SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass",
                ("anvil." + table,),
            ).fetchone()
            assert flags["relrowsecurity"] and flags["relforcerowsecurity"]
            assert not c.execute(
                "SELECT has_table_privilege('anvil_worker',%s,'SELECT') AS allowed",
                ("anvil." + table,),
            ).fetchone()["allowed"]
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute("DELETE FROM anvil.benchmark_builds WHERE id=%s", (build["build_id"],))
    outsider.close()


def test_real_native_receipts_persist_through_durable_pipeline(signed_lab):
    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Explicit isolated native opt-in required; not a passing native result")
    case = signed_lab
    build, _ = review_and_build(case)
    queued = case["admin"].post(
        case["base"] + "/builds/" + build["build_id"] + "/qualify",
        json={"expected_subject_sha256": build["subject_sha256"]},
    )
    assert queued.status_code == 202, queued.text
    operation = queued.json()["data"]
    assert (
        process_operation(case["lab"]["project"], operation["operation_id"], case["lab"]["admin"])
        == "passed"
    )
    result = (
        case["admin"]
        .get(case["base"] + "/qualification-operations/" + operation["operation_id"])
        .json()["data"]
    )
    assert result["state"] == "passed" and len(result["qualifications"]) == 3
    ready = (
        case["admin"]
        .get(case["base"] + "/builds/" + build["build_id"] + "/readiness")
        .json()["data"]
    )
    assert ready["software_qualified"] and not ready["ready"]
    assert "protocol_required" in {item["code"] for item in ready["blockers"]}
    assert (
        process_operation(case["lab"]["project"], operation["operation_id"], case["lab"]["admin"])
        == "not_claimed"
    )
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_qualifications WHERE project_id=%s AND outcome='passed'",
                (case["lab"]["project"],),
            ).fetchone()["n"]
            == 3
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_operation_events WHERE operation_id=%s",
                (operation["operation_id"],),
            ).fetchone()["n"]
            == 3
        )
    case["trust"]["keys"][0]["revoked"] = True
    case["trust_path"].write_text(json.dumps(case["trust"]))
    stale = (
        case["admin"]
        .get(case["base"] + "/builds/" + build["build_id"] + "/readiness")
        .json()["data"]
    )
    assert not stale["software_qualified"] and not stale["ready"]
    assert stale["state"] == "stale"


@pytest.mark.parametrize("missing", ["idempotency", "csrf", "session"])
def test_review_command_requires_transport_guards(signed_lab, missing):
    case = signed_lab
    client = case["admin"]
    if missing == "idempotency":
        del client.headers["idempotency-key"]
    elif missing == "csrf":
        del client.headers["x-csrf-token"]
    else:
        client.cookies.clear()
    response = client.post(
        case["base"] + "/imports/" + case["receipt"]["receipt_id"] + "/reviews",
        json=case["review_body"],
    )
    assert response.status_code == {"idempotency": 428, "csrf": 403, "session": 401}[missing]
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_source_reviews WHERE project_id=%s",
                (case["lab"]["project"],),
            ).fetchone()["n"]
            == 0
        )


@pytest.mark.parametrize("change", ["rights", "expired", "hash", "extra", "wrong_evidence"])
def test_review_cannot_infer_rights_or_trust_changed_scope(signed_lab, change):
    case = signed_lab
    body = dict(case["review_body"])
    if change == "rights":
        body["rights_confirmed"] = False
    elif change == "expired":
        body["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    elif change == "hash":
        body["expected_manifest_sha256"] = "0" * 64
    elif change == "extra":
        body["production_approved"] = True
    else:
        body["evidence_artifact_id"] = str(uuid4())
    response = case["admin"].post(
        case["base"] + "/imports/" + case["receipt"]["receipt_id"] + "/reviews", json=body
    )
    assert response.status_code in {403, 409, 422}
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_source_reviews WHERE project_id=%s",
                (case["lab"]["project"],),
            ).fetchone()["n"]
            == 0
        )


def test_concurrent_build_and_queue_create_only_one_bound_operation(signed_lab):
    case = signed_lab
    build, body = review_and_build(case)
    endpoint = case["base"] + "/imports/" + case["receipt"]["receipt_id"] + "/build"

    def build_again(index):
        return case["client"].post(
            endpoint, json=body, headers={"idempotency-key": "concurrent-build-" + str(index)}
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(build_again, range(2)))
    assert all(r.status_code == 200 and r.json()["data"] == build for r in responses)
    endpoint = case["base"] + "/builds/" + build["build_id"] + "/qualify"

    def queue(index):
        return case["admin"].post(
            endpoint,
            json={"expected_subject_sha256": build["subject_sha256"]},
            headers={"idempotency-key": "concurrent-qualify-" + str(index)},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(queue, range(2)))
    assert sorted(r.status_code for r in responses) == [202, 409]
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_builds WHERE receipt_id=%s",
                (case["receipt"]["receipt_id"],),
            ).fetchone()["n"]
            == 1
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_qualification_operations WHERE build_id=%s",
                (build["build_id"],),
            ).fetchone()["n"]
            == 1
        )


def test_cancel_before_claim_is_terminal_and_does_not_start_native(signed_lab):
    case = signed_lab
    build, _ = review_and_build(case)
    response = case["admin"].post(
        case["base"] + "/builds/" + build["build_id"] + "/qualify",
        json={"expected_subject_sha256": build["subject_sha256"]},
    )
    operation = response.json()["data"]
    cancelled = case["admin"].post(
        case["base"] + "/qualification-operations/" + operation["operation_id"] + "/cancel"
    )
    assert cancelled.status_code == 200 and cancelled.json()["data"]["state"] == "cancelled"
    assert claim(case["lab"]["project"], operation["operation_id"], case["lab"]["admin"]) is None
    with connection() as c:
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute(
                "UPDATE anvil.benchmark_qualification_operations SET state='running' WHERE id=%s",
                (operation["operation_id"],),
            )


def test_unassigned_same_project_admin_cannot_build_or_read_private(signed_lab):
    case = signed_lab
    build, body = review_and_build(case)
    with connection() as c:
        assignments = c.execute(
            "SELECT id FROM anvil.benchmark_private_assignments WHERE project_id=%s AND user_id=%s",
            (case["lab"]["project"], case["lab"]["admin"]),
        ).fetchall()
        for assignment in assignments:
            c.execute(
                "INSERT INTO anvil.benchmark_private_revocations(project_id,assignment_id,revoked_by,rationale) VALUES(%s,%s,%s,'Synthetic assignment revoked')",
                (case["lab"]["project"], assignment["id"], case["lab"]["admin"]),
            )
    blocked = case["admin"].post(
        case["base"] + "/builds/" + build["build_id"] + "/qualify",
        json={"expected_subject_sha256": build["subject_sha256"]},
    )
    assert blocked.status_code == 409
    assert (
        not case["admin"]
        .get(case["base"] + "/builds/" + build["build_id"] + "/readiness")
        .json()["data"]["ready"]
    )
    with connection() as c:
        package = c.execute(
            "SELECT p.package_artifact_id FROM anvil.harbor_packages p JOIN anvil.benchmark_build_tasks t ON t.package_id=p.id WHERE t.build_id=%s LIMIT 1",
            (build["build_id"],),
        ).fetchone()
    response = case["admin"].get(
        f"/api/v1/projects/{case['lab']['project']}/artifacts/{package['package_artifact_id']}/content"
    )
    assert response.status_code == 404


def queued_operation(case, build):
    response = case["admin"].post(
        case["base"] + "/builds/" + build["build_id"] + "/qualify",
        json={"expected_subject_sha256": build["subject_sha256"]},
    )
    assert response.status_code == 202, response.text
    return response.json()["data"]


def sql_guard_artifact(case, classification="benchmark_trace"):
    prepared = stage_private(
        case["lab"]["project"],
        b"Manufactured SQL metadata guard input; NOT native evidence",
        classification,
    )
    with transaction(case["lab"]["project"], case["lab"]["admin"]) as c:
        identifier = bind_private(c, prepared, created_by=case["lab"]["admin"])
    return prepared, identifier


def test_sql_rejects_pass_without_complete_task_results(signed_lab):
    case = signed_lab
    build, _ = review_and_build(case)
    operation = queued_operation(case, build)
    assert claim(case["lab"]["project"], operation["operation_id"], case["lab"]["admin"])
    _, report = sql_guard_artifact(case)
    with connection("anvil_app", case["lab"]["project"], case["lab"]["admin"]) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="complete current qualification"):
            c.execute(
                "UPDATE anvil.benchmark_qualification_operations SET state='passed',report_artifact_id=%s,finished_at=now() WHERE id=%s",
                (report, operation["operation_id"]),
            )


@pytest.mark.parametrize(
    "fault", ["compiler", "environment", "tools", "private_report", "queued", "expired"]
)
def test_sql_rejects_mismatched_or_unleased_task_capture(signed_lab, fault):
    case = signed_lab
    build, _ = review_and_build(case)
    operation = queued_operation(case, build)
    if fault != "queued":
        assert claim(
            case["lab"]["project"],
            operation["operation_id"],
            case["lab"]["admin"],
            lease_seconds=1 if fault == "expired" else 1800,
        )
    _, artifact = sql_guard_artifact(
        case, "benchmark_eval" if fault == "private_report" else "benchmark_trace"
    )
    with connection() as c:
        row = c.execute(
            "SELECT t.*,p.package_sha256,b.dependencies FROM anvil.benchmark_build_tasks t JOIN anvil.harbor_packages p ON p.id=t.package_id JOIN anvil.benchmark_builds b ON b.id=t.build_id WHERE t.build_id=%s ORDER BY task_id LIMIT 1",
            (build["build_id"],),
        ).fetchone()
    with transaction(case["lab"]["project"], case["lab"]["admin"]) as c:
        bindings = json.loads(read_private(c, row["bindings_artifact_id"]))
    identifier = str(uuid4())
    with connection("anvil_app", case["lab"]["project"], case["lab"]["admin"]) as c:
        c.execute(
            "INSERT INTO anvil.benchmark_qualifications(id,project_id,source_id,package_id,evaluator_binding_id,package_sha256,environment_digest,compiler_sha256,tool_schema_sha256,harbor_version,outcome,report_artifact_id,reviewed_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'0.25.0','passed',%s,%s)",
            (
                identifier,
                case["lab"]["project"],
                row["source_id"],
                row["package_id"],
                build["evaluator_binding_id"],
                row["package_sha256"],
                "sha256:" + "0" * 64
                if fault == "environment"
                else bindings["environment"]["oci_manifest_digest"],
                "0" * 64
                if fault == "compiler"
                else row["dependencies"]["sources"][
                    "services/backend/src/anvil/benchmark_compiler.py"
                ],
                "0" * 64
                if fault == "tools"
                else hashlib.sha256(rfc8785.dumps(bindings["tools"])).hexdigest(),
                artifact,
                case["lab"]["admin"],
            ),
        )
    if fault == "expired":
        time.sleep(1.1)
    with connection("anvil_app", case["lab"]["project"], case["lab"]["admin"]) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="live private build"):
            c.execute(
                "INSERT INTO anvil.benchmark_operation_results(project_id,operation_id,build_id,task_id,source_id,package_id,qualification_id) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    case["lab"]["project"],
                    operation["operation_id"],
                    build["build_id"],
                    row["task_id"],
                    row["source_id"],
                    row["package_id"],
                    identifier,
                ),
            )


@pytest.mark.parametrize("fault", ["fence", "cancelled", "expired", "review_revoked"])
def test_worker_cannot_capture_after_fence_cancel_expiry_or_revocation(signed_lab, fault):
    case = signed_lab
    build, _ = review_and_build(case)
    queued = queued_operation(case, build)
    operation = claim(
        case["lab"]["project"],
        queued["operation_id"],
        case["lab"]["admin"],
        lease_seconds=1 if fault == "expired" else 1800,
    )
    report, _ = sql_guard_artifact(case)
    if fault == "fence":
        operation["fence"] = uuid4()
    elif fault == "cancelled":
        assert (
            case["admin"]
            .post(case["base"] + "/qualification-operations/" + queued["operation_id"] + "/cancel")
            .status_code
            == 200
        )
    elif fault == "expired":
        time.sleep(1.1)
    else:
        assert (
            case["admin"]
            .post(
                case["base"] + "/reviews/" + build["review_id"] + "/revoke",
                json={"target": "review", "rationale": "Manufactured SQL review revocation"},
            )
            .status_code
            == 200
        )
    with pytest.raises(HTTPException) as error:
        _finish(operation, report, [], "passed" if fault == "review_revoked" else "failed")
    assert error.value.status_code == 409
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_operation_results WHERE operation_id=%s",
                (queued["operation_id"],),
            ).fetchone()["n"]
            == 0
        )


def test_review_revocation_while_worker_waits_for_capture_lock_is_rechecked(signed_lab):
    case = signed_lab
    build, _ = review_and_build(case)
    queued = queued_operation(case, build)
    operation = claim(case["lab"]["project"], queued["operation_id"], case["lab"]["admin"])
    report, _ = sql_guard_artifact(case)
    application = "t04-capture-race-" + uuid4().hex
    with setting("DATABASE_URL", os.environ["DATABASE_URL"] + "&application_name=" + application):
        with ThreadPoolExecutor(max_workers=1) as pool:
            with connection() as c:
                c.execute(
                    "SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE",
                    (case["lab"]["project"],),
                )
                future = pool.submit(_finish, operation, report, [], "passed")
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    c.execute("SELECT pg_stat_clear_snapshot()")
                    waiting = c.execute(
                        "SELECT 1 FROM pg_stat_activity WHERE application_name=%s AND wait_event_type='Lock'",
                        (application,),
                    ).fetchone()
                    if waiting:
                        break
                    time.sleep(0.02)
                else:
                    raise AssertionError("Real worker never reached the capture lock")
                c.execute(
                    "INSERT INTO anvil.benchmark_review_revocations(id,project_id,review_id,target,actor_id,rationale) VALUES(%s,%s,%s,'review',%s,'Manufactured concurrent source review revocation')",
                    (
                        str(uuid4()),
                        case["lab"]["project"],
                        build["review_id"],
                        case["lab"]["admin"],
                    ),
                )
            with pytest.raises(HTTPException) as error:
                future.result(timeout=5)
            assert error.value.status_code == 409
    with connection() as c:
        row = c.execute(
            "SELECT state,report_artifact_id FROM anvil.benchmark_qualification_operations WHERE id=%s",
            (queued["operation_id"],),
        ).fetchone()
        assert row["state"] == "running" and row["report_artifact_id"] is None


@pytest.mark.parametrize(
    "table,assignment",
    [
        ("benchmark_builds", "dependencies='{}'::jsonb"),
        ("benchmark_build_tasks", "environment_digest='sha256:" + "0" * 64 + "'"),
        ("benchmark_build_tasks", "tool_schema_sha256='" + "0" * 64 + "'"),
        ("benchmark_source_reviews", "rights_confirmed=false"),
    ],
)
def test_bound_build_inputs_are_immutable_in_real_sql(signed_lab, table, assignment):
    case = signed_lab
    build, _ = review_and_build(case)
    key, identifier = (
        ("build_id", build["build_id"])
        if table == "benchmark_build_tasks"
        else (
            "id",
            build["review_id"] if table == "benchmark_source_reviews" else build["build_id"],
        )
    )
    with connection("anvil_app", case["lab"]["project"], case["lab"]["admin"]) as c:
        with pytest.raises((psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)):
            c.execute(f"UPDATE anvil.{table} SET {assignment} WHERE {key}=%s", (identifier,))


def test_cancel_and_terminal_capture_race_transition_once(signed_lab):
    case = signed_lab
    build, _ = review_and_build(case)
    queued = queued_operation(case, build)
    operation = claim(case["lab"]["project"], queued["operation_id"], case["lab"]["admin"])
    report, _ = sql_guard_artifact(case)

    def finish():
        try:
            return _finish(operation, report, [], "failed")
        except HTTPException as exc:
            assert exc.status_code == 409
            return "fenced"

    def cancel():
        response = case["admin"].post(
            case["base"] + "/qualification-operations/" + queued["operation_id"] + "/cancel"
        )
        assert response.status_code == 200
        return response.json()["data"]["state"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(finish), pool.submit(cancel)
        assert first.result(timeout=5) in {"failed", "fenced"}
        assert second.result(timeout=5) in {"failed", "execution_unknown"}
    with connection() as c:
        row = c.execute(
            "SELECT state FROM anvil.benchmark_qualification_operations WHERE id=%s",
            (queued["operation_id"],),
        ).fetchone()
        assert row["state"] in {"failed", "execution_unknown"}
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_operation_events WHERE operation_id=%s",
                (queued["operation_id"],),
            ).fetchone()["n"]
            == 3
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_operation_results WHERE operation_id=%s",
                (queued["operation_id"],),
            ).fetchone()["n"]
            == 0
        )
    assert claim(case["lab"]["project"], queued["operation_id"], case["lab"]["admin"]) is None
