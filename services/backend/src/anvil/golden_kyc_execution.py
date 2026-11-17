"""Anvil-only durable Golden capture → separate grading → canonical report path.

Each cell commits independently. A running owner is never automatically reclaimed
or replayed. The software candidate sees only assigned tool observations. Grader
and scheduler connections are disjoint; neither is an ordinary Anvil worker.
"""

from collections import Counter

from fastapi import HTTPException

from anvil.db import Jsonb, digest, uid
from anvil.golden_kyc_anvil import CANDIDATE, ENVIRONMENT_KEY, validate
from anvil.golden_kyc_evaluators import CRITERIA
from anvil.golden_kyc_investigator import investigate
from anvil.golden_kyc_runtime import locked, prepare_run, tick


def capture_run(connections, project, *, max_cells=2000):
    from anvil.golden_kyc_data import SEED
    from anvil.golden_kyc_openenv import GoldenAction, GoldenEnvironment

    with connections() as c:
        job = c.execute(
            "SELECT * FROM banking.execution_jobs WHERE project_id=%s AND state='queued' ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1",
            (project,),
        ).fetchone()
        if not job:
            return None
        run = c.execute(
            "SELECT * FROM anvil.benchmark_runs WHERE id=%s", (job["run_id"],)
        ).fetchone()
        imported = c.execute(
            "SELECT * FROM banking.anvil_imports WHERE id=%s", (run["snapshot"]["import_id"],)
        ).fetchone()
        validate(c, imported)
        if (
            digest(run["snapshot"]) != run["snapshot_sha256"]
            or run["snapshot"]["import_sha256"] != imported["manifest_sha256"]
            or run["snapshot"]["planned_cells"] > max_cells
        ):
            raise HTTPException(409, "Frozen Golden Run binding invalid or exceeds worker limit")
        user = run["created_by"]
        member = c.execute(
            "SELECT m.role FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active",
            (project, user),
        ).fetchone()
        if not member:
            raise HTTPException(403, "Current authenticated membership revoked")
        software = prepare_run(
            c,
            project,
            user,
            imported["pack_id"],
            run["snapshot"]["repetitions"],
            case_ids=[a["application_id"] for a in imported["manifest"]["case_assignments"]]
            if imported["manifest"].get("task_mode") in {"reusable_state_workflow", "reusable_application_workflow"}
            else None,
        )
        c.execute(
            "INSERT INTO banking.anvil_runs(project_id,run_id,import_id,software_run_id) VALUES(%s,%s,%s,%s)",
            (project, run["id"], imported["id"], software["run_id"]),
        )
        token = uid()
        c.execute(
            "UPDATE banking.execution_jobs SET state='running',claim_token=%s WHERE id=%s",
            (token, job["id"]),
        )
        c.execute(
            "UPDATE anvil.benchmark_runs SET state='running',executed_by=%s,admin_execution=%s WHERE id=%s",
            (user, member["role"] == "admin", run["id"]),
        )
        cells = c.execute(
            "SELECT * FROM banking.run_cells WHERE run_id=%s ORDER BY application_id,repetition",
            (software["run_id"],),
        ).fetchall()
    try:
        for cell in cells:
            case_assignment = next(
                (
                    a
                    for a in imported["manifest"].get("case_assignments", [])
                    if a["application_id"] == cell["application_id"]
                ),
                None,
            )
            if (
                imported["manifest"].get("task_mode") in {"reusable_state_workflow", "reusable_application_workflow"}
                and case_assignment is None
            ):
                raise RuntimeError("Case has no immutable state task assignment")
            task_id = case_assignment["task_id"] if case_assignment else cell["application_id"]
            episode = GoldenEnvironment(connections, project, user, cell["trial_id"])
            episode.reset(seed=SEED)
            credentials = episode.credentials

            def tool(action, arguments):
                with connections() as c:
                    member = c.execute(
                        "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active",
                        (project, user),
                    ).fetchone()
                    if not member:
                        raise RuntimeError("membership_revoked")
                observed = episode.step(
                    GoldenAction(
                        operation=action,
                        arguments=arguments,
                        expected_generation=credentials["generation"],
                    )
                ).result
                if observed["status"] != "completed":
                    raise RuntimeError("tool_action_denied_or_runtime_unavailable")
                return observed["result"]

            def wait(kind, amount):
                with connections() as c:
                    tick(
                        c,
                        project,
                        user,
                        cell["trial_id"],
                        business_days=amount if kind == "customer_response" else 0,
                        wait_seconds=0 if kind == "customer_response" else amount,
                    )

            investigate(tool, wait)
            with connections() as c:
                trial = locked(c, project, user, cell["trial_id"])
                events = c.execute(
                    "SELECT action,record,sequence FROM banking.events WHERE trial_id=%s AND generation=%s ORDER BY sequence",
                    (cell["trial_id"], credentials["generation"]),
                ).fetchall()
                capture = {
                    "schema_version": "anvil.golden-kyc-capture.v1",
                    "origin": "software_control_not_model",
                    "trial_id": str(cell["trial_id"]),
                    "generation": credentials["generation"],
                    "state_sha256": digest(trial["state"]),
                    "output": trial["state"]["final"],
                    "events_sha256": digest(events),
                    "event_count": len(events),
                    "tool_calls": trial["state"]["counters"]["calls"],
                    "environment_manifest_sha256": run["snapshot"]["environment_manifest_sha256"],
                    "import_sha256": imported["manifest_sha256"],
                    "task_id": task_id,
                    "application_id": cell["application_id"],
                    "application_sha256": case_assignment["application_sha256"]
                    if case_assignment
                    else None,
                    "binding_sha256": next(
                        b["binding_sha256"]
                        for b in imported["manifest"]["bindings"]
                        if b["task_id"] == task_id
                    ),
                    "provider_calls": 0,
                    "model_performance": False,
                }
                c.execute(
                    "INSERT INTO anvil.benchmark_run_cells(id,project_id,run_id,model_key,task_key,environment_key,repetition,capture,capture_sha256,case_key) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        uid(),
                        project,
                        run["id"],
                        CANDIDATE["id"],
                        task_id,
                        ENVIRONMENT_KEY,
                        cell["repetition"] - 1,
                        Jsonb(capture),
                        digest(capture),
                        cell["application_id"] if case_assignment else "",
                    ),
                )
            episode.close()
        with connections() as c:
            c.execute(
                "UPDATE banking.execution_jobs SET state='captured' WHERE id=%s AND claim_token=%s",
                (job["id"], token),
            )
        return {"run_id": str(run["id"]), "state": "captured", "captured_cells": len(cells)}
    except Exception as exc:
        with connections() as c:
            failure = {
                "error_code": "golden_capture_failed",
                "error_type": type(exc).__name__,
                "provider_calls": 0,
                "model_performance": False,
                "retained_partial_captures": True,
            }
            c.execute(
                "UPDATE banking.execution_jobs SET state='failed',error_code='golden_capture_failed',finished_at=now() WHERE id=%s AND claim_token=%s",
                (job["id"], token),
            )
            c.execute(
                "UPDATE anvil.benchmark_runs SET state='failed',result=%s,result_sha256=%s,executed_at=now() WHERE id=%s",
                (Jsonb(failure), digest(failure), run["id"]),
            )
        raise


def canonical_assessment(result):
    rubric = result["rubric_score"]
    earned = None if rubric["unscored_points"] else str(rubric["earned_points"])
    criteria = [
        {
            "id": name,
            "description": name.replace("_", " "),
            "dimension": "correctness" if i < 6 else "evidence" if i < 8 else "constraints",
            "earned_points": None
            if result["checks"][name] is None
            else str(result["checks"][name]),
            "possible_points": "5",
            "passed": None if result["checks"][name] is None else result["checks"][name] == 5,
        }
        for i, name in enumerate(CRITERIA)
    ]
    findings = [
        {
            "policy_id": "golden-bank",
            "rule_id": name,
            "outcome": "unknown"
            if result["checks"][name] is None
            else "pass"
            if result["checks"][name] > 0
            else "fail",
            "reason": "Separate sealed-evidence rubric check; pending review remains unscored",
            "severity": "review_required" if result["checks"][name] is None else "rubric",
            "requirement": name.replace("_", " "),
        }
        for name in CRITERIA
    ]
    if result["critical_failures"]:
        findings.append(
            {
                "policy_id": "golden-critical-failure",
                "rule_id": "critical",
                "outcome": "fail",
                "reason": "Observed critical failures: " + ", ".join(result["critical_failures"]),
            }
        )
    return {
        "earned_points": earned,
        "diagnostic_points": str(rubric["earned_points"]),
        "possible_points": "100",
        "unscored_points": rubric["unscored_points"],
        "criteria": criteria,
        "failure_modes": [
            {"id": failure, "title": failure.replace("_", " ")}
            for failure in result["critical_failures"]
        ],
        "policy_findings": findings,
        "safety": [
            {
                "axis": "injection",
                "outcome": "not_evaluated",
                "reason": "No qualified semantic injection verdict inferred from task score",
            },
            {
                "axis": "containment",
                "outcome": "not_evaluated",
                "reason": "Native Harbor isolation remains a separate qualification gate",
            },
        ],
        "judge": {"status": "off", "value": None},
        "logprobs": {"status": "unavailable", "value": None},
        "overall_result": result["overall_result"],
        "evaluation_coverage": result["evaluation_coverage"],
        "issues": result["issues"],
    }


def grade_run(connections, project):
    from anvil.golden_kyc_grader import grade

    with connections() as c:
        job = c.execute(
            "SELECT j.* FROM banking.execution_jobs j WHERE j.project_id=%s AND j.state='captured' AND EXISTS(SELECT 1 FROM anvil.benchmark_run_cells b WHERE b.run_id=j.run_id AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_run_scores s WHERE s.cell_id=b.id)) ORDER BY j.created_at,j.id FOR UPDATE SKIP LOCKED LIMIT 1",
            (project,),
        ).fetchone()
        if not job:
            return None
        imported = c.execute(
            "SELECT i.* FROM banking.anvil_imports i JOIN banking.anvil_runs l ON l.import_id=i.id WHERE l.run_id=%s",
            (job["run_id"],),
        ).fetchone()
        validate(c, imported)
        cells = c.execute(
            "SELECT * FROM anvil.benchmark_run_cells WHERE run_id=%s ORDER BY task_key,repetition",
            (job["run_id"],),
        ).fetchall()
        for cell in cells:
            if c.execute(
                "SELECT 1 FROM anvil.benchmark_run_scores WHERE cell_id=%s", (cell["id"],)
            ).fetchone():
                continue
            if digest(cell["capture"]) != cell["capture_sha256"]:
                raise ValueError("Captured Golden evidence changed")
            result = grade(c, project, cell["capture"]["trial_id"], cell["capture"]["generation"])
            if result["state_sha256"] != cell["capture"]["state_sha256"]:
                raise ValueError("Grader sealed state differs from captured binding")
            assessment = canonical_assessment(result)
            c.execute(
                "INSERT INTO anvil.benchmark_run_scores(id,project_id,cell_id,assessment,assessment_sha256) VALUES(%s,%s,%s,%s,%s)",
                (uid(), project, cell["id"], Jsonb(assessment), digest(assessment)),
            )
            from anvil.expert_reviews import register_kyc_cell

            register_kyc_cell(c, project, job["run_id"], cell, result)
        # Scheduler alone finalizes the canonical Run after observing all scores.
        return {"run_id": str(job["run_id"]), "graded_cells": len(cells), "state": "graded"}


def finish_run(connections, project):
    with connections() as c:
        job = c.execute(
            "SELECT j.* FROM banking.execution_jobs j WHERE j.project_id=%s AND j.state='captured' AND (SELECT count(*) FROM anvil.benchmark_run_scores s JOIN anvil.benchmark_run_cells b ON b.id=s.cell_id WHERE b.run_id=j.run_id)=(SELECT (snapshot->>'planned_cells')::int FROM anvil.benchmark_runs r WHERE r.id=j.run_id) ORDER BY j.created_at FOR UPDATE SKIP LOCKED LIMIT 1",
            (project,),
        ).fetchone()
        if not job:
            return None
        cells = c.execute(
            "SELECT b.capture,s.assessment FROM anvil.benchmark_run_cells b JOIN anvil.benchmark_run_scores s ON s.cell_id=b.id WHERE b.run_id=%s ORDER BY b.task_key,b.repetition",
            (job["run_id"],),
        ).fetchall()
        result = {
            "schema_version": "anvil.golden-kyc-result.v1",
            "cells": len(cells),
            "graded_cells": sum(x["assessment"]["earned_points"] is not None for x in cells),
            "unscored_cells": sum(x["assessment"]["earned_points"] is None for x in cells),
            "dispositions": dict(Counter(x["capture"]["output"]["decision"] for x in cells)),
            "overall_results": dict(Counter(x["assessment"]["overall_result"] for x in cells)),
            "provider_calls": 0,
            "model_performance": False,
            "legal_review": "pending",
            "independent_case_review": "pending",
        }
        c.execute(
            "UPDATE anvil.benchmark_runs SET state='completed',result=%s,result_sha256=%s,executed_at=now() WHERE id=%s",
            (Jsonb(result), digest(result), job["run_id"]),
        )
        c.execute(
            "UPDATE banking.execution_jobs SET state='completed',finished_at=now() WHERE id=%s",
            (job["id"],),
        )
        return {"run_id": str(job["run_id"]), "state": "completed", "result": result}
