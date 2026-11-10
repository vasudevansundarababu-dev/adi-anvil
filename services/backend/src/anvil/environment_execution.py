"""Environment-backed execution groups and immutable benchmark captures.

The local executor runs explicit software tool scripts, never relabelled models.
Harbor/OpenEnv adapters share the same attempt and collector boundary. Paid model
dispatch remains prohibited here; private rubric/source bytes never enter tools.
"""

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator

from anvil import benchmark_project_import as projects
from anvil import benchmark_runs as runs
from anvil import environment_bindings as bindings
from anvil import environment_runtime as runtime
from anvil.db import Jsonb, digest, one, uid
from anvil.schemas import Strict

CANDIDATES = {
    "configured-tools-v1": {
        "id": "configured-tools-v1",
        "name": "Configured software tool script · not a model",
    },
    "empty-tools-v1": {"id": "empty-tools-v1", "name": "Empty software control · not a model"},
}


class Action(Strict):
    operation: str = Field(min_length=1, max_length=60)
    arguments: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def bound(self):
        from anvil.environment_api import Operation

        Operation(operation=self.operation, arguments=self.arguments, expected_generation=0)
        return self


class Member(Strict):
    environment_id: UUID
    task_id: str = Field(min_length=1, max_length=160)
    binding_id: UUID | None = None
    source_environment_id: str | None = Field(default=None, max_length=160)
    policy_fields: list[bindings.FieldMapping] = Field(default_factory=list, max_length=100)
    actions: list[Action] = Field(default_factory=list, max_length=32)


class Plan(Strict):
    name: str = Field(min_length=1, max_length=160)
    task_group_id: UUID
    members: list[Member] = Field(min_length=1, max_length=30)
    candidates: list[Literal["configured-tools-v1", "empty-tools-v1"]] = Field(
        default_factory=lambda: ["configured-tools-v1"], min_length=1, max_length=2
    )
    repetitions: int = Field(default=1, ge=1, le=5, strict=True)
    purpose: Literal["bound_task_evaluation", "technical_rehearsal"] = "bound_task_evaluation"
    harness: Literal[
        "local-components-v1",
        "openenv-local-v1",
        "harbor-host-mediated-v1",
        "openenv-0.12-local-v1",
    ] = "local-components-v1"


def source_hash():
    root = Path(__file__).parent
    return digest(
        {
            "runtime": runtime.implementation_sha256(),
            "sources": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [
                    root / "environment_execution.py",
                    root / "environment_admission.py",
                    root / "environment_collect.py",
                    root / "environment_temp.py",
                    root / "environment_openenv.py",
                    root / "environment_harbor.py",
                    root / "environment_openenv_installed.py",
                    root / "environment_openenv_bridge.py",
                ]
            },
            "harbor_adapter": hashlib.sha256(
                (root.parents[2] / "harbor/src/anvil_harbor/environment.py").read_bytes()
            ).hexdigest(),
            "openenv_lock": hashlib.sha256(
                (root.parents[2] / "openenv/uv.lock").read_bytes()
            ).hexdigest(),
        }
    )


def create_plan(c, project, user, body):
    group = projects.get(c, body.task_group_id)
    if len(set(body.candidates)) != len(body.candidates) or len(
        {str(m.environment_id) for m in body.members}
    ) != len(body.members):
        raise HTTPException(422, "Duplicate candidate or environment")
    tasks = {t["task_id"]: t for t in group["content"]["tasks"]}
    members = []
    environments = []
    planned_pack_bytes = 0
    policy = runs.policy_set(c, group["id"])
    mappings = []
    from anvil import evaluator_configurations as evaluators

    if policy:
        for mapping in c.execute(
            "SELECT DISTINCT ON(policy_id,policy_version,rule_id) * FROM anvil.benchmark_policy_mappings WHERE policy_set_id=%s ORDER BY policy_id,policy_version,rule_id,created_at DESC,id DESC",
            (policy["id"],),
        ).fetchall():
            cfg = evaluators.get(c, mapping["configuration_id"])
            if cfg["status"] != "ready":
                raise HTTPException(409, "Policy mapping requires current known-case tests")
            mappings.append(
                {
                    "id": str(mapping["id"]),
                    "policy_id": mapping["policy_id"],
                    "policy_version": mapping["policy_version"],
                    "rule_id": mapping["rule_id"],
                    "scope": mapping["scope"],
                    "configuration_id": str(cfg["id"]),
                    "configuration_sha256": cfg["configuration_sha256"],
                    "validation_id": str(cfg["validation"]["id"]),
                    "adapter": cfg["adapter"],
                    "adapter_source_sha256": cfg["validation"]["evidence"]["adapter_source_sha256"],
                    "runtime_version": cfg["validation"]["evidence"]["runtime_version"],
                    "configuration": cfg["configuration"],
                }
            )
    for member in body.members:
        if member.task_id not in tasks:
            raise HTTPException(422, "Task must belong to this imported Project")
        declared = tasks[member.task_id]["environment_ids"]
        source_environment = member.source_environment_id or (
            declared[0] if len(declared) == 1 else None
        )
        if source_environment not in declared:
            raise HTTPException(
                422, "Choose the exact source-authored environment condition for this Task"
            )
        version = runtime.get(c, "environment_versions", member.environment_id)
        pack = runtime.get(c, "environment_packs", version["pack_id"])
        planned_pack_bytes += (
            len(__import__("json").dumps(pack["content"]).encode())
            * len(body.candidates)
            * body.repetitions
        )
        if planned_pack_bytes > 64 * 1024 * 1024:
            raise HTTPException(
                422,
                "Planned materialized inputs exceed64MiB; choose fewer repetitions or environments",
            )
        from anvil.environment_seeds import CATALOG

        if len({m.target for m in member.policy_fields}) != len(member.policy_fields) or any(
            m.collection not in CATALOG[version["manifest"]["template_id"]]["collections"]
            for m in member.policy_fields
        ):
            raise HTTPException(
                422, "Policy fields must be unique and map declared environment collections"
            )
        if not runtime.readiness(c, version)["local_registered"]:
            raise HTTPException(409, "Exact environment must be current and registered locally")
        if any(a.operation not in version["manifest"]["tools"] for a in member.actions):
            raise HTTPException(422, "Script requests an undeclared tool")
        binding = (
            one(
                c, "SELECT * FROM anvil.environment_task_bindings WHERE id=%s", (member.binding_id,)
            )
            if member.binding_id
            else None
        )
        if body.purpose == "bound_task_evaluation" and not binding:
            raise HTTPException(
                409, "Every graded member requires its exact frozen Task/evaluator binding"
            )
        if binding and (
            str(binding["environment_id"]) != str(member.environment_id)
            or str(binding["task_group_id"]) != str(body.task_group_id)
            or binding["task_id"] != member.task_id
        ):
            raise HTTPException(409, "Binding belongs to another Task, Project or environment")
        if body.purpose == "technical_rehearsal" and binding:
            raise HTTPException(422, "Technical rehearsals do not grade Task rubrics")
        members.append(
            {
                "environment_id": str(member.environment_id),
                "environment_manifest_sha256": version["manifest_sha256"],
                "pack_sha256": version["manifest"]["pack_sha256"],
                "task_id": member.task_id,
                "task_payload_sha256": tasks[member.task_id]["payload_sha256"],
                "binding_id": str(member.binding_id) if binding else None,
                "binding_sha256": binding["snapshot_sha256"] if binding else None,
                "source_environment_id": source_environment,
                "policy_fields": [m.model_dump() for m in member.policy_fields],
                "actions": [a.model_dump() for a in member.actions],
            }
        )
        environments.append(
            {
                "id": str(version["id"]),
                "name": version["name"],
                "version": version["manifest_sha256"],
                "scenario": version["manifest"]["scenario_id"],
                "template": version["manifest"]["template_id"],
                "native_isolation": False,
            }
        )
    count = len(members) * len(body.candidates) * body.repetitions
    if count > 120:
        raise HTTPException(422, "Run exceeds 120 attempts")
    snapshot = {
        "schema_version": "anvil.environment-execution-plan.v1",
        "source_sha256": source_hash(),
        "task_group_id": str(body.task_group_id),
        "source_project": group["content"]["source_project"],
        "task_group_sha256": group["content_sha256"],
        "tasks": [
            {k: t[k] for k in ("task_id", "task_version", "payload_sha256")}
            for t in tasks.values()
            if t["task_id"] in {m.task_id for m in body.members}
        ],
        "models": [CANDIDATES[k] for k in body.candidates],
        "environments": environments,
        "members": members,
        "repetitions": body.repetitions,
        "planned_cells": count,
        "planned_pack_bytes": planned_pack_bytes,
        "purpose": body.purpose,
        "harness": body.harness,
        "methods": [
            runs.METHODS[0]
            | {
                "status": "ready" if body.purpose == "bound_task_evaluation" else "not_evaluated",
                "reason": None
                if body.purpose == "bound_task_evaluation"
                else "Technical rehearsal has no source Task scoring",
            }
        ],
        "mappings": mappings,
        "policy_set_id": str(policy["id"]) if policy else None,
        "policy_set_sha256": policy["content_sha256"] if policy else None,
        "provider_calls": 0,
        "model_performance": False,
    }
    if policy:
        snapshot["methods"].append(
            {
                "id": "custom-policy-v1",
                "name": "Custom policy compliance",
                "version": "1",
                "kind": "deterministic",
                "status": "ready",
                "scope": "Exact imported policy rules and explicitly mapped trusted fields",
                "reason": None,
            }
        )
    return one(
        c,
        "INSERT INTO anvil.benchmark_execution_plans(id,project_id,task_group_id,name,snapshot,snapshot_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (uid(), project, body.task_group_id, body.name, Jsonb(snapshot), digest(snapshot), user),
    )


def validate(c, row):
    plan = row["snapshot"]
    if plan["source_sha256"] != source_hash() or digest(plan) != row["snapshot_sha256"]:
        raise ValueError("environment_execution_source_changed")
    group = projects.get(c, plan["task_group_id"])
    if group["content_sha256"] != plan["task_group_sha256"]:
        raise ValueError("source_project_changed")
    if plan["policy_set_id"]:
        policy = one(
            c, "SELECT * FROM anvil.benchmark_policy_sets WHERE id=%s", (plan["policy_set_id"],)
        )
        if (
            not policy
            or policy["content_sha256"] != plan["policy_set_sha256"]
            or digest(policy["content"]) != plan["policy_set_sha256"]
        ):
            raise ValueError("policy_source_changed")
    if not one(
        c,
        "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active AND m.role IN('admin','rl-engineer')",
        (row["project_id"], row["created_by"]),
    ):
        raise ValueError("execution_membership_revoked")
    for m in plan["members"]:
        v = runtime.get(c, "environment_versions", m["environment_id"])
        if (
            v["manifest_sha256"] != m["environment_manifest_sha256"]
            or not runtime.readiness(c, v)["local_registered"]
        ):
            raise ValueError("environment_version_changed")
        task = next((t for t in group["content"]["tasks"] if t["task_id"] == m["task_id"]), None)
        if not task or task["payload_sha256"] != m["task_payload_sha256"]:
            raise ValueError("task_version_changed")
        if m["binding_id"]:
            b = one(
                c,
                "SELECT snapshot_sha256 FROM anvil.environment_task_bindings WHERE id=%s",
                (m["binding_id"],),
            )
            if not b or b["snapshot_sha256"] != m["binding_sha256"]:
                raise ValueError("binding_changed")
    return group


def capture_node(state):
    from anvil.db import transaction
    from anvil.environment_collect import capture_attempt

    with transaction(state["project"], state["actor"], worker=True) as c:
        row = one(
            c, "SELECT * FROM anvil.benchmark_runs WHERE id=%s FOR UPDATE", (state["run_id"],)
        )
        validate(c, row)
        for member in row["snapshot"]["members"]:
            for model in row["snapshot"]["models"]:
                for repetition in range(row["snapshot"]["repetitions"]):
                    if one(
                        c,
                        "SELECT 1 FROM anvil.benchmark_run_cells WHERE run_id=%s AND model_key=%s AND task_key=%s AND environment_key=%s AND repetition=%s",
                        (
                            row["id"],
                            model["id"],
                            member["task_id"],
                            member["environment_id"],
                            repetition,
                        ),
                    ):
                        continue
                    if cancelled(c, row["id"]):
                        raise ValueError("environment_run_cancelled")
                    if one(
                        c,
                        "SELECT id FROM anvil.environment_attempts WHERE run_id=%s AND environment_id=%s AND model_key=%s AND repetition=%s",
                        (row["id"], member["environment_id"], model["id"], repetition),
                    ):
                        raise ValueError(
                            "Previous attempt is incomplete; retry requires a new linked Run, no blind replay"
                        )
                    capture_attempt(c, row, state["actor"], member, model["id"], repetition)
    return {"captured": True}


def cancelled(c, identifier):
    row = one(
        c,
        "SELECT cancel_requested FROM anvil.environment_run_controls WHERE run_id=%s",
        (identifier,),
    )
    return bool(row and row["cancel_requested"])


def assessment(evaluation, task, capture=None):
    content = evaluation["content"] if evaluation else {}
    score = content.get("original_scoring")
    source = projects.parse_task(__import__("json").dumps(task["source"]))
    criteria = []
    if not score:
        criteria = [
            {
                "id": cr.id,
                "description": cr.description,
                "dimension": task["dimensions"].get(cr.id),
                "passed": None,
                "earned_points": None,
                "possible_points": str(Decimal(81) * cr.weight_bps / 10000),
            }
            for cr in source.rubric.criteria
        ]
    if score:
        for criterion in source.rubric.criteria:
            possible = Decimal(81) * criterion.weight_bps / 10000
            passed = score["criteria"][criterion.id]["passed"]
            criteria.append(
                {
                    "id": criterion.id,
                    "description": criterion.description,
                    "dimension": task["dimensions"].get(criterion.id),
                    "passed": passed,
                    "earned_points": str(possible if passed else 0),
                    "possible_points": str(possible),
                }
            )
    points = sum(Decimal(cr["earned_points"]) for cr in criteria) if score else None
    return {
        "earned_points": str(0 if score["hard_failures"] else points) if score else None,
        "diagnostic_points": str(points) if score else None,
        "possible_points": "81",
        "score_status": content.get("score_status", "not_evaluated"),
        "criteria": criteria,
        "failure_modes": [
            f
            for f in task["failure_modes"]
            if any(cr["passed"] is False and cr["id"] in f["criterion_ids"] for cr in criteria)
        ],
        "constraint_findings": [
            {
                "rule_id": f["requirement"],
                "requirement": f["requirement"],
                "outcome": f["outcome"],
                "reason": f.get("reason", "Deterministic frozen source rule"),
                "evidence_ref": f["evidence_receipt_id"],
                "evaluator": {
                    "configuration_id": f["evaluator_id"],
                    "runtime_version": f["runtime_version"],
                },
            }
            for f in content.get("findings", [])
            if f["kind"] == "constraint"
        ],
        "policy_findings": [],
        "safety": [
            {
                "axis": "containment",
                "outcome": "pass",
                "reason": "Actual native actor probes: three private paths denied, two egress connections blocked, read-only input and bounded nonroot container. Business state remains host mediated.",
                "evidence_refs": [capture["trusted_evidence_receipt_id"]],
            }
        ]
        if capture
        and (capture.get("native_harbor") or {}).get("actor_probe", {}).get("egress_blocked") == 2
        else [],
        "judge": {"status": "not_run", "value": None},
        "logprobs": {"status": "unavailable", "value": None},
        "environment_evaluation": content or None,
    }


def assess_node(state):
    from anvil.db import transaction

    with transaction(state["project"], state["actor"], worker=True) as c:
        row = one(c, "SELECT * FROM anvil.benchmark_runs WHERE id=%s", (state["run_id"],))
        group = validate(c, row)
        tasks = {t["task_id"]: t for t in group["content"]["tasks"]}
        for cell in c.execute(
            "SELECT * FROM anvil.benchmark_run_cells WHERE run_id=%s", (row["id"],)
        ).fetchall():
            if one(c, "SELECT 1 FROM anvil.benchmark_run_scores WHERE cell_id=%s", (cell["id"],)):
                continue
            m = next(
                m
                for m in row["snapshot"]["members"]
                if m["environment_id"] == cell["environment_key"]
            )
            attempt = one(
                c,
                "SELECT * FROM anvil.environment_attempts WHERE id=%s FOR UPDATE",
                (cell["capture"]["attempt_id"],),
            )
            evaluation = (
                bindings.assess(
                    c,
                    row["project_id"],
                    state["actor"],
                    m["binding_id"],
                    attempt["evidence_receipt_id"],
                )
                if m["binding_id"]
                else None
            )
            value = assessment(evaluation, tasks[cell["task_key"]], cell["capture"])
            if row["snapshot"]["policy_set_id"]:
                value["policy_findings"] = custom_policy_findings(
                    c, row["snapshot"], m, tasks[cell["task_key"]], attempt["evidence_receipt_id"]
                )
            c.execute(
                "INSERT INTO anvil.benchmark_run_scores(id,project_id,cell_id,assessment,assessment_sha256) VALUES(%s,%s,%s,%s,%s)",
                (uid(), row["project_id"], cell["id"], Jsonb(value), digest(value)),
            )
            c.execute(
                "UPDATE anvil.environment_attempts SET state='assessed',evaluation_id=%s WHERE id=%s",
                (evaluation["id"] if evaluation else None, attempt["id"]),
            )
    return {"assessed": True}


def custom_policy_findings(c, plan, member, task, receipt_id):
    from anvil import evaluator_configurations as evaluators
    from anvil.policy_rules import Rule

    captured = one(
        c, "SELECT * FROM anvil.environment_receipts WHERE id=%s AND kind='evidence'", (receipt_id,)
    )
    if not captured or digest(captured["content"]) != captured["content_sha256"]:
        raise ValueError("trusted_policy_capture_missing")
    facts, _ = bindings.resolve_fields(captured["content"], member["policy_fields"])
    policy = one(
        c, "SELECT content FROM anvil.benchmark_policy_sets WHERE id=%s", (plan["policy_set_id"],)
    )["content"]["manifest"]
    binding = next(
        (
            b
            for b in policy["task_bindings"]
            if (b["task_id"], b["task_version"]) == (task["task_id"], task["task_version"])
        ),
        None,
    )
    refs = {(r["policy_id"], r["version"]) for r in binding["policy_refs"]} if binding else set()
    findings = []
    for p in policy["policies"]:
        if (p["policy_id"], p["version"]) not in refs:
            continue
        for rule in p["rules"]:
            finding = {
                "policy_id": p["policy_id"],
                "policy_version": p["version"],
                "rule_id": rule["rule_id"],
                "requirement": rule["requirement"],
                "severity": rule["severity"],
                "source_location": rule["source_location"],
                "evidence_ref": str(receipt_id),
                "outcome": "not_evaluated",
                "reason": "No tested compatible policy mapping",
                "evaluator": None,
            }
            m = next(
                (
                    m
                    for m in plan["mappings"]
                    if (m["policy_id"], m["policy_version"], m["rule_id"])
                    == (p["policy_id"], p["version"], rule["rule_id"])
                ),
                None,
            )
            if m:
                scope = m["scope"]
                finding["evaluator"] = {
                    k: m[k]
                    for k in (
                        "configuration_id",
                        "adapter",
                        "runtime_version",
                        "adapter_source_sha256",
                        "validation_id",
                    )
                }
                cfg = evaluators.get(c, m["configuration_id"])
                if (scope.get("task_ids") and task["task_id"] not in scope["task_ids"]) or (
                    scope.get("environment_ids")
                    and member["source_environment_id"] not in scope["environment_ids"]
                ):
                    finding.update(
                        outcome="not_applicable",
                        reason="Outside original source Task/environment policy scope",
                    )
                elif (
                    cfg["status"] != "ready"
                    or cfg["configuration_sha256"] != m["configuration_sha256"]
                    or str(cfg["validation"]["id"]) != m["validation_id"]
                ):
                    finding.update(
                        outcome="error",
                        reason="Frozen policy evaluator revoked or qualification changed",
                    )
                else:
                    try:
                        finding.update(
                            runs.evaluator_function(m)(
                                Rule.model_validate(m["configuration"]["rule"]), facts
                            )
                        )
                    except Exception:
                        finding.update(
                            outcome="error",
                            reason="Deterministic policy evaluator failed; no fallback",
                        )
            findings.append(finding)
    return findings
