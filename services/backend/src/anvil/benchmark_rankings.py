"""Separate observed win rates and unregularized Bradley–Terry estimates.

MM update follows Hunter (2004), Annals of Statistics 32(1), 384–406:
https://doi.org/10.1214/aos/1079120141 . Ties contribute half an observation
to each direction (explicit fractional-win convention, not a Davidson model).
No pseudocounts repair disconnected/separated data into an invented ranking.
"""

import math
from collections import defaultdict
from decimal import Decimal


def paired_rankings(observations):
    """Observations are reviewed matched cells, keyed by immutable match identity.

    Each item: {match_key, model_key, percent}. One model per match is allowed;
    duplicates are rejected rather than selected by arrival/order/best score.
    """
    groups = defaultdict(dict)
    for row in observations:
        key, model = row["match_key"], row["model_key"]
        value = Decimal(str(row["percent"]))
        if not value.is_finite() or not 0 <= value <= 100:
            raise ValueError("Invalid matched score")
        if model in groups[key]:
            raise ValueError("Duplicate model observation in a matched cell")
        groups[key][model] = value
    wins, losses, ties, matches = (defaultdict(int) for _ in range(4))
    directed = defaultdict(lambda: defaultdict(float))
    pairs = 0
    for group in groups.values():
        models = sorted(group)
        for i, left in enumerate(models):
            for right in models[i + 1 :]:
                pairs += 1
                matches[left] += 1
                matches[right] += 1
                if group[left] == group[right]:
                    ties[left] += 1
                    ties[right] += 1
                    directed[left][right] += 0.5
                    directed[right][left] += 0.5
                else:
                    winner, loser = (left, right) if group[left] > group[right] else (right, left)
                    wins[winner] += 1
                    losses[loser] += 1
                    directed[winner][loser] += 1
    models = sorted(matches)
    rows = [
        {
            "model_key": model,
            "wins": wins[model],
            "losses": losses[model],
            "ties": ties[model],
            "matchups": matches[model],
            "percent": format(
                (Decimal(wins[model]) + Decimal(ties[model]) / 2) / matches[model] * 100,
                ".4f",
            ),
        }
        for model in models
    ]
    observed = {
        "status": "available" if pairs else "insufficient_data",
        "method": "wins_plus_half_ties_over_matchups",
        "pair_count": pairs,
        "rows": rows,
    }
    bt = {
        "status": "insufficient_data",
        "method": "bradley_terry_mm_fractional_ties_v1",
        "tie_policy": "one_half_win_each; not a fitted tie-probability model",
        "pair_count": pairs,
        "rows": [],
        "iterations": 0,
        "reason": "At least two models with matched reviewed observations are required",
    }
    if len(models) < 2:
        return {"observed_win_rate": observed, "bradley_terry": bt}
    if len(models) > 50:
        bt.update(
            status="cohort_too_broad",
            reason="Select at most 50 model bindings for the bounded Bradley–Terry fit",
        )
        return {"observed_win_rate": observed, "bradley_terry": bt}

    def reachable(start, reverse=False):
        found, pending = {start}, [start]
        while pending:
            node = pending.pop()
            for other in models:
                edge = directed[other][node] if reverse else directed[node][other]
                if edge > 0 and other not in found:
                    found.add(other)
                    pending.append(other)
        return found

    # Ford's strong-connection condition prevents a nonfinite boundary MLE.
    if any(len(reachable(models[0], reverse)) != len(models) for reverse in (False, True)):
        bt.update(
            status="not_estimable",
            reason="Win graph is disconnected or separated; no finite common maximum-likelihood ranking",
        )
        return {"observed_win_rate": observed, "bradley_terry": bt}
    strength = {model: 1 / len(models) for model in models}
    total_wins = {model: sum(directed[model].values()) for model in models}
    for iteration in range(1, 10001):
        updated = {}
        for model in models:
            denominator = sum(
                (directed[model][other] + directed[other][model])
                / (strength[model] + strength[other])
                for other in models
                if other != model
            )
            updated[model] = total_wins[model] / denominator
        scale = sum(updated.values())
        updated = {model: value / scale for model, value in updated.items()}
        delta = max(abs(math.log(updated[model] / strength[model])) for model in models)
        strength = updated
        if delta < 1e-10:
            ordered = sorted(models, key=lambda model: (-strength[model], model))
            bt.update(
                status="available",
                reason=None,
                iterations=iteration,
                rows=[
                    {
                        "model_key": model,
                        "relative_strength": format(strength[model], ".10f"),
                        "rank": 1
                        + sum(strength[other] > strength[model] + 1e-9 for other in models),
                    }
                    for model in ordered
                ],
            )
            break
    else:
        bt.update(
            status="not_converged", reason="Bounded fit did not converge; no ranking published"
        )
    return {"observed_win_rate": observed, "bradley_terry": bt}
