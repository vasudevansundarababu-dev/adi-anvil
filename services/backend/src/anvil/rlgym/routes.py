"""RL Gym v2 HTTP API (ARCHITECTURE 9): `/api/v1/workspaces/{ws}/…` for the UI and integrations, plus the registry
webhook and qualification routes. People use their OIDC session (CSRF on writes); Studio and ADI Forge use client
keys; every POST/PUT carries an Idempotency-Key."""

import json

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from anvil import auth
from anvil.rlgym import integrations
from anvil.rlgym.admin import todo, users
from anvil.rlgym.catalog import evaluators, inbox, registry, selection, templates, verifier
from anvil.rlgym.common import (
    GymError,
    idempotent,
    require,
    scope,
    service_client,
    verify_signature,
)
from anvil.rlgym.projects import service as projects

W = "/api/v1/workspaces/{ws}"
STUDIO = ("studio",)
FORGE = ("adi-forge",)


def ok(data, request: Request, status=200):
    return JSONResponse(
        {
            "data": json.loads(json.dumps(data, default=str)),
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
        status_code=status,
    )


def routes():
    r = APIRouter()

    # --- identity and home -------------------------------------------------------------------------------------
    @r.get("/api/v1/rlgym/me")
    def me(request: Request):
        try:
            user = auth.identity(request)
        except Exception:
            raise GymError("UNAUTHENTICATED", "Sign in required") from None
        return ok(
            {"id": user["id"], "name": user["name"], "workspaces": users.my_workspaces(user["id"])},
            request,
        )

    @r.get(W + "/home")
    def home(ws: str, request: Request):
        with scope(request, ws) as ctx:
            board = []
            for p in ctx.c.execute(
                """SELECT p.project_id, p.name, p.state,
                          (SELECT r.id FROM runs.runs r WHERE r.workspace_id=p.workspace_id AND r.project_id=p.project_id
                           AND r.state='completed' AND r.purpose='benchmark' ORDER BY r.finished_at DESC NULLS LAST LIMIT 1) latest_run
                   FROM projects.projects p WHERE p.workspace_id=%s ORDER BY p.name""",
                (ctx.ws,),
            ).fetchall():
                board.append({**p, "has_results": p["latest_run"] is not None})
            return ok(
                {
                    "workspace": ctx.workspace,
                    "me": ctx.actor.__dict__,
                    "todo_count": todo.list_open(ctx.c, ctx.ws, ctx.actor)["count"],
                    "projects": board,
                },
                request,
            )

    @r.get(W + "/projects/{pid}/leaderboard")
    def leaderboard(ws: str, pid: str, request: Request, cohort: str | None = None):
        from anvil.rlgym.results import leaderboard as board

        with scope(request, ws) as ctx:
            return ok(board.leaderboard(ctx.c, ctx.ws, pid, cohort), request)

    @r.get(W + "/todo")
    def todo_list(ws: str, request: Request):
        with scope(request, ws) as ctx:
            return ok(todo.list_open(ctx.c, ctx.ws, ctx.actor), request)

    # --- projects (A-04 and views) -----------------------------------------------------------------------------
    @r.post(W + "/projects/{pid}/exports", status_code=201)
    def receive_export(
        ws: str, pid: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws, services=FORGE, people=False) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: projects.receive_export(ctx.c, ctx.ws, ctx.actor, pid, body),
                ),
                request,
                201,
            )

    @r.get(W + "/projects")
    def project_list(ws: str, request: Request, q: str | None = None, state: str | None = None):
        with scope(request, ws) as ctx:
            rows = projects.list_projects(ctx.c, ctx.ws, q, state)
            return ok({"items": rows, "total": len(rows)}, request)

    @r.get(W + "/projects/{pid}")
    def project_get(ws: str, pid: str, request: Request):
        with scope(request, ws) as ctx:
            return ok(
                projects.project_summary(
                    ctx.c, ctx.ws, projects.get_project_row(ctx.c, ctx.ws, pid)
                ),
                request,
            )

    @r.get(W + "/projects/{pid}/tasks")
    def project_tasks(
        ws: str,
        pid: str,
        request: Request,
        q: str | None = None,
        state: str | None = None,
        task_id: str | None = None,
        revision: int | None = None,
    ):
        with scope(request, ws, services=STUDIO) as ctx:
            if task_id:
                if ctx.actor.kind == "service":
                    rows = [
                        t
                        for t in projects.tasks(ctx.c, ctx.ws, pid)
                        if t["task_id"] == task_id and (not revision or t["revision"] == revision)
                    ]
                    return ok({"items": rows}, request)
                return ok(
                    projects.task_detail(ctx.c, ctx.ws, ctx.actor, pid, task_id, revision), request
                )
            return ok({"items": projects.tasks(ctx.c, ctx.ws, pid, q, state)}, request)

    @r.get(W + "/projects/{pid}/tasks/{task_id}")
    def project_task(
        ws: str, pid: str, task_id: str, request: Request, revision: int | None = None
    ):
        with scope(request, ws) as ctx:
            return ok(
                projects.task_detail(ctx.c, ctx.ws, ctx.actor, pid, task_id, revision), request
            )

    @r.get(W + "/projects/{pid}/exports")
    def project_exports(ws: str, pid: str, request: Request):
        with scope(request, ws) as ctx:
            return ok({"items": projects.exports(ctx.c, ctx.ws, pid)}, request)

    @r.get(W + "/projects/{pid}/selection-rules")
    def selection_rules(ws: str, pid: str, request: Request):
        with scope(request, ws, services=STUDIO) as ctx:
            return ok(projects.selection_view(ctx.c, ctx.ws, pid, ctx.actor), request)

    @r.get(W + "/projects/{pid}/selection-rules/{alias}")
    def selection_rule(ws: str, pid: str, alias: str, request: Request):
        with scope(request, ws, services=STUDIO) as ctx:
            view = projects.selection_view(ctx.c, ctx.ws, pid, ctx.actor)
            match = [a for a in view["aliases"] if a["alias"] == alias]
            require(match, "NOT_FOUND", "Alias not found")
            return ok(match[0], request)

    @r.put(W + "/projects/{pid}/evaluator-rules/{criterion}")
    def evaluator_rule(
        ws: str, pid: str, criterion: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: projects.set_evaluator_rule(
                        ctx.c, ctx.ws, ctx.actor, pid, criterion, body
                    ),
                ),
                request,
            )

    @r.post(W + "/rule-overrides", status_code=201)
    def override_request(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: projects.request_override(ctx.c, ctx.ws, ctx.actor, body),
                ),
                request,
                201,
            )

    @r.post(W + "/rule-overrides/{oid}/decision")
    def override_decision(
        ws: str, oid: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: projects.decide_override(ctx.c, ctx.ws, ctx.actor, oid, body),
                ),
                request,
            )

    @r.post(W + "/rule-overrides/{oid}/remove")
    def override_remove(
        ws: str, oid: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: projects.remove_override(ctx.c, ctx.ws, ctx.actor, oid),
                ),
                request,
            )

    # --- catalog: environments (read-only mirror) ----------------------------------------------------------------
    @r.get(W + "/catalog/contracts")
    def contracts(ws: str, request: Request):
        with scope(request, ws, services=STUDIO) as ctx:
            return ok(
                {
                    "items": ctx.c.execute(
                        """SELECT contract_id, count(*) versions, count(*) FILTER (WHERE state='qualified') qualified
                   FROM catalog.environment_versions GROUP BY contract_id ORDER BY contract_id"""
                    ).fetchall()
                },
                request,
            )

    @r.get(W + "/catalog/environments")
    def environments(ws: str, request: Request, q: str | None = None, state: str | None = None):
        with scope(request, ws, services=STUDIO) as ctx:
            sql, params = "SELECT * FROM catalog.environment_versions WHERE true", []
            if q:
                sql += " AND (id ILIKE %s OR contract_id ILIKE %s OR seed_family ILIKE %s)"
                params += [f"%{q}%"] * 3
            if state:
                sql += " AND state=%s"
                params.append(state)
            rows = ctx.c.execute(sql + " ORDER BY contract_id, version DESC", params).fetchall()
            for row in rows:
                _environment_extras(ctx, row)
            return ok({"items": rows}, request)

    def _environment_extras(ctx, row):
        receipts = registry.latest_receipts(ctx.c, row["id"])
        row["qualification"] = receipts[0] if receipts else None
        row["receipts"] = receipts
        row["selectable"] = bool(
            row["state"] == "qualified" and (not receipts or receipts[0]["result"] == "qualified")
        )
        row["selected_by"] = ctx.c.execute(
            """SELECT p.project_id, p.name, s.kind, s.change_cause FROM projects.selection_rules s JOIN projects.projects p USING (workspace_id, project_id)
               WHERE s.workspace_id=%s AND s.valid_to IS NULL AND s.resolved_version_id=%s""",
            (ctx.ws, row["id"]),
        ).fetchall()
        row["instances"] = {
            "running": 0,
            "cost_30d_usd": None,
            "note": "Instances arrive with work package 2.7",
        }
        row["can_requalify"] = bool(
            receipts
            and receipts[0]["result"] == "failed"
            and receipts[0]["failure_class"] == "infrastructure"
        )

    @r.get(W + "/catalog/environments/{vid}")
    def environment(ws: str, vid: str, request: Request):
        with scope(request, ws, services=STUDIO) as ctx:
            row = ctx.c.execute(
                "SELECT * FROM catalog.environment_versions WHERE id=%s", (vid,)
            ).fetchone()
            require(row, "NOT_FOUND", "Not found or no longer available")
            _environment_extras(ctx, row)
            row["inbox_items"] = inbox.list_items(ctx.c, ctx.ws, environment_version=vid)
            row["more_data_items"] = [
                i
                for i in inbox.list_items(ctx.c, ctx.ws, kind="more_data")
                if (i["evidence"] or {}).get("contract_id") in (None, row["contract_id"])
            ]
            row["used_by"] = {
                "templates": ctx.c.execute(
                    "SELECT template_id, version, name FROM catalog.template_activations WHERE workspace_id=%s AND default_bindings @> %s::jsonb",
                    (ctx.ws, json.dumps([{"contract_id": row["contract_id"]}])),
                ).fetchall(),
                "tasks_bound": sum(
                    ctx.c.execute(
                        "SELECT count(*) n FROM projects.task_imports WHERE workspace_id=%s AND project_id=%s AND state='ready'",
                        (ctx.ws, p["project_id"]),
                    ).fetchone()["n"]
                    for p in row["selected_by"]
                ),
                "runs": 0,
            }
            return ok(row, request)

    @r.post(W + "/catalog/environments/{vid}/requalify")
    def requalify(ws: str, vid: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            ctx.actor.require_person()
            receipts = registry.latest_receipts(ctx.c, vid, 1)
            require(
                receipts and receipts[0]["failure_class"] == "infrastructure",
                "VALIDATION_FAILED",
                "Re-qualify is only for an infrastructure failure; an environment defect needs a new version from Studio",
            )

            def run():
                return registry.qualify(vid, requested_by=ctx.actor.id)

            return ok(idempotent(ctx, request, body, run), request)

    # --- inbox -----------------------------------------------------------------------------------------------------
    @r.post(W + "/inbox-items", status_code=201)
    def inbox_create(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            ctx.actor.require_person()
            if (
                body.get("kind") == "environment_defect"
                and body.get("environment_version")
                and not body.get("evidence")
            ):
                receipts = registry.latest_receipts(ctx.c, body["environment_version"], 1)
                failed = [
                    ch
                    for ch in (receipts[0]["checks"] if receipts else [])
                    if ch.get("result") == "fail"
                ]
                body = {
                    **body,
                    "evidence": {
                        "receipt_id": receipts[0]["receipt_id"] if receipts else None,
                        "failed_checks": failed,
                        "likely_cause": failed[0].get("likely_cause") if failed else None,
                        "impact": {
                            "projects": [body.get("project_id")] if body.get("project_id") else []
                        },
                    },
                }
            return ok(
                idempotent(
                    ctx, request, body, lambda: inbox.create(ctx.c, ctx.ws, ctx.actor, body)
                ),
                request,
                201,
            )

    @r.get(W + "/inbox-items")
    def inbox_list(
        ws: str,
        request: Request,
        kind: str | None = None,
        state: str | None = None,
        template_id: str | None = None,
    ):
        with scope(request, ws) as ctx:
            return ok({"items": inbox.list_items(ctx.c, ctx.ws, kind, state, template_id)}, request)

    # --- evaluators (A-06 and Admin → Evaluators) -------------------------------------------------------------------
    @r.post(W + "/evaluators", status_code=201)
    def evaluator_create(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws, services=STUDIO, people=False) as ctx:

            def run():
                row, created = evaluators.create_from_studio(ctx.c, ctx.ws, ctx.actor, body)
                return {
                    "id": row["id"],
                    "version": row["version"],
                    "state": row["state"],
                    "config_sha256": row["config_sha256"],
                    "created": created,
                }

            return ok(idempotent(ctx, request, body, run), request, 201)

    @r.post(W + "/evaluators/{cid}/test")
    def evaluator_test(
        ws: str, cid: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws, services=STUDIO) as ctx:
            require(
                body.get("version"), "VALIDATION_FAILED", "version is required", field="version"
            )
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: evaluators.run_known_case_tests(
                        ctx.c,
                        ctx.ws,
                        ctx.actor,
                        cid,
                        body["version"],
                        blocks=body.get("blocks"),
                        expected_values_from=body.get("expected_values_from"),
                    ),
                ),
                request,
            )

    @r.post(W + "/evaluators/{cid}/versions", status_code=201)
    def evaluator_fix(ws: str, cid: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: evaluators.create_fix_version(ctx.c, ctx.ws, ctx.actor, cid, body),
                ),
                request,
                201,
            )

    @r.post(W + "/evaluators/{cid}/deprecate")
    def evaluator_deprecate(
        ws: str, cid: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: evaluators.deprecate(
                        ctx.c, ctx.ws, ctx.actor, cid, body.get("version"), body.get("reason")
                    ),
                ),
                request,
            )

    @r.get(W + "/evaluators/{cid}/impact")
    def evaluator_impact(ws: str, cid: str, version: int, request: Request):
        with scope(request, ws, services=STUDIO) as ctx:
            return ok(evaluators.impact(ctx.c, ctx.ws, cid, version), request)

    @r.post(W + "/evaluators/{cid}/revoke")
    def evaluator_revoke(
        ws: str, cid: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: evaluators.revoke(
                        ctx.c, ctx.ws, ctx.actor, cid, body.get("version"), body.get("reason")
                    ),
                ),
                request,
            )

    @r.get(W + "/catalog/evaluators")
    def evaluator_list(ws: str, request: Request, q: str | None = None, state: str | None = None):
        with scope(request, ws, services=STUDIO) as ctx:
            rows = evaluators.list_configurations(ctx.c, ctx.ws, q, state)
            for row in rows:
                row["used_by"] = ctx.c.execute(
                    """SELECT p.project_id, p.name FROM projects.evaluator_selection_rules r JOIN projects.projects p USING (workspace_id, project_id)
                       WHERE r.workspace_id=%s AND r.configuration_id=%s AND r.valid_to IS NULL AND r.resolved_version=%s""",
                    (ctx.ws, row["id"], row["version"]),
                ).fetchall()
            return ok({"items": rows}, request)

    @r.get(W + "/catalog/evaluators/{cid}/versions/{version}")
    def evaluator_get(ws: str, cid: str, version: int, request: Request):
        with scope(request, ws, services=STUDIO) as ctx:
            row = evaluators.get_version(ctx.c, ctx.ws, cid, version)
            fw = ctx.c.execute(
                "SELECT * FROM catalog.framework_versions WHERE id=%s",
                (row["framework_version_id"],),
            ).fetchone()
            receipts = ctx.c.execute(
                """SELECT * FROM catalog.qualification_receipts WHERE workspace_id=%s AND subject_kind='evaluator_configuration' AND subject_id=%s
                   AND subject_version=%s ORDER BY issued_at DESC""",
                (ctx.ws, cid, str(version)),
            ).fetchall()
            history = ctx.c.execute(
                """SELECT version, state, state_reason, replaced_by_version, created_by, fix_of_version, fix_reason, created_at, config_sha256
                   FROM catalog.evaluator_configurations WHERE workspace_id=%s AND id=%s ORDER BY version""",
                (ctx.ws, cid),
            ).fetchall()
            used = ctx.c.execute(
                """SELECT p.project_id, p.name, r.kind, r.resolved_version FROM projects.evaluator_selection_rules r
                   JOIN projects.projects p USING (workspace_id, project_id) WHERE r.workspace_id=%s AND r.configuration_id=%s AND r.valid_to IS NULL""",
                (ctx.ws, cid),
            ).fetchall()
            known = {
                k: {"case_id": v.get("case_id"), "expect": v.get("expect")}
                for k, v in row["known_cases"].items()
            }
            return ok(
                {
                    **row,
                    "known_cases": known,
                    "framework": fw,
                    "receipts": receipts,
                    "history": history,
                    "used_by": used,
                },
                request,
            )

    @r.get(W + "/catalog/rubrics")
    def rubric_registry(ws: str, request: Request):
        """The rubrics a Rubric verifier block may name (Studio's validate refuses others). Mock judge locally."""
        with scope(request, ws, services=STUDIO):
            return ok({"rubrics": verifier.RUBRICS}, request)

    @r.get(W + "/catalog/frameworks")
    def framework_list(ws: str, request: Request, q: str | None = None, state: str | None = None):
        with scope(request, ws, services=STUDIO) as ctx:
            sql, params = (
                """SELECT f.*, (SELECT count(*) FROM catalog.evaluator_configurations e WHERE e.workspace_id=%s
                               AND e.framework_version_id=f.id AND e.state<>'revoked') AS configurations
                             FROM catalog.framework_versions f WHERE true""",
                [ctx.ws],
            )
            if q:
                sql += " AND (f.id ILIKE %s OR f.runtime_id ILIKE %s)"
                params += [f"%{q}%"] * 2
            if state:
                sql += " AND f.state=%s"
                params.append(state)
            return ok(
                {
                    "items": ctx.c.execute(
                        sql + " ORDER BY f.runtime_id, f.version", params
                    ).fetchall()
                },
                request,
            )

    @r.get(W + "/frameworks/{fid}/impact")
    def framework_impact(ws: str, fid: str, request: Request):
        with scope(request, ws) as ctx:
            return ok(evaluators.framework_impact(ctx.c, ctx.ws, fid), request)

    @r.post(W + "/frameworks/{fid}/deprecate")
    def framework_deprecate(
        ws: str, fid: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: evaluators.framework_state(
                        ctx.c, ctx.ws, ctx.actor, fid, "deprecated", body.get("reason")
                    ),
                ),
                request,
            )

    @r.post(W + "/frameworks/{fid}/revoke")
    def framework_revoke(
        ws: str, fid: str, request: Request, body: dict = Body(default_factory=dict)
    ):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: evaluators.framework_state(
                        ctx.c, ctx.ws, ctx.actor, fid, "revoked", body.get("reason")
                    ),
                ),
                request,
            )

    # --- templates (A-03) ------------------------------------------------------------------------------------------
    @r.post(W + "/templates/validate")
    def template_validate(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws, services=STUDIO, people=False) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: templates.validate(ctx.c, ctx.ws, body)),
                request,
            )

    @r.post(W + "/templates/known-case-tests")
    def template_kct(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws, services=STUDIO, people=False) as ctx:
            return ok(
                idempotent(
                    ctx,
                    request,
                    body,
                    lambda: templates.known_case_tests(ctx.c, ctx.ws, ctx.actor, body),
                ),
                request,
            )

    @r.post(W + "/templates/activations", status_code=201)
    def template_activate(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws, services=STUDIO, people=False) as ctx:

            def run():
                row, created = templates.activate(ctx.c, ctx.ws, ctx.actor, body)
                return {
                    "template_id": row["template_id"],
                    "version": row["version"],
                    "state": row["state"],
                    "checks": row["checks"],
                    "created": created,
                }

            return ok(idempotent(ctx, request, body, run), request, 201)

    @r.get(W + "/templates")
    def template_list(ws: str, request: Request, q: str | None = None, state: str | None = None):
        with scope(request, ws, services=STUDIO) as ctx:
            return ok({"items": templates.list_templates(ctx.c, ctx.ws, q, state)}, request)

    @r.get(W + "/templates/{tid}/versions/{version}")
    def template_get(ws: str, tid: str, version: int, request: Request):
        with scope(request, ws, services=STUDIO) as ctx:
            return ok(templates.get_template(ctx.c, ctx.ws, tid, version), request)

    @r.get(W + "/templates/{tid}/versions/{version}/workflow")
    def template_workflow(ws: str, tid: str, version: int, request: Request):
        with scope(request, ws) as ctx:
            return ok(templates.get_template(ctx.c, ctx.ws, tid, version)["workflow"], request)

    # --- users (2.10 subset) -------------------------------------------------------------------------------------------
    @r.get(W + "/users")
    def user_list(ws: str, request: Request):
        with scope(request, ws) as ctx:
            return ok({"items": users.list_users(ctx)}, request)

    @r.patch(W + "/users/{uid}")
    def user_update(ws: str, uid: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: users.update_user(ctx, uid, body)), request
            )

    @r.post(W + "/users/invitations", status_code=201)
    def user_invite(ws: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: users.invite_user(ctx, body)), request, 201
            )

    @r.post(W + "/users/{uid}/remove")
    def user_remove(ws: str, uid: str, request: Request, body: dict = Body(default_factory=dict)):
        with scope(request, ws) as ctx:
            return ok(
                idempotent(ctx, request, body, lambda: users.remove_access(ctx, uid, body)), request
            )

    @r.get(W + "/users/{uid}/history")
    def user_history(ws: str, uid: str, request: Request):
        with scope(request, ws) as ctx:
            require(ctx.actor.profile == "admin", "FORBIDDEN", "Admin only")
            return ok({"items": users.access_history(ctx, uid)}, request)

    # --- registry (Studio → RL Gym) ------------------------------------------------------------------------------------
    @r.post("/api/v1/registry-events")
    async def registry_events(request: Request):
        raw = await request.body()
        verify_signature(request.headers, raw)
        event = json.loads(raw)
        require(
            event.get("type") and isinstance(event.get("data"), dict) and "seq" in event["data"],
            "VALIDATION_FAILED",
            "CloudEvent with data.seq required",
        )
        return ok(await run_in_threadpool(registry.receive, event), request, 202)

    @r.post("/api/v1/qualifications")
    def qualification_request(request: Request, body: dict = Body(default_factory=dict)):
        require(
            service_client(request) == "studio",
            "FORBIDDEN",
            "Only Studio's registry asks for qualification",
        )
        subject = body.get("subject") or {}
        require(
            subject.get("kind") == "environment_version" and subject.get("id"),
            "VALIDATION_FAILED",
            "subject.id required",
        )
        return ok(registry.qualify(subject["id"]), request, 202)

    @r.post("/api/v1/rlgym/dispatch")
    def dispatch(request: Request):
        """Local operator hook: deliver pending outbox rows now (the background dispatcher does this every 1.5 s)."""
        require(
            service_client(request) in ("studio", "adi-forge"), "FORBIDDEN", "Client key required"
        )
        return ok({"delivered": integrations.dispatch_once()}, request)

    @r.get(W + "/selection/preview")
    def selection_preview(
        ws: str,
        request: Request,
        contract_id: str,
        kind: str,
        seed_family: str | None = None,
        pinned_version_id: str | None = None,
    ):
        with scope(request, ws) as ctx:
            pick, code, reason = selection.resolve_environment(
                ctx.c,
                {
                    "contract_id": contract_id,
                    "kind": kind,
                    "seed_family": seed_family,
                    "pinned_version_id": pinned_version_id,
                },
            )
            return ok(
                {"selects": pick["id"] if pick else None, "code": code, "reason": reason}, request
            )

    return r
