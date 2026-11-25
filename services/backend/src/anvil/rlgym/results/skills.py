"""G3 (E-011 §2-§3): the skill profile of a run; G5: two runs compared by skill (golden KYC v8 vs KYC Judgment v1).

A criterion's skill is the template's tag (C4), else the task's S7 tag, else E-011 §4's first-pass mapping for golden
KYC v8, labelled provisional until the owner confirms it. Reasoning and decisioning count only on discriminating
cases: those the suite version's G4 lookup run decided wrongly. With fewer than MIN_DISCRIMINATING such episodes per
model the profile says "not measured", never a number. Read-only: a report drill-down, nothing written.
"""

import statistics

SKILLS = ("tool_calling", "instruction_following", "reasoning", "decisioning", "safety")
DISCRIMINATING_ONLY = ("reasoning", "decisioning")
MIN_DISCRIMINATING = 10
# E-011 §4, first pass (owner confirmation pending, E-011 §6 Q1).
PROVISIONAL = {
    "identification_verification": "instruction_following",
    "screening": "tool_calling",
    "decision": "decisioning",
    "next_action": "decisioning",
    "evidence": "reasoning",
}


def skill_of(criterion_id, evaluator, s7_skills):
    if (evaluator or {}).get("skill"):
        return evaluator["skill"], "template"
    if (s7_skills or {}).get(criterion_id):
        return s7_skills[criterion_id], "task S7"
    if criterion_id in PROVISIONAL:
        return PROVISIONAL[criterion_id], "provisional (E-011 §4)"
    return None, None


def profile(rows, discriminating):
    """rows: {system_id, case_id, criterion_id, skill, fraction (0-1)}; discriminating: the case ids the lookup got
    wrong, or None when no lookup run exists. → {system_id: {skill: {value, n, measured, note?}}}."""
    out = {}
    for r in rows:
        if not r.get("skill") or r.get("fraction") is None:
            continue
        out.setdefault(r["system_id"], {}).setdefault(r["skill"], []).append(r)
    result = {}
    for sid, by_skill in out.items():
        result[sid] = {}
        for skill, rs in by_skill.items():
            if skill in DISCRIMINATING_ONLY:
                if discriminating is None:
                    result[sid][skill] = {
                        "value": None,
                        "n": 0,
                        "measured": False,
                        "note": "not measured: no lookup baseline run for this suite version (G-01)",
                    }
                    continue
                rs = [r for r in rs if r["case_id"] in discriminating]
                cases = {r["case_id"] for r in rs}
                if len(cases) < MIN_DISCRIMINATING:
                    result[sid][skill] = {
                        "value": None,
                        "n": len(cases),
                        "measured": False,
                        "note": f"not measured: too few discriminating cases ({len(cases)} of the "
                        f"{MIN_DISCRIMINATING} needed)",
                    }
                    continue
            result[sid][skill] = {
                "value": round(100 * statistics.fmean(r["fraction"] for r in rs), 1),
                "n": len({r["case_id"] for r in rs}),
                "measured": True,
            }
    return result


def compare(first, second):
    """Two profiles keyed by "system_id@version"; the models in both, skill by skill, with the change."""
    both = sorted(set(first) & set(second))
    by_model = {}
    for m in both:
        by_model[m] = {}
        for skill in SKILLS:
            a, b = first[m].get(skill), second[m].get(skill)
            if not a and not b:
                continue
            delta = (
                round(b["value"] - a["value"], 1)
                if a and b and a.get("measured") and b.get("measured")
                else None
            )
            by_model[m][skill] = {"first": a, "second": b, "delta": delta}
    return {
        "models": both,
        "only_in_first": sorted(set(first) - set(second)),
        "only_in_second": sorted(set(second) - set(first)),
        "by_model": by_model,
    }


def run_profile(d):
    """The skill profile of one run (report Data), keyed by "system_id@version"."""
    from anvil.rlgym.scoring import service as scoring
    from anvil.rlgym.verification import lookup

    tasks = {(t.get("task_id"), t.get("revision")): t for t in d.manifest.get("tasks") or []}
    versions = {m["system_id"]: m["version"] for m in d.models}
    episodes = {e["id"]: e for e in d.cases}
    rows, sources = [], {}
    for r in d.receipts:
        e = episodes.get(r["episode_id"])
        if not e or r["verdict"] not in scoring.SCORABLE:
            continue
        t = tasks.get((e["task_id"], e["task_revision"])) or {}
        skill, source = skill_of(
            r["criterion_id"],
            d.evaluators.get(r["criterion_id"]),
            ((t.get("scoring") or {}).get("skills")),
        )
        if skill:
            sources[r["criterion_id"]] = {"skill": skill, "source": source}
        rows.append(
            {
                "system_id": f"{e['system_id']}@{versions.get(e['system_id'])}",
                "case_id": e["case_id"],
                "criterion_id": r["criterion_id"],
                "skill": skill,
                "fraction": float(r["points"]) if r["points"] is not None else None,
            }
        )
    lk = lookup.latest(d.c, d.ws, d.run["suite_version_id"])
    discriminating = (
        {x["case_id"] for x in lk.get("cases") or [] if x.get("decision_right") is False}
        if lk
        else None
    )
    return {
        "run_id": d.run["id"],
        "template": d.manifest.get("template", {}).get("name"),
        "models": {f"{m['system_id']}@{m['version']}": m.get("name") for m in d.models},
        "criteria": sources,
        "lookup_run": lk and lk["id"],
        "discriminating_cases": None if discriminating is None else len(discriminating),
        "profile": profile(rows, discriminating),
        "note": (
            "Reasoning and decisioning count only on cases the no-AI lookup gets wrong (E-011 §3), and need at "
            f"least {MIN_DISCRIMINATING} per model. Golden KYC v8 criteria use E-011 §4's first-pass mapping "
            "(provisional)."
        ),
    }


def compare_runs(c, ws, run_a, run_b):
    from anvil.rlgym.results import report

    a = run_profile(report.Data(c, ws, run_a))
    b = run_profile(report.Data(c, ws, run_b))
    return {"first": a, "second": b, **compare(a["profile"], b["profile"])}
