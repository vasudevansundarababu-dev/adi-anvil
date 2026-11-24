"""E-006 §3: the Trust & Safety category table for a suite version.

For each category: what it tests, whether it applies here (computed from the tools the suite's tasks use and which of
the environment's operations reach the customer, from Studio's operation audience), severity, its prompts (with where
each is delivered on this environment, its source, approval and recent results), which layer grades it, and whether it
can be graded on this environment (D-035's declared needs).
"""

from anvil.rlgym import integrations
from anvil.rlgym.scoring import safety
from anvil.rlgym.suites import environment

RULES = {
    "aml_tipping_off": (("screening.check",), True, "screening and a customer-facing request"),
    "personal_data_leakage": ((), True, "a customer-facing request that could carry personal data"),
    "structuring_advice": ((), True, "a customer-facing request where advice could be given"),
    "sanctions_evasion": (("screening.check",), False, "screening"),
    "social_engineering_takeover": (
        ("identity.check", "recommend"),
        False,
        "identity checks and a recommendation",
    ),
    "decision_authority": (
        ("recommend",),
        False,
        "a recommendation the agent might replace with a decision",
    ),
    "evidence_integrity": (("finding.write",), False, "findings that cite evidence"),
    "indirect_prompt_injection": (("document.read",), False, "documents the agent reads"),
    "over_refusal": (("recommend",), False, "a recommendation that must be made"),
    "assigned_case_isolation": ((), False, "an environment holding many cases"),
    "system_prompt_extraction": ((), False, "instructions the agent holds"),
}


def _customer_facing(env):
    try:
        got = integrations.registry_get(
            f"/versions/{env['id']}/operation-audience", base=env.get("registry")
        )
        return set(got.get("customer_facing") or []), got.get("source") or "studio"
    except Exception:
        return set(
            safety.CUSTOMER_TOOLS
        ), "rlgym default (Studio's operation audience not available)"


def applies(key, tools, customer):
    rule = RULES.get(key)
    if not rule:
        return "Partly", "no rule for this category: check by hand"
    need, needs_customer, what = rule
    missing = [t for t in need if t not in tools]
    reach = sorted(customer & tools) if needs_customer else []
    if missing:
        return "No", f"the tasks don't use {', '.join(missing)} (needs {what})"
    if needs_customer and not reach:
        return (
            "Partly",
            f"no customer-facing operation in the tasks; only the final answer can carry it (needs {what})",
        )
    return "Yes", f"the tasks have {what}" + (f" ({', '.join(reach)})" if reach else "")


def table(c, ws, sv_id):
    sv = c.execute(
        "SELECT * FROM suites.suite_versions WHERE workspace_id=%s AND id=%s", (ws, sv_id)
    ).fetchone()
    env = (
        c.execute(
            "SELECT id, registry, operations, schema, image_recipe FROM catalog.environment_versions WHERE id=%s",
            (sv["planned_on_env_version"],),
        ).fetchone()
        or {}
    )
    tasks = c.execute(
        """SELECT p.content actor FROM suites.suite_tasks s JOIN projects.task_imports t ON t.id=s.task_import_id
           LEFT JOIN projects.task_payloads p ON p.workspace_id=t.workspace_id AND p.package_sha256=t.package_sha256 AND p.part='actor'
           WHERE s.suite_version_id=%s""",
        (sv_id,),
    ).fetchall()
    tools = set().union(*[environment.task_tools(t["actor"]) for t in tasks]) if tasks else set()
    customer, audience_source = _customer_facing(env) if env else (set(), "no environment")
    plan = c.execute("SELECT * FROM suites.ts_plans WHERE suite_version_id=%s", (sv_id,)).fetchone()
    cats = c.execute(
        "SELECT * FROM suites.ts_categories WHERE suite_version_id=%s ORDER BY category_group, key",
        (sv_id,),
    ).fetchall()
    prompts = c.execute(
        "SELECT * FROM suites.ts_prompts WHERE suite_version_id=%s ORDER BY category_key, id",
        (sv_id,),
    ).fetchall()
    # Where this suite's attacks will reach the agent on the next run (E-006: OpenEnv now carries "tool_result").
    from anvil.rlgym.runs import openenv

    placement = (plan or {}).get("placement")
    delivered = (
        (placement if not openenv.is_openenv(env) or placement == "tool_result" else "user_message")
        if plan
        else None
    )
    recent = {}
    for r in c.execute(
        """SELECT o.category_key, o.outcome, count(*) n FROM scoring.safety_outcomes o
           JOIN runs.episodes e ON e.id=o.episode_id JOIN runs.runs r ON r.id=e.run_id
           WHERE r.workspace_id=%s AND r.suite_version_id=%s GROUP BY 1,2""",
        (ws, sv_id),
    ).fetchall():
        recent.setdefault(r["category_key"], {})[r["outcome"]] = r["n"]
    rows = []
    for cat in cats:
        verdict, why = applies(cat["key"], tools, customer)
        gradable, grade_why = safety.can_grade(cat["key"], env)
        mine = [p for p in prompts if p["category_key"] == cat["key"]]
        rows.append(
            {
                "key": cat["key"],
                "name": cat["name"],
                "group": cat["category_group"],
                "what_it_tests": cat["boundary_tested"],
                "applies": verdict,
                "applies_why": why,
                "severity": sorted({p["severity"] for p in mine}) or None,
                "prompts": [
                    {
                        "id": p["id"],
                        "text": p["text"],
                        "strategy": p["strategy"],
                        "severity": p["severity"],
                        "approved": p["approved"],
                        "delivered_as": delivered,
                    }
                    for p in mine
                ],
                "source": (plan or {}).get("generator"),
                "approved_by": (plan or {}).get("approved_by"),
                "approved_at": (plan or {}).get("approved_at"),
                "grader": f"{safety.GRADER} (action checks; no model)",
                "can_be_graded": gradable,
                "can_be_graded_why": grade_why,
                "include_default": verdict != "No" and gradable,
                "recent": recent.get(cat["key"], {}),
            }
        )
    return {
        "environment": env.get("id"),
        "operation_audience": {"source": audience_source, "customer_facing": sorted(customer)},
        "placement": (plan or {}).get("placement"),
        "delivered_as": delivered,
        "categories": rows,
    }
