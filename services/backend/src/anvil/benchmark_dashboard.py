"""Project-scoped immutable observations for the four connected benchmark views."""

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import median
from uuid import UUID

from fastapi import HTTPException

from anvil import benchmark_dashboard_traces as historical
from anvil import benchmark_execution as execution
from anvil import benchmark_pipeline as pipeline
from anvil import benchmark_results as results
from anvil.benchmark_protocol import Protocol
from anvil.benchmark_rankings import paired_rankings
from anvil.db import digest, one


def unavailable(reason, status="not_run"):
    return {"status": status, "value": None, "reason": reason}


JUDGE_REASON = "No separately approved judge observations are stored; paid calls remain off"
LOGPROB_REASON = (
    "No supported token-likelihood telemetry is stored; likelihood is not factual accuracy"
)


def query(request):
    p = request.query_params
    result = {
        "model": sorted(set(p.getlist("model"))),
        "task": p.get("task", "all"),
        "period": p.get("period", "all"),
        "environment": p.get("environment", "all"),
        **{
            key: p.get(key) or None
            for key in ("run_id", "score_revision_id", "trace_id", "cluster")
        },
    }
    if result["period"] not in {"all", "7d", "30d"} or len(result["model"]) > 12:
        raise HTTPException(422, "Unsupported dashboard period or model selection")
    for key in ("run_id", "score_revision_id", "trace_id"):
        if result[key]:
            try:
                result[key] = str(UUID(result[key]))
            except ValueError:
                raise HTTPException(422, "Invalid dashboard record reference") from None
    if result["score_revision_id"] and not result["run_id"]:
        raise HTTPException(422, "A score revision requires its exact run reference")
    if result["task"] != "all" and not re.fullmatch(
        r"fictional-points:1\.0\.0:FX-[0-9]{3}", result["task"]
    ):
        try:
            identifier = (
                result["task"][6:] if result["task"].startswith("suite:") else result["task"]
            )
            normalized = str(UUID(identifier))
            result["task"] = (
                "suite:" + normalized if result["task"].startswith("suite:") else normalized
            )
        except ValueError:
            raise HTTPException(422, "Invalid task or suite reference") from None
    if any(
        len(value) > 256
        for value in result["model"]
        + [result["task"], result["environment"], result["cluster"] or ""]
    ):
        raise HTTPException(422, "Dashboard context exceeds bounds")
    return result


def model_key(slot):
    return digest(
        {
            "binding": slot.binding.model_dump(mode="json"),
            "configuration": slot.configuration_sha256,
        }
    )[:24]


def score(earned, possible):
    earned, possible = Decimal(str(earned)), Decimal(str(possible))
    if (
        not earned.is_finite()
        or not possible.is_finite()
        or not 0 <= earned <= possible
        or possible <= 0
    ):
        raise ValueError("Invalid stored score observation")
    return {
        "earned_points": format(earned, "f"),
        "possible_points": format(possible, "f"),
        "percent": format(earned / possible * 100, ".4f"),
    }


def selected_score(model, task, *, primary, allowed=None):
    included = model["diagnostic"]["included"]
    if allowed is not None:
        included = [x for x in included if (x["task_revision_id"], x["repetition"]) in allowed]
    if task == "all" or task.startswith("suite:"):
        if primary:
            return model["primary"] if len(included) == 6 else None
        repetitions = [[x for x in included if x["repetition"] == rep] for rep in range(2)]
        complete = [items for items in repetitions if len(items) == 3]
        if not complete:
            return None
        return score(
            sum(sum(Decimal(x["earned_points"]) for x in items) for items in complete)
            / len(complete),
            81,
        )
    included = [x for x in included if x["task_revision_id"] == task]
    if not included or (primary and (model["primary"] is None or len(included) != 2)):
        return None
    if len({x["repetition"] for x in included}) != len(included):
        raise ValueError("Duplicate original task repetition")
    possible = {x["possible_points"] for x in included}
    if len(possible) != 1:
        raise ValueError("Incompatible task denominators")
    return score(sum(Decimal(x["earned_points"]) for x in included) / len(included), possible.pop())


def mean_score(values):
    if not values or len({x["possible_points"] for x in values}) != 1:
        return None
    return score(
        sum(Decimal(x["earned_points"]) for x in values) / len(values), values[0]["possible_points"]
    )


def resolve_anchor(c, trace_id, project=None, user=None):
    row = one(c, "SELECT id,run_id FROM anvil.benchmark_cells WHERE id=%s", (trace_id,))
    if row:
        execution.export_rights(c, row["run_id"])
        return {
            "kind": "comparison_cell",
            "run_id": str(row["run_id"]),
            "cell_id": str(row["id"]),
            "source_build_id": None,
            "current_authority": True,
        }
    row = historical.metadata(c, trace_id)
    return {
        "kind": "historical_control",
        "run_id": None,
        "cell_id": None,
        "source_build_id": None,
        "current_authority": False,
        "artifact_id": str(row["artifact_id"]),
    }


def matches_case_context(c, content, context, *, created_at=None):
    """Relate curation to its actual source; never attribute an unbound case to a model."""
    if created_at is not None and context["period"] != "all":
        since = datetime.now(timezone.utc) - timedelta(days=int(context["period"][:-1]))
        if created_at < since:
            return False
    anchor = content.get("source_anchor")
    historical_id = content.get("source_trace_id")
    trace_id = str(historical_id) if historical_id else str(anchor["cell_id"]) if anchor else None
    if context["trace_id"] and context["trace_id"] != trace_id:
        return False
    if context["run_id"] and (not anchor or str(anchor["run_id"]) != context["run_id"]):
        return False
    if context["cluster"]:
        if "_cluster_trace_ids" not in context:
            cohort = collect(
                c,
                {k: v for k, v in context.items() if not k.startswith("_")},
                include_curation=False,
            )
            context["_cluster_trace_ids"] = {item["id"] for item in cohort["traces"]}
        if trace_id not in context["_cluster_trace_ids"]:
            return False
    task_key = None
    model = None
    environment = "unrecorded"
    suite = None
    if anchor:
        row = one(
            c,
            "SELECT cell.task_revision_id,cell.slot,cell.benchmark_revision_id,p.content "
            "FROM anvil.benchmark_cells cell JOIN anvil.benchmark_comparisons b ON b.project_id=cell.project_id AND b.run_id=cell.run_id "
            "JOIN anvil.revisions p ON p.project_id=b.project_id AND p.id=b.protocol_revision_id "
            "WHERE cell.id=%s AND cell.run_id=%s",
            (anchor["cell_id"], anchor["run_id"]),
        )
        if row is None:
            return False
        frozen = Protocol.model_validate(row["content"])
        model = model_key(frozen.slots[row["slot"]])
        task_key = str(row["task_revision_id"])
        suite = "suite:" + str(row["benchmark_revision_id"])
        environment = (
            "offline_contract"
            if all(x.transport == "offline_contract" for x in frozen.slots)
            else "unrecorded"
        )
    elif historical_id:
        try:
            trace = historical.summary(historical.metadata(c, historical_id))
        except HTTPException:
            return False
        task_key, environment = trace["task_key"], trace["environment"]
    if context["model"] and model not in context["model"]:
        return False
    if context["environment"] not in {"all", environment}:
        return False
    task = context["task"]
    if task == "all" or task in {task_key, suite}:
        return True
    if task.startswith("suite:"):
        if content.get("source_build_id"):
            revision = one(c, "SELECT content FROM anvil.revisions WHERE id=%s", (task[6:],))
            return bool(
                revision and revision["content"].get("build_id") == str(content["source_build_id"])
            )
        return False
    fictional = content.get("fictional_task_id")
    if task.startswith("fictional-points:1.0.0:"):
        return task.rsplit(":", 1)[-1] == fictional
    try:
        identifier = str(UUID(task))
    except ValueError:
        return False
    revision = one(c, "SELECT content FROM anvil.revisions WHERE id=%s", (identifier,))
    return bool(revision and revision["content"].get("task_id") == fictional)


def collect(c, context, *, now=None, include_curation=True):
    now = now or datetime.now(timezone.utc)
    since = (
        now - timedelta(days=int(context["period"][:-1])) if context["period"] != "all" else None
    )
    runs = c.execute(
        "SELECT b.*,r.state,pr.content protocol FROM anvil.benchmark_comparisons b "
        "JOIN anvil.runs r ON r.project_id=b.project_id AND r.id=b.run_id "
        "JOIN anvil.revisions pr ON pr.project_id=b.project_id AND pr.id=b.protocol_revision_id "
        "WHERE (%s::uuid IS NULL OR b.run_id=%s::uuid) ORDER BY b.created_at,b.run_id LIMIT 501",
        (context["run_id"], context["run_id"]),
    ).fetchall()
    if len(runs) > 500:
        raise HTTPException(409, "Cohort exceeds bounded read size; narrow the run selection")
    if context["run_id"] and not runs:
        raise HTTPException(404, "Comparison not found in this project")
    traces, observations, model_rows = [], [], defaultdict(list)
    policy_cache = {}
    options = {"models": {}, "tasks": {}, "environments": {}}
    eligible_suites = set()
    for run in runs:
        protocol = Protocol.model_validate(run["protocol"])
        suite = "suite:" + str(run["benchmark_revision_id"])
        options["tasks"][suite] = "Suite " + str(run["benchmark_revision_id"])[:8]
        environment = (
            "offline_contract"
            if all(x.transport == "offline_contract" for x in protocol.slots)
            else "unrecorded"
        )
        options["environments"][environment] = environment.replace("_", " ")
        if context["environment"] not in {"all", environment}:
            continue
        if context["task"].startswith("suite:") and context["task"] != suite:
            continue
        try:
            stored = results.latest(c, run["run_id"], context["score_revision_id"])
        except HTTPException as failure:
            if failure.status_code == 409:
                stored = None
            else:
                raise
        if stored and (
            stored["projection"]["protocol_sha256"] != run["subject_sha256"]
            or stored["projection"]["origin"] != protocol.origin
        ):
            raise HTTPException(409, "Stored dashboard projection binding changed")
        rights = True
        try:
            execution.export_rights(c, run["run_id"])
            bound = execution.version(c, run["benchmark_revision_id"])
            build_id = str(bound["build_id"])
            if build_id not in policy_cache:
                scope = c.execute(
                    "SELECT current_setting('anvil.project') project, current_setting('anvil.user') actor"
                ).fetchone()
                _, blockers = pipeline.policy_status(scope["project"], scope["actor"], build_id)
                policy_cache[build_id] = not blockers
            rights = policy_cache[build_id]
        except HTTPException:
            rights = False
        stale = one(
            c,
            "SELECT 1 FROM anvil.benchmark_version_tasks t JOIN anvil.benchmark_qualification_events e "
            "ON e.project_id=t.project_id AND e.qualification_id=t.qualification_id WHERE t.benchmark_revision_id=%s LIMIT 1",
            (run["benchmark_revision_id"],),
        )
        reviewed = bool(
            stored
            and stored["review_state"]
            in {
                "approved",
                "adjudicated",
                "admin_run_exempt",
                "admin_approved",
                "policy_no_review",
                "reviewed",
            }
            and rights
            and not stale
        )
        state = stored["review_state"] if stored else "no_score_revision"
        if not rights or stale:
            state = "current_source_review_unavailable"
        cells = c.execute(
            "SELECT cell.*,coalesce(e.state,'queued') execution_state,coalesce(e.validity,'pending') validity,"
            "coalesce(e.created_at,cell.created_at) observed_at,rt.duration_ms,rt.output_artifact_id "
            "FROM anvil.benchmark_cells cell LEFT JOIN anvil.benchmark_cell_attempts a "
            "ON a.project_id=cell.project_id AND a.cell_id=cell.id AND a.attempt_no=1 "
            "LEFT JOIN anvil.benchmark_offline_runtime rt ON rt.project_id=a.project_id AND rt.attempt_id=a.id "
            "LEFT JOIN LATERAL (SELECT state,validity,created_at FROM anvil.benchmark_attempt_events "
            "WHERE project_id=a.project_id AND attempt_id=a.id ORDER BY event_seq DESC LIMIT 1) e ON true "
            "WHERE cell.run_id=%s ORDER BY cell.task_revision_id,cell.slot,cell.repetition",
            (run["run_id"],),
        ).fetchall()
        task_labels = {}
        for task in protocol.tasks:
            item = one(
                c, "SELECT content FROM anvil.revisions WHERE id=%s", (task.task_revision_id,)
            )
            task_labels[str(task.task_revision_id)] = (
                (
                    item["content"].get("task_id")
                    or item["content"].get("name")
                    or str(task.task_revision_id)[:8]
                )
                if item
                else str(task.task_revision_id)[:8]
            )
            options["tasks"][str(task.task_revision_id)] = task_labels[str(task.task_revision_id)]
        for number, slot in enumerate(protocol.slots):
            key = model_key(slot)
            ranking_eligible = (
                protocol.origin == "authorized_benchmark" and slot.transport == "live"
            )
            options["models"][key] = {
                "key": key,
                "label": slot.binding.model_id,
                "provider": slot.binding.provider,
            }
            if context["model"] and key not in context["model"]:
                continue
            model = (
                next((x for x in stored["projection"]["models"] if x["slot"] == number), None)
                if stored
                else None
            )
            selected_cells = [
                x
                for x in cells
                if x["slot"] == number
                and (
                    context["task"] == "all"
                    or context["task"] == suite
                    or str(x["task_revision_id"]) == context["task"]
                )
            ]
            selected_cells = [
                x for x in selected_cells if since is None or x["observed_at"] >= since
            ]
            if not selected_cells:
                continue
            allowed = {(str(x["task_revision_id"]), x["repetition"]) for x in selected_cells}
            primary = (
                selected_score(model, context["task"], primary=True, allowed=allowed)
                if model and reviewed
                else None
            )
            diagnostic = (
                selected_score(model, context["task"], primary=False, allowed=allowed)
                if model and rights and not stale
                else None
            )
            # A partly selected time window must not carry a full-run primary into the cohort.
            expected_cells = 2 if context["task"] not in {"all", suite} else 6
            if len(selected_cells) != expected_cells:
                primary = None
            if primary and ranking_eligible:
                eligible_suites.add(suite)
            included = model["diagnostic"]["included"] if model and rights and not stale else []
            for cell in selected_cells:
                observed = next(
                    (
                        x
                        for x in included
                        if x["task_revision_id"] == str(cell["task_revision_id"])
                        and x["repetition"] == cell["repetition"]
                    ),
                    None,
                )
                points = (
                    score(observed["earned_points"], observed["possible_points"])
                    if observed
                    else None
                )
                threshold = (
                    next(
                        (
                            Decimal(x.pass_threshold_percent)
                            for x in protocol.review_policy.tasks
                            if str(x.task_revision_id) == str(cell["task_revision_id"])
                        ),
                        None,
                    )
                    if protocol.review_policy
                    else None
                )
                below_threshold = bool(
                    points is not None
                    and threshold is not None
                    and Decimal(points["percent"]) < threshold
                )
                failed = cell["execution_state"] == "model_failed" or below_threshold
                infrastructure = cell["execution_state"] in {
                    "operational_failed",
                    "dispatch_unknown",
                }
                tags = (
                    ["operational_failure"]
                    if infrastructure
                    else [
                        "below_declared_threshold" if below_threshold else "task_criterion_failure"
                    ]
                    if failed
                    else []
                )
                trace = {
                    "id": str(cell["id"]),
                    "kind": "comparison_cell",
                    "label": task_labels[str(cell["task_revision_id"])]
                    + f" · repetition {cell['repetition'] + 1}",
                    "task_key": str(cell["task_revision_id"]),
                    "task_label": task_labels[str(cell["task_revision_id"])],
                    "model_key": key,
                    "model_label": slot.binding.model_id
                    + (
                        " · offline contract control"
                        if slot.transport == "offline_contract"
                        else ""
                    ),
                    "run_id": str(run["run_id"]),
                    "state": cell["execution_state"],
                    "validity": cell["validity"],
                    "origin": protocol.origin,
                    "environment": environment,
                    "recorded_at": cell["observed_at"].isoformat(),
                    "duration_ms": cell["duration_ms"],
                    "points": points,
                    "official": bool(primary and observed and ranking_eligible),
                    "review_state": state,
                    "failure_tags": tags,
                    "severity": "high" if failed else "medium" if infrastructure else "none",
                    "severity_basis": "derived_execution_state_and_frozen_task_threshold_v1; not calibrated risk",
                    "evidence_available": bool(
                        cell["output_artifact_id"]
                        and rights
                        and not stale
                        and one(
                            c,
                            "SELECT 1 FROM anvil.artifacts WHERE id=%s",
                            (cell["output_artifact_id"],),
                        )
                    ),
                    "source_sha256": observed["evidence_sha256"] if observed else None,
                }
                traces.append(trace)
                if trace["official"]:
                    observations.append(
                        {
                            "match_key": f"{run['run_id']}:{cell['task_revision_id']}:{cell['repetition']}",
                            "model_key": key,
                            "percent": points["percent"],
                        }
                    )
            model_rows[(key, suite)].append(
                {
                    "primary": primary,
                    "diagnostic": diagnostic,
                    "state": state,
                    "model": model if rights and not stale else None,
                    "ranking_eligible": ranking_eligible,
                    "cells": selected_cells,
                    "slot": slot,
                }
            )
    if not context["run_id"] and not context["model"] and not context["score_revision_id"]:
        rows = c.execute(
            "SELECT * FROM anvil.benchmark_trace_audit WHERE (%s::timestamptz IS NULL OR recorded_at>=%s) ORDER BY recorded_at,id LIMIT 1001",
            (since, since),
        ).fetchall()
        if len(rows) > 1000:
            raise HTTPException(
                409, "Historical trace cohort exceeds bounded read size; narrow period"
            )
        for row in rows:
            item = historical.summary(row)
            options["tasks"][item["task_key"]] = item["task_label"]
            options["environments"][item["environment"]] = item["environment"].replace("_", " ")
            if context["task"] not in {"all", item["task_key"]} or context["environment"] not in {
                "all",
                item["environment"],
            }:
                continue
            traces.append(item)
    models = []
    for (key, suite), values in sorted(model_rows.items()):
        slot = values[0]["slot"]
        primary_values = [x["primary"] for x in values if x["primary"]]
        diagnostic_values = [x["diagnostic"] for x in values if x["diagnostic"]]
        durations = [
            cell["duration_ms"]
            for x in values
            for cell in x["cells"]
            if cell["duration_ms"] is not None
        ]
        costs = [
            x["model"]["cost"]["combined_micro_usd"]
            if x["model"] and len(x["cells"]) == 6
            else None
            for x in values
        ]
        models.append(
            {
                "key": key + ":" + suite,
                "model_key": key,
                "provider": slot.binding.provider,
                "model_id": slot.binding.model_id,
                "suite_key": suite,
                "primary": mean_score(primary_values),
                "diagnostic": mean_score(diagnostic_values),
                "review_state": (
                    next(iter({x["state"] for x in values}))
                    if len({x["state"] for x in values}) == 1
                    else "mixed_authorization"
                )
                if len(primary_values) == len(values)
                else "pending_or_unavailable",
                "authorization_basis": sorted({x["state"] for x in values}),
                "reviewer_verified": bool(primary_values)
                and all(x["state"] in {"approved", "adjudicated", "reviewed"} for x in values),
                "run_count": len(values),
                "authorized_run_count": len(primary_values),
                "reviewed_run_count": sum(
                    bool(x["primary"]) and x["state"] in {"approved", "adjudicated", "reviewed"}
                    for x in values
                ),
                "ranking_eligible": all(x["ranking_eligible"] for x in values),
                "measurement_notice": "Offline contract scores prove software behavior, not model performance"
                if not all(x["ranking_eligible"] for x in values)
                else "Authorized live model observations; current review gates still apply",
                "scored_cells": sum(
                    sum(
                        (a["task_revision_id"], a["repetition"])
                        in {
                            (str(cell["task_revision_id"]), cell["repetition"])
                            for cell in x["cells"]
                        }
                        for a in x["model"]["diagnostic"]["included"]
                    )
                    if x["model"]
                    else 0
                    for x in values
                ),
                "planned_cells": sum(len(x["cells"]) for x in values),
                "duration_ms": median(durations) if durations else None,
                "cost_micro_usd": sum(costs) if all(x is not None for x in costs) else None,
                "judge": unavailable(JUDGE_REASON),
                "logprobs": unavailable(LOGPROB_REASON, "unavailable"),
            }
        )
    ranking = paired_rankings(observations)
    if len(eligible_suites) > 1:
        ranking = paired_rankings([])
        for value in ranking.values():
            value["status"] = "mixed_suites_select_one"
    official = [x for x in models if x["primary"] and x["ranking_eligible"]]
    leader = (
        max(official, key=lambda x: Decimal(x["primary"]["percent"]))
        if official and len(eligible_suites) == 1
        else None
    )
    model_traces = [
        x
        for x in traces
        if x["kind"] == "comparison_cell"
        and x["environment"] != "offline_contract"
        and x["origin"] == "authorized_benchmark"
    ]
    eligible = [
        x
        for x in model_traces
        if x["validity"] == "valid" and x["state"] in {"completed", "model_failed"}
    ]
    eligible = [x for x in eligible if x["points"] is not None]
    failed = [
        x
        for x in eligible
        if any(
            tag in x["failure_tags"]
            for tag in ("task_criterion_failure", "below_declared_threshold")
        )
    ]
    categories = Counter(tag for item in model_traces for tag in item["failure_tags"])
    heat = Counter((x["model_key"], x["task_key"]) for x in model_traces if x["failure_tags"])
    if context["cluster"]:
        visible_traces = [x for x in traces if context["cluster"] in x["failure_tags"]]
    else:
        visible_traces = traces
    if len(traces) > 2000:
        raise HTTPException(409, "Trace cohort exceeds bounded projection; narrow the filters")
    data = {
        "schema_version": "anvil-dashboard-v1",
        "context": {k: v for k, v in context.items() if not k.startswith("_")},
        "options": {
            "models": list(options["models"].values()),
            "tasks": [
                {"key": key, "label": label} for key, label in sorted(options["tasks"].items())
            ],
            "environments": [
                {"key": key, "label": label}
                for key, label in sorted(options["environments"].items())
            ],
        },
        "origin_notice": "Fictional and offline control observations are not live model performance. Only reviewed, current eligible comparison observations can rank.",
        "limitations": [
            "Judge, retrieval relevance and semantic drift measurements require separately supported observations.",
            "No hidden chain-of-thought is captured or reconstructed.",
            "Historical control points are software conformance only and excluded from all model rankings.",
            "No active endpoint count is inferred from configured or previously observed model IDs.",
            "Cluster focus narrows trace inspection and linked curation; overview and failure-rate denominators retain the selected model/task/time/environment cohort.",
        ],
        "overview": {
            "leader": {
                "model_key": leader["model_key"],
                "model_id": leader["model_id"],
                "percent": leader["primary"]["percent"],
            }
            if leader
            else None,
            "average_score_percent": format(
                sum(Decimal(x["primary"]["percent"]) for x in official) / len(official), ".4f"
            )
            if official and len(eligible_suites) == 1
            else None,
            "total_traces": len(traces),
            "model_trace_count": len(model_traces),
            "control_trace_count": len(traces) - len(model_traces),
            "ranked_models": len({x["model_key"] for x in official}),
            "models": models,
            "ranking": ranking,
        },
        "traces": sorted(visible_traces, key=lambda x: (x["recorded_at"], x["id"]), reverse=True),
        "failures": {
            "classification_basis": "Declared terminal states and frozen task thresholds only; no inferred hallucination or root cause",
            "rate_basis": "diagnostic valid captured model cells with available points; controls and infrastructure excluded",
            "eligible_traces": len(eligible),
            "failed_traces": len(failed),
            "error_rate_percent": format(Decimal(len(failed)) / len(eligible) * 100, ".4f")
            if eligible
            else None,
            "control_traces": len(traces) - len(model_traces),
            "infrastructure_events": sum(
                x["state"] in {"operational_failed", "dispatch_unknown"} for x in traces
            ),
            "categories": [
                {
                    "key": key,
                    "label": key.replace("_", " "),
                    "count": value,
                    "severity": "medium" if key == "operational_failure" else "high",
                }
                for key, value in sorted(categories.items())
            ],
            "heatmap": [
                {"model_key": key[0], "task_key": key[1], "count": value, "severity": "high"}
                for key, value in sorted(heat.items())
            ],
            "traces": [x for x in visible_traces if x["failure_tags"]],
        },
        "availability": {
            "judge": unavailable(JUDGE_REASON),
            "logprobs": unavailable(LOGPROB_REASON, "unavailable"),
            "retrieval_noise": unavailable(
                "No judged retrieval relevance observations are stored", "unavailable"
            ),
            "multi_step_drift": unavailable(
                "No reviewed constraint-drift labels are stored", "unavailable"
            ),
        },
        "report": {"path": "/dashboard/report", "raw_prompts_included": False},
    }
    from . import benchmark_golden

    if include_curation:
        scope = c.execute(
            "SELECT current_setting('anvil.project') project, current_setting('anvil.user') actor"
        ).fetchone()
        data["curation"] = benchmark_golden.dashboard_summary(
            c, scope["project"], scope["actor"], dict(context)
        )
    data["snapshot_sha256"] = digest(data)
    data["generated_at"] = now.isoformat()
    return data
