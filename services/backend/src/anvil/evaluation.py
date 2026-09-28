from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Jsonb
from pydantic import Field

from anvil import artifacts, auth, domain
from anvil.db import audit, one, uid
from anvil.schemas import Assessment, Strict

router = APIRouter(prefix="/api/v1/projects/{project}")
GRAPH_VERSION = "fixture-static-review-v1"
EXTERNAL_GRAPH_VERSION = "external-static-review-v1"


class NewRun(Strict):
    protocol_revision_id: UUID
    external_origin: Literal["customer_reported", "partner_reported"] | None = None


class ReviewIssue(Strict):
    code: Literal["ambiguous_reference", "missing_evidence", "rubric_issue"]
    rationale: str = Field(min_length=10, max_length=5000)


class ResolveIssue(Strict):
    decision: Literal["invalid", "resume_review"]
    rationale: str = Field(min_length=10, max_length=5000)


def protocol_for(c, run):
    return domain.get_revision(c, run["protocol_revision_id"], "protocol", ["approved"])["content"]


def get_run(c, rid, lock=False):
    r = one(c, "SELECT * FROM anvil.runs WHERE id=%s" + (" FOR UPDATE" if lock else ""), (rid,))
    if not r:
        raise HTTPException(404, "Run not found")
    return r


def enqueue(c, project, kind, target, key):
    c.execute(
        "INSERT INTO anvil.jobs(id,project_id,kind,target_id,operation_key) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(operation_key) DO NOTHING",
        (uid(), project, kind, target, key),
    )


def score_rubric(rubric, scores, critical):
    criteria = rubric["criteria"]
    if set(scores) != {d["id"] for d in criteria}:
        raise HTTPException(422, "Every rubric dimension must be judged; missing is not zero")
    if any(type(x) is not int or not 0 <= x <= 4 for x in scores.values()):
        raise HTTPException(422, "Dimension scores must be integers 0–4")
    if not set(critical) <= set(rubric["critical_rules"]):
        raise HTTPException(422, "Unknown critical rule")
    score = sum(Decimal(d["weight_bps"]) * scores[d["id"]] for d in criteria) / 400
    return score, "pass" if not critical and score >= Decimal(str(rubric["threshold"])) else "fail"


def routes(context, wrap, idempotent):
    @router.post("/runs", status_code=201)
    def new_run(project: UUID, body: NewRun, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher")

            def create():
                protocol = domain.get_revision(
                    c, body.protocol_revision_id, "protocol", ["approved"]
                )
                external = protocol["content"]["mode"] == "external_result_import_v1"
                if external != (body.external_origin is not None):
                    raise HTTPException(
                        422, "External protocols require an explicit reported origin"
                    )
                rid = uid()
                c.execute(
                    "INSERT INTO anvil.runs(id,project_id,protocol_revision_id,origin,created_by) VALUES(%s,%s,%s,%s,%s)",
                    (
                        rid,
                        project,
                        body.protocol_revision_id,
                        body.external_origin or "illustrative",
                        user,
                    ),
                )
                audit(c, project, user, "run.prepared", rid)
                return get_run(c, rid)

            return wrap(idempotent(c, project, user, request, body, create), request)

    @router.get("/runs")
    def runs(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "advisor", "product-owner", "data-engineer")
            return wrap(
                c.execute("""SELECT r.*,count(e.id) episode_count,
                    count(e.id) FILTER(WHERE e.state IN ('queued','output_captured')) pending_execution,
                    count(e.id) FILTER(WHERE e.state IN ('awaiting_review','disputed','review_blocked')) pending_reviews,
                    count(e.id) FILTER(WHERE e.state='finalized') finalized_reviews
                    FROM anvil.runs r LEFT JOIN anvil.episodes e ON e.run_id=r.id
                    GROUP BY r.id ORDER BY r.created_at DESC LIMIT 100""").fetchall(),
                request,
            )

    @router.get("/runs/{rid}")
    def run_detail(project: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "advisor", "product-owner", "data-engineer")
            run = get_run(c, rid)
            run["episodes"] = c.execute(
                "SELECT id,state,outcome,score,invocation_count FROM anvil.episodes WHERE run_id=%s ORDER BY id",
                (rid,),
            ).fetchall()
            run["episode_count"] = len(run["episodes"])
            run["pending_execution"] = sum(
                e["state"] in ("queued", "output_captured") for e in run["episodes"]
            )
            run["pending_reviews"] = sum(
                e["state"] in ("awaiting_review", "disputed", "review_blocked")
                for e in run["episodes"]
            )
            run["finalized_reviews"] = sum(e["state"] == "finalized" for e in run["episodes"])
            return wrap(run, request)

    @router.post("/runs/{rid}/launch")
    def launch(project: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher")

            def dispatch():
                run = get_run(c, rid, True)
                domain.etag(run, request.headers.get("if-match"))
                if run["state"] != "draft":
                    raise HTTPException(409, "Run already launched or not launchable")
                protocol = protocol_for(c, run)
                if protocol["mode"] != "fixture":
                    raise HTTPException(
                        409, "External runs accept manifests; they never dispatch candidates"
                    )
                suite = domain.get_revision(c, protocol["suite_revision_id"], "suite", ["frozen"])[
                    "content"
                ]
                domain.get_revision(c, protocol["objective_revision_id"], "objective", ["approved"])
                for tid in suite["task_revision_ids"]:
                    task = domain.get_revision(c, tid, "task", ["published"])["content"]
                    domain.current_source(c, task["source_revision_id"])
                    if task["mode"] != "static" or not domain.rights_ok(
                        c, task["source_revision_id"]
                    ):
                        raise HTTPException(409, "Execution mode or rights blocker")
                    for aid in task["actor_artifact_ids"]:
                        artifacts.read(c, aid, actor_only=True)
                    for candidate in protocol["candidates"]:
                        eid = uid()
                        c.execute(
                            "INSERT INTO anvil.episodes(id,project_id,run_id,task_revision_id,candidate_key,thread_id,graph_version) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                            (eid, project, rid, tid, candidate, uid(), GRAPH_VERSION),
                        )
                        enqueue(c, project, "episode", eid, f"episode:{eid}")
                c.execute(
                    "UPDATE anvil.runs SET state='queued',row_version=row_version+1 WHERE id=%s",
                    (rid,),
                )
                audit(c, project, user, "run.launched", rid)
                return get_run(c, rid)

            return wrap(idempotent(c, project, user, request, {}, dispatch), request)

    @router.post("/runs/{rid}/cancel")
    def cancel(project: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher")

            def apply():
                run = get_run(c, rid, True)
                domain.etag(run, request.headers.get("if-match"))
                c.execute(
                    "UPDATE anvil.runs SET cancel_requested=true,state='cancelled',row_version=row_version+1 WHERE id=%s",
                    (rid,),
                )
                c.execute(
                    "UPDATE anvil.episodes SET state='cancelled',row_version=row_version+1 WHERE run_id=%s AND state NOT IN ('finalized','failed_operational','execution_unknown','unscorable')",
                    (rid,),
                )
                c.execute(
                    "UPDATE anvil.jobs SET status='cancelled' WHERE target_id IN (SELECT id FROM anvil.episodes WHERE run_id=%s) AND status IN ('queued','leased')",
                    (rid,),
                )
                audit(c, project, user, "run.cancelled", rid)
                enqueue(c, project, "sales_kit_prepare", rid, "provisional-kit:" + str(rid))
                return get_run(c, rid)

            return wrap(idempotent(c, project, user, request, {}, apply), request)

    @router.get("/episodes/{eid}/evidence")
    def evidence(project: UUID, eid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "advisor")
            e = one(c, "SELECT * FROM anvil.episodes WHERE id=%s", (eid,))
            if not e:
                raise HTTPException(404, "Episode not found")
            if e["state"] != "finalized":
                raise HTTPException(409, "Evidence interpretation requires finalized review")
            task = domain.get_revision(c, e["task_revision_id"], "task")["content"]
            rubric = domain.get_revision(c, task["rubric_revision_id"], "rubric")["content"]
            audit(c, project, user, "episode.evidence_read", eid)
            return wrap(
                {
                    "id": str(eid),
                    "output": artifacts.read(c, e["output_artifact_id"]).decode(),
                    "outcome": e["outcome"],
                    "criteria": [{"id": x["id"], "label": x["label"]} for x in rubric["criteria"]],
                    "capabilities": task["capabilities"],
                    "origin": get_run(c, e["run_id"])["origin"],
                },
                request,
            )

    @router.get("/reviews")
    def inbox(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "reviewer", "adjudicator")
            rows = c.execute("""SELECT e.id,e.state,e.outcome,e.row_version,e.run_id,r.protocol_revision_id
                              FROM anvil.episodes e JOIN anvil.runs r ON r.id=e.run_id
                              WHERE e.state IN ('awaiting_review','disputed','review_blocked') ORDER BY e.id""").fetchall()
            out = []
            for row in rows:
                p = protocol_for(c, row)
                if str(user) in p["reviewer_ids"] or str(user) == p["adjudicator_id"]:
                    row.pop("protocol_revision_id")
                    row["my_review_submitted"] = (
                        one(
                            c,
                            "SELECT 1 FROM anvil.assessments WHERE episode_id=%s AND reviewer_id=%s",
                            (row["id"], user),
                        )
                        is not None
                    )
                    out.append(row)
            return wrap(out, request)

    @router.get("/reviews/{eid}")
    def review_detail(project: UUID, eid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "reviewer", "adjudicator")
            e = one(c, "SELECT * FROM anvil.episodes WHERE id=%s", (eid,))
            if not e:
                raise HTTPException(404, "Episode not found")
            p = protocol_for(c, get_run(c, e["run_id"]))
            if str(user) not in p["reviewer_ids"] + [p["adjudicator_id"]]:
                raise HTTPException(403, "Reviewer not assigned")
            task = domain.get_revision(c, e["task_revision_id"], "task")["content"]
            rubric = domain.get_revision(c, task["rubric_revision_id"], "rubric")["content"]
            out = {
                "id": e["id"],
                "state": e["state"],
                "row_version": e["row_version"],
                "title": task["title"],
                "execution_origin": get_run(c, e["run_id"])["origin"],
                "evidence_limitations": e["external_provenance"]["attempt"]["limitations"]
                if e["external_provenance"]
                else [],
                "trace_coverage": e["external_provenance"]["attempt"]["trace_coverage"]
                if e["external_provenance"]
                else "none",
                "output": artifacts.read(c, e["output_artifact_id"]).decode()
                if e["output_artifact_id"]
                else None,
                "references": [
                    artifacts.read(c, aid).decode() for aid in task["reference_artifact_ids"]
                ],
                "rubric": rubric,
                "adjudication_allowed": str(user) == p["adjudicator_id"]
                and e["state"] == "disputed",
                "issue_resolution_allowed": str(user) == p["adjudicator_id"]
                and e["state"] == "review_blocked",
                "issues": c.execute(
                    "SELECT id,code,rationale,status FROM anvil.review_issues WHERE episode_id=%s ORDER BY created_at",
                    (eid,),
                ).fetchall(),
            }
            if out["adjudication_allowed"]:
                out["submitted_assessments"] = c.execute(
                    "SELECT scores,critical,evidence,rationale FROM anvil.assessments WHERE episode_id=%s",
                    (eid,),
                ).fetchall()
            audit(c, project, user, "review.evidence_read", eid)
            return wrap(out, request)

    @router.post("/episodes/{eid}/review-issues")
    def issue(project: UUID, eid: UUID, body: ReviewIssue, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "reviewer")

            def act():
                e = one(c, "SELECT * FROM anvil.episodes WHERE id=%s FOR UPDATE", (eid,))
                if not e:
                    raise HTTPException(404, "Episode not found")
                domain.etag(e, request.headers.get("if-match"))
                run = get_run(c, e["run_id"])
                p = protocol_for(c, run)
                if str(user) not in p["reviewer_ids"]:
                    raise HTTPException(403, "Assigned independent reviewer required")
                if (
                    e["state"] not in ("awaiting_review", "disputed")
                    or e["final_assessment_id"]
                    or run["cancel_requested"]
                ):
                    raise HTTPException(409, "Episode is not open to review issues")
                iid = uid()
                c.execute(
                    "INSERT INTO anvil.review_issues(id,project_id,episode_id,reported_by,code,rationale) VALUES(%s,%s,%s,%s,%s,%s)",
                    (iid, project, eid, user, body.code, body.rationale),
                )
                c.execute(
                    "UPDATE anvil.episodes SET state='review_blocked',row_version=row_version+1 WHERE id=%s",
                    (eid,),
                )
                audit(c, project, user, "review.issue_raised", eid, {"code": body.code})
                return {"id": iid, "episode_id": str(eid), "state": "review_blocked"}

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/episodes/{eid}/resolve-issue")
    def resolve_issue(project: UUID, eid: UUID, body: ResolveIssue, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "adjudicator")

            def act():
                e = one(c, "SELECT * FROM anvil.episodes WHERE id=%s FOR UPDATE", (eid,))
                if not e:
                    raise HTTPException(404, "Episode not found")
                domain.etag(e, request.headers.get("if-match"))
                run = get_run(c, e["run_id"])
                p = protocol_for(c, run)
                if str(user) != p["adjudicator_id"]:
                    raise HTTPException(403, "Independent assigned adjudicator required")
                issue = one(
                    c,
                    "SELECT * FROM anvil.review_issues WHERE episode_id=%s AND status='open' FOR UPDATE",
                    (eid,),
                )
                if not issue or e["state"] != "review_blocked" or run["cancel_requested"]:
                    raise HTTPException(409, "No open review issue")
                if issue["reported_by"] == user:
                    raise HTTPException(409, "Issue resolution must be independent")
                resolution = uid()
                c.execute(
                    "INSERT INTO anvil.review_resolutions(id,project_id,issue_id,episode_id,resolved_by,decision,rationale) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (resolution, project, issue["id"], eid, user, body.decision, body.rationale),
                )
                c.execute(
                    "UPDATE anvil.review_issues SET status='resolved' WHERE id=%s", (issue["id"],)
                )
                if body.decision == "invalid":
                    c.execute(
                        "UPDATE anvil.episodes SET invalidity_resolution_id=%s,state='invalid_pending_finalization',outcome='invalid',score=NULL,row_version=row_version+1 WHERE id=%s",
                        (resolution, eid),
                    )
                    enqueue(c, project, "resume", eid, f"resume-invalid:{eid}:{resolution}")
                else:
                    count = one(
                        c, "SELECT count(*) n FROM anvil.assessments WHERE episode_id=%s", (eid,)
                    )["n"]
                    c.execute(
                        "UPDATE anvil.episodes SET state=%s,row_version=row_version+1 WHERE id=%s",
                        ("disputed" if count >= 2 else "awaiting_review", eid),
                    )
                audit(c, project, user, "review.issue_resolved", eid, {"decision": body.decision})
                return {
                    "id": resolution,
                    "episode_id": str(eid),
                    "decision": body.decision,
                    "score": None,
                }

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/episodes/{eid}/assessments")
    @router.post("/episodes/{eid}/adjudicate")
    def assess(project: UUID, eid: UUID, body: Assessment, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "reviewer", "adjudicator")

            def apply():
                e = one(c, "SELECT * FROM anvil.episodes WHERE id=%s FOR UPDATE", (eid,))
                if not e:
                    raise HTTPException(404, "Episode not found")
                domain.etag(e, request.headers.get("if-match"))
                run = get_run(c, e["run_id"])
                if e["state"] not in ("awaiting_review", "disputed") or run["cancel_requested"]:
                    raise HTTPException(409, "Episode is not reviewable")
                p = protocol_for(c, run)
                adjudicate = request.url.path.endswith("/adjudicate")
                if adjudicate:
                    if str(user) != p["adjudicator_id"] or e["state"] != "disputed":
                        raise HTTPException(403, "Independent assigned adjudicator required")
                elif str(user) not in p["reviewer_ids"]:
                    raise HTTPException(403, "Reviewer not assigned")
                task = domain.get_revision(c, e["task_revision_id"], "task")["content"]
                rubric = domain.get_revision(c, task["rubric_revision_id"], "rubric")["content"]
                score, outcome = score_rubric(rubric, body.scores, body.critical)
                output = artifacts.read(c, e["output_artifact_id"]).decode()
                if set(body.evidence) != set(body.scores) or any(
                    len(q.strip()) < 3 or q not in output for q in body.evidence.values()
                ):
                    raise HTTPException(
                        422, "Each criterion requires a verbatim output evidence locator"
                    )
                aid = uid()
                c.execute(
                    "INSERT INTO anvil.assessments(id,project_id,episode_id,reviewer_id,scores,critical,evidence,rationale,score,outcome,round) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        aid,
                        project,
                        eid,
                        user,
                        Jsonb(body.scores),
                        Jsonb(body.critical),
                        Jsonb(body.evidence),
                        body.rationale,
                        score,
                        outcome,
                        "adjudication" if adjudicate else "independent",
                    ),
                )
                judgments = c.execute(
                    "SELECT * FROM anvil.assessments WHERE episode_id=%s ORDER BY created_at",
                    (eid,),
                ).fetchall()
                final = adjudicate
                if len(judgments) == 2 and not adjudicate:
                    a, b = judgments
                    dispute = (
                        a["outcome"] != b["outcome"]
                        or set(a["critical"]) != set(b["critical"])
                        or any(abs(a["scores"][k] - b["scores"][k]) >= 2 for k in body.scores)
                    )
                    if dispute:
                        c.execute(
                            "UPDATE anvil.episodes SET state='disputed',row_version=row_version+1 WHERE id=%s",
                            (eid,),
                        )
                    else:
                        # Retain primary judgment rather than averaging; secondary corroborates.
                        aid, score, outcome = a["id"], a["score"], a["outcome"]
                        body.critical = a["critical"]
                        final = True
                if final:
                    c.execute(
                        "UPDATE anvil.episodes SET final_assessment_id=%s,score=%s,outcome=%s,critical=%s,row_version=row_version+1 WHERE id=%s",
                        (aid, score, outcome, Jsonb(body.critical), eid),
                    )
                    enqueue(c, project, "resume", eid, f"resume:{eid}:{aid}")
                else:
                    c.execute(
                        "UPDATE anvil.episodes SET row_version=row_version+1 WHERE id=%s", (eid,)
                    )
                audit(
                    c,
                    project,
                    user,
                    "assessment.submitted",
                    eid,
                    {"round": "adjudication" if adjudicate else "independent"},
                )
                return {"id": eid, "final": final, "score": score, "outcome": outcome}

            return wrap(idempotent(c, project, user, request, body, apply), request)

    return router
