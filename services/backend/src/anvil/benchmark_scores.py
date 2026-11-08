"""Exact primary score projections from sealed, validated criterion observations.

This module does not grade answers, infer missing criteria, pick best attempts or
turn operational failures into model zeroes. Its input is the evaluator evidence.
"""

import re
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from anvil.db import digest


def exact(value):
    if type(value) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]{0,6})(?:\.[0-9]{1,8})?", value):
        raise ValueError("Points must be exact decimal strings")
    result = Decimal(value)
    if not result.is_finite() or result < 0 or result > 1000000:
        raise ValueError("Invalid points")
    if result.as_tuple().exponent < -8:
        raise ValueError("Points exceed stored decimal precision")
    return result


def text(value):
    return format(value.normalize(), "f") if value else "0"


def percent(earned, possible):
    if possible <= 0:
        raise ValueError("A positive denominator is required")
    return format((earned * 100 / possible).quantize(Decimal(".01"), ROUND_HALF_UP), ".2f")


def criterion_totals(criteria, expected):
    """Require every frozen criterion exactly once and its original denominator."""
    if not isinstance(criteria, list) or not isinstance(expected, dict) or not expected:
        raise ValueError("Frozen criteria and observed results are required")
    seen, earned, possible = set(), Decimal(0), Decimal(0)
    for item in criteria:
        key = item["criterion_id"]
        if key in seen or key not in expected:
            raise ValueError("Duplicate or unexpected criterion")
        seen.add(key)
        maximum, actual = exact(item["possible_points"]), exact(item["earned_points"])
        if maximum <= 0 or maximum != exact(expected[key]) or actual > maximum:
            raise ValueError("Criterion denominator or earned points mismatch")
        # Evidence authorization is performed at API export time; identity remains
        # bound here and no private oracle/definition is copied into the scorecard.
        if not re.fullmatch(r"[a-f0-9]{64}", item.get("evidence_sha256", "")):
            raise ValueError("Criterion evidence binding is required")
        earned += actual
        possible += maximum
    if seen != set(expected):
        raise ValueError("Incomplete criterion set")
    return earned, possible


def scorecard(protocol, cells):
    """One observation per initial cell; incomplete primary is always null.

    Each supplied row carries task_revision_id, slot, repetition, attempt_no,
    validity, state, criteria, expected_criteria and immutable evidence digest.
    Missing rows stay missing rather than becoming manufactured zero scores.
    """
    planned = {
        (row["task_revision_id"], row["slot"], row["repetition"])
        for row in protocol.cells()
    }
    observations = {}
    task_points = {str(t.task_revision_id): Decimal(t.possible_points) for t in protocol.tasks}
    for cell in cells:
        key = (str(cell["task_revision_id"]), cell["slot"], cell["repetition"])
        if key not in planned or key in observations:
            raise ValueError("Unexpected or duplicate comparison cell")
        if cell["attempt_no"] != 1:
            raise ValueError("Primary comparison never selects a replacement/best attempt")
        if not re.fullmatch(r"[a-f0-9]{64}", cell.get("evidence_sha256", "")):
            raise ValueError("Cell evidence binding is required")
        observations[key] = cell
    rows = []
    for slot, binding in enumerate(protocol.slots):
        included, excluded, earned, possible, durations = [], [], Decimal(0), Decimal(0), []
        for key in sorted(k for k in planned if k[1] == slot):
            cell = observations.get(key)
            reason = "missing" if cell is None else cell["state"]
            if cell and cell["validity"] == "valid" and cell["state"] in (
                "completed", "model_failed"
            ):
                actual, maximum = criterion_totals(cell["criteria"], cell["expected_criteria"])
                if maximum != task_points[key[0]]:
                    raise ValueError("Task point total differs from frozen protocol")
                included.append({"task_revision_id": key[0], "repetition": key[2],
                                 "earned_points": text(actual), "possible_points": text(maximum),
                                 "evidence_sha256": cell["evidence_sha256"]})
                earned += actual
                possible += maximum
                duration = cell.get("duration_ms")
                if duration is not None:
                    if type(duration) is not int or duration < 0:
                        raise ValueError("Invalid measured duration")
                    durations.append(duration)
            else:
                excluded.append({"task_revision_id": key[0], "repetition": key[2],
                                 "reason": reason})
        complete = len(included) == 6
        rows.append({
            "slot": slot, "provider": binding.binding.provider,
            "model_id": binding.binding.model_id, "planned": 6,
            "scored": len(included), "completion": "complete" if complete else "incomplete",
            "primary": {"earned_points": text(earned), "possible_points": text(possible),
                        "percent": percent(earned, possible)} if complete else None,
            "diagnostic": {"earned_points": text(earned), "possible_points": text(possible),
                           "included": included, "excluded": excluded},
            "duration": {"median_ms": median(durations) if durations else None,
                         "samples": len(durations)},
            "cost": {"candidate_micro_usd": None, "judge_micro_usd": None,
                     "combined_micro_usd": None, "status": "unknown"},
        })
    projection = {"profile": "sme-scorecard-v1", "protocol_sha256": protocol.subject_sha256,
                  "origin": protocol.origin, "models": rows,
                  "complete": all(row["completion"] == "complete" for row in rows)}
    return projection, digest(projection)
