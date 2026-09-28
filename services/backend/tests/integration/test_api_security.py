"""Direct API negatives; real OIDC acquisition is separately covered by Playwright."""

import json
import secrets
import time

import httpx
import pytest
from authlib.jose import JsonWebKey, JsonWebToken
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

from anvil import auth, graph
from anvil.api import app
from anvil.artifacts import store
from anvil.auth import hashed
from anvil.cli import OUTSIDER_PROJECT, PROJECT
from anvil.config import ROOT, setting
from anvil.db import transaction, uid

USERS = json.loads((ROOT / ".local/demo-identities.json").read_text())
BASE = f"/api/v1/projects/{PROJECT}"


@pytest.fixture
def client_factory():
    sessions = []

    def make(name="researcher"):
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with transaction() as c:
            c.execute(
                "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
                (hashed(token), USERS[name], hashed(csrf)),
            )
        sessions.append(hashed(token))
        client = TestClient(app)
        client.cookies.set("anvil_session", token)
        client.headers.update(
            {"Origin": "http://127.0.0.1:3202", "X-CSRF-Token": csrf, "Idempotency-Key": uid()}
        )
        return client, hashed(token)

    yield make
    with transaction() as c:
        for token_hash in sessions:
            c.execute(
                "UPDATE anvil.sessions SET revoked_at=now() WHERE token_hash=%s", (token_hash,)
            )


@pytest.mark.parametrize(
    "valid_alternative", [False, True], ids=["missing-answer", "valid-alternative"]
)
def test_external_results_preserve_origin_and_never_invoke(
    client_factory, monkeypatch, valid_alternative
):
    from anvil import evaluation, external_results, reports, worker
    from anvil.db import one

    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    project = journey["project_id"]
    base = f"/api/v1/projects/{project}"
    clients = {
        name: client_factory(name)[0]
        for name in [
            "researcher",
            "data-engineer",
            "advisor",
            "reviewer-1",
            "reviewer-2",
            "sales",
            "product-owner",
        ]
    }

    def post(name, path, body, version=None, expected=200):
        result = clients[name].post(
            base + path,
            json=body,
            headers={"Idempotency-Key": uid(), **({"If-Match": str(version)} if version else {})},
        )
        assert result.status_code == expected, result.text
        return result.json().get("data")

    def get(name, path):
        result = clients[name].get(base + path)
        assert result.status_code == 200, result.text
        return result.json()["data"]

    original = get("researcher", "/protocols/" + journey["protocol"]["id"])
    body = {
        **original["content"],
        "title": "Synthetic partner import acceptance",
        "mode": "external_result_import_v1",
        "candidates": ["external-reported"],
    }
    protocol = post("researcher", "/protocols", body, expected=201)
    protocol = post(
        "researcher", "/protocols/" + protocol["id"] + "/submit", {}, protocol["row_version"]
    )
    protocol = post(
        "advisor",
        "/protocols/" + protocol["id"] + "/decisions",
        {
            "purpose": "technical",
            "decision": "approve",
            "rationale": "Independent review of the local reported-execution protocol.",
        },
        protocol["row_version"],
    )
    run = post(
        "researcher",
        "/runs",
        {
            "protocol_revision_id": protocol["current_revision_id"],
            "external_origin": "partner_reported",
        },
        expected=201,
    )
    post("researcher", "/runs/" + run["id"] + "/launch", {}, run["row_version"], expected=409)
    with transaction(project, USERS["data-engineer"]) as c:
        tasks = one(
            c,
            "SELECT content FROM anvil.revisions WHERE id=%s",
            (journey["suite"]["current_revision_id"],),
        )["content"]["task_revision_ids"]
        tasks.sort(
            key=lambda tid: (
                one(
                    c,
                    "SELECT content->>'external_case_id' AS case_id FROM anvil.revisions WHERE id=%s",
                    (tid,),
                )["case_id"]
                != "MKT-001"
            )
        )
        alternate = json.loads(
            (ROOT / "fixtures/calibration/valid-alternative-mkt.json").read_text()
        )["output"]
        output_text = (
            json.dumps(alternate)
            if valid_alternative
            else "Synthetic externally supplied final answer for import verification."
        )
        if valid_alternative:
            original_output = next(
                row["output"]
                for row in json.loads(
                    (ROOT / "fixtures/candidate-outputs/responses.json").read_text()
                )["responses"]
                if row["case_id"] == "MKT-001" and row["candidate"] == "fixture-correct"
            )
            assert alternate != original_output
        output = store(
            c,
            project,
            output_text.encode(),
            "internal",
            "text/plain",
            origin="partner_reported",
        )
        hidden = store(
            c,
            project,
            b"Private reference must not be imported as output",
            "hidden_reference",
            "text/plain",
            origin="partner_reported",
        )
    manifest = {
        "schema_version": "anvil.external_results.v1",
        "run_id": run["id"],
        "origin": "partner_reported",
        "producer": "Synthetic integration test only",
        "executed_at": "2026-09-27T10:00:00Z",
        "protocol_hash": None,
        "producer_manifest_hash": "a" * 64,
        "incomparability_reasons": [
            "Synthetic external recording has no matching execution protocol."
        ],
        "candidate_descriptor": {
            "model_requested": None,
            "model_returned": None,
            "harness_version": None,
            "graph_version": None,
            "tools": None,
            "parameters": None,
        },
        "attempts": [
            {
                "task_revision_id": tasks[0],
                "repetition": 1,
                "attempt": 1,
                "execution_state": "completed",
                "output_artifact_id": output,
                "source_score": 99,
                "source_rubric_version": "partner-test-v1",
                "limitations": ["Final output only; no action trajectory supplied."],
            },
            {
                "task_revision_id": tasks[1],
                "repetition": 1,
                "attempt": 1,
                "execution_state": "completed",
                "source_score": 100,
                "source_rubric_version": "partner-test-v1",
                "limitations": ["Aggregate-only result; no output available for Anvil grading."],
            },
            {
                "task_revision_id": tasks[2],
                "repetition": 1,
                "attempt": 1,
                "execution_state": "execution_unknown",
                "limitations": ["Producer could not determine execution acceptance."],
            },
        ],
    }
    path = "/runs/" + run["id"] + "/external-results/validate"
    post("sales", path, manifest, expected=403)
    for mutation, expected_code in [
        ({"protocol_hash": "b" * 64}, "protocol_hash_mismatch"),
        ({"origin": "customer_reported"}, "execution_origin_mismatch"),
        (
            {"attempts": [{**manifest["attempts"][0], "task_revision_id": uid()}]},
            "task_not_in_frozen_suite",
        ),
        ({"attempts": [manifest["attempts"][0], manifest["attempts"][0]]}, "duplicate_attempt"),
        (
            {"attempts": [{**manifest["attempts"][0], "output_artifact_id": hidden}]},
            "evidence_unavailable_or_unqualified",
        ),
    ]:
        bad = post("data-engineer", path, {**manifest, **mutation})
        assert bad["status"] == "rejected" and expected_code in [e["code"] for e in bad["errors"]]
        post(
            "data-engineer",
            "/imports/" + bad["id"] + "/commit-results",
            {"manifest_hash": bad["manifest_hash"]},
            expected=409,
        )
    preview = post("data-engineer", path, manifest)
    assert preview["status"] == "validated" and not preview["independently_reproduced"]
    assert get("researcher", "/runs/" + run["id"])["episodes"] == []
    post(
        "data-engineer",
        "/imports/" + preview["id"] + "/commit",
        {"manifest_hash": preview["manifest_hash"]},
        expected=409,
    )

    jobs = []

    def enqueue(c, project, kind, target, key):
        if kind not in ("episode", "resume"):
            return
        jid, token = uid(), uid()
        c.execute(
            "INSERT INTO anvil.jobs(id,project_id,kind,target_id,operation_key,status,lease_token,lease_until) VALUES(%s,%s,%s,%s,%s,'leased',%s,now()+interval '60 seconds')",
            (jid, project, kind, target, key, token),
        )
        jobs.append(one(c, "SELECT * FROM anvil.jobs WHERE id=%s", (jid,)))

    monkeypatch.setattr(external_results, "enqueue", enqueue)
    monkeypatch.setattr(evaluation, "enqueue", enqueue)
    receipt = post(
        "data-engineer",
        "/imports/" + preview["id"] + "/commit-results",
        {"manifest_hash": preview["manifest_hash"]},
    )
    repeat = post(
        "data-engineer",
        "/imports/" + preview["id"] + "/commit-results",
        {"manifest_hash": preview["manifest_hash"]},
    )
    assert receipt == repeat and receipt["receipt_hash"] != manifest["producer_manifest_hash"]
    original_one = worker.one
    monkeypatch.setattr(
        worker,
        "one",
        lambda c, query, params=(): (
            jobs.pop(0)
            if query == "SELECT * FROM anvil.claim_job()"
            else original_one(c, query, params)
        ),
    )
    assert worker.tick()
    episodes = get("researcher", "/runs/" + run["id"])["episodes"]
    reviewable = next(e for e in episodes if e["state"] == "awaiting_review")
    assert all(e["score"] is None and e["invocation_count"] == 0 for e in episodes)
    for name in ["reviewer-1", "reviewer-2"]:
        detail = get(name, "/reviews/" + reviewable["id"])
        assert (
            detail["execution_origin"] == "partner_reported" and detail["trace_coverage"] == "none"
        )
        assert "source_score" not in detail and "external_provenance" not in detail
        post(
            name,
            "/episodes/" + reviewable["id"] + "/assessments",
            {
                "scores": {k: 4 if valid_alternative else 0 for k in ["R1", "R2", "R3"]},
                "critical": [],
                "evidence": {
                    "R1": '"gross_profit": 3750',
                    "R2": "Ten-percent reduction",
                    "R3": "actor/exhibits.json",
                }
                if valid_alternative
                else {k: "Synthetic externally supplied final answer" for k in ["R1", "R2", "R3"]},
                "rationale": "Scripted calibration review credits equivalent option names, correct calculations and limits; no exact-answer matching."
                if valid_alternative
                else "Independent synthetic review disagrees with the supplied source score.",
            },
            detail["row_version"],
        )
    assert worker.tick()
    with transaction(project, USERS["researcher"]) as c:
        facts = reports.facts(c, run["id"])
        assert facts["origin"] == "partner_reported" and facts["mean_score"] == (
            100 if valid_alternative else 0
        )
        assert facts["passes"] == int(valid_alternative)
        assert facts["failures"] == int(not valid_alternative)
        assert facts["unscorable"] == 1 and facts["unknown"] == 1 and facts["valid"] == 1
        assert all(
            e["trace_coverage"] == "none" and not e["independently_reproduced"]
            for e in facts["external_results"]
        )
        assert sorted(
            e["source_score_reported"]
            for e in facts["external_results"]
            if e["source_score_reported"] is not None
        ) == [99, 100]
        kit = reports.kit_content(
            {"content": {"facts": facts}, "current_revision_id": uid(), "content_hash": "c" * 64}
        )
        assert "PARTNER REPORTED" in kit["label"] and "NOT INDEPENDENTLY REPRODUCED" in kit["label"]
        assert b"PARTNER REPORTED" in reports.html_bytes(kit)
        assert reports.pdf_bytes(kit).startswith(b"%PDF")
        assert all(
            e["invocation_count"] == 0
            for e in c.execute(
                "SELECT invocation_count FROM anvil.episodes WHERE run_id=%s", (run["id"],)
            ).fetchall()
        )
        from psycopg.errors import CheckViolation, RaiseException

        with (
            pytest.raises(RaiseException, match="immutable imported execution binding"),
            c.transaction(),
        ):
            c.execute(
                "UPDATE anvil.episodes SET output_artifact_id=NULL WHERE id=%s", (reviewable["id"],)
            )
        with pytest.raises(CheckViolation), c.transaction():
            c.execute(
                "UPDATE anvil.episodes SET invocation_count=1 WHERE id=%s", (reviewable["id"],)
            )
    assert (
        get("researcher", "/episodes/" + reviewable["id"] + "/evidence")["origin"]
        == "partner_reported"
    )
    report = post(
        "researcher",
        "/reports",
        {
            "title": "Synthetic reported-origin export acceptance",
            "run_id": run["id"],
            "finding_revision_ids": [],
            "advisor_id": USERS["advisor"],
            "reviewer_id": USERS["reviewer-1"],
            "product_owner_id": USERS["product-owner"],
            "audience": "internal_fixture",
        },
        expected=201,
    )
    report_path = "/reports/" + report["id"]
    report = post("researcher", report_path + "/submit", {}, report["row_version"])
    for role, purpose in [
        ("advisor", "technical"),
        ("reviewer-1", "domain"),
        ("product-owner", "audience"),
        ("product-owner", "release"),
    ]:
        report = post(
            role,
            report_path + "/decisions",
            {
                "purpose": purpose,
                "decision": "approve",
                "rationale": "Independent internal approval of the synthetic external-origin test report.",
            },
            report["row_version"],
        )
    post("researcher", report_path + "/build", {}, report["row_version"])
    import io
    import zipfile

    from pypdf import PdfReader

    pdf = clients["sales"].get(base + report_path + "/download/sales-kit.pdf")
    assert pdf.status_code == 200
    pages = PdfReader(io.BytesIO(pdf.content)).pages
    assert len(pages) == 1 and "PARTNER REPORTED" in pages[0].extract_text()
    (ROOT / "artifacts/test-runs/external-sales-kit.pdf").write_bytes(pdf.content)
    bundle = clients["sales"].get(base + report_path + "/download/evidence.zip")
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        exported = json.loads(archive.read("manifest.json"))
        assert exported["origin"] == "partner_reported"
        receipt_rows = json.loads(archive.read("external-result-receipts.json"))
        assert len(receipt_rows) == 3 and all(
            not row["independently_reproduced"] for row in receipt_rows
        )
        assert b"PARTNER REPORTED" in archive.read("email-draft.txt")
        assert all("reference" not in name for name in archive.namelist())
    latest = get("researcher", "/runs/" + run["id"])
    post("researcher", "/runs/" + run["id"] + "/cancel", {}, latest["row_version"])
    assert sorted(e["state"] for e in get("researcher", "/runs/" + run["id"])["episodes"]) == [
        "execution_unknown",
        "finalized",
        "unscorable",
    ]


@pytest.mark.parametrize("state", ["expired", "idle", "revoked"])
def test_expired_idle_revoked_session(client_factory, state):
    client, token_hash = client_factory()
    statements = {
        "expired": "expires_at=now()-interval '1 second'",
        "idle": "last_seen_at=now()-interval '31 minutes'",
        "revoked": "revoked_at=now()",
    }
    with transaction() as c:
        c.execute(
            f"UPDATE anvil.sessions SET {statements[state]} WHERE token_hash=%s", (token_hash,)
        )
    assert client.get("/api/v1/me").status_code == 401


def test_200_synthetic_source_inventory_pagination_and_search(client_factory):
    import contextlib
    import io
    import math
    import os
    import platform
    import shutil
    import subprocess

    from anvil.operations import new_demo

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        new_demo("Synthetic 200-source inventory acceptance")
    project = json.loads(captured.getvalue())["project_id"]
    base = f"/api/v1/projects/{project}"
    client, _ = client_factory("data-engineer")
    with transaction(project, USERS["data-engineer"]) as c:
        aid = store(
            c,
            project,
            b"Original synthetic load-test exhibit. Not university cases or model-performance evidence.",
            "internal",
            "text/plain",
            origin="synthetic_load_test",
        )
    manifest = {
        "schema_version": "anvil.case_import.v1",
        "partner_key": "synthetic-load-test",
        "cases": [
            {
                "external_case_id": f"LOAD-{i:03}",
                "source_version": "synthetic-v1",
                "title": f"Synthetic inventory load case {i:03}",
                "subjects": ["test_only"],
                "source_family_key": f"load-family-{i // 2:03}",
                "artifact_ids": [aid],
                "provenance": {"origin": "synthetic_load_test", "faculty_reviewed": False},
                "readiness": [],
                "rights_declarations": [],
            }
            for i in range(200)
        ],
    }
    preview = client.post(
        base + "/imports/validate", json=manifest, headers={"Idempotency-Key": uid()}
    )
    assert preview.status_code == 200, preview.text
    batch = preview.json()["data"]
    assert batch["status"] == "validated"
    assert client.get(base + "/cases").json()["meta"]["inventory_total"] == 0
    committed = client.post(
        base + "/imports/" + batch["id"] + "/commit",
        json={"manifest_hash": batch["manifest_hash"]},
        headers={"Idempotency-Key": uid()},
    )
    assert committed.status_code == 200, committed.text
    revised_manifest = {
        **manifest,
        "cases": [
            {**case, "source_version": "synthetic-v2", "title": case["title"] + " version two"}
            for case in manifest["cases"]
        ],
    }
    revised_preview = client.post(
        base + "/imports/validate", json=revised_manifest, headers={"Idempotency-Key": uid()}
    ).json()["data"]
    assert revised_preview["status"] == "validated"
    revised = client.post(
        base + "/imports/" + revised_preview["id"] + "/commit",
        json={"manifest_hash": revised_preview["manifest_hash"]},
        headers={"Idempotency-Key": uid()},
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["data"]["source_ids"] == committed.json()["data"]["source_ids"]
    ids, cursor = [], None
    while True:
        page = client.get(
            base + "/cases", params={"limit": 25, **({"after": cursor} if cursor else {})}
        )
        assert page.status_code == 200, page.text
        result = page.json()
        assert result["meta"]["inventory_total"] == 200 and result["meta"]["qualified_sources"] == 0
        assert result["meta"]["source_versions"] == 400 and result["meta"]["source_families"] == 100
        ids.extend(row["id"] for row in result["data"])
        cursor = result["meta"]["next_cursor"]
        if not cursor:
            break
    assert len(ids) == len(set(ids)) == 200
    search = client.get(base + "/cases", params={"q": "LOAD-199"}).json()
    assert search["meta"]["matching_total"] == 1 and len(search["data"]) == 1
    assert client.get(base + "/cases", params={"q": "%"}).json()["data"] == []
    assert client.get(base + "/cases", params={"q": "x" * 201}).status_code == 422
    measurements = {}
    for kind, path in [("list", "/cases"), ("detail", "/cases/" + ids[-1])]:
        elapsed = []
        for _ in range(30):
            start = time.perf_counter()
            response = client.get(base + path)
            elapsed.append((time.perf_counter() - start) * 1000)
            assert response.status_code == 200
        measurements[kind] = {
            "samples": 30,
            "p95_ms": sorted(elapsed)[math.ceil(len(elapsed) * 0.95) - 1],
            "max_ms": max(elapsed),
        }
    memory = (
        subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
        if platform.system() == "Darwin"
        else "not_measured"
    )
    evidence = {
        "project_id": project,
        "origin": "synthetic_load_test",
        "source_records": 200,
        "source_versions": 400,
        "source_families": 100,
        "published_tasks": 0,
        "model_performance": "not_measured",
        "concurrency": 1,
        "transport": "in_process_ASGI_with_real_PostgreSQL",
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "ram_bytes": memory,
        "free_disk_bytes": shutil.disk_usage(ROOT).free,
        "measurements": measurements,
        "target_under_500ms": all(m["p95_ms"] < 500 for m in measurements.values()),
        "not_run": ["400_episode_batch", "browser_network_latency"],
    }
    (ROOT / "artifacts/test-runs/inventory-performance.json").write_text(
        json.dumps(evidence, indent=2)
    )
    assert evidence["target_under_500ms"], evidence["measurements"]


def test_graph_old_version_edges_cannot_starve_current_snapshot(monkeypatch):
    import contextlib
    import io

    from anvil import domain
    from anvil.operations import new_demo

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        new_demo("Synthetic graph version-history boundary")
    project = json.loads(captured.getvalue())["project_id"]
    with transaction(project, USERS["researcher"]) as c:
        target = domain.create(c, project, USERS["researcher"], "objective", objective_body())
        source = domain.create(c, project, USERS["researcher"], "objective", objective_body())
        with monkeypatch.context() as patched:
            patched.setattr(domain, "uid", lambda: "11111111" + uid()[8:])
            for revision in range(501):
                source = domain.revise(
                    c,
                    source,
                    USERS["researcher"],
                    {**objective_body(), "title": f"Synthetic historical graph version {revision}"},
                )
            patched.setattr(domain, "uid", lambda: "ffffffff" + uid()[8:])
            source = domain.revise(
                c,
                source,
                USERS["researcher"],
                {**objective_body(), "title": "Current synthetic graph version"},
            )
        c.execute(
            "INSERT INTO anvil.revision_links VALUES(%s,%s,%s,'objective')",
            (project, source["current_revision_id"], target["current_revision_id"]),
        )
        snapshot = graph.canonical(c)
        assert len(snapshot["nodes"]) == 2 and not snapshot["truncated"]
        assert snapshot["edges"] == [
            {
                "source": str(source["current_revision_id"]),
                "target": str(target["current_revision_id"]),
                "relation": "objective",
            }
        ]


def test_logout_invalidates_captured_cookie(client_factory):
    client, _ = client_factory()
    token = client.cookies.get("anvil_session")
    assert client.post("/api/v1/auth/logout").status_code == 200
    client.cookies.set("anvil_session", token)
    assert client.get("/api/v1/me").status_code == 401


@pytest.mark.parametrize(
    "origin,csrf",
    [("https://evil.invalid", "keep"), ("", "keep"), ("http://127.0.0.1:3202", "wrong")],
)
def test_origin_and_csrf(client_factory, origin, csrf):
    client, _ = client_factory()
    headers = {"Origin": origin}
    if csrf != "keep":
        headers["X-CSRF-Token"] = csrf
    assert client.post(BASE + "/objectives", json={}, headers=headers).status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/objectives",
        "/objectives/{id}",
        "/artifacts/{id}/content",
        "/reviews/{id}",
        "/diagnostics",
        "/reports/{id}/download/evidence.zip",
        "/runs/{id}",
    ],
)
def test_cross_project_endpoint_substitution(client_factory, path):
    client, _ = client_factory()
    path = path.replace("{id}", uid())
    result = client.get(f"/api/v1/projects/{OUTSIDER_PROJECT}" + path)
    assert result.status_code == 404, result.text


@pytest.mark.parametrize("role", ["sales", "admin-1"])
def test_content_role_required(client_factory, role):
    client, _ = client_factory(role)
    for path in ("/rubrics", "/cases", "/artifacts/" + uid() + "/content"):
        assert client.get(BASE + path).status_code == 403
    assert client.post(BASE + "/objectives", json={}).status_code == 403


def objective_body():
    return {
        "title": "API security fixture",
        "origin": "adi_initiated",
        "entry_type": "capability",
        "hypothesis": "Known synthetic constraints remain satisfied.",
        "business_context": "Negative API verification, illustrative data only.",
        "measurement_plan": "Synthetic unit of work with independent scoped approval.",
        "researcher_id": USERS["researcher"],
        "advisor_id": USERS["advisor"],
        "product_owner_id": USERS["product-owner"],
    }


def test_idempotency_stale_etag_and_submitted_immutability(client_factory):
    client, _ = client_factory()
    body = objective_body()
    first = client.post(BASE + "/objectives", json=body)
    assert first.status_code == 201, first.text
    original = first.json()["data"]
    replay = client.post(BASE + "/objectives", json=body)
    assert replay.json()["data"]["id"] == original["id"]
    assert (
        client.post(BASE + "/objectives", json={**body, "title": "Changed payload"}).status_code
        == 409
    )
    path = BASE + "/objectives/" + original["id"]
    assert client.patch(path + "/draft", json=body, headers={"If-Match": "999"}).status_code == 412
    submit = client.post(
        path + "/submit", json={}, headers={"If-Match": str(original["row_version"])}
    )
    assert submit.status_code == 200, submit.text
    current = submit.json()["data"]
    assert (
        client.patch(
            path + "/draft", json=body, headers={"If-Match": str(current["row_version"])}
        ).status_code
        == 409
    )


def test_draft_edit_replay_preserves_one_new_revision(client_factory):
    client, _ = client_factory()
    body = objective_body()
    original = client.post(BASE + "/objectives", json=body).json()["data"]
    path = BASE + "/objectives/" + original["id"] + "/draft"
    changed = {**body, "title": "Edited draft with immutable history"}
    headers = {"If-Match": str(original["row_version"]), "Idempotency-Key": uid()}
    response = client.patch(path, json=changed, headers=headers)
    assert response.status_code == 200, response.text
    edited = response.json()["data"]
    assert edited["revision"] == original["revision"] + 1
    assert client.patch(path, json=changed, headers=headers).json()["data"] == edited
    assert client.patch(path, json=body, headers=headers).status_code == 409
    assert (
        client.patch(path, json=changed, headers={**headers, "Idempotency-Key": uid()}).status_code
        == 412
    )
    with transaction(PROJECT, USERS["researcher"]) as c:
        versions = c.execute(
            "SELECT content FROM anvil.revisions WHERE resource_id=%s ORDER BY revision",
            (original["id"],),
        ).fetchall()
    assert len(versions) == 2
    assert versions[0]["content"] == body
    assert versions[1]["content"] == changed


def test_readiness_gap_is_scoped_versioned_and_blocks_launch(client_factory):
    from anvil.db import one

    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    project = journey["project_id"]
    base = f"/api/v1/projects/{project}"
    engineer = client_factory("data-engineer")[0]
    researcher = client_factory("researcher")[0]
    with transaction(project, USERS["researcher"]) as c:
        source = one(
            c,
            "SELECT r.id,r.current_revision_id FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE r.kind='case' AND v.content->>'external_case_id'='MKT-001'",
        )
    path = base + "/cases/" + str(source["id"]) + "/readiness"
    initial = engineer.get(path).json()["data"]
    assert initial["local_blockers"] == []
    assert (
        next(x for x in initial["items"] if x["item_key"] == "external_processing_rights")["status"]
        == "missing"
    )
    assert client_factory("sales")[0].get(path).status_code == 403
    assert client_factory("outsider")[0].get(path).status_code == 404
    item = next(x for x in initial["items"] if x["item_key"] == "actor_inputs")
    body = {
        "source_revision_id": str(source["current_revision_id"]),
        "status": "missing",
        "explanation": "Synthetic missing-exhibit gate exercise",
        "owner_user_id": USERS["data-engineer"],
        "evidence_ids": [],
    }
    headers = {"If-Match": str(item["row_version"]), "Idempotency-Key": uid()}
    assert researcher.patch(path + "/actor_inputs", json=body, headers=headers).status_code == 403
    assert (
        client_factory("reviewer-2")[0]
        .patch(path + "/actor_inputs", json=body, headers=headers)
        .status_code
        == 403
    )
    assert (
        engineer.patch(path + "/evaluation_rights", json=body, headers=headers).status_code == 422
    )
    assert (
        engineer.patch(
            path + "/actor_inputs", json={**body, "evidence_ids": [uid()]}, headers=headers
        ).status_code
        == 422
    )
    missing = engineer.patch(path + "/actor_inputs", json=body, headers=headers)
    assert missing.status_code == 200, missing.text
    assert "actor_inputs" in missing.json()["data"]["local_blockers"]
    assert (
        engineer.patch(path + "/actor_inputs", json=body, headers=headers).json()["data"]
        == missing.json()["data"]
    )
    run = researcher.post(
        base + "/runs",
        json={"protocol_revision_id": journey["protocol"]["current_revision_id"]},
        headers={"Idempotency-Key": uid()},
    ).json()["data"]
    blocked = researcher.post(
        base + "/runs/" + run["id"] + "/launch",
        json={},
        headers={"Idempotency-Key": uid(), "If-Match": str(run["row_version"])},
    )
    assert blocked.status_code == 409 and "readiness" in blocked.text
    assert researcher.get(base + "/runs/" + run["id"]).json()["data"]["episodes"] == []
    item = next(x for x in missing.json()["data"]["items"] if x["item_key"] == "actor_inputs")
    resolved = {
        **body,
        "status": "available",
        "explanation": "Verified both original actor artifacts for this synthetic source.",
        "evidence_ids": [
            str(x["id"]) for x in initial["evidence_options"] if x["classification"] == "actor"
        ],
    }
    assert (
        engineer.patch(
            path + "/actor_inputs", json=resolved, headers={**headers, "Idempotency-Key": uid()}
        ).status_code
        == 412
    )
    result = engineer.patch(
        path + "/actor_inputs",
        json=resolved,
        headers={"Idempotency-Key": uid(), "If-Match": str(item["row_version"])},
    )
    assert result.status_code == 200, result.text
    assert result.json()["data"]["local_blockers"] == []
    with transaction(project, USERS["researcher"]) as c:
        from anvil import domain

        domain.current_source(c, source["current_revision_id"])


def test_cross_project_mutation_matrix_preserves_foreign_records(client_factory):
    from anvil.db import digest

    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    foreign_project = journey["project_id"]
    assert foreign_project != PROJECT
    clients = {
        name: client_factory(name)[0]
        for name in [
            "researcher",
            "data-engineer",
            "reviewer-1",
            "adjudicator",
            "product-owner",
            "sales",
        ]
    }
    with transaction(foreign_project, USERS["researcher"]) as c:
        resources = c.execute(
            "SELECT id,kind,current_revision_id,row_version,lifecycle FROM anvil.resources WHERE kind IN ('objective','case','rubric','task','suite','protocol','finding','report') ORDER BY id"
        ).fetchall()
        episode = c.execute(
            "SELECT id FROM anvil.episodes WHERE run_id=%s LIMIT 1", (journey["run_id"],)
        ).fetchone()["id"]
        artifact = c.execute("SELECT id FROM anvil.artifacts LIMIT 1").fetchone()["id"]
    checks = 0
    for row in resources:
        collection = {
            "case": "cases",
            "objective": "objectives",
            "rubric": "rubrics",
            "task": "tasks",
            "suite": "suites",
            "protocol": "protocols",
            "finding": "findings",
            "report": "reports",
        }[row["kind"]]
        path = BASE + "/" + collection + "/" + str(row["id"])
        commands = [
            ("researcher", "GET", "", None),
            ("researcher", "PATCH", "/draft", {}),
            ("researcher", "POST", "/successor", {}),
            ("researcher", "POST", "/submit", {}),
            ("data-engineer", "POST", "/publish", {}),
            ("researcher", "POST", "/freeze", {}),
            (
                "researcher",
                "POST",
                "/withdraw",
                {"reason": "Synthetic cross-project negative verification"},
            ),
            (
                "reviewer-1",
                "POST",
                "/decisions",
                {
                    "purpose": "content",
                    "decision": "approve",
                    "rationale": "Synthetic cross-project negative verification",
                },
            ),
        ]
        for user, method, suffix, body in commands:
            response = clients[user].request(
                method,
                path + suffix,
                json=body,
                headers={"Idempotency-Key": uid(), "If-Match": str(row["row_version"])},
            )
            assert response.status_code == 404, (
                collection,
                suffix,
                response.status_code,
                response.text,
            )
            checks += 1
    for action in ["launch", "cancel"]:
        response = clients["researcher"].post(
            BASE + "/runs/" + journey["run_id"] + "/" + action,
            json={},
            headers={"If-Match": "1", "Idempotency-Key": uid()},
        )
        assert response.status_code == 404
    for user, action, body in [
        (
            "reviewer-1",
            "assessments",
            {
                "scores": {"R1": 4},
                "critical": [],
                "evidence": {"R1": "Synthetic"},
                "rationale": "Synthetic cross-project judgment",
            },
        ),
        (
            "adjudicator",
            "adjudicate",
            {
                "scores": {"R1": 4},
                "critical": [],
                "evidence": {"R1": "Synthetic"},
                "rationale": "Synthetic cross-project judgment",
            },
        ),
        (
            "reviewer-1",
            "review-issues",
            {"code": "ambiguous_reference", "rationale": "Synthetic cross-project issue"},
        ),
        (
            "adjudicator",
            "resolve-issue",
            {"decision": "invalid", "rationale": "Synthetic cross-project resolution"},
        ),
    ]:
        response = clients[user].post(
            BASE + "/episodes/" + str(episode) + "/" + action,
            json=body,
            headers={"If-Match": "1", "Idempotency-Key": uid()},
        )
        assert response.status_code == 404, response.text
    assert (
        clients["data-engineer"].get(BASE + "/artifacts/" + str(artifact) + "/content").status_code
        == 404
    )
    assert clients["reviewer-1"].get(BASE + "/reviews/" + str(episode)).status_code == 404
    assert (
        clients["sales"]
        .get(BASE + "/reports/" + journey["report"]["id"] + "/download/sales-kit.pdf")
        .status_code
        == 404
    )
    assert checks >= 8 * 8
    with transaction(foreign_project, USERS["researcher"]) as c:
        after = c.execute(
            "SELECT id,kind,current_revision_id,row_version,lifecycle FROM anvil.resources WHERE kind IN ('objective','case','rubric','task','suite','protocol','finding','report') ORDER BY id"
        ).fetchall()
    assert digest(json.loads(json.dumps(resources, default=str))) == digest(
        json.loads(json.dumps(after, default=str))
    )


def test_manifest_dryrun_atomic_commit_dedup_and_quarantine(client_factory):
    client, _ = client_factory("data-engineer")
    with transaction(PROJECT, USERS["data-engineer"]) as c:
        clean = store(
            c, PROJECT, b'{"synthetic_test":true}', "actor", origin="original_synthetic_fixture"
        )
        quarantine = store(c, PROJECT, b"untrusted test bytes", "internal", scan="quarantined")
        before = c.execute("SELECT count(*) n FROM anvil.resources WHERE kind='case'").fetchone()[
            "n"
        ]
    case = {
        "external_case_id": uid(),
        "source_version": "1",
        "title": "Synthetic import test",
        "subjects": ["Test"],
        "source_family_key": "test",
        "artifact_ids": [clean],
        "provenance": {"origin": "synthetic_fixture", "faculty_review_claim": None},
    }
    manifest = {
        "schema_version": "anvil.case_import.v1",
        "partner_key": "integration-fixture",
        "cases": [case],
    }

    def preview(value):
        response = client.post(
            BASE + "/imports/validate", json=value, headers={"Idempotency-Key": uid()}
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]

    def commit(batch):
        return client.post(
            BASE + "/imports/" + batch["id"] + "/commit",
            json={"manifest_hash": batch["manifest_hash"]},
            headers={"Idempotency-Key": uid()},
        )

    rejected = preview(
        {
            **manifest,
            "cases": [case, {**case, "external_case_id": uid(), "artifact_ids": [quarantine]}],
        }
    )
    assert rejected["status"] == "rejected" and rejected["errors"][0]["row"] == 1
    assert commit(rejected).status_code == 409
    batch = preview(manifest)
    assert batch["status"] == "validated"
    with transaction(PROJECT, USERS["data-engineer"]) as c:
        assert (
            c.execute("SELECT count(*) n FROM anvil.resources WHERE kind='case'").fetchone()["n"]
            == before
        )
    first = commit(batch)
    assert first.status_code == 200, first.text
    ids = first.json()["data"]["source_ids"]
    assert commit(batch).json()["data"]["source_ids"] == ids
    assert commit(preview(manifest)).json()["data"]["source_ids"] == ids
    source = client.get(BASE + "/cases/" + ids[0]).json()["data"]
    assert source["content"]["faculty_validation"] is None
    assert source["content"]["rights_status"] == "unknown"
    assert source["rights"] == []
    owner, _ = client_factory("product-owner")
    grant_body = {
        "operation": "managed_evaluation",
        "destination": "local_fixture",
        "status": "approved",
        "evidence": "Independent synthetic first-version rights review for version-isolation testing.",
    }
    grant_headers = {"Idempotency-Key": uid(), "If-Match": str(source["row_version"])}
    grant = owner.post(
        BASE + "/cases/" + ids[0] + "/rights", json=grant_body, headers=grant_headers
    )
    assert grant.status_code == 200, grant.text
    old_revision = source["current_revision_id"]
    gap_body = {
        "source_revision_id": old_revision,
        "status": "missing",
        "explanation": "Synthetic first-version gap remains in its historical record",
        "evidence_ids": [],
    }
    gap_path = BASE + "/cases/" + ids[0] + "/readiness/actor_inputs"
    assert (
        client.patch(
            gap_path, json=gap_body, headers={"Idempotency-Key": uid(), "If-Match": "0"}
        ).status_code
        == 200
    )
    second = commit(
        preview(
            {
                **manifest,
                "cases": [
                    {**case, "source_version": "2", "title": "Synthetic corrected source version"}
                ],
            }
        )
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["source_ids"] == ids
    new_revision = second.json()["data"]["source_revision_ids"][0]
    readiness = client.get(BASE + "/cases/" + ids[0] + "/readiness").json()["data"]
    assert all(item["declared_status"] is None for item in readiness["items"])
    assert (
        client.patch(
            gap_path, json=gap_body, headers={"Idempotency-Key": uid(), "If-Match": "1"}
        ).status_code
        == 409
    )
    researcher = client_factory("researcher")[0]
    template = researcher.get(BASE + "/tasks?limit=100").json()["data"][0]["content"]
    draft = researcher.post(
        BASE + "/tasks",
        json={
            **template,
            "title": "Cannot relabel a partner source as an original fixture",
            "source_revision_id": new_revision,
        },
        headers={"Idempotency-Key": uid()},
    ).json()["data"]
    rejected_origin = researcher.post(
        BASE + "/tasks/" + draft["id"] + "/submit",
        json={},
        headers={"Idempotency-Key": uid(), "If-Match": str(draft["row_version"])},
    )
    assert rejected_origin.status_code == 409 and "source origin" in rejected_origin.text
    assert new_revision != old_revision
    current = client.get(BASE + "/cases/" + ids[0]).json()["data"]
    assert current["current_revision_id"] == new_revision and current["rights"] == []
    replay = owner.post(
        BASE + "/cases/" + ids[0] + "/rights", json=grant_body, headers=grant_headers
    )
    assert replay.status_code == 200 and replay.json()["data"] == grant.json()["data"]
    assert replay.json()["data"]["source_revision_id"] == old_revision
    assert client.get(BASE + "/cases/" + ids[0]).json()["data"]["rights"] == []
    assert (
        current["content"]["faculty_validation"] is None
        and current["content"]["qualification"] == "not_reviewed"
    )
    assert commit(preview(manifest)).json()["data"]["source_revision_ids"] == [old_revision]
    assert (
        client.get(BASE + "/cases/" + ids[0]).json()["data"]["current_revision_id"] == new_revision
    )
    from fastapi import HTTPException

    from anvil import domain

    with transaction(PROJECT, USERS["data-engineer"]) as c:
        assert domain.rights_ok(c, old_revision) and not domain.rights_ok(c, new_revision)
        assert domain.get_revision(c, old_revision)["content"]["title"] == case["title"]
        with pytest.raises(HTTPException, match="Source was superseded"):
            domain.current_source(c, old_revision)
        assert str(domain.current_source(c, new_revision)["id"]) == new_revision
    from datetime import datetime, timedelta, timezone

    expiry_body = {
        **grant_body,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    expiring = owner.post(
        BASE + "/cases/" + ids[0] + "/rights",
        json=expiry_body,
        headers={"Idempotency-Key": uid(), "If-Match": str(current["row_version"])},
    )
    assert expiring.status_code == 200, expiring.text
    with transaction(PROJECT, USERS["product-owner"]) as c:
        assert domain.rights_ok(c, new_revision)
        c.execute(
            "UPDATE anvil.rights_grants SET expires_at=now()-interval '1 second' WHERE source_revision_id=%s",
            (new_revision,),
        )
        assert not domain.rights_ok(c, new_revision)
    conflict = preview({**manifest, "cases": [{**case, "title": "Changed original"}]})
    assert conflict["status"] == "rejected"
    assert conflict["errors"][0]["code"] == "source_version_conflict"
    duplicate = preview({**manifest, "cases": [case, case]})
    assert any(e["code"] == "duplicate_external_id" for e in duplicate["errors"])
    with transaction(PROJECT, USERS["data-engineer"]) as c:
        assert (
            c.execute("SELECT count(*) n FROM anvil.resources WHERE kind='case'").fetchone()["n"]
            == before + 1
        )


def test_graph_rebuild_replay_and_unavailable_fallback(client_factory, monkeypatch):
    client, _ = client_factory()
    first = graph.project_graph(PROJECT)
    second = graph.project_graph(PROJECT)
    assert first == second
    result = client.get(BASE + "/diagnostics").json()["data"]
    assert result["projection_status"] == "current"
    assert result["nodes"] == first["nodes"]
    assert all(n["kind"] != "rubric" for n in result["nodes"])
    root_id = result["edges"][0]["source"]
    neighborhood = client.get(BASE + "/graph", params={"root": root_id, "depth": 1}).json()["data"]
    expected = {root_id}
    expected.update(e["target"] for e in result["edges"] if e["source"] == root_id)
    expected.update(e["source"] for e in result["edges"] if e["target"] == root_id)
    assert {n["id"] for n in neighborhood["nodes"]} == expected
    assert client.get(BASE + "/graph", params={"root": uid()}).status_code == 404

    def unavailable():
        raise ServiceUnavailable("Controlled graph outage")

    monkeypatch.setattr(graph, "driver", unavailable)
    fallback = client.get(BASE + "/diagnostics").json()["data"]
    assert fallback["projection_status"] == "unavailable"
    assert fallback["nodes"] == result["nodes"] and fallback["edges"] == result["edges"]
    assert client.get(BASE + "/diagnostics?depth=4").status_code == 422


def test_successor_and_withdrawal_preserve_history(client_factory):
    client, _ = client_factory()
    body = objective_body()
    original = client.post(BASE + "/objectives", json=body).json()["data"]
    path = BASE + "/objectives/" + original["id"]
    submitted = client.post(
        path + "/submit", json={}, headers={"If-Match": str(original["row_version"])}
    ).json()["data"]
    successor = client.post(
        path + "/successor",
        json={**body, "title": "Revised synthetic question"},
        headers={"If-Match": str(submitted["row_version"])},
    ).json()["data"]
    assert successor["lifecycle"] == "draft"
    assert successor["current_revision_id"] != original["current_revision_id"]
    with transaction(PROJECT, USERS["researcher"]) as c:
        old = c.execute(
            "SELECT content FROM anvil.revisions WHERE id=%s", (original["current_revision_id"],)
        ).fetchone()
        assert old["content"]["title"] == body["title"]
    withdrawn = client.post(
        path + "/withdraw",
        json={"reason": "Synthetic correction requires withdrawal"},
        headers={"If-Match": str(successor["row_version"])},
    ).json()["data"]
    assert withdrawn["lifecycle"] == "withdrawn"
    graph_data = client.get(BASE + "/diagnostics").json()["data"]
    assert not any(n["resource_id"] == original["id"] for n in graph_data["nodes"])


@pytest.mark.parametrize(
    "invalid", ["issuer", "audience", "nonce", "expired", "signature", "none", "valid"]
)
def test_signed_oidc_claim_validation(client_factory, monkeypatch, invalid):
    client, _ = client_factory()
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with transaction() as c:
        c.execute(
            "INSERT INTO anvil.oidc_login_attempts(state_hash,nonce_hash,verifier_cipher) VALUES(%s,%s,%s)",
            (
                hashed(state),
                hashed(nonce),
                auth.cipher().encrypt(b"synthetic-test-verifier").decode(),
            ),
        )
    client.cookies.set("anvil_login", state)
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    claims = {
        "iss": setting("OIDC_ISSUER"),
        "aud": setting("OIDC_CLIENT_ID"),
        "sub": USERS["researcher"],
        "exp": int(time.time()) + 60,
        "nonce": nonce,
    }
    if invalid == "issuer":
        claims["iss"] = "https://untrusted.invalid"
    if invalid == "audience":
        claims["aud"] = "different-client"
    if invalid == "nonce":
        claims["nonce"] = "wrong-nonce"
    if invalid == "expired":
        claims["exp"] = int(time.time()) - 60
    signing_key = (
        JsonWebKey.generate_key("RSA", 2048, is_private=True) if invalid == "signature" else key
    )
    if invalid == "none":
        import base64

        def encoded(b):
            return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

        token = encoded(b'{"alg":"none"}') + "." + encoded(json.dumps(claims).encode()) + "."
    else:
        token = JsonWebToken(["RS256"]).encode({"alg": "RS256"}, claims, signing_key).decode()

    class MockOIDC:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            return httpx.Response(200, json={"id_token": token}, request=httpx.Request("POST", url))

        def get(self, url):
            return httpx.Response(
                200,
                json={"keys": [key.as_dict(is_private=False)]},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(auth.httpx, "Client", MockOIDC)
    response = client.get(
        "/api/v1/auth/callback", params={"state": state, "code": "test"}, follow_redirects=False
    )
    assert response.status_code == (307 if invalid == "valid" else 401), response.text
    assert (
        client.get(
            "/api/v1/auth/callback", params={"state": state, "code": "test"}, follow_redirects=False
        ).status_code
        == 401
    )
    if invalid == "valid":
        with transaction() as c:
            c.execute(
                "UPDATE anvil.sessions SET revoked_at=now() WHERE token_hash=%s",
                (hashed(response.cookies.get("anvil_session")),),
            )


def test_fixture_delivery_bound_approval_unknown_replay_and_suppression(
    client_factory, monkeypatch
):
    from anvil import delivery

    # Prevent background pickup so revocation can be exercised between queue and worker.
    monkeypatch.setattr(delivery, "enqueue", lambda *args: None)
    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    project = journey.get("project_id", PROJECT)
    base = f"/api/v1/projects/{project}"
    clients = {
        name: client_factory(name)[0]
        for name in [
            "researcher",
            "advisor",
            "reviewer-1",
            "product-owner",
            "sales",
            "admin-1",
            "admin-2",
        ]
    }

    def post(name, path, body, version=None, expected=200):
        headers = {"Idempotency-Key": uid()}
        if version:
            headers["If-Match"] = str(version)
        result = clients[name].post(base + path, json=body, headers=headers)
        assert result.status_code == expected, result.text
        return result.json().get("data")

    report = post(
        "researcher",
        "/reports",
        {
            "title": "Fixture delivery guard test",
            "run_id": journey["run_id"],
            "finding_revision_ids": [],
            "advisor_id": USERS["advisor"],
            "reviewer_id": USERS["reviewer-1"],
            "product_owner_id": USERS["product-owner"],
            "audience": "internal_fixture",
        },
        expected=201,
    )
    path = "/reports/" + report["id"]
    report = post("researcher", path + "/submit", {}, report["row_version"])
    for role, purpose in [
        ("advisor", "technical"),
        ("reviewer-1", "domain"),
        ("product-owner", "audience"),
        ("product-owner", "release"),
    ]:
        report = post(
            role,
            path + "/decisions",
            {
                "purpose": purpose,
                "decision": "approve",
                "rationale": "Independent synthetic delivery pipeline verification.",
            },
            report["row_version"],
        )
    kit = post("researcher", path + "/build", {}, report["row_version"])
    post(
        "sales",
        "/sales-contacts",
        {
            "name": "Synthetic recipient",
            "email": "real@example.com",
            "organization_label": "Fixture",
            "contact_basis": "Synthetic fixture only",
        },
        expected=422,
    )
    for scenario in ("accepted", "failed", "unknown", "suppressed"):
        contact = post(
            "sales",
            "/sales-contacts",
            {
                "name": "Synthetic recipient",
                "email": "test@fixture.invalid",
                "organization_label": "Fixture",
                "contact_basis": "Synthetic test, no real contact or sending authority.",
            },
        )
        contact = post(
            "product-owner",
            "/sales-contacts/" + contact["id"] + "/decision",
            {"status": "approved"},
            contact["row_version"],
        )
        sender = post(
            "admin-1",
            "/fixture-senders",
            {
                "name": "Network-free test sender",
                "scenario": "accepted" if scenario == "suppressed" else scenario,
            },
        )
        post(
            "admin-1",
            "/fixture-senders/" + sender["id"] + "/activate",
            {},
            sender["row_version"],
            expected=409,
        )
        sender = post(
            "admin-2", "/fixture-senders/" + sender["id"] + "/activate", {}, sender["row_version"]
        )
        approval_body = {
            "recipient_contact_id": contact["id"],
            "sender_connection_id": sender["id"],
        }
        approval = post(
            "product-owner", "/sales-kits/" + kit["id"] + "/delivery-approvals", approval_body
        )
        send_body = {
            "delivery_approval_id": approval["id"],
            "content_hash": approval["content_hash"],
        }
        record = post("sales", "/sales-kits/" + kit["id"] + "/simulate-send", send_body)
        if scenario == "suppressed":
            post(
                "product-owner",
                "/sales-contacts/" + contact["id"] + "/decision",
                {"status": "suppressed"},
                contact["row_version"],
            )
        job = {"target_id": record["id"], "project_id": project}
        with transaction(project, worker=True) as c:
            delivery.dispatch_fixture(c, job)
            delivery.dispatch_fixture(c, job)
        state = clients["sales"].get(base + "/sales-deliveries/" + record["id"]).json()["data"]
        assert state["status"] == ("blocked" if scenario == "suppressed" else "fixture_" + scenario)
        assert state["attempts"] == (0 if scenario == "suppressed" else 1)
        assert state["real_email_sent"] is False
        if scenario != "suppressed":
            new_approval = post(
                "product-owner", "/sales-kits/" + kit["id"] + "/delivery-approvals", approval_body
            )
            replay = post(
                "sales",
                "/sales-kits/" + kit["id"] + "/simulate-send",
                {
                    "delivery_approval_id": new_approval["id"],
                    "content_hash": new_approval["content_hash"],
                },
            )
            assert replay["id"] == record["id"]


@pytest.mark.parametrize(
    "filename,payload,mime",
    [
        ("../../escape.exe", b"MZ harmless non-executable test bytes", "application/pdf"),
        (
            "macro.docm",
            b"PK\\x03\\x04 harmless macro-container marker",
            "application/vnd.ms-word.document.macroEnabled.12",
        ),
        ("bomb.zip", b"PK\\x03\\x04 truncated archive; never decompressed", "application/zip"),
        ("mismatch.png", b"not an image", "image/png"),
    ],
)
def test_untrusted_uploads_stay_quarantined_without_parsing(
    client_factory, filename, payload, mime
):
    client, _ = client_factory("data-engineer")
    response = client.post(BASE + "/artifacts", files={"file": (filename, payload, mime)})
    assert response.status_code == 200, response.text
    artifact = response.json()["data"]
    assert artifact["scan_status"] == "quarantined"
    assert client.get(BASE + "/artifacts/" + artifact["id"] + "/content").status_code == 403
    with transaction(PROJECT, USERS["data-engineer"]) as c:
        row = c.execute(
            "SELECT object_key,scan_status FROM anvil.artifacts WHERE id=%s", (artifact["id"],)
        ).fetchone()
        assert ".." not in row["object_key"] and filename not in row["object_key"]


def test_oversized_upload_rejected_before_artifact_storage(client_factory):
    client, _ = client_factory("data-engineer")
    with transaction(PROJECT, USERS["data-engineer"]) as c:
        before = c.execute("SELECT count(*) n FROM anvil.artifacts").fetchone()["n"]
    response = client.post(
        BASE + "/artifacts",
        files={"file": ("oversized.txt", b"x" * (26 * 1024 * 1024), "text/plain")},
    )
    assert response.status_code == 413
    with transaction(PROJECT, USERS["data-engineer"]) as c:
        assert c.execute("SELECT count(*) n FROM anvil.artifacts").fetchone()["n"] == before


def test_task_missing_duplicate_cross_source_and_unsupported_inputs(client_factory):
    client, _ = client_factory()
    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    base = f"/api/v1/projects/{journey['project_id']}"
    tasks = [
        t
        for t in client.get(base + "/tasks?limit=100").json()["data"]
        if t["lifecycle"] == "published"
    ]
    source = tasks[0]["content"]
    for body in (
        {**source, "actor_artifact_ids": source["actor_artifact_ids"][:1]},
        {**source, "actor_artifact_ids": [source["actor_artifact_ids"][0]] * 2},
    ):
        assert (
            client.post(base + "/tasks", json=body, headers={"Idempotency-Key": uid()}).status_code
            == 422
        )
    for body in (
        {**source, "mode": "interactive"},
        {
            **source,
            "actor_artifact_ids": [
                tasks[1]["content"]["actor_artifact_ids"][0],
                source["actor_artifact_ids"][1],
            ],
        },
    ):
        response = client.post(base + "/tasks", json=body, headers={"Idempotency-Key": uid()})
        assert response.status_code == 201, response.text
        draft = response.json()["data"]
        rejected = client.post(
            base + "/tasks/" + draft["id"] + "/submit",
            json={},
            headers={"Idempotency-Key": uid(), "If-Match": str(draft["row_version"])},
        )
        assert rejected.status_code == 409, rejected.text


def test_invalid_and_reused_login_state(client_factory):
    client, _ = client_factory()
    assert client.get("/api/v1/auth/callback?state=bad&code=bad").status_code == 401
    state = secrets.token_urlsafe(32)
    with transaction() as c:
        c.execute(
            "INSERT INTO anvil.oidc_login_attempts(state_hash,nonce_hash,verifier_cipher,consumed_at) VALUES(%s,%s,%s,now())",
            (hashed(state), hashed("nonce"), "unused"),
        )
    client.cookies.set("anvil_login", state)
    assert (
        client.get("/api/v1/auth/callback", params={"state": state, "code": "unused"}).status_code
        == 401
    )
