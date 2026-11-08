"""Frozen point-percent borderline and reproducible review selection."""

import hashlib
from decimal import Decimal


def key(task, slot, repetition):
    return f"{task}:{slot}:{repetition}"


def requirements(protocol, cells):
    policy = protocol.review_policy
    if policy is None:
        return {"state": "blocked_missing_policy", "second_required": None, "cells": []}
    declared = {str(t.task_revision_id): t for t in policy.tasks}
    observed = {key(c["task_revision_id"], c["slot"], c["repetition"]): c for c in cells}
    selection = []
    for cell in protocol.cells():
        stable = key(cell["task_revision_id"], cell["slot"], cell["repetition"])
        # Same immutable protocol/cell always selects the same cohort before any
        # output, score, retry or success is available. This matches the existing
        # D-SIMPLE reproducible10% hash policy, using point percentages below.
        sampled = (
            int(hashlib.sha256((protocol.subject_sha256 + ":" + stable).encode()).hexdigest(), 16)
            % 100
            < 10
        )
        reasons = ["frozen_sample"] if sampled else []
        actual = observed.get(stable)
        if (
            actual
            and actual["validity"] == "valid"
            and actual["state"] in ("completed", "model_failed")
        ):
            task_policy = declared[cell["task_revision_id"]]
            criteria = actual["criteria"]
            if actual.get("hard_constraint_ids"):
                reasons.append("declared_hard_safety_failure")
            maximum = sum(Decimal(c["possible_points"]) for c in criteria)
            earned = sum(Decimal(c["earned_points"]) for c in criteria)
            if (
                maximum
                and abs(earned * 100 / maximum - Decimal(task_policy.pass_threshold_percent)) <= 5
            ):
                reasons.append("within_five_percentage_points")
            if any(
                c["criterion_id"] in task_policy.critical_criterion_ids
                and Decimal(c["earned_points"]) < Decimal(c["possible_points"])
                for c in criteria
            ):
                reasons.append("critical_failure")
        selection.append({"cell_key": stable, "reasons": reasons, "second_required": bool(reasons)})
    return {
        "state": "declared",
        "first_assignment_id": str(policy.first_assignment_id),
        "second_assignment_id": str(policy.second_assignment_id),
        "adjudicator_assignment_id": str(policy.adjudicator_assignment_id),
        "calibration_sha256": policy.calibration_sha256,
        "sample_percent": 10,
        "borderline_percentage_points": 5,
        "second_required": any(c["second_required"] for c in selection),
        "cells": selection,
    }


def review_state(projection, reviews):
    policy = projection.get("review_requirements", {})
    if policy.get("state") != "declared":
        return "blocked_missing_policy"
    duties = {
        "first": policy["first_assignment_id"],
        "second": policy["second_assignment_id"],
        "adjudicator": policy["adjudicator_assignment_id"],
    }
    decisions = {str(r["assignment_id"]): r["decision"] for r in reviews}
    first, second, adjudicator = (
        decisions.get(duties[k]) for k in ("first", "second", "adjudicator")
    )
    if adjudicator == "adjudicated":
        return "adjudicated"
    if "disputed" in (first, second):
        return "adjudication_required" if second is not None else "second_review_required"
    if "changes_required" in (first, second):
        return "changes_required"
    if first is None:
        return "pending"
    if policy["second_required"] and second is None:
        return "second_review_required"
    return (
        "approved"
        if first == "approved" and (not policy["second_required"] or second == "approved")
        else "pending"
    )
