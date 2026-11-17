"""Compatibility is enforced before AI ranking or human method selection.

Names, prompts and AI explanations cannot grant an original-suite harness or
turn a business task into a coding benchmark. This module makes no model call.
"""

ORIGINAL_METHODS = {"gdpval-aa-2.1", "humaneval-plus", "swe-bench", "agents-last-exam"}
BUSINESS_METHODS = {
    "task-rubric-v1",
    "safety-observed-v1",
    "custom-gdpval-v1",
    "custom-agents-last-exam",
}


def check(task, method):
    key = method["id"]
    if key in ORIGINAL_METHODS:
        # Original-suite execution belongs to its separately qualified protocol,
        # never a generic Project/task plan. Even a coding title is insufficient.
        return {
            "compatible": False,
            "reason": "Use the original suite's exact licensed dataset and qualified protocol; this imported-task path cannot run that suite.",
        }
    if key not in BUSINESS_METHODS:
        return {
            "compatible": False,
            "reason": "No registered compatibility contract for this task and method version.",
        }
    if task.get("workflow") and method.get("kind") == "judge":
        return {
            "compatible": False,
            "reason": "This workflow requires an explicitly qualified trajectory judge; output-only judging is insufficient.",
        }
    return {
        "compatible": True,
        "reason": "Compatible method family; exact rubric, evidence, runtime and spending readiness remain separate checks.",
    }


def validate_ai_selection(tasks, methods, selected):
    """An AI may rank supplied compatible IDs, never create or authorize them."""
    if not tasks:
        raise ValueError("A versioned task is required before recommendation")
    by_id = {m["id"]: m for m in methods}
    if (
        not isinstance(selected, list)
        or not 1 <= len(selected) <= 100
        or any(type(k) is not str for k in selected)
        or len(selected) != len(set(selected))
    ):
        raise ValueError("Unique registered method IDs required")
    for key in selected:
        if (
            key not in by_id
            or by_id[key].get("status") != "ready"
            or by_id[key].get("runtime_qualified") is not True
            or by_id[key].get("revoked") is not False
            or any(not check(t, by_id[key])["compatible"] for t in tasks)
        ):
            raise ValueError("AI or user selected a method incompatible with the task")
    return [by_id[key] for key in selected]
