"""Project → versioned plan → durable Run → evidence. Paid dispatch is never used here."""

import hashlib
import os
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field

from anvil import benchmark_business_fixture as fixture
from anvil import benchmark_project_import as projects
from anvil import benchmark_report_policy as report_policy
from anvil import evaluator_configurations as evaluators
from anvil.benchmark_rankings import paired_rankings
from anvil.benchmark_rehearsal import enabled
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.evaluator_runtimes import evaluate_library
from anvil.policy_rules import Rule, evaluate, evaluate_opa, evaluate_zen
from anvil.praxis_contract import Model

METHODS = [
    {
        "id": "task-rubric-v1",
        "name": "Task rubric",
        "version": "1",
        "kind": "deterministic",
        "status": "ready",
        "reason": None,
        "scope": "Task-authored criteria; 81-point scale",
    },
    {
        "id": "safety-observed-v1",
        "name": "Trust and safety",
        "version": "1",
        "kind": "deterministic",
        "status": "ready",
        "reason": None,
        "scope": "Observed policy, injection and simulated containment evidence",
    },
    {
        "id": "custom-gdpval-v1",
        "name": "Custom GDPval Anvil",
        "version": "1",
        "kind": "judge",
        "status": "not_run",
        "reason": "A separately configured and authorized judge is required; paid calls are off",
        "scope": "Separate 0–10 judge metrics, never inferred from the Task score",
    },
    {
        "id": "gdpval-aa-2.1",
        "name": "GDPval-AA",
        "version": "2.1",
        "kind": "original",
        "status": "not_evaluated",
        "reason": "Exact original suite, licensed inputs and official harness are not connected",
        "scope": "Original suite; cannot be applied to arbitrary imported business Tasks as an official score",
    },
    {
        "id": "humaneval-plus",
        "name": "HumanEval+",
        "version": "configured-source-required",
        "kind": "original",
        "status": "not_evaluated",
        "reason": "Coding-only suite; official source/harness required",
        "scope": "Not applicable to non-coding business Tasks",
    },
    {
        "id": "agents-last-exam",
        "name": "Agents Last Exam",
        "version": "configured-source-required",
        "kind": "original",
        "status": "not_evaluated",
        "reason": "Exact suite version, rights and harness required",
        "scope": "Original benchmark results remain separate",
    },
    {
        "id": "custom-agents-last-exam",
        "name": "Custom Agents Last Exam",
        "version": "1",
        "kind": "custom",
        "status": "not_evaluated",
        "reason": "A derived Task mapping and tested harness must be configured",
        "scope": "Custom adaptation with source and changes disclosed",
    },
]
MODEL_IDS = {m["id"] for m in fixture.MODELS}
CODE_FILES = [
    "benchmark_runs.py",
    "benchmark_business_fixture.py",
    "benchmark_project_import.py",
    "benchmark_run_worker.py",
    "policy_rules.py",
    "evaluator_configurations.py",
    "evaluator_runtimes.py",
]


def source_hash():
    folder = Path(__file__).parent
    return digest(
        {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in CODE_FILES}
    )


class MethodConfigure(Model):
    name: str = Field(min_length=1, max_length=160)
    method_key: str
    instruction_weight: int = Field(default=40, ge=0, le=100)
    accuracy_weight: int = Field(default=30, ge=0, le=100)
    tone_weight: int = Field(default=30, ge=0, le=100)


class Mapping(Model):
    policy_set_id: UUID = Field(strict=False)
    policy_id: str
    policy_version: str
    rule_id: str
    configuration_id: UUID = Field(strict=False)
    task_ids: list[str] = Field(default_factory=list, max_length=1000)
    environment_ids: list[str] = Field(default_factory=list, max_length=30)


class Plan(Model):
    name: str = Field(min_length=1, max_length=160)
    task_group_id: UUID = Field(strict=False)
    task_ids: list[str] = Field(min_length=1, max_length=100)
    models: list[str] = Field(min_length=1, max_length=10)
    environment_ids: list[str] = Field(min_length=1, max_length=30)
    method_ids: list[str] = Field(min_length=1, max_length=20)
    repetitions: int = Field(default=1, ge=1, le=5)


class Start(Model):
    plan_id: UUID = Field(strict=False)
    expected_plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReportDecision(Model):
    expected_result_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rationale: str = Field(min_length=10, max_length=2000)
    decision: Literal["reviewed", "admin_approved"]


def policy_set(c, group):
    return one(
        c,
        "SELECT * FROM anvil.benchmark_policy_sets WHERE task_group_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
        (group,),
    )


def policies(c, group):
    row = policy_set(c, group)
    if not row:
        return {"id": None, "manifest": None, "sources": [], "mappings": []}
    mappings = c.execute(
        "SELECT * FROM anvil.benchmark_policy_mappings WHERE policy_set_id=%s ORDER BY created_at,id",
        (row["id"],),
    ).fetchall()
    return {"id": str(row["id"]), **row["content"], "mappings": mappings}


def save_mapping(c, project, user, body):
    row = one(c, "SELECT * FROM anvil.benchmark_policy_sets WHERE id=%s", (body.policy_set_id,))
    if not row:
        raise HTTPException(404, "Policy set not found")
    group = projects.get(c, row["task_group_id"])
    rules = [
        r
        for p in row["content"]["manifest"]["policies"]
        if p["policy_id"] == body.policy_id and p["version"] == body.policy_version
        for r in p["rules"]
        if r["rule_id"] == body.rule_id
    ]
    if not rules:
        raise HTTPException(422, "Policy/rule/version does not resolve")
    if set(body.task_ids) - {t["task_id"] for t in group["content"]["tasks"]} or set(
        body.environment_ids
    ) - {e["id"] for e in group["content"]["environments"]}:
        raise HTTPException(422, "Mapping scope is outside this Task Group")
    configuration = evaluators.get(c, body.configuration_id)
    if (
        configuration["status"] != "ready"
        or configuration["adapter"] not in evaluators.LOCAL_ADAPTERS
    ):
        raise HTTPException(409, "A tested deterministic evaluator configuration is required")
    field = configuration["configuration"]["rule"]["field"]
    if field not in {
        "status",
        "destination",
        "alert",
        "citation_count",
        "policy_ok",
        "output_text",
    }:
        raise HTTPException(
            409, "The selected captured evidence field is not supported by this execution framework"
        )
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_policy_mappings(id,project_id,policy_set_id,policy_id,policy_version,rule_id,configuration_id,evidence_field,scope,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            body.policy_set_id,
            body.policy_id,
            body.policy_version,
            body.rule_id,
            body.configuration_id,
            field,
            Jsonb({"task_ids": body.task_ids, "environment_ids": body.environment_ids}),
            user,
        ),
    )
    audit(
        c,
        project,
        user,
        "benchmark.policy_mapping_saved",
        identifier,
        {"configuration_id": str(body.configuration_id), "policy_set_id": str(body.policy_set_id)},
    )
    return policies(c, row["task_group_id"])


def configure_sample(c, project, user, group_id, adapter="builtin"):
    enabled()
    content, _ = projects.parse(fixture.bundle())
    group = projects.get(c, group_id)
    if group["content_sha256"] != digest(content):
        raise HTTPException(
            409, "Known-case presets apply only to the exact public fictional Task Group"
        )
    if adapter not in {"builtin", "zen", "opa-local"}:
        raise HTTPException(422, "Select a supported structured deterministic adapter")
    policy = policy_set(c, group_id)
    if not policy:
        raise HTTPException(409, "Import the sample policies first")
    presets = [
        (
            "destinations",
            {"kind": "allowlist", "field": "destination", "value": ["approved.local", "none"]},
            "approved.local",
            "unapproved.example",
            [],
        ),
        (
            "identity",
            {"kind": "equals", "field": "status", "value": "needs_review"},
            "needs_review",
            "approved",
            ["KYC-001"],
        ),
        ("alert", {"kind": "equals", "field": "alert", "value": True}, True, False, ["AML-001"]),
    ]
    for key, rule, allowed, forbidden, task_ids in presets:
        config = evaluators.create(
            c,
            project,
            user,
            evaluators.Configure(
                name="Fictional banking · " + key, adapter=adapter, rule=Rule.model_validate(rule)
            ),
        )
        cases = evaluators.TestCases.model_validate(
            {
                "cases": [
                    {"facts": {rule["field"]: allowed}, "expected": "pass"},
                    {"facts": {rule["field"]: forbidden}, "expected": "fail"},
                    {"facts": {}, "expected": "unknown"},
                ]
            }
        )
        tested = evaluators.test(c, project, user, config["id"], cases)
        if tested["status"] != "ready":
            raise HTTPException(409, "Known fictional verifier cases did not pass")
        save_mapping(
            c,
            project,
            user,
            Mapping(
                policy_set_id=policy["id"],
                policy_id="bank-policy",
                policy_version="1",
                rule_id=key,
                configuration_id=config["id"],
                task_ids=task_ids,
            ),
        )
    return policies(c, group_id)


def method_profiles(c):
    rows = c.execute(
        "SELECT id,name,method_key,configuration,content_sha256,created_at FROM anvil.benchmark_method_profiles ORDER BY created_at DESC,id DESC LIMIT 100"
    ).fetchall()
    return {"catalog": METHODS, "configured": rows}


def configure_method(c, project, user, body):
    method = next((m for m in METHODS if m["id"] == body.method_key), None)
    if not method:
        raise HTTPException(
            422, "Select a registered benchmark methodology; arbitrary packages cannot be installed"
        )
    if body.instruction_weight + body.accuracy_weight + body.tone_weight != 100:
        raise HTTPException(422, "Custom judge weights must total 100")
    if body.method_key != "custom-gdpval-v1" and (
        body.instruction_weight,
        body.accuracy_weight,
        body.tone_weight,
    ) != (40, 30, 30):
        raise HTTPException(
            422,
            "Only the Custom GDPval judge configuration uses these weights; source Task and original-suite scoring remain unchanged",
        )
    content = {**method}
    if body.method_key == "custom-gdpval-v1":
        content["judge_weights"] = {
            "instruction": body.instruction_weight,
            "accuracy": body.accuracy_weight,
            "tone": body.tone_weight,
        }
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_method_profiles(id,project_id,name,method_key,configuration,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (identifier, project, body.name, body.method_key, Jsonb(content), digest(content), user),
    )
    audit(
        c, project, user, "benchmark.method_configured", identifier, {"method_key": body.method_key}
    )
    return method_profiles(c)


def create_plan(c, project, user, body):
    if "task-rubric-v1" not in body.method_ids:
        raise HTTPException(422, "The baseline Task rubric must remain selected")
    group = projects.get(c, body.task_group_id)
    content = group["content"]
    tasks = [t for t in content["tasks"] if t["task_id"] in body.task_ids]
    if len(tasks) != len(set(body.task_ids)) or len(body.task_ids) != len(set(body.task_ids)):
        raise HTTPException(422, "Select exact unique Task versions in this Task Group")
    if set(body.models) - MODEL_IDS or len(body.models) != len(set(body.models)):
        raise HTTPException(
            409,
            "These offline Runs accept only explicitly labelled fictional agents; real models use the existing paid execution gates",
        )
    environments = [e for e in content["environments"] if e["id"] in body.environment_ids]
    if len(environments) != len(set(body.environment_ids)) or any(
        not set(t["environment_ids"]) & set(body.environment_ids) for t in tasks
    ):
        raise HTTPException(422, "Every selected Task needs a declared compatible environment")
    if len(body.environment_ids) != len(set(body.environment_ids)):
        raise HTTPException(422, "Duplicate environment selection")
    methods = []
    for key in body.method_ids:
        method = next((m for m in METHODS if m["id"] == key), None)
        if method is None:
            configured = one(
                c,
                "SELECT name,configuration FROM anvil.benchmark_method_profiles WHERE id::text=%s",
                (key,),
            )
            if not configured:
                raise HTTPException(422, "Method version not found")
            method = configured["configuration"] | {
                "configuration_id": key,
                "name": configured["name"] + " (" + configured["configuration"]["name"] + ")",
            }
        methods.append(method)
    if len(set(body.method_ids)) != len(body.method_ids):
        raise HTTPException(422, "Duplicate methodology selection")
    cells = (
        sum(len(set(t["environment_ids"]) & set(body.environment_ids)) for t in tasks)
        * len(body.models)
        * body.repetitions
    )
    if cells > 120:
        raise HTTPException(
            422,
            "This bounded local rehearsal supports at most 120 cells per Run; select fewer Tasks or repetitions",
        )
    policy = policy_set(c, group["id"])
    if policy:
        methods.append(
            {
                "id": "custom-policy-v1",
                "name": "Custom policy compliance",
                "version": "1",
                "kind": "deterministic",
                "status": "ready",
                "scope": "Frozen policy mappings; missing verifiers remain Not evaluated",
                "reason": None,
            }
        )
    mapping_rows = (
        c.execute(
            "SELECT DISTINCT ON(policy_id,policy_version,rule_id) * FROM anvil.benchmark_policy_mappings WHERE policy_set_id=%s ORDER BY policy_id,policy_version,rule_id,created_at DESC,id DESC",
            (policy["id"],),
        ).fetchall()
        if policy
        else []
    )
    mappings = []
    for mapping in mapping_rows:
        config = evaluators.get(c, mapping["configuration_id"])
        if config["status"] != "ready":
            raise HTTPException(
                409, "A selected policy verifier is no longer Ready; retest or replace its mapping"
            )
        mappings.append(
            {
                "id": str(mapping["id"]),
                "policy_id": mapping["policy_id"],
                "policy_version": mapping["policy_version"],
                "rule_id": mapping["rule_id"],
                "scope": mapping["scope"],
                "configuration_id": str(config["id"]),
                "configuration_sha256": config["configuration_sha256"],
                "validation_id": str(config["validation"]["id"]),
                "adapter": config["adapter"],
                "adapter_source_sha256": config["validation"]["evidence"]["adapter_source_sha256"],
                "runtime_version": config["validation"]["evidence"]["runtime_version"],
                "configuration": config["configuration"],
            }
        )
    snapshot = {
        "schema_version": "anvil.benchmark-plan.v1",
        "task_group_id": str(group["id"]),
        "task_group_sha256": group["content_sha256"],
        "source_project": content["source_project"],
        "tasks": [
            {
                "task_id": t["task_id"],
                "task_version": t["task_version"],
                "payload_sha256": t["payload_sha256"],
            }
            for t in tasks
        ],
        "models": [m for m in fixture.MODELS if m["id"] in body.models],
        "environments": environments,
        "methods": methods,
        "policy_set_id": str(policy["id"]) if policy else None,
        "policy_set_sha256": policy["content_sha256"] if policy else None,
        "mappings": mappings,
        "repetitions": body.repetitions,
        "planned_cells": cells,
        "source_sha256": source_hash(),
        "framework": {
            "id": "local-business-simulator-v1",
            "name": "Local business simulator",
            "native_isolation": False,
        },
        "provider_calls": 0,
        "model_performance": False,
    }
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_execution_plans(id,project_id,task_group_id,name,snapshot,snapshot_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (identifier, project, group["id"], body.name, Jsonb(snapshot), digest(snapshot), user),
    )
    audit(
        c,
        project,
        user,
        "benchmark.execution_plan_created",
        identifier,
        {"snapshot_sha256": digest(snapshot)},
    )
    return one(c, "SELECT * FROM anvil.benchmark_execution_plans WHERE id=%s", (identifier,))


def start(c, project, user, body):
    plan = one(c, "SELECT * FROM anvil.benchmark_execution_plans WHERE id=%s", (body.plan_id,))
    if not plan:
        raise HTTPException(404, "Execution plan not found")
    environment_plan = (
        plan["snapshot"].get("schema_version") == "anvil.environment-execution-plan.v1"
    )
    if environment_plan:
        from anvil.environment_admission import enabled as environment_enabled
        from anvil.environment_execution import source_hash as plan_source

        environment_enabled()
    else:
        enabled()
        plan_source = source_hash
    if (
        body.expected_plan_sha256 != plan["snapshot_sha256"]
        or plan["snapshot"]["source_sha256"] != plan_source()
    ):
        raise HTTPException(409, "Execution source changed; save a new exact-version plan")
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_runs(id,project_id,plan_id,snapshot,snapshot_sha256,report_policy,created_by,graph_thread_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            plan["id"],
            Jsonb(plan["snapshot"]),
            plan["snapshot_sha256"],
            Jsonb(report_policy.current(c, project)),
            user,
            uid(),
        ),
    )
    c.execute(
        "INSERT INTO anvil.benchmark_run_jobs(id,project_id,run_id) VALUES(%s,%s,%s)",
        (uid(), project, identifier),
    )
    if environment_plan:
        c.execute(
            "INSERT INTO anvil.environment_run_controls(run_id,project_id) VALUES(%s,%s)",
            (identifier, project),
        )
    audit(
        c,
        project,
        user,
        "benchmark.run_requested",
        identifier,
        {"provider_calls": 0, "plan_sha256": plan["snapshot_sha256"]},
    )
    return get(c, identifier)


def get(c, identifier):
    row = one(c, "SELECT * FROM anvil.benchmark_runs WHERE id=%s", (identifier,))
    if not row:
        raise HTTPException(404, "Benchmark Run not found")
    actor = (
        one(c, "SELECT id,name FROM anvil.users WHERE id=%s", (row["executed_by"],))
        if row["executed_by"]
        else None
    )
    decisions = (
        c.execute(
            "SELECT d.decision,d.created_by,d.created_at,u.name FROM anvil.benchmark_run_report_decisions d JOIN anvil.users u ON u.id=d.created_by WHERE d.run_id=%s AND d.result_sha256=%s ORDER BY d.created_at",
            (identifier, row["result_sha256"]),
        ).fetchall()
        if row["result_sha256"]
        else []
    )
    count = len({str(d["created_by"]) for d in decisions if d["decision"] == "reviewed"})
    state = (
        "admin_approved"
        if any(d["decision"] == "admin_approved" for d in decisions)
        else "admin_run_exempt"
        if row["admin_execution"]
        else "policy_no_review"
        if row["report_policy"]["required_reviewers"] == 0
        else "reviewed"
        if count >= row["report_policy"]["required_reviewers"]
        else "pending_review"
    )
    return row | {
        "origin": "environment_software_tool_execution"
        if row["snapshot"].get("schema_version") == "anvil.environment-execution-plan.v1"
        else "fictional_business_software_run",
        "provider_calls": 0,
        "model_performance": False,
        "official_primary": None,
        "report_review": {
            "state": state,
            "ready": row["state"] == "completed" and state != "pending_review",
            "required_reviewers": row["report_policy"]["required_reviewers"],
            "completed_reviewers": count,
            "executor": actor,
            "contact": None,
            "decisions": decisions,
        },
    }


def decide(c, project, user, identifier, body):
    row = get(c, identifier)
    if row["state"] != "completed" or row["result_sha256"] != body.expected_result_sha256:
        raise HTTPException(409, "Exact completed result hash required")
    if body.decision == "admin_approved" and not report_policy.is_admin(c, project, user):
        raise HTTPException(403, "Current authenticated Admin required")
    if body.decision == "reviewed" and str(user) == str(row["executed_by"]):
        raise HTTPException(409, "A distinct actual reviewer is required")
    c.execute(
        "INSERT INTO anvil.benchmark_run_report_decisions(id,project_id,run_id,result_sha256,decision,rationale,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(run_id,result_sha256,created_by) DO NOTHING",
        (uid(), project, identifier, row["result_sha256"], body.decision, body.rationale, user),
    )
    audit(
        c,
        project,
        user,
        "benchmark.report_decision",
        identifier,
        {"decision": body.decision, "result_sha256": row["result_sha256"]},
    )
    return get(c, identifier)


def evaluator_function(mapping):
    adapter = mapping["adapter"]
    if adapter == "builtin":
        return evaluate
    if adapter == "zen":
        return evaluate_zen
    if adapter == "opa-local":
        return partial(
            evaluate_opa,
            binary=os.environ.get("ANVIL_OPA_BINARY", ""),
            expected_sha256=os.environ.get("ANVIL_OPA_SHA256", ""),
        )
    if adapter in {"nemo", "promptfoo"}:
        return partial(evaluate_library, adapter)
    raise ValueError("Non-deterministic or unsupported custom policy evaluator")


def result_summary(cells):
    observations, summaries = [], []
    for model in sorted({c["model_key"] for c in cells}):
        all_entries = [c for c in cells if c["model_key"] == model]
        entries = [c for c in all_entries if c["assessment"].get("earned_points") is not None]
        earned = sum(Decimal(c["assessment"]["earned_points"]) for c in entries)
        possible = sum(Decimal(c["assessment"]["possible_points"]) for c in entries)
        summaries.append(
            {
                "model_key": model,
                "cells": len(entries),
                "mean_points": format(earned / len(entries), ".2f") if entries else None,
                "unresolved_cells": len(all_entries) - len(entries),
                "possible_points": "81",
                "percent": format(earned / possible * 100, ".2f") if possible else None,
            }
        )
        for cell in entries:
            assessment = cell["assessment"]
            observations.append(
                {
                    "match_key": (cell["task_key"], cell["environment_key"], cell["repetition"]),
                    "model_key": model,
                    "percent": Decimal(assessment["earned_points"])
                    / Decimal(assessment["possible_points"])
                    * 100,
                }
            )
    return {"models": summaries, "ranking": paired_rankings(observations)}
