"""E-008 / D-047: read-only facts for the suite header and the project's Suites table.

Nothing here writes. It derives, from rows that already exist:
- the version picker (this suite's saved versions and its draft);
- this suite's environment against the project rule's environment, and why they differ;
- run size (cases + approved safety prompts per model and attempt);
- the suite's side of leaderboard eligibility (models are chosen at New run, so they are not judged here);
- what a draft changes from the saved version it is based on;
- a default case set name ("Set A", "Set B", ...) per sampling seed, in the order the suite first used each seed.
"""

from anvil.rlgym.catalog import selection

PLAN_FIELDS = {
    "sample_size": "sample size",
    "completeness_quotas": "completeness",
    "required_edges": "edge cases",
    "stratify_by": "split",
    "sampling_seed": "case set (seed)",
    "case_set_name": "case set name",
    "missing_policy": "when cases are short",
}


def _letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def case_set_names(c, ws, sv):
    """{seed: "Set X"} in the order this suite's versions first used each seed, plus the next free name."""
    rows = c.execute(
        """SELECT p.sampling_seed FROM suites.suite_versions v JOIN suites.data_plans p ON p.suite_version_id=v.id
           WHERE v.workspace_id=%s AND v.project_id=%s AND v.suite_id=%s ORDER BY v.created_at, v.id""",
        (ws, sv["project_id"], sv["suite_id"]),
    ).fetchall()
    names = {}
    for r in rows:
        if r["sampling_seed"] not in names:
            names[r["sampling_seed"]] = f"Set {_letter(len(names))}"
    return names, f"Set {_letter(len(names))}"


def default_case_set_name(c, ws, sv, seed):
    names, nxt = case_set_names(c, ws, sv)
    return names.get(seed, nxt)


def _bindings(c, ws, sv):
    from anvil.rlgym.projects.service import environment_lines
    from anvil.rlgym.suites import service

    rule_now = {line["alias"]: line for line in environment_lines(c, ws, sv["project_id"])}
    out = []
    for b in c.execute(
        "SELECT * FROM suites.suite_bindings WHERE suite_version_id=%s ORDER BY alias", (sv["id"],)
    ).fetchall():
        pick, _, reason, _ = service.resolve_binding(c, ws, sv["project_id"], b)
        project = rule_now.get(b["alias"]) or {}
        follows = b["rule_kind"] == "project_rule"
        if follows:
            why = "follows the project rule"
        elif b["source"] == "experiment":
            why = "pinned as an experiment" + (f": {b['reason']}" if b.get("reason") else "")
        else:
            why = "pinned" + (f": {b['reason']}" if b.get("reason") else "")
        out.append(
            {
                "alias": b["alias"],
                "binds_now": pick["id"] if pick else None,
                "unbound_reason": None if pick else reason,
                "rule_kind": b["rule_kind"],
                "source": b["source"],
                "follows_project_rule": follows,
                "why": why,
                "project_rule": project.get("rule"),
                "project_binds_now": project.get("version_id") if project.get("ok") else None,
                "differs": bool(pick)
                and project.get("ok")
                and pick["id"] != project.get("version_id"),
            }
        )
    return out


def _plan(c, sv_id):
    return c.execute(
        "SELECT * FROM suites.data_plans WHERE suite_version_id=%s", (sv_id,)
    ).fetchone()


def _ts(c, sv_id):
    ts = c.execute("SELECT * FROM suites.ts_plans WHERE suite_version_id=%s", (sv_id,)).fetchone()
    if not ts or not ts.get("enabled"):
        return {"enabled": False, "categories": 0, "prompts": 0}
    cats = c.execute(
        "SELECT count(*) n FROM suites.ts_categories WHERE suite_version_id=%s", (sv_id,)
    ).fetchone()["n"]
    prompts = c.execute(
        "SELECT count(*) n FROM suites.ts_prompts WHERE suite_version_id=%s AND approved",
        (sv_id,),
    ).fetchone()["n"]
    return {"enabled": True, "categories": cats, "prompts": prompts, "state": ts.get("state")}


def run_size(c, sv_id):
    plan = _plan(c, sv_id) or {}
    cases = plan.get("sample_size") or 0
    ts = _ts(c, sv_id)
    return {
        "cases": cases,
        "safety_prompts": ts["prompts"],
        "episodes_per_model_attempt": cases + (ts["prompts"] if cases else 0),
        "cost_note": "Projected cost depends on the models and attempts chosen at New run "
        "(episodes × each model's spend per episode); mock models cost $0.",
    }


def leaderboard(c, sv, bindings):
    from anvil.rlgym.scoring import safety

    reasons = []
    for b in bindings:
        if b["source"] == "experiment" and b["rule_kind"] == "pinned":
            reasons.append(f"{b['alias']} is pinned as an experiment")
        if not b["binds_now"]:
            reasons.append(f"{b['alias']} doesn't bind: {b['unbound_reason']}")
    env = None
    if bindings and bindings[0]["binds_now"]:
        env = c.execute(
            "SELECT * FROM catalog.environment_versions WHERE id=%s", (bindings[0]["binds_now"],)
        ).fetchone()
        if env and env.get("state") != "qualified":
            reasons.append(f"environment {env['id']} is {env['state']}, not qualified")
    cats = [
        r["key"]
        for r in c.execute(
            """SELECT DISTINCT k.key FROM suites.ts_categories k JOIN suites.ts_plans p ON p.suite_version_id=k.suite_version_id
               WHERE k.suite_version_id=%s AND p.enabled""",
            (sv["id"],),
        ).fetchall()
    ]
    bad = [why for k in cats for ok, why in [safety.can_grade(k, env)] if not ok]
    if bad:
        reasons.append("safety: " + "; ".join(bad))
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "note": "Suite side only. At New run, every agent model must also be live (not a mock).",
    }


def _saved_base(c, ws, sv):
    if sv.get("based_on"):
        row = c.execute(
            "SELECT * FROM suites.suite_versions WHERE workspace_id=%s AND id=%s AND state='saved'",
            (ws, sv["based_on"]),
        ).fetchone()
        if row:
            return row
    return c.execute(
        """SELECT * FROM suites.suite_versions WHERE workspace_id=%s AND project_id=%s AND suite_id=%s AND state='saved'
           ORDER BY version DESC LIMIT 1""",
        (ws, sv["project_id"], sv["suite_id"]),
    ).fetchone()


def _fmt(v):
    if isinstance(v, dict):
        return ", ".join(f"{k} {x}" for k, x in sorted(v.items())) or "none"
    if isinstance(v, list):
        return " × ".join(str(x) for x in v) or "none"
    return "none" if v in (None, "") else str(v)


def changes(c, ws, sv, bindings):
    """What a draft changes from the saved version it is based on (or the latest saved one)."""
    if sv["state"] != "draft":
        return None
    base = _saved_base(c, ws, sv)
    if not base:
        return {"from_version": None, "changes": ["New suite: no saved version yet"]}
    out = []
    old = {b["alias"]: b for b in _bindings(c, ws, base)}
    for b in bindings:
        o = old.get(b["alias"])
        if not o:
            continue
        was = f"{selection.short(o['binds_now'])} ({o['why']})"
        now = f"{selection.short(b['binds_now'])} ({b['why']})"
        if was != now:
            out.append(f"Environment: {was} → {now}")
    p0, p1 = _plan(c, base["id"]) or {}, _plan(c, sv["id"]) or {}
    for k, label in PLAN_FIELDS.items():
        if p0.get(k) != p1.get(k):
            out.append(f"Data plan {label}: {_fmt(p0.get(k))} → {_fmt(p1.get(k))}")
    t0, t1 = _ts(c, base["id"]), _ts(c, sv["id"])
    if t0 != t1:
        out.append(
            "Trust & Safety: "
            + (
                f"{t0['categories']} categories, {t0['prompts']} prompts"
                if t0["enabled"]
                else "off"
            )
            + " → "
            + (
                f"{t1['categories']} categories, {t1['prompts']} prompts"
                if t1["enabled"]
                else "off"
            )
        )
    n0, n1 = (
        c.execute(
            "SELECT count(*) n FROM suites.suite_tasks WHERE suite_version_id=%s", (x,)
        ).fetchone()["n"]
        for x in (base["id"], sv["id"])
    )
    if n0 != n1:
        out.append(f"Tasks: {n0} → {n1}")
    return {"from_version": base["version"], "from_id": base["id"], "changes": out}


def versions(c, ws, sv):
    return c.execute(
        """SELECT id, version, state, saved_at, created_at FROM suites.suite_versions
           WHERE workspace_id=%s AND project_id=%s AND suite_id=%s ORDER BY version DESC NULLS FIRST""",
        (ws, sv["project_id"], sv["suite_id"]),
    ).fetchall()


def header(c, ws, sv):
    b = _bindings(c, ws, sv)
    plan = _plan(c, sv["id"]) or {}
    names, nxt = case_set_names(c, ws, sv)
    return {
        "versions": versions(c, ws, sv),
        "environment": b,
        "run_size": run_size(c, sv["id"]),
        "leaderboard": leaderboard(c, sv, b),
        "changed": changes(c, ws, sv, b),
        "case_set": {
            "name": plan.get("case_set_name") or names.get(plan.get("sampling_seed"), nxt),
            "named": bool(plan.get("case_set_name")),
            "next_name": nxt,
        },
    }


def table_row(c, ws, sv):
    """One version's line for the project's Suites table."""
    b = _bindings(c, ws, sv)
    return {
        "environment": [
            {
                "alias": x["alias"],
                "binds_now": x["binds_now"],
                "label": (f"@{x['binds_now'].split('@')[-1]}" if x["binds_now"] else "unbound")
                + (" (project rule)" if x["follows_project_rule"] else " pinned"),
            }
            for x in b
        ],
        "run_size": run_size(c, sv["id"]),
        "leaderboard": leaderboard(c, sv, b),
    }
