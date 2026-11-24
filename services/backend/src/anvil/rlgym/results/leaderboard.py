"""Home leaderboard (SPEC 07.0; SCREENS 3.3): rank the models of a project's latest completed benchmark run in one frozen
cohort. A cohort is the suite version plus the environment version and the evaluator versions its latest scoring pass
used, so a custom suite, a new data plan, a new environment or a new evaluator version (or a re-score) starts its own
group; runs of different cohorts are never ranked together. Validation runs are not on the leaderboard.
D-033: only runs whose person ticked "Count this run on the leaderboard" at New run (frozen in the manifest) count.
"""

from anvil.rlgym.common import GymError, sha
from anvil.rlgym.results import report, sme
from anvil.rlgym.scoring import service as scoring

# Runs admitted before D-033 have no flag in their manifest, so they are not counted (no backfill).
ON_BOARD = "(m.manifest->'leaderboard')::boolean IS TRUE"


def _cohort(c, run, manifest):
    latest = scoring.latest_pass(c, run["id"])
    evaluators = sorted(
        (e["criterion_id"], e["configuration_id"], e["version"])
        for e in latest["evaluator_versions"]
    )
    key = sha(
        {
            "suite_version_id": str(run["suite_version_id"]),
            "environment": manifest["environment"]["version_id"],
            "evaluators": evaluators,
        }
    )[:16]
    suite = c.execute(
        "SELECT s.is_default FROM suites.suites s JOIN suites.suite_versions v USING (workspace_id, project_id, suite_id) WHERE v.id=%s",
        (run["suite_version_id"],),
    ).fetchone()
    return {
        "key": key,
        "suite": f"{manifest['suite']['name']} v{manifest['suite']['version']}",
        "custom_suite": not (suite and suite["is_default"]),
        "environment": manifest["environment"]["version_id"],
        "evaluators": len(evaluators),
        "pass": latest["pass"],
        "label": (
            f"{manifest['suite']['name']} v{manifest['suite']['version']}"
            + (" (custom suite)" if not (suite and suite["is_default"]) else "")
            + f" · {manifest['environment']['version_id'].replace('@', ' ')} · {len(evaluators)} evaluators"
            + (f" · re-scored (pass {latest['pass']})" if latest["pass"] > 1 else "")
        ),
    }


def leaderboard(c, ws, pid, cohort_key=None):
    project = c.execute(
        "SELECT * FROM projects.projects WHERE workspace_id=%s AND project_id=%s", (ws, pid)
    ).fetchone()
    if not project:
        raise GymError("NOT_FOUND", "Project not found")
    runs = c.execute(
        """SELECT r.*, m.manifest FROM runs.runs r JOIN runs.run_manifests m ON m.run_id=r.id
           WHERE r.workspace_id=%s AND r.project_id=%s AND r.state='completed' AND r.purpose='benchmark'
             AND """
        + ON_BOARD
        + """
           ORDER BY r.finished_at DESC NULLS LAST, r.created_at DESC""",
        (ws, pid),
    ).fetchall()
    empty = {
        "project_id": pid,
        "project_name": project["name"],
        "run": None,
        "rows": [],
        "cohorts": [],
        "empty": "No leaderboard runs yet. Tick 'Count this run on the leaderboard' when you start a run.",
    }
    if not runs:
        return empty
    cohorts = {}
    for run in runs:
        ch = _cohort(c, run, run["manifest"])
        if ch["key"] not in cohorts:
            cohorts[ch["key"]] = {**ch, "latest_run": run["id"], "runs": 0}
        cohorts[ch["key"]]["runs"] += 1
    key = cohort_key if cohort_key in cohorts else next(iter(cohorts))
    chosen = cohorts[key]
    run = next(r for r in runs if r["id"] == chosen["latest_run"])
    d = report.Data(c, ws, run["id"])
    cards = {card["system_id"]: card for card in report.score_cards(d)}
    reviewed = sme.reviewed_for_run(c, run["id"])
    rows = []
    for m in d.models:
        mine = [e for e in d.cases if e["system_id"] == m["system_id"]]
        executed = sum(1 for e in mine if e["score"] is not None)
        unresolved = sum(
            1
            for e in mine
            if e["score"] is None
            or e["state"] in ("errored", "timed_out")
            or (e["blocked_reasons"] or [])
        )
        card = cards[m["system_id"]]
        r = reviewed.get(m["system_id"])
        score = float(r["reviewed"]) if r and r["reviewed"] is not None else card["mean"]
        rows.append(
            {
                "system_id": m["system_id"],
                "model": f"{m['name']} v{m['version']}",
                "score": score,
                "automated": card["mean"],
                "reviewed": r is not None,
                "excluded": r["excluded"] if r else 0,
                "likely_range": card["likely_range"],
                "gate": card["gate"],
                "gate_notes": card["gate_notes"],
                "executed_cells": executed,
                "unresolved": unresolved,
            }
        )
    ranked = sorted((r for r in rows if r["score"] is not None), key=lambda r: -r["score"])
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    for r in rows:
        r.setdefault("rank", None)
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0))
    return {
        "project_id": pid,
        "project_name": project["name"],
        "run": {"id": run["id"], "name": run["name"], "finished_at": run["finished_at"]},
        "cohort": chosen,
        "cohorts": list(cohorts.values()),
        "rows": rows,
        "note": d.manifest["note"],
        "gate_note": "Gates are shown beside the rank: a FAILED gate fails the model whatever its score.",
    }
