"""E-005 §2.3: which environment versions a suite can be pointed at without any task needing re-authoring.

Only versions that are qualified are offered (choosing never builds an image). A version is greyed out, with the
reason, when:
- a tool any of the suite's tasks names (S3 tools, S5 steps and follow-ups) is missing from the version;
- a reference field the graders read (template blocks: case_reference.*, reference_answers.*) is missing;
- its image isn't on this machine (it would have to be built).
Allowed with a warning: an extra tool no task uses (the agent sees it).
Not checked yet: tool arguments and document types (the registry record carries operation ids only), said so.
"""

import re

from anvil.rlgym.catalog import selection

REF = re.compile(r"(?:case_reference|reference_answers)\.([A-Za-z0-9_]+)")


def task_tools(actor):
    actor = actor or {}
    tools = set(actor.get("tools") or [])
    sections = actor.get("sections") if isinstance(actor.get("sections"), dict) else {}
    s3 = sections.get("S3") if isinstance(sections.get("S3"), dict) else {}
    tools |= set(s3.get("tools") or [])
    s5 = sections.get("S5") if isinstance(sections.get("S5"), dict) else {}
    for step in s5.get("steps") or []:
        if isinstance(step, dict):
            if step.get("tool"):
                tools.add(step["tool"])
            for f in step.get("followUps") or []:
                if isinstance(f, dict):
                    tools |= {t for t in f.get("tools") or [] if isinstance(t, str)}
    return {t for t in tools if isinstance(t, str) and t}


def grader_reference_fields(blocks_by_criterion):
    import json

    return set(REF.findall(json.dumps(blocks_by_criterion or {})))


def _image_here(env):
    from anvil.rlgym.runs import openenv

    if not openenv.is_openenv(env):
        return True  # bridge images are built from the recipe at admission, as today
    try:
        return bool(openenv.local_image_id(openenv.recipe(env)["image_ref"]))
    except Exception:
        return False


def options(c, ws, sv_id):
    sv = c.execute(
        "SELECT * FROM suites.suite_versions WHERE workspace_id=%s AND id=%s", (ws, sv_id)
    ).fetchone()
    project = c.execute(
        "SELECT * FROM projects.projects WHERE workspace_id=%s AND project_id=%s",
        (ws, sv["project_id"]),
    ).fetchone()
    tasks = c.execute(
        """SELECT t.task_id, t.revision, p.content actor FROM suites.suite_tasks s
           JOIN projects.task_imports t ON t.id=s.task_import_id
           LEFT JOIN projects.task_payloads p ON p.workspace_id=t.workspace_id AND p.package_sha256=t.package_sha256 AND p.part='actor'
           WHERE s.suite_version_id=%s ORDER BY t.task_id""",
        (sv_id,),
    ).fetchall()
    blocks = {
        r["criterion_id"]: r["verifier_blocks"]
        for r in c.execute(
            "SELECT criterion_id, verifier_blocks FROM catalog.template_criteria WHERE workspace_id=%s AND template_id=%s AND version=%s",
            (ws, project["template_id"], project["template_version"]),
        ).fetchall()
    }
    needed_refs = grader_reference_fields(blocks)
    needed_tools = {t["task_id"]: task_tools(t["actor"]) for t in tasks}
    all_tools = set().union(*needed_tools.values()) if needed_tools else set()
    bindings = c.execute(
        "SELECT * FROM suites.suite_bindings WHERE suite_version_id=%s ORDER BY alias", (sv_id,)
    ).fetchall()
    out = []
    for b in bindings:
        contract = c.execute(
            "SELECT contract_id FROM catalog.environment_versions WHERE id=%s",
            (sv["planned_on_env_version"],),
        ).fetchone()
        contract_id = (contract or {}).get("contract_id") or (
            sv["planned_on_env_version"] or ""
        ).split("@")[0]
        versions = []
        for v in selection.selectable_environments(c, contract_id):
            ops = {o.get("operation_id") for o in v.get("operations") or [] if isinstance(o, dict)}
            fields = {
                f.get("name")
                for col in ((v.get("schema") or {}).get("collections") or [])
                if col.get("name") == "reference_answers"
                for f in col.get("fields") or []
            }
            reasons = []
            if not ops:
                reasons.append(
                    f"{v['id']}'s record lists no operations, so its tools can't be checked"
                )
            for task_id, tools in sorted(needed_tools.items()):
                missing = sorted(t for t in tools if ops and t not in ops)
                if missing:
                    reasons.append(
                        f"needs re-authoring: task {task_id[:8]} uses {', '.join(missing)}, which {v['id']} doesn't have"
                    )
            if fields:
                gone = sorted(f for f in needed_refs if f not in fields)
                if gone:
                    reasons.append(
                        f"graders read reference field(s) {', '.join(gone)}, which {v['id']} doesn't have (grader change: E-004)"
                    )
            if not _image_here(v):
                reasons.append(f"{v['id']} isn't built on this machine")
            extra = sorted(t for t in ops if all_tools and t not in all_tools)
            versions.append(
                {
                    "version_id": v["id"],
                    "version": v["version"],
                    "seed_family": v["seed_family"],
                    "cases": (v.get("case_catalog") or {}).get("cases"),
                    "current": v["id"] == sv["planned_on_env_version"],
                    "selectable": not reasons,
                    "reasons": reasons,
                    "warnings": [
                        f"{len(extra)} extra tool(s) no task uses (the agent sees them): {', '.join(extra[:6])}"
                    ]
                    if extra
                    else [],
                }
            )
        out.append(
            {
                "alias": b["alias"],
                "rule_kind": b["rule_kind"],
                "source": b["source"],
                "pinned_version_id": b["pinned_version_id"],
                "experiment": b["source"] == "experiment",
                "legacy_pin": b["rule_kind"] == "pinned" and b["source"] != "experiment",
                "versions": versions,
                "not_checked": "tool arguments and document types (the registry record lists operation ids only)",
            }
        )
    return {"bindings": out}
