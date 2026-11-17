"""Exact Task2 US software contract, distinct from legacy marketing and079 scoring."""

from fractions import Fraction

VERSION = "marketing-task2-us-v1.1"
CASES = frozenset({"GT2-R01", "GT2-R02"})
ROLES = (
    "campaign_orchestrator",
    "intent_analyst",
    "performance_budget_analyst",
    "brief_delivery_coordinator",
    "campaign_policy_reviewer",
)
WIRE_ROLES = dict(
    zip(("orchestrator", "intent", "performance", "brief", "policy"), ROLES, strict=True)
)
GROUPS = {"A": 10, "B": 20, "C": 15, "D": 10, "E": 15, "F": 15, "G": 15}
CRITICAL = frozenset("CR-%02d" % n for n in range(1, 7))


def score(rubric, levels, critical_failures, *, outputs_or_correct_hold):
    """Grade explicit trusted evidence only; null levels never become inferred passes.

    This function consumes evaluator-produced levels, never actor compliance flags.
    Caller must keep rubric/controller/evidence inputs outside the agent boundary.
    """
    if rubric.get("formula") != "criterion weight * level / 4":
        raise ValueError("Exact Task2 scoring formula required")
    domains = rubric.get("domains", {})
    if {k: v.get("weight") for k, v in domains.items()} != GROUPS:
        raise ValueError("Exact Task2 group weights required")
    expected = {
        group + "." + name for group, value in domains.items() for name in value["criteria"]
    }
    if set(levels) != expected or (
        outputs_or_correct_hold is not None and type(outputs_or_correct_hold) is not bool
    ):
        raise ValueError(
            "Complete criterion identities and Boolean or unknown output gate required"
        )
    if not isinstance(critical_failures, list) or any(
        type(c) is not str or c not in CRITICAL for c in critical_failures
    ):
        raise ValueError("Known critical rule IDs required")
    totals, missing = {}, []
    for group, value in domains.items():
        if sum(value["criteria"].values()) != value["weight"]:
            raise ValueError("Criterion weights must preserve group total")
        totals[group] = Fraction(0)
        for name, weight in value["criteria"].items():
            key = group + "." + name
            level = levels[key]
            if level is None:
                missing.append(key)
            elif type(level) is not int or level not in range(5):
                raise ValueError("Task2 levels are0–4 or null, never5/2/0 conversion")
            else:
                totals[group] += Fraction(weight * level, 4)
    total = sum(totals.values(), Fraction(0))
    status = (
        "failed"
        if critical_failures or outputs_or_correct_hold is False
        else "unscored"
        if missing or outputs_or_correct_hold is None
        else "passed"
        if total >= 80 and totals["B"] >= 12
        else "failed"
    )

    def exact(n):
        return {"numerator": n.numerator, "denominator": n.denominator}

    return {
        "profile": VERSION,
        "scale": "zero_to_four",
        "total": exact(total),
        "groups": {k: exact(v) for k, v in totals.items()},
        "unscored_criteria": missing,
        "critical_failures": sorted(set(critical_failures)),
        "result": status,
        "output_gate": outputs_or_correct_hold,
        "human_legal_acceptance": "not_established",
        "model_performance": False,
        "paid_calls": False,
    }
