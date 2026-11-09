"""Actual local capture/evaluation/export flow and authority boundaries."""

import io
import json
import zipfile
from uuid import uuid4

import pytest
from pypdf import PdfReader
from test_benchmark_pipeline import login
from test_private_storage import connection
from test_private_storage import lab as storage_lab

from anvil import benchmark_business_fixture as fixture
from anvil import benchmark_project_import as imports
from anvil.benchmark_run_worker import claim, process

lab = storage_lab


@pytest.mark.parametrize("identity", ["admin", "engineer"])
def test_complete_flow(lab, identity, monkeypatch):
    monkeypatch.setenv("ANVIL_BENCHMARK_REHEARSAL_ENABLED", "true")
    client = login(lab, identity)
    base = f"/api/v1/projects/{lab['project']}/workspace/benchmark"
    imported = client.post(
        base + "/import", content=fixture.bundle(), headers={"content-type": "application/zip"}
    )
    assert imported.status_code == 200, imported.text
    group = imported.json()["data"]
    assert len(group["tasks"]) == 3
    assert "reference_output" not in imported.text
    mapped = client.post(base + f"/groups/{group['id']}/sample-verifiers?adapter=zen")
    assert mapped.status_code == 200, mapped.text
    body = {
        "name": "Actual fictional flow",
        "task_group_id": group["id"],
        "task_ids": [t["task_id"] for t in group["tasks"]],
        "models": [m["id"] for m in fixture.MODELS],
        "environment_ids": [e["id"] for e in group["environments"]],
        "method_ids": ["task-rubric-v1", "safety-observed-v1", "custom-gdpval-v1"],
        "repetitions": 1,
    }
    saved = client.post(base + "/plans", json=body, headers={"idempotency-key": uuid4().hex})
    assert saved.status_code == 200, saved.text
    plan = saved.json()["data"]
    started = client.post(
        base + "/runs",
        json={"plan_id": plan["id"], "expected_plan_sha256": plan["snapshot_sha256"]},
        headers={"idempotency-key": uuid4().hex},
    )
    assert started.status_code == 200, started.text
    run = started.json()["data"]
    job = claim()
    assert str(job["run_id"]) == run["id"]
    process(job)
    response = client.get(base + "/runs/" + run["id"])
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["run"]["state"] == "completed"
    assert len(data["cells"]) == 18
    assert len(data["series"]) == 3
    assert all(len(s["axes"]) == 6 for s in data["series"])
    assert data["run"]["provider_calls"] == 0
    assert data["run"]["model_performance"] is False
    assert data["selected_cell"]["id"] == data["cells"][0]["id"]
    assert any(f["outcome"] == "fail" for f in data["failures"]["policy_findings"])
    permissive = next(s for s in data["series"] if s["model_key"] == "fictional-permissive-v1")
    assert permissive["axes"][4]["value"] == 0
    assert permissive["axes"][5]["value"] == 50
    assert any(
        f["rule_id"] == "destinations" and f["outcome"] == "fail"
        for f in data["failures"]["policy_findings"]
    )
    assert all(
        r["sample"]["example_response"]["status"] == "observed_software_example"
        and not r["sample"]["example_response"]["human_verified"]
        for r in data["remediation"]
    )
    if identity == "engineer":
        assert not data["run"]["report_review"]["ready"]
        assert (
            client.get(
                base + f"/runs/{run['id']}/export?expected_view_sha256={data['view_sha256']}"
            ).status_code
            == 409
        )
        admin = login(lab, "admin")
        approved = admin.post(
            base + f"/runs/{run['id']}/review",
            json={
                "decision": "admin_approved",
                "expected_result_sha256": data["run"]["result_sha256"],
                "rationale": "Actual test actor reviews this exact software result.",
            },
        )
        assert approved.status_code == 200, approved.text
        data = client.get(base + "/runs/" + run["id"]).json()["data"]
    assert data["run"]["report_review"]["ready"]
    pdf = client.get(base + f"/runs/{run['id']}/export?expected_view_sha256={data['view_sha256']}")
    assert pdf.status_code == 200, pdf.text[:100]
    reader = PdfReader(io.BytesIO(pdf.content))
    assert len(reader.pages) >= 5
    text = " ".join(p.extract_text() for p in reader.pages)
    assert "Environment containment" in text and "Appendix: all Task rubrics" in text
    assert "Not run" in text or "not_run" in text
    assert (
        client.get(base + f"/runs/{run['id']}/export?expected_view_sha256={'0' * 64}").status_code
        == 409
    )
    filtered = client.get(
        base + f"/runs/{run['id']}?model=fictional-compliant-v1&environment=enforced-v1"
    ).json()["data"]
    assert len(filtered["cells"]) == 3
    assert len(filtered["series"]) == 1
    outsider = login(lab, "outsider")
    assert outsider.get(base + "/runs/" + run["id"]).status_code == 404
    with connection("anvil_app", lab["project"], lab[identity]) as c:
        with pytest.raises(Exception):
            c.execute(
                "UPDATE anvil.benchmark_runs SET admin_execution=true WHERE id=%s", (run["id"],)
            )


def test_import_fixture_is_versioned_and_candidate_safe():
    content, policies = imports.parse(fixture.bundle())
    assert len(content["tasks"]) == 3 and policies
    assert all("reference_output" not in str(t["actor"]) for t in content["tasks"])
    with pytest.raises(Exception):
        imports.parse(b"invalid archive")


def test_import_errors_and_report_policy_roles(lab):
    client = login(lab, "admin")
    base = f"/api/v1/projects/{lab['project']}/workspace/benchmark"
    invalid = client.post(
        base + "/import", content=b"invalid ZIP", headers={"content-type": "application/zip"}
    )
    assert invalid.status_code == 422
    changed = client.post(
        base + "/report-policy",
        json={
            "required_reviewers": 0,
            "rationale": "Actual Admin configures zero report reviewers.",
        },
    )
    assert changed.status_code == 200, changed.text
    assert client.get(base).json()["data"]["report_policy"]["required_reviewers"] == 0
    engineer = login(lab, "engineer")
    denied = engineer.post(
        base + "/report-policy",
        json={
            "required_reviewers": 3,
            "rationale": "Engineer cannot change the report review policy.",
        },
    )
    assert denied.status_code == 403


def test_custom_judge_weights_do_not_relabel_original_scoring(lab):
    client = login(lab, "engineer")
    base = f"/api/v1/projects/{lab['project']}/workspace/benchmark"
    original = client.post(
        base + "/methods",
        json={"name": "Original suite configuration", "method_key": "gdpval-aa-2.1"},
        headers={"idempotency-key": uuid4().hex},
    )
    assert original.status_code == 200
    saved = original.json()["data"]["configured"][0]
    assert "judge_weights" not in saved["configuration"]
    changed = client.post(
        base + "/methods",
        json={
            "name": "Cannot change original",
            "method_key": "gdpval-aa-2.1",
            "instruction_weight": 50,
            "accuracy_weight": 25,
            "tone_weight": 25,
        },
        headers={"idempotency-key": uuid4().hex},
    )
    assert changed.status_code == 422


def test_chunked_collection_limit_returns_413(lab):
    client = login(lab, "admin")
    base = f"/api/v1/projects/{lab['project']}/workspace/benchmark"
    response = client.post(
        base + "/import",
        content=(b"x" * (13 * 1024 * 1024) for _ in range(3)),
        headers={"content-type": "application/zip"},
    )
    assert response.status_code == 413


@pytest.mark.parametrize("path", ["../project.json", "/project.json", "tasks/../project.json"])
def test_collection_rejects_unsafe_paths(path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr(path, b"{}")
    with pytest.raises(ValueError, match="Unsafe"):
        imports.parse(stream.getvalue())


def test_optional_policy_absence_is_na_not_fake_pass(lab):
    files = imports.archive_files(fixture.bundle())
    manifest = json.loads(files["project.json"])
    manifest.pop("policy_manifest_path")
    files = {k: v for k, v in files.items() if not k.startswith("policies/") and k != "policy.json"}
    files["project.json"] = json.dumps(manifest).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    client = login(lab, "admin")
    base = f"/api/v1/projects/{lab['project']}/workspace/benchmark"
    group = client.post(
        base + "/import", content=stream.getvalue(), headers={"content-type": "application/zip"}
    ).json()["data"]
    body = {
        "name": "No optional policy",
        "task_group_id": group["id"],
        "task_ids": ["KYC-001"],
        "models": [fixture.MODELS[0]["id"]],
        "environment_ids": [group["environments"][0]["id"]],
        "method_ids": ["task-rubric-v1", "safety-observed-v1"],
        "repetitions": 1,
    }
    plan = client.post(base + "/plans", json=body, headers={"idempotency-key": uuid4().hex}).json()[
        "data"
    ]
    run = client.post(
        base + "/runs",
        json={"plan_id": plan["id"], "expected_plan_sha256": plan["snapshot_sha256"]},
        headers={"idempotency-key": uuid4().hex},
    ).json()["data"]
    process(claim())
    view = client.get(base + "/runs/" + run["id"]).json()["data"]
    policy = view["series"][0]["axes"][3]
    assert policy["value"] is None and policy["availability"] == "not_applicable"


def prepare(lab, mapped=False):
    client = login(lab, "admin")
    base = f"/api/v1/projects/{lab['project']}/workspace/benchmark"
    group = client.post(base + "/sample").json()["data"]
    if mapped:
        response = client.post(base + f"/groups/{group['id']}/sample-verifiers?adapter=builtin")
        assert response.status_code == 200, response.text
    body = {
        "name": "Guard cases",
        "task_group_id": group["id"],
        "task_ids": [t["task_id"] for t in group["tasks"]],
        "models": [fixture.MODELS[0]["id"]],
        "environment_ids": [group["environments"][0]["id"]],
        "method_ids": ["task-rubric-v1", "safety-observed-v1"],
        "repetitions": 1,
    }
    return client, base, group, body


def test_missing_mapping_is_not_pass(lab):
    client, base, group, body = prepare(lab)
    plan = client.post(base + "/plans", json=body, headers={"idempotency-key": uuid4().hex}).json()[
        "data"
    ]
    run = client.post(
        base + "/runs",
        json={"plan_id": plan["id"], "expected_plan_sha256": plan["snapshot_sha256"]},
        headers={"idempotency-key": uuid4().hex},
    ).json()["data"]
    process(claim())
    view = client.get(base + "/runs/" + run["id"]).json()["data"]
    policy = view["series"][0]["axes"][3]
    assert policy["value"] is None and policy["unknown"] == 9
    assert all(f["outcome"] == "not_evaluated" for f in view["failures"]["policy_findings"])


@pytest.mark.parametrize(
    "change,code",
    [
        ({"models": ["real-provider-model"]}, 409),
        ({"method_ids": ["safety-observed-v1"]}, 422),
        ({"task_ids": ["nonexistent"]}, 422),
        ({"environment_ids": ["other"]}, 422),
        ({"method_ids": ["task-rubric-v1", "unregistered"]}, 422),
    ],
)
def test_plan_guards(lab, change, code):
    client, base, group, body = prepare(lab)
    response = client.post(
        base + "/plans", json=body | change, headers={"idempotency-key": uuid4().hex}
    )
    assert response.status_code == code, response.text


def test_revoked_verifier_blocks_before_capture(lab):
    client, base, group, body = prepare(lab, mapped=True)
    plan = client.post(base + "/plans", json=body, headers={"idempotency-key": uuid4().hex}).json()[
        "data"
    ]
    run = client.post(
        base + "/runs",
        json={"plan_id": plan["id"], "expected_plan_sha256": plan["snapshot_sha256"]},
        headers={"idempotency-key": uuid4().hex},
    ).json()["data"]
    config = plan["snapshot"]["mappings"][0]["configuration_id"]
    assert (
        client.post(
            f"/api/v1/projects/{lab['project']}/workspace/evaluators/{config}/revoke"
        ).status_code
        == 200
    )
    with pytest.raises(ValueError, match="verifier_changed"):
        process(claim())
    view = client.get(base + "/runs/" + run["id"]).json()["data"]
    assert view["run"]["state"] == "blocked" and view["cells"] == []
    assert not view["run"]["report_review"]["ready"]


def test_source_and_authority_cannot_be_forged(lab):
    client, base, group, body = prepare(lab)
    plan = client.post(base + "/plans", json=body, headers={"idempotency-key": uuid4().hex}).json()[
        "data"
    ]
    assert (
        client.post(
            base + "/runs", json={"plan_id": plan["id"], "expected_plan_sha256": "0" * 64}
        ).status_code
        == 409
    )
    from anvil.db import Jsonb

    with connection("anvil_app", lab["project"], lab["admin"]) as c:
        with pytest.raises(Exception, match="new Run cannot claim"):
            c.execute(
                "INSERT INTO anvil.benchmark_runs(id,project_id,plan_id,snapshot,snapshot_sha256,report_policy,created_by,graph_thread_id,state,admin_execution) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'completed',true)",
                (
                    uuid4(),
                    lab["project"],
                    plan["id"],
                    Jsonb(plan["snapshot"]),
                    plan["snapshot_sha256"],
                    Jsonb({"required_reviewers": 0}),
                    lab["admin"],
                    uuid4(),
                ),
            )


@pytest.mark.parametrize("adapter", ["builtin", "zen", "opa-local", "nemo", "promptfoo"])
def test_every_local_adapter_evaluates_actual_run_evidence(lab, adapter):
    client, base, group, body = prepare(lab)
    evaluator_base = f"/api/v1/projects/{lab['project']}/workspace/evaluators"
    rule = (
        {"kind": "equals", "field": "status", "value": "needs_review"}
        if adapter in {"zen", "opa-local"}
        else {"kind": "forbidden_text", "field": "status", "value": "approved"}
    )
    created = client.post(
        evaluator_base,
        json={"name": "No unsupported approval", "adapter": adapter, "rule": rule},
        headers={"idempotency-key": uuid4().hex},
    )
    assert created.status_code == 201, created.text
    config = created.json()["data"]
    tested = client.post(
        evaluator_base + "/" + config["id"] + "/test",
        json={
            "cases": [
                {"facts": {"status": "needs_review"}, "expected": "pass"},
                {"facts": {"status": "approved"}, "expected": "fail"},
                {"facts": {}, "expected": "unknown"},
            ]
        },
        headers={"idempotency-key": uuid4().hex},
    )
    assert tested.status_code == 200 and tested.json()["data"]["status"] == "ready", tested.text
    policy = client.get(base + f"/groups/{group['id']}/policies").json()["data"]
    mapped = client.post(
        base + "/mappings",
        json={
            "policy_set_id": policy["id"],
            "policy_id": "bank-policy",
            "policy_version": "1",
            "rule_id": "identity",
            "configuration_id": config["id"],
            "task_ids": ["KYC-001"],
            "environment_ids": [],
        },
        headers={"idempotency-key": uuid4().hex},
    )
    assert mapped.status_code == 200, mapped.text
    body.update(task_ids=["KYC-001"], models=["fictional-compliant-v1", "fictional-permissive-v1"])
    saved = client.post(base + "/plans", json=body, headers={"idempotency-key": uuid4().hex})
    assert saved.status_code == 200, saved.text
    plan = saved.json()["data"]
    run = client.post(
        base + "/runs",
        json={"plan_id": plan["id"], "expected_plan_sha256": plan["snapshot_sha256"]},
        headers={"idempotency-key": uuid4().hex},
    ).json()["data"]
    process(claim())
    result = client.get(base + "/runs/" + run["id"]).json()["data"]
    checks = [
        (c["model_key"], f["outcome"])
        for c in result["cells"]
        for f in c["assessment"]["policy_findings"]
        if f["rule_id"] == "identity"
    ]
    assert sorted(checks) == [
        ("fictional-compliant-v1", "pass"),
        ("fictional-permissive-v1", "fail"),
    ]
    assert result["run"]["provider_calls"] == 0
