"""Immutable score revisions and deliberately redacted exports."""

import copy
import csv
import io
import json

from fastapi import HTTPException

from anvil import domain
from anvil.benchmark_protocol import Protocol
from anvil.benchmark_review_policy import review_state
from anvil.benchmark_scores import exact, scorecard, text
from anvil.db import Jsonb, audit, digest, one, uid


def latest(c, run_id, revision_id=None):
    if not one(c, "SELECT 1 FROM anvil.benchmark_comparisons WHERE run_id=%s", (run_id,)):
        raise HTTPException(404, "Comparison not found")
    row = one(
        c,
        "SELECT * FROM anvil.benchmark_score_revisions WHERE run_id=%s AND (%s::uuid IS NULL OR id=%s::uuid) ORDER BY revision DESC LIMIT 1",
        (run_id, revision_id, revision_id),
    )
    if row is None:
        raise HTTPException(409, "No stored score revision is available")
    reviews = c.execute(
        "SELECT assignment_id,decision FROM anvil.benchmark_score_reviews WHERE score_revision_id=%s ORDER BY created_at,id",
        (row["id"],),
    ).fetchall()
    basis = row["redacted_projection"].get("review_basis")
    return {
        "score_revision_id": str(row["id"]),
        "revision": row["revision"],
        "projection_sha256": row["projection_sha256"],
        "projection": row["redacted_projection"],
        "review_state": basis["state"]
        if basis
        else review_state(row["redacted_projection"], reviews),
        "reviews": basis.get("authorization_basis", {}).get(
            "completed_reviewers", len(basis["decisions"])
        )
        if basis
        else len(reviews),
    }


def publish(c, project, user, run_id, *, adjustments=None):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    comparison = one(c, "SELECT * FROM anvil.benchmark_comparisons WHERE run_id=%s", (run_id,))
    if comparison is None:
        raise HTTPException(404, "Comparison not found")
    protocol = Protocol.model_validate(
        domain.get_revision(c, comparison["protocol_revision_id"], "protocol")["content"]
    )
    previous = one(
        c,
        "SELECT * FROM anvil.benchmark_score_revisions WHERE run_id=%s ORDER BY revision DESC LIMIT 1",
        (run_id,),
    )
    adjudications = (
        list(previous["redacted_projection"].get("adjudications", [])) if previous else []
    )
    adjudications.extend(adjustments or [])
    expected = {
        str(t.task_revision_id): {
            x["id"]: x["possible_points"]
            for x in domain.get_revision(c, t.task_revision_id, "task")["content"]["criteria"]
        }
        for t in protocol.tasks
    }
    attempts = c.execute(
        """SELECT c.id cell_id,c.task_revision_id,c.slot,c.repetition,a.id attempt_id,a.attempt_no,
        e.state,e.validity,rt.report_artifact_id,rt.duration_ms,art.sha256 evidence_sha256,po.hard_constraint_ids
        FROM anvil.benchmark_cells c JOIN anvil.benchmark_cell_attempts a ON a.project_id=c.project_id AND a.cell_id=c.id AND a.attempt_no=1
        JOIN anvil.benchmark_offline_runtime rt ON rt.project_id=a.project_id AND rt.attempt_id=a.id
        LEFT JOIN anvil.artifacts art ON art.project_id=rt.project_id AND art.id=rt.report_artifact_id
        LEFT JOIN anvil.benchmark_attempt_policy_outcomes po ON po.project_id=a.project_id AND po.attempt_id=a.id
        JOIN LATERAL (SELECT state,validity FROM anvil.benchmark_attempt_events WHERE attempt_id=a.id ORDER BY event_seq DESC LIMIT 1) e ON true
        WHERE c.run_id=%s ORDER BY c.task_revision_id,c.slot,c.repetition""",
        (run_id,),
    ).fetchall()
    cells = []
    for row in attempts:
        criteria = c.execute(
            "SELECT r.criterion_id,r.earned_points,r.possible_points,r.output_sha256 evidence_sha256,r.absence_event_id FROM anvil.benchmark_criterion_results r JOIN anvil.benchmark_evaluator_calls ec ON ec.project_id=r.project_id AND ec.id=r.evaluator_call_id WHERE ec.attempt_id=%s AND ec.evaluation_revision=1 AND ec.purpose='deterministic' ORDER BY r.criterion_id",
            (row["attempt_id"],),
        ).fetchall()
        adjusted = [
            {
                k: format(v, "f")
                if k in ("earned_points", "possible_points")
                else str(v)
                if k == "absence_event_id" and v is not None
                else v
                for k, v in criterion.items()
            }
            for criterion in criteria
        ]
        for adjudication in adjudications:
            if adjudication["cell_id"] == str(row["cell_id"]):
                for criterion in adjusted:
                    if criterion["criterion_id"] == adjudication["criterion_id"]:
                        criterion["earned_points"] = adjudication["earned_points"]
        cells.append(
            {
                "task_revision_id": str(row["task_revision_id"]),
                "slot": row["slot"],
                "repetition": row["repetition"],
                "attempt_no": row["attempt_no"],
                "state": row["state"],
                "validity": row["validity"],
                "duration_ms": row["duration_ms"],
                "evidence_sha256": row["evidence_sha256"],
                "hard_constraint_ids": row["hard_constraint_ids"] or [],
                "expected_criteria": expected[str(row["task_revision_id"])],
                "criteria": adjusted,
            }
        )
    projection, hash_ = scorecard(protocol, cells)
    if protocol.review_policy and protocol.review_policy.version == 2:
        from anvil import benchmark_report_policy as report_policy

        release = report_policy.authorization(c, project, "comparison", run_id, None)
        # Release is not a human verification fact; no fictional review rows.
        if release["state"] in {"admin_run_exempt", "policy_no_review"}:
            for model in projection["models"]:
                if model["score_complete"]:
                    model["primary"] = model["diagnostic"]["complete_repetition_mean"]
                    model["completion"] = "complete"
            projection["complete"] = all(m["primary"] is not None for m in projection["models"])
            projection["review_basis"] = {
                "state": release["state"],
                "decisions": [],
                "reviewer_verified": False,
                "authorization_basis": release,
            }
    if adjudications:
        projection["adjudications"] = adjudications
    measurement = digest(projection)
    if previous and previous["redacted_projection"].get("measurement_sha256") == measurement:
        return latest(c, run_id)
    projection["measurement_sha256"] = measurement
    hash_ = digest(projection)
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_score_revisions(id,project_id,run_id,revision,predecessor_id,projection_sha256,redacted_projection,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            run_id,
            previous["revision"] + 1 if previous else 1,
            previous["id"] if previous else None,
            hash_,
            Jsonb(projection),
            user,
        ),
    )
    if projection["execution_complete"]:
        c.execute(
            "UPDATE anvil.runs SET state='awaiting_review',row_version=row_version+1 WHERE id=%s AND NOT cancel_requested",
            (run_id,),
        )
    audit(
        c,
        project,
        user,
        "benchmark.score_revision_published",
        identifier,
        {"projection_sha256": hash_, "complete": projection["complete"]},
    )
    return latest(c, run_id)


def publish_reviewed(c, project, user, run_id, parent, decisions, state):
    """Review decisions become a source-bound immutable successor, not a mutable view."""
    projection = copy.deepcopy(parent["redacted_projection"])
    for model in projection["models"]:
        if model["score_complete"]:
            model["primary"] = model["diagnostic"]["complete_repetition_mean"]
            model["completion"] = "complete"
    projection["complete"] = all(model["primary"] is not None for model in projection["models"])
    projection["review_basis"] = {
        "state": state,
        "reviewer_verified": state in {"approved", "adjudicated", "reviewed"},
        "score_revision_id": str(parent["id"]),
        "projection_sha256": parent["projection_sha256"],
        "decisions": [
            {
                "review_id": str(row["id"]),
                "assignment_id": str(row["assignment_id"]),
                "reviewer_id": str(row["reviewer_id"]),
                "decision": row["decision"],
                "evidence_sha256": row["evidence_sha256"],
            }
            for row in decisions
        ],
    }
    if state in {"admin_approved", "admin_run_exempt", "policy_no_review", "reviewed"}:
        from anvil import benchmark_report_policy as report_policy

        projection["review_basis"]["authorization_basis"] = report_policy.authorization(
            c, project, "comparison", run_id, parent["projection_sha256"]
        )
    identifier, hash_ = uid(), digest(projection)
    c.execute(
        "INSERT INTO anvil.benchmark_score_revisions(id,project_id,run_id,revision,predecessor_id,projection_sha256,redacted_projection,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            run_id,
            parent["revision"] + 1,
            parent["id"],
            hash_,
            Jsonb(projection),
            user,
        ),
    )
    if projection["complete"]:
        c.execute(
            "UPDATE anvil.runs SET state='completed',row_version=row_version+1 WHERE id=%s AND NOT cancel_requested",
            (run_id,),
        )
    audit(
        c,
        project,
        user,
        "benchmark.reviewed_score_published",
        identifier,
        {"predecessor_score_revision_id": str(parent["id"]), "projection_sha256": hash_},
    )
    return latest(c, run_id)


def admin_approve(c, project, user, run_id, body):
    from anvil import benchmark_execution as execution
    from anvil import benchmark_report_policy as report_policy

    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    execution.report_authority_current(c, project, user, run_id)
    current = latest(c, run_id)
    report_policy.decide(
        c, project, user, "comparison", run_id, current["projection_sha256"], body, admin=True
    )
    parent = one(
        c,
        "SELECT * FROM anvil.benchmark_score_revisions WHERE id=%s",
        (current["score_revision_id"],),
    )
    result = publish_reviewed(c, project, user, run_id, parent, [], "admin_approved")
    return result


def correct(c, project, user, run_id, body):
    """An assigned human adjudicator creates a successor; native raw rows stay immutable."""
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    current = latest(c, run_id)
    if (
        current["score_revision_id"] != str(body.score_revision_id)
        or current["projection_sha256"] != body.expected_projection_sha256
    ):
        raise HTTPException(409, "Corrections require the exact latest score revision")
    policy = current["projection"]["review_requirements"]
    if (
        policy.get("state") != "declared"
        or str(body.assignment_id) != policy["adjudicator_assignment_id"]
    ):
        raise HTTPException(403, "Only the frozen independent adjudicator can propose corrections")
    duty = one(
        c,
        "SELECT 1 FROM anvil.benchmark_private_assignments a WHERE a.id=%s AND a.user_id=%s AND a.scope='evaluation_review' AND a.artifact_id IS NULL AND a.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r WHERE r.assignment_id=a.id)",
        (body.assignment_id, user),
    )
    reviews = c.execute(
        "SELECT assignment_id,decision FROM anvil.benchmark_score_reviews WHERE score_revision_id=%s",
        (body.score_revision_id,),
    ).fetchall()
    done = {str(row["assignment_id"]): row["decision"] for row in reviews}
    if (
        duty is None
        or not {policy["first_assignment_id"], policy["second_assignment_id"]} <= set(done)
        or not any(d in {"disputed", "changes_required"} for d in done.values())
    ):
        raise HTTPException(
            409, "Corrections require current duty and completed independent disputed reviews"
        )
    changes, seen = [], set()
    for change in body.corrections:
        key = (str(change.cell_id), change.criterion_id)
        if key in seen:
            raise HTTPException(422, "Each criterion correction must occur once")
        seen.add(key)
        observed = one(
            c,
            """SELECT cr.earned_points,cr.possible_points,cr.output_sha256,trace.sha256 report_sha256
            FROM anvil.benchmark_cells cell JOIN anvil.benchmark_cell_attempts a ON a.project_id=cell.project_id AND a.cell_id=cell.id AND a.attempt_no=1
            JOIN anvil.benchmark_evaluator_calls ec ON ec.project_id=a.project_id AND ec.attempt_id=a.id AND ec.evaluation_revision=1 AND ec.purpose='deterministic'
            JOIN anvil.benchmark_criterion_results cr ON cr.project_id=ec.project_id AND cr.evaluator_call_id=ec.id AND cr.criterion_id=%s
            JOIN anvil.benchmark_offline_runtime rt ON rt.project_id=a.project_id AND rt.attempt_id=a.id AND rt.state='completed'
            JOIN anvil.artifacts trace ON trace.project_id=rt.project_id AND trace.id=rt.report_artifact_id
            WHERE cell.run_id=%s AND cell.id=%s""",
            (change.criterion_id, run_id, change.cell_id),
        )
        if observed is None:
            raise HTTPException(404, "A valid original criterion result is required")
        earned = exact(change.earned_points)
        if observed["output_sha256"] is None and earned != 0:
            raise HTTPException(
                409, "An absent deliverable cannot receive positive criterion credit"
            )
        if earned > observed["possible_points"] or change.evidence_sha256 not in {
            observed["output_sha256"],
            observed["report_sha256"],
        }:
            raise HTTPException(
                409, "Correction points/evidence differ from the captured criterion"
            )
        changes.append(
            {
                "cell_id": str(change.cell_id),
                "criterion_id": change.criterion_id,
                "earned_points": text(earned),
                "possible_points": format(observed["possible_points"], "f"),
                "native_earned_points": format(observed["earned_points"], "f"),
                "evidence_sha256": change.evidence_sha256,
                "adjudicated_by": str(user),
                "predecessor_score_revision_id": current["score_revision_id"],
            }
        )
    if policy["adjudicator_assignment_id"] not in done:
        c.execute(
            "INSERT INTO anvil.benchmark_score_reviews(id,project_id,score_revision_id,reviewer_id,assignment_id,decision,evidence_sha256,rationale) VALUES(%s,%s,%s,%s,%s,'adjudicated',%s,%s)",
            (
                uid(),
                project,
                body.score_revision_id,
                user,
                body.assignment_id,
                current["projection_sha256"],
                body.rationale,
            ),
        )
    successor = publish(c, project, user, run_id, adjustments=changes)
    audit(
        c,
        project,
        user,
        "benchmark.score_corrected",
        successor["score_revision_id"],
        {
            "predecessor_score_revision_id": current["score_revision_id"],
            "criterion_count": len(changes),
        },
    )
    return successor


def review(c, project, user, run_id, body):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    current = latest(c, run_id, body.score_revision_id)
    newest = latest(c, run_id)
    if newest["score_revision_id"] != current["score_revision_id"] or current["projection"].get(
        "review_basis"
    ):
        raise HTTPException(409, "Review requires the latest unreviewed score revision")
    if current["projection_sha256"] != body.expected_projection_sha256:
        raise HTTPException(409, "Exact score projection changed")
    assignment = one(
        c,
        "SELECT * FROM anvil.benchmark_private_assignments a WHERE id=%s AND user_id=%s AND scope='evaluation_review' AND expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r WHERE r.assignment_id=a.id)",
        (body.assignment_id, user),
    )
    if assignment is None or assignment["artifact_id"] is not None:
        raise HTTPException(403, "A current project-wide evaluation duty is required")
    policy = current["projection"].get("review_requirements", {})
    if policy.get("state") == "report_policy_v2":
        from anvil import benchmark_report_policy as report_policy

        if str(body.assignment_id) not in policy["reviewer_assignment_ids"]:
            raise HTTPException(403, "Duty is not in the frozen report policy")
        if body.decision != "approved" or body.evidence_sha256 != current["projection_sha256"]:
            raise HTTPException(409, "Exact result and affirmative human report review required")
        release = report_policy.decide(
            c,
            project,
            user,
            "comparison",
            run_id,
            current["projection_sha256"],
            report_policy.Review(
                expected_result_sha256=body.expected_projection_sha256,
                rationale=body.rationale,
                assignment_id=body.assignment_id,
                human_reviewed=True,
            ),
        )
        if release["ready"]:
            parent = one(
                c,
                "SELECT * FROM anvil.benchmark_score_revisions WHERE id=%s",
                (body.score_revision_id,),
            )
            return publish_reviewed(c, project, user, run_id, parent, [], release["state"])
        return latest(c, run_id)
    if policy.get("state") != "declared":
        raise HTTPException(409, "Score review policy is incomplete")
    stage = next(
        (
            stage
            for stage in ("first", "second", "adjudicator")
            if policy[stage + "_assignment_id"] == str(body.assignment_id)
        ),
        None,
    )
    if stage is None:
        raise HTTPException(403, "This individual duty is not assigned by the frozen protocol")
    prior = c.execute(
        "SELECT reviewer_id,assignment_id,decision FROM anvil.benchmark_score_reviews WHERE score_revision_id=%s",
        (body.score_revision_id,),
    ).fetchall()
    completed = {str(r["assignment_id"]) for r in prior}
    if stage != "first" and policy["first_assignment_id"] not in completed:
        raise HTTPException(409, "First assigned review is required before a later position")
    if stage == "adjudicator" and policy["second_assignment_id"] not in completed:
        raise HTTPException(409, "Second assigned review is required before adjudication")
    if (stage == "adjudicator") != (body.decision == "adjudicated"):
        raise HTTPException(403, "Only the distinct assigned adjudicator can adjudicate")
    evidence = one(
        c,
        "SELECT 1 FROM anvil.benchmark_offline_runtime rt JOIN anvil.artifacts a ON a.project_id=rt.project_id AND a.id IN (rt.output_artifact_id,rt.report_artifact_id) WHERE rt.run_id=%s AND a.sha256=%s LIMIT 1",
        (run_id, body.evidence_sha256),
    )
    if body.evidence_sha256 != current["projection_sha256"] and evidence is None:
        raise HTTPException(
            409, "Review evidence must bind this exact projection or its captured outputs"
        )
    if any(str(x["reviewer_id"]) == str(user) for x in prior):
        raise HTTPException(409, "Immutable reviewer decision already exists")
    if any(x["decision"] == "adjudicated" for x in prior):
        raise HTTPException(409, "Adjudicated evidence requires a successor score revision")
    if body.decision == "adjudicated" and not any(
        x["decision"] in {"disputed", "changes_required"} for x in prior
    ):
        raise HTTPException(409, "Adjudication requires an existing independent dispute")
    c.execute(
        "INSERT INTO anvil.benchmark_score_reviews(id,project_id,score_revision_id,reviewer_id,assignment_id,decision,evidence_sha256,rationale) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            uid(),
            project,
            body.score_revision_id,
            user,
            body.assignment_id,
            body.decision,
            body.evidence_sha256,
            body.rationale,
        ),
    )
    audit(
        c,
        project,
        user,
        "benchmark.score_reviewed",
        body.score_revision_id,
        {"decision": body.decision},
    )
    decisions = c.execute(
        "SELECT * FROM anvil.benchmark_score_reviews WHERE score_revision_id=%s ORDER BY created_at,id",
        (body.score_revision_id,),
    ).fetchall()
    state = review_state(current["projection"], decisions)
    if state in {"approved", "adjudicated"}:
        parent = one(
            c,
            "SELECT * FROM anvil.benchmark_score_revisions WHERE id=%s",
            (body.score_revision_id,),
        )
        return publish_reviewed(c, project, user, run_id, parent, decisions, state)
    return latest(c, run_id, body.score_revision_id)


def export(c, run_id, format_, revision_id=None):
    stored = latest(c, run_id, revision_id)
    if format_ == "json":
        return json.dumps(
            stored, sort_keys=True, ensure_ascii=False, allow_nan=False
        ), "application/json"
    if format_ == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(
            [
                "score_revision_id",
                "origin",
                "slot",
                "provider",
                "model",
                "completion",
                "earned_points",
                "possible_points",
                "percent",
            ]
        )
        for model in stored["projection"]["models"]:
            primary = model["primary"] or {}
            values = [
                stored["score_revision_id"],
                stored["projection"]["origin"],
                model["slot"] + 1,
                model["provider"],
                model["model_id"],
                model["completion"],
                primary.get("earned_points", ""),
                primary.get("possible_points", ""),
                primary.get("percent", ""),
            ]
            writer.writerow(
                [
                    "'" + str(v)
                    if str(v).lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
                    else v
                    for v in values
                ]
            )
        return stream.getvalue(), "text/csv"
    if format_ == "report":
        lines = [
            "# Benchmark score report",
            "",
            "Origin: " + stored["projection"]["origin"],
            "Score revision: " + stored["score_revision_id"],
            "Projection SHA-256: " + stored["projection_sha256"],
            "Review: " + stored["review_state"],
            "",
            "Offline software conformance is not model performance. Primary is the mean of two complete repetitions out of81, released under the frozen report policy or explicit authenticated Admin authorization. Authorization is distinct from human reviewer verification; pending required authorization keeps primary null.",
            "",
        ]
        for model in stored["projection"]["models"]:
            primary = model["primary"]
            lines.append(
                json.dumps(
                    {
                        "slot": model["slot"] + 1,
                        "provider": model["provider"],
                        "model_id": model["model_id"],
                        "completion": model["completion"],
                        "primary": primary,
                        "scored_cells": model["scored"],
                        "duration": model["duration"],
                        "cost": model["cost"],
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                )
            )
        return "\n".join(lines) + "\n", "text/plain"
    raise HTTPException(409, "This comparison has no reviewed export adapter for that format")
