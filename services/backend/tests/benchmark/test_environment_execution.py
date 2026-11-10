"""Actual six-environment attempt/collector/report pipeline, no provider calls."""

import io
import os
from uuid import uuid4

import pytest
from pypdf import PdfReader
from test_benchmark_pipeline import login
from test_private_storage import connection
from test_private_storage import lab as storage_lab

from anvil import benchmark_business_fixture as fixture
from anvil import benchmark_project_import as projects
from anvil import environment_builds as builds
from anvil import environment_execution as execution
from anvil import (
    environment_runtime as worlds,
)
from anvil import (
    environment_seeds as seeds,
)
from anvil import (
    environment_validation as validation,
)
from anvil.benchmark_run_worker import claim, process
from anvil.environment_openenv import LocalEpisode, Reset, Step

lab = storage_lab


@pytest.mark.parametrize("adapter", ["builtin", "zen", "opa-local", "nemo", "promptfoo"])
def test_environment_custom_policy_uses_trusted_fields_and_missing_is_unknown(
    lab, monkeypatch, adapter
):
    from anvil import benchmark_runs as runs
    from anvil import evaluator_configurations as evaluators

    monkeypatch.setenv("ANVIL_BENCHMARK_REHEARSAL_ENABLED", "true")
    monkeypatch.setenv("ANVIL_LOCAL_FIXTURE_ENABLED", "true")
    with connection("anvil_app", lab["project"], lab["admin"]) as c:
        content, policies = projects.parse(fixture.bundle())
        group = projects.store(c, lab["project"], lab["admin"], content, policies)
        text = adapter in ("nemo", "promptfoo")
        rule = (
            {"kind": "forbidden_text", "field": "status", "value": "approved"}
            if text
            else {"kind": "equals", "field": "status", "value": "needs_review"}
        )
        config = evaluators.create(
            c,
            lab["project"],
            lab["admin"],
            evaluators.Configure(
                name="Explicit missing-identity workflow rule", adapter=adapter, rule=rule
            ),
        )
        evaluators.test(
            c,
            lab["project"],
            lab["admin"],
            config["id"],
            evaluators.TestCases(
                cases=[
                    {"facts": {"status": "needs_review"}, "expected": "pass"},
                    {"facts": {"status": "approved"}, "expected": "fail"},
                    {"facts": {}, "expected": "unknown"},
                ]
            ),
        )
        policy = runs.policy_set(c, group["id"])
        runs.save_mapping(
            c,
            lab["project"],
            lab["admin"],
            runs.Mapping(
                policy_set_id=policy["id"],
                policy_id="bank-policy",
                policy_version="1",
                rule_id="identity",
                configuration_id=config["id"],
                task_ids=[content["tasks"][0]["task_id"]],
            ),
        )
        members = []
        for record in ("case", "missing-record"):
            pack = worlds.pack_store(
                c, lab["project"], lab["admin"], seeds.generate("BNK-KYC", "complete")
            )
            version = worlds.create_version(
                c, lab["project"], lab["admin"], pack["id"], "Trusted policy evidence " + record
            )
            validation.validate(c, lab["project"], lab["admin"], version["id"])
            validation.register(c, lab["project"], lab["admin"], version["id"])
            members.append(
                {
                    "environment_id": version["id"],
                    "task_id": content["tasks"][0]["task_id"],
                    "source_environment_id": content["tasks"][0]["environment_ids"][0],
                    "policy_fields": [
                        {
                            "target": "status",
                            "collection": "cases",
                            "record_id": record,
                            "field": "status",
                        }
                    ],
                    "actions": [],
                }
            )
        plan = execution.create_plan(
            c,
            lab["project"],
            lab["admin"],
            execution.Plan(
                name="Trusted mapped policy",
                task_group_id=group["id"],
                members=members,
                purpose="technical_rehearsal",
            ),
        )
        run = runs.start(
            c,
            lab["project"],
            lab["admin"],
            runs.Start(plan_id=plan["id"], expected_plan_sha256=plan["snapshot_sha256"]),
        )
    process(claim())
    client = login(lab, "admin")
    view = client.get(
        f"/api/v1/projects/{lab['project']}/workspace/benchmark/runs/{run['id']}"
    ).json()["data"]
    findings = [f for f in view["failures"]["policy_findings"] if f["rule_id"] == "identity"]
    assert len(findings) == 2
    assert {f["outcome"] for f in findings} == {"pass" if text else "fail", "unknown"}
    assert all(f["evaluator"]["adapter"] == adapter for f in findings)
    policy_axis = view["series"][0]["axes"][3]
    assert policy_axis["decided"] == 1
    assert policy_axis["unknown"] >= 1


@pytest.mark.parametrize(
    "harness",
    [
        "local-components-v1",
        "openenv-local-v1",
        pytest.param(
            "openenv-0.12-local-v1",
            marks=pytest.mark.skipif(
                os.environ.get("ANVIL_ENVIRONMENT_OPENENV_ENABLED") != "true",
                reason="Dedicated pinned OpenEnv interpreter required",
            ),
        ),
        pytest.param(
            "harbor-host-mediated-v1",
            marks=pytest.mark.skipif(
                os.environ.get("ANVIL_ENVIRONMENT_NATIVE_ENABLED") != "true",
                reason="Dedicated native Harbor test scope required",
            ),
        ),
    ],
)
def test_six_environment_attempts_are_in_existing_dashboard_and_pdf(lab, monkeypatch, harness):
    monkeypatch.setenv("ANVIL_BENCHMARK_REHEARSAL_ENABLED", "true")
    monkeypatch.setenv("ANVIL_LOCAL_FIXTURE_ENABLED", "true")
    with connection("anvil_app", lab["project"], lab["admin"]) as c:
        content, policies = projects.parse(fixture.bundle())
        group = projects.store(c, lab["project"], lab["admin"], content, policies)
        members = []
        for template, config in seeds.CATALOG.items():
            pack = worlds.pack_store(
                c, lab["project"], lab["admin"], seeds.generate(template, config["scenarios"][0])
            )
            version = worlds.create_version(
                c, lab["project"], lab["admin"], pack["id"], template + " execution world"
            )
            validation.validate(c, lab["project"], lab["admin"], version["id"])
            validation.register(c, lab["project"], lab["admin"], version["id"])
            members.append(
                {
                    "environment_id": version["id"],
                    "task_id": content["tasks"][0]["task_id"],
                    "source_environment_id": content["tasks"][0]["environment_ids"][0],
                    "actions": [
                        {
                            "operation": "list_records",
                            "arguments": {"collection": config["collections"][0]},
                        }
                    ],
                }
            )
        plan = execution.create_plan(
            c,
            lab["project"],
            lab["admin"],
            execution.Plan(
                name="Six actual environment worlds",
                task_group_id=group["id"],
                members=members,
                candidates=["configured-tools-v1", "empty-tools-v1"],
                purpose="technical_rehearsal",
                harness=harness,
            ),
        )
    client = login(lab, "admin")
    base = f"/api/v1/projects/{lab['project']}/workspace/benchmark"
    response = client.post(
        base + "/runs",
        json={"plan_id": str(plan["id"]), "expected_plan_sha256": plan["snapshot_sha256"]},
        headers={"idempotency-key": uuid4().hex},
    )
    assert response.status_code == 200, response.text
    run = response.json()["data"]
    job = claim()
    assert str(job["run_id"]) == run["id"]
    process(job)
    process(job)  # Terminal job delivery is idempotent, not a second execution.
    result = client.get(base + "/runs/" + run["id"])
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    assert data["run"]["state"] == "completed", data["run"]
    assert len(data["cells"]) == 12
    assert all(cell["assessment"]["earned_points"] is None for cell in data["cells"])
    assert all(m["mean_points"] is None for m in data["summary"]["models"])
    assert all(s["axes"][0]["value"] is None for s in data["series"])
    if harness == "harbor-host-mediated-v1":
        assert all(s["axes"][5]["value"] == 100 for s in data["series"])
    if harness == "openenv-0.12-local-v1":
        assert data["selected_cell"]["capture"]["openenv_adapter"]["version"] == "0.12.0"
    assert data["run"]["provider_calls"] == 0 and not data["run"]["model_performance"]
    assert data["failures"]["cells"] == 0
    assert data["failures"]["unknown_cells"] == 12 and data["failures"]["percent"] is None
    assert all(f["outcome"] == "not_evaluated" for f in data["failures"]["policy_findings"])
    with connection("anvil_app", lab["project"], lab["admin"]) as c:
        attempts = c.execute(
            "SELECT * FROM anvil.environment_attempts WHERE run_id=%s", (run["id"],)
        ).fetchall()
        assert len(attempts) == 12 and all(
            a["state"] == "assessed" and a["evidence_receipt_id"] for a in attempts
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.environment_instances WHERE state='active'"
            ).fetchone()["n"]
            == 0
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_run_report_decisions WHERE run_id=%s",
                (run["id"],),
            ).fetchone()["n"]
            == 0
        )
    pdf = client.get(base + f"/runs/{run['id']}/export?expected_view_sha256={data['view_sha256']}")
    assert pdf.status_code == 200, pdf.text[:200] if not pdf.content.startswith(b"%PDF") else ""
    text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Not evaluated" in text
    assert PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text().count("Not evaluated\n6") == 2
    engineer = login(lab, "engineer")
    retry = engineer.post(
        f"/api/v1/projects/{lab['project']}/workspace/environments/runs/{run['id']}/retry",
        json={},
        headers={"idempotency-key": uuid4().hex},
    )
    assert retry.status_code == 200, retry.text
    child = retry.json()["data"]
    process(claim())
    retried = engineer.get(base + "/runs/" + child["id"]).json()["data"]
    assert (
        retried["run"]["state"] == "completed"
        and retried["run"]["report_review"]["state"] == "pending_review"
    )
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.environment_attempts WHERE run_id=%s AND parent_attempt_id IS NOT NULL",
                (child["id"],),
            ).fetchone()["n"]
            == 12
        )
    outsider = login(lab, "outsider")
    assert outsider.get(base + "/runs/" + run["id"]).status_code == 404


def test_build_phase_resume_cancellation_and_episode_reset(lab):
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        pack = worlds.pack_store(
            c, lab["project"], lab["engineer"], seeds.generate("BNK-AML", "unresolved")
        )
        version = worlds.create_version(
            c, lab["project"], lab["engineer"], pack["id"], "Phase-resumable world"
        )
        job = builds.create(c, lab["project"], lab["engineer"], version["id"])
        for revision in range(4):
            job = builds.advance(c, lab["engineer"], job["id"], revision)
        assert job["state"] == "completed" and len(job["steps"]) == 4
        assert builds.advance(c, lab["engineer"], job["id"], 4)["state"] == "completed"
        second = builds.create(c, lab["project"], lab["engineer"], version["id"])
        assert (
            builds.advance(c, lab["engineer"], second["id"], 0, cancel=True)["state"] == "cancelled"
        )
        instance = worlds.create_instance(c, lab["project"], lab["engineer"], version["id"])
        episode = LocalEpisode(c, lab["engineer"], instance["id"])
        result = episode.step(
            Step(
                operation="record_step",
                arguments={
                    "case_id": "case",
                    "note": "Actual investigation step",
                    "transaction_ids": ["txn-0"],
                },
                expected_generation=0,
            )
        )
        assert result["native_reward"] is None and result["anvil_score"] is None
        assert (
            episode.reset(
                Reset(expected_generation=0, expected_pack_sha256=pack["content_sha256"])
            )["generation"]
            == 1
        )
        episode.close()


def test_failed_native_dispatch_retains_attempt_evidence_and_never_blindly_replays(
    lab, monkeypatch
):
    from anvil import environment_harbor

    monkeypatch.setenv("ANVIL_BENCHMARK_REHEARSAL_ENABLED", "true")
    monkeypatch.setenv("ANVIL_LOCAL_FIXTURE_ENABLED", "true")
    with connection("anvil_app", lab["project"], lab["admin"]) as c:
        content, policies = projects.parse(fixture.bundle())
        group = projects.store(c, lab["project"], lab["admin"], content, policies)
        pack = worlds.pack_store(
            c, lab["project"], lab["admin"], seeds.generate("BNK-KYC", "complete")
        )
        version = worlds.create_version(
            c, lab["project"], lab["admin"], pack["id"], "Retained failed native attempt"
        )
        validation.validate(c, lab["project"], lab["admin"], version["id"])
        validation.register(c, lab["project"], lab["admin"], version["id"])
        plan = execution.create_plan(
            c,
            lab["project"],
            lab["admin"],
            execution.Plan(
                name="Uncertain native fixture",
                task_group_id=group["id"],
                purpose="technical_rehearsal",
                harness="harbor-host-mediated-v1",
                members=[
                    {
                        "environment_id": version["id"],
                        "task_id": content["tasks"][0]["task_id"],
                        "source_environment_id": content["tasks"][0]["environment_ids"][0],
                    }
                ],
            ),
        )
    client = login(lab, "admin")
    base = f"/api/v1/projects/{lab['project']}/workspace/benchmark"
    started = client.post(
        base + "/runs",
        json={"plan_id": str(plan["id"]), "expected_plan_sha256": plan["snapshot_sha256"]},
        headers={"idempotency-key": uuid4().hex},
    )
    assert started.status_code == 200, started.text
    run = started.json()["data"]
    calls = []

    def failure(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("Synthetic native transport uncertainty")

    monkeypatch.setattr(environment_harbor, "execute", failure)
    job = claim()
    with pytest.raises(ValueError, match="retained evidence"):
        process(job)
    process(job)
    assert len(calls) == 1
    attempts = client.get(
        f"/api/v1/projects/{lab['project']}/workspace/environments/runs/{run['id']}/attempts"
    ).json()["data"]
    assert (
        len(attempts) == 1
        and attempts[0]["state"] == "uncertain"
        and attempts[0]["evidence_receipt_id"]
    )
    receipt = client.get(
        f"/api/v1/projects/{lab['project']}/workspace/environments/receipts/{attempts[0]['evidence_receipt_id']}"
    )
    assert receipt.status_code == 200 and receipt.json()["data"]["content"]["provider_calls"] == 0


def test_gcp_profile_is_admin_configuration_not_activation(lab):
    from test_environment_integration import profile

    body = {
        "name": "Synthetic wire-only GCP configuration",
        "configuration": profile().model_dump(),
    }
    base = f"/api/v1/projects/{lab['project']}/workspace/environments/runtime-profiles"
    engineer = login(lab, "engineer")
    admin = login(lab, "admin")
    assert (
        engineer.post(base, json=body, headers={"idempotency-key": uuid4().hex}).status_code == 403
    )
    saved = admin.post(base, json=body, headers={"idempotency-key": uuid4().hex})
    assert saved.status_code == 200, saved.text
    row = saved.json()["data"]
    assert row["cloud_enabled"] is False and row["status"] == "configured_not_cloud_qualified"
    assert engineer.get(base).status_code == 200
    with connection("anvil_app", lab["project"], lab["admin"]) as c:
        with pytest.raises(Exception):
            c.execute(
                "UPDATE anvil.environment_runtime_profiles SET name='Changed' WHERE id=%s",
                (row["id"],),
            )


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
@pytest.mark.parametrize("template", list(seeds.CATALOG))
def test_real_sdk_tool_contract_uses_component_state_without_provider_calls(
    lab, monkeypatch, provider, template
):
    import json

    import httpx
    from test_benchmark_provider_loop import binding, response

    from anvil.environment_model_tools import Mediator, sdk_contract

    monkeypatch.setenv("ANVIL_BENCHMARK_REHEARSAL_ENABLED", "true")
    monkeypatch.setenv("ANVIL_LOCAL_FIXTURE_ENABLED", "true")
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        content, policies = projects.parse(fixture.bundle())
        group = projects.store(c, lab["project"], lab["engineer"], content, policies)
        config = seeds.CATALOG[template]
        pack = worlds.pack_store(
            c, lab["project"], lab["engineer"], seeds.generate(template, config["scenarios"][0])
        )
        version = worlds.create_version(
            c, lab["project"], lab["engineer"], pack["id"], "SDK " + template
        )
        instance = worlds.create_instance(c, lab["project"], lab["engineer"], version["id"])
        requests = []

        def wire(request):
            requests.append(json.loads(request.content))
            assert (
                "reference_output" not in request.content.decode()
                and "reviewer_ref" not in request.content.decode()
            )
            return httpx.Response(
                200,
                json=response(
                    provider,
                    calls=[("c1", "list_records", {"collection": config["collections"][0]})]
                    if len(requests) == 1
                    else (),
                    text="" if len(requests) == 1 else "Completed synthetic SDK contract",
                ),
            )

        result = sdk_contract(
            c,
            lab["engineer"],
            group["id"],
            content["tasks"][0]["task_id"],
            instance["id"],
            binding(provider),
            httpx.MockTransport(wire),
        )
        assert (
            result["status"] == "completed"
            and result["provider_calls"] == 0
            and result["model_performance"] is False
        ), result
        assert len(requests) == 2 and result["turns"][0]["observations"][0]["error"] is None
        receipt = worlds.export_evidence(c, lab["engineer"], instance["id"])
        assert receipt["content"]["events"][-1]["operation"] == "list_records"
        mediator = Mediator(c, lab["engineer"], instance["id"])
        with pytest.raises(ValueError):
            mediator.call("reset", {}, timeout=1)
        with pytest.raises(ValueError):
            sdk_contract(
                c,
                lab["engineer"],
                group["id"],
                content["tasks"][0]["task_id"],
                instance["id"],
                binding(provider),
                None,
            )
        worlds.close(c, lab["engineer"], instance["id"])
