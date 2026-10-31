"""Safe diagnostic-run projections. Unfinished grading remains blinded."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from anvil import artifacts, auth, domain
from anvil.db import audit, digest, one
from anvil.workspace import READ_ROLES


def summarize(episodes):
    valid = [
        e
        for e in episodes
        if e["state"] == "finalized" and e["outcome"] in ("pass", "fail") and e["score"] is not None
    ]
    return {
        "reward": None,
        "score": float(sum(e["score"] for e in valid) / len(valid)) if valid else None,
        "scored": len(valid),
        "attempts": len(episodes),
        "passed": sum(e["outcome"] == "pass" for e in valid),
        "task_failed": sum(e["outcome"] == "fail" for e in valid),
        "execution_errors": sum(e["state"] == "failed_operational" for e in episodes),
        "unknown": sum(e["state"] == "execution_unknown" for e in episodes),
        "cancelled": sum(e["state"] == "cancelled" for e in episodes),
        "invalid": sum(
            e["outcome"] == "invalid"
            and e["state"] in ("finalized", "unscorable", "failed_operational", "execution_unknown")
            for e in episodes
        ),
        "unscorable": sum(e["state"] == "unscorable" for e in episodes),
        "pending": sum(
            e["state"]
            not in (
                "finalized",
                "cancelled",
                "failed_operational",
                "execution_unknown",
                "unscorable",
            )
            for e in episodes
        ),
        "elapsed_seconds": None,
    }


def result_public(row):
    finalized = row["state"] == "finalized"
    return {
        "id": row["id"],
        "state": row["state"],
        "outcome": row["outcome"] if finalized else "not_finalized",
        "score": row["score"] if finalized and row["outcome"] in ("pass", "fail") else None,
        "candidate": row["candidate_key"] if finalized else "Blinded until finalized",
        "task_revision_id": row["task_revision_id"],
        "output_available": bool(finalized and row["output_artifact_id"]),
    }


def snapshots(c, row):
    protocol = domain.get_revision(c, row["protocol_revision_id"], "protocol")
    p = protocol["content"]
    suite = domain.get_revision(c, p["suite_revision_id"], "suite")
    tasks, rubrics = [], {}
    for tid in suite["content"]["task_revision_ids"]:
        task = domain.get_revision(c, tid, "task")
        t = task["content"]
        tasks.append(
            {
                "revision_id": task["id"],
                "content_hash": task["content_hash"],
                **{
                    k: t[k]
                    for k in ("title", "mode", "family_id", "capabilities", "rubric_revision_id")
                    if k in t
                },
            }
        )
        rid = t["rubric_revision_id"]
        if rid not in rubrics:
            rubric = domain.get_revision(c, rid, "rubric")
            content = rubric["content"]
            rubrics[rid] = {
                "revision_id": rubric["id"],
                "content_hash": rubric["content_hash"],
                "threshold": content["threshold"],
                "criteria": [
                    {k: criterion[k] for k in ("id", "label", "weight_bps")}
                    for criterion in content["criteria"]
                ],
            }
    return protocol, suite, tasks, list(rubrics.values())


def planned_attempts(row, suite, protocol):
    snapshot = row.get("dataset_snapshot")
    count = snapshot.get("task_count") if snapshot else len(suite["task_revision_ids"])
    return (
        count * len(protocol["candidates"]) * protocol.get("repetitions", 1)
        if isinstance(count, int)
        else None
    )


def project_run(c, row, detail=False):
    episodes = c.execute(
        "SELECT id,state,outcome,score,candidate_key,task_revision_id,output_artifact_id,graph_version FROM anvil.episodes WHERE run_id=%s ORDER BY id",
        (row["id"],),
    ).fetchall()
    protocol = domain.get_revision(c, row["protocol_revision_id"], "protocol")
    p = protocol["content"]
    suite = domain.get_revision(c, p["suite_revision_id"], "suite")
    m = summarize(episodes)
    m["planned"] = planned_attempts(row, suite["content"], p)
    budget = one(
        c, "SELECT reserved_micro_usd FROM anvil.run_budgets WHERE run_id=%s", (row["id"],)
    )
    m.update(
        known_cost_micro_usd=row["actual_cost_micro_usd"]
        if row["actual_cost_micro_usd"] is not None
        else 0
        if row["origin"] == "illustrative"
        else None,
        cost_complete=row["origin"] == "illustrative"
        or (row["cost_status"] == "reconciled" and row["actual_cost_micro_usd"] is not None),
        reserved_micro_usd=budget["reserved_micro_usd"] if budget else 0,
    )
    output = {
        "id": row["id"],
        "kind": "diagnostic",
        "title": p["title"],
        "task_id": None,
        "task_version": str(len(suite["content"]["task_revision_ids"])) + " bound task revisions",
        "package_id": row["protocol_revision_id"],
        "package_sha256": protocol["content_hash"],
        "candidate": "Protocol candidates",
        "model": None,
        "origin": row["origin"],
        "state": row["state"],
        "created_at": row["created_at"],
        "started_at": None,
        "finished_at": None,
        "error_code": None,
        "metrics": m,
        "metric_scope": "whole_run",
        "comparison_signature": digest(
            {
                "protocol": protocol["content_hash"],
                "suite": suite["content_hash"],
                "origin": row["origin"],
                "dataset_version_id": str(row["dataset_version_id"])
                if row.get("dataset_version_id")
                else None,
                "finalized_cohort": sorted(
                    (str(e["task_revision_id"]), e["candidate_key"], e["graph_version"])
                    for e in episodes
                    if e["state"] == "finalized"
                    and e["outcome"] in ("pass", "fail")
                    and e["score"] is not None
                ),
            }
        ),
    }
    if detail:
        _, _, tasks, rubrics = snapshots(c, row)
        output.update(
            actor_snapshot={
                "objective": "Exact task metadata; private references and unfinished grading remain restricted.",
                "tasks": tasks,
            },
            source_revision_id=row["protocol_revision_id"],
            source_sha256=protocol["content_hash"],
            evaluation_snapshot={
                "protocol_revision_id": protocol["id"],
                "protocol_hash": protocol["content_hash"],
                "suite_revision_id": suite["id"],
                "suite_hash": suite["content_hash"],
                "dataset": {
                    k: v
                    for k, v in (row.get("dataset_snapshot") or {}).items()
                    if k
                    in (
                        "version_id",
                        "version_number",
                        "task_count",
                        "task_schema_version",
                        "normalized_sha256",
                        "source_sha256",
                    )
                },
                "protocol": {
                    k: p[k]
                    for k in ("mode", "repetitions", "comparison_policy", "pass_policy")
                    if k in p
                },
                "rubrics": rubrics,
                "restricted": "Reference artifacts, anchors, calibration and grader identities excluded",
            },
            trajectory_limitations="Finalized output evidence only. No private checkpoints, hidden reasoning or invented intermediate steps.",
            diagnostics=None,
            evidence=[],
            calls=[],
        )
    return output


def routes(context, wrap):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace")

    @router.get("/diagnostic-tasks")
    def tasks(
        project: UUID,
        request: Request,
        limit: int = Query(50, ge=1, le=100),
        after: UUID | None = None,
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            rows = c.execute(
                """SELECT r.id,r.id::text task_id,v.revision::text task_version,v.content->>'title' title,
                v.content_hash source_sha256,
                (SELECT count(*) FROM anvil.revisions x WHERE x.resource_id=r.id) versions,
                (SELECT count(*) FROM anvil.runs run JOIN anvil.revisions p ON p.id=run.protocol_revision_id
                 JOIN anvil.revisions s ON s.id=(p.content->>'suite_revision_id')::uuid
                 WHERE EXISTS(SELECT 1 FROM anvil.revisions t WHERE t.resource_id=r.id
                 AND (s.content->'task_revision_ids') @> to_jsonb(ARRAY[t.id::text]))) run_count
                FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id
                WHERE r.kind='task' AND (%s::uuid IS NULL OR r.id>%s) ORDER BY r.id LIMIT %s""",
                (after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": rows[:limit],
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                    "scope": "diagnostic",
                },
                request,
            )

    @router.get("/diagnostic-runs")
    def runs(
        project: UUID,
        request: Request,
        task_id: UUID | None = None,
        after: UUID | None = None,
        limit: int = Query(50, ge=1, le=100),
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            cursor = (
                one(c, "SELECT created_at FROM anvil.runs WHERE id=%s", (after,)) if after else None
            )
            if after and not cursor:
                raise HTTPException(404, "Run cursor not found in this project")
            rows = c.execute(
                """SELECT r.* FROM anvil.runs r JOIN anvil.revisions p ON p.id=r.protocol_revision_id
                JOIN anvil.revisions s ON s.id=(p.content->>'suite_revision_id')::uuid
                WHERE (%s::uuid IS NULL OR EXISTS(SELECT 1 FROM anvil.revisions t
                    WHERE t.resource_id=%s AND (s.content->'task_revision_ids') @> to_jsonb(ARRAY[t.id::text])))
                AND (%s::timestamptz IS NULL OR (r.created_at,r.id)<(%s,%s))
                ORDER BY r.created_at DESC,r.id DESC LIMIT %s""",
                (
                    task_id,
                    task_id,
                    cursor["created_at"] if cursor else None,
                    cursor["created_at"] if cursor else None,
                    after,
                    limit + 1,
                ),
            ).fetchall()
            return wrap(
                {
                    "items": [project_run(c, r) for r in rows[:limit]],
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                    "scope": "diagnostic",
                },
                request,
            )

    @router.get("/diagnostic-runs/{rid}")
    def detail(project: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            row = one(c, "SELECT * FROM anvil.runs WHERE id=%s", (rid,))
            if not row:
                raise HTTPException(404, "Run not found in this project")
            return wrap(project_run(c, row, True), request)

    @router.get("/diagnostic-runs/{rid}/results")
    def results(
        project: UUID,
        rid: UUID,
        request: Request,
        after: UUID | None = None,
        limit: int = Query(50, ge=1, le=100),
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            if not one(c, "SELECT id FROM anvil.runs WHERE id=%s", (rid,)):
                raise HTTPException(404, "Run not found in this project")
            rows = c.execute(
                "SELECT id,state,outcome,score,candidate_key,task_revision_id,output_artifact_id FROM anvil.episodes WHERE run_id=%s AND (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
                (rid, after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": [result_public(e) for e in rows[:limit]],
                    "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
                },
                request,
            )

    @router.get("/diagnostic-runs/{rid}/results/{eid}/output")
    def output(project: UUID, rid: UUID, eid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            episode = one(c, "SELECT * FROM anvil.episodes WHERE run_id=%s AND id=%s", (rid, eid))
            if not episode:
                raise HTTPException(404, "Run result not found in this project")
            if episode["state"] != "finalized":
                raise HTTPException(409, "Output remains blinded until review is finalized")
            artifact = one(
                c,
                "SELECT classification,byte_size,sha256 FROM anvil.artifacts WHERE id=%s",
                (episode["output_artifact_id"],),
            )
            if not artifact or artifact["classification"] != "internal":
                raise HTTPException(404, "Permitted output unavailable")
            if artifact["byte_size"] > 262144:
                raise HTTPException(409, "Output exceeds inline evidence limit")
            value = artifacts.read(c, episode["output_artifact_id"]).decode(
                "utf-8", errors="replace"
            )
            audit(c, project, user, "workspace.diagnostic_output_read", eid, {"run_id": str(rid)})
            return wrap({"content": value, "sha256": artifact["sha256"]}, request)

    return router
