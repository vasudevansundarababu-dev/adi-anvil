"""Explicit synchronous fictional execution, disjoint from official comparisons."""

import os
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from anvil import auth
from anvil import benchmark_rehearsal as rehearsal
from anvil import benchmark_report_policy as report_policy


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/benchmarks")

    def authorize(roles):
        rehearsal.enabled()
        auth.require(roles, "admin", "rl-engineer")

    def authorize_policy(roles):
        if os.environ.get("ANVIL_BENCHMARK_ENABLED") != "true":
            raise HTTPException(503, "Benchmark workbench is disabled")
        auth.require(roles, "admin", "rl-engineer")

    @router.get("/report-review-policy")
    def policy(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            authorize_policy(roles)
            return wrap(report_policy.current(c, project), request)

    @router.post("/report-review-policy")
    def configure(project: UUID, body: report_policy.Configure, request: Request):
        with context(request, project) as (c, user, roles):
            authorize_policy(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: report_policy.configure(c, project, user, body),
                ),
                request,
            )

    def decide(project, identifier, body, request, admin):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            row = rehearsal.get(c, identifier, lock=True)
            if row["state"] != "completed":
                raise HTTPException(409, "Completed rehearsal required")
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: report_policy.decide(
                        c,
                        project,
                        user,
                        "rehearsal",
                        identifier,
                        row["result"]["result_sha256"],
                        body,
                        admin=admin,
                    ),
                ),
                request,
            )

    @router.post("/rehearsals/{identifier}/report-approval")
    def approve(project: UUID, identifier: UUID, body: report_policy.Approve, request: Request):
        return decide(project, identifier, body, request, True)

    @router.post("/rehearsals/{identifier}/report-review")
    def review(project: UUID, identifier: UUID, body: report_policy.Review, request: Request):
        return decide(project, identifier, body, request, False)

    @router.post("/rehearsals", status_code=201)
    def create(project: UUID, body: rehearsal.Create, request: Request):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: rehearsal.create(c, project, user, body),
                ),
                request,
            )

    @router.get("/rehearsals")
    def listing(project: UUID, request: Request, limit: int = 25, after: UUID | None = None):
        if not 1 <= limit <= 100:
            raise HTTPException(422, "Page size must be between 1 and 100")
        with context(request, project) as (c, user, roles):
            authorize(roles)
            rows = c.execute(
                "SELECT id FROM anvil.benchmark_rehearsals WHERE (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
                (after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": [rehearsal.get(c, row["id"]) for row in rows[:limit]],
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                },
                request,
            )

    @router.get("/rehearsals/{identifier}")
    def detail(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            return wrap(rehearsal.get(c, identifier), request)

    @router.post("/rehearsals/{identifier}/execute")
    def execute(project: UUID, identifier: UUID, body: rehearsal.Execute, request: Request):
        with context(request, project) as (c, user, roles):
            authorize(roles)
            # Row lock and immutable terminal result make retries safe even with a new key.
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: rehearsal.execute(c, project, user, identifier, body),
                ),
                request,
            )

    return router
