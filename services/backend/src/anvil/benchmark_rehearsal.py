"""Bounded public-input software execution; no model, native or approval authority."""

import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from time import perf_counter_ns

from fastapi import HTTPException
from pydantic import Field

from anvil import benchmark_report_policy as report_policy
from anvil.benchmark_rankings import paired_rankings
from anvil.config import ROOT
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.schemas import Strict

PROFILES = (
    {
        "id": "square-all-v1",
        "label": "Square every public integer",
        "version": "1",
        "algorithm": "n*n",
    },
    {
        "id": "square-first-six-v1",
        "label": "Square first six items; identity remainder",
        "version": "1",
        "algorithm": "n*n if item_index<6 else n",
    },
    {
        "id": "square-even-v1",
        "label": "Square even integers only",
        "version": "1",
        "algorithm": "n*n if n%2==0 else n",
    },
)
TASKS = (("FX-001", 24), ("FX-002", 6), ("FX-003", 51))
PAID_FLAGS = (
    "ANVIL_LIVE_PROVIDERS_ENABLED",
    "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED",
    "ANVIL_VERTEX_ENABLED",
    "ANVIL_REAL_EMAIL_ENABLED",
)


class Create(Strict):
    name: str = Field(min_length=1, max_length=160)


class Execute(Strict):
    expected_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def enabled():
    if (
        os.environ.get("ANVIL_ENV") != "local"
        or os.environ.get("ANVIL_BENCHMARK_REHEARSAL_ENABLED") != "true"
        or os.environ.get("ANVIL_LOCAL_FIXTURE_ENABLED") != "true"
    ):
        raise HTTPException(503, "Local fictional software rehearsal is disabled")
    if any(os.environ.get(flag, "false") != "false" for flag in PAID_FLAGS):
        raise HTTPException(409, "All paid/provider/email feature flags must be false")


def _public_input(task_id):
    # Fixed allowlist only. Never traverse eval_pack or consume expected-answer references.
    if task_id not in dict(TASKS):
        raise ValueError("Unknown public task")
    path = (
        ROOT / "fixtures/benchmark-bundle/fictional-points-v1/runtime_pack" / task_id / "items.json"
    )
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise ValueError("Invalid bounded public input")
    raw = path.read_bytes()
    items = json.loads(raw)["items"]
    if len(items) != dict(TASKS)[task_id] or any(
        set(item) != {"id", "n"}
        or type(item["n"]) is not int
        or not 1 <= item["n"] <= 100
        or item["id"] != f"item-{index:03d}"
        for index, item in enumerate(items, 1)
    ):
        raise ValueError("Public input contract changed")
    return items, hashlib.sha256(raw).hexdigest()


def manifest():
    source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ranking_hash = hashlib.sha256(
        (Path(__file__).parent / "benchmark_rankings.py").read_bytes()
    ).hexdigest()
    return {
        "suite_id": "fictional-points-v1",
        "origin": "fictional_scripted_rehearsal",
        "repetitions": 2,
        "source_hashes": {"executor_evaluator": source_hash, "ranking": ranking_hash},
        "profiles": [profile | {"sha256": digest(profile)} for profile in PROFILES],
        "tasks": [
            {"id": task, "possible_points": points, "items_sha256": _public_input(task)[1]}
            for task, points in TASKS
        ],
        "evaluation_rule": "independent_repeated_addition_one_point_per_public_item_v1",
        "environment": "local_builtin_trusted_functions",
        "official_primary": None,
        "model_performance": False,
    }


def candidate(profile_id, public_items):
    if profile_id not in {p["id"] for p in PROFILES}:
        raise ValueError("Unknown fixed algorithm")
    answers = {}
    for index, item in enumerate(public_items):
        n = item["n"]
        answers[item["id"]] = (
            n * n
            if profile_id == "square-all-v1"
            or (profile_id == "square-even-v1" and n % 2 == 0)
            or (profile_id == "square-first-six-v1" and index < 6)
            else n
        )
    return {
        "answers_json": answers,
        "report_md": f"Executed {profile_id} on {len(public_items)} public integers. Software control only.",
    }


def evaluate(public_items, outputs):
    # Independently derives the mathematical oracle; no private grader files are loaded.
    criteria = []
    for index, item in enumerate(public_items, 1):
        expected = sum(item["n"] for _ in range(item["n"]))
        actual = outputs["answers_json"].get(item["id"])
        passed = type(actual) is int and actual == expected
        criteria.append(
            {
                "id": f"criterion-{index:03d}",
                "earned_points": "1" if passed else "0",
                "possible_points": "1",
                "passed": passed,
            }
        )
    return criteria


def run(frozen):
    if frozen != manifest():
        raise HTTPException(409, "Rehearsal source or public fixture changed; create a new draft")
    cells, observations = [], []
    for profile in frozen["profiles"]:
        for repetition in range(2):
            for task in frozen["tasks"]:
                started = perf_counter_ns()
                items, _ = _public_input(task["id"])
                outputs = candidate(profile["id"], items)
                criteria = evaluate(items, outputs)
                earned = sum(int(c["earned_points"]) for c in criteria)
                cell = {
                    "id": uid(),
                    "profile_id": profile["id"],
                    "task_id": task["id"],
                    "repetition": repetition,
                    "state": "completed",
                    "outputs": outputs,
                    "output_sha256": digest(outputs),
                    "criteria": criteria,
                    "earned_points": str(earned),
                    "possible_points": str(task["possible_points"]),
                    "duration_ms": (perf_counter_ns() - started) / 1_000_000,
                    "failure_tags": []
                    if earned == task["possible_points"]
                    else ["arithmetic_mismatch"],
                    "steps": [
                        {"kind": "public_input", "item_count": len(items)},
                        {"kind": "scripted_algorithm", "profile_id": profile["id"]},
                        {
                            "kind": "separate_deterministic_evaluation",
                            "criteria_count": len(criteria),
                        },
                    ],
                }
                cells.append(cell)
                observations.append(
                    {
                        "match_key": (task["id"], repetition),
                        "model_key": profile["id"],
                        "percent": Decimal(earned) / task["possible_points"] * 100,
                    }
                )
    profiles = []
    for profile in frozen["profiles"]:
        reps = [
            {
                "repetition": rep,
                "earned_points": str(
                    sum(
                        int(c["earned_points"])
                        for c in cells
                        if c["profile_id"] == profile["id"] and c["repetition"] == rep
                    )
                ),
                "possible_points": "81",
            }
            for rep in range(2)
        ]
        profiles.append(
            {
                "profile_id": profile["id"],
                "repetitions": reps,
                "mean_points": str(sum(Decimal(r["earned_points"]) for r in reps) / 2),
                "possible_points": "81",
            }
        )
    ranking = paired_rankings(observations)
    for metric in ranking.values():
        for row in metric["rows"]:
            row["profile_id"] = row.pop("model_key")
    result = {
        "cells": cells,
        "profiles": profiles,
        "ranking": ranking,
        "ranking_scope": "fictional_scripted_profiles_only",
        "provider_calls": 0,
        "official_primary": None,
        "model_performance": False,
    }
    if frozen != manifest():
        raise HTTPException(409, "Rehearsal source changed during execution; no result was stored")
    return result | {"result_sha256": digest(result)}


def get(c, identifier, lock=False):
    row = one(
        c,
        "SELECT * FROM anvil.benchmark_rehearsals WHERE id=%s" + (" FOR UPDATE" if lock else ""),
        (identifier,),
    )
    if not row:
        raise HTTPException(404, "Rehearsal not found")
    return row | {
        "report_authorization": report_policy.authorization(
            c,
            row["project_id"],
            "rehearsal",
            row["id"],
            row["result"].get("result_sha256") if row["result"] else None,
        ),
        "origin": "fictional_scripted_rehearsal",
        "model_performance": False,
        "provider_calls": 0,
        "official_primary": None,
    }


def create(c, project, user, body):
    frozen = manifest()
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_rehearsals(id,project_id,name,created_by,manifest,manifest_sha256) VALUES(%s,%s,%s,%s,%s,%s)",
        (identifier, project, body.name, user, Jsonb(frozen), digest(frozen)),
    )
    audit(c, project, user, "benchmark_rehearsal_created", identifier, {"provider_calls": 0})
    report_policy.snapshot(c, project, user, "rehearsal", identifier, executing=False)
    return get(c, identifier)


def execute(c, project, user, identifier, body):
    row = get(c, identifier, lock=True)
    if row["manifest_sha256"] != body.expected_manifest_sha256:
        raise HTTPException(409, "Exact frozen rehearsal manifest required")
    if row["state"] != "draft":
        return row
    try:
        result = run(row["manifest"])
    except HTTPException:
        raise
    except Exception:
        result = {
            "failure_code": "bounded_software_execution_failed",
            "provider_calls": 0,
            "official_primary": None,
            "model_performance": False,
        }
        result["result_sha256"] = digest(result)
        c.execute(
            "UPDATE anvil.benchmark_rehearsals SET state='failed',result=%s,executed_at=now() WHERE id=%s",
            (Jsonb(result), identifier),
        )
    else:
        c.execute(
            "UPDATE anvil.benchmark_rehearsals SET state='completed',result=%s,executed_at=now() WHERE id=%s",
            (Jsonb(result), identifier),
        )
        report_policy.record_execution(c, project, user, "rehearsal", identifier)
    audit(
        c,
        project,
        user,
        "benchmark_rehearsal_executed",
        identifier,
        {"provider_calls": 0, "result_sha256": result["result_sha256"]},
    )
    return get(c, identifier)


def require_report(c, row):
    if row["state"] != "completed" or not row["report_authorization"]["ready"]:
        raise HTTPException(409, "Completed execution and configured report authorization required")
    return row
