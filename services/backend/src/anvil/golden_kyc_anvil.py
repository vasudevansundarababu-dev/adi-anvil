"""Golden import/admission into canonical Anvil registries. No paid dispatch.

Public task/environment/configuration bindings live in the existing registries;
private expectations remain exclusively in banking_private. Technical evaluator
known cases are not legal approval or independent per-application review.
"""

from fastapi import HTTPException

from anvil import benchmark_project_import as catalog
from anvil import evaluator_configurations as configurations
from anvil.benchmark_report_policy import current as report_policy
from anvil.db import Jsonb, digest, uid
from anvil.golden_kyc_data import VERSION
from anvil.golden_kyc_evaluators import CRITERIA, OPA_POLICIES, TRACE_CHECKS, ZEN_TABLES
from anvil.golden_kyc_policy import ASSIGNMENT, library
from anvil.golden_kyc_runtime import binding
from anvil.policy_rules import Rule
from anvil.praxis_case_dataset import NAMES, CaseDataset, from_snapshots

SCHEMA = "anvil.golden-kyc-execution-plan.v1"
ENVIRONMENT_KEY = "golden-kyc-v1"
CANDIDATE = {
    "id": "golden-investigator-software-v1",
    "name": "Golden evidence investigator · software control",
    "kind": "software_control",
    "version": "1",
}
PRODUCT_NAMES = {"individual": "Single KYC", "adult_joint": "Joint KYC",
                 "teen_joint": "Minor (joint with adult) KYC", "custodial": "Custodian KYC"}


def application_assignments(dataset, apps):
    """Exact actual snapshot routing for the software reference import only."""
    by_id = {app["id"]: app for app in apps}
    if len(by_id) != len(apps) or set(by_id) != {member.id for member in dataset.cases}:
        raise HTTPException(409, "Complete original application membership required")
    rows = []
    for member in dataset.cases:
        app = by_id[member.id]
        product = app["snapshot"].get("product")
        if (digest(app["snapshot"]) != member.snapshot_sha256 or app["snapshot_sha256"] != member.snapshot_sha256
                or product not in PRODUCT_NAMES):
            raise HTTPException(409, "Qualified reference population requires exact supported original product")
        rows.append({"application_id": member.id, "application_sha256": member.snapshot_sha256,
                     "governing_state": member.governing_state, "product": product, "task_id": "KYC-" + product})
    return rows


def source_hash():
    from anvil.golden_kyc_source import source_hash as pure_source_hash

    return pure_source_hash()


def _evaluators(c, project, user):
    entries = []
    groups = [
        ("rubric", CRITERIA, "zen"),
        ("business", ZEN_TABLES, "zen"),
        ("safety", OPA_POLICIES, "opa-local"),
        ("trace", TRACE_CHECKS, "builtin"),
    ]
    for group, names, adapter in groups:
        for name in names:
            config = configurations.create(
                c,
                project,
                user,
                configurations.Configure(
                    name=f"Golden KYC {group}: {name}",
                    adapter=adapter,
                    rule=Rule(kind="equals", field="supported", value=True),
                ),
            )
            config = configurations.test(
                c,
                project,
                user,
                config["id"],
                configurations.TestCases(
                    cases=[
                        configurations.Case(facts={"supported": True}, expected="pass"),
                        configurations.Case(facts={"supported": False}, expected="fail"),
                        configurations.Case(facts={}, expected="unknown"),
                    ]
                ),
            )
            if config["status"] != "ready":
                raise HTTPException(409, "Pinned evaluator runtime/known cases did not qualify")
            entries.append(
                {
                    "requirement": name,
                    "kind": group,
                    "configuration_id": str(config["id"]),
                    "configuration_sha256": config["configuration_sha256"],
                    "adapter": adapter,
                    "runtime_version": config["validation"]["evidence"]["runtime_version"],
                    "validation_id": str(config["validation"]["id"]),
                    "validation_sha256": config["validation"]["evidence_sha256"],
                    "normalizer_source_sha256": source_hash(),
                }
            )
    return entries


def register(c, project, user, pack, *, reusable=False, application_types=False):
    if type(reusable) is not bool or type(application_types) is not bool or reusable and application_types:
        raise HTTPException(422, "Select one explicit Golden reference import mode")
    reusable = reusable or application_types
    mode = "reusable_application_workflow" if application_types else "reusable_state_workflow" if reusable else "per_application"
    manifest = binding(c, project, pack)
    current = source_hash()
    old = c.execute(
        "SELECT * FROM banking.anvil_imports WHERE project_id=%s AND pack_id=%s AND manifest->>'source_sha256'=%s AND COALESCE(manifest->>'task_mode','per_application')=%s",
        (project, pack, current, mode),
    ).fetchone()
    if old:
        validate(c, old)
        return public(old)
    apps = c.execute(
        "SELECT id,snapshot,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id",
        (project, pack),
    ).fetchall()
    if (not reusable and len(apps) != 200) or any(
        digest(a["snapshot"]) != a["snapshot_sha256"] for a in apps
    ):
        raise HTTPException(409, "Exact frozen200-case snapshot required")
    dataset = None
    if reusable:
        dataset = from_snapshots("golden-kyc-applications", str(pack), apps)
    version = VERSION + ("-products-" if application_types else "-states-" if reusable else "-") + current[:12]
    tasks = []
    states = set()
    for app in apps:
        state = app["snapshot"]["governing_state"]
        selector = app["snapshot"]["product"] if application_types else state
        if application_types and selector not in PRODUCT_NAMES:
            raise HTTPException(409, "Supported original product required for reference import")
        if reusable and selector in states:
            continue
        states.add(selector)
        task_id = "KYC-" + selector if reusable else app["id"]
        actor = {
            "assignment": ASSIGNMENT,
            "environment_version": VERSION,
            "policy_bundle": VERSION,
            "output_schema": "golden-kyc-recommendation-v1",
        }
        if not reusable:
            actor.update(
                application_id=app["id"],
                application_sha256=app["snapshot_sha256"],
                account_type=app["snapshot"]["product"],
            )
        else:
            actor["task_mode"] = mode
        actor["objective"] = ASSIGNMENT
        if application_types:
            actor["workflow_product"] = selector
        else:
            actor["governing_state"] = state
        source = {
            "schema_version": "anvil.golden-kyc.task.v1",
            "task_id": task_id,
            "task_version": version,
            "actor": actor,
            "origin": "original_synthetic",
        }
        tasks.append(
            {
                "task_id": task_id,
                "task_version": version,
                "title": PRODUCT_NAMES[selector] if application_types else NAMES[state]
                if reusable
                else f"Golden Bank KYC · {app['snapshot']['product']} · {state} · {app['id']}",
                "payload_sha256": digest(source),
                "source": source,
                "actor": actor,
                "environment_ids": [ENVIRONMENT_KEY],
                "dimensions": {
                    name: "correctness" if i < 6 else "evidence" if i < 8 else "constraints"
                    for i, name in enumerate(CRITERIA)
                },
                "failure_modes": [],
                "rubric": {
                    "criteria": [
                        {"id": name, "description": name.replace("_", " "), "points": 5}
                        for name in CRITERIA
                    ]
                },
            }
        )
    content = {
        "source_project": {
            "id": "golden-bank-kyc",
            "version": version,
            "name": "Golden Bank KYC · four reusable application workflows" if application_types else "Golden Bank KYC · five reusable state workflows"
            if reusable
            else "Golden Bank KYC ·200 applications",
        },
        "environments": [
            {
                "id": ENVIRONMENT_KEY,
                "name": "Golden KYC versioned banking environment",
                "version": version,
                "kind": "golden-kyc-postgres-openenv-harbor-v1",
                "enforce": True,
            }
        ],
        "tasks": tasks,
    }
    if application_types and states != set(PRODUCT_NAMES):
        raise HTTPException(409, "Golden software qualification requires all four workflow types")
    group = catalog.store(c, project, user, content, None)
    prior = (
        c.execute(
            "SELECT * FROM banking.anvil_imports WHERE project_id=%s AND manifest->>'source_sha256'=%s ORDER BY created_at DESC LIMIT 1",
            (project, current),
        ).fetchone()
        if reusable
        else None
    )
    if prior:
        validate(c, prior)
    evaluators = prior["manifest"]["evaluators"] if prior else _evaluators(c, project, user)
    epack_id, environment_id = uid(), uid()
    public_pack = {
        "schema_version": "anvil.golden-kyc-environment-pack.v1",
        "seed": manifest["seed"],
        "origin": manifest["data_provenance"],
        "banking_pack_id": str(pack),
        "application_count": len(apps),
        "policy_bundle": library(),
        "applications": [{"id": a["id"], "sha256": a["snapshot_sha256"]} for a in apps],
    }
    c.execute(
        "INSERT INTO anvil.environment_packs(id,project_id,template_id,scenario_id,content,content_sha256,validation,created_by) VALUES(%s,%s,'golden-kyc',%s,%s,%s,%s,%s) ON CONFLICT(project_id,content_sha256) DO NOTHING",
        (
            epack_id,
            project,
            f"pilot-{len(apps)}",
            Jsonb(public_pack),
            digest(public_pack),
            Jsonb(
                {
                    "status": "software_import_validated",
                    "legal_review": "pending",
                    "independent_case_review": "pending",
                }
            ),
            user,
        ),
    )
    epack_id = c.execute(
        "SELECT id FROM anvil.environment_packs WHERE project_id=%s AND content_sha256=%s",
        (project, digest(public_pack)),
    ).fetchone()["id"]
    environment = {
        "schema_version": "anvil.golden-kyc-environment.v1",
        "template_id": "golden-kyc",
        "version": version,
        "banking_pack_id": str(pack),
        "pack_sha256": digest(public_pack),
        "source_sha256": current,
        "implementation_sha256": current,
        "runtime": "golden-kyc-postgres-v1",
        "openenv": "0.12.0",
        "harbor": "0.25.0",
        "reset": "before_every_application_model_repetition",
        "policy_sha256": manifest["policy_sha256"],
        "paid_calls": False,
        "model_performance": False,
        "legal_review": "pending",
        "tools": ["assigned_banking_api_v1"],
        "clock": "2026-11-11",
    }
    environment["logical_environment_sha256"] = digest(
        {
            "data_sha256": manifest["public_sha256"],
            "policy_sha256": manifest["policy_sha256"],
            "source_sha256": current,
            "seed": manifest["seed"],
            "runtime": environment["runtime"],
            "openenv": environment["openenv"],
            "harbor": environment["harbor"],
        }
    )
    c.execute(
        "INSERT INTO anvil.environment_versions(id,project_id,pack_id,name,manifest,manifest_sha256,created_by) VALUES(%s,%s,%s,'Golden Bank KYC',%s,%s,%s)",
        (environment_id, project, epack_id, Jsonb(environment), digest(environment), user),
    )
    bindings = []
    for task in tasks:
        identifier = uid()
        snapshot = {
            "schema_version": "anvil.golden-kyc-binding.v1",
            "environment_manifest_sha256": digest(environment),
            "task_payload_sha256": task["payload_sha256"],
            "source_sha256": current,
            "fields": [],
            "evaluators": evaluators,
            "rubric_points": 100,
            "legal_review": "pending",
            "independent_expectation_review": "pending",
        }
        if reusable:
            state = task["actor"].get("governing_state")
            product = task["actor"].get("workflow_product")
            snapshot["case_dataset"] = dataset.reference().model_dump()
            snapshot["case_selector"] = {
                "field": "product" if application_types else "governing_state",
                "value": product if application_types else state,
                "case_count": sum(a["snapshot"]["product" if application_types else "governing_state"]
                                  == (product if application_types else state) for a in apps),
            }
            snapshot["policy_scopes"] = {
                "bank_bundle_sha256": manifest["policy_sha256"],
                **({"applicability": "actual_application_state_charter_date"} if application_types else {"state": state}),
                "federal_legal_review": "pending",
                "state_legal_review": "pending",
            }
        c.execute(
            "INSERT INTO anvil.environment_task_bindings(id,project_id,environment_id,task_group_id,task_id,task_version,snapshot,snapshot_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                identifier,
                project,
                environment_id,
                group["id"],
                task["task_id"],
                task["task_version"],
                Jsonb(snapshot),
                digest(snapshot),
                user,
            ),
        )
        bindings.append(
            {
                "task_id": task["task_id"],
                "binding_id": identifier,
                "binding_sha256": digest(snapshot),
            }
        )
    frozen = {
        "schema_version": "anvil.golden-kyc-import.v1",
        "source_sha256": current,
        "banking_pack_id": str(pack),
        "data_manifest_sha256": digest(manifest),
        "task_group_sha256": digest(content),
        "environment_manifest_sha256": digest(environment),
        "evaluators": evaluators,
        "bindings": bindings,
        "paid_calls": False,
    }
    if reusable:
        frozen.update(
            task_mode=mode,
            case_dataset=dataset.reference().model_dump(),
            case_dataset_manifest=dataset.model_dump(),
        )
        frozen["case_assignments"] = application_assignments(dataset, apps) if application_types else [
            {
                "application_id": member.id,
                "application_sha256": member.snapshot_sha256,
                "governing_state": member.governing_state,
                "task_id": "KYC-" + member.governing_state,
            }
            for member in dataset.cases
        ]
    identifier = uid()
    row = c.execute(
        "INSERT INTO banking.anvil_imports(id,project_id,pack_id,task_group_id,environment_id,manifest,manifest_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            identifier,
            project,
            pack,
            group["id"],
            environment_id,
            Jsonb(frozen),
            digest(frozen),
            user,
        ),
    ).fetchone()
    return public(row)


def public(row):
    return {
        "id": str(row["id"]),
        "pack_id": str(row["pack_id"]),
        "task_group_id": str(row["task_group_id"]),
        "environment_id": str(row["environment_id"]),
        "manifest_sha256": row["manifest_sha256"],
        "binding_count": len(row["manifest"]["bindings"]),
        "evaluator_count": len(row["manifest"]["evaluators"]),
        "readiness": readiness(row),
        "manifest": row["manifest"],
    }


def readiness(row):
    return {
        "software_run": "ready"
        if row["manifest"]["source_sha256"] == source_hash()
        else "source_changed",
        "model_benchmark": "blocked",
        "paid_calls": False,
        "review_blockers": [
            "state_and_charter_legal_review",
            "independent_case_expectation_review",
        ],
        "native_harbor": "requires_exact_linux_qualification",
    }


def validate(c, row):
    if (
        digest(row["manifest"]) != row["manifest_sha256"]
        or row["manifest"]["source_sha256"] != source_hash()
    ):
        raise HTTPException(
            409, "Golden import implementation changed; reimport and qualify new binding"
        )
    binding(c, row["project_id"], row["pack_id"])
    if row["manifest"].get("task_mode") in {"reusable_state_workflow", "reusable_application_workflow"}:
        dataset = CaseDataset.model_validate(row["manifest"]["case_dataset_manifest"])
        apps = c.execute(
            "SELECT id,snapshot,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id",
            (row["project_id"], row["pack_id"]),
        ).fetchall()
        actual = from_snapshots(dataset.id, dataset.version, apps)
        product_mode = row["manifest"]["task_mode"] == "reusable_application_workflow"
        assignments = application_assignments(actual, apps) if product_mode else [
            {
                "application_id": m.id,
                "application_sha256": m.snapshot_sha256,
                "governing_state": m.governing_state,
                "task_id": "KYC-" + m.governing_state,
            }
            for m in actual.cases
        ]
        if (
            actual != dataset
            or row["manifest"]["case_dataset"] != actual.reference().model_dump()
            or row["manifest"]["case_assignments"] != assignments
            or {b["task_id"] for b in row["manifest"]["bindings"]}
            != {"KYC-" + value for value in (PRODUCT_NAMES if product_mode else NAMES)}
        ):
            raise HTTPException(409, "State-task dataset membership or routing changed")
    env = c.execute(
        "SELECT manifest,manifest_sha256 FROM anvil.environment_versions WHERE id=%s",
        (row["environment_id"],),
    ).fetchone()
    if (
        not env
        or digest(env["manifest"]) != row["manifest"]["environment_manifest_sha256"]
        or env["manifest_sha256"] != digest(env["manifest"])
    ):
        raise HTTPException(409, "Environment binding changed")
    for e in row["manifest"]["evaluators"]:
        config = configurations.get(c, e["configuration_id"])
        receipt = c.execute(
            "SELECT evidence_sha256 FROM anvil.evaluator_validation_receipts WHERE id=%s AND configuration_id=%s",
            (e["validation_id"], e["configuration_id"]),
        ).fetchone()
        revoked = c.execute(
            "SELECT 1 FROM anvil.evaluator_revocations WHERE configuration_id=%s",
            (e["configuration_id"],),
        ).fetchone()
        if (
            not config
            or config["status"] != "ready"
            or config["configuration_sha256"] != e["configuration_sha256"]
            or not receipt
            or receipt["evidence_sha256"] != e["validation_sha256"]
            or revoked
        ):
            raise HTTPException(409, "Evaluator binding revoked or changed")


def start(c, project, user, import_id, repetitions=1):
    row = c.execute(
        "SELECT * FROM banking.anvil_imports WHERE project_id=%s AND id=%s", (project, import_id)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Golden import not found")
    validate(c, row)
    case_count = row["manifest"].get("case_dataset", {}).get("case_count", 200)
    # Creation of banking trials is scheduler-only. A queued command retains the
    # actual requester; ordinary API cannot create or change observed state.
    run_id, plan_id = uid(), uid()
    snapshot = {
        "schema_version": SCHEMA,
        "name": "Golden Bank KYC software qualification",
        "task_group_id": str(row["task_group_id"]),
        "source_sha256": source_hash(),
        "import_id": str(import_id),
        "import_sha256": row["manifest_sha256"],
        "environment_id": str(row["environment_id"]),
        "environment_manifest_sha256": row["manifest"]["environment_manifest_sha256"],
        "tasks": [
            {
                "task_id": b["task_id"],
                "binding_id": b["binding_id"],
                "binding_sha256": b["binding_sha256"],
            }
            for b in row["manifest"]["bindings"]
        ],
        "models": [CANDIDATE],
        "environments": [{"id": ENVIRONMENT_KEY, "name": "Golden KYC", "version": VERSION}],
        "methods": [
            {"id": "golden-kyc-rubric-v1", "name": "Golden KYC100point rubric", "version": VERSION}
        ],
        "planned_cells": case_count * repetitions,
        "repetitions": repetitions,
        "paid_calls": False,
        "model_performance": False,
    }
    if row["manifest"].get("task_mode") in {"reusable_state_workflow", "reusable_application_workflow"}:
        snapshot.update(
            case_dataset=row["manifest"]["case_dataset"],
            case_assignments=row["manifest"]["case_assignments"],
        )
    snapshot["policy_set_id"] = None
    snapshot["harness"] = "openenv-0.12.0"
    snapshot["policy_set_sha256"] = None
    snapshot["methods"][0].update(
        status="ready",
        kind="deterministic",
        scope="Software qualification; unreviewed expectations remain unscored",
        reason=None,
    )
    snapshot["mappings"] = [
        e | {"rule_id": e["requirement"], "adapter_source_sha256": e["normalizer_source_sha256"]}
        for e in row["manifest"]["evaluators"]
    ]
    if type(repetitions) is not int or not 1 <= repetitions <= 10:
        raise HTTPException(422, "Repetitions must be1–10")
    c.execute(
        "INSERT INTO anvil.benchmark_execution_plans(id,project_id,task_group_id,name,snapshot,snapshot_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (
            plan_id,
            project,
            row["task_group_id"],
            snapshot["name"],
            Jsonb(snapshot),
            digest(snapshot),
            user,
        ),
    )
    c.execute(
        "INSERT INTO anvil.benchmark_runs(id,project_id,plan_id,snapshot,snapshot_sha256,report_policy,created_by,graph_thread_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            run_id,
            project,
            plan_id,
            Jsonb(snapshot),
            digest(snapshot),
            Jsonb(report_policy(c, project)),
            user,
            uid(),
        ),
    )
    # Runtime linking is done by scheduler in the same transaction as trial creation.
    c.execute(
        "INSERT INTO banking.execution_jobs(id,project_id,run_id) VALUES(%s,%s,%s)",
        (uid(), project, run_id),
    )
    return {
        "run_id": run_id,
        "plan_id": plan_id,
        "planned_cells": case_count * repetitions,
        "state": "queued",
        "paid_calls": False,
        "model_performance": False,
    }
