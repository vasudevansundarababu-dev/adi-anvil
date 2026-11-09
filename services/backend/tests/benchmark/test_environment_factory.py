"""Actual SQL/state/file boundaries; no cloud or model calls."""

from uuid import uuid4

import pytest
from test_benchmark_pipeline import login
from test_private_storage import connection
from test_private_storage import lab as storage_lab

from anvil import environment_bindings as bindings
from anvil import environment_runtime as runtime
from anvil import environment_seeds as seeds
from anvil import environment_validation as validation
from anvil.db import digest

lab = storage_lab


@pytest.mark.parametrize("template", list(seeds.CATALOG))
def test_five_actual_scenario_worlds_load_mutate_reset_and_isolate(lab, template):
    for scenario in seeds.CATALOG[template]["scenarios"]:
        with connection("anvil_app", lab["project"], lab["engineer"]) as c:
            pack = runtime.pack_store(
                c, lab["project"], lab["engineer"], seeds.generate(template, scenario)
            )
            version = runtime.create_version(
                c, lab["project"], lab["engineer"], pack["id"], "Actual local validation"
            )
            receipt = validation.validate(c, lab["project"], lab["engineer"], version["id"])
            assert receipt["content"]["passed"], receipt["content"]["checks"]
            assert receipt["content"]["provider_calls"] == 0
            assert receipt["content"]["cloud_tested"] is False
            registered = validation.register(c, lab["project"], lab["engineer"], version["id"])
            assert registered["content"]["runnable_for_task"] is False
            assert (
                c.execute(
                    "SELECT count(*) AS n FROM anvil.environment_instances WHERE environment_id=%s AND state='active'",
                    (version["id"],),
                ).fetchone()["n"]
                == 0
            )


@pytest.mark.parametrize("identity", ["admin", "engineer"])
def test_authenticated_api_role_flow_idempotency_files_and_immutable_evidence(lab, identity):
    client = login(lab, identity)
    base = f"/api/v1/projects/{lab['project']}/workspace/environments"
    assert len(client.get(base).json()["data"]["templates"]) == 6

    def post(path, body=None, key=None):
        r = client.post(base + path, json=body, headers={"idempotency-key": key or uuid4().hex})
        assert r.status_code == 200, r.text
        return r.json()["data"]

    pack = post("/packs/generate", {"template": "BNK-KYC", "scenario": "incomplete"})
    version = post(
        "/versions", {"pack_id": pack["id"], "name": "Preserve authentic KYC-001 separately"}
    )
    key = uuid4().hex
    instance = post(f"/versions/{version['id']}/instances", key=key)
    assert post(f"/versions/{version['id']}/instances", key=key)["id"] == instance["id"]
    path = f"/instances/{instance['id']}"
    body = {
        "operation": "request_information",
        "arguments": {"case_id": "case", "reason": "Actual missing evidence request"},
        "expected_generation": 0,
    }
    action_key = uuid4().hex
    event = post(path + "/tools", body, action_key)
    assert event["result"]["status"] == "ok"
    assert post(path + "/tools", body, action_key)["sha256"] == event["sha256"]
    content = client.get(base + path + "/files?path=documents/address.txt")
    assert content.status_code == 200 and b"SYNTHETIC" in content.content
    evidence = post(path + "/evidence")
    assert evidence["content_sha256"] == digest(evidence["content"])
    post(path + "/reset", {"expected_generation": 0})
    assert (
        client.post(
            base + path + "/tools", json=body, headers={"idempotency-key": uuid4().hex}
        ).status_code
        == 409
    )
    outsider = login(lab, "outsider")
    assert outsider.get(base + path).status_code == 404
    with connection("anvil_app", lab["project"], lab[identity]) as c:
        with pytest.raises(Exception):
            c.execute(
                "UPDATE anvil.environment_receipts SET content='{}' WHERE id=%s", (evidence["id"],)
            )
    post(path + "/close")
    assert (
        client.post(base + path + "/evidence", headers={"idempotency-key": uuid4().hex}).status_code
        == 409
    )


def test_actor_cannot_reset_approve_or_inject_trusted_evidence(lab):
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        p = runtime.pack_store(
            c, lab["project"], lab["engineer"], seeds.generate("MKT-PHONE", "missing_approval")
        )
        v = runtime.create_version(c, lab["project"], lab["engineer"], p["id"], "Actor boundary")
        i = runtime.create_instance(c, lab["project"], lab["engineer"], v["id"])
        baseline = digest(runtime.state(c, i["id"]))
        for operation in ("reset", "approve", "write_evidence", "execute_sql"):
            with pytest.raises(Exception):
                runtime.execute(c, lab["engineer"], i["id"], operation, {}, 0)
        denied = runtime.execute(
            c,
            lab["engineer"],
            i["id"],
            "schedule_placement",
            {"target_id": "campaign", "channel": "social"},
            0,
        )
        assert denied["result"]["status"] == "rejected"
        assert digest(runtime.state(c, i["id"])) == baseline


def test_event_chain_and_reset_generation_do_not_rewrite_history(lab):
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        p = runtime.pack_store(
            c, lab["project"], lab["engineer"], seeds.generate("BNK-AML", "missing_context")
        )
        v = runtime.create_version(c, lab["project"], lab["engineer"], p["id"], "Immutable history")
        i = runtime.create_instance(c, lab["project"], lab["engineer"], v["id"])
        e = runtime.execute(
            c, lab["engineer"], i["id"], "list_records", {"collection": "transactions"}, 0
        )
        runtime.reset(c, lab["engineer"], i["id"], 0)
        rows = c.execute(
            "SELECT * FROM anvil.environment_events WHERE instance_id=%s ORDER BY sequence",
            (i["id"],),
        ).fetchall()
        assert len(rows) == 2 and rows[0]["generation"] == 0 and rows[1]["generation"] == 1
        assert rows[1]["previous_sha256"] == e["sha256"]


def test_frozen_source_rule_mapping_unknown_and_original_scoring(lab):
    from anvil import benchmark_business_fixture as fixture
    from anvil import benchmark_project_import as imports
    from anvil import evaluator_configurations as evaluators
    from anvil.praxis_contract import PraxisTask, grade

    content, policy = imports.parse(fixture.bundle())
    task = content["tasks"][0]
    # Manufactured schema fixture in the isolated test database. This does not
    # perform or represent a human source review in the application/preview.
    task["source"]["provenance"]["review"]["status"] = "approved"
    task["source"]["provenance"]["review"]["reviewer_ref"] = (
        "manufactured-contract-fixture-not-human-approval"
    )
    parsed = PraxisTask.model_validate(task["source"])
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        group = imports.store(c, lab["project"], lab["engineer"], content, policy)
        pack = runtime.pack_store(
            c, lab["project"], lab["engineer"], seeds.generate("BNK-KYC", "complete")
        )
        version = runtime.create_version(
            c, lab["project"], lab["engineer"], pack["id"], "Frozen evidence binding"
        )
        validation.validate(c, lab["project"], lab["engineer"], version["id"])
        validation.register(c, lab["project"], lab["engineer"], version["id"])
        mapping = []
        for kind, requirement in [("criterion", r) for r in parsed.rubric.criteria] + [
            ("constraint", r) for r in parsed.constraints
        ]:
            rule = bindings.expected_rule(requirement.binding)
            config = evaluators.create(
                c,
                lab["project"],
                lab["engineer"],
                evaluators.Configure(
                    name="Original criterion known-case test", adapter="builtin", rule=rule
                ),
            )
            good = requirement.binding.value
            bad = "different" if isinstance(good, str) else False if good is True else 0
            evaluators.test(
                c,
                lab["project"],
                lab["engineer"],
                config["id"],
                evaluators.TestCases(
                    cases=[
                        {"facts": {rule.field: good}, "expected": "pass"},
                        {"facts": {rule.field: bad}, "expected": "fail"},
                        {"facts": {}, "expected": "unknown"},
                    ]
                ),
            )
            mapping.append(
                {"kind": kind, "requirement": requirement.id, "configuration_id": config["id"]}
            )
        fields = [
            {"target": "status", "collection": "cases", "record_id": "case", "field": "status"},
            {
                "target": "policy_ok",
                "collection": "customers",
                "record_id": "customer",
                "field": "identity_conflict",
            },
            {
                "target": "citation_count",
                "collection": "decisions",
                "record_id": "absent",
                "field": "evidence_ids",
                "transform": "count",
            },
        ]
        body = bindings.Create(
            environment_id=version["id"],
            task_group_id=group["id"],
            task_id=task["task_id"],
            expected_task_sha256=task["payload_sha256"],
            fields=fields,
            evaluators=mapping,
        )
        binding = bindings.create(c, lab["project"], lab["engineer"], body)
        assert "task_source" not in binding
        instance = runtime.create_instance(c, lab["project"], lab["engineer"], version["id"])
        evidence = runtime.export_evidence(c, lab["engineer"], instance["id"])
        result = bindings.assess(c, lab["project"], lab["engineer"], binding["id"], evidence["id"])
        assert result["content"]["original_scoring"] is None
        assert "citation_count" in result["content"]["missing_fields"]
        decision = runtime.execute(
            c,
            lab["engineer"],
            instance["id"],
            "record_decision",
            {
                "case_id": "case",
                "decision": "needs_review",
                "rationale": "Test-only manual evidence",
                "evidence_ids": ["identity", "address"],
            },
            0,
        )
        fields[2]["record_id"] = decision["result"]["value"]["id"]
        successor = bindings.create(
            c,
            lab["project"],
            lab["engineer"],
            body.model_copy(
                update={"fields": [bindings.FieldMapping.model_validate(f) for f in fields]}
            ),
        )
        captured = runtime.export_evidence(c, lab["engineer"], instance["id"])
        scored = bindings.assess(
            c, lab["project"], lab["engineer"], successor["id"], captured["id"]
        )
        assert scored["content"]["original_scoring"] == grade(
            parsed, {"status": "needs_review", "citation_count": 2, "policy_ok": False}
        )
        assert scored["content"]["provider_calls"] == 0


@pytest.mark.parametrize(
    "scenario,expected",
    [("incomplete", "unavailable"), ("conflict", "ambiguous"), ("complete", "clear")],
)
def test_identity_stub_never_infers_clear_from_missing_results(lab, scenario, expected):
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        p = runtime.pack_store(
            c, lab["project"], lab["engineer"], seeds.generate("BNK-KYC", scenario)
        )
        v = runtime.create_version(
            c, lab["project"], lab["engineer"], p["id"], "Screening response fixture"
        )
        i = runtime.create_instance(c, lab["project"], lab["engineer"], v["id"])
        result = runtime.execute(c, lab["engineer"], i["id"], "screen_case", {"case_id": "case"}, 0)
        assert result["result"]["value"]["status"] == expected


@pytest.mark.parametrize("scenario", ["unit_mismatch", "missing_line"])
def test_financial_unavailable_or_incomparable_values_do_not_become_zero(lab, scenario):
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        p = runtime.pack_store(
            c, lab["project"], lab["engineer"], seeds.generate("BOD-FIN", scenario)
        )
        v = runtime.create_version(
            c, lab["project"], lab["engineer"], p["id"], "Finance boundary fixture"
        )
        i = runtime.create_instance(c, lab["project"], lab["engineer"], v["id"])
        result = runtime.execute(
            c,
            lab["engineer"],
            i["id"],
            "calculate_financial",
            {
                "line_ids": ["fictional-1-1-2024-revenue", "fictional-1-1-2025-revenue"],
                "operator": "subtract",
            },
            0,
        )
        assert result["result"]["status"] == "rejected"
        assert "value" not in result["result"]
        assert runtime.records(c, i["id"], "saved_analysis") == []


def test_implementation_drift_blocks_new_and_existing_instances(lab, monkeypatch):
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        p = runtime.pack_store(
            c, lab["project"], lab["engineer"], seeds.generate("BNK-AML", "explainable")
        )
        v = runtime.create_version(
            c, lab["project"], lab["engineer"], p["id"], "Pinned implementation"
        )
        i = runtime.create_instance(c, lab["project"], lab["engineer"], v["id"])
        monkeypatch.setattr(runtime, "implementation_sha256", lambda: "0" * 64)
        assert runtime.readiness(c, v)["status"] == "implementation_changed"
        with pytest.raises(Exception, match="implementation changed"):
            runtime.execute(c, lab["engineer"], i["id"], "list_records", {"collection": "cases"}, 0)
        with pytest.raises(Exception, match="implementation changed"):
            runtime.create_instance(c, lab["project"], lab["engineer"], v["id"])


def test_automatic_local_build_is_idempotent_and_cloud_dispatch_is_blocked(lab):
    client = login(lab, "engineer")
    base = f"/api/v1/projects/{lab['project']}/workspace/environments"
    body = {
        "template": "BNK-AML",
        "scenario": "duplicate",
        "name": "Automatic local build",
        "runtime_profile": "local-reference-v1",
    }
    key = uuid4().hex
    first = client.post(base + "/builds", json=body, headers={"idempotency-key": key})
    assert first.status_code == 200, first.text
    result = first.json()["data"]
    assert result["state"] == "validated_local" and result["cloud_provisioned"] is False
    again = client.post(base + "/builds", json=body, headers={"idempotency-key": key})
    assert again.json()["data"]["environment"]["id"] == result["environment"]["id"]
    denied = client.post(
        base + "/builds",
        json=body | {"runtime_profile": "gcp"},
        headers={"idempotency-key": uuid4().hex},
    )
    assert denied.status_code == 409


def test_domain_approval_is_actual_admin_only_and_cannot_follow_changed_asset(lab):
    engineer = login(lab, "engineer")
    admin = login(lab, "admin")
    base = f"/api/v1/projects/{lab['project']}/workspace/environments"
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        p = runtime.pack_store(
            c, lab["project"], lab["engineer"], seeds.generate("MKT-LOCALE", "complete")
        )
        v = runtime.create_version(
            c, lab["project"], lab["engineer"], p["id"], "Asset-specific business decision"
        )
        i = runtime.create_instance(c, lab["project"], lab["engineer"], v["id"])
        request = runtime.execute(
            c, lab["engineer"], i["id"], "request_approval", {"target_id": "search-en-IN"}, 0
        )
        approval = request["result"]["value"]["id"]
    route = base + f"/instances/{i['id']}/approvals/{approval}"
    body = {
        "decision": "approved",
        "rationale": "Actual synthetic Admin API test decision, not a human source review",
    }
    assert (
        engineer.post(route, json=body, headers={"idempotency-key": uuid4().hex}).status_code == 403
    )
    accepted = admin.post(route, json=body, headers={"idempotency-key": uuid4().hex})
    assert accepted.status_code == 200, accepted.text
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        first = runtime.execute(
            c, lab["engineer"], i["id"], "submit_variant", {"target_id": "search-en-IN"}, 0
        )
        assert first["result"]["status"] == "ok"
        runtime.execute(
            c,
            lab["engineer"],
            i["id"],
            "render_variant",
            {
                "channel": "search",
                "locale": "en-IN",
                "caption": "Changed actual pixels",
                "disclosure": "Fictional reference offer",
            },
            0,
        )
        denied = runtime.execute(
            c, lab["engineer"], i["id"], "submit_variant", {"target_id": "search-en-IN"}, 0
        )
        assert denied["result"]["status"] == "rejected"
        assert (
            c.execute("SELECT count(*) AS n FROM anvil.benchmark_run_report_decisions").fetchone()[
                "n"
            ]
            == 0
        )


def test_actual_generated_file_bytes_survive_reset_in_immutable_evidence(lab):
    import base64
    import hashlib

    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        p = runtime.pack_store(
            c, lab["project"], lab["engineer"], seeds.generate("BOD-FIN", "comparable")
        )
        v = runtime.create_version(c, lab["project"], lab["engineer"], p["id"], "Artifact custody")
        i = runtime.create_instance(c, lab["project"], lab["engineer"], v["id"])
        output = runtime.execute(
            c,
            lab["engineer"],
            i["id"],
            "save_analysis",
            {"text": "Actual saved software output", "source_ids": ["fictional-1-1-2025-revenue"]},
            0,
        )
        path = output["result"]["value"]["path"]
        evidence = runtime.export_evidence(c, lab["engineer"], i["id"])
        runtime.reset(c, lab["engineer"], i["id"], 0)
        assert not any(f["path"] == path for f in runtime.state(c, i["id"])["files"])
        artifact = next(f for f in evidence["content"]["artifacts"] if f["path"] == path)
        raw = base64.b64decode(artifact["bytes_base64"])
        assert raw == b"Actual saved software output"
        assert hashlib.sha256(raw).hexdigest() == artifact["sha256"]


def test_event_limit_rolls_back_the_action_and_still_allows_capture_and_close(lab):
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        p = runtime.pack_store(
            c, lab["project"], lab["engineer"], seeds.generate("BNK-AML", "explainable")
        )
        v = runtime.create_version(
            c, lab["project"], lab["engineer"], p["id"], "Bounded local episode"
        )
        i = runtime.create_instance(c, lab["project"], lab["engineer"], v["id"])
        for _ in range(200):
            runtime.execute(c, lab["engineer"], i["id"], "list_records", {"collection": "cases"}, 0)
        before = digest(runtime.state(c, i["id"]))
        with pytest.raises(Exception, match="event budget"):
            runtime.execute(
                c,
                lab["engineer"],
                i["id"],
                "record_step",
                {"case_id": "case", "note": "Must roll back", "transaction_ids": ["txn-0"]},
                0,
            )
        assert digest(runtime.state(c, i["id"])) == before
        captured = runtime.export_evidence(c, lab["engineer"], i["id"])
        assert len(captured["content"]["events"]) == 200
        assert runtime.close(c, lab["engineer"], i["id"])["content"]["status"] == "closed_retained"
