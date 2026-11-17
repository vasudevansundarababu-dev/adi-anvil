"""Pinned-runtime worker for bounded library calls; no uploaded code or model providers.

Run with the independently locked engine interpreter. This is an integration
building block, not execution authority or a claim of Run/UI availability.
"""

import asyncio
import json
import math
import re
import sys
from importlib.metadata import version


def nemo(value):
    from nemoguardrails import RailsConfig
    from nemoguardrails.library.regex.actions import detect_regex_pattern

    text, forbidden = value.get("text"), value.get("forbidden_literals")
    if text is None:
        return {"outcome": "unknown"}
    if not isinstance(text, str) or len(text) > 8192:
        raise ValueError("Bounded captured text required")
    if (
        not isinstance(forbidden, list)
        or not 1 <= len(forbidden) <= 30
        or any(not isinstance(v, str) or not 1 <= len(v) <= 100 for v in forbidden)
    ):
        raise ValueError("Bounded literal policy required")
    # Literal-only patterns prevent arbitrary regular-expression complexity/code.
    config = RailsConfig.from_content(
        config={
            "models": [],
            "rails": {
                "config": {
                    "regex_detection": {"output": {"patterns": [re.escape(v) for v in forbidden]}}
                }
            },
        }
    )
    outcome = asyncio.run(detect_regex_pattern(source="output", text=text, config=config))
    if outcome.failed:
        raise ValueError("NeMo rail error")
    return {
        "outcome": {"allow": "pass", "block": "fail"}[outcome.decision.value],
        "capability": "deterministic_literal_detection",
        "runtime_version": version("nemoguardrails"),
        "provider_calls": 0,
    }


def trulens(value):
    from trulens.feedback.groundtruth import GroundTruthAggregator

    labels, scores = value.get("labels"), value.get("scores")
    if labels is None or scores is None:
        return {"state": "unknown", "metric": "precision", "value": None}
    if (
        not isinstance(labels, list)
        or not isinstance(scores, list)
        or not 1 <= len(labels) == len(scores) <= 1000
        or any(type(v) is not int or v not in (0, 1) for v in labels)
        or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in scores)
    ):
        raise ValueError("Matched bounded binary labels and finite scores required")
    result = float(GroundTruthAggregator(true_labels=labels).precision(scores))
    return {
        "state": "completed" if math.isfinite(result) else "unknown",
        "metric": "precision",
        "value": result if math.isfinite(result) else None,
        "capability": "deterministic_calibration_metric",
        "custom_policy_verdict": False,
        "runtime_version": version("trulens-feedback"),
        "provider_calls": 0,
    }


def main():
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError("Worker input exceeds limit")
    value = json.loads(raw)
    engine = sys.argv[1]
    result = {"nemo": nemo, "trulens": trulens}[engine](value)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
