"""Bounded structured-decision software episode; no models, network or private grader."""

from copy import deepcopy
from fractions import Fraction
from uuid import uuid4

from anvil.praxis_generic_contract import canonical, digest, schema_errors, weight_bps


class StructuredEpisode:
    def __init__(self, execution, actor):
        if execution.environment.id != "structured-decision-v1" or execution.tools:
            raise ValueError("This installed episode supports structured decisions without tools")
        self.execution = execution
        self._actor = deepcopy(actor)
        self.history = []
        self.generation = -1
        self.reset()

    def reset(self):
        if self.generation >= 0:
            self.history.append(self.capture())
        self.generation += 1
        self.episode_id = str(uuid4())
        self.final = None
        self.events = []
        return {
            "episode_id": self.episode_id,
            "generation": self.generation,
            "actor": deepcopy(self._actor),
        }

    def submit(self, value, *, episode_id, generation):
        if episode_id != self.episode_id or generation != self.generation or self.final is not None:
            raise ValueError("Wrong or completed episode generation")
        if len(self.events) >= self.execution.limits.transitions:
            raise ValueError("Episode transition limit reached")
        if (
            schema_errors(value, self.execution.output_schema)
            or len(canonical(value)) > self.execution.limits.output_bytes
        ):
            self.events.append({"action": "submit", "status": "rejected"})
            raise ValueError("Final output violates declared contract")
        self.final = deepcopy(value)
        self.events.append(
            {"action": "submit", "status": "accepted", "output_sha256": digest(value)}
        )
        return {"status": "completed", "capture_sha256": digest(self.capture())}

    def capture(self):
        return {
            "episode_id": self.episode_id,
            "generation": self.generation,
            "actor_sha256": digest(self._actor),
            "output": deepcopy(self.final),
            "events": deepcopy(self.events),
            "origin": "software_contract_not_model",
            "paid_calls": False,
        }


def reference_anchor(output, field, reference, partial_values=()):
    if field not in output:
        return None
    value = canonical(output[field])
    if value == canonical(reference):
        return 5
    return 2 if value in [canonical(v) for v in partial_values] else 0


def evaluate_output(criteria, output):
    """Trusted grader input, never mounted/passed into StructuredEpisode."""
    if not isinstance(output, dict):
        raise ValueError("Captured output object required")
    grades = []
    for criterion in criteria:
        if (criterion.get("evaluatorKind"), criterion.get("evaluatorVersion")) != (
            "output-reference-v1",
            "1",
        ):
            raise ValueError("Unsupported evaluator ID/version")
        grades.append(
            {
                "id": criterion["id"],
                "weight_bps": weight_bps(criterion["weight"]),
                "critical": criterion["critical"],
                "anchor": reference_anchor(
                    output,
                    criterion["outputField"],
                    criterion["expectedValue"],
                    criterion.get("partialValues", []),
                ),
            }
        )
    return {
        "criteria": grades,
        "score": weighted_score(grades),
        "origin": "software_reference_grader",
        "model_performance": False,
        "paid_calls": False,
    }


def weighted_score(criteria):
    """No normalization or invented pass threshold; critical failures separate."""
    if (
        any(
            type(c["weight_bps"]) is not int
            or c["weight_bps"] <= 0
            or c["anchor"] is not None
            and (type(c["anchor"]) is not int or c["anchor"] not in (0, 2, 5))
            for c in criteria
        )
        or sum(c["weight_bps"] for c in criteria) != 10000
    ):
        raise ValueError("Weights must total10000 basis points")
    earned = sum(
        (Fraction(c["weight_bps"] * c["anchor"], 500) for c in criteria if c["anchor"] is not None),
        Fraction(0),
    )
    unknown = sum(c["weight_bps"] for c in criteria if c["anchor"] is None)
    return {
        "earned_points": {"numerator": earned.numerator, "denominator": earned.denominator},
        "maximum_points": 100,
        "unscored_weight_bps": unknown,
        "critical_failures": [c["id"] for c in criteria if c["critical"] and c["anchor"] == 0],
        "overall_result": "not_evaluated" if unknown else "graded_no_pass_threshold",
    }


def conformance(execution):
    """Run only the local software adapter's synthetic boundary probes, not a Run."""
    actor = {"synthetic_probe": "isolated"}
    first, second = StructuredEpisode(execution, actor), StructuredEpisode(execution, actor)
    observed = first.reset()
    observed["actor"]["synthetic_probe"] = "mutated"
    first.submit(
        execution.conformance_output,
        episode_id=observed["episode_id"],
        generation=observed["generation"],
    )
    sealed = first.capture()
    next_state = first.reset()
    isolation = second.capture()["output"] is None and next_state["actor"] == actor
    retained = sealed in first.history
    denied = False
    try:
        first.submit(
            execution.conformance_output,
            episode_id=observed["episode_id"],
            generation=observed["generation"],
        )
    except ValueError:
        denied = True
    anchors = [
        reference_anchor({"value": "full"}, "value", "full", ["partial"]),
        reference_anchor({"value": "partial"}, "value", "full", ["partial"]),
        reference_anchor({"value": "wrong"}, "value", "full"),
        reference_anchor({}, "value", "full"),
    ]
    checks = {
        "reset_isolation": isolation,
        "prior_capture_retained": retained,
        "stale_generation_denied": denied,
        "anchors_5_2_0_unknown": anchors == [5, 2, 0, None],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "origin": "synthetic_software_conformance",
        "model_performance": False,
        "paid_calls": False,
    }
