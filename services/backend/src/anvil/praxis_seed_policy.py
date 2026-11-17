"""Explicit proposed-policy constraint bridge, not general policy interpretation.

Only a published rule's exact policy-constraint counterpart is evaluated. Unknown
is retained for absent mappings/fields. Rubric grading remains unchanged. A true
output boolean is never evidence of a real manager approval or source review.
"""

from anvil.praxis_contract import matches


def evaluate(task, rules, output):
    constraints = {constraint.id: constraint for constraint in task.constraints}
    results = []
    seen = set()
    for rule in rules:
        identifier = rule["rule_id"]
        if not identifier.startswith("R-") or identifier in seen:
            raise ValueError("Unique published rule IDs required")
        seen.add(identifier)
        constraint = constraints.get("policy-" + identifier[2:])
        profile = (rule.get("evaluator") or {}).get("profile_ref", {})
        supported = (rule.get("evaluator") or {}).get(
            "type"
        ) == "task_constraint_binding" and profile == {
            "evaluator_id": "anvil.task-constraint-binding",
            "version": "1.0.0-proposed",
        }
        outcome, reason = "unknown", "needs_evaluator"
        if supported and constraint:
            if not isinstance(output, dict) or constraint.binding.field not in output:
                reason = "missing_output_evidence"
            else:
                outcome = "pass" if matches(constraint.binding, output) else "fail"
                reason = "exact_task_constraint"
        results.append(
            {
                "rule_id": identifier,
                "constraint_id": constraint.id if constraint and supported else None,
                "outcome": outcome,
                "reason": reason,
                "basis": "submitted_task_output_only",
                "human_approval_verified": False,
            }
        )
    return results
