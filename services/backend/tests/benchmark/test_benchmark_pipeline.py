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
from fastapi.testclient import TestClient
from test_benchmark_imports import archive, setting
from test_private_storage import assign, connection
from test_private_storage import lab as storage_lab

from anvil.api import app
from anvil.benchmark_pipeline import claim, expire_claim, process_operation
from anvil.benchmark_storage import bind_private, stage_private
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
    assert "execution_profile_not_implemented" in {item["code"] for item in ready["blockers"]}
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
