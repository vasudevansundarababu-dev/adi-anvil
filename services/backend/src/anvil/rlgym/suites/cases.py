"""E-005 §3.1: the cases behind a suite's data plan, from Studio's registry.

- `case_set`: the exact cases the plan picks (the same selection admission makes: plan, cells, the environment's case
  rows, only cases a suite task takes), with which task takes each.
- `browse`: every case of the bound environment version, filtered (application type, completeness, edge case,
  family), paged by Studio.
- `case_detail`: one case's records and its expected outcome (reference answers). Owner decision: the RL Engineer may
  see expected outcomes (to debug graders) but never edit them; only RL Engineers and Admins, every read audited.
  This is a person's read in the RL Gym's UI; it never goes near an agent (hidden-reference isolation holds).
"""

from anvil.rlgym import integrations
from anvil.rlgym.common import GymError, audit, require
from anvil.rlgym.suites import header

VIEWERS = ("rl_engineer", "admin")


def _sv_env(c, ws, sv_id):
    sv = c.execute(
        "SELECT * FROM suites.suite_versions WHERE workspace_id=%s AND id=%s", (ws, sv_id)
    ).fetchone()
    if not sv:
        raise GymError("NOT_FOUND", "Suite version not found")
    env = c.execute(
        "SELECT id, registry, case_catalog FROM catalog.environment_versions WHERE id=%s",
        (sv["planned_on_env_version"],),
    ).fetchone()
    require(env, "CONFLICT", "The suite version is not planned on an environment version yet")
    return sv, env


def _rows(env):
    from anvil.rlgym.suites import service as suites

    suites.edge_counts(env)  # reads and caches the version's case rows (immutable per version)
    rows = suites._ROWS.get(env["id"])
    if rows is None:
        rows = integrations.registry_get(f"/versions/{env['id']}/cases", base=env.get("registry"))[
            "cases"
        ]
        suites._ROWS[env["id"]] = rows
    return rows


def case_set(c, ws, sv_id):
    from anvil.rlgym.runs import sampling

    sv, env = _sv_env(c, ws, sv_id)
    plan = c.execute(
        "SELECT * FROM suites.data_plans WHERE suite_version_id=%s", (sv_id,)
    ).fetchone()
    require(plan, "CONFLICT", "The suite version has no data plan")
    cells = c.execute(
        "SELECT * FROM suites.data_plan_cells WHERE suite_version_id=%s ORDER BY cell_key", (sv_id,)
    ).fetchall()
    tasks = c.execute(
        """SELECT t.id, t.task_id, t.revision, t.case_selector FROM suites.suite_tasks s
           JOIN projects.task_imports t ON t.id=s.task_import_id WHERE s.suite_version_id=%s ORDER BY t.task_id""",
        (sv_id,),
    ).fetchall()
    selected, counts, short = sampling.select_cases(plan, cells, _rows(env), tasks or None)
    out = []
    for case in selected:
        task = sampling.match_task(case, tasks, plan["sampling_seed"]) if tasks else None
        out.append(
            {
                "case_id": case["case_id"],
                "application_type": case.get("application_type"),
                "completeness": case.get("completeness"),
                "edge_cases": case.get("edge_cases") or [],
                "edge_families": case.get("edge_families") or [],
                "task": task and {"task_id": task["task_id"], "revision": task["revision"]},
            }
        )
    return {
        "environment": env["id"],
        # D-047: an unnamed set gets "Set A", "Set B"... per seed, in the order this suite first used it.
        "case_set": plan.get("case_set_name")
        or header.default_case_set_name(c, ws, sv, plan["sampling_seed"]),
        "sampling_seed": plan["sampling_seed"],
        "cases": out,
        "short": short,
        "every_case_matches_a_task": bool(out) and all(x["task"] for x in out),
    }


def browse(c, ws, sv_id, filters, offset=0, limit=50):
    _, env = _sv_env(c, ws, sv_id)
    params = {
        k: v
        for k, v in (filters or {}).items()
        if k in ("application_type", "completeness", "edge_case", "family") and v
    }
    params.update(offset=max(int(offset or 0), 0), limit=min(max(int(limit or 50), 1), 200))
    got = integrations.registry_get(
        f"/versions/{env['id']}/cases", params=params, base=env.get("registry")
    )
    return {"environment": env["id"], **got}


def case_detail(ctx, sv_id, case_id):
    """Records and the expected outcome of one case, read-only, for an RL Engineer or Admin; audited."""
    ctx.actor.require_person()
    require(
        ctx.actor.profile in VIEWERS,
        "FORBIDDEN",
        "Only an RL Engineer or Admin can see a case's expected outcome",
    )
    _, env = _sv_env(ctx.c, ctx.ws, sv_id)
    got = integrations.registry_get(
        f"/versions/{env['id']}/cases/{case_id}",
        base=env.get("registry"),
        headers={
            "X-ADI-Audience": "engineer",
            "X-ADI-Viewer-Id": str(ctx.actor.id),
            "X-ADI-Viewer-Role": ctx.actor.profile,
        },
    )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "case.expected_outcome_viewed",
        f"{env['id']}:{case_id}",
        details={"suite_version_id": str(sv_id)},
    )
    return {"environment": env["id"], "read_only": True, **got}


# --- E-005 §3.2 / E-001 §6b: edge-case families ------------------------------------------------------------------


def _env_key(c, env_id):
    row = c.execute(
        "SELECT contract_id FROM catalog.environment_versions WHERE id=%s", (env_id,)
    ).fetchone()
    return (row or {}).get("contract_id") or env_id.split("@")[0]


def edge_catalog(c, ws, sv_id):
    """Studio's edge-case catalog for the bound environment, grouped by family, with how many cases of each variant the
    bound version has (counted from its cases, D-038)."""
    from anvil.rlgym.suites import service as suites

    _, env = _sv_env(c, ws, sv_id)
    key = _env_key(c, env["id"])
    cat = integrations.registry_get(f"/environments/{key}/edge-case-catalog")
    counts = suites.edge_counts(env) or {}
    families = []
    for f in cat.get("families") or []:
        variants = [
            {
                **{
                    k: v.get(k)
                    for k in (
                        "tag",
                        "kind",
                        "name",
                        "state",
                        "products",
                        "outcome_status",
                        "available_in",
                        "minimum_per_product",
                        "context",
                        "twist",
                    )
                },
                "available": (counts.get(v.get("tag")) or {}).get("available", 0),
                "in_this_version": v.get("tag") in counts,
            }
            for v in cat.get("variants") or []
            if v.get("family_id") == f.get("family_id")
        ]
        families.append(
            {
                **{k: f.get(k) for k in ("family_id", "name", "description", "state", "products")},
                "variants": variants,
            }
        )
    return {
        "environment": env["id"],
        "environment_key": key,
        "revision": cat.get("revision"),
        "families": families,
    }


def request_variant(ctx, sv_id, body, idempotency_key):
    """An RL Engineer proposes a variant or boundary case inside an existing family (E-001 §6b). Studio checks
    feasibility and opens the inbox item; the RL Engineer never sets the expected outcome (SMEs do)."""
    ctx.actor.require_person()
    require(
        ctx.actor.profile in VIEWERS,
        "FORBIDDEN",
        "Only an RL Engineer or Admin can request an edge-case variant",
    )
    require(body.get("family_id"), "VALIDATION_FAILED", "Choose a family", field="family_id")
    require(
        body.get("kind") in ("variant", "boundary"),
        "VALIDATION_FAILED",
        "Kind is variant or boundary",
        field="kind",
    )
    require(
        (body.get("name") or "").strip(),
        "VALIDATION_FAILED",
        "Give the variant a name",
        field="name",
    )
    require(
        (body.get("reason") or "").strip(), "VALIDATION_FAILED", "Give a reason", field="reason"
    )
    require(
        "outcome" not in body,
        "FORBIDDEN",
        "Expected outcomes are written by SMEs, not in the RL Gym",
    )
    _, env = _sv_env(ctx.c, ctx.ws, sv_id)
    key = _env_key(ctx.c, env["id"])
    payload = {
        k: body.get(k)
        for k in (
            "family_id",
            "tag",
            "kind",
            "name",
            "context",
            "twist",
            "products",
            "recipe",
            "minimum_per_product",
            "expected_revision",
            "reason",
        )
        if body.get(k) is not None
    }
    payload["proposed_by"] = {
        "actor_id": str(ctx.actor.id),
        "name": getattr(ctx.actor, "name", None) or str(ctx.actor.id),
        "role": ctx.actor.profile,
        "request_id": idempotency_key,
    }
    got = integrations.registry_post(
        f"/environments/{key}/edge-case-variants",
        payload,
        headers={"Idempotency-Key": idempotency_key},
    )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "edge_variant.requested",
        f"{key}:{body.get('family_id')}",
        body.get("reason"),
        {"name": body.get("name"), "kind": body.get("kind"), "studio": got},
    )
    return got


def write_recipe(ctx, sv_id, tag, body, idempotency_key):
    """Studio b5e925e: an SME variant waiting for a recipe gets one from the RL Engineer (the SME's outcome is not
    touched; Studio runs feasibility at once)."""
    ctx.actor.require_person()
    require(
        ctx.actor.profile in VIEWERS, "FORBIDDEN", "Only an RL Engineer or Admin writes a recipe"
    )
    recipe = body.get("recipe")
    require(
        isinstance(recipe, list) and recipe,
        "VALIDATION_FAILED",
        "A recipe is a list of conditions",
        field="recipe",
    )
    require(
        "outcome" not in body,
        "FORBIDDEN",
        "Expected outcomes are written by SMEs, not in the RL Gym",
    )
    _, env = _sv_env(ctx.c, ctx.ws, sv_id)
    key = _env_key(ctx.c, env["id"])
    payload = {
        k: body[k]
        for k in ("expected_revision", "recipe", "products", "minimum_per_product")
        if body.get(k) is not None
    }
    payload["written_by"] = {
        "actor_id": str(ctx.actor.id),
        "name": getattr(ctx.actor, "name", None) or str(ctx.actor.id),
        "role": ctx.actor.profile,
        "request_id": idempotency_key,
    }
    got = integrations.registry_post(
        f"/environments/{key}/edge-case-variants/{tag}/recipe",
        payload,
        headers={"Idempotency-Key": idempotency_key},
    )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "edge_variant.recipe_written",
        f"{key}:{tag}",
        None,
        {"studio": got},
    )
    return got
