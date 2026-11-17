"""Real PostgreSQL/file mutation, reset and isolation probes; not model grading."""

from anvil import environment_runtime as runtime
from anvil.db import digest


def validate(c, project, user, environment):
    version = runtime.get(c, "environment_versions", environment)
    template = version["manifest"]["template_id"]
    first = runtime.create_instance(c, project, user, environment)
    second = runtime.create_instance(c, project, user, environment)
    baseline = runtime.state(c, first["id"])
    other_before = digest(runtime.state(c, second["id"]))
    checks = []

    def check(name, success, evidence):
        checks.append({"check": name, "passed": bool(success), "evidence": evidence})

    check(
        "actual_load_readback",
        digest(baseline) == first["initial_sha256"],
        {
            "collections": {k: len(v) for k, v in baseline["records"].items()},
            "file_count": len(baseline["files"]),
        },
    )
    if template == "BOD-FIN":
        company = baseline["records"]["companies"][0]["id"]
        period = next(
            p["id"] for p in baseline["records"]["reporting_periods"] if p["company_id"] == company
        )
        query = runtime.execute(
            c,
            user,
            first["id"],
            "query_statements",
            {"company_id": company, "period_id": period},
            0,
        )
        check(
            "trusted_statement_query",
            query["result"]["status"] == "ok" and len(query["result"]["value"]["rows"]) == 8,
            {"event": query["sha256"]},
        )
        source = baseline["records"]["financial_statement_lines"][0]["id"]
        mutation = runtime.execute(
            c,
            user,
            first["id"],
            "save_analysis",
            {
                "text": "Software validation artifact, not a candidate answer.",
                "source_ids": [source],
            },
            0,
        )
    elif template == "MKT-PHONE":
        mutation = runtime.execute(
            c,
            user,
            first["id"],
            "create_campaign",
            {
                "objective": "Validation only",
                "copy": "noise cancelling",
                "audience_ids": ["student"],
            },
            0,
        )
        denial = runtime.execute(
            c,
            user,
            first["id"],
            "schedule_placement",
            {"target_id": "campaign", "channel": "social"},
            0,
        )
        check(
            "no_fabricated_approval",
            denial["result"]["status"] == "rejected",
            {"event": denial["sha256"]},
        )
        overrun = runtime.execute(
            c,
            user,
            first["id"],
            "allocate_budget",
            {"campaign_id": "campaign", "amount": "1001.00", "currency": "INR"},
            0,
        )
        check(
            "aggregate_budget_boundary",
            overrun["result"]["status"] == "rejected",
            {"event": overrun["sha256"]},
        )
    elif template == "MKT-LOCALE":
        mutation = runtime.execute(
            c,
            user,
            first["id"],
            "render_variant",
            {
                "channel": "search",
                "locale": "en-IN",
                "caption": "Validation only",
                "disclosure": "Fictional reference offer",
            },
            0,
        )
        inspected = runtime.execute(
            c, user, first["id"], "inspect_asset", {"path": "assets/search-en-IN.png"}, 0
        )
        check(
            "actual_png_metadata",
            inspected["result"]["status"] == "ok"
            and inspected["result"]["value"]["width"] == 320
            and inspected["result"]["value"]["height"] == 180,
            {"event": inspected["sha256"]},
        )
    elif template == "BNK-KYC":
        mutation = runtime.execute(
            c,
            user,
            first["id"],
            "request_information",
            {"case_id": "case", "reason": "Software validation request"},
            0,
        )
        check(
            "case_document_links",
            all(
                r["case_id"] == "case" and any(f["path"] == r["path"] for f in baseline["files"])
                for r in baseline["records"]["documents"]
            ),
            {"documents": [d["id"] for d in baseline["records"]["documents"]]},
        )
    elif template == "BNK-KYB":
        mutation = runtime.execute(
            c, user, first["id"], "ownership_paths", {"entity_id": "company"}, 0
        )
        value = mutation["result"].get("value", {})
        scenario = version["manifest"]["scenario_id"]
        check(
            "bounded_exact_ownership",
            mutation["result"]["status"] == "ok"
            and (
                any(p["kind"] == "cycle" for p in value.get("problems", []))
                if scenario == "cycle"
                else value.get("totals", {}).get("person-a")
                in (("10.00",) if scenario == "missing_evidence" else ("35.0000", "35.00", "25.00"))
            ),
            {"event": mutation["sha256"]},
        )
    else:
        query = runtime.execute(
            c,
            user,
            first["id"],
            "query_transactions",
            {
                "account_id": "account",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-03T23:59:59Z",
            },
            0,
        )
        check(
            "bounded_transaction_window",
            query["result"]["status"] == "ok"
            and len(query["result"]["value"]["rows"]) == 3
            and query["result"]["value"]["total"] == "601.50",
            {"event": query["sha256"]},
        )
        mutation = runtime.execute(
            c,
            user,
            first["id"],
            "record_step",
            {
                "case_id": "case",
                "note": "Software validation investigation",
                "transaction_ids": ["txn-0"],
            },
            0,
        )
    check(
        "actual_state_mutation",
        mutation["result"]["status"] == "ok"
        and digest(runtime.state(c, first["id"])) != first["initial_sha256"],
        {"event": mutation["sha256"]},
    )
    check(
        "independent_instance_state",
        digest(runtime.state(c, second["id"])) == other_before,
        {"first_instance": str(first["id"]), "second_instance": str(second["id"])},
    )
    exported = runtime.export_evidence(c, user, first["id"])
    reset = runtime.reset(c, user, first["id"], 0)
    check(
        "reset_exact_pinned_pack",
        digest(runtime.state(c, first["id"])) == first["initial_sha256"],
        {"receipt": str(reset["id"]), "baseline_sha256": first["initial_sha256"]},
    )
    check(
        "evidence_survives_reset",
        bool(exported["content"]["events"])
        and exported["content_sha256"] == digest(exported["content"]),
        {"receipt": str(exported["id"])},
    )
    cleanup = [runtime.close(c, user, row["id"])["id"] for row in (first, second)]
    content = {
        "schema_version": "anvil.environment-validation.v1",
        "environment_manifest_sha256": version["manifest_sha256"],
        "pack_sha256": version["manifest"]["pack_sha256"],
        "runtime": "postgres-local-components-v1",
        "checks": checks,
        "passed": all(x["passed"] for x in checks),
        "cleanup_receipts": list(map(str, cleanup)),
        "cloud_tested": False,
        "model_performance": False,
        "provider_calls": 0,
        "native_isolation": False,
        "limitations": [
            "Logical instance isolation in PostgreSQL, not native container or network isolation",
            "Published Task/rule/evaluator binding is required separately",
            "No GCP provisioning or model execution",
        ],
    }
    return runtime.receipt(c, project, user, environment, "validation", content)


def register(c, project, user, environment):
    version = runtime.get(c, "environment_versions", environment)
    runtime.current_runtime(version)
    rows = c.execute(
        "SELECT * FROM anvil.environment_receipts WHERE environment_id=%s AND kind='validation' ORDER BY created_at DESC,id DESC",
        (environment,),
    ).fetchall()
    valid = next(
        (
            r
            for r in rows
            if r["content"].get("passed")
            and r["content"].get("environment_manifest_sha256") == version["manifest_sha256"]
        ),
        None,
    )
    if not valid:
        from fastapi import HTTPException

        raise HTTPException(409, "Exact version has no passing local validation receipt")
    return runtime.receipt(
        c,
        project,
        user,
        environment,
        "registration",
        {
            "status": "registered_local_reference",
            "environment_manifest_sha256": version["manifest_sha256"],
            "validation_receipt": str(valid["id"]),
            "runnable_for_task": False,
            "cloud_ready": False,
            "reason": "Published task, evaluator/evidence binding and qualified runtime remain required",
        },
    )
