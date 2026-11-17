"""Private logical-effect checks, separate from invocation custody and prose.

Reviewed argument/state subsets are expected facts. Runtime IDs and whole-body
hashes establish custody; a reference is never copied from an observed effect.
This does not evaluate meaning, optional workflow quality or internal reasoning.
"""

import json
import re
from collections import deque

from anvil.db import digest

METHOD = "anvil-logical-effect-subset-v2"
TARGETS = {
    "K.PERSIST",
    *("M.TOOL." + role for role in ("Intent", "Performance", "Orchestrator", "Creative", "Policy")),
}


def _bounded(value):
    if len(json.dumps(value, allow_nan=False).encode()) > 262144:
        raise ValueError("Effect projection capacity exceeded")
    pending, leaves = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        if depth > 12:
            raise ValueError("Effect projection depth exceeded")
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("JSON object keys required")
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            if len(item) > 1000:
                raise ValueError("Effect array capacity exceeded")
            pending.extend((child, depth + 1) for child in item)
        elif item is None or type(item) in (str, int, float, bool):
            leaves += 1
        else:
            raise ValueError("JSON effect facts required")
    return leaves


def _maximum(edges, tick):
    """Maximum matching avoids order-dependent false failures for overlapping facts."""
    owners, assigned = {}, {}
    for start in range(len(edges)):
        queue, visited, predecessor = deque([start]), {start}, {}
        end = None
        while queue and end is None:
            wanted = queue.popleft()
            for observed in edges[wanted]:
                tick()
                if observed in predecessor:
                    continue
                predecessor[observed] = wanted
                if observed not in owners:
                    end = observed
                    break
                prior = owners[observed]
                if prior not in visited:
                    visited.add(prior)
                    queue.append(prior)
        while end is not None:
            wanted = predecessor[end]
            previous = assigned.get(wanted)
            owners[end], assigned[wanted] = wanted, end
            end = previous
    return len(assigned)


def evaluate(target, context, actual, reference):
    base = {
        "schema_version": "anvil.diagnostic-measure.v1",
        "target": target,
        "official_points": 0,
        "model_performance": False,
        "ran": bool(actual.get("execution_receipt_sha256")),
        "comparison_contract": {
            "method": METHOD,
            "facts": "reviewed_arguments_and_persisted_state_subsets",
            "arrays": "order_independent_exact_cardinality",
            "invocation_ids_and_whole_body_hashes": "custody_only_not_expected_equality",
            "semantic_judgment": False,
        },
    }

    def unknown(reason, owner="reference_or_evidence_owner"):
        return base | {
            "status": "unscored",
            "measurements": {},
            "unscored_reason": reason,
            "owner": owner,
        }

    if any(
        not isinstance(actual.get(key), str) or re.fullmatch(r"[a-f0-9]{64}", actual[key]) is None
        for key in ("execution_receipt_sha256", "source_evidence_sha256")
    ):
        return unknown("logical_effect_source_custody_required", "anvil")
    if reference.get("comparison_mode") != METHOD:
        return unknown("reviewed_logical_effect_reference_required")
    obligations = reference.get("obligations")
    if not isinstance(obligations, list) or not 1 <= len(obligations) <= 200:
        return unknown("bounded_logical_effect_obligations_required")
    try:
        ids = []
        for obligation in obligations:
            if not isinstance(obligation, dict) or set(obligation) - {
                "id",
                "operation",
                "subject_id",
                "arguments_match",
                "persisted_match",
            }:
                raise ValueError
            for field in ("id", "operation"):
                if (
                    not isinstance(obligation.get(field), str)
                    or not 1 <= len(obligation[field]) <= 200
                ):
                    raise ValueError
            if "subject_id" in obligation and (
                not isinstance(obligation["subject_id"], str)
                or not 1 <= len(obligation["subject_id"]) <= 200
            ):
                raise ValueError
            if target == "K.PERSIST" and "subject_id" not in obligation:
                raise ValueError
            for field in ("arguments_match", "persisted_match"):
                pattern = obligation.get(field)
                if field == "arguments_match" and pattern == {}:
                    continue  # Exact empty API arguments, never a wildcard.
                if not isinstance(pattern, dict) or not pattern or not _bounded(pattern):
                    raise ValueError
            ids.append(obligation["id"])
        if len(set(ids)) != len(ids):
            raise ValueError
    except (ValueError, TypeError, RecursionError):
        return unknown("reviewed_logical_effect_predicates_required")
    invocations = actual.get("observed_invocations")
    if (
        actual.get("normalizer_available") is not True
        or not isinstance(invocations, list)
        or len(invocations) > 1000
    ):
        return unknown("logical_effect_capture_required", "anvil")
    try:
        identifiers = []
        for invocation in invocations:
            for field in ("invocation_id", "operation", "subject_id", "role"):
                if (
                    not isinstance(invocation.get(field), str)
                    or not 1 <= len(invocation[field]) <= 200
                ):
                    raise ValueError
            if (
                invocation["role"] != context["role"]
                or invocation.get("effect_verified") is not True
            ):
                raise ValueError
            for field in ("arguments", "response", "persisted_state"):
                view = invocation[field]
                _bounded(view)
                if digest(view) != invocation[field + "_sha256"]:
                    raise ValueError
            identifiers.append(invocation["invocation_id"])
        if len(set(identifiers)) != len(identifiers):
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return unknown("verified_invocation_and_persisted_effect_custody_required", "anvil")
    remaining = 200000

    def tick():
        nonlocal remaining
        remaining -= 1
        if remaining < 0:
            raise ValueError("Logical comparison work capacity exceeded")

    def matches(pattern, value):
        tick()
        if type(pattern) is not type(value):
            return False
        if isinstance(pattern, dict):
            return all(
                key in value and matches(child, value[key]) for key, child in pattern.items()
            )
        if isinstance(pattern, list):
            if len(pattern) != len(value):
                return False
            edges = [
                [i for i, child in enumerate(value) if matches(expected, child)]
                for expected in pattern
            ]
            return _maximum(edges, tick) == len(pattern)
        return pattern == value

    try:
        edges = [
            [
                i
                for i, invocation in enumerate(invocations)
                if invocation["operation"] == obligation["operation"]
                and (
                    "subject_id" not in obligation
                    or invocation["subject_id"] == obligation["subject_id"]
                )
                and (
                    invocation["arguments"] == {}
                    if obligation["arguments_match"] == {}
                    else matches(obligation["arguments_match"], invocation["arguments"])
                )
                and matches(obligation["persisted_match"], invocation["persisted_state"])
            ]
            for obligation in obligations
        ]
        correct = _maximum(edges, tick)
    except ValueError:
        return unknown("logical_effect_comparison_capacity_exceeded", "anvil")
    eligible, reported = len(obligations), len(invocations)
    return base | {
        "status": "pass" if correct == eligible == reported else "partial" if correct else "fail",
        "measurements": {
            key: {"kind": "ratio", "numerator": correct, "denominator": count}
            for key, count in (("precision", reported), ("recall", eligible))
            if count
        },
        "counts": {
            "eligible": eligible,
            "reported": reported,
            "correct": correct,
            "invented_or_duplicate": reported - correct,
            "missed": eligible - correct,
        },
    }
