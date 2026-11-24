"""Runs (SPEC 07.5, 07.6a; SCREENS 3.17-3.21; ARCHITECTURE 7.3).

New run picks a saved suite version, a model set, attempts, timeout, retries and a budget. The admission checklist
lists every failing item, not just the first. Start run re-checks everything, probes stale models, stores a refused run
with its reasons, or freezes the manifest (template, suite, the environment and evaluator versions bound now by rule,
the selected cases, the approved safety prompts, tasks and exact model versions) and queues the episodes. Nothing in a
manifest changes afterwards, even when a version is later revoked.

Only the controlled mock provider can run here (live provider calls are not approved on this machine); every run says
so, and its scores are synthetic, never model performance.
"""

import datetime as dt
import statistics

from psycopg.types.json import Jsonb

from anvil.rlgym import integrations
from anvil.rlgym.catalog import selection
from anvil.rlgym.common import GymError, audit, emit, new_id, require, sha
from anvil.rlgym.runs import aliasing, clauses, images, instructions, openenv, sampling
from anvil.rlgym.scoring import s7
from anvil.rlgym.scoring import service as scoring
from anvil.rlgym.suites import service as suites
from anvil.rlgym.systems import service as systems

RUNNERS = ("admin", "rl_engineer")
LIVE_NOTE = (
    "Live model run on synthetic cases, under the owner's approval (provider, model, caps): real model calls, real "
    "spend; the cases are synthetic."
)
MOCK_NOTE = (
    "Controlled mock agents (predetermined behaviour profiles, no model called): synthetic results, not model "
    "performance."
)


def _can_run(actor):
    actor.require_person()
    require(actor.profile in RUNNERS, "FORBIDDEN", "Viewers cannot start, cancel or re-score runs")


def _int(body, name, default, low, high):
    value = body.get(name, default)
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if low <= value <= high else None


def _members(ctx, body):
    ms = body.get("model_set") or {}
    if ms.get("members"):
        members = sorted({(m["system_id"], int(m["system_version"])) for m in ms["members"]})
        return {"id": "custom", "version": None, "name": "Custom", "custom": True}, members
    if not ms.get("id"):
        return None, []
    row = ctx.c.execute(
        "SELECT * FROM systems.model_sets WHERE workspace_id=%s AND id=%s"
        + (" AND version=%s" if ms.get("version") else "")
        + " ORDER BY version DESC LIMIT 1",
        (ctx.ws, ms["id"], int(ms["version"])) if ms.get("version") else (ctx.ws, ms["id"]),
    ).fetchone()
    if not row:
        return None, []
    members = [
        (m["system_id"], m["system_version"])
        for m in ctx.c.execute(
            "SELECT * FROM systems.model_set_members WHERE workspace_id=%s AND model_set_id=%s AND model_set_version=%s ORDER BY system_id",
            (ctx.ws, row["id"], row["version"]),
        ).fetchall()
    ]
    return {
        "id": row["id"],
        "version": row["version"],
        "name": row["name"],
        "custom": False,
    }, members


def _model_line(ctx, system_id, version):
    system = ctx.c.execute(
        "SELECT * FROM systems.systems WHERE workspace_id=%s AND system_id=%s", (ctx.ws, system_id)
    ).fetchone()
    v = ctx.c.execute(
        "SELECT * FROM systems.system_versions WHERE workspace_id=%s AND system_id=%s AND version=%s",
        (ctx.ws, system_id, version),
    ).fetchone()
    if not system or not v:
        return {
            "system_id": system_id,
            "version": version,
            "ok": False,
            "problem": "does not exist",
        }
    status = systems._status(ctx, system, version)
    problem, live = None, None
    if not system["enabled"]:
        problem = f"disabled ({system['disabled_reason']})"
    elif v["provider"] != "mock":
        live, problem = _live_line(ctx, v)
    elif status not in ("Ready", "Not tested in 24 h"):
        problem = status
    if v["provider"] == "mock":
        key = ctx.c.execute(
            "SELECT status FROM systems.provider_keys WHERE workspace_id=%s AND id=%s",
            (ctx.ws, v["key_id"]),
        ).fetchone()
        if not problem and (not key or key["status"] != "valid"):
            problem = "KEY_MISSING: its provider key is not valid"
    return {
        "system_id": system_id,
        "version": version,
        "name": system["name"],
        "provider": v["provider"],
        "model_id": v["model_id"],
        "config_sha256": v["config_sha256"],
        "synthetic": system["synthetic"],
        "status": status,
        "spend_per_episode_usd": float((v["limits"] or {}).get("spend_per_episode_usd", 0)),
        "live": live,
        "ok": problem is None,
        "problem": problem,
    }


def _live_line(ctx, v):
    """A live model can run only with the live flag on, its key present through the allowlist (or ADC for Vertex),
    and an active approval for exactly this provider and model, recorded by an Admin who is not the person starting
    the run. Returns (live settings frozen into the manifest, problem)."""
    from anvil.rlgym.live import approvals, gateway

    if not gateway.live_enabled():
        return (
            None,
            "live provider calls are disabled locally (ANVIL_LIVE_PROVIDERS_ENABLED is not true)",
        )
    name = gateway.KEY_NAMES.get(v["provider"])
    if name:
        present, why = gateway.key_source(name)
        if not present:
            return None, f"KEY_MISSING: {name} ({why}); keys are read only from the allowlist"
    a = approvals.find(ctx.c, ctx.ws, v["provider"], v["model_id"], "agent", v.get("hf_revision"))
    if not a:
        return None, f"no active live approval for {v['provider']} {v['model_id']} (agent)"
    if str(a["approved_by"]) == str(ctx.actor.id):
        return None, f"the approver of {a['id']} cannot also start this run"
    return {
        "approval_id": a["id"],
        "per_run_cap_usd": float(a["per_run_cap_usd"]),
        "price_in_per_mtok_usd": float(a["price_in_per_mtok_usd"]),
        "price_out_per_mtok_usd": float(a["price_out_per_mtok_usd"]),
        "params": v["params"] or {},
        "serving": v["serving"] or {},
        "hf_revision": v.get("hf_revision"),
    }, None


def admission_check(ctx, body):
    """Every item of the checklist (SCREENS 3.18), plus everything Start run freezes into the manifest."""
    items = []
    resolved = {}

    def item(key, ok, label, detail=None):
        items.append({"key": key, "ok": bool(ok), "label": label, "detail": detail})
        return ok

    name = (body.get("name") or "").strip()
    item("name", name, "Run name" if name else "Enter a run name")
    attempts = _int(body, "attempts", 1, 1, 10)
    timeout_min = _int(body, "episode_timeout_min", 10, 1, 120)
    retries = _int(body, "infra_retries", 2, 0, 5)
    item(
        "settings",
        None not in (attempts, timeout_min, retries),
        "Attempts 1–10, timeout at least 1 minute, retries 0–5",
    )
    try:
        budget = float(body.get("budget_usd", 0))
    except (TypeError, ValueError):
        budget = 0.0
    pid = body.get("project_id")
    project = (
        ctx.c.execute(
            "SELECT * FROM projects.projects WHERE workspace_id=%s AND project_id=%s", (ctx.ws, pid)
        ).fetchone()
        if pid
        else None
    )
    sv = None
    if body.get("suite_version_id"):
        try:
            sv = suites._sv(ctx.c, ctx.ws, body["suite_version_id"])
        except GymError:
            sv = None
    if not project:
        item("project", False, "Choose a project")
    if not sv or (project and sv["project_id"] != project["project_id"]):
        item("suite", False, "Choose a saved suite version of this project")
        sv = None
    elif sv["state"] != "saved":
        item("suite", False, "Save the suite version first (a draft cannot run)")
    else:
        item("suite", True, f"Suite {sv['suite_id']} v{sv['version']}", sv["suite_sha256"][:12])
    activation = None
    if project:
        activation = ctx.c.execute(
            "SELECT * FROM catalog.template_activations WHERE workspace_id=%s AND template_id=%s AND version=%s",
            (ctx.ws, project["template_id"], project["template_version"]),
        ).fetchone()
        item(
            "template",
            activation and activation["state"] == "active",
            "Template active",
            f"{project['template_id']} v{project['template_version']} is "
            + (activation["state"] if activation else "not activated")
            if not activation or activation["state"] != "active"
            else f"{activation['name']} · {activation['template_sha256'][:12]}",
        )
    ms_label, members = _members(ctx, body)
    lines = [_model_line(ctx, s, v) for s, v in members]
    resolved.update(project=project, sv=sv, activation=activation, model_set=ms_label, models=lines)
    if sv and project and sv["state"] == "saved":
        tasks = ctx.c.execute(
            """SELECT t.*, p.content actor FROM suites.suite_tasks s JOIN projects.task_imports t ON t.id=s.task_import_id
               LEFT JOIN projects.task_payloads p ON p.workspace_id=t.workspace_id AND p.package_sha256=t.package_sha256
                 AND p.part='actor'
               WHERE s.suite_version_id=%s ORDER BY t.task_id""",
            (sv["id"],),
        ).fetchall()
        not_ready = [
            f"{t['task_id']} r{t['revision']} is {t['state']}"
            for t in tasks
            if t["state"] != "ready"
        ]
        # D-007: every task must yield agent instructions (assignment or sections); a run never uses a fallback.
        for t in tasks:
            why = instructions.problem(t["actor"])
            if why:
                not_ready.append(f"{t['task_id']} r{t['revision']}: {why}")
            else:
                t["instructions_sha256"] = instructions.build(
                    t["actor"], clauses.task_clauses(t["actor"], t)
                )["sha256"]
        now_ready = {
            r["id"]
            for r in ctx.c.execute(
                "SELECT id FROM projects.task_imports WHERE workspace_id=%s AND project_id=%s AND state='ready'",
                (ctx.ws, project["project_id"]),
            ).fetchall()
        }
        missing = len(now_ready - {t["id"] for t in tasks})
        detail = "; ".join(not_ready[:5])
        if missing:
            detail = (detail + "; " if detail else "") + (
                f"{missing} ready tasks are not in this suite version; save a new suite version"
            )
        item(
            "tasks",
            tasks and not not_ready and not missing,
            f"Tasks ready ({len(tasks)} — all ready tasks of the project)",
            detail or None,
        )
        # D-036 (E-007 §7.1): each task is scored with its published S7 (anchors, weights, threshold, critical
        # criteria). The profile is read from the task's private part now and frozen in the manifest. A task whose S7
        # can't be read as points (e.g. v6's 100-point allocation) keeps the RL Gym's scale, and admission and the
        # report say so by task; tasks without an S7 (fixtures, stub exports) keep it too.
        unreadable = []
        for t in tasks:
            private = ctx.c.execute(
                "SELECT content FROM projects.task_payloads WHERE workspace_id=%s AND package_sha256=%s AND part='private'",
                (ctx.ws, t["package_sha256"]),
            ).fetchone()
            s7_section = (
                (((private or {}).get("content") or {}).get("authored") or {}).get("sections") or {}
            ).get("S7")
            if s7_section is None:
                continue
            prof, why = s7.profile(s7_section)
            if prof:
                t["scoring"] = prof
            else:
                t["scoring_unreadable"] = why
                unreadable.append(f"{t['task_id'][:8]} r{t['revision']}: {why}")
        if any(t.get("scoring") for t in tasks) or unreadable:
            first = next((t["scoring"] for t in tasks if t.get("scoring")), None)
            item(
                "scoring_rule",
                True,
                (
                    "Scored with each task's S7"
                    + (
                        f" ({first['anchors']['pass']:g}/{first['anchors']['partial']:g}/{first['anchors']['fail']:g}"
                        f" points, pass at {first['threshold_points']:g} of {first['max_points']:g})"
                        if first
                        else ""
                    )
                )
                if not unreadable
                else f"S7 read for {sum(1 for t in tasks if t.get('scoring'))} of {len(tasks)} tasks",
                (
                    "RL Gym scale (pass 1, fail 0, pass mark "
                    f"{float(activation['pass_mark']) if activation else 90:g}%) for: "
                    + "; ".join(unreadable[:5])
                )
                if unreadable
                else None,
            )
        resolved["tasks"] = tasks
        # E-002: every selected clause must be valid; its setup gaps are checked once the environment is known.
        clause_tasks = [t for t in tasks if clauses.task_clauses(t["actor"], t)]
        bindings = ctx.c.execute(
            "SELECT * FROM suites.suite_bindings WHERE suite_version_id=%s ORDER BY alias",
            (sv["id"],),
        ).fetchall()
        resolved["experiment"] = any(b["source"] == "experiment" for b in bindings)
        env = None
        for b in bindings:
            pick, code, reason, effective = suites.resolve_binding(
                ctx.c, ctx.ws, project["project_id"], b
            )
            label = (
                "Follow project rules · " if b["rule_kind"] == "project_rule" else "Custom · "
            ) + selection.rule_label(effective)
            item(
                f"environment:{b['alias']}",
                pick,
                "Environments qualified",
                f"alias {b['alias']} · {label} → "
                + (
                    f"{selection.short(pick['id'])} · seed family {pick['seed_family']}"
                    if pick
                    else f"{code}: {reason}"
                ),
            )
            if pick and env is None:
                env = {"binding": b, "version": pick, "rule": effective, "rule_label": label}
        resolved["env"] = env
        if clause_tasks and env:
            # E-002 §9.2: a tool or evidence source a selected clause needs is a setup gap; it blocks the run here.
            pb = (resolved.get("activation") or {}).get("policy_bindings")
            resolved["policy_bindings"] = pb
            gaps = clauses.admission_gaps(clause_tasks, env["version"], pb)
            item(
                "policy_clauses",
                not gaps,
                f"Policy clauses can be evaluated on {selection.short(env['version']['id'])}"
                if not gaps
                else "Setup gap: a selected clause cannot be evaluated (fix before the run)",
                "; ".join(f"{g['task_id']} · {g['clause']}: {g['detail']}" for g in gaps) or None,
            )
            zen = ctx.c.execute(
                """SELECT manifest FROM catalog.framework_versions
                   WHERE runtime_id=%s AND state='qualified' AND manifest IS NOT NULL ORDER BY created_at DESC LIMIT 1""",
                (clauses.ZEN_PLUGIN,),
            ).fetchone()
            resolved["clause_engine"] = zen and zen["manifest"]
        ok_docker, docker_detail = images.docker_status()
        env_row = (
            ctx.c.execute(
                "SELECT * FROM catalog.environment_versions WHERE id=%s", (env["version"]["id"],)
            ).fetchone()
            if env
            else None
        )
        image = None
        if env and openenv.is_openenv(env_row):
            # Studio built this image; the RL Gym only checks that the exact registered image is in local Docker.
            detail, found = docker_detail, None
            if ok_docker:
                try:
                    found = openenv.check_image(env_row, openenv.recipe(env_row))
                    detail = f"Studio-built {env_row['image_recipe']['image_ref']} · {found[:19]}"
                except GymError as exc:
                    detail = exc.message
            item("image", bool(found), "Environment image present locally", detail)
        elif env:
            image = images.built(ctx.c, env["version"]["id"]) if ok_docker else None
            base_ok = ok_docker and images.image_present(images.base_image())
            item(
                "image",
                ok_docker and (image or base_ok),
                "Environment image built locally",
                (
                    f"{image['image_tag']} · {image['local_image_id'][:19]}"
                    if image
                    else "built at Start from the Studio recipe (no network)"
                    if base_ok
                    else f"{docker_detail}; pinned base image present: {base_ok}"
                ),
            )
        resolved["env_row"] = env_row
        resolved["image"] = image
        evaluator_versions, bad = [], []
        criteria = {
            r["criterion_id"]: r
            for r in ctx.c.execute(
                "SELECT * FROM catalog.template_criteria WHERE workspace_id=%s AND template_id=%s AND version=%s",
                (ctx.ws, project["template_id"], project["template_version"]),
            ).fetchall()
        }
        for b in ctx.c.execute(
            "SELECT * FROM suites.suite_criterion_bindings WHERE suite_version_id=%s ORDER BY criterion_id",
            (sv["id"],),
        ).fetchall():
            pick, code, reason = suites.resolve_criterion(ctx.c, ctx.ws, project["project_id"], b)
            fw = (
                ctx.c.execute(
                    "SELECT * FROM catalog.framework_versions WHERE id=%s",
                    (pick["framework_version_id"],),
                ).fetchone()
                if pick
                else None
            )
            if not pick:
                bad.append(f"{b['criterion_id']}: {reason}")
                continue
            if not fw["installed_locally"] or fw["state"] == "revoked":
                bad.append(f"{pick['id']} v{pick['version']}: framework {fw['id']} cannot run here")
                continue
            crit = criteria.get(b["criterion_id"], {})
            evaluator_versions.append(
                {
                    "criterion_id": b["criterion_id"],
                    "configuration_id": pick["id"],
                    "version": pick["version"],
                    "config_sha256": pick["config_sha256"],
                    "framework": fw["id"],
                    "weight": float(crit.get("weight", pick["weight"])),
                    "is_gate": bool(crit.get("is_gate", False)),
                    "capability": pick["capability"],
                    "skill_group": crit.get("skill_group"),
                    "rule": b["rule_kind"],
                }
            )
        frameworks = sorted({e["framework"] for e in evaluator_versions})
        item(
            "evaluators",
            evaluator_versions and not bad,
            f"Evaluators qualified ({len(evaluator_versions)} configurations · {', '.join(frameworks) or 'none'})",
            "; ".join(bad) or None,
        )
        resolved["evaluator_versions"] = evaluator_versions
        # Verifier plug-ins (D22): each plug-in block binds a qualified version now; the manifest freezes it.
        from anvil.rlgym.plugins import service as plugins

        bound_plugins, unbound = {}, []
        for cr in criteria.values():
            for b in cr.get("verifier_blocks") or []:
                if not b.get("plugin"):
                    continue
                row = plugins.resolve(ctx.c, b["plugin"])
                if row:
                    bound_plugins[b["id"]] = {
                        "plugin_id": row["runtime_id"],
                        "version": row["version"],
                        "framework_version_id": row["id"],
                        "image": row["image_digest"],
                        "manifest_sha256": row["manifest_sha256"],
                    }
                else:
                    unbound.append(f"{b['id']}: no qualified {b['plugin'].get('id')}")
        if bound_plugins or unbound:
            item(
                "plugins",
                not unbound,
                "Verifier plug-ins qualified",
                "; ".join(unbound)
                or ", ".join(
                    sorted({f"{v['plugin_id']} {v['version']}" for v in bound_plugins.values()})
                ),
            )
        resolved["plugins"] = bound_plugins
        # D-034: what scores each criterion, frozen in the manifest (configuration, blocks, plug-in versions).
        from anvil.rlgym.results import scorer

        resolved["graders"] = scorer.for_admission(
            ctx.c, ctx.ws, project, resolved.get("evaluator_versions"), bound_plugins
        )
        plan = ctx.c.execute(
            "SELECT * FROM suites.data_plans WHERE suite_version_id=%s", (sv["id"],)
        ).fetchone()
        cells = ctx.c.execute(
            "SELECT * FROM suites.data_plan_cells WHERE suite_version_id=%s ORDER BY cell_key",
            (sv["id"],),
        ).fetchall()
        selected, unmatched, short = [], [], []
        if env and plan:
            case_list = integrations.registry_get(
                f"/versions/{env['version']['id']}/cases", base=env["version"].get("registry")
            )["cases"]
            selected, counts, short = sampling.select_cases(
                plan, cells, case_list, resolved.get("tasks") or None
            )
            # E-001 §3.6: a task focused on an edge case the bound version has no cases for is held before the run.
            holds = clauses.edge_holds(resolved.get("tasks") or [], case_list, env["version"]["id"])
            if holds:
                item(
                    "edge_cases",
                    False,
                    "Held: a task's edge case has no cases in the bound environment version",
                    "; ".join(f"{h['task_id']} ({h['edge_case']}): {h['detail']}" for h in holds),
                )
            tolerated = plan["missing_policy"] == "use_available" or all(
                next(cl for cl in cells if cl["cell_key"] == s["cell_key"])["inbox_item_id"]
                for s in short
            )
            item(
                "data_plan",
                selected and (not short or tolerated),
                f"Data plan fits the bound data ({len(selected)} cases from {selection.short(env['version']['id'])})",
                "; ".join(
                    f"{s['cell_key'].replace('|', ' · ')}: the plan asks for {s['quota']}; the data has {s['picked']}"
                    for s in short
                )
                + (" (runs on what exists)" if short and tolerated else "")
                or None,
            )
        resolved.update(plan=plan, cells=cells, selected=selected, short=short)
        ts = ctx.c.execute(
            "SELECT * FROM suites.ts_plans WHERE suite_version_id=%s", (sv["id"],)
        ).fetchone()
        prompts = []
        if ts and ts["enabled"]:
            prompts = ctx.c.execute(
                "SELECT * FROM suites.ts_prompts WHERE suite_version_id=%s AND approved ORDER BY id",
                (sv["id"],),
            ).fetchall()
            item(
                "trust_and_safety",
                ts["state"] == "approved" and prompts,
                f"Trust & Safety: {len(prompts)} approved prompts"
                if ts["state"] == "approved"
                else "Trust & Safety prompt set approved",
                None if ts["state"] == "approved" else f"Prompt set is {ts['state']}",
            )
        resolved.update(ts=ts, prompts=prompts)
        if clause_tasks and selected:
            # The facts each selected case supplies (Studio's case rows); a missing fact makes a clause Unresolved.
            resolved["case_facts"] = {c["case_id"]: c.get("facts") or {} for c in selected}
        if resolved.get("tasks") and selected:
            specs, unmatched = sampling.expand(
                plan,
                selected,
                resolved["tasks"],
                prompts,
                [(m["system_id"], m["version"]) for m in lines],
                attempts or 1,
            )
            resolved["specs"] = specs
            # A sampled case no task takes never becomes an episode; a run with none would admit and do nothing.
            item(
                "task_match",
                len(unmatched) < len(selected),
                f"Sampled cases match a task ({len(selected) - len(unmatched)} of {len(selected)})",
                None
                if not unmatched
                else f"No task takes {len(unmatched)} sampled case(s): {', '.join(unmatched[:5])}"
                + (" …" if len(unmatched) > 5 else ""),
            )
        resolved["unmatched"] = unmatched
    item(
        "models",
        lines and all(m["ok"] for m in lines),
        "Models reachable" if lines else "Pick at least one model",
        "; ".join(
            f"{m.get('name', m['system_id'])} v{m['version']}: {m['problem']}"
            for m in lines
            if not m["ok"]
        )
        or (
            "; ".join(
                f"{m['name']}: probed at Start"
                for m in lines
                if m.get("status") == "Not tested in 24 h"
            )
            or None
        ),
    )
    # Only cases matched to a task become episodes (and safety prompts need at least one), so the count and the
    # spend projection are of the episodes the run will actually create.
    cases_n = len(resolved.get("selected") or []) - len(resolved.get("unmatched") or [])
    prompts_n = len(resolved.get("prompts") or []) if cases_n else 0
    per_model = [
        {
            "system_id": m["system_id"],
            "version": m["version"],
            "name": m.get("name"),
            "episodes": (cases_n + prompts_n) * (attempts or 1),
            "formula": f"({cases_n} cases + {prompts_n} safety) × {attempts or 1}",
            "spend_per_episode_usd": m.get("spend_per_episode_usd", 0),
            "projected_usd": round(
                (cases_n + prompts_n) * (attempts or 1) * m.get("spend_per_episode_usd", 0), 4
            ),
        }
        for m in lines
    ]
    projected = round(sum(p["projected_usd"] for p in per_model), 4)
    # Live models: the projection (episodes × the version's spend limit per episode, also enforced per call) must fit
    # the approval's per-run cap and what is left of its total cap.
    from anvil.rlgym.live import approvals as live_approvals

    for p, m in zip(per_model, lines, strict=True):
        if not m.get("live"):
            continue
        try:
            live_approvals.require_for(
                ctx.c,
                ctx.ws,
                m["provider"],
                m["model_id"],
                "agent",
                hf_revision=m["live"].get("hf_revision"),
                requested_by=ctx.actor.id,
                estimate_usd=p["projected_usd"],
            )
            item(
                "live_approval",
                True,
                f"{m['name']}: approval {m['live']['approval_id']} covers ${p['projected_usd']:g}",
            )
        except GymError as exc:
            item("live_approval", False, f"{m['name']}: live approval", exc.message)
    item(
        "budget",
        budget > 0 and projected <= budget,
        f"Budget ${budget:g} covers the projected ${projected:g}"
        if budget > 0
        else "Enter a budget cap above $0",
        None
        if budget <= 0 or projected <= budget
        else f"BUDGET_EXCEEDED: projected ${projected:g} is over the ${budget:g} cap",
    )
    # D-034 (E-004 §3.4): a run can count on the leaderboard only when its graders, environment, safety detectors and
    # models are all real and approved. The tick is refused (with the reasons) otherwise.
    eligibility = leaderboard_eligibility(resolved, lines)
    if body.get("leaderboard") is True and not eligibility["eligible"]:
        item(
            "leaderboard",
            False,
            "Leaderboard run: not eligible",
            "; ".join(eligibility["reasons"]),
        )
    episodes = sum(p["episodes"] for p in per_model)
    return {
        "leaderboard": eligibility,
        "passed": all(i["ok"] for i in items),
        "items": items,
        "episodes": episodes,
        "projected_usd": projected,
        "per_model": per_model,
        "execution_mode": "controlled_mock",
        "note": MOCK_NOTE,
        "unmatched_cases": resolved.get("unmatched", []),
        "uses": _uses(resolved),
        "_resolved": resolved,
        "_settings": {
            "attempts": attempts,
            "timeout_min": timeout_min,
            "retries": retries,
            "budget": budget,
            "name": name,
            # D-033: counted on the leaderboard only when the person starting the run ticks it (default: not).
            "leaderboard": body.get("leaderboard") is True,
        },
    }


def _uses(r):
    env = r.get("env")
    plan = r.get("plan")
    return {
        "environment": env
        and {
            "alias": env["binding"]["alias"],
            "rule": env["rule_label"],
            "version_id": env["version"]["id"],
            "seed_family": env["version"]["seed_family"],
        },
        "evaluators": [
            f"{e['configuration_id']} v{e['version']}" for e in r.get("evaluator_versions") or []
        ],
        "data_plan": plan
        and {
            "sample_size": plan["sample_size"],
            "selected": len(r.get("selected") or []),
            "quotas": plan["completeness_quotas"],
            "required_edges": plan["required_edges"],
            "seed": plan["sampling_seed"],
        },
        "trust_and_safety": f"{len(r.get('prompts') or [])} approved prompts"
        if r.get("prompts")
        else "off",
        "tasks": f"all {len(r.get('tasks') or [])} ready tasks of the project",
    }


def leaderboard_eligibility(resolved, lines):
    """{"eligible", "reasons"}: every criterion bound to a qualified grader version, the environment version
    qualified, every Trust & Safety category gradable on that environment (D-035's declared needs), every agent model
    live (not a mock). Approved = qualified until grader promotion (E-004 §3.3) exists."""
    from anvil.rlgym.scoring import safety

    reasons = []
    evs = resolved.get("evaluator_versions") or []
    if not evs:
        reasons.append("no criterion is bound to a qualified grader version")
    env_row = resolved.get("env_row")
    if not env_row:
        reasons.append("no environment version is bound")
    elif env_row.get("state") != "qualified":
        reasons.append(f"environment {env_row.get('id')} is {env_row.get('state')}, not qualified")
    cats = sorted({p["category_key"] for p in resolved.get("prompts") or []})
    bad = [why for cat in cats for ok, why in [safety.can_grade(cat, env_row)] if not ok]
    if bad:
        reasons.append("safety: " + "; ".join(bad))
    if resolved.get("experiment"):
        reasons.append("the suite pins an environment version as an experiment (E-005)")
    mocks = [m.get("name", m["system_id"]) for m in lines or [] if not m.get("live")]
    if mocks:
        reasons.append(f"agent model(s) are mocks, not live: {', '.join(mocks)}")
    if not lines:
        reasons.append("no agent model chosen")
    return {"eligible": not reasons, "reasons": reasons}


def public_check(check):
    return {k: v for k, v in check.items() if not k.startswith("_")}


def _next_id(c):
    return "run-" + f"{c.execute('SELECT nextval(%s) n', ('runs.run_number',)).fetchone()['n']:04d}"


def _manifest(run_id, check):
    r, s = check["_resolved"], check["_settings"]
    env, sv, act = r["env"], r["sv"], r["activation"]
    image = r["image"]
    return {
        "schema": "rlgym.run-manifest.v1",
        "run_id": run_id,
        "execution_mode": "live" if any(m.get("live") for m in r["models"]) else "controlled_mock",
        "synthetic": True,
        # Owner decision 24 Nov 2026 (D-039): on Studio's OpenEnv images the agent sees opaque IDs.
        **(
            {"ids_aliased": True, "id_aliasing": aliasing.VERSION}
            if openenv.is_openenv(r.get("env_row"))
            else {}
        ),
        # D-033: frozen with the run (inside manifest_sha256), so it cannot change after admission.
        "leaderboard": bool(s.get("leaderboard")),
        "note": LIVE_NOTE if any(m.get("live") for m in r["models"]) else MOCK_NOTE,
        "project": {"id": r["project"]["project_id"], "name": r["project"]["name"]},
        "template": {
            "id": act["template_id"],
            "version": act["version"],
            "name": act["name"],
            "template_sha256": act["template_sha256"],
            "pass_mark": float(act["pass_mark"]),
        },
        "suite": {
            "id": str(sv["id"]),
            "suite_id": sv["suite_id"],
            "version": sv["version"],
            "name": sv["name"],
            "suite_sha256": sv["suite_sha256"],
        },
        "environment": {
            "alias": env["binding"]["alias"],
            "version_id": env["version"]["id"],
            "registry_image_digest": env["version"]["image_digest"],
            "seed_family": env["version"]["seed_family"],
            "seed_sha256": env["version"]["seed_sha256"],
            "spec_sha256": env["version"]["spec_sha256"],
            "rule": env["rule_label"],
            "local_image": image and {"tag": image["image_tag"], "id": image["local_image_id"]},
        },
        "evaluators": r["evaluator_versions"],
        # D-034: per criterion, the hash of what scores it and its plain description (absent before D-034).
        **({"graders": r["graders"]} if r.get("graders") else {}),
        "plugins": r.get("plugins") or {},
        "data_plan": {
            "sample_size": r["plan"]["sample_size"],
            "completeness_quotas": r["plan"]["completeness_quotas"],
            "required_edges": r["plan"]["required_edges"],
            "sampling_seed": r["plan"]["sampling_seed"],
            "missing_policy": r["plan"]["missing_policy"],
            "short_cells": r["short"],
            "case_ids": [c["case_id"] for c in r["selected"]],
            "case_ids_sha256": sha([c["case_id"] for c in r["selected"]]),
        },
        "trust_and_safety": {
            "enabled": bool(r["prompts"]),
            "placement": r["ts"]["placement"] if r["prompts"] else None,
            # D-040: where the attack actually reaches the agent. Studio's OpenEnv simulator has no injection point,
            # so every attack is sent with the user message there, whatever placement the suite asked for.
            "delivered_as": (
                ("user_message" if openenv.is_openenv(r.get("env_row")) else r["ts"]["placement"])
                if r["prompts"]
                else None
            ),
            "prompt_set_sha256": r["ts"]["prompt_set_sha256"] if r["prompts"] else None,
            "prompts": [
                {k: p[k] for k in ("id", "category_key", "strategy", "severity", "text")}
                for p in r["prompts"]
            ],
        },
        "tasks": [
            {
                "task_import_id": str(t["id"]),
                "task_id": t["task_id"],
                "revision": t["revision"],
                "package_sha256": t["package_sha256"],
                "case_selector": t["case_selector"],
                # D-007: hash of the instructions the agent is given for this task (built from the actor payload).
                "instructions_sha256": t.get("instructions_sha256"),
                # D-036: the task's S7 scoring profile (numbers and the rule's hash; never the private text).
                **({"scoring": t["scoring"]} if t.get("scoring") else {}),
                **(
                    {"scoring_unreadable": t["scoring_unreadable"]}
                    if t.get("scoring_unreadable")
                    else {}
                ),
                # E-002: the clause versions this task selected, frozen whole (the worker resolves from these, so a
                # run reproduces from its manifest). Absent when none, so manifests stay as before.
                **(
                    {"clauses": clauses.task_clauses(t.get("actor"), t)}
                    if clauses.task_clauses(t.get("actor"), t)
                    else {}
                ),
            }
            for t in r["tasks"]
        ],
        **({"case_facts": r["case_facts"]} if r.get("case_facts") else {}),
        # E-002: the qualified ZEN plug-in that replays each clause decision (frozen here, so receipts reproduce).
        **({"clause_engine": r["clause_engine"]} if r.get("clause_engine") else {}),
        # E-002: the template's policy bindings (fact mapping, needs per clause), frozen with the run.
        **({"policy_bindings": r["policy_bindings"]} if r.get("policy_bindings") else {}),
        "model_set": r["model_set"],
        "models": [
            {
                k: m[k]
                for k in (
                    "system_id",
                    "version",
                    "name",
                    "provider",
                    "model_id",
                    "config_sha256",
                    "synthetic",
                    "live",
                    "spend_per_episode_usd",
                )
                if k in m
            }
            for m in r["models"]
        ],
        "attempts": s["attempts"],
        "episode_timeout_s": s["timeout_min"] * 60,
        "infra_retries": s["retries"],
        "budget_usd": s["budget"],
        "episodes": check["episodes"],
        "episode_formula": "(cases + safety prompts) × models × attempts",
        "projected_usd": check["projected_usd"],
    }


def _fetch_references(ctx, vid, case_ids):
    """Private reference answers for the selected cases, for the scorer only (verified against their hashes)."""
    have = {
        r["case_id"]: r
        for r in ctx.c.execute(
            "SELECT case_id, reference_sha256 FROM scoring.case_references WHERE workspace_id=%s AND environment_version_id=%s",
            (ctx.ws, vid),
        ).fetchall()
    }
    need = [i for i in case_ids if i not in have]
    if not need:
        return
    origin = ctx.c.execute(
        "SELECT registry FROM catalog.environment_versions WHERE id=%s", (vid,)
    ).fetchone()
    got = integrations.registry_get(
        f"/versions/{vid}/references",
        params={"ids": ",".join(need)},
        audience="scorer",
        timeout=30,
        base=origin and origin["registry"],
    )["references"]
    for case_id in need:
        row = got.get(case_id)
        if not row or sha(row["reference"]) != row["reference_sha256"]:
            raise GymError(
                "HASH_MISMATCH",
                f"Reference answer for {case_id} is missing or does not match its hash",
            )
        ctx.c.execute(
            "INSERT INTO scoring.case_references(workspace_id,environment_version_id,case_id,reference,reference_sha256) VALUES(%s,%s,%s,%s,%s)",
            (ctx.ws, vid, case_id, Jsonb(row["reference"]), row["reference_sha256"]),
        )


def start(ctx, body):
    _can_run(ctx.actor)
    check = admission_check(ctx, body)
    r, s = check["_resolved"], check["_settings"]
    if check["passed"]:
        # Stale models are probed first (controlled mock only; a live probe never runs here).
        for m in r["models"]:
            if m["status"] == "Not tested in 24 h" and not m.get("live"):
                probe = systems.probe_system(ctx, m["system_id"], m["version"])
                if probe["result"] != "ok":
                    check["items"].append(
                        {
                            "key": "models",
                            "ok": False,
                            "label": "Models reachable",
                            "detail": f"{m['name']}: probe {probe['result']}",
                        }
                    )
                    check["passed"] = False
    if check["passed"] and not r["image"]:
        # The image is built now (from the Studio recipe, no network) so the frozen manifest names the exact image.
        try:
            vid = r["env"]["version"]["id"]
            r["image"] = (
                openenv.resolve(ctx.c, vid, r["env_row"])
                if openenv.is_openenv(r.get("env_row"))
                else images.build(ctx.c, vid)
            )
        except GymError as exc:
            check["items"].append(
                {
                    "key": "image",
                    "ok": False,
                    "label": "Environment image built locally",
                    "detail": exc.message,
                }
            )
            check["passed"] = False
    run_id = _next_id(ctx.c)
    project_id = r["project"]["project_id"] if r.get("project") else body.get("project_id")
    require(r.get("project"), "VALIDATION_FAILED", "Choose a project", field="project_id")
    require(
        r.get("sv"),
        "VALIDATION_FAILED",
        "Choose a saved suite version of this project",
        field="suite_version_id",
    )
    model_set = {
        "label": r.get("model_set"),
        "members": [{"system_id": m["system_id"], "version": m["version"]} for m in r["models"]],
    }
    common = (
        run_id,
        ctx.ws,
        project_id,
        s["name"] or "(unnamed run)",
        r["sv"]["id"],
        Jsonb(model_set),
        s["attempts"] or 1,
        s["budget"] if s["budget"] > 0 else 0.01,
        (s["timeout_min"] or 10) * 60,
        s["retries"] if s["retries"] is not None else 2,
        ctx.actor.id,
    )
    if not check["passed"]:
        reasons = [
            {"key": i["key"], "label": i["label"], "detail": i["detail"]}
            for i in check["items"]
            if not i["ok"]
        ]
        ctx.c.execute(
            """INSERT INTO runs.runs(id,workspace_id,project_id,name,suite_version_id,model_set,attempts,budget_usd,episode_timeout_s,
                 infra_retries,created_by,execution_mode,state,refusal_reasons) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'controlled_mock','refused',%s)""",
            (*common, Jsonb(reasons)),
        )
        audit(ctx.c, ctx.ws, ctx.actor, "run.refused", run_id, details={"reasons": reasons})
        emit(
            ctx.c,
            ctx.ws,
            "run.refused",
            run_id,
            {"run_id": run_id, "project_id": project_id, "reasons": reasons},
        )
        return {"run": get_run(ctx, run_id), "refused": True, "check": public_check(check)}
    _fetch_references(ctx, r["env"]["version"]["id"], [c["case_id"] for c in r["selected"]])
    manifest = _manifest(run_id, check)
    ctx.c.execute(
        """INSERT INTO runs.runs(id,workspace_id,project_id,name,suite_version_id,model_set,attempts,budget_usd,episode_timeout_s,
             infra_retries,created_by,execution_mode,state,live_approvals) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'admitted',%s)""",
        (
            *common,
            manifest["execution_mode"],
            Jsonb(
                {
                    m["system_id"]: m["live"]["approval_id"]
                    for m in manifest["models"]
                    if m.get("live")
                }
            )
            if manifest["execution_mode"] == "live"
            else None,
        ),
    )
    manifest_sha = sha(manifest)
    ctx.c.execute(
        "INSERT INTO runs.run_manifests(run_id,workspace_id,manifest,manifest_sha256) VALUES(%s,%s,%s,%s)",
        (run_id, ctx.ws, Jsonb(manifest), manifest_sha),
    )
    scoring.create_pass(ctx.c, ctx.ws, run_id, "initial", manifest["evaluators"], ctx.actor.id)
    for n, spec in enumerate(r["specs"], start=1):
        case, task, prompt = spec["case"], spec["task"], spec["prompt"]
        ctx.c.execute(
            """INSERT INTO runs.episodes(id,run_id,workspace_id,kind,task_import_id,task_id,task_revision,case_id,application_type,
                 completeness,edge_cases,ts_prompt_id,ts_category,system_id,system_version,attempt,state)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued')""",
            (
                f"{run_id}-e{n:04d}",
                run_id,
                ctx.ws,
                spec["kind"],
                task["id"],
                task["task_id"],
                task["revision"],
                case["case_id"],
                case["application_type"],
                case["completeness"],
                case["edge_cases"],
                prompt["id"] if prompt else None,
                prompt["category_key"] if prompt else None,
                spec["system_id"],
                spec["system_version"],
                spec["attempt"],
            ),
        )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "run.admitted",
        run_id,
        details={"manifest_sha256": manifest_sha, "episodes": len(r["specs"])},
    )
    emit(
        ctx.c,
        ctx.ws,
        "run.admitted",
        run_id,
        {
            "run_id": run_id,
            "project_id": project_id,
            "manifest_sha256": manifest_sha,
            "episodes": len(r["specs"]),
        },
    )
    # Usage for the registry's impact reports (ARCHITECTURE 9.4): which released version this run binds. It goes to
    # the registry that released the version; the registry takes the tenant from the RL Gym's key.
    env = r["env"]["version"]
    emit(
        ctx.c,
        ctx.ws,
        "registry.usage",
        run_id,
        {
            "_base": env.get("registry"),
            "schema": "rlgym.registry-usage.v1",
            "event": "run.admitted",
            "environment_version": env["id"],
            "contract_id": env["contract_id"],
            "seed_family": env["seed_family"],
            "template": {
                "id": manifest["template"]["id"],
                "version": manifest["template"]["version"],
            },
            "project_id": project_id,
            "run_id": run_id,
            "episodes": len(r["specs"]),
            "execution_mode": manifest["execution_mode"],
            "at": dt.datetime.now(dt.UTC).isoformat(),
        },
        destination="registry",
    )
    return {"run": get_run(ctx, run_id), "refused": False, "check": public_check(check)}


def _run(ctx, run_id):
    row = ctx.c.execute(
        "SELECT * FROM runs.runs WHERE workspace_id=%s AND id=%s", (ctx.ws, run_id)
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "Run not found")
    return row


def cancel(ctx, run_id, body):
    _can_run(ctx.actor)
    run = _run(ctx, run_id)
    require(
        run["state"] in ("admitted", "running"),
        "CONFLICT",
        f"A {run['state']} run cannot be cancelled",
    )
    ctx.c.execute(
        "UPDATE runs.runs SET cancel_requested_by=%s, cancel_requested_at=now() WHERE id=%s",
        (ctx.actor.id, run_id),
    )
    n = ctx.c.execute(
        "UPDATE runs.episodes SET state='cancelled', last_error='run cancelled' WHERE run_id=%s AND state='queued'",
        (run_id,),
    ).rowcount
    running = ctx.c.execute(
        "SELECT count(*) n FROM runs.episodes WHERE run_id=%s AND state IN ('running','scoring')",
        (run_id,),
    ).fetchone()["n"]
    if not running:
        ctx.c.execute(
            "UPDATE runs.runs SET state='cancelled', finished_at=now() WHERE id=%s", (run_id,)
        )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "run.cancelled",
        run_id,
        reason=body.get("reason"),
        details={"cancelled_queued": n},
    )
    emit(
        ctx.c,
        ctx.ws,
        "run.cancelled",
        run_id,
        {"run_id": run_id, "cancelled_queued": n, "still_sealing": running},
    )
    return get_run(ctx, run_id)


def rescore(ctx, run_id, body):
    """Explicit re-score: grade the recorded episodes again with the evaluator versions the suite binds now. No model is
    called; earlier passes are kept and the run is marked re-scored."""
    _can_run(ctx.actor)
    run = _run(ctx, run_id)
    require(
        run["state"] in ("completed", "cancelled"),
        "CONFLICT",
        "Only a finished run can be re-scored",
    )
    manifest = _manifest_row(ctx, run_id)["manifest"]
    versions, bad = [], []
    for ev in manifest["evaluators"]:
        b = ctx.c.execute(
            "SELECT * FROM suites.suite_criterion_bindings WHERE suite_version_id=%s AND criterion_id=%s",
            (run["suite_version_id"], ev["criterion_id"]),
        ).fetchone()
        pick, _, reason = suites.resolve_criterion(ctx.c, ctx.ws, run["project_id"], b)
        if not pick:
            bad.append(f"{ev['criterion_id']}: {reason}")
            continue
        versions.append(
            {
                **ev,
                "version": pick["version"],
                "config_sha256": pick["config_sha256"],
                "framework": pick["framework_version_id"],
            }
        )
    require(not bad, "CONFLICT", "Some criteria have no qualified evaluator version now", items=bad)
    pass_row = scoring.create_pass(ctx.c, ctx.ws, run_id, "rescore", versions, ctx.actor.id)
    episodes = ctx.c.execute(
        """SELECT e.* FROM runs.episodes e JOIN runs.sealed_evidence s ON s.episode_id=e.id WHERE e.run_id=%s ORDER BY e.id""",
        (run_id,),
    ).fetchall()
    for e in episodes:
        scoring.score_episode(ctx.c, ctx.ws, e, pass_row, manifest)
    ctx.c.execute(
        "UPDATE scoring.scoring_passes SET finished_at=now() WHERE id=%s", (pass_row["id"],)
    )
    ctx.c.execute("UPDATE runs.runs SET rescored=true WHERE id=%s", (run_id,))
    changed = [
        f"{v['criterion_id']} v{o['version']}→v{v['version']}"
        for v, o in zip(versions, manifest["evaluators"], strict=True)
        if v["version"] != o["version"]
    ]
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "run.rescored",
        run_id,
        reason=body.get("reason"),
        details={"pass": pass_row["pass"], "changed": changed},
    )
    emit(
        ctx.c,
        ctx.ws,
        "run.rescored",
        run_id,
        {"run_id": run_id, "pass": pass_row["pass"], "episodes": len(episodes)},
    )
    return get_run(ctx, run_id)


# --- views --------------------------------------------------------------------------------------------------------


def _manifest_row(ctx, run_id):
    return ctx.c.execute("SELECT * FROM runs.run_manifests WHERE run_id=%s", (run_id,)).fetchone()


def _counts(ctx, run_id):
    rows = ctx.c.execute(
        "SELECT state, kind, count(*) n FROM runs.episodes WHERE run_id=%s GROUP BY state, kind",
        (run_id,),
    ).fetchall()
    by_state = {}
    for r in rows:
        by_state[r["state"]] = by_state.get(r["state"], 0) + r["n"]
    return by_state


def list_runs(ctx, state=None, q=None, project_id=None):
    rows = ctx.c.execute(
        """SELECT r.*, m.manifest_sha256, m.manifest->'models' models, (m.manifest->'leaderboard')::boolean leaderboard, p.name project_name, sv.suite_id, sv.version suite_version,
                  sv.name suite_name, (SELECT count(*) FROM runs.episodes e WHERE e.run_id=r.id) episodes
           FROM runs.runs r JOIN projects.projects p USING (workspace_id, project_id)
           JOIN suites.suite_versions sv ON sv.id=r.suite_version_id
           LEFT JOIN runs.run_manifests m ON m.run_id=r.id WHERE r.workspace_id=%s
           ORDER BY r.created_at DESC""",
        (ctx.ws,),
    ).fetchall()
    out = []
    for r in rows:
        if state and r["state"] != state:
            continue
        if project_id and r["project_id"] != project_id:
            continue
        if q and q.lower() not in (r["name"] + " " + r["id"] + " " + r["project_name"]).lower():
            continue
        out.append(
            {
                **{
                    k: r[k]
                    for k in (
                        "id",
                        "name",
                        "project_id",
                        "project_name",
                        "state",
                        "created_at",
                        "rescored",
                        "execution_mode",
                    )
                },
                "manifest_sha256": r["manifest_sha256"],
                "suite": {
                    "id": r["suite_id"],
                    "version": r["suite_version"],
                    "name": r["suite_name"],
                },
                "models": [m["name"] for m in (r["models"] or [])],
                "episodes": r["episodes"],
                "leaderboard": r["leaderboard"] is True,
                "refusal_reasons": r["refusal_reasons"],
                "report_available": r["state"] == "completed",
            }
        )
    return out


def _scoring(ctx, m, latest):
    if not m:
        return {}
    from anvil.rlgym.results import scorer

    evs = (
        ctx.c.execute(
            "SELECT evaluator_versions FROM scoring.scoring_passes WHERE id=%s", (latest["id"],)
        ).fetchone()["evaluator_versions"]
        if latest
        else m["manifest"].get("evaluators")
    )
    try:
        return scorer.for_run(ctx.c, ctx.ws, m["manifest"], evs)
    except Exception:  # the view never fails the run page; the report says what it could not read
        return {}


def get_run(ctx, run_id):
    run = _run(ctx, run_id)
    m = _manifest_row(ctx, run_id)
    counts = _counts(ctx, run_id)
    passes = ctx.c.execute(
        "SELECT id, pass, reason, requested_by, created_at, finished_at, evaluator_versions_sha256, draft IS NOT NULL AS is_draft FROM scoring.scoring_passes WHERE run_id=%s ORDER BY pass",
        (run_id,),
    ).fetchall()
    # E-004: draft re-scores are experiments; the run's latest pass is its latest real one.
    real = [p for p in passes if p.get("reason") != "draft"]
    latest = real[-1] if real else None
    stats = (
        scoring.run_statistics(ctx.c, run_id, latest["id"])
        if latest
        else {"systems": [], "by_stratum": []}
    )
    timings = ctx.c.execute(
        "SELECT avg((timings->>'wall_ms')::numeric) ms, coalesce(sum(cost_usd),0) cost FROM runs.sealed_evidence s JOIN runs.episodes e ON e.id=s.episode_id WHERE e.run_id=%s",
        (run_id,),
    ).fetchone()
    now = dt.datetime.now(dt.UTC)
    remaining = counts.get("queued", 0) + counts.get("running", 0)
    elapsed = (
        (run["finished_at"] or now) - (run["started_at"] or run["created_at"])
    ).total_seconds()
    eta = remaining * float(timings["ms"]) / 1000 if timings["ms"] and remaining else None
    instance = ctx.c.execute(
        "SELECT id, container, started_at, stopped_at, local_image_id, environment_version_id FROM runs.instances WHERE run_id=%s ORDER BY started_at DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    names = {mm["system_id"]: mm["name"] for mm in (m["manifest"]["models"] if m else [])}
    for s in stats["systems"]:
        s["name"] = names.get(s["system_id"], s["system_id"])
    return {
        **run,
        "manifest_sha256": m and m["manifest_sha256"],
        "manifest": m and m["manifest"],
        "leaderboard": bool(m and m["manifest"].get("leaderboard") is True),
        # D-034: how each criterion was scored in this run (its latest scoring pass and frozen manifest).
        "scoring": _scoring(ctx, m, latest),
        "counts": counts,
        "total_episodes": sum(counts.values()),
        "elapsed_s": round(elapsed),
        "estimated_remaining_s": round(eta) if eta else None,
        "cost_so_far_usd": round(float(timings["cost"]), 4),
        "passes": passes,
        "latest_pass": latest and latest["pass"],
        "statistics": stats,
        "instance": instance,
        "report_available": run["state"] == "completed",
        "note": MOCK_NOTE if run["execution_mode"] == "controlled_mock" else LIVE_NOTE,
        "live_spend": _live_spend(ctx, run_id, m),
    }


def _live_spend(ctx, run_id, m):
    """Per live model: calls, tokens and cost recorded against its approval for this run, with the run cap."""
    out = []
    for model in m["manifest"]["models"] if m else []:
        live = model.get("live")
        if not live:
            continue
        row = ctx.c.execute(
            """SELECT count(*) calls, coalesce(sum(tokens_in),0) tin, coalesce(sum(tokens_out),0) tout,
                      coalesce(sum(cost_usd),0) cost, count(*) FILTER (WHERE status='ambiguous') ambiguous,
                      count(*) FILTER (WHERE status='error') errors
               FROM systems.live_calls WHERE workspace_id=%s AND approval_id=%s AND run_id=%s""",
            (ctx.ws, live["approval_id"], run_id),
        ).fetchone()
        out.append(
            {
                "system_id": model["system_id"],
                "name": model.get("name"),
                "provider": model["provider"],
                "model_id": model["model_id"],
                "approval_id": live["approval_id"],
                "per_run_cap_usd": live["per_run_cap_usd"],
                "calls": row["calls"],
                "tokens_in": row["tin"],
                "tokens_out": row["tout"],
                "cost_usd": round(float(row["cost"]), 6),
                "ambiguous": row["ambiguous"],
                "errors": row["errors"],
            }
        )
    return out


def episodes(
    ctx,
    run_id,
    system_id=None,
    state=None,
    kind=None,
    verdict=None,
    stratum=None,
    q=None,
    page=1,
    size=50,
):
    _run(ctx, run_id)
    latest = scoring.latest_pass(ctx.c, run_id)
    rows = ctx.c.execute(
        """SELECT e.id, e.kind, e.task_id, e.task_revision, e.case_id, e.application_type, e.completeness, e.edge_cases,
                  e.ts_prompt_id, e.ts_category, e.system_id, e.system_version, e.attempt, e.state, e.tries, e.last_error,
                  e.likely_cause, e.likely_cause_source, s.score, s.passed, s.failed_criteria, o.outcome safety_outcome,
                  o.critical safety_critical, x.sealed_sha256, x.cost_usd
           FROM runs.episodes e
           LEFT JOIN scoring.episode_scores s ON s.episode_id=e.id AND s.pass_id=%s
           LEFT JOIN scoring.safety_outcomes o ON o.episode_id=e.id AND o.pass_id=%s
           LEFT JOIN runs.sealed_evidence x ON x.episode_id=e.id
           WHERE e.run_id=%s ORDER BY e.id""",
        (latest and latest["id"], latest and latest["id"], run_id),
    ).fetchall()

    def keep(e):
        if system_id and e["system_id"] != system_id:
            return False
        if state and e["state"] != state:
            return False
        if kind and e["kind"] != kind:
            return False
        if verdict == "passed" and not e["passed"]:
            return False
        if verdict == "failed" and (e["passed"] is not False):
            return False
        if stratum and stratum not in (e["application_type"], e["completeness"], *e["edge_cases"]):
            return False
        return not (q and q.lower() not in (e["id"] + e["case_id"] + e["task_id"]).lower())

    kept = [e for e in rows if keep(e)]
    page, size = max(1, int(page)), min(200, max(1, int(size)))
    return {
        "items": kept[(page - 1) * size : page * size],
        "total": len(kept),
        "page": page,
        "size": size,
    }


def episode_scores(ctx, run_id):
    latest = scoring.latest_pass(ctx.c, run_id)
    if not latest:
        return {}
    return {
        r["episode_id"]: r
        for r in ctx.c.execute(
            """SELECT s.*, e.task_id, e.case_id, e.system_id, e.attempt FROM scoring.episode_scores s JOIN runs.episodes e ON e.id=s.episode_id
               WHERE e.run_id=%s AND s.pass_id=%s""",
            (run_id, latest["id"]),
        ).fetchall()
    }


def compare(ctx, baseline_id, compared_id):
    """Two runs are comparable only on the same suite version and the same environment and evaluator versions."""
    require(
        baseline_id and compared_id and baseline_id != compared_id,
        "VALIDATION_FAILED",
        "Pick two different runs.",
    )
    a, b = _run(ctx, baseline_id), _run(ctx, compared_id)
    ma, mb = _manifest_row(ctx, baseline_id), _manifest_row(ctx, compared_id)
    checks = []

    def check(key, ok, label, detail=None):
        checks.append(
            {"key": key, "ok": bool(ok), "label": label, "detail": None if ok else detail}
        )

    check(
        "suite",
        a["suite_version_id"] == b["suite_version_id"],
        "Same suite version",
        f"{baseline_id} is {ma and ma['manifest']['suite']['name']} v{ma and ma['manifest']['suite']['version']}; "
        f"{compared_id} is {mb and mb['manifest']['suite']['name']} v{mb and mb['manifest']['suite']['version']}",
    )
    check(
        "environment",
        ma
        and mb
        and ma["manifest"]["environment"]["version_id"]
        == mb["manifest"]["environment"]["version_id"],
        "Same environment versions",
        f"{ma and ma['manifest']['environment']['version_id']} vs {mb and mb['manifest']['environment']['version_id']}",
    )
    pa, pb = scoring.latest_pass(ctx.c, baseline_id), scoring.latest_pass(ctx.c, compared_id)
    va = {(e["criterion_id"], e["version"]) for e in (pa["evaluator_versions"] if pa else [])}
    vb = {(e["criterion_id"], e["version"]) for e in (pb["evaluator_versions"] if pb else [])}
    check(
        "evaluators",
        pa and pb and va == vb,
        "Same evaluator versions",
        "; ".join(f"{c} v{v}" for c, v in sorted(va ^ vb)) or "a run has no scoring pass",
    )
    sa, sb = episode_scores(ctx, baseline_id), episode_scores(ctx, compared_id)
    check(
        "scored",
        sa and sb,
        "Each run completed or has scored episodes",
        f"{baseline_id}: {len(sa)} scored; {compared_id}: {len(sb)} scored",
    )
    comparable = all(c["ok"] for c in checks)
    result = {
        "baseline": baseline_id,
        "compared": compared_id,
        "checks": checks,
        "comparable": comparable,
    }
    if not comparable:
        result["message"] = "These runs are not comparable. The differences are listed on the left."
        return result

    def key(s):
        return (s["system_id"], s["task_id"], s["case_id"], s["attempt"])

    ka = {key(s): s for s in sa.values() if s["score"] is not None}
    kb = {key(s): s for s in sb.values() if s["score"] is not None}
    shared = sorted(set(ka) & set(kb))
    diffs = [float(kb[k]["score"]) - float(ka[k]["score"]) for k in shared]
    mean_a = statistics.fmean(float(ka[k]["score"]) for k in shared) if shared else None
    mean_b = statistics.fmean(float(kb[k]["score"]) for k in shared) if shared else None
    disagreements = [
        {
            "system_id": k[0],
            "task_id": k[1],
            "case_id": k[2],
            "attempt": k[3],
            "baseline": ka[k]["passed"],
            "compared": kb[k]["passed"],
        }
        for k in shared
        if ka[k]["passed"] != kb[k]["passed"]
    ]

    def crit(pass_row, run_id):
        rows = ctx.c.execute(
            """SELECT r.criterion_id, count(*) FILTER (WHERE verdict='pass') p, count(*) FILTER (WHERE verdict IN ('pass','partial','fail')) n
               FROM scoring.criterion_receipts r JOIN runs.episodes e ON e.id=r.episode_id WHERE e.run_id=%s AND r.pass_id=%s GROUP BY 1""",
            (run_id, pass_row["id"]),
        ).fetchall()
        return {r["criterion_id"]: (r["p"] / r["n"] if r["n"] else None) for r in rows}

    ca, cb = crit(pa, baseline_id), crit(pb, compared_id)
    result.update(
        paired_episodes=len(shared),
        mean_score={
            "baseline": mean_a and round(mean_a, 2),
            "compared": mean_b and round(mean_b, 2),
        },
        delta=round(statistics.fmean(diffs), 2) if diffs else None,
        paired_ci=scoring.paired_bootstrap(diffs),
        pass_rate={
            "baseline": round(sum(1 for k in shared if ka[k]["passed"]) / len(shared), 4)
            if shared
            else None,
            "compared": round(sum(1 for k in shared if kb[k]["passed"]) / len(shared), 4)
            if shared
            else None,
        },
        disagreements=disagreements,
        criteria=[
            {
                "criterion_id": c,
                "baseline": ca.get(c) and round(ca[c], 4),
                "compared": cb.get(c) and round(cb[c], 4),
                "delta": round(cb[c] - ca[c], 4)
                if ca.get(c) is not None and cb.get(c) is not None
                else None,
            }
            for c in sorted(set(ca) | set(cb))
        ],
    )
    return result


def save_comparison(ctx, body):
    ctx.actor.require_person()
    result = compare(ctx, body.get("baseline"), body.get("compared"))
    require(
        result["comparable"],
        "VALIDATION_FAILED",
        "These runs are not comparable",
        checks=result["checks"],
    )
    cid = new_id("cmp-")
    ctx.c.execute(
        "INSERT INTO runs.comparisons(id,workspace_id,baseline_run_id,compared_run_id,result,result_sha256,saved_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (
            cid,
            ctx.ws,
            result["baseline"],
            result["compared"],
            Jsonb(result),
            sha(result),
            ctx.actor.id,
        ),
    )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "comparison.saved",
        cid,
        details={"baseline": result["baseline"], "compared": result["compared"]},
    )
    return {"id": cid, **result}
