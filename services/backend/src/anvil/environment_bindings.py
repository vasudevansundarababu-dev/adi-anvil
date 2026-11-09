"""Frozen legacy rubric → registered evaluator → trusted field mapping.

No new domain rules, weights or policy approval. Unsupported task schemas are refused;
private references stay in the evaluator side and out of environment actor tools.
"""

import os
from functools import partial
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field

from anvil import environment_runtime as runtime
from anvil import evaluator_configurations as evaluators
from anvil.db import Jsonb, digest, one, uid
from anvil.evaluator_runtimes import evaluate_library
from anvil.policy_rules import Rule, evaluate, evaluate_opa, evaluate_zen
from anvil.praxis_contract import PraxisTask, grade
from anvil.schemas import Strict


class FieldMapping(Strict):
    target: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
    collection: str = Field(pattern=r"^[a-z][a-z0-9_]{0,60}$")
    record_id: str = Field(min_length=1, max_length=160)
    field: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
    transform: Literal["identity", "count"] = "identity"


class EvaluatorMapping(Strict):
    requirement: str = Field(min_length=1, max_length=100)
    kind: Literal["criterion", "constraint"]
    configuration_id: UUID


class Create(Strict):
    environment_id: UUID
    task_group_id: UUID
    task_id: str = Field(min_length=1, max_length=160)
    expected_task_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fields: list[FieldMapping] = Field(min_length=1, max_length=100)
    evaluators: list[EvaluatorMapping] = Field(min_length=1, max_length=100)


def public(row):
    snapshot = row["snapshot"]
    return {
        "id": row["id"],
        "environment_id": row["environment_id"],
        "task_group_id": row["task_group_id"],
        "task_id": row["task_id"],
        "task_version": row["task_version"],
        "snapshot_sha256": row["snapshot_sha256"],
        "created_at": row["created_at"],
        "fields": snapshot["fields"],
        "evaluators": [
            {
                k: e[k]
                for k in (
                    "requirement",
                    "kind",
                    "configuration_id",
                    "configuration_sha256",
                    "adapter",
                    "runtime_version",
                )
            }
            for e in snapshot["evaluators"]
        ],
        "cloud_ready": False,
        "live_dispatch": "disabled",
        "task_payload_sha256": snapshot["task_payload_sha256"],
    }


def expected_rule(binding):
    return Rule(
        kind={
            "json_equals": "equals",
            "json_number_min": "number_min",
            "json_number_max": "number_max",
        }[binding.kind],
        field=binding.field,
        value=binding.value,
    )


def options(c, environment):
    runtime.get(c, "environment_versions", environment)
    configurations = [
        evaluators.get(c, r["id"])
        for r in c.execute(
            "SELECT id FROM anvil.evaluator_configurations ORDER BY created_at DESC,id DESC LIMIT 100"
        ).fetchall()
    ]
    tasks = []
    for group in c.execute(
        "SELECT * FROM anvil.benchmark_task_groups ORDER BY created_at DESC,id DESC LIMIT 100"
    ).fetchall():
        for task in group["content"]["tasks"]:
            source = task.get("source", {})
            item = {
                "task_group_id": str(group["id"]),
                "task_group_name": group["name"],
                "task_id": task["task_id"],
                "task_version": task["task_version"],
                "title": task["title"],
                "payload_sha256": task["payload_sha256"],
                "requirements": [],
                "fields": [],
                "supported": False,
                "reason": "Installed bridge supports structured-decision-v1; this Task requires another exact rubric bridge",
            }
            if source.get("schema_version") == "praxis.anvil.task.v1":
                parsed = PraxisTask.model_validate(source)
                required_fields = set()
                for kind, requirement in [("criterion", r) for r in parsed.rubric.criteria] + [
                    ("constraint", r) for r in parsed.constraints
                ]:
                    rule = expected_rule(requirement.binding).model_dump()
                    required_fields.add(requirement.binding.field)
                    compatible = [
                        {"id": str(cfg["id"]), "name": cfg["name"], "adapter": cfg["adapter"]}
                        for cfg in configurations
                        if cfg["status"] == "ready" and cfg["configuration"].get("rule") == rule
                    ]
                    item["requirements"].append(
                        {
                            "kind": kind,
                            "id": requirement.id,
                            "description": requirement.description,
                            "field": requirement.binding.field,
                            "compatible_evaluators": compatible,
                        }
                    )
                item["fields"] = sorted(required_fields)
                item["supported"] = parsed.provenance.review.status == "approved"
                item["reason"] = (
                    "Frozen reviewed source; technical field/evaluator mappings still required"
                    if item["supported"]
                    else "Source snapshot is a draft; import a published reviewed revision from Praxis"
                )
            tasks.append(item)
    return tasks


def create(c, project, user, body):
    version = runtime.get(c, "environment_versions", body.environment_id)
    registered = one(
        c,
        "SELECT id FROM anvil.environment_receipts WHERE environment_id=%s AND kind='registration' LIMIT 1",
        (body.environment_id,),
    )
    if not registered:
        raise HTTPException(409, "Register this exact locally validated environment first")
    group = one(c, "SELECT * FROM anvil.benchmark_task_groups WHERE id=%s", (body.task_group_id,))
    if not group:
        raise HTTPException(404, "Imported Project snapshot not found")
    task = next((t for t in group["content"]["tasks"] if t["task_id"] == body.task_id), None)
    if not task:
        raise HTTPException(404, "Task not present in frozen Project snapshot")
    if task["payload_sha256"] != body.expected_task_sha256:
        raise HTTPException(409, "Task source hash changed")
    source = task.get("source", {})
    if source.get("schema_version") != "praxis.anvil.task.v1":
        raise HTTPException(
            409,
            "This evidence bridge supports structured-decision-v1 only; no fallback or rubric conversion",
        )
    parsed = PraxisTask.model_validate(source)
    if parsed.provenance.review.status != "approved":
        raise HTTPException(409, "Only a published reviewed Task snapshot can bind")
    requirements = [("criterion", r) for r in parsed.rubric.criteria] + [
        ("constraint", r) for r in parsed.constraints
    ]
    keys = [(m.kind, m.requirement) for m in body.evaluators]
    if len(set(keys)) != len(keys) or set(keys) != {(kind, r.id) for kind, r in requirements}:
        raise HTTPException(
            422, "Every original criterion and constraint needs exactly one evaluator"
        )
    needed = {r.binding.field for _, r in requirements}
    if (
        len({m.target for m in body.fields}) != len(body.fields)
        or {m.target for m in body.fields} != needed
    ):
        raise HTTPException(422, "Map each exact source binding field once, without extra fields")
    from anvil.environment_seeds import CATALOG

    collections = CATALOG[version["manifest"]["template_id"]]["collections"]
    if any(m.collection not in collections for m in body.fields):
        raise HTTPException(422, "Evidence collection is not provided by this environment")
    resolved = []
    for kind, requirement in requirements:
        mapping = next(
            m for m in body.evaluators if m.kind == kind and m.requirement == requirement.id
        )
        configuration = evaluators.get(c, mapping.configuration_id)
        if configuration["status"] != "ready":
            raise HTTPException(409, "Evaluator requires current passing known-case tests")
        if (
            configuration["configuration"].get("rule")
            != expected_rule(requirement.binding).model_dump()
        ):
            raise HTTPException(
                409,
                "Evaluator rule differs from the frozen source rubric/constraint; no reinterpretation allowed",
            )
        resolved.append(
            {
                "requirement": requirement.id,
                "kind": kind,
                "configuration_id": str(mapping.configuration_id),
                "configuration_sha256": configuration["configuration_sha256"],
                "adapter": configuration["adapter"],
                "runtime_version": configuration["validation"]["evidence"]["runtime_version"],
                "adapter_source_sha256": configuration["validation"]["evidence"][
                    "adapter_source_sha256"
                ],
                "validation_receipt_id": str(configuration["validation"]["id"]),
            }
        )
    snapshot = {
        "schema_version": "anvil.environment-task-binding.v1",
        "environment_manifest_sha256": version["manifest_sha256"],
        "pack_sha256": version["manifest"]["pack_sha256"],
        "task_payload_sha256": task["payload_sha256"],
        "group_sha256": group["content_sha256"],
        "task_source": source,
        "fields": [f.model_dump() for f in body.fields],
        "evaluators": resolved,
    }
    row = one(
        c,
        "INSERT INTO anvil.environment_task_bindings(id,project_id,environment_id,task_group_id,task_id,task_version,snapshot,snapshot_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            uid(),
            project,
            body.environment_id,
            body.task_group_id,
            parsed.task_id,
            parsed.task_version,
            Jsonb(snapshot),
            digest(snapshot),
            user,
        ),
    )
    return public(row)


def run_evaluator(configuration, facts):
    rule = Rule.model_validate(configuration["configuration"]["rule"])
    adapter = configuration["adapter"]
    engine = (
        evaluate_zen
        if adapter == "zen"
        else evaluate
        if adapter == "builtin"
        else partial(
            evaluate_opa,
            binary=os.environ.get("ANVIL_OPA_BINARY", ""),
            expected_sha256=os.environ.get("ANVIL_OPA_SHA256", ""),
        )
        if adapter == "opa-local"
        else partial(evaluate_library, adapter)
    )
    return engine(rule, facts)


def assess(c, project, user, binding_id, evidence_id):
    binding = one(c, "SELECT * FROM anvil.environment_task_bindings WHERE id=%s", (binding_id,))
    evidence = one(
        c,
        "SELECT * FROM anvil.environment_receipts WHERE id=%s AND kind='evidence'",
        (evidence_id,),
    )
    if not binding or not evidence:
        raise HTTPException(404, "Binding or trusted evidence not found")
    snapshot, captured = binding["snapshot"], evidence["content"]
    if (
        evidence["environment_id"] != binding["environment_id"]
        or captured["environment_manifest_sha256"] != snapshot["environment_manifest_sha256"]
        or captured["pack_sha256"] != snapshot["pack_sha256"]
        or digest(captured) != evidence["content_sha256"]
    ):
        raise HTTPException(409, "Evidence does not match the frozen environment/binding")
    facts, missing = {}, []
    for m in snapshot["fields"]:
        rows = captured["state"]["records"].get(m["collection"], [])
        row = next((r for r in rows if r["id"] == m["record_id"]), None)
        if row is None or row.get(m["field"]) is None:
            missing.append(m["target"])
        else:
            value = row[m["field"]]
            if m.get("transform") == "count":
                if not isinstance(value, list):
                    missing.append(m["target"])
                    continue
                value = len(value)
            facts[m["target"]] = value
    findings = []
    for m in snapshot["evaluators"]:
        configuration = evaluators.get(c, m["configuration_id"])
        qualified = configuration.get("validation") or {}
        known = qualified.get("evidence", {})
        if (
            configuration["status"] != "ready"
            or configuration["configuration_sha256"] != m["configuration_sha256"]
            or known.get("runtime_version") != m["runtime_version"]
            or known.get("adapter_source_sha256") != m["adapter_source_sha256"]
        ):
            result = {
                "outcome": "error",
                "reason": "Frozen evaluator is revoked, changed or no longer qualified",
            }
        else:
            try:
                result = run_evaluator(configuration, facts)
            except Exception:
                result = {"outcome": "error", "reason": "Evaluator execution failed; no fallback"}
        findings.append(
            {
                "requirement": m["requirement"],
                "kind": m["kind"],
                "evaluator_id": m["configuration_id"],
                "runtime_version": m["runtime_version"],
                "evidence_receipt_id": str(evidence_id),
                **result,
            }
        )
    source = PraxisTask.model_validate(snapshot["task_source"])
    resolved = not missing and all(f["outcome"] in ("pass", "fail") for f in findings)
    scoring = grade(source, facts) if resolved else None
    content = {
        "schema_version": "anvil.environment-evaluation.v1",
        "binding_sha256": binding["snapshot_sha256"],
        "evidence_sha256": evidence["content_sha256"],
        "task_payload_sha256": snapshot["task_payload_sha256"],
        "findings": findings,
        "missing_fields": missing,
        "score_status": "scored_original_formula" if resolved else "unresolved",
        "original_scoring": scoring,
        "source_formula": "hard-failure-zero-v1",
        "model_performance": False,
        "origin": "manual_environment_evidence_assessment",
        "provider_calls": 0,
        "policy_additional_weight": 0,
    }
    return one(
        c,
        "INSERT INTO anvil.environment_evaluations(id,project_id,binding_id,evidence_receipt_id,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (uid(), project, binding_id, evidence_id, Jsonb(content), digest(content), user),
    )
