"""One scope projection shared by the interactive dashboard, JSON and actual PDF exports."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException

from anvil import benchmark_project_import as projects
from anvil import benchmark_runs as runs
from anvil.db import Jsonb, audit, digest, uid
from anvil.policy_rules import coverage

AXES = [
    ("correctness", "Correctness"),
    ("evidence", "Evidence completeness"),
    ("constraints", "Constraint adherence"),
    ("policy", "Policy adherence"),
    ("injection", "Injection resistance"),
    ("containment", "Environment containment"),
]


def percent(earned, possible):
    return (
        round(float(Decimal(str(earned)) / Decimal(str(possible)) * 100), 2) if possible else None
    )


def profile(cells):
    axes = []
    for key, label in AXES:
        if key in {"correctness", "evidence", "constraints"}:
            criteria = [
                cr
                for cell in cells
                for cr in cell["assessment"]["criteria"]
                if cr["dimension"] == key
            ]
            earned = sum(Decimal(cr["earned_points"]) for cr in criteria)
            possible = sum(Decimal(cr["possible_points"]) for cr in criteria)
            axes.append(
                {
                    "id": key,
                    "label": label,
                    "value": percent(earned, possible),
                    "numerator": str(earned),
                    "denominator": str(possible),
                    "decided": len(criteria),
                    "planned": len(criteria),
                    "unknown": 0,
                    "basis": "Source Task rubric points in this exact cohort",
                }
            )
        else:
            findings = [
                finding
                for cell in cells
                for finding in (
                    cell["assessment"]["policy_findings"]
                    if key == "policy"
                    else cell["assessment"]["safety"]
                )
                if key == "policy" or finding["axis"] == key
            ]
            stats = coverage([f["outcome"] for f in findings])
            axes.append(
                {
                    "id": key,
                    "label": label,
                    "value": round(stats["percent"], 2) if stats["percent"] is not None else None,
                    "numerator": stats["counts"]["pass"],
                    "denominator": stats["decided"],
                    "decided": stats["decided"],
                    "planned": stats["planned"],
                    "unknown": stats["counts"]["unknown"]
                    + stats["counts"]["not_evaluated"]
                    + stats["counts"]["error"],
                    "counts": stats["counts"],
                    "availability": "not_applicable"
                    if key == "policy" and cells and not findings
                    else "not_evaluated"
                    if not stats["decided"]
                    else "available",
                    "basis": "Pass / (Pass + Fail); Unknown and coverage are separate"
                    if key == "policy"
                    else "Observed response to injected notes; legitimate completion reported separately"
                    if key == "injection"
                    else "Local simulator boundary probes; not native or network isolation",
                }
            )
    return axes


def remediation(tasks, cells, run):
    result = []
    for task in tasks:
        failing = [
            cell
            for cell in cells
            if cell["task_key"] == task["task_id"]
            and (
                cell["assessment"]["failure_modes"]
                or any(f["outcome"] == "fail" for f in cell["assessment"]["policy_findings"])
            )
        ]
        if not failing:
            continue
        criteria = {
            cr["id"]: cr["description"]
            for cell in failing
            for cr in cell["assessment"]["criteria"]
            if not cr["passed"]
        }
        exemplar = next(
            (
                cell
                for cell in cells
                if cell["task_key"] == task["task_id"]
                and Decimal(cell["assessment"]["earned_points"])
                == Decimal(cell["assessment"]["possible_points"])
                and (not run["snapshot"]["policy_set_id"] or cell["assessment"]["policy_findings"])
                and all(
                    f["outcome"] in {"pass", "not_applicable"}
                    for f in cell["assessment"]["policy_findings"]
                )
            ),
            None,
        )
        result.append(
            {
                "task_id": task["task_id"],
                "task_version": task["task_version"],
                "title": task["title"],
                "failed_cells": len(failing),
                "failure_modes": sorted(
                    {f["title"] for cell in failing for f in cell["assessment"]["failure_modes"]}
                ),
                "recommendation": "Proposed remediation package: license this versioned Task, its declared environments and the failure-matched regression dataset to address the observed gaps. Request the applicable licensing and training-rights terms; no purchase or entitlement is assumed.",
                "environment_ids": sorted({cell["environment_key"] for cell in failing}),
                "sample": {
                    "sample_type": "unverified_authoring_draft",
                    "input": task["actor"],
                    "expected_behavior": list(criteria.values()) or [task["actor"]["objective"]],
                    "source_run_id": str(run["id"]),
                    "evidence_ids": [str(cell["id"]) for cell in failing],
                    "human_verified": False,
                    "example_response": {
                        "status": "observed_software_example",
                        "evidence_id": str(exemplar["id"]),
                        "environment_id": exemplar["environment_key"],
                        "output": exemplar["capture"]["output"],
                        "human_verified": False,
                        "hidden_reference_used": False,
                    }
                    if exemplar
                    else {
                        "status": "needs_authoring",
                        "output": None,
                        "reason": "No qualifying observed example in the selected cohort; no hidden reference or outside-scope model is substituted",
                    },
                },
                "licensing": "Task/environment terms and training rights have not been supplied; no purchase or entitlement is created",
                "improvement": "Evaluate the remediated agent on held-out matched Tasks and environments to measure improvement",
            }
        )
    return result


def view(
    c,
    identifier,
    *,
    models=None,
    environments=None,
    task="all",
    period="all",
    method="all",
    cell_id=None,
):
    row = runs.get(c, identifier)
    group = projects.get(c, row["snapshot"]["task_group_id"])
    snapshot = row["snapshot"]
    model_ids, env_ids, task_ids = (
        {m["id"] for m in snapshot["models"]},
        {e["id"] for e in snapshot["environments"]},
        {t["task_id"] for t in snapshot["tasks"]},
    )
    models, environments = models or [], environments or []
    if (
        set(models) - model_ids
        or set(environments) - env_ids
        or task != "all"
        and task not in task_ids
        or period not in {"all", "7d", "30d"}
    ):
        raise HTTPException(422, "Filter does not belong to this frozen Run")
    if method != "all" and method not in {
        m.get("configuration_id", m["id"]) for m in snapshot["methods"]
    }:
        raise HTTPException(422, "Evaluation method is not selected by this Run")
    cells = c.execute(
        "SELECT b.*,s.assessment,s.assessment_sha256 FROM anvil.benchmark_run_cells b JOIN anvil.benchmark_run_scores s ON s.cell_id=b.id WHERE b.run_id=%s ORDER BY task_key,model_key,environment_key,repetition,b.id",
        (identifier,),
    ).fetchall()
    cells = [
        cell
        for cell in cells
        if (not models or cell["model_key"] in models)
        and (not environments or cell["environment_key"] in environments)
        and (task == "all" or cell["task_key"] == task)
    ]
    recorded = row["executed_at"] or row["created_at"]
    if period != "all" and recorded < datetime.now(timezone.utc) - timedelta(days=int(period[:-1])):
        cells = []
    selected = next(
        (cell for cell in cells if str(cell["id"]) == str(cell_id)), cells[0] if cells else None
    )
    tasks = [
        t
        for t in group["content"]["tasks"]
        if t["task_id"] in task_ids and (task == "all" or task == t["task_id"])
    ]
    series = [
        {
            "model_key": m["id"],
            "name": m["name"],
            "axes": profile([cell for cell in cells if cell["model_key"] == m["id"]]),
        }
        for m in snapshot["models"]
        if not models or m["id"] in models
    ]
    if snapshot["policy_set_id"]:
        for model_series in series:
            axis = model_series["axes"][3]
            if axis.get("availability") == "not_applicable":
                axis["availability"] = "not_evaluated"
                axis["basis"] = (
                    "Policy source attached, but no executable rule findings are defined in this cohort"
                )
    findings = [
        {
            **finding,
            "cell_id": str(cell["id"]),
            "task_id": cell["task_key"],
            "model_key": cell["model_key"],
            "environment_key": cell["environment_key"],
        }
        for cell in cells
        for finding in cell["assessment"]["policy_findings"]
    ]
    failed = [
        cell
        for cell in cells
        if any(not cr["passed"] for cr in cell["assessment"]["criteria"])
        or any(f["outcome"] == "fail" for f in cell["assessment"]["policy_findings"])
    ]
    method_rows = []
    for selected_method in snapshot["methods"]:
        status = (
            "completed"
            if row["state"] == "completed" and selected_method["status"] == "ready"
            else selected_method["status"]
            if selected_method["status"] != "ready"
            else "not_run"
        )
        if selected_method["id"] == "humaneval-plus":
            status = "not_applicable"
        if selected_method["id"] == "custom-policy-v1" and row["state"] == "completed":
            policy_coverage = coverage([f["outcome"] for f in findings])
            status = (
                "not_evaluated"
                if not policy_coverage["decided"]
                else "completed_with_gaps"
                if any(policy_coverage["counts"][k] for k in ("unknown", "error", "not_evaluated"))
                else "completed"
            )
        method_rows.append(selected_method | {"execution_status": status})
    captured_evaluators = []
    for mapping in snapshot["mappings"]:
        checks = [
            f
            for f in findings
            if f.get("evaluator", {})
            and f["evaluator"]["configuration_id"] == mapping["configuration_id"]
        ]
        captured_evaluators.append(
            {
                "id": mapping["configuration_id"],
                "name": mapping["adapter"],
                "version": mapping["runtime_version"],
                "rule_id": mapping["rule_id"],
                "kind": "deterministic custom policy",
                "coverage": coverage([f["outcome"] for f in checks]),
                "validation_id": mapping["validation_id"],
                "source_sha256": mapping["adapter_source_sha256"],
            }
        )
    public = projects.public_group(group)
    content = {
        "schema_version": "anvil.benchmark-dashboard.v2",
        "run": row,
        "task_group": public,
        "context": {
            "models": models,
            "environments": environments,
            "task": task,
            "period": period,
            "method": method,
            "cell_id": str(selected["id"]) if selected else None,
        },
        "summary": runs.result_summary(cells)
        if cells
        else {
            "models": [],
            "ranking": {
                "observed_win_rate": {"rows": [], "status": "insufficient_data"},
                "bradley_terry": {
                    "rows": [],
                    "status": "insufficient_data",
                    "reason": "No matched observations in selected scope",
                },
            },
        },
        "cells": [{k: value for k, value in cell.items() if k != "capture"} for cell in cells],
        "selected_cell": selected,
        "series": series,
        "methods": method_rows,
        "evaluators": captured_evaluators,
        "failures": {
            "cells": len(failed),
            "total_cells": len(cells),
            "percent": percent(len(failed), len(cells)),
            "policy_findings": findings,
            "by_task": [
                {
                    "task_id": t["task_id"],
                    "name": t["title"],
                    "failed": sum(cell["task_key"] == t["task_id"] for cell in failed),
                    "total": sum(cell["task_key"] == t["task_id"] for cell in cells),
                }
                for t in tasks
            ],
        },
        "remediation": remediation(tasks, cells, row),
        "limitations": [
            "Fictional software agents; no vendor model inference or model-performance ranking",
            "Business environments and boundary effects are local simulations, not Harbor, OS or real-network isolation",
            "Judge scores are Not run and token likelihoods are Unavailable",
            "Missing checks remain gaps; no combined quality and safety score",
            "Source reviews and real data/model qualification are not supplied by an Admin report exemption",
        ],
    }
    # Stable exact-scope hash: timestamps and serialized UUIDs are normalized through encoder.
    from fastapi.encoders import jsonable_encoder

    content["view_sha256"] = digest(jsonable_encoder(content))
    return content


def save_pack(c, project, user, identifier, scope):
    result = view(c, identifier, **scope)
    if result["run"]["state"] != "completed":
        raise HTTPException(409, "A completed Run is required")
    content = {
        "schema_version": "anvil.remediation-pack.v1",
        "run_id": str(identifier),
        "result_sha256": result["run"]["result_sha256"],
        "view_sha256": result["view_sha256"],
        "scope": result["context"],
        "source_project": result["task_group"]["source_project_id"],
        "source_version": result["task_group"]["source_version"],
        "samples": result["remediation"],
        "human_verified": False,
        "licensing_purchase": False,
        "provider_calls": 0,
    }
    identifier_pack = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_remediation_packs(id,project_id,run_id,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
        (identifier_pack, project, identifier, Jsonb(content), digest(content), user),
    )
    audit(
        c,
        project,
        user,
        "benchmark.remediation_pack_saved",
        identifier_pack,
        {"result_sha256": content["result_sha256"], "view_sha256": content["view_sha256"]},
    )
    return {"id": identifier_pack, "content": content, "content_sha256": digest(content)}
