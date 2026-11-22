"""To do items (ARCHITECTURE 10.1): `admin.notifications` rows opened and closed only by events."""

from uuid import uuid4

GROUPS = {
    "ready_to_run": "Ready to run",
    "bindings": "Bindings",
    "review": "Review",
    "import_export": "Import / Export",
    "studio_inbox": "Studio inbox",
}


def open_item(
    c,
    ws,
    event_id,
    kind,
    subject,
    group,
    title,
    reason,
    link,
    action_label=None,
    audience="workspace",
    project_id=None,
    severity="ok",
    user_id=None,
):
    c.execute(
        """INSERT INTO admin.notifications(id,workspace_id,kind,todo_group,project_id,subject,title,reason,action_label,
             link,severity,audience,user_id,opened_by_event)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (workspace_id, kind, subject) WHERE closed_at IS NULL
           DO UPDATE SET reason=EXCLUDED.reason, title=EXCLUDED.title, link=EXCLUDED.link""",
        (
            "td-" + uuid4().hex[:10],
            ws,
            kind,
            group,
            project_id,
            subject,
            title,
            reason,
            action_label,
            link,
            severity,
            audience,
            user_id,
            event_id,
        ),
    )


def close_items(c, ws, event_id, kind, subject=None, project_id=None):
    sql = "UPDATE admin.notifications SET closed_at=now(), closed_by_event=%s WHERE workspace_id=%s AND kind=%s AND closed_at IS NULL"
    params = [event_id, ws, kind]
    if subject is not None:
        sql += " AND subject=%s"
        params.append(subject)
    if project_id is not None:
        sql += " AND project_id=%s"
        params.append(project_id)
    c.execute(sql, params)


def on_event(c, ws, topic, d, event_id):
    p = d.get("project_id")
    name = d.get("project_name") or p
    link_project = f"/gym/projects/{p}" if p else "/gym/projects"
    if topic == "project.exported":
        close_items(c, ws, event_id, "export_received", project_id=p)
        open_item(
            c,
            ws,
            event_id,
            "export_received",
            d["export_id"],
            "import_export",
            f"Export {d['export_id']} received",
            f"{d['new']} new · {d['superseding']} superseding · {d['unchanged']} unchanged · {len(d['blocked'])} blocked",
            f"{link_project}/exports",
            "View import receipt",
            project_id=p,
        )
        if d.get("ready_tasks"):
            open_item(
                c,
                ws,
                event_id,
                "project_ready",
                p,
                "ready_to_run",
                name,
                d.get("ready_reason") or f"{d['ready_tasks']} ready tasks; never run",
                f"/gym/runs/new?project={p}",
                "Run benchmark",
                project_id=p,
            )
    elif topic == "task.blocked":
        open_item(
            c,
            ws,
            event_id,
            "tasks_blocked",
            p,
            "bindings",
            f"{d['count']} tasks blocked",
            d.get("reason", "A binding cannot select a version"),
            f"{link_project}/selection-rules",
            "See why",
            project_id=p,
            severity="bad",
        )
    elif topic == "task.ready":
        close_items(c, ws, event_id, "tasks_blocked", subject=p)
    elif topic == "rule_override.requested":
        open_item(
            c,
            ws,
            event_id,
            "override_waiting",
            d["override_id"],
            "bindings",
            "Override waiting for approval",
            f"{name} · {d['alias']}: {d['summary']} · requested by {d['requested_by_name']}",
            f"{link_project}/selection-rules?review={d['override_id']}",
            "Approve or reject",
            audience="binding_approvers",
            project_id=p,
            severity="warn",
        )
    elif topic == "rule_override.decided":
        close_items(c, ws, event_id, "override_waiting", subject=d["override_id"])
    elif topic == "binding.changed":
        if d.get("resolved") and d.get("cause") != "automatic_failed":
            close_items(c, ws, event_id, "version_revoked", project_id=p)
    elif topic == "registry.version.qualified":
        c.execute(
            """UPDATE admin.notifications SET closed_at=now(), closed_by_event=%s WHERE workspace_id=%s
                     AND kind='version_stopped' AND closed_at IS NULL""",
            (event_id, ws),
        )
    elif topic in ("project.blocked", "environment.stopped"):
        kind = "version_stopped" if d.get("urgent") else "version_revoked"
        open_item(
            c,
            ws,
            event_id,
            kind,
            f"{p}:{d['alias']}",
            "bindings",
            "Version stopped (urgent)" if d.get("urgent") else "Version revoked under a project",
            d["reason"],
            f"{link_project}/selection-rules",
            "See why",
            project_id=p,
            severity="bad",
        )
    elif topic == "inbox_item.status":
        item = d["item_id"]
        for kind in ("inbox_waiting", "inbox_released", "inbox_declined"):
            close_items(c, ws, event_id, kind, subject=item)
        label = d.get("label") or item
        if d["state"] in ("queued", "sent", "received", "planned"):
            extra = f" · planned {d['planned_version']}" if d.get("planned_version") else ""
            open_item(
                c,
                ws,
                event_id,
                "inbox_waiting",
                item,
                "studio_inbox",
                f"{label} · {d['kind']}",
                f"{d['summary']} · {d['state']}{extra} · waiting for Studio",
                d.get("link") or "/gym/admin/environments",
                None,
                project_id=p,
            )
        elif d["state"] == "released":
            open_item(
                c,
                ws,
                event_id,
                "inbox_released",
                item,
                "studio_inbox",
                f"{label} released",
                f"New version {d.get('released_version')} has what you asked for: re-plan and run",
                d.get("link") or "/gym/projects",
                "Re-plan suite" if d["kind"] == "more_data" else "Open",
                project_id=p,
            )
        elif d["state"] == "declined":
            open_item(
                c,
                ws,
                event_id,
                "inbox_declined",
                item,
                "studio_inbox",
                f"{label} declined",
                d.get("decline_reason") or "Declined by Studio",
                d.get("link") or "/gym/projects",
                "View reason",
                project_id=p,
                severity="warn",
            )
    elif topic == "evaluator.revoked" and not d.get("replacement"):
        open_item(
            c,
            ws,
            event_id,
            "evaluator_no_replacement",
            d["id"],
            "bindings",
            f"{d['id']} v{d['version']} revoked with no replacement",
            "Admission refuses runs that need this criterion until the RL Gym qualifies a fix version",
            f"/gym/admin/evaluators/{d['id']}/{d['version']}",
            "Create fix version",
            severity="bad",
        )
    elif topic == "evaluator.qualified":
        close_items(c, ws, event_id, "evaluator_no_replacement", subject=d["id"])
        # A fix version the RL Gym made after an SME "grader is wrong" decision: re-score is offered, never automatic.
        for item in c.execute(
            """SELECT i.id, b.run_id, b.project_id FROM results.sme_review_items i JOIN results.sme_review_batches b ON b.id=i.batch_id
               WHERE i.workspace_id=%s AND i.fix_configuration=%s AND i.fix_version=%s""",
            (ws, d["id"], d["version"]),
        ).fetchall():
            open_item(
                c,
                ws,
                event_id,
                "rescore_ready",
                f"{item['run_id']}:{d['id']}@{d['version']}",
                "review",
                "Fix version qualified",
                f"{d['id']} v{d['version']} qualified after SME review; re-score {item['run_id']} if you want it graded again (explicit)",
                f"/gym/runs/{item['run_id']}/sme",
                "Re-score…",
                project_id=item["project_id"],
            )
        for proj in d.get("new_cohort_projects", []):
            open_item(
                c,
                ws,
                event_id,
                "evaluator_new_cohort",
                f"{proj['project_id']}:{d['id']}",
                "review",
                "New evaluator version: new cohort",
                f"{d['id']} v{d['version']} qualified; the next run of {proj['name']} binds it (Latest qualified) and starts a new leaderboard cohort",
                f"/gym/projects/{proj['project_id']}/selection-rules",
                "View rules",
                project_id=proj["project_id"],
            )
    elif topic == "run.admitted":
        close_items(c, ws, event_id, "project_ready", subject=p)
        close_items(c, ws, event_id, "evaluator_new_cohort", project_id=p)
        if d.get("batch_id"):
            close_items(c, ws, event_id, "validation_ready", subject=d["batch_id"])
    elif topic == "registry.identity_conflict":
        open_item(
            c,
            ws,
            event_id,
            "registry_conflict",
            d["version_id"],
            "bindings",
            "Registry conflict",
            f"{d['registry']} sent {d['version_id']} with a different {', '.join(d['fields'])}; the mirrored release was kept (released versions are final)",
            f"/gym/admin/environments/{d['version_id']}",
            "View environment",
            severity="bad",
        )
    elif topic == "delivery.refused":
        open_item(
            c,
            ws,
            event_id,
            "delivery_refused",
            d["key"],
            "import_export",
            f"Delivery refused by {d['destination']}",
            f"{d['topic']} {d['key']}: {d['error'][:200]}",
            "/gym/admin",
            None,
            severity="bad",
        )
    elif topic == "sme_item.fix_qualified":
        open_item(
            c,
            ws,
            event_id,
            "rescore_ready",
            f"{d['run_id']}:{d['id']}@{d['version']}",
            "review",
            "Fix version qualified",
            f"{d['id']} v{d['version']} qualified after SME review; re-score {d['run_id']} if you want it graded again (explicit)",
            f"/gym/runs/{d['run_id']}/sme",
            "Re-score…",
            project_id=p,
        )
    elif topic == "run.completed":
        run = c.execute(
            "SELECT purpose, name FROM runs.runs WHERE id=%s", (d["run_id"],)
        ).fetchone()
        failed = c.execute(
            """SELECT count(*) n FROM runs.episodes e JOIN scoring.episode_scores s ON s.episode_id=e.id
               WHERE e.run_id=%s AND e.kind='case' AND NOT s.passed""",
            (d["run_id"],),
        ).fetchone()["n"]
        if run and run["purpose"] == "benchmark" and failed:
            open_item(
                c,
                ws,
                event_id,
                "send_for_sme",
                d["run_id"],
                "review",
                f"{run['name']} ({d['run_id']})",
                f"{failed} failed episodes with no SME item",
                f"/gym/runs/{d['run_id']}/sme",
                "Send for SME review",
                project_id=p,
            )
    elif topic == "sme_batch.sent":
        close_items(c, ws, event_id, "send_for_sme", subject=d["run_id"])
        items = c.execute(
            "SELECT count(*) n FROM results.sme_review_items WHERE batch_id=%s", (d["batch_id"],)
        ).fetchone()["n"]
        open_item(
            c,
            ws,
            event_id,
            "sme_waiting",
            d["batch_id"],
            "import_export",
            "Results sent to ADI Forge",
            f"{d['batch_id']} ({items} items) · waiting for SME decisions.",
            f"/gym/runs/{d['run_id']}/sme",
            None,
            project_id=p,
        )
    elif topic == "sme_batch.decided":
        close_items(c, ws, event_id, "sme_waiting", subject=d["batch_id"])
    elif topic == "sme_batch.corrections_imported":
        open_item(
            c,
            ws,
            event_id,
            "validation_ready",
            d["batch_id"],
            "review",
            "Corrected tasks arrived",
            f"{d['batch_id']}: corrected revisions arrived in a re-export; start the validation run",
            f"/gym/runs/{d['run_id']}/sme",
            "Start validation run",
            project_id=p,
        )


def list_open(c, ws, actor):
    rows = c.execute(
        """SELECT n.*, p.name AS project_name FROM admin.notifications n
           LEFT JOIN projects.projects p ON p.workspace_id=n.workspace_id AND p.project_id=n.project_id
           WHERE n.workspace_id=%s AND n.closed_at IS NULL
             AND (n.audience='workspace' OR (n.audience='binding_approvers' AND %s) OR (n.audience='user' AND n.user_id=%s::uuid))
           ORDER BY n.created_at""",
        (ws, actor.binding_approver, actor.id if actor.kind == "person" else None),
    ).fetchall()
    groups = []
    for key, label in GROUPS.items():
        items = [r for r in rows if r["todo_group"] == key]
        if items:
            groups.append({"key": key, "label": label, "items": items})
    return {"count": len(rows), "groups": groups}
