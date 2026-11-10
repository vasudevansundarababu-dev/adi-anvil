"""Real PostgreSQL/API contracts. Synthetic row fixtures are NOT native evidence."""

import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
import rfc8785
from pypdf import PdfReader
from test_benchmark_pipeline import login
from test_private_storage import assign, connection
from test_private_storage import lab as storage_lab

from anvil.benchmark_storage import bind_private, stage_private
from anvil.db import Jsonb

lab = storage_lab


@pytest.fixture
def dashboard_lab(lab, monkeypatch):
    monkeypatch.setenv("ANVIL_BENCHMARK_ENABLED", "true")
    admin = login(lab, "admin")
    engineer = login(lab, "engineer")
    yield {
        "lab": lab,
        "admin": admin,
        "engineer": engineer,
        "base": "/api/v1/projects/" + lab["project"] + "/workspace/benchmarks",
    }
    admin.close()
    engineer.close()


def seed_control(case, *, recorded_at=None, mode="positive"):
    """Manufactured API contract fixture only; never used in the visible demo."""
    lab = case["lab"]
    assignment = assign(lab, "admin", scope="evaluation_review")
    text = '{"square":4}'
    output = {
        "path": "answers.json",
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "byte_size": len(text.encode()),
        "text": text,
    }
    seal = hashlib.sha256(
        rfc8785.dumps(
            {"files": [{k: output[k] for k in ("path", "sha256", "byte_size")}], "missing": []}
        )
    ).hexdigest()
    raw = json.dumps(
        {
            "fixture_notice": "MANUFACTURED SQL CONTRACT DATA: NO EXECUTION",
            "fixture_nonce": str(uuid4()),
            "origin": "original_synthetic_software_conformance",
            "task_id": "FX-001",
            "mode": mode,
            "points": 1,
            "possible_points": 1,
            "seal_sha256": seal,
            "tool_calls": 1,
            "denied_tool_calls": 0,
            "public_capture": {
                "outputs": [output],
                "missing": [],
                "criteria": [{"criterion_id": "c1", "earned_points": "1", "possible_points": "1"}],
            },
        }
    ).encode()
    artifact = stage_private(lab["project"], raw, "benchmark_trace", "application/json")
    with connection("anvil_app", lab["project"], lab["admin"]) as c:
        artifact_id = bind_private(c, artifact, created_by=lab["admin"])
    identifier = str(uuid4())
    metadata = {
        "kind": "historical_control",
        "origin": "original_synthetic_software_conformance",
        "current_authority": False,
        "measured_model_performance": False,
        "task_id": "FX-001",
        "task_key": "fictional-points:1.0.0:FX-001",
        "mode": mode,
        "points": 1,
        "possible_points": 1,
    }
    with connection() as c:
        c.execute(
            "INSERT INTO anvil.benchmark_trace_audit(id,project_id,artifact_id,source_record_sha256,source_commit,source_packet_sha256,recorded_at,environment,metadata,imported_by) VALUES(%s,%s,%s,%s,%s,%s,%s,'linux_qa',%s,%s)",
            (
                identifier,
                lab["project"],
                artifact_id,
                artifact.sha256,
                "a" * 40,
                "b" * 64,
                recorded_at or datetime.now(timezone.utc),
                Jsonb(metadata),
                lab["admin"],
            ),
        )
    return identifier, assignment


def test_empty_cohort_has_no_invented_model_judge_or_rank(dashboard_lab):
    case = dashboard_lab
    r = case["admin"].get(case["base"] + "/dashboard")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["overview"]["models"] == [] and d["overview"]["leader"] is None
    assert (
        d["overview"]["average_score_percent"] is None
        and d["failures"]["error_rate_percent"] is None
    )
    assert d["availability"]["judge"]["value"] is None
    assert d["overview"]["ranking"]["bradley_terry"]["rows"] == []
    foreign = (
        case["base"].replace(case["lab"]["project"], case["lab"]["other_project"]) + "/dashboard"
    )
    assert case["admin"].get(foreign).status_code in (403, 404)


def test_historical_control_is_actual_stored_record_but_never_model_rank(dashboard_lab):
    case = dashboard_lab
    identifier, _ = seed_control(case)
    response = case["admin"].get(case["base"] + "/dashboard")
    assert response.status_code == 200, response.text
    d = response.json()["data"]
    assert d["overview"]["control_trace_count"] == 1
    assert d["overview"]["model_trace_count"] == 0 and d["overview"]["ranked_models"] == 0
    assert d["failures"]["eligible_traces"] == 0 and d["failures"]["error_rate_percent"] is None
    assert d["traces"][0]["official"] is False
    r = case["admin"].get(case["base"] + "/dashboard/traces/" + identifier)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["outputs"][0]["text"] == '{"square":4}'
    assert r.json()["data"]["judge"]["value"] is None
    assert case["engineer"].get(case["base"] + "/dashboard").json()["data"]["traces"] == []
    assert case["engineer"].get(case["base"] + "/dashboard/traces/" + identifier).status_code == 404


def test_filter_snapshot_and_report_are_consistent_and_no_raw_prompts(dashboard_lab):
    case = dashboard_lab
    identifier, _ = seed_control(case)
    url = case["base"] + "/dashboard"
    d = case["admin"].get(url).json()["data"]
    assert case["admin"].get(url + "?model=not-an-observed-model").json()["data"]["traces"] == []
    assert case["admin"].get(url + "?environment=staging").json()["data"]["traces"] == []
    assert (
        case["admin"].get(url + "?task=fictional-points:1.0.0:FX-002").json()["data"]["traces"]
        == []
    )
    assert case["admin"].get(url + "?task=suite:not-a-uuid").status_code == 422
    assert case["admin"].get(url + "?period=yesterday").status_code == 422
    assert case["admin"].get(url + "?score_revision_id=" + str(uuid4())).status_code == 422
    assert case["admin"].get(url + "?run_id=" + str(uuid4())).status_code == 404
    r = case["admin"].get(
        url + "/report?template=technical&snapshot_sha256=" + d["snapshot_sha256"]
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    text = "\n".join(x.extract_text() for x in PdfReader(io.BytesIO(r.content)).pages)
    assert identifier in text and "Raw prompts: excluded" in text
    assert case["admin"].get(url + "/report?include_prompts=true").status_code == 403
    assert case["admin"].get(url + "/report?include_raw_prompts=true").status_code == 403
    seed_control(case)
    assert (
        case["admin"].get(url + "/report?snapshot_sha256=" + d["snapshot_sha256"]).status_code
        == 409
    )


def test_period_filter_uses_actual_recorded_window(dashboard_lab):
    case = dashboard_lab
    seed_control(case, recorded_at=datetime.now(timezone.utc) - timedelta(days=40))
    assert len(case["admin"].get(case["base"] + "/dashboard").json()["data"]["traces"]) == 1
    assert case["admin"].get(case["base"] + "/dashboard?period=30d").json()["data"]["traces"] == []


def test_revoked_duty_clears_trace_and_stale_export(dashboard_lab):
    case = dashboard_lab
    identifier, assignment = seed_control(case)
    d = case["admin"].get(case["base"] + "/dashboard").json()["data"]
    with connection(project=case["lab"]["project"], user=case["lab"]["admin"]) as c:
        c.execute(
            "INSERT INTO anvil.benchmark_private_revocations(project_id,assignment_id,revoked_by,rationale) VALUES(%s,%s,%s,'Explicit contract-test access revocation')",
            (case["lab"]["project"], assignment, case["lab"]["admin"]),
        )
    assert case["admin"].get(case["base"] + "/dashboard").json()["data"]["traces"] == []
    assert case["admin"].get(case["base"] + "/dashboard/traces/" + identifier).status_code == 404
    assert (
        case["admin"]
        .get(case["base"] + "/dashboard/report?snapshot_sha256=" + d["snapshot_sha256"])
        .status_code
        == 409
    )


def test_app_worker_cannot_author_audit_evidence_or_mutate_history(dashboard_lab):
    case = dashboard_lab
    identifier, _ = seed_control(case)
    for role in ("anvil_app", "anvil_worker", "anvil_benchmark_evaluator"):
        with connection() as c:
            row = c.execute(
                "SELECT has_table_privilege(%s,'anvil.benchmark_trace_audit','INSERT') ins,has_table_privilege(%s,'anvil.benchmark_trace_audit','UPDATE') upd,has_table_privilege(%s,'anvil.benchmark_trace_audit','DELETE') del",
                (role, role, role),
            ).fetchone()
            assert not any(row.values())
    with pytest.raises(psycopg.Error):
        with connection() as c:
            c.execute(
                "UPDATE anvil.benchmark_trace_audit SET environment='local_qa' WHERE id=%s",
                (identifier,),
            )
