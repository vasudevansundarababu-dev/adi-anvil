"""Projects (SPEC 07.0a, ARCHITECTURE 6.3 projects.*): ADI Forge exports, imported tasks, selection rules,
overrides with a second person, and the project views with their suggested action.

An RL Gym Project is the ADI Forge project with the same Project ID; it is created by the first export and belongs to
exactly one template version. Tasks change only in ADI Forge: an import is immutable, a correction is a new revision.
"""

import hashlib
import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from anvil.rlgym.catalog import inbox, selection
from anvil.rlgym.catalog.selection import rule_label, short
from anvil.rlgym.common import GymError, audit, emit, require, sha
from anvil.rlgym.integrations import forge_package
from anvil.rlgym.runs import clauses, instructions

CAUSE = {
    "version.revoked": "automatic_revoked",
    "version.emergency_revoked": "automatic_revoked",
    "version.deleted": "automatic_revoked",
    "version.deprecated": "automatic_deprecated",
    "version.failed": "automatic_failed",
    "qualification.failed": "automatic_failed",
    "evaluator.revoked": "automatic_revoked",
    "framework.revoked": "automatic_revoked",
    "evaluator.deprecated": "automatic_deprecated",
}


# --- exports ---------------------------------------------------------------------------------------------------


def package_bytes_match(raw, package_sha256):
    """ADI Forge serves the stored RFC 8785 (JCS) bytes of a package, so `package_sha256` is checked over exactly the
    bytes received, never over a re-serialised parse: a parse and re-dump can change decimals (criterion weights such
    as 0.50 or 1e-7) and so the hash. The local stub serves its own canonical bytes, which hash the same way."""
    return hashlib.sha256(raw).hexdigest() == package_sha256


def test_channel_export_problem(activation, body):
    """A test-channel template activation never satisfies a real project's export: only test_only: true."""
    if (activation or {}).get("channel") == "test" and (body or {}).get("test_only") is not True:
        return "The template is activated on the test channel: only a test_only export may use it"
    return None


def template_hash_matches(activation, t):
    """An export names the activated version by one of its two fingerprints: the RL Gym document's `spec_sha256`, or
    (real Authoring) the joint template-version hash Studio's release recorded as `forge_template_version_hash`.
    Authoring sends its hash in `spec_sha256` or in `template_version_hash`. Either identifies this immutable
    activation; anything else is refused. The project always stores the activation's own `spec_sha256`."""
    sent = {
        t.get(k) for k in ("spec_sha256", "template_version_hash", "forge_template_version_hash")
    } - {
        None,
        "",
    }
    known = {activation["spec_sha256"], activation.get("forge_template_version_hash")} - {None, ""}
    return bool(sent & known)


def latest_map(c, task_import_id):
    """The newest policy_id_map attached to a task import (D-056), or None."""
    return c.execute(
        "SELECT * FROM projects.task_policy_maps WHERE task_import_id=%s ORDER BY received_at DESC, id DESC LIMIT 1",
        (task_import_id,),
    ).fetchone()


def _attach_map(c, ws, task_import_id, export_id, policy_id_map):
    """D-056: append Authoring's policy_id_map for a task import. True if a row was added; the same map as the newest
    one is not added again. Never updates projects.task_imports."""
    if policy_id_map is None:
        return False
    digest = sha(policy_id_map)
    newest = latest_map(c, task_import_id)
    if newest and newest["map_sha256"] == digest:
        return False
    c.execute(
        """INSERT INTO projects.task_policy_maps(id,workspace_id,task_import_id,export_id,policy_id_map,map_sha256,received_at)
           VALUES(%s,%s,%s,%s,%s,%s,clock_timestamp())""",
        (str(uuid4()), ws, task_import_id, export_id, Jsonb(policy_id_map), digest),
    )
    return True


def receive_export(c, ws, actor, project_id, body):
    """POST /projects/{project_id}/exports (client adi-forge). Idempotent by export hash; tasks deduplicated by
    package hash. Every package is fetched from the ADI Forge stub and checked against its hash before import."""
    require(
        body.get("schema") == "rlgym.project-export.v1",
        "VALIDATION_FAILED",
        "schema must be rlgym.project-export.v1",
    )
    require(
        body.get("project_id") == project_id,
        "VALIDATION_FAILED",
        "project_id in body and path differ",
        field="project_id",
    )
    # Authoring's test-only marker (Project.testOnly → export `test_only`).
    require(
        body.get("test_only") in (None, True, False),
        "VALIDATION_FAILED",
        "test_only must be true or false",
        field="test_only",
    )
    for field in ("project_name", "template", "export_id", "tasks", "export_sha256"):
        require(
            body.get(field) not in (None, ""),
            "VALIDATION_FAILED",
            f"{field} is required",
            field=field,
        )
    expected = sha({k: v for k, v in body.items() if k != "export_sha256"})
    require(
        body["export_sha256"] == expected,
        "HASH_MISMATCH",
        "export_sha256 does not match the export body",
        expected=expected,
        got=body["export_sha256"],
    )
    same = c.execute(
        "SELECT receipt FROM projects.project_exports WHERE workspace_id=%s AND project_id=%s AND export_sha256=%s",
        (ws, project_id, body["export_sha256"]),
    ).fetchone()
    if same:
        return {**same["receipt"], "replayed": True}
    clash = c.execute(
        "SELECT 1 FROM projects.project_exports WHERE workspace_id=%s AND project_id=%s AND export_id=%s",
        (ws, project_id, body["export_id"]),
    ).fetchone()
    require(
        not clash,
        "IDEMPOTENCY_CONFLICT",
        f"Export {body['export_id']} was already received with different content",
    )
    t = body["template"]
    activation = c.execute(
        "SELECT * FROM catalog.template_activations WHERE workspace_id=%s AND template_id=%s AND version=%s",
        (ws, t["id"], int(t["version"])),
    ).fetchone()
    if not activation or activation["state"] != "active":
        raise GymError(
            "TEMPLATE_NOT_ACTIVE",
            f"Template {t['id']} v{t['version']} is not active in this workspace",
        )
    why = test_channel_export_problem(activation, body)
    if why:
        raise GymError("TEMPLATE_TEST_CHANNEL", why)
    require(
        template_hash_matches(activation, t),
        "HASH_MISMATCH",
        "The export's template fingerprint differs from the activated Studio release",
        activated=activation["spec_sha256"],
        activated_forge_version_hash=activation.get("forge_template_version_hash"),
        exported=t.get("spec_sha256"),
    )
    project = c.execute(
        "SELECT * FROM projects.projects WHERE workspace_id=%s AND project_id=%s FOR UPDATE",
        (ws, project_id),
    ).fetchone()
    if project:
        require(
            project["template_id"] == t["id"] and project["template_version"] == int(t["version"]),
            "VALIDATION_FAILED",
            "A project belongs to exactly one template version; move the project in ADI Forge to change it",
        )
    else:
        mode = (body.get("project_config") or {}).get("mode", activation["mode"])
        c.execute(
            """INSERT INTO projects.projects(workspace_id,project_id,name,template_id,template_version,spec_sha256,forge_template_id,
                 forge_version,mode,config,state) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'blocked')""",
            (
                ws,
                project_id,
                body["project_name"],
                t["id"],
                int(t["version"]),
                activation["spec_sha256"],
                t["forge_template_id"],
                int(t["forge_version"]),
                mode,
                Jsonb(body.get("project_config") or {}),
            ),
        )
    if body.get("test_only") is True:
        # Sticky: a test-only project stays labelled TEST (a later export can't silently unlabel it).
        marked = c.execute(
            "UPDATE projects.projects SET test_only=true WHERE workspace_id=%s AND project_id=%s AND NOT test_only RETURNING project_id",
            (ws, project_id),
        ).fetchone()
        if marked:
            audit(
                c,
                ws,
                actor,
                "project.test_only",
                project_id,
                "Authoring marked the project test-only",
            )
    if not project:
        # After the test_only mark, so a test-only project's first rules can resolve Studio's test channel.
        _initial_rules(c, ws, project_id, activation)
        audit(
            c,
            ws,
            actor,
            "project.created",
            project_id,
            details={"template": f"{t['id']}@{t['version']}"},
        )
    # Verify every package first; nothing is imported from a partially valid export.
    packages, mismatched = {}, []
    for task in body["tasks"]:
        for field in ("task_id", "revision", "package_ref", "package_sha256", "case_selector"):
            require(
                task.get(field) not in (None, ""),
                "VALIDATION_FAILED",
                f"task {field} is required",
                task=task.get("task_id"),
            )
        raw = forge_package(task)
        if not package_bytes_match(raw, task["package_sha256"]):
            mismatched.append(task["task_id"])
        package = json.loads(raw)
        for part in ("actor", "private"):
            require(
                isinstance(package.get(part), dict),
                "VALIDATION_FAILED",
                f"the package needs an {part} object",
                task=task["task_id"],
            )
        packages[task["task_id"]] = package
    require(
        not mismatched,
        "HASH_MISMATCH",
        "Package content does not match package_sha256",
        tasks=mismatched,
    )
    counts = {"new": 0, "superseding": 0, "unchanged": 0, "map_attached": 0}
    blocked, bindable = [], _bindable(c, ws, project_id)
    for task in body["tasks"]:
        existing = c.execute(
            "SELECT * FROM projects.task_imports WHERE workspace_id=%s AND project_id=%s AND task_id=%s ORDER BY revision DESC",
            (ws, project_id, task["task_id"]),
        ).fetchall()
        same_rev = next((e for e in existing if e["revision"] == int(task["revision"])), None)
        if same_rev:
            require(
                same_rev["package_sha256"] == task["package_sha256"],
                "VALIDATION_FAILED",
                f"{task['task_id']} r{task['revision']} already exists with another package; a correction is a new revision",
            )
            # D-056: a re-export of the same revision may bring Authoring's policy_id_map. It is attached append-only
            # (the import row is never touched); the same map twice is not attached again.
            if _attach_map(c, ws, same_rev["id"], body["export_id"], task.get("policy_id_map")):
                counts["map_attached"] += 1
            else:
                counts["unchanged"] += 1
            continue
        latest = existing[0] if existing else None
        require(
            not latest or int(task["revision"]) > latest["revision"],
            "VALIDATION_FAILED",
            f"{task['task_id']} r{task['revision']} is older than imported r{latest['revision'] if latest else 0}",
        )
        package = packages[task["task_id"]]
        for part in ("actor", "private"):
            c.execute(
                """INSERT INTO projects.task_payloads(package_sha256,workspace_id,part,content,content_sha256) VALUES(%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING""",
                (task["package_sha256"], ws, part, Jsonb(package[part]), sha(package[part])),
            )
        state, reason = ("ready", None) if bindable["ok"] else ("blocked", bindable["reason"])
        if not bindable["ok"]:
            blocked.append(
                {
                    "task_id": task["task_id"],
                    "reason": "BINDING_UNRESOLVED",
                    "alias": bindable["alias"],
                }
            )
        # D-007: a task the agent cannot be given (no assignment, no sections) is kept but blocked, never run.
        no_instructions = instructions.problem(package["actor"])
        if no_instructions:
            state, reason = "blocked", f"TASK_NO_INSTRUCTIONS: {no_instructions}"
            blocked.append({"task_id": task["task_id"], "reason": "TASK_NO_INSTRUCTIONS"})
        # E-002: the export's selected clause versions (approved-task-export.v1 policy_clauses, optional). An invalid
        # clause blocks the task here, so a run never meets it.
        policy_clauses = task.get("policy_clauses") or None
        bad_clause = clauses.problems(policy_clauses)
        if bad_clause:
            state, reason = "blocked", f"CLAUSE_INVALID: {bad_clause}"
            blocked.append({"task_id": task["task_id"], "reason": "CLAUSE_INVALID"})
        import_id = str(uuid4())
        c.execute(
            """INSERT INTO projects.task_imports(id,workspace_id,project_id,export_id,task_id,revision,title,package_ref,package_sha256,
                 case_selector,actor_payload,private_payload,state,state_reason,corrects_id,sme_batch_id,complexity,archetype,
                 policy_clauses,policy_id_map)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                import_id,
                ws,
                project_id,
                body["export_id"],
                task["task_id"],
                int(task["revision"]),
                task.get("title") or task["task_id"],
                task["package_ref"],
                task["package_sha256"],
                Jsonb(task["case_selector"]),
                f"rlgym-pkg://{task['package_sha256']}/actor",
                f"rlgym-pkg://{task['package_sha256']}/private",
                state,
                reason,
                latest["id"] if latest else None,
                task.get("sme_batch_id"),
                # Slice tags (2.12): the private part of the authored package (S1 lists of the template).
                package["private"].get("complexity"),
                package["private"].get("archetype"),
                Jsonb(policy_clauses) if policy_clauses else None,
                # D-056: the map is kept in projects.task_policy_maps (below), not in this column (left unused).
                None,
            ),
        )
        # D-056: Authoring's map from its S4 rule ids to the environment's policy ids (optional, kept as sent; checked
        # against the environment at reset, never at import, so it can't block a task).
        _attach_map(c, ws, import_id, body["export_id"], task.get("policy_id_map"))
        if latest:
            c.execute(
                "UPDATE projects.task_imports SET state='superseded', state_reason=%s WHERE id=%s",
                (f"superseded by r{task['revision']} in {body['export_id']}", latest["id"]),
            )
            emit(
                c,
                ws,
                "task.superseded",
                f"{project_id}:{task['task_id']}",
                {
                    "project_id": project_id,
                    "task_id": task["task_id"],
                    "revision": latest["revision"],
                },
            )
            counts["superseding"] += 1
        else:
            counts["new"] += 1
    from anvil.rlgym.common import Actor
    from anvil.rlgym.suites import service as suites

    refresh_state(c, ws, project_id)
    default_suite = suites.ensure_default(
        c, ws, Actor("rlgym", "system", "RL Gym"), project_id, body["project_name"]
    )
    receipt = {
        "project_id": project_id,
        "export_id": body["export_id"],
        # D-056: map_attached appears only when an export attached a map, so other receipts keep their shape.
        **{k: v for k, v in counts.items() if k != "map_attached" or v},
        "blocked": blocked,
        "default_suite_version": default_suite,
    }
    receipt["receipt_sha256"] = sha(receipt)
    c.execute(
        """INSERT INTO projects.project_exports(workspace_id,project_id,export_id,export_sha256,new_count,superseding_count,unchanged_count,
             blocked_count,reason,blocked,receipt,receipt_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            ws,
            project_id,
            body["export_id"],
            body["export_sha256"],
            counts["new"],
            counts["superseding"],
            counts["unchanged"],
            len(blocked),
            body.get("reason"),
            Jsonb(blocked),
            Jsonb(receipt),
            receipt["receipt_sha256"],
        ),
    )
    status = refresh_state(c, ws, project_id)
    ready = c.execute(
        "SELECT count(*) n FROM projects.task_imports WHERE workspace_id=%s AND project_id=%s AND state='ready'",
        (ws, project_id),
    ).fetchone()["n"]
    changed = counts["new"] + counts["superseding"]
    emit(
        c,
        ws,
        "project.exported",
        f"{project_id}:{body['export_id']}",
        {
            "project_id": project_id,
            "project_name": body["project_name"],
            "export_id": body["export_id"],
            **counts,
            "blocked": blocked,
            "ready_tasks": ready if (changed and status == "ready") else 0,
            "ready_reason": (
                f"{counts['superseding']} corrected tasks arrived in {body['export_id']}"
                if counts["superseding"]
                else f"{ready} ready tasks from {body['export_id']}; never run"
            ),
        },
    )
    if blocked:
        emit(
            c,
            ws,
            "task.blocked",
            project_id,
            {
                "project_id": project_id,
                "count": len(blocked),
                "reason": bindable["reason"] or "; ".join(sorted({b["reason"] for b in blocked})),
            },
        )
    audit(
        c,
        ws,
        actor,
        "project.export_received",
        f"{project_id}:{body['export_id']}",
        body.get("reason"),
        receipt,
    )
    # Corrected revisions after SME review link back to their batch (07.9 step 5).
    from anvil.rlgym.results import sme

    sme.on_export(c, ws, project_id, [t.get("sme_batch_id") for t in body["tasks"]])
    return receipt


def _initial_rules(c, ws, project_id, activation):
    for b in activation["default_bindings"]:
        r = b["rule"]
        rule = {
            "workspace_id": ws,
            "project_id": project_id,
            "contract_id": b["contract_id"],
            "kind": r["kind"],
            "pinned_version_id": r.get("pinned_version_id"),
            "seed_family": r.get("seed_family"),
        }
        pick, code, reason = selection.resolve_environment(c, rule)
        c.execute(
            """INSERT INTO projects.selection_rules(workspace_id,project_id,alias,contract_id,kind,pinned_version_id,seed_family,
                 template_rule,resolved_version_id,change_cause,change_note) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'initial',%s)""",
            (
                ws,
                project_id,
                b["alias"],
                b["contract_id"],
                rule["kind"],
                rule["pinned_version_id"],
                rule["seed_family"],
                Jsonb(r),
                pick["id"] if pick else None,
                f"initial · {rule_label(rule)} → {short(pick['id']) if pick else 'nothing (' + reason + ')'}",
            ),
        )
    for cr in c.execute(
        "SELECT * FROM catalog.template_criteria WHERE workspace_id=%s AND template_id=%s AND version=%s",
        (ws, activation["template_id"], activation["version"]),
    ).fetchall():
        rule = {"configuration_id": cr["configuration_id"], "kind": "latest_qualified"}
        pick, code, reason = selection.resolve_evaluator(c, ws, rule)
        c.execute(
            """INSERT INTO projects.evaluator_selection_rules(workspace_id,project_id,criterion_id,configuration_id,kind,resolved_version,
                 change_cause,change_note) VALUES(%s,%s,%s,%s,'latest_qualified',%s,'initial',%s)""",
            (
                ws,
                project_id,
                cr["criterion_id"],
                cr["configuration_id"],
                pick["version"] if pick else None,
                f"initial · Latest qualified → {'v' + str(pick['version']) if pick else 'nothing'}",
            ),
        )


def _current_rules(c, ws, project_id):
    return c.execute(
        "SELECT * FROM projects.selection_rules WHERE workspace_id=%s AND project_id=%s AND valid_to IS NULL ORDER BY alias",
        (ws, project_id),
    ).fetchall()


def _current_eval_rules(c, ws, project_id):
    return c.execute(
        "SELECT * FROM projects.evaluator_selection_rules WHERE workspace_id=%s AND project_id=%s AND valid_to IS NULL ORDER BY criterion_id",
        (ws, project_id),
    ).fetchall()


def _bindable(c, ws, project_id):
    for rule in _current_rules(c, ws, project_id):
        pick, code, reason = selection.resolve_environment(c, rule)
        if not pick:
            return {"ok": False, "alias": rule["alias"], "code": code, "reason": reason}
    return {"ok": True, "alias": None, "code": None, "reason": None}


# --- reselection -----------------------------------------------------------------------------------------------


def _replace_rule(c, table, keycol, row, **changes):
    c.execute(
        f"UPDATE projects.{table} SET valid_to=clock_timestamp() WHERE workspace_id=%s AND project_id=%s AND {keycol}=%s AND valid_to IS NULL",
        (row["workspace_id"], row["project_id"], row[keycol]),
    )
    new = {**row, **changes}
    new.pop("valid_from", None)
    new.pop("valid_to", None)
    cols = list(new.keys())
    values = [Jsonb(v) if isinstance(v, (dict, list)) else v for v in new.values()]
    c.execute(
        f"INSERT INTO projects.{table}({','.join(cols)}) VALUES({','.join(['%s'] * len(cols))})",
        values,
    )


def reselect_project(c, ws, project, trigger=None):
    trigger = trigger or {}
    pid = project["project_id"]
    cause = CAUSE.get(trigger.get("event"), "automatic_new_version")
    env_changed = eval_changed = False
    problems, stopped = [], []
    for rule in _current_rules(c, ws, pid):
        pick, code, reason = selection.resolve_environment(c, rule)
        new = pick["id"] if pick else None
        if (
            trigger.get("urgent")
            and rule["resolved_version_id"] == trigger.get("version_id")
            and new != rule["resolved_version_id"]
        ):
            stopped.append({"alias": rule["alias"], "rule": rule, "now": new})
        if new != rule["resolved_version_id"]:
            why = {
                "automatic_revoked": f"{short(rule['resolved_version_id'])} revoked",
                "automatic_failed": f"{short(rule['resolved_version_id'])} failed re-qualification",
                "automatic_deprecated": f"{short(rule['resolved_version_id'])} deprecated",
            }.get(cause, f"{short(new)} qualified")
            note = f"{short(rule['resolved_version_id'])} → {short(new)} · automatic · {rule_label(rule)} · {why}"
            _replace_rule(
                c,
                "selection_rules",
                "alias",
                rule,
                resolved_version_id=new,
                change_cause=cause,
                change_note=note,
            )
            emit(
                c,
                ws,
                "binding.changed",
                f"{pid}:{rule['alias']}",
                {
                    "project_id": pid,
                    "alias": rule["alias"],
                    "from": rule["resolved_version_id"],
                    "to": new,
                    "resolved": new is not None,
                    "cause": cause,
                    "note": note,
                },
            )
            env_changed = True
            if new:
                inbox.close_for_version(c, ws, rule["contract_id"], new)
        if not pick:
            problems.append({"alias": rule["alias"], "code": code, "reason": reason, "rule": rule})
    for rule in _current_eval_rules(c, ws, pid):
        pick, code, reason = selection.resolve_evaluator(c, ws, rule)
        new = pick["version"] if pick else None
        if new != rule["resolved_version"]:
            note = (
                f"v{rule['resolved_version']} → {'v' + str(new) if new else 'nothing'} · automatic · {rule_label(rule)}"
                + (
                    " · new leaderboard cohort"
                    if new
                    else " · admission refuses runs that need it (B4)"
                )
            )
            _replace_rule(
                c,
                "evaluator_selection_rules",
                "criterion_id",
                rule,
                resolved_version=new,
                change_cause=cause
                if cause in ("automatic_revoked", "automatic_deprecated")
                else "automatic_new_version",
                change_note=note,
                changed_by="rlgym",
            )
            emit(
                c,
                ws,
                "binding.changed",
                f"{pid}:{rule['criterion_id']}",
                {
                    "project_id": pid,
                    "criterion": rule["criterion_id"],
                    "from": rule["resolved_version"],
                    "to": new,
                    "resolved": new is not None,
                    "note": note,
                },
            )
            eval_changed = True
        if not pick:
            problems.append({"criterion": rule["criterion_id"], "code": code, "reason": reason})
    before = project["state"]
    after = refresh_state(c, ws, pid)
    if trigger.get("urgent") and stopped:
        for p in stopped:
            emit(
                c,
                ws,
                "project.blocked" if not p["now"] else "environment.stopped",
                f"{pid}:{p['alias']}",
                {
                    "project_id": pid,
                    "alias": p["alias"],
                    "urgent": True,
                    "code": "urgent",
                    "reason": f"{short(trigger['version_id'])} failed re-qualification; "
                    + (
                        f"now selecting {short(p['now'])}"
                        if p["now"]
                        else "nothing can be selected"
                    ),
                },
            )
    elif after == "blocked" and before != "blocked":
        for p in problems:
            if "alias" in p:
                emit(
                    c,
                    ws,
                    "project.blocked",
                    f"{pid}:{p['alias']}",
                    {
                        "project_id": pid,
                        "alias": p["alias"],
                        "code": p["code"],
                        "reason": f"{project['name']}: {p['reason']}",
                        "urgent": bool(trigger.get("urgent")),
                    },
                )
    for p in stopped:
        _auto_environment_defect(c, ws, project, p, trigger)
    for p in problems:
        if (
            "alias" in p
            and p["code"] == "B2"
            and not any(s["alias"] == p["alias"] for s in stopped)
        ):
            _auto_environment_defect(c, ws, project, p, trigger)
    return {
        "project_id": pid,
        "name": project["name"],
        "env_changed": env_changed,
        "evaluator_changed": eval_changed,
        "state": after,
    }


def _auto_environment_defect(c, ws, project, problem, trigger):
    """B2: nothing can be selected. The RL Gym sends an environment_defect item by itself (urgent when the version
    failed re-qualification)."""
    version = trigger.get("version_id") or problem["rule"]["resolved_version_id"]
    if not version:
        return
    failed = [ch for ch in trigger.get("checks", []) if ch.get("result") == "fail"]
    try:
        inbox.create(
            c,
            ws,
            "rlgym",
            {
                "kind": "environment_defect",
                "template_id": project["template_id"],
                "version": project["template_version"],
                "environment_version": version,
                "project_id": project["project_id"],
                "summary": (
                    f"{short(version)} failed re-qualification ({', '.join(ch['name'] for ch in failed) or 'check failed'}); "
                    f"the RL Gym stopped selecting it. "
                    + (
                        f"{project['name']} moved to {short(problem['now'])} automatically ({rule_label(problem['rule'])})."
                        if problem.get("now")
                        else f"No qualified version of {problem['rule']['contract_id']} remains: {project['name']} is Blocked."
                    )
                ),
                "evidence": {
                    "receipt_id": trigger.get("receipt_id"),
                    "failed_checks": failed,
                    "likely_cause": failed[0].get("likely_cause") if failed else None,
                    "impact": {
                        "projects": [project["project_id"]],
                        "blocked_tasks": _task_count(c, ws, project["project_id"]),
                    },
                },
            },
            urgent=bool(trigger.get("urgent")),
        )
    except GymError as exc:
        if exc.code != "CONFLICT":
            raise


def reselect_all(c, ws, trigger=None):
    out = []
    for project in c.execute(
        "SELECT * FROM projects.projects WHERE workspace_id=%s ORDER BY project_id", (ws,)
    ).fetchall():
        out.append(reselect_project(c, ws, project, trigger))
    return out


def _task_count(c, ws, pid):
    return c.execute(
        "SELECT count(*) n FROM projects.task_imports WHERE workspace_id=%s AND project_id=%s AND state IN ('ready','blocked')",
        (ws, pid),
    ).fetchone()["n"]


def refresh_state(c, ws, pid):
    project = c.execute(
        "SELECT * FROM projects.projects WHERE workspace_id=%s AND project_id=%s", (ws, pid)
    ).fetchone()
    activation = c.execute(
        "SELECT state FROM catalog.template_activations WHERE workspace_id=%s AND template_id=%s AND version=%s",
        (ws, project["template_id"], project["template_version"]),
    ).fetchone()
    reasons = []
    if not activation or activation["state"] == "revoked":
        state = "revoked"
        reasons.append("Template version revoked: no new runs")
    else:
        for rule in _current_rules(c, ws, pid):
            pick, code, reason = selection.resolve_environment(c, rule)
            if not pick:
                reasons.append(f"{code} · {rule['alias']}: {reason}")
        for rule in _current_eval_rules(c, ws, pid):
            pick, code, reason = selection.resolve_evaluator(c, ws, rule)
            if not pick:
                reasons.append(f"{code} · {rule['criterion_id']}: {reason}")
        state = "blocked" if reasons else ("running" if project["state"] == "running" else "ready")
    env_ok = not any(r.startswith(("B1", "B2", "B3")) for r in reasons) and state != "revoked"
    task_state, task_reason = (
        ("ready", None)
        if env_ok
        else (
            "blocked",
            "BINDING_UNRESOLVED: "
            + "; ".join(r for r in reasons if r.startswith(("B1", "B2", "B3"))),
        )
    )
    flipped = c.execute(
        """UPDATE projects.task_imports SET state=%s, state_reason=%s WHERE workspace_id=%s AND project_id=%s
           AND state IN ('ready','blocked') AND state<>%s
           AND coalesce(state_reason,'') NOT LIKE 'TASK_NO_INSTRUCTIONS%%'
           AND coalesce(state_reason,'') NOT LIKE 'CLAUSE_INVALID%%' RETURNING task_id""",
        (task_state, task_reason, ws, pid, task_state),
    ).fetchall()
    if flipped:
        emit(
            c,
            ws,
            "task.ready" if task_state == "ready" else "task.blocked",
            pid,
            {"project_id": pid, "count": len(flipped), "reason": task_reason},
        )
    c.execute(
        "UPDATE projects.projects SET state=%s, state_reason=%s WHERE workspace_id=%s AND project_id=%s",
        (state, "; ".join(reasons) or None, ws, pid),
    )
    # A suite draft follows the project's ready tasks (a draft made while a task was blocked gains it once it's ready).
    from anvil.rlgym.suites.service import sync_drafts

    sync_drafts(c, ws, pid)
    return state


# --- overrides -------------------------------------------------------------------------------------------------


def _normalise_rule(contract_id, to_rule):
    kind = to_rule.get("kind")
    require(
        kind in ("pinned", "same_data", "latest"),
        "VALIDATION_FAILED",
        "Rule kind must be pinned, same_data or latest",
        field="to_rule.kind",
    )
    rule = {
        "contract_id": contract_id,
        "kind": kind,
        "pinned_version_id": None,
        "seed_family": None,
    }
    if kind == "pinned":
        require(
            to_rule.get("pinned_version_id"),
            "VALIDATION_FAILED",
            "A pinned rule names a version",
            field="to_rule.pinned_version_id",
        )
        require(
            to_rule["pinned_version_id"].startswith(contract_id + "@"),
            "BINDING_INCOMPATIBLE",
            "The version belongs to another contract",
        )
        rule["pinned_version_id"] = to_rule["pinned_version_id"]
    if kind == "same_data":
        require(
            to_rule.get("seed_family"),
            "VALIDATION_FAILED",
            "A same-data rule names a seed family",
            field="to_rule.seed_family",
        )
        rule["seed_family"] = to_rule["seed_family"]
    return rule


def _rule_json(rule):
    return {
        k: rule.get(k)
        for k in ("kind", "pinned_version_id", "seed_family")
        if rule.get(k) is not None
    }


def rule_options(c, ws, pid, alias):
    """Rules a person may request: those that select a qualified version of the same contract."""
    current = next((r for r in _current_rules(c, ws, pid) if r["alias"] == alias), None)
    if not current:
        raise GymError("NOT_FOUND", "Alias not found")
    versions = selection.selectable_environments(c, current["contract_id"])
    options = []
    for fam in sorted({v["seed_family"] for v in versions}):
        options.append({"kind": "same_data", "seed_family": fam})
    for v in versions:
        options.append({"kind": "pinned", "pinned_version_id": v["id"]})
    if versions:
        options.append({"kind": "latest"})
    out = []
    for o in options:
        rule = {"contract_id": current["contract_id"], **o}
        pick, _, _ = selection.resolve_environment(
            c, {"pinned_version_id": None, "seed_family": None, **rule}
        )
        same = _rule_json(current) == _rule_json(rule)
        out.append(
            {
                **o,
                "label": rule_label({"pinned_version_id": None, "seed_family": None, **rule}),
                "selects": pick["id"],
                "cases": (pick["case_catalog"] or {}).get("cases"),
                "current": same,
            }
        )
    return out


def request_override(c, ws, actor, body):
    actor.require_person()
    pid, alias = body.get("project_id"), body.get("alias")
    reason = (body.get("reason") or "").strip()
    require(reason, "VALIDATION_FAILED", "A reason is required", field="reason")
    project = get_project_row(c, ws, pid)
    current = next((r for r in _current_rules(c, ws, pid) if r["alias"] == alias), None)
    require(current, "VALIDATION_FAILED", "Unknown alias", field="alias")
    rule = _normalise_rule(current["contract_id"], body.get("to_rule") or {})
    require(
        _rule_json(rule) != _rule_json(current),
        "VALIDATION_FAILED",
        "The requested rule is the current rule",
    )
    pick, code, why = selection.resolve_environment(c, rule)
    if not pick:
        raise GymError(
            "BINDING_INCOMPATIBLE", f"The requested rule selects nothing ({why})", {"code": code}
        )
    from_pick, _, _ = selection.resolve_environment(c, current)
    from_family = from_pick["seed_family"] if from_pick else current["seed_family"]
    data_change = from_family is not None and pick["seed_family"] != from_family
    if c.execute(
        "SELECT 1 FROM projects.rule_overrides WHERE workspace_id=%s AND project_id=%s AND alias=%s AND decision='requested'",
        (ws, pid, alias),
    ).fetchone():
        raise GymError("CONFLICT", "An override request is already waiting for this alias")
    n = (
        c.execute(
            "SELECT count(*) n FROM projects.rule_overrides WHERE workspace_id=%s", (ws,)
        ).fetchone()["n"]
        + 1
    )
    oid = str(uuid4())
    row = c.execute(
        """INSERT INTO projects.rule_overrides(id,short_id,workspace_id,project_id,alias,from_rule,to_rule,from_version_id,to_version_id,
             data_change,reason,requested_by,decision) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'requested') RETURNING *""",
        (
            oid,
            f"ov-{n:02d}",
            ws,
            pid,
            alias,
            Jsonb(_rule_json(current)),
            Jsonb(_rule_json(rule)),
            from_pick["id"] if from_pick else None,
            pick["id"],
            data_change,
            reason,
            actor.id,
        ),
    ).fetchone()
    summary = f"{rule_label(current)} → {rule_label(rule)} (selects {short(pick['id'])})"
    audit(
        c,
        ws,
        actor,
        "rule_override.requested",
        row["short_id"],
        reason,
        {"project_id": pid, "alias": alias, "to_rule": _rule_json(rule)},
    )
    emit(
        c,
        ws,
        "rule_override.requested",
        row["short_id"],
        {
            "override_id": row["short_id"],
            "project_id": pid,
            "project_name": project["name"],
            "alias": alias,
            "summary": summary,
            "requested_by_name": actor.name,
        },
    )
    return row


def decide_override(c, ws, actor, short_id, body):
    actor.require_person()
    decision = body.get("decision")
    note = (body.get("note") or "").strip()
    require(
        decision in ("approved", "rejected"),
        "VALIDATION_FAILED",
        "decision must be approved or rejected",
        field="decision",
    )
    row = c.execute(
        "SELECT * FROM projects.rule_overrides WHERE workspace_id=%s AND short_id=%s FOR UPDATE",
        (ws, short_id),
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "Override not found")
    require(row["decision"] == "requested", "CONFLICT", f"Override already {row['decision']}")
    require(actor.binding_approver, "FORBIDDEN", "Only a binding approver may decide an override")
    require(
        str(row["requested_by"]) != actor.id,
        "VALIDATION_FAILED",
        "A different person must decide: you requested this override",
        field="decided_by",
    )
    if decision == "rejected":
        require(note, "VALIDATION_FAILED", "A decision note is required to reject", field="note")
        c.execute(
            "UPDATE projects.rule_overrides SET decision='rejected', decided_by=%s, decided_at=now(), decision_note=%s WHERE id=%s",
            (actor.id, note, row["id"]),
        )
    else:
        ack = bool(body.get("new_cohort_acknowledged"))
        require(
            not row["data_change"] or ack,
            "VALIDATION_FAILED",
            "The seed family changes: tick 'I understand results will start a new cohort'",
            field="new_cohort_acknowledged",
        )
        current = next(
            r for r in _current_rules(c, ws, row["project_id"]) if r["alias"] == row["alias"]
        )
        rule = _normalise_rule(current["contract_id"], row["to_rule"])
        pick, code, why = selection.resolve_environment(c, rule)
        if not pick:
            raise GymError(
                "BINDING_INCOMPATIBLE",
                f"The requested rule no longer selects a qualified version ({why})",
            )
        c.execute(
            """UPDATE projects.rule_overrides SET decision='approved', decided_by=%s, decided_at=now(), decision_note=%s,
                     new_cohort_acknowledged=%s WHERE id=%s""",
            (actor.id, note or None, ack, row["id"]),
        )
        note_text = f"{rule_label(current)} → {rule_label(rule)} · override {row['short_id']} approved by {actor.name} · selects {short(pick['id'])}"
        _replace_rule(
            c,
            "selection_rules",
            "alias",
            current,
            kind=rule["kind"],
            pinned_version_id=rule["pinned_version_id"],
            seed_family=rule["seed_family"],
            override_id=row["id"],
            resolved_version_id=pick["id"],
            change_cause="override",
            change_note=note_text,
        )
        emit(
            c,
            ws,
            "binding.changed",
            f"{row['project_id']}:{row['alias']}",
            {
                "project_id": row["project_id"],
                "alias": row["alias"],
                "from": current["resolved_version_id"],
                "to": pick["id"],
                "resolved": True,
                "cause": "override",
                "note": note_text,
            },
        )
        refresh_state(c, ws, row["project_id"])
    audit(c, ws, actor, f"rule_override.{decision}", row["short_id"], note or None)
    emit(
        c,
        ws,
        "rule_override.decided",
        row["short_id"],
        {"override_id": row["short_id"], "project_id": row["project_id"], "decision": decision},
    )
    return c.execute("SELECT * FROM projects.rule_overrides WHERE id=%s", (row["id"],)).fetchone()


def remove_override(c, ws, actor, short_id):
    """Return the alias to the template's rule. No approval: it only restores the designer's rule."""
    actor.require_person()
    row = c.execute(
        "SELECT * FROM projects.rule_overrides WHERE workspace_id=%s AND short_id=%s FOR UPDATE",
        (ws, short_id),
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "Override not found")
    require(row["decision"] == "approved", "CONFLICT", "Only an approved override can be removed")
    current = next(
        r for r in _current_rules(c, ws, row["project_id"]) if r["alias"] == row["alias"]
    )
    require(
        str(current["override_id"]) == str(row["id"]),
        "CONFLICT",
        "This override is no longer the active rule",
    )
    template_rule = _normalise_rule(current["contract_id"], current["template_rule"])
    pick, _, why = selection.resolve_environment(c, template_rule)
    note = f"override {row['short_id']} removed by {actor.name} · back to template rule {rule_label(template_rule)} → {short(pick['id']) if pick else 'nothing'}"
    _replace_rule(
        c,
        "selection_rules",
        "alias",
        current,
        kind=template_rule["kind"],
        pinned_version_id=template_rule["pinned_version_id"],
        seed_family=template_rule["seed_family"],
        override_id=None,
        resolved_version_id=pick["id"] if pick else None,
        change_cause="override_removed",
        change_note=note,
    )
    c.execute(
        "UPDATE projects.rule_overrides SET decision='removed', removed_by=%s, removed_at=now() WHERE id=%s",
        (actor.id, row["id"]),
    )
    audit(c, ws, actor, "rule_override.removed", row["short_id"])
    emit(
        c,
        ws,
        "rule_override.removed",
        row["short_id"],
        {"override_id": row["short_id"], "project_id": row["project_id"]},
    )
    emit(
        c,
        ws,
        "binding.changed",
        f"{row['project_id']}:{row['alias']}",
        {
            "project_id": row["project_id"],
            "alias": row["alias"],
            "to": pick["id"] if pick else None,
            "resolved": pick is not None,
            "note": note,
        },
    )
    refresh_state(c, ws, row["project_id"])
    return c.execute("SELECT * FROM projects.rule_overrides WHERE id=%s", (row["id"],)).fetchone()


def set_evaluator_rule(c, ws, actor, pid, criterion, body):
    """PUT /projects/{id}/evaluator-rules/{criterion}: Latest qualified, or Pinned (its own leaderboard group)."""
    actor.require_person()
    reason = (body.get("reason") or "").strip()
    require(reason, "VALIDATION_FAILED", "A reason is required", field="reason")
    get_project_row(c, ws, pid)
    current = next(
        (r for r in _current_eval_rules(c, ws, pid) if r["criterion_id"] == criterion), None
    )
    if not current:
        raise GymError("NOT_FOUND", "Criterion not found")
    kind = body.get("kind")
    require(
        kind in ("latest_qualified", "pinned"),
        "VALIDATION_FAILED",
        "kind must be latest_qualified or pinned",
        field="kind",
    )
    rule = {
        "configuration_id": current["configuration_id"],
        "kind": kind,
        "pinned_version": body.get("pinned_version") if kind == "pinned" else None,
    }
    pick, code, why = selection.resolve_evaluator(c, ws, rule)
    if not pick:
        raise GymError("BINDING_INCOMPATIBLE", f"The rule selects nothing ({why})")
    note = f"{rule_label(current)} → {rule_label(rule)}{' v' + str(rule['pinned_version']) if kind == 'pinned' else ''} · by {actor.name} · {reason}"
    _replace_rule(
        c,
        "evaluator_selection_rules",
        "criterion_id",
        current,
        kind=kind,
        pinned_version=rule["pinned_version"],
        resolved_version=pick["version"],
        change_cause="pinned_by_project" if kind == "pinned" else "unpinned",
        change_note=note,
        changed_by=actor.id,
    )
    audit(c, ws, actor, "evaluator_rule.changed", f"{pid}:{criterion}", reason, rule)
    emit(
        c,
        ws,
        "binding.changed",
        f"{pid}:{criterion}",
        {
            "project_id": pid,
            "criterion": criterion,
            "to": pick["version"],
            "resolved": True,
            "note": note,
        },
    )
    refresh_state(c, ws, pid)
    return {"criterion_id": criterion, **rule, "resolved_version": pick["version"]}


# --- views -----------------------------------------------------------------------------------------------------


def get_project_row(c, ws, pid):
    row = c.execute(
        "SELECT * FROM projects.projects WHERE workspace_id=%s AND project_id=%s", (ws, pid)
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "Not found or no longer available")
    return row


def environment_lines(c, ws, pid):
    lines = []
    for rule in _current_rules(c, ws, pid):
        pick, code, reason = selection.resolve_environment(c, rule)
        if pick:
            lines.append(
                {
                    "alias": rule["alias"],
                    "ok": True,
                    "version_id": pick["id"],
                    "label": f"{rule['alias']} · {short(pick['id'])} · Qualified",
                    "rule": rule_label(rule),
                    "override": rule["override_id"] is not None,
                }
            )
        else:
            last = rule["resolved_version_id"] or rule["pinned_version_id"]
            state = None
            if last:
                v = c.execute(
                    "SELECT state FROM catalog.environment_versions WHERE id=%s", (last,)
                ).fetchone()
                state = v["state"] if v else None
            lines.append(
                {
                    "alias": rule["alias"],
                    "ok": False,
                    "version_id": last,
                    "code": code,
                    "reason": reason,
                    "label": f"{rule['alias']} · {short(last) if last else rule['contract_id']} · {code}: {reason}",
                    "rule": rule_label(rule),
                    "version_state": state,
                    "override": rule["override_id"] is not None,
                }
            )
    return lines


def suggested_actions(c, ws, project):
    pid = project["project_id"]
    actions = []
    for rule in _current_rules(c, ws, pid):
        pick, code, reason = selection.resolve_environment(c, rule)
        if code in ("B1", "B3") and selection.selectable_environments(c, rule["contract_id"]):
            actions.append(
                {
                    "rule": 1,
                    "label": "Fix bindings",
                    "kind": "bad",
                    "reason": reason,
                    "link": f"/gym/projects/{pid}/selection-rules?fix={rule['alias']}",
                }
            )
        if code == "B2":
            item = c.execute(
                """SELECT * FROM catalog.inbox_items WHERE workspace_id=%s AND kind='environment_defect' AND project_id=%s
                   AND state NOT IN ('closed','declined') ORDER BY sent_at DESC LIMIT 1""",
                (ws, pid),
            ).fetchone()
            version = (
                rule["resolved_version_id"]
                or rule["pinned_version_id"]
                or (item and item["environment_version_id"])
            )
            if not version:
                last = c.execute(
                    "SELECT id FROM catalog.environment_versions WHERE contract_id=%s ORDER BY version DESC LIMIT 1",
                    (rule["contract_id"],),
                ).fetchone()
                version = last["id"] if last else None
            actions.append(
                {
                    "rule": 2,
                    "label": "Track inbox item" if item else "Report environment defect",
                    "kind": "bad",
                    "reason": reason,
                    "link": f"/gym/admin/environments/{version}"
                    if version
                    else "/gym/admin/environments",
                }
            )
    for rule in _current_eval_rules(c, ws, pid):
        pick, code, reason = selection.resolve_evaluator(c, ws, rule)
        if not pick:
            last = c.execute(
                "SELECT max(version) v FROM catalog.evaluator_configurations WHERE workspace_id=%s AND id=%s",
                (ws, rule["configuration_id"]),
            ).fetchone()["v"]
            actions.append(
                {
                    "rule": 2.5,
                    "label": "Create evaluator fix version",
                    "kind": "bad",
                    "reason": reason,
                    "link": f"/gym/admin/evaluators/{rule['configuration_id']}/{last}",
                }
            )
            break
    if c.execute(
        "SELECT 1 FROM projects.rule_overrides WHERE workspace_id=%s AND project_id=%s AND decision='requested'",
        (ws, pid),
    ).fetchone():
        ov = c.execute(
            "SELECT short_id FROM projects.rule_overrides WHERE workspace_id=%s AND project_id=%s AND decision='requested' LIMIT 1",
            (ws, pid),
        ).fetchone()
        actions.append(
            {
                "rule": 3,
                "label": "Approve override",
                "kind": "warn",
                "reason": f"{ov['short_id']} waits for a binding approver",
                "link": f"/gym/projects/{pid}/selection-rules?review={ov['short_id']}",
            }
        )
    blocked = c.execute(
        "SELECT count(*) n FROM projects.task_imports WHERE workspace_id=%s AND project_id=%s AND state='blocked'",
        (ws, pid),
    ).fetchone()["n"]
    if blocked and not actions:
        actions.append(
            {
                "rule": 4,
                "label": "Review blocked tasks",
                "kind": "warn",
                "reason": f"{blocked} tasks blocked",
                "link": f"/gym/projects/{pid}/tasks",
            }
        )
    if project["state"] == "ready":
        actions.append(
            {
                "rule": 5,
                "label": "Run benchmark",
                "kind": "ok",
                "reason": "Never run (Runs arrive with work package 2.7)",
                "link": f"/gym/runs/new?project={pid}",
            }
        )
    actions.append(
        {
            "rule": 7,
            "label": "View tasks",
            "kind": "ok",
            "reason": "Nothing pending" if len(actions) == 0 else "",
            "link": f"/gym/projects/{pid}/tasks",
        }
    )
    actions.sort(key=lambda a: a["rule"])
    return actions


def project_summary(c, ws, project):
    last = c.execute(
        "SELECT * FROM projects.project_exports WHERE workspace_id=%s AND project_id=%s ORDER BY received_at DESC LIMIT 1",
        (ws, project["project_id"]),
    ).fetchone()
    tasks = c.execute(
        "SELECT count(*) n FROM projects.task_imports WHERE workspace_id=%s AND project_id=%s AND state<>'superseded'",
        (ws, project["project_id"]),
    ).fetchone()["n"]
    activation = c.execute(
        "SELECT name FROM catalog.template_activations WHERE workspace_id=%s AND template_id=%s AND version=%s",
        (ws, project["template_id"], project["template_version"]),
    ).fetchone()
    overrides = c.execute(
        "SELECT count(*) n FROM projects.rule_overrides WHERE workspace_id=%s AND project_id=%s AND decision='requested'",
        (ws, project["project_id"]),
    ).fetchone()["n"]
    return {
        **project,
        "template_name": activation["name"] if activation else project["template_id"],
        "tasks": tasks,
        "environments": environment_lines(c, ws, project["project_id"]),
        "overrides_waiting": overrides,
        "last_export": last
        and {
            k: last[k]
            for k in (
                "export_id",
                "received_at",
                "new_count",
                "superseding_count",
                "unchanged_count",
                "blocked_count",
                "reason",
            )
        }
        | {"map_attached_count": int((last["receipt"] or {}).get("map_attached") or 0)},
        "suggested_actions": suggested_actions(c, ws, project),
    }


def list_projects(c, ws, q=None, state=None):
    sql, params = "SELECT * FROM projects.projects WHERE workspace_id=%s", [ws]
    if q:
        sql += " AND (name ILIKE %s OR project_id ILIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    if state:
        sql += " AND state=%s"
        params.append(state)
    return [project_summary(c, ws, p) for p in c.execute(sql + " ORDER BY name", params).fetchall()]


def tasks(c, ws, pid, q=None, state=None):
    get_project_row(c, ws, pid)
    sql = """SELECT t.id, t.task_id, t.revision, t.title, t.package_sha256, t.case_selector, t.state, t.state_reason, t.export_id,
               t.sme_batch_id, t.created_at, prev.revision AS corrects_revision
             FROM projects.task_imports t LEFT JOIN projects.task_imports prev ON prev.id=t.corrects_id
             WHERE t.workspace_id=%s AND t.project_id=%s"""
    params = [ws, pid]
    if q:
        sql += " AND (t.task_id ILIKE %s OR t.title ILIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    if state:
        sql += " AND t.state=%s"
        params.append(state)
    return c.execute(sql + " ORDER BY t.task_id, t.revision DESC", params).fetchall()


def task_detail(c, ws, actor, pid, task_id, revision=None):
    project = get_project_row(c, ws, pid)
    sql = (
        "SELECT * FROM projects.task_imports WHERE workspace_id=%s AND project_id=%s AND task_id=%s"
    )
    params = [ws, pid, task_id]
    if revision:
        sql += " AND revision=%s"
        params.append(int(revision))
    row = c.execute(sql + " ORDER BY revision DESC LIMIT 1", params).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "Task not found")
    parts = {
        r["part"]: r["content"]
        for r in c.execute(
            "SELECT part, content FROM projects.task_payloads WHERE workspace_id=%s AND package_sha256=%s",
            (ws, row["package_sha256"]),
        ).fetchall()
    }
    # "Reviewer only": readable by signed-in members, every view audited (D12, G-31); never sent to runners or exports.
    audit(c, ws, actor, "task.private_viewed", f"{pid}:{task_id}@{row['revision']}")
    activation = c.execute(
        "SELECT name, workflow FROM catalog.template_activations WHERE workspace_id=%s AND template_id=%s AND version=%s",
        (ws, project["template_id"], project["template_version"]),
    ).fetchone()
    revisions = c.execute(
        "SELECT revision, state, export_id, package_sha256 FROM projects.task_imports WHERE workspace_id=%s AND project_id=%s AND task_id=%s ORDER BY revision",
        (ws, pid, task_id),
    ).fetchall()
    return {
        "task": row,
        "actor": parts.get("actor"),
        "private": parts.get("private"),
        "private_label": "Reviewer only · view audited",
        "template_name": activation["name"] if activation else project["template_id"],
        "workflow": activation["workflow"] if activation else None,
        "project": {"project_id": pid, "name": project["name"], "mode": project["mode"]},
        "revisions": revisions,
        "runs": [],
        "runs_note": "Runs arrive with work package 2.7.",
    }


def exports(c, ws, pid):
    get_project_row(c, ws, pid)
    return c.execute(
        """SELECT export_id, export_sha256, received_at, new_count, superseding_count, unchanged_count, blocked_count, reason, blocked,
                  receipt_sha256, coalesce((receipt->>'map_attached')::int, 0) map_attached_count
                  FROM projects.project_exports WHERE workspace_id=%s AND project_id=%s ORDER BY received_at DESC""",
        (ws, pid),
    ).fetchall()


def selection_view(c, ws, pid, actor):
    project_row = get_project_row(c, ws, pid)
    aliases = []
    for rule in _current_rules(c, ws, pid):
        pick, code, reason = selection.resolve_environment(c, rule)
        history = c.execute(
            """SELECT kind, pinned_version_id, seed_family, resolved_version_id, change_cause, change_note, valid_from, valid_to
               FROM projects.selection_rules WHERE workspace_id=%s AND project_id=%s AND alias=%s ORDER BY valid_from""",
            (ws, pid, rule["alias"]),
        ).fetchall()
        aliases.append(
            {
                "alias": rule["alias"],
                "contract_id": rule["contract_id"],
                "rule": rule_label(rule),
                "rule_raw": _rule_json(rule),
                "template_rule": rule_label(
                    {"pinned_version_id": None, "seed_family": None, **rule["template_rule"]}
                ),
                "override": rule["override_id"] is not None,
                "override_id": rule["override_id"],
                "would_bind": pick["id"] if pick else None,
                "ok": pick is not None,
                "code": code,
                "reason": reason,
                "history": history,
                "options": rule_options(c, ws, pid, rule["alias"]),
            }
        )
    criteria = []
    for rule in _current_eval_rules(c, ws, pid):
        pick, code, reason = selection.resolve_evaluator(c, ws, rule)
        criteria.append(
            {
                "criterion_id": rule["criterion_id"],
                "configuration_id": rule["configuration_id"],
                "kind": rule["kind"],
                "rule": rule_label(rule)
                + (f" · v{rule['pinned_version']}" if rule["kind"] == "pinned" else ""),
                "binds_now": pick["version"] if pick else None,
                "ok": pick is not None,
                "reason": reason,
                "last_note": rule["change_note"],
            }
        )
    # D-034: how each criterion is scored now (Scored by, and the checks behind it).
    from anvil.rlgym.results import scorer

    scoring_now = scorer.for_project(c, ws, project_row, criteria)
    for cr in criteria:
        cr["scoring"] = scoring_now.get(cr["criterion_id"])
    eval_history = c.execute(
        """SELECT criterion_id, kind, pinned_version, resolved_version, change_cause, change_note, valid_from FROM projects.evaluator_selection_rules
           WHERE workspace_id=%s AND project_id=%s AND change_cause<>'initial' ORDER BY valid_from""",
        (ws, pid),
    ).fetchall()
    overrides = c.execute(
        """SELECT o.*, ru.name AS requested_by_name, du.name AS decided_by_name FROM projects.rule_overrides o
           LEFT JOIN admin.users ru ON ru.workspace_id=o.workspace_id AND ru.id=o.requested_by
           LEFT JOIN admin.users du ON du.workspace_id=o.workspace_id AND du.id=o.decided_by
           WHERE o.workspace_id=%s AND o.project_id=%s ORDER BY o.requested_at DESC""",
        (ws, pid),
    ).fetchall()
    for o in overrides:
        to_pick, _, _ = selection.resolve_environment(
            c,
            {
                "contract_id": next(a["contract_id"] for a in aliases if a["alias"] == o["alias"]),
                "pinned_version_id": None,
                "seed_family": None,
                **o["to_rule"],
            },
        )
        o["to_label"] = rule_label({"pinned_version_id": None, "seed_family": None, **o["to_rule"]})
        o["from_label"] = rule_label(
            {"pinned_version_id": None, "seed_family": None, **o["from_rule"]}
        )
        o["review"] = {
            "different_person": str(o["requested_by"]) != actor.id,
            "you_are_approver": actor.binding_approver,
            "version_safe": to_pick is not None,
            "selects_now": to_pick["id"] if to_pick else None,
            "data_change": o["data_change"],
            "tasks_affected": _task_count(c, ws, pid),
            "impact": "From the next run; runs already started keep their version (runs arrive with 2.7).",
        }
    inbox_items = inbox.list_items(c, ws, project_id=pid)
    return {
        "aliases": aliases,
        "criteria": criteria,
        "evaluator_history": eval_history,
        "overrides": overrides,
        "inbox_items": inbox_items,
        "me": {"id": actor.id, "name": actor.name, "binding_approver": actor.binding_approver},
    }
