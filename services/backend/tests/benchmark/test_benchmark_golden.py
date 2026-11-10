"""Actual isolated SQL/API golden workflows; test humans/rights are not product approvals."""

from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from test_benchmark_pipeline import login, review_and_build
from test_benchmark_pipeline import signed_lab as signed_fixture
from test_private_storage import connection
from test_private_storage import lab as storage_lab

from anvil import benchmark_golden
from anvil.api import context, idempotent, wrap
from anvil.benchmark_golden_api import routes
from anvil.db import Jsonb

lab = storage_lab
signed_lab = signed_fixture
PREFIX = "/api/v1/projects/{project}/workspace/benchmarks"


def client(lab, identity):
    original = login(lab, identity)
    app = FastAPI()

    @app.middleware("http")
    async def ids(request: Request, call_next):
        request.state.request_id = uuid4().hex
        return await call_next(request)

    app.include_router(routes(context, wrap, idempotent))
    c = TestClient(app)
    c.cookies.update(original.cookies)
    c.headers.update(original.headers)
    original.close()
    return c


def create(c, base):
    r = c.post(
        base + "/golden-datasets",
        json={
            "name": "Original fictional Golden lab",
            "description": "Software test, not measured model data",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def body(**changes):
    return {
        "case_key": "fictional-1",
        "title": "Human authored original fixture",
        "category": "task_correctness",
        "input_text": "Original fictional square input",
        "expected_output": "Original manually authored expected result",
        "fictional_task_id": "FX-001",
        **changes,
    }


def test_drafts_persist_no_auto_verified_and_privacy(lab):
    a = client(lab, "engineer")
    b = client(lab, "admin")
    base = PREFIX.format(project=lab["project"])
    dataset = create(a, base)
    response = a.post(base + "/golden-datasets/" + dataset + "/versions", json=body())
    assert response.status_code == 201, response.text
    v = response.json()["data"]
    assert (
        v["status"] == "draft" and v["verification"] is None and not v["is_task_scoring_authority"]
    )
    assert "current_source_binding_required" in v["permissions"]["verification_blockers"]
    assert b.get(base + "/golden-versions/" + v["id"]).status_code == 404
    assert (
        b.get(base + "/golden-datasets").json()["data"]["items"][0]["name"]
        == "Original fictional Golden lab"
    )
    assert (
        a.get(base + "/golden-versions/" + v["id"]).json()["data"]["content"]["expected_output"]
        == body()["expected_output"]
    )
    assert (
        a.get(
            base.replace(lab["project"], lab["other_project"]) + "/golden-versions/" + v["id"]
        ).status_code
        == 404
    )
    with connection("anvil_worker", lab["project"], lab["engineer"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT * FROM anvil.benchmark_golden_versions")
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(
                "UPDATE anvil.benchmark_golden_versions SET content=%s WHERE id=%s", ("{}", v["id"])
            )


def test_revision_append_idempotency_archive_and_no_anchor_mutation(lab):
    c = client(lab, "engineer")
    base = PREFIX.format(project=lab["project"])
    dataset = create(c, base)
    path = base + "/golden-datasets/" + dataset + "/versions"
    first = c.post(path, json=body()).json()["data"]
    assert c.post(path, json=body()).json()["data"]["id"] == first["id"]
    c.headers["idempotency-key"] = uuid4().hex
    stale = c.post(path, json=body(expected_output="New draft output"))
    assert stale.status_code == 409
    revised = c.post(
        path, json=body(expected_output="New draft output", predecessor_id=first["id"])
    )
    assert revised.status_code == 201, revised.text
    newer = revised.json()["data"]
    assert newer["revision"] == 2 and newer["status"] == "draft"
    assert (
        c.get(base + "/golden-versions/" + first["id"]).json()["data"]["content_sha256"]
        == first["content_sha256"]
    )
    c.headers["idempotency-key"] = uuid4().hex
    assert (
        c.post(
            base + "/golden-datasets/" + dataset + "/archive",
            json={"rationale": "Archive only this original software test dataset"},
        ).status_code
        == 200
    )
    assert c.post(path, json=body(predecessor_id=newer["id"])).status_code == 409
    assert c.get(base + "/golden-versions/" + first["id"]).status_code == 200


def test_personas_only_persist_bounded_blocked_intents_no_execution(lab):
    c = client(lab, "engineer")
    base = PREFIX.format(project=lab["project"])
    r = c.post(
        base + "/remediation",
        json={
            "title": "Original fictional urgency proposal",
            "persona": "customer_urgency",
            "rationale": "Human proposed stress case for software test only",
            "proposed_prompt": "Please clarify the fictional task",
            "fictional_task_id": "FX-001",
            "offline_only": True,
        },
    )
    assert r.status_code == 201, r.text
    p = r.json()["data"]
    assert p["state"] == "proposed" and not p["auto_applied"] and p["run_intents"] == []
    path = base + "/remediation/" + p["id"] + "/run-intents"
    b = {
        "expected_content_sha256": p["content_sha256"],
        "offline_only": True,
        "max_steps": 10,
        "max_output_bytes": 1024,
    }
    r = c.post(path, json=b)
    assert r.status_code == 202, r.text
    intent = r.json()["data"]["run_intents"][0]
    assert (
        intent["state"] == "blocked"
        and intent["code"] == "compatible_offline_executor_unavailable"
        and intent["provider_calls"] == 0
        and not intent["auto_applied"]
    )
    assert intent["limits"] == {"max_steps": 10, "max_output_bytes": 1024}
    assert len(c.post(path, json=b).json()["data"]["run_intents"]) == 1
    assert c.post(path, json={**b, "offline_only": False}).status_code == 422
    assert c.post(path, json={**b, "max_steps": 21}).status_code == 422
    with connection() as db:
        assert (
            db.execute(
                "SELECT count(*) AS n FROM anvil.runs WHERE project_id=%s", (lab["project"],)
            ).fetchone()["n"]
            == 0
        )


def test_distinct_human_verification_exact_evidence_and_immutable_anchor(signed_lab):
    case = signed_lab
    build, _ = review_and_build(case)
    lab = case["lab"]
    author = client(lab, "engineer")
    reviewer = client(lab, "admin")
    base = case["base"]
    dataset = create(author, base)
    r = author.post(
        base + "/golden-datasets/" + dataset + "/versions",
        json=body(source_build_id=build["build_id"]),
    )
    assert r.status_code == 201, r.text
    v = r.json()["data"]
    with connection() as db:
        assignment = db.execute(
            "SELECT id FROM anvil.benchmark_private_assignments WHERE project_id=%s AND user_id=%s AND scope='evaluation_review'",
            (lab["project"], lab["admin"]),
        ).fetchone()["id"]
        artifact = db.execute(
            "SELECT sha256 FROM anvil.artifacts WHERE id=%s",
            (case["review_body"]["evidence_artifact_id"],),
        ).fetchone()
    b = {
        "assignment_id": str(assignment),
        "evidence_artifact_id": str(case["review_body"]["evidence_artifact_id"]),
        "evidence_sha256": artifact["sha256"],
        "expected_content_sha256": v["content_sha256"],
        "decision": "verified",
        "human_reviewed": True,
        "rationale": "Distinct synthetic test human explicitly reviewed expected output",
    }
    assert (
        author.post(base + "/golden-versions/" + v["id"] + "/verification", json=b).status_code
        == 403
    )
    assert (
        reviewer.post(
            base + "/golden-versions/" + v["id"] + "/verification",
            json={**b, "human_reviewed": False},
        ).status_code
        == 422
    )
    assert (
        reviewer.post(
            base + "/golden-versions/" + v["id"] + "/verification",
            json={**b, "evidence_sha256": "0" * 64},
        ).status_code
        == 409
    )
    r = reviewer.post(base + "/golden-versions/" + v["id"] + "/verification", json=b)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "verified"
    author.headers["idempotency-key"] = uuid4().hex
    new = author.post(
        base + "/golden-datasets/" + dataset + "/versions",
        json=body(
            source_build_id=build["build_id"],
            predecessor_id=v["id"],
            expected_output="A new human-authored draft",
        ),
    )
    assert new.status_code == 201, new.text
    assert new.json()["data"]["status"] == "draft"
    assert author.get(base + "/golden-versions/" + v["id"]).json()["data"]["status"] == "verified"
    reviewer.headers["idempotency-key"] = uuid4().hex
    assert (
        reviewer.post(
            base + "/golden-versions/" + v["id"] + "/verification",
            json={**b, "decision": "rejected"},
        ).status_code
        == 409
    )
    assert (
        case["admin"]
        .post(
            base + "/reviews/" + build["review_id"] + "/revoke",
            json={"target": "review", "rationale": "Actual isolated SQL test source revocation"},
        )
        .status_code
        == 200
    )
    assert author.get(base + "/golden-versions/" + v["id"]).status_code in (403, 404, 409)


def test_direct_sql_cannot_spoof_author_or_turn_intent_into_execution(lab):
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(
                "INSERT INTO anvil.benchmark_golden_datasets(id,project_id,name,description,created_by) VALUES(%s,%s,'spoof','',%s)",
                (str(uuid4()), lab["project"], lab["admin"]),
            )
    user = client(lab, "engineer")
    base = PREFIX.format(project=lab["project"])
    proposal = user.post(
        base + "/remediation",
        json={
            "title": "Bounded original software proposal",
            "persona": "repetitive_loop",
            "rationale": "Explicit original software control only",
            "fictional_task_id": "FX-001",
        },
    ).json()["data"]
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(
                "INSERT INTO anvil.benchmark_remediation_intents(id,project_id,proposal_id,created_by,state,code,provider_calls,auto_applied,limits) VALUES(%s,%s,%s,%s,'completed','compatible_offline_executor_unavailable',0,false,%s)",
                (
                    str(uuid4()),
                    lab["project"],
                    proposal["id"],
                    lab["engineer"],
                    Jsonb({"max_steps": 1, "max_output_bytes": 64}),
                ),
            )
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(
                "INSERT INTO anvil.benchmark_remediation_intents(id,project_id,proposal_id,created_by,state,code,provider_calls,auto_applied,limits) VALUES(%s,%s,%s,%s,'blocked','compatible_offline_executor_unavailable',1,false,%s)",
                (
                    str(uuid4()),
                    lab["project"],
                    proposal["id"],
                    lab["engineer"],
                    Jsonb({"max_steps": 1, "max_output_bytes": 64}),
                ),
            )


def test_direct_sql_self_verification_and_revoked_duty_fail_closed(signed_lab):
    case = signed_lab
    build, _ = review_and_build(case)
    lab = case["lab"]
    author = client(lab, "engineer")
    reviewer = client(lab, "admin")
    base = case["base"]
    dataset = create(author, base)
    response = author.post(
        base + "/golden-datasets/" + dataset + "/versions",
        json=body(source_build_id=build["build_id"]),
    )
    assert response.status_code == 201, response.text
    v = response.json()["data"]
    with connection() as c:
        duty = c.execute(
            "SELECT id FROM anvil.benchmark_private_assignments WHERE project_id=%s AND user_id=%s AND scope='evaluation_review'",
            (lab["project"], lab["admin"]),
        ).fetchone()["id"]
        evidence = c.execute(
            "SELECT id,sha256 FROM anvil.artifacts WHERE id=%s",
            (case["review_body"]["evidence_artifact_id"],),
        ).fetchone()
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="distinct human"):
            c.execute(
                "INSERT INTO anvil.benchmark_golden_verifications(id,project_id,version_id,assignment_id,evidence_artifact_id,evidence_sha256,expected_content_sha256,verifier_id,decision,rationale,human_reviewed) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'verified','No self verification is allowed',true)",
                (
                    str(uuid4()),
                    lab["project"],
                    v["id"],
                    duty,
                    evidence["id"],
                    evidence["sha256"],
                    v["content_sha256"],
                    lab["engineer"],
                ),
            )
    with connection("anvil_app", lab["project"], lab["admin"]) as c:
        c.execute(
            "INSERT INTO anvil.benchmark_private_revocations(project_id,assignment_id,revoked_by,rationale) VALUES(%s,%s,%s,'Revoke only this synthetic test duty')",
            (lab["project"], duty, lab["admin"]),
        )
    assert reviewer.get(base + "/golden-versions/" + v["id"]).status_code == 404
    assert author.get(base + "/golden-versions/" + v["id"]).json()["data"]["status"] == "draft"
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_golden_verifications WHERE version_id=%s",
                (v["id"],),
            ).fetchone()["n"]
            == 0
        )


def test_untrusted_anchor_and_auto_verified_payload_rejected(lab):
    c = client(lab, "engineer")
    base = PREFIX.format(project=lab["project"])
    dataset = create(c, base)
    path = base + "/golden-datasets/" + dataset + "/versions"
    assert c.post(path, json=body(status="verified")).status_code == 422
    assert c.post(path, json=body(source_trace_id=str(uuid4()))).status_code == 404
    assert (
        c.post(
            path, json=body(source_trace_id=str(uuid4()), source_build_id=str(uuid4()))
        ).status_code
        == 422
    )
    assert (
        c.post(
            path, json=body(source_anchor={"run_id": str(uuid4()), "cell_id": str(uuid4())})
        ).status_code
        == 404
    )
    assert c.get(base + "/golden-datasets/" + dataset + "/versions").json()["data"]["items"] == []


def test_context_filters_and_redacted_summary_use_only_latest_heads(lab):
    user = client(lab, "engineer")
    base = PREFIX.format(project=lab["project"])
    dataset = create(user, base)
    path = base + "/golden-datasets/" + dataset + "/versions"
    first = user.post(path, json=body()).json()["data"]
    user.headers["idempotency-key"] = uuid4().hex
    second = user.post(
        path, json=body(predecessor_id=first["id"], expected_output="Updated private ground truth")
    ).json()["data"]
    query = "?task=fictional-points:1.0.0:FX-003"
    assert user.get(path + query).json()["data"]["items"] == []
    assert user.get(base + "/golden-versions/" + second["id"] + query).status_code == 404
    assert user.get(path + "?model=unobserved-model-key").json()["data"]["items"] == []
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        context = {
            "model": [],
            "task": "all",
            "period": "all",
            "environment": "all",
            "run_id": None,
            "trace_id": None,
            "score_revision_id": None,
            "cluster": None,
        }
        summary = benchmark_golden.dashboard_summary(c, lab["project"], lab["engineer"], context)
        assert (
            summary["case_versions"] == 1
            and summary["cases"][0]["id"] == second["id"]
            and summary["verified_cases"] == 0
        )
        assert (
            "expected_output" not in str(summary)
            and "input_text" not in str(summary)
            and "Updated private" not in str(summary)
        )
        filtered = benchmark_golden.dashboard_summary(
            c, lab["project"], lab["engineer"], {**context, "task": "fictional-points:1.0.0:FX-003"}
        )
        assert filtered["case_versions"] == 0 and filtered["datasets"] == 0
