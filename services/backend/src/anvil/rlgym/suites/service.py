"""Suites (SPEC 07.5, 07.5b; SCREENS 3.11-3.16).

A suite = template activation + bindings + data plan (+ Trust & Safety plan) + all ready tasks of the project. Edits
happen on a draft; Save gives version N+1 and a suite_sha256, after which the version never changes. The data plan
is checked against the case catalog of the environment version the bindings select now; a run never creates data.
Suggestions here are rule-based (no model is approved locally) and say so.
"""

import re
import uuid

from psycopg.types.json import Jsonb

from anvil.rlgym.catalog import inbox, selection
from anvil.rlgym.common import GymError, audit, emit, require, sha
from anvil.rlgym.suites import header, trust_safety

SLUG = re.compile(r"[^a-z0-9-]+")
DEFAULT_PLAN = {
    "sample_size": 40,
    "stratify_by": ["application_type"],
    "completeness_quotas": {"complete": 70, "incomplete": 30},
    "required_edges": {},
    "sampling_seed": 20261121,
    "missing_policy": "block",
    "case_set_name": None,
}
# E-005 §3: the properties a sample can be split by (one or two). application_type is the default and keeps the
# original cells; the others are read from the bound environment's case rows.
STRATA = ("application_type", "completeness", "edge_case", "edge_family", "product")


def _cases_for(cat, sel):
    """Catalog cases a task's selector can take: its type at its completeness, or at either completeness when the
    selector names none (ADI Forge's exports name only the application type)."""
    cells = cat.get("cells", {})
    if sel.get("completeness"):
        return cells.get(f"{sel['application_type']}|{sel['completeness']}", 0)
    return sum(n for k, n in cells.items() if k.split("|", 1)[0] == sel["application_type"])


def _recipe_text(recipe):
    """An edge case's recipe as text for a data request description (plain English or structured conditions)."""
    if not recipe or isinstance(recipe, str):
        return recipe
    import json

    return "Cases matching: " + json.dumps(recipe, separators=(",", ":"))[:1500]


def _edge_cases(c, ws, pid):
    """The S4 edge cases of the project's activated template (2.12), by tag."""
    row = c.execute(
        """SELECT a.edge_cases FROM projects.projects p JOIN catalog.template_activations a
           ON a.workspace_id=p.workspace_id AND a.template_id=p.template_id AND a.version=p.template_version
           WHERE p.workspace_id=%s AND p.project_id=%s""",
        (ws, pid),
    ).fetchone()
    return {e["tag"]: e for e in ((row or {}).get("edge_cases") or [])}


def _project(c, ws, pid):
    row = c.execute(
        "SELECT * FROM projects.projects WHERE workspace_id=%s AND project_id=%s", (ws, pid)
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "Project not found")
    return row


def _sv(c, ws, sv_id):
    try:
        uuid.UUID(str(sv_id))
    except ValueError:
        raise GymError("NOT_FOUND", "Suite version not found") from None
    row = c.execute(
        "SELECT * FROM suites.suite_versions WHERE workspace_id=%s AND id=%s", (ws, sv_id)
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "Suite version not found")
    return row


def _draft(c, ws, sv_id):
    row = _sv(c, ws, sv_id)
    require(row["state"] == "draft", "CONFLICT", "A saved suite version is final; create a draft")
    return row


# --- bindings ----------------------------------------------------------------------------------------------------


def _project_rules(c, ws, pid):
    return c.execute(
        "SELECT * FROM projects.selection_rules WHERE workspace_id=%s AND project_id=%s AND valid_to IS NULL",
        (ws, pid),
    ).fetchall()


def resolve_binding(c, ws, pid, b):
    rule = next(r for r in _project_rules(c, ws, pid) if r["alias"] == b["alias"])
    if b["rule_kind"] == "project_rule":
        effective = rule
    else:
        effective = {
            "contract_id": rule["contract_id"],
            "kind": b["rule_kind"],
            "pinned_version_id": b.get("pinned_version_id"),
            "seed_family": b.get("seed_family"),
        }
    pick, code, reason = selection.resolve_environment(c, effective)
    return pick, code, reason, effective


def resolve_criterion(c, ws, pid, b):
    if b["rule_kind"] == "project_rule":
        rule = c.execute(
            """SELECT * FROM projects.evaluator_selection_rules WHERE workspace_id=%s AND project_id=%s AND criterion_id=%s
                            AND valid_to IS NULL""",
            (ws, pid, b["criterion_id"]),
        ).fetchone()
    else:
        rule = {
            "configuration_id": b["configuration_id"],
            "kind": b["rule_kind"],
            "pinned_version": b.get("pinned_version"),
        }
    return selection.resolve_evaluator(c, ws, rule)


def _bound_env(c, ws, pid, sv_id):
    bindings = c.execute(
        "SELECT * FROM suites.suite_bindings WHERE suite_version_id=%s ORDER BY alias", (sv_id,)
    ).fetchall()
    if not bindings:
        return None
    pick, _, _, _ = resolve_binding(c, ws, pid, bindings[0])
    return pick


# --- data plan ---------------------------------------------------------------------------------------------------


def validate_plan(plan):
    require(
        isinstance(plan.get("sample_size"), int) and plan["sample_size"] > 0,
        "VALIDATION_FAILED",
        "Sample size must be a positive whole number",
        field="sample_size",
    )
    quotas = plan.get("completeness_quotas") or {}
    require(
        quotas and all(isinstance(v, (int, float)) and v >= 0 for v in quotas.values()),
        "VALIDATION_FAILED",
        "Completeness quotas are percentages",
        field="completeness_quotas",
    )
    edges = plan.get("required_edges") or {}
    require(
        all(isinstance(v, int) and v >= 0 for v in edges.values()),
        "VALIDATION_FAILED",
        "Edge-case minimums are whole numbers",
        field="required_edges",
    )
    require(
        plan.get("missing_policy", "block") in ("block", "use_available"),
        "VALIDATION_FAILED",
        "Unknown missing policy",
    )
    by = plan.get("stratify_by") or ["application_type"]
    require(
        isinstance(by, list)
        and 1 <= len(by) <= 2
        and len(set(by)) == len(by)
        and all(p in STRATA for p in by),
        "VALIDATION_FAILED",
        f"Split the sample by one or two of: {', '.join(STRATA)}",
        field="stratify_by",
    )
    name = plan.get("case_set_name")
    require(
        name is None or (isinstance(name, str) and 1 <= len(name.strip()) <= 80),
        "VALIDATION_FAILED",
        "A case set name has 1 to 80 characters",
        field="case_set_name",
    )


def case_value(case, prop):
    """A case's value for a split property (E-005): its own field, its first edge-case tag or family ("none" when it
    has none), or a fact (product)."""
    if prop in ("application_type", "completeness"):
        return case.get(prop)
    if prop == "edge_case":
        return (case.get("edge_cases") or ["none"])[0]
    if prop == "edge_family":
        return (case.get("edge_families") or ["none"])[0]
    return (case.get("facts") or {}).get(prop) or "unknown"


def _split_cells(plan, rows, task_types):
    """Cells for a split other than the default: equal shares over the value combinations the cases have (only the
    application types the suite has tasks for), each split by the completeness quotas unless completeness is itself
    a split property. Keys are the values joined by "|"."""
    by = plan["stratify_by"]
    rows = [r for r in rows if not task_types or r.get("application_type") in task_types]
    combos = {}
    for r in rows:
        combos.setdefault(tuple(case_value(r, p) for p in by), []).append(r)
    cells = []
    if not combos:
        return cells
    keys = sorted(combos)
    base, extra = divmod(plan["sample_size"], len(keys))
    split_completeness = "completeness" not in by
    for i, combo in enumerate(keys):
        share = base + (1 if i < extra else 0)
        dims = dict(zip(by, combo, strict=True))
        if not split_completeness:
            cells.append(
                {
                    "cell_key": "|".join(map(str, combo)),
                    "dimension_values": dims,
                    "quota_kind": "share",
                    "quota_value": share,
                    "quota": share,
                    "available": len(combos[combo]),
                }
            )
            continue
        raw = {k: share * pct / 100 for k, pct in plan["completeness_quotas"].items()}
        split = {k: int(v) for k, v in raw.items()}
        left = share - sum(split.values()) if sum(raw.values()) else 0
        for k in sorted(raw, key=lambda k: (-(raw[k] - split[k]), list(raw).index(k)))[
            : max(left, 0)
        ]:
            split[k] += 1
        for completeness, pct in plan["completeness_quotas"].items():
            have = sum(1 for r in combos[combo] if r.get("completeness") == completeness)
            cells.append(
                {
                    "cell_key": "|".join(map(str, (*combo, completeness))),
                    "dimension_values": {**dims, "completeness": completeness},
                    "quota_kind": "percent",
                    "quota_value": pct,
                    "quota": split[completeness],
                    "available": have,
                }
            )
    return cells


def compute_cells(plan, catalog, task_types=None):
    """Quota cells. The sample is spread over the application types the suite has tasks for (`task_types`), so every
    sampled case can become an episode; with no tasks known, over every type in the catalog. E-005: a split by other
    properties builds its cells from the environment's case rows (`catalog["_rows"]`)."""
    if (plan.get("stratify_by") or ["application_type"]) != ["application_type"]:
        cells = _split_cells(plan, (catalog or {}).get("_rows") or [], task_types)
        for tag, n in (plan.get("required_edges") or {}).items():
            cells.append(
                {
                    "cell_key": f"edge:{tag}",
                    "dimension_values": {"edge_case": tag},
                    "quota_kind": "count",
                    "quota_value": n,
                    "quota": n,
                    "available": int(
                        (catalog or {}).get("dimensions", {}).get("edge_cases", {}).get(tag, 0)
                    ),
                }
            )
        return cells
    types = list((catalog or {}).get("dimensions", {}).get("application_type", {}).keys())
    if task_types:
        types = [t for t in types if t in task_types] or types
    cells = []
    if not types:
        return cells
    base, extra = divmod(plan["sample_size"], len(types))
    for i, t in enumerate(types):
        share = base + (1 if i < extra else 0)
        # Largest remainder, so the completeness quotas of a type add up to its share exactly (rounding each one on its
        # own could give 12 cases for a sample size of 10).
        raw = {k: share * pct / 100 for k, pct in plan["completeness_quotas"].items()}
        split = {k: int(v) for k, v in raw.items()}
        left = share - sum(split.values()) if sum(raw.values()) else 0
        for k in sorted(raw, key=lambda k: (-(raw[k] - split[k]), list(raw).index(k)))[
            : max(left, 0)
        ]:
            split[k] += 1
        for completeness, pct in plan["completeness_quotas"].items():
            quota = split[completeness]
            cells.append(
                {
                    "cell_key": f"{t}|{completeness}",
                    "dimension_values": {"application_type": t, "completeness": completeness},
                    "quota_kind": "percent",
                    "quota_value": pct,
                    "quota": quota,
                    "available": int(catalog.get("cells", {}).get(f"{t}|{completeness}", 0)),
                }
            )
    for tag, n in (plan.get("required_edges") or {}).items():
        cells.append(
            {
                "cell_key": f"edge:{tag}",
                "dimension_values": {"edge_case": tag},
                "quota_kind": "count",
                "quota_value": n,
                "quota": n,
                "available": int(catalog.get("dimensions", {}).get("edge_cases", {}).get(tag, 0)),
            }
        )
    return cells


def _task_types(c, sv_id):
    """Application types the suite version's tasks cover (a task with no type selector covers all → None)."""
    rows = c.execute(
        """SELECT t.case_selector FROM suites.suite_tasks s JOIN projects.task_imports t ON t.id=s.task_import_id
           WHERE s.suite_version_id=%s""",
        (sv_id,),
    ).fetchall()
    types = {(r["case_selector"] or {}).get("application_type") for r in rows}
    if not rows or None in types:
        return None
    return types


def _write_plan(c, ws, sv_id, plan, catalog, source="manual", ai=None):
    validate_plan(plan)
    c.execute("DELETE FROM suites.data_plan_cells WHERE suite_version_id=%s", (sv_id,))
    c.execute("DELETE FROM suites.data_plans WHERE suite_version_id=%s", (sv_id,))
    c.execute(
        """INSERT INTO suites.data_plans(suite_version_id,workspace_id,sample_size,stratify_by,completeness_quotas,required_edges,sampling_seed,
             missing_policy,source,ai_suggested,case_set_name) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            sv_id,
            ws,
            plan["sample_size"],
            plan.get("stratify_by") or ["application_type"],
            Jsonb(plan["completeness_quotas"]),
            Jsonb(plan.get("required_edges") or {}),
            int(plan.get("sampling_seed", 20261121)),
            plan.get("missing_policy", "block"),
            source,
            Jsonb(ai) if ai else None,
            (plan.get("case_set_name") or "").strip() or None,
        ),
    )
    for cell in compute_cells(plan, catalog, _task_types(c, sv_id)):
        c.execute(
            """INSERT INTO suites.data_plan_cells(suite_version_id,workspace_id,cell_key,dimension_values,quota_kind,quota_value,quota,available)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                sv_id,
                ws,
                cell["cell_key"],
                Jsonb(cell["dimension_values"]),
                cell["quota_kind"],
                cell["quota_value"],
                cell["quota"],
                cell["available"],
            ),
        )


def _refresh_availability(c, ws, sv_id, catalog):
    for cell in c.execute(
        "SELECT * FROM suites.data_plan_cells WHERE suite_version_id=%s", (sv_id,)
    ).fetchall():
        dv = cell["dimension_values"]
        if cell["cell_key"].startswith("edge:"):
            have = int(
                (catalog or {}).get("dimensions", {}).get("edge_cases", {}).get(dv["edge_case"], 0)
            )
        elif set(dv) == {"application_type", "completeness"}:
            have = int((catalog or {}).get("cells", {}).get(cell["cell_key"], 0))
        else:  # E-005 split: counted from the environment's case rows
            have = sum(
                1
                for r in (catalog or {}).get("_rows") or []
                if all(case_value(r, k) == v for k, v in dv.items())
            )
        if have != cell["available"]:
            c.execute(
                "UPDATE suites.data_plan_cells SET available=%s WHERE suite_version_id=%s AND cell_key=%s",
                (have, sv_id, cell["cell_key"]),
            )


# --- checklist ---------------------------------------------------------------------------------------------------


def checklist(c, ws, sv):
    pid = sv["project_id"]
    items = []
    for b in c.execute(
        "SELECT * FROM suites.suite_bindings WHERE suite_version_id=%s ORDER BY alias", (sv["id"],)
    ).fetchall():
        pick, code, reason, _ = resolve_binding(c, ws, pid, b)
        items.append(
            {
                "key": f"binding:{b['alias']}",
                "ok": pick is not None and (b["source"] != "custom" or bool(b["reason"])),
                "label": f"Environment {b['alias']} binds {selection.short(pick['id']) if pick else 'nothing'}",
                "detail": None if pick else f"{code}: {reason}",
            }
        )
    bad_criteria = []
    for b in c.execute(
        "SELECT * FROM suites.suite_criterion_bindings WHERE suite_version_id=%s", (sv["id"],)
    ).fetchall():
        pick, code, reason = resolve_criterion(c, ws, pid, b)
        if not pick:
            bad_criteria.append(f"{b['criterion_id']} ({reason})")
    items.append(
        {
            "key": "criteria",
            "ok": not bad_criteria,
            "label": "Every criterion binds a qualified evaluator configuration",
            "detail": "; ".join(bad_criteria) or None,
        }
    )
    plan = c.execute(
        "SELECT * FROM suites.data_plans WHERE suite_version_id=%s", (sv["id"],)
    ).fetchone()
    if plan:
        total = sum(float(v) for v in plan["completeness_quotas"].values())
        items.append(
            {
                "key": "quotas_100",
                "ok": abs(total - 100) < 1e-6,
                "label": "Completeness quotas add up to 100%",
                "detail": None if abs(total - 100) < 1e-6 else f"They add up to {total:g}%",
            }
        )
        for cell in c.execute(
            "SELECT * FROM suites.data_plan_cells WHERE suite_version_id=%s ORDER BY cell_key",
            (sv["id"],),
        ).fetchall():
            if cell["quota"] > cell["available"]:
                resolved = (
                    plan["missing_policy"] == "use_available" or cell["inbox_item_id"] is not None
                )
                items.append(
                    {
                        "key": f"cell:{cell['cell_key']}",
                        "ok": resolved,
                        "cell_key": cell["cell_key"],
                        "short": True,
                        "label": f"{cell['cell_key'].replace('|', ' · ')}: the plan asks for {cell['quota']}; the data has {cell['available']}",
                        "detail": (
                            "use what is available"
                            if plan["missing_policy"] == "use_available"
                            else f"more data asked ({cell['inbox_item_id']})"
                            if cell["inbox_item_id"]
                            else None
                        ),
                    }
                )
    else:
        items.append(
            {"key": "data_plan", "ok": False, "label": "A data plan is set", "detail": None}
        )
    ts = c.execute(
        "SELECT * FROM suites.ts_plans WHERE suite_version_id=%s", (sv["id"],)
    ).fetchone()
    if ts and ts["enabled"]:
        items.append(
            {
                "key": "ts_approved",
                "ok": ts["state"] == "approved",
                "label": "Trust & Safety prompt set approved",
                "detail": None if ts["state"] == "approved" else f"Prompt set is {ts['state']}",
            }
        )
    tasks = c.execute(
        "SELECT count(*) n FROM suites.suite_tasks WHERE suite_version_id=%s", (sv["id"],)
    ).fetchone()["n"]
    items.append(
        {
            "key": "tasks",
            "ok": tasks > 0,
            "label": f"{tasks} ready tasks (all ready tasks of the project)",
            "detail": None,
        }
    )
    return {"can_run": all(i["ok"] for i in items), "items": items}


# --- versions ----------------------------------------------------------------------------------------------------


def _ready_tasks(c, ws, pid):
    return c.execute(
        "SELECT id, task_id, revision, package_sha256, case_selector FROM projects.task_imports WHERE workspace_id=%s AND project_id=%s AND state='ready' ORDER BY task_id",
        (ws, pid),
    ).fetchall()


def _new_version_row(c, ws, pid, suite_id, name, actor_id, based_on=None):
    sv_id = str(uuid.uuid4())
    c.execute(
        """INSERT INTO suites.suite_versions(id,workspace_id,project_id,suite_id,name,state,planned_on_env_version,based_on,created_by)
                 VALUES(%s,%s,%s,%s,%s,'draft','pending',%s,%s)""",
        (sv_id, ws, pid, suite_id, name, based_on, actor_id),
    )
    from anvil.rlgym.projects.service import latest_map

    for t in _ready_tasks(c, ws, pid):
        # D-056: the draft captures the task's newest attached policy_id_map; a later attachment never reaches it.
        pm = latest_map(c, t["id"])
        c.execute(
            "INSERT INTO suites.suite_tasks(suite_version_id,workspace_id,task_import_id,policy_map_id) VALUES(%s,%s,%s,%s)",
            (sv_id, ws, t["id"], pm and pm["id"]),
        )
    return sv_id


def _copy_from(c, ws, src, dst):
    for b in c.execute(
        "SELECT * FROM suites.suite_bindings WHERE suite_version_id=%s", (src,)
    ).fetchall():
        c.execute(
            "INSERT INTO suites.suite_bindings(suite_version_id,workspace_id,alias,rule_kind,pinned_version_id,seed_family,source,reason) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                dst,
                ws,
                b["alias"],
                b["rule_kind"],
                b["pinned_version_id"],
                b["seed_family"],
                b["source"],
                b["reason"],
            ),
        )
    for b in c.execute(
        "SELECT * FROM suites.suite_criterion_bindings WHERE suite_version_id=%s", (src,)
    ).fetchall():
        c.execute(
            "INSERT INTO suites.suite_criterion_bindings(suite_version_id,workspace_id,criterion_id,configuration_id,rule_kind,pinned_version,source,reason) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                dst,
                ws,
                b["criterion_id"],
                b["configuration_id"],
                b["rule_kind"],
                b["pinned_version"],
                b["source"],
                b["reason"],
            ),
        )
    plan = c.execute("SELECT * FROM suites.data_plans WHERE suite_version_id=%s", (src,)).fetchone()
    ts = c.execute("SELECT * FROM suites.ts_plans WHERE suite_version_id=%s", (src,)).fetchone()
    return plan, ts


def _default_bindings(c, ws, pid, sv_id):
    for r in _project_rules(c, ws, pid):
        c.execute(
            "INSERT INTO suites.suite_bindings(suite_version_id,workspace_id,alias,rule_kind,source) VALUES(%s,%s,%s,'project_rule','project_default')",
            (sv_id, ws, r["alias"]),
        )
    for r in c.execute(
        "SELECT * FROM projects.evaluator_selection_rules WHERE workspace_id=%s AND project_id=%s AND valid_to IS NULL",
        (ws, pid),
    ).fetchall():
        c.execute(
            """INSERT INTO suites.suite_criterion_bindings(suite_version_id,workspace_id,criterion_id,configuration_id,rule_kind,source)
                     VALUES(%s,%s,%s,%s,'project_rule','project_default')""",
            (sv_id, ws, r["criterion_id"], r["configuration_id"]),
        )


def _write_ts(
    c, ws, sv_id, settings, categories=(), prompts=(), state="draft", generator=None, approval=None
):
    c.execute("DELETE FROM suites.ts_prompts WHERE suite_version_id=%s", (sv_id,))
    c.execute("DELETE FROM suites.ts_categories WHERE suite_version_id=%s", (sv_id,))
    c.execute("DELETE FROM suites.ts_plans WHERE suite_version_id=%s", (sv_id,))
    c.execute(
        """INSERT INTO suites.ts_plans(suite_version_id,workspace_id,enabled,domain,strategies,prompts_per_category,placement,state,generator,promptfoo_version,approved_by,approved_at,prompt_set_sha256)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            sv_id,
            ws,
            bool(settings.get("enabled")),
            settings.get("domain", "Banking · KYC / AML"),
            list(settings.get("strategies") or ["plain"]),
            int(settings.get("prompts_per_category", 3)),
            settings.get("placement", "tool_result"),
            state,
            generator,
            settings.get("promptfoo_version", "fw-promptfoo-0.121.0"),
            *(approval or (None, None, None)),
        ),
    )
    for cat in categories:
        c.execute(
            """INSERT INTO suites.ts_categories(suite_version_id,workspace_id,key,name,category_group,source,boundary_tested,observable_check,promptfoo_plugin,grounding,policy_text)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                sv_id,
                ws,
                cat["key"],
                cat["name"],
                cat["category_group"],
                cat.get("source", "pack"),
                cat["boundary_tested"],
                cat["observable_check"],
                cat.get("promptfoo_plugin"),
                cat.get("grounding"),
                cat.get("policy_text"),
            ),
        )
    for p in prompts:
        c.execute(
            """INSERT INTO suites.ts_prompts(suite_version_id,workspace_id,id,category_key,text,strategy,severity,approved)
                     VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                sv_id,
                ws,
                p["id"],
                p["category_key"],
                p["text"],
                p["strategy"],
                p["severity"],
                p.get("approved", True),
            ),
        )


def _catalog_for(c, ws, pid, sv_id):
    env = _bound_env(c, ws, pid, sv_id)
    if env:
        c.execute(
            "UPDATE suites.suite_versions SET planned_on_env_version=%s WHERE id=%s AND state='draft'",
            (env["id"], sv_id),
        )
    return env, with_edges(env)


# D-038: edge-case tags come from the bound environment version's own cases. A version's case rows never change, so
# the counts are kept per version id once read.
_EDGE_CACHE = {}
_ROWS = {}


def edge_counts(env):
    """{tag: {"available": n, "application_types": {type: n}}} for an environment version row, or None when unknown.
    From the mirrored summary when it lists edge cases, else counted from the registry's case rows (a summary is only
    refreshed on a version event, so @6-@8 carried none)."""
    if not env:
        return None
    if env["id"] in _EDGE_CACHE:
        return _EDGE_CACHE[env["id"]]
    from anvil.rlgym import integrations

    try:
        rows = integrations.registry_get(f"/versions/{env['id']}/cases", base=env.get("registry"))[
            "cases"
        ]
    except GymError:
        summary = ((env.get("case_catalog") or {}).get("dimensions") or {}).get("edge_cases") or {}
        return {
            t: {"available": int(n), "application_types": {}} for t, n in summary.items()
        } or None
    _ROWS[env["id"]] = rows
    out = {}
    for r in rows:
        for tag in r.get("edge_cases") or []:
            e = out.setdefault(tag, {"available": 0, "application_types": {}})
            e["available"] += 1
            at = r.get("application_type")
            e["application_types"][at] = e["application_types"].get(at, 0) + 1
    _EDGE_CACHE[env["id"]] = out
    return out


def with_edges(env):
    """The version's case catalog with `dimensions.edge_cases` filled from its cases (D-038)."""
    cat = (env or {}).get("case_catalog")
    if not cat:
        return cat
    counts = edge_counts(env)
    if not counts:
        return cat
    dims = dict(cat.get("dimensions") or {})
    dims["edge_cases"] = {t: e["available"] for t, e in sorted(counts.items())}
    # E-005: the case rows themselves, for splits by other properties (in memory only; never stored).
    return {**cat, "dimensions": dims, "_rows": _ROWS.get(env["id"]) or []}


def create_suite(c, ws, actor, pid, name, from_default=True, is_default=False):
    project = _project(c, ws, pid)
    suite_id = SLUG.sub("-", name.lower()).strip("-")[:60]
    require(suite_id, "VALIDATION_FAILED", "A name is required", field="name")
    require(
        not c.execute(
            "SELECT 1 FROM suites.suites WHERE workspace_id=%s AND project_id=%s AND suite_id=%s",
            (ws, pid, suite_id),
        ).fetchone(),
        "CONFLICT",
        f"Suite {suite_id} exists",
    )
    c.execute(
        "INSERT INTO suites.suites(workspace_id,project_id,suite_id,name,is_default,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
        (ws, pid, suite_id, name, is_default, actor.id),
    )
    sv_id = _new_version_row(c, ws, pid, suite_id, name, actor.id)
    default = (
        None
        if is_default or not from_default
        else c.execute(
            """SELECT v.id FROM suites.suite_versions v JOIN suites.suites s USING (workspace_id, project_id, suite_id)
           WHERE v.workspace_id=%s AND v.project_id=%s AND s.is_default AND v.state='saved' ORDER BY v.version DESC LIMIT 1""",
            (ws, pid),
        ).fetchone()
    )
    if default:
        plan, ts = _copy_from(c, ws, default["id"], sv_id)
    else:
        _default_bindings(c, ws, pid, sv_id)
        plan, ts = None, None
    env, catalog = _catalog_for(c, ws, pid, sv_id)
    plan_body = DEFAULT_PLAN if not plan else {k: plan[k] for k in DEFAULT_PLAN}
    if not plan and env and catalog and catalog.get("cases", 0) < plan_body["sample_size"]:
        plan_body = {
            **plan_body,
            "sample_size": catalog["cases"],
            "missing_policy": "use_available",
        }
    edges = _edge_cases(c, ws, pid)
    if not plan and edges:
        # 2.12: the default plan counts cases per S4 edge-case tag at the template's minimum. A short tag shows in the
        # plan and can be asked for (more data); the run uses what exists meanwhile.
        from anvil.rlgym.catalog.templates import edge_minimum

        plan_body = {
            **plan_body,
            "required_edges": {tag: edge_minimum(e) for tag, e in edges.items()},
            "missing_policy": "use_available",
        }
    _write_plan(c, ws, sv_id, plan_body, catalog)
    _write_ts(
        c,
        ws,
        sv_id,
        {
            "enabled": False,
            "domain": "Banking · KYC / AML",
            "strategies": ["plain", "prompt-injection wrapper"],
        }
        if not ts
        else {
            k: ts[k]
            for k in (
                "enabled",
                "domain",
                "strategies",
                "prompts_per_category",
                "placement",
                "promptfoo_version",
            )
        },
    )
    audit(c, ws, actor, "suite.created", f"{pid}:{suite_id}", details={"project": project["name"]})
    return sv_id


def new_draft(c, ws, actor, pid, suite_id):
    suite = c.execute(
        "SELECT * FROM suites.suites WHERE workspace_id=%s AND project_id=%s AND suite_id=%s",
        (ws, pid, suite_id),
    ).fetchone()
    if not suite:
        raise GymError("NOT_FOUND", "Suite not found")
    existing = c.execute(
        "SELECT id FROM suites.suite_versions WHERE workspace_id=%s AND project_id=%s AND suite_id=%s AND state='draft'",
        (ws, pid, suite_id),
    ).fetchone()
    if existing:
        return existing["id"]
    latest = c.execute(
        """SELECT * FROM suites.suite_versions WHERE workspace_id=%s AND project_id=%s AND suite_id=%s AND state='saved'
                          ORDER BY version DESC LIMIT 1""",
        (ws, pid, suite_id),
    ).fetchone()
    sv_id = _new_version_row(
        c, ws, pid, suite_id, suite["name"], actor.id, latest["id"] if latest else None
    )
    if latest:
        plan, ts = _copy_from(c, ws, latest["id"], sv_id)
    else:
        _default_bindings(c, ws, pid, sv_id)
        plan, ts = None, None
    env, catalog = _catalog_for(c, ws, pid, sv_id)
    _write_plan(c, ws, sv_id, {k: plan[k] for k in DEFAULT_PLAN} if plan else DEFAULT_PLAN, catalog)
    if latest:
        # Keep lowered quotas and inbox links from the saved version, re-checked against today's data.
        for cell in c.execute(
            "SELECT * FROM suites.data_plan_cells WHERE suite_version_id=%s", (latest["id"],)
        ).fetchall():
            c.execute(
                "UPDATE suites.data_plan_cells SET quota=%s, original_quota=%s, inbox_item_id=%s WHERE suite_version_id=%s AND cell_key=%s",
                (
                    cell["quota"],
                    cell["original_quota"],
                    cell["inbox_item_id"],
                    sv_id,
                    cell["cell_key"],
                ),
            )
    if ts:
        cats = c.execute(
            "SELECT * FROM suites.ts_categories WHERE suite_version_id=%s", (latest["id"],)
        ).fetchall()
        prompts = c.execute(
            "SELECT * FROM suites.ts_prompts WHERE suite_version_id=%s", (latest["id"],)
        ).fetchall()
        _write_ts(
            c,
            ws,
            sv_id,
            {
                k: ts[k]
                for k in (
                    "enabled",
                    "domain",
                    "strategies",
                    "prompts_per_category",
                    "placement",
                    "promptfoo_version",
                )
            },
            cats,
            prompts,
            ts["state"],
            ts["generator"],
            (ts["approved_by"], ts["approved_at"], ts["prompt_set_sha256"])
            if ts["state"] == "approved"
            else None,
        )
    return sv_id


def _content(c, sv_id):
    """Everything that defines what a run uses; hashed into suite_sha256."""
    plan = c.execute(
        "SELECT * FROM suites.data_plans WHERE suite_version_id=%s", (sv_id,)
    ).fetchone()
    ts = c.execute("SELECT * FROM suites.ts_plans WHERE suite_version_id=%s", (sv_id,)).fetchone()
    # D-056: each task's captured policy_id_map, hashed in only when some task has one, so every suite saved without
    # maps keeps the hash it had.
    maps = c.execute(
        """SELECT t.package_sha256, m.map_sha256 FROM suites.suite_tasks s JOIN projects.task_imports t ON t.id=s.task_import_id
           JOIN projects.task_policy_maps m ON m.id=s.policy_map_id WHERE s.suite_version_id=%s ORDER BY 1""",
        (sv_id,),
    ).fetchall()
    return {
        **({"policy_maps": [[m["package_sha256"], m["map_sha256"]] for m in maps]} if maps else {}),
        "bindings": c.execute(
            "SELECT alias, rule_kind, pinned_version_id, seed_family FROM suites.suite_bindings WHERE suite_version_id=%s ORDER BY alias",
            (sv_id,),
        ).fetchall(),
        "criteria": c.execute(
            "SELECT criterion_id, configuration_id, rule_kind, pinned_version FROM suites.suite_criterion_bindings WHERE suite_version_id=%s ORDER BY criterion_id",
            (sv_id,),
        ).fetchall(),
        "tasks": [
            r["package_sha256"]
            for r in c.execute(
                "SELECT t.package_sha256 FROM suites.suite_tasks s JOIN projects.task_imports t ON t.id=s.task_import_id WHERE s.suite_version_id=%s ORDER BY 1",
                (sv_id,),
            ).fetchall()
        ],
        "plan": plan
        and {
            k: plan[k]
            for k in (
                "sample_size",
                "stratify_by",
                "completeness_quotas",
                "required_edges",
                "sampling_seed",
                "missing_policy",
            )
        },
        "cells": c.execute(
            "SELECT cell_key, quota FROM suites.data_plan_cells WHERE suite_version_id=%s ORDER BY cell_key",
            (sv_id,),
        ).fetchall(),
        "ts": ts
        and {
            "enabled": ts["enabled"],
            "prompt_set_sha256": ts["prompt_set_sha256"],
            "placement": ts["placement"],
        },
    }


def save(c, ws, actor, sv_id):
    sv = _draft(c, ws, sv_id)
    _, catalog = _catalog_for(c, ws, sv["project_id"], sv_id)
    _refresh_availability(c, ws, sv_id, catalog)
    check = checklist(c, ws, sv)
    if not check["can_run"]:
        raise GymError(
            "VALIDATION_FAILED",
            "The suite cannot run yet: resolve every item first",
            {"items": [i for i in check["items"] if not i["ok"]]},
        )
    h = sha(_content(c, sv_id))
    latest = c.execute(
        """SELECT version, suite_sha256 FROM suites.suite_versions WHERE workspace_id=%s AND project_id=%s AND suite_id=%s
                          AND state='saved' ORDER BY version DESC LIMIT 1""",
        (ws, sv["project_id"], sv["suite_id"]),
    ).fetchone()
    require(
        not latest or latest["suite_sha256"] != h,
        "CONFLICT",
        f"Nothing changed since version {latest and latest['version']}",
    )
    version = (latest["version"] + 1) if latest else 1
    env = _bound_env(c, ws, sv["project_id"], sv_id)
    c.execute(
        """UPDATE suites.suite_versions SET state='saved', version=%s, suite_sha256=%s, planned_on_env_version=%s, saved_by=%s, saved_at=now()
                 WHERE id=%s""",
        (version, h, env["id"] if env else sv["planned_on_env_version"], actor.id, sv_id),
    )
    audit(
        c,
        ws,
        actor,
        "suite.version_saved",
        f"{sv['project_id']}:{sv['suite_id']}@{version}",
        details={"suite_sha256": h},
    )
    emit(
        c,
        ws,
        "suite.version_created",
        f"{sv['suite_id']}@{version}",
        {"project_id": sv["project_id"], "suite_id": sv["suite_id"], "version": version},
    )
    return {
        "id": sv_id,
        "suite_id": sv["suite_id"],
        "version": version,
        "suite_sha256": h,
        "label": f"{sv['suite_id']}-v{version}",
    }


def discard(c, ws, actor, sv_id):
    sv = _draft(c, ws, sv_id)
    for t in (
        "ts_prompts",
        "ts_categories",
        "ts_plans",
        "data_plan_cells",
        "data_plans",
        "suite_tasks",
        "suite_criterion_bindings",
        "suite_bindings",
    ):
        c.execute(f"DELETE FROM suites.{t} WHERE suite_version_id=%s", (sv_id,))
    c.execute("DELETE FROM suites.suite_versions WHERE id=%s", (sv_id,))
    audit(c, ws, actor, "suite.draft_discarded", f"{sv['project_id']}:{sv['suite_id']}")
    return {"discarded": sv_id}


def patch(c, ws, actor, sv_id, body):
    """Draft edits: bindings, criterion bindings, data plan, lower/lower-all, Trust & Safety settings and categories."""
    sv = _draft(c, ws, sv_id)
    pid = sv["project_id"]
    if "bindings" in body:
        for b in body["bindings"]:
            kind = b.get("rule_kind", "project_rule")
            require(
                kind in ("project_rule", "pinned", "same_data", "latest"),
                "VALIDATION_FAILED",
                "Unknown rule",
                field="rule_kind",
            )
            source = "project_default" if kind == "project_rule" else b.get("source", "custom")
            require(
                source in ("project_default", "ai_suggestion", "custom", "experiment"),
                "VALIDATION_FAILED",
                "Unknown binding source",
                field="source",
            )
            # E-005 §2.2: an experiment pins one version, with a reason; the suite is then not leaderboard-eligible.
            require(
                source != "experiment" or (kind == "pinned" and (b.get("reason") or "").strip()),
                "VALIDATION_FAILED",
                "An experiment pins one environment version and needs a reason",
                field="reason",
            )
            require(
                source != "custom" or (b.get("reason") or "").strip(),
                "VALIDATION_FAILED",
                "A custom binding needs a reason",
                field="reason",
            )
            probe = {
                "alias": b["alias"],
                "rule_kind": kind,
                "pinned_version_id": b.get("pinned_version_id"),
                "seed_family": b.get("seed_family"),
            }
            pick, code, why, _ = resolve_binding(c, ws, pid, probe)
            if not pick:
                raise GymError(
                    "BINDING_INCOMPATIBLE", f"The binding selects nothing ({why})", {"code": code}
                )
            c.execute(
                "DELETE FROM suites.suite_bindings WHERE suite_version_id=%s AND alias=%s",
                (sv_id, b["alias"]),
            )
            c.execute(
                "INSERT INTO suites.suite_bindings(suite_version_id,workspace_id,alias,rule_kind,pinned_version_id,seed_family,source,reason) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    sv_id,
                    ws,
                    b["alias"],
                    kind,
                    b.get("pinned_version_id"),
                    b.get("seed_family"),
                    source,
                    b.get("reason"),
                ),
            )
        env, catalog = _catalog_for(c, ws, pid, sv_id)
        plan = c.execute(
            "SELECT * FROM suites.data_plans WHERE suite_version_id=%s", (sv_id,)
        ).fetchone()
        _write_plan(c, ws, sv_id, {k: plan[k] for k in DEFAULT_PLAN}, catalog)
    if "criterion_bindings" in body:
        for b in body["criterion_bindings"]:
            kind = b.get("rule_kind", "project_rule")
            current = c.execute(
                "SELECT * FROM suites.suite_criterion_bindings WHERE suite_version_id=%s AND criterion_id=%s",
                (sv_id, b["criterion_id"]),
            ).fetchone()
            require(current, "NOT_FOUND", "Unknown criterion")
            source = "project_default" if kind == "project_rule" else b.get("source", "custom")
            require(
                source != "custom" or (b.get("reason") or "").strip(),
                "VALIDATION_FAILED",
                "A custom binding needs a reason",
                field="reason",
            )
            pick, code, why = resolve_criterion(
                c,
                ws,
                pid,
                {**current, "rule_kind": kind, "pinned_version": b.get("pinned_version")},
            )
            if not pick:
                raise GymError(
                    "BINDING_INCOMPATIBLE", f"The evaluator binding selects nothing ({why})"
                )
            c.execute(
                "UPDATE suites.suite_criterion_bindings SET rule_kind=%s, pinned_version=%s, source=%s, reason=%s WHERE suite_version_id=%s AND criterion_id=%s",
                (kind, b.get("pinned_version"), source, b.get("reason"), sv_id, b["criterion_id"]),
            )
    if "data_plan" in body:
        _, catalog = _catalog_for(c, ws, pid, sv_id)
        current = c.execute(
            "SELECT * FROM suites.data_plans WHERE suite_version_id=%s", (sv_id,)
        ).fetchone()
        plan = {**{k: current[k] for k in DEFAULT_PLAN}, **body["data_plan"]}
        _write_plan(
            c, ws, sv_id, plan, catalog, body.get("plan_source", "manual"), body.get("ai_suggested")
        )
    if body.get("lower"):
        cell = c.execute(
            "SELECT * FROM suites.data_plan_cells WHERE suite_version_id=%s AND cell_key=%s",
            (sv_id, body["lower"]),
        ).fetchone()
        require(cell, "NOT_FOUND", "Unknown cell")
        c.execute(
            "UPDATE suites.data_plan_cells SET original_quota=coalesce(original_quota, quota), quota=%s WHERE suite_version_id=%s AND cell_key=%s",
            (min(cell["quota"], cell["available"]), sv_id, body["lower"]),
        )
    if body.get("lower_all"):
        c.execute(
            """UPDATE suites.data_plan_cells SET original_quota=coalesce(original_quota, quota), quota=available
                     WHERE suite_version_id=%s AND quota > available""",
            (sv_id,),
        )
    if "missing_policy" in body:
        require(
            body["missing_policy"] in ("block", "use_available"),
            "VALIDATION_FAILED",
            "Unknown missing policy",
        )
        c.execute(
            "UPDATE suites.data_plans SET missing_policy=%s WHERE suite_version_id=%s",
            (body["missing_policy"], sv_id),
        )
    if "ts_settings" in body or "ts_categories" in body:
        ts = c.execute(
            "SELECT * FROM suites.ts_plans WHERE suite_version_id=%s", (sv_id,)
        ).fetchone()
        settings = {
            **{
                k: ts[k]
                for k in (
                    "enabled",
                    "domain",
                    "strategies",
                    "prompts_per_category",
                    "placement",
                    "promptfoo_version",
                )
            },
            **(body.get("ts_settings") or {}),
        }
        require(
            set(settings["strategies"]) <= set(trust_safety.STRATEGIES) and settings["strategies"],
            "VALIDATION_FAILED",
            "Unknown strategy",
        )
        cats = body.get("ts_categories")
        if cats is None:
            cats = c.execute(
                "SELECT * FROM suites.ts_categories WHERE suite_version_id=%s", (sv_id,)
            ).fetchall()
        for cat in cats:
            if cat.get("source") == "custom":
                require(
                    trust_safety.check_custom(cat),
                    "VALIDATION_FAILED",
                    f"Category '{cat.get('name')}' has no observable check (a tool call or an output field)",
                    field="observable_check",
                )
        # Any change to categories or settings needs regeneration and a new approval.
        _write_ts(c, ws, sv_id, settings, cats)
    audit(
        c,
        ws,
        actor,
        "suite.draft_edited",
        str(sv_id),
        details={"sections": sorted(k for k in body if k != "ai_suggested")},
    )
    return view(c, ws, sv_id)


GENERATOR_GATEWAY = None  # tests set a fake gateway factory


def ts_generate(c, ws, actor, sv_id, body=None):
    _draft(c, ws, sv_id)
    ts = c.execute("SELECT * FROM suites.ts_plans WHERE suite_version_id=%s", (sv_id,)).fetchone()
    require(ts and ts["enabled"], "VALIDATION_FAILED", "Turn Trust & Safety on first")
    cats = c.execute(
        "SELECT * FROM suites.ts_categories WHERE suite_version_id=%s ORDER BY key", (sv_id,)
    ).fetchall()
    require(cats, "VALIDATION_FAILED", "Choose at least one category")
    gen = (body or {}).get("generator")
    if gen:
        from anvil.rlgym.live import generator as live_generator

        prompts, generator_label = live_generator.generate(
            c,
            ws,
            gen,
            cats,
            list(ts["strategies"]),
            ts["prompts_per_category"],
            ts["placement"],
            gateway_factory=GENERATOR_GATEWAY,
        )
    else:
        prompts = trust_safety.generate(
            cats, list(ts["strategies"]), ts["prompts_per_category"], ts["placement"]
        )
        generator_label = trust_safety.GENERATOR
    _write_ts(
        c,
        ws,
        sv_id,
        {
            k: ts[k]
            for k in (
                "enabled",
                "domain",
                "strategies",
                "prompts_per_category",
                "placement",
                "promptfoo_version",
            )
        },
        cats,
        prompts,
        "generated",
        generator_label,
    )
    audit(
        c,
        ws,
        actor,
        "ts.generated",
        str(sv_id),
        details={"prompts": len(prompts), "generator": trust_safety.GENERATOR},
    )
    return view(c, ws, sv_id)


def ts_review(c, ws, actor, sv_id, body):
    _draft(c, ws, sv_id)
    for pid, approved in (body.get("prompts") or {}).items():
        c.execute(
            "UPDATE suites.ts_prompts SET approved=%s WHERE suite_version_id=%s AND id=%s",
            (bool(approved), sv_id, pid),
        )
    c.execute(
        "UPDATE suites.ts_plans SET state='generated', approved_by=NULL, approved_at=NULL, prompt_set_sha256=NULL WHERE suite_version_id=%s AND state='approved'",
        (sv_id,),
    )
    return view(c, ws, sv_id)


def ts_approve(c, ws, actor, sv_id):
    actor.require_person()
    _draft(c, ws, sv_id)
    ts = c.execute("SELECT * FROM suites.ts_plans WHERE suite_version_id=%s", (sv_id,)).fetchone()
    require(
        ts and ts["state"] == "generated", "VALIDATION_FAILED", "Generate prompts before approving"
    )
    approved = c.execute(
        "SELECT id, category_key, text, strategy FROM suites.ts_prompts WHERE suite_version_id=%s AND approved ORDER BY id",
        (sv_id,),
    ).fetchall()
    require(approved, "VALIDATION_FAILED", "Keep at least one prompt")
    h = sha(approved)
    c.execute(
        "UPDATE suites.ts_plans SET state='approved', approved_by=%s, approved_at=now(), prompt_set_sha256=%s WHERE suite_version_id=%s",
        (actor.id, h, sv_id),
    )
    audit(
        c,
        ws,
        actor,
        "ts.approved",
        str(sv_id),
        details={"prompt_set_sha256": h, "prompts": len(approved)},
    )
    emit(
        c,
        ws,
        "ts_plan.approved",
        str(sv_id),
        {"suite_version_id": str(sv_id), "prompt_set_sha256": h},
    )
    return view(c, ws, sv_id)


def send_more_data(c, ws, actor, sv_id, body):
    """`more_data` item to Studio's next-version inbox: every short cell with the business description of the data needed."""
    actor.require_person()
    sv = _draft(c, ws, sv_id)
    project = _project(c, ws, sv["project_id"])
    descriptions = body.get("descriptions") or {}
    short = c.execute(
        "SELECT * FROM suites.data_plan_cells WHERE suite_version_id=%s AND quota > available ORDER BY cell_key",
        (sv_id,),
    ).fetchall()
    require(short, "VALIDATION_FAILED", "No short cells: the bound data covers the plan")
    plan = c.execute(
        "SELECT * FROM suites.data_plans WHERE suite_version_id=%s", (sv_id,)
    ).fetchone()
    env = _bound_env(c, ws, sv["project_id"], sv_id)
    edges = _edge_cases(c, ws, sv["project_id"])

    def edge_detail(cell_key):
        """2.12: an edge-case cell carries the tag, the generator recipe and the expected outcome, so Studio can make
        those cases with the same generator and seed family."""
        e = edges.get(cell_key.removeprefix("edge:")) if cell_key.startswith("edge:") else None
        if not e:
            return {}
        return {
            "edge_case": {
                k: e.get(k)
                for k in (
                    "tag",
                    "recipe",
                    "expected_outcome",
                    "archetype",
                    "complexity",
                    "products",
                )
            }
        }

    cells = [
        {
            "cell_key": s["cell_key"],
            "values": s["dimension_values"],
            "quota": s["original_quota"] or s["quota"],
            "have": s["available"],
            "request": (s["original_quota"] or s["quota"]) - s["available"],
            "description": (descriptions.get(s["cell_key"]) or "").strip()
            or (
                _recipe_text(edges.get(s["cell_key"].removeprefix("edge:"), {}).get("recipe"))
                if s["cell_key"].startswith("edge:")
                else None
            )
            or None,
            **edge_detail(s["cell_key"]),
        }
        for s in short
    ]
    require(
        all(cell["description"] for cell in cells),
        "VALIDATION_FAILED",
        "Describe the data needed for every short cell",
        missing=[cell["cell_key"] for cell in cells if not cell["description"]],
    )
    item = inbox.create(
        c,
        ws,
        actor,
        {
            "kind": "more_data",
            "template_id": project["template_id"],
            "version": project["template_version"],
            "project_id": sv["project_id"],
            "suite_version_id": sv_id,
            "environment_version": env["id"] if env else None,
            "summary": (
                body.get("summary")
                or f"{project['name']}: {len(cells)} cells of the data plan are short"
            ).strip(),
            "needed_by": body.get("needed_by"),
            "evidence": {
                "cells": cells,
                "lineage": body.get("lineage", "same_seed_family"),
                "contract_id": env and env["contract_id"],
                "distribution": plan["completeness_quotas"],
                "why": body.get("why"),
            },
        },
    )
    for s in short:
        c.execute(
            "UPDATE suites.data_plan_cells SET inbox_item_id=%s WHERE suite_version_id=%s AND cell_key=%s",
            (item["id"], sv_id, s["cell_key"]),
        )
    return {"item": item, "suite": view(c, ws, sv_id)}


# --- suggestions (rule-based, no model) ------------------------------------------------------------------------


def suggest_bindings(c, ws, sv_id):
    sv = _sv(c, ws, sv_id)
    out = [
        {
            "name": "Follow project rules",
            "recommended": True,
            "reason": "Keeps results comparable with the project's last run and moves with the project's selection rules.",
            "bindings": [
                {"alias": b["alias"], "rule_kind": "project_rule"}
                for b in _project_rules(c, ws, sv["project_id"])
            ],
        }
    ]
    pins = []
    for b in _project_rules(c, ws, sv["project_id"]):
        pick, _, _ = selection.resolve_environment(c, b)
        if pick:
            pins.append(
                {
                    "alias": b["alias"],
                    "rule_kind": "pinned",
                    "pinned_version_id": pick["id"],
                    "source": "ai_suggestion",
                    "reason": "Pin today's versions for a study over several weeks",
                }
            )
    if pins:
        out.append(
            {
                "name": "Pin today's versions",
                "recommended": False,
                "reason": "For a study over several weeks: the suite keeps today's environment version; its runs are ranked in their own group.",
                "bindings": pins,
            }
        )
    return {"source": "rule_based_no_model", "suggestions": out}


def suggest_mix(c, ws, sv_id):
    sv = _sv(c, ws, sv_id)
    _, catalog = _catalog_for(c, ws, sv["project_id"], sv_id)
    require(catalog, "VALIDATION_FAILED", "The bound environment version has no case catalog")
    dims = catalog["dimensions"]
    total = sum(dims["completeness"].values()) or 1
    representative = {k: round(100 * v / total) for k, v in dims["completeness"].items()}
    diff = 100 - sum(representative.values())
    first = next(iter(representative))
    representative[first] += diff
    edges_balanced = {tag: min(3, n) for tag, n in dims["edge_cases"].items()}
    capped = [tag for tag, n in dims["edge_cases"].items() if n < 3]
    sample = min(40, catalog["cases"])
    return {
        "source": "rule_based_no_model",
        "suggestions": [
            {
                "name": "Balanced coverage",
                "recommended": True,
                "plan": {
                    "sample_size": sample,
                    "completeness_quotas": {
                        k: round(100 / len(dims["completeness"])) for k in dims["completeness"]
                    },
                    "required_edges": edges_balanced,
                },
                "reason": "Every S4 edge-case rule exercised at least 3 times where the data has them; equal application types.",
                "capped": capped,
            },
            {
                "name": "Representative",
                "recommended": False,
                "plan": {
                    "sample_size": sample,
                    "completeness_quotas": representative,
                    "required_edges": {},
                },
                "reason": "Mirrors the completeness distribution of the bound data.",
                "capped": [],
            },
            {
                "name": "Diagnostic",
                "recommended": False,
                "plan": None,
                "reason": "Needs results by stratum from an earlier run; no runs yet (2.7).",
                "capped": [],
            },
        ],
    }


def suggest_ts(c, ws, sv_id):
    sv = _sv(c, ws, sv_id)
    ts = c.execute(
        "SELECT domain FROM suites.ts_plans WHERE suite_version_id=%s", (sv_id,)
    ).fetchone()
    project = _project(c, ws, sv["project_id"])
    act = c.execute(
        "SELECT workflow FROM catalog.template_activations WHERE workspace_id=%s AND template_id=%s AND version=%s",
        (ws, project["template_id"], project["template_version"]),
    ).fetchone()
    tools = {t for n in (act["workflow"]["nodes"] if act else []) for t in n.get("tools", [])} | {
        "application.write"
    }
    return trust_safety.suggest_categories(ts["domain"] if ts else "General", tools)


# --- views -------------------------------------------------------------------------------------------------------


def view(c, ws, sv_id):
    sv = _sv(c, ws, sv_id)
    pid = sv["project_id"]
    bindings = []
    for b in c.execute(
        "SELECT * FROM suites.suite_bindings WHERE suite_version_id=%s ORDER BY alias", (sv_id,)
    ).fetchall():
        pick, code, reason, effective = resolve_binding(c, ws, pid, b)
        bindings.append(
            {
                **b,
                "binds_now": pick["id"] if pick else None,
                "ok": pick is not None,
                "reason_unbound": reason if not pick else None,
                "rule_label": ("Follow project rule · " if b["rule_kind"] == "project_rule" else "")
                + selection.rule_label(effective),
                "seed_family": pick["seed_family"] if pick else b["seed_family"],
                "options": [
                    {
                        "rule_kind": "pinned",
                        "pinned_version_id": v["id"],
                        "label": f"Pinned · {selection.short(v['id'])}",
                        "cases": (v["case_catalog"] or {}).get("cases"),
                    }
                    for v in selection.selectable_environments(c, effective["contract_id"])
                ],
            }
        )
    criteria = []
    for b in c.execute(
        "SELECT * FROM suites.suite_criterion_bindings WHERE suite_version_id=%s ORDER BY criterion_id",
        (sv_id,),
    ).fetchall():
        pick, code, reason = resolve_criterion(c, ws, pid, b)
        criteria.append(
            {**b, "binds_now": pick["version"] if pick else None, "ok": pick is not None}
        )
    plan = c.execute(
        "SELECT * FROM suites.data_plans WHERE suite_version_id=%s", (sv_id,)
    ).fetchone()
    cells = c.execute(
        "SELECT * FROM suites.data_plan_cells WHERE suite_version_id=%s ORDER BY cell_key", (sv_id,)
    ).fetchall()
    ts = c.execute("SELECT * FROM suites.ts_plans WHERE suite_version_id=%s", (sv_id,)).fetchone()
    tasks = c.execute(
        """SELECT t.task_id, t.revision, t.case_selector, s.policy_map_id FROM suites.suite_tasks s
           JOIN projects.task_imports t ON t.id=s.task_import_id WHERE s.suite_version_id=%s ORDER BY t.task_id""",
        (sv_id,),
    ).fetchall()
    env = c.execute(
        "SELECT id, case_catalog, registry FROM catalog.environment_versions WHERE id=%s",
        (sv["planned_on_env_version"],),
    ).fetchone()
    cat = with_edges(env) or {}
    edges = edge_counts(env) or {}
    unmatched = [
        t["task_id"]
        for t in tasks
        if cat
        and (
            _cases_for(cat, t["case_selector"]) == 0
            or any(
                cat.get("dimensions", {}).get("edge_cases", {}).get(e, 0) == 0
                for e in t["case_selector"].get("edge_cases", [])
            )
        )
    ]
    return {
        **sv,
        "bindings": bindings,
        "criteria": criteria,
        "plan": plan,
        "cells": cells,
        "ts": ts
        and {
            **ts,
            "categories": c.execute(
                "SELECT * FROM suites.ts_categories WHERE suite_version_id=%s ORDER BY category_group, key",
                (sv_id,),
            ).fetchall(),
            "prompts": c.execute(
                "SELECT * FROM suites.ts_prompts WHERE suite_version_id=%s ORDER BY category_key, id",
                (sv_id,),
            ).fetchall(),
        },
        "tasks": {
            "count": len(tasks),
            # D-056: how many tasks carry a captured policy_id_map in this version.
            "policy_maps": sum(1 for t in tasks if t["policy_map_id"]),
            "unmatched": unmatched,
            "by_application_type": {
                k: sum(1 for t in tasks if t["case_selector"]["application_type"] == k)
                for k in sorted({t["case_selector"]["application_type"] for t in tasks})
            },
        },
        # D-038: the edge cases the planned environment version actually has (tag, cases, application types).
        "edge_catalog": [
            {"tag": t, "available": e["available"], "application_types": e["application_types"]}
            for t, e in sorted(edges.items())
        ],
        "checklist": checklist(c, ws, sv),
        "inbox_items": [
            i
            for i in inbox.list_items(c, ws, kind="more_data", project_id=pid)
            if str(i["suite_version_id"]) == str(sv_id)
            or any(cl["inbox_item_id"] == i["id"] for cl in cells)
        ],
        "label": f"{sv['suite_id']}-v{sv['version']}"
        if sv["version"]
        else f"{sv['suite_id']} (draft)",
        # E-008 / D-047: read-only header facts (version picker, environment and why, run size, leaderboard, changes).
        "header": header.header(c, ws, sv),
    }


def list_suites(c, ws, pid):
    _project(c, ws, pid)
    out = []
    for s in c.execute(
        "SELECT * FROM suites.suites WHERE workspace_id=%s AND project_id=%s ORDER BY is_default DESC, name",
        (ws, pid),
    ).fetchall():
        versions = c.execute(
            """SELECT id, version, state, suite_sha256, planned_on_env_version, saved_at, saved_by, created_at
                                FROM suites.suite_versions WHERE workspace_id=%s AND project_id=%s AND suite_id=%s
                                ORDER BY version DESC NULLS FIRST""",
            (ws, pid, s["suite_id"]),
        ).fetchall()
        runs = c.execute(
            """SELECT r.id, r.name, r.state, r.created_at, v.version suite_version FROM runs.runs r
               JOIN suites.suite_versions v ON v.id=r.suite_version_id
               WHERE r.workspace_id=%s AND v.project_id=%s AND v.suite_id=%s ORDER BY r.created_at DESC""",
            (ws, pid, s["suite_id"]),
        ).fetchall()
        versions = [
            {**v, **header.table_row(c, ws, {**v, "project_id": pid, "suite_id": s["suite_id"]})}
            for v in versions
        ]
        out.append(
            {
                **s,
                "versions": versions,
                "runs": runs,
                "runs_note": f"{len(runs)} runs" if runs else "Not used in a run yet.",
            }
        )
    return out


def ensure_default(c, ws, actor, pid, project_name):
    """Default suite = all ready tasks after the latest export, project rules, default data plan. A new export that
    changes the ready task set saves a new default version."""
    suite = c.execute(
        "SELECT * FROM suites.suites WHERE workspace_id=%s AND project_id=%s AND is_default",
        (ws, pid),
    ).fetchone()
    if not suite:
        sv_id = create_suite(c, ws, actor, pid, f"{project_name} default", is_default=True)
    else:
        latest = c.execute(
            """SELECT id FROM suites.suite_versions WHERE workspace_id=%s AND project_id=%s AND suite_id=%s AND state='saved'
                              ORDER BY version DESC LIMIT 1""",
            (ws, pid, suite["suite_id"]),
        ).fetchone()
        ready = {r["id"] for r in _ready_tasks(c, ws, pid)}
        current = (
            {
                r["task_import_id"]
                for r in c.execute(
                    "SELECT task_import_id FROM suites.suite_tasks WHERE suite_version_id=%s",
                    (latest["id"],),
                ).fetchall()
            }
            if latest
            else set()
        )
        if latest and ready == current:
            v = c.execute(
                "SELECT version, suite_id FROM suites.suite_versions WHERE id=%s", (latest["id"],)
            ).fetchone()
            return f"{v['suite_id']}-v{v['version']}"
        sv_id = new_draft(c, ws, actor, pid, suite["suite_id"])
    sv = _sv(c, ws, sv_id)
    if not checklist(c, ws, sv)["can_run"]:
        c.execute(
            "UPDATE suites.data_plans SET missing_policy='use_available' WHERE suite_version_id=%s",
            (sv_id,),
        )
    try:
        saved = save(c, ws, actor, sv_id)
    except GymError:
        return None
    return saved["label"]
