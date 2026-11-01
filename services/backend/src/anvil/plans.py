"""Five-step evaluation wizard over the existing versioned records (D-SIMPLE, AGENTS.md).

Objective -> research (background, sources, benchmark research) -> tasks and data -> rubric ->
benchmark and run. Submitting creates the rubric and task drafts and submits the objective. One
Admin decision then approves every component in dependency order inside one
transaction; the existing qualification checks, rights rules and exact version binding still
apply to each record. Launching stays an explicit, separate action on the prepared run.
"""

import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from anvil import auth, domain, fixtures
from anvil.db import audit, one, uid
from anvil.schemas import Criterion, Decision, FixtureImport, Strict

router = APIRouter(prefix="/api/v1/projects/{project}/evaluations")
BUILT_IN = ["MKT-001", "FIN-001", "STR-001"]
EDITABLE = ("draft", "changes_requested")


class Source(Strict):
    label: str = Field(min_length=1, max_length=200)
    url: str = Field(default="", max_length=2000)


class NewPlan(Strict):
    title: str = Field(min_length=3, max_length=200)
    hypothesis: str = Field(min_length=10, max_length=5000)
    success_criteria: str = Field(min_length=20, max_length=10000)
    business_context: str = Field(default="", max_length=5000)


class RubricDraft(Strict):
    criteria: list[Criterion] = Field(min_length=1, max_length=30)
    threshold: float = Field(ge=0, le=100)
    critical_rules: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def valid(self):
        if sum(c.weight_bps for c in self.criteria) != 10000:
            raise ValueError("Criterion weights must total 10000 (100%)")
        if len({c.id for c in self.criteria}) != len(self.criteria):
            raise ValueError("Criterion IDs must be unique")
        for c in self.criteria:
            if set(c.anchors) != {"0", "1", "2", "3", "4"} or not all(
                v.strip() for v in c.anchors.values()
            ):
                raise ValueError("Every criterion needs anchors for scores 0-4")
        return self


class Benchmark(Strict):
    recommendation_revision_id: UUID | None = None
    benchmark_revision_ids: list[UUID] = Field(default_factory=list, max_length=10)
    override_reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def paired(self):
        if bool(self.benchmark_revision_ids) != bool(self.recommendation_revision_id):
            raise ValueError("Pick a recommendation and its benchmark versions together")
        return self


class PlanUpdate(Strict):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    hypothesis: str | None = Field(default=None, min_length=10, max_length=5000)
    success_criteria: str | None = Field(default=None, min_length=20, max_length=10000)
    business_context: str | None = Field(default=None, max_length=5000)
    background_notes: str | None = Field(default=None, max_length=20000)
    sources: list[Source] | None = Field(default=None, max_length=50)
    case_ids: list[Literal["MKT-001", "FIN-001", "STR-001"]] | None = Field(
        default=None, max_length=3
    )
    rubric: RubricDraft | None = None
    benchmark: Benchmark | None = None
    grader_ids: list[UUID] | None = Field(default=None, max_length=2)
    candidates: list[Literal["fixture-correct", "fixture-constraint-blind"]] | None = Field(
        default=None, min_length=1, max_length=2
    )


class PlanDecision(Strict):
    decision: Literal["approve", "changes_requested"]
    rationale: str = Field(min_length=10, max_length=5000)


def objective_content(user, title, hypothesis, success, context):
    return {
        "title": title,
        "origin": "adi_initiated",
        "entry_type": "capability",
        "hypothesis": hypothesis,
        "business_context": context or "Internal ADI evaluation",
        "measurement_plan": success,
        "researcher_id": str(user),
    }


def get_plan(c, pid, lock=False):
    plan = one(
        c,
        "SELECT * FROM anvil.evaluation_plans WHERE id=%s" + (" FOR UPDATE" if lock else ""),
        (pid,),
    )
    if not plan:
        raise HTTPException(404, "Evaluation not found")
    return plan


def members(c, project, role):
    return [
        str(r["user_id"])
        for r in c.execute(
            """SELECT m.user_id FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id
               WHERE m.project_id=%s AND m.role=ANY(%s) AND m.active AND u.active ORDER BY (m.role='admin'),u.name""",
            (
                project,
                ["admin"] if role in ("admin", "product-owner") else ["admin", "rl-engineer"],
            ),
        ).fetchall()
    ]


def default_graders(c, project, creator):
    """Prefer individually assigned engineers; Admin fills missing grading duties."""
    reviewers = [u for u in members(c, project, "reviewer") if u != str(creator)]
    if reviewers:
        return reviewers[:2]
    owners = [u for u in domain.administrators(c, project) if u != str(creator)]
    return (owners or domain.administrators(c, project))[:1]


def view(c, plan):
    out = dict(plan)
    objective = domain.get_resource(c, plan["objective_id"])
    out["objective"] = {
        "id": objective["id"],
        "lifecycle": objective["lifecycle"],
        "row_version": objective["row_version"],
        **{
            k: objective["content"].get(k)
            for k in ("title", "hypothesis", "measurement_plan", "business_context")
        },
    }
    components = []
    for tid in plan["task_ids"]:
        task = domain.get_resource(c, tid)
        rubric = domain.get_revision(c, task["content"]["rubric_revision_id"], "rubric")
        components.append(
            {"kind": "task", "title": task["content"]["title"], "lifecycle": task["lifecycle"]}
        )
        components.append(
            {
                "kind": "rubric",
                "title": rubric["content"]["title"],
                "lifecycle": rubric["lifecycle"],
            }
        )
    for kind, rid in (("suite", plan["suite_id"]), ("protocol", plan["protocol_id"])):
        if rid:
            r = domain.get_resource(c, rid)
            components.append(
                {"kind": kind, "title": r["content"]["title"], "lifecycle": r["lifecycle"]}
            )
    out["components"] = components
    if plan["run_id"]:
        out["run"] = one(
            c, "SELECT id,state,row_version FROM anvil.runs WHERE id=%s", (plan["run_id"],)
        )
    out["missing"] = missing(plan)
    return out


def missing(plan):
    gaps = []
    if not plan["case_ids"]:
        gaps.append("Choose at least one task set in step 3")
    if not plan["rubric"]:
        gaps.append("Define the rubric in step 4")
    return gaps


def approve_component(c, rid, user, roles, rationale):
    r = domain.get_resource(c, rid, True)
    if r["lifecycle"] in ("draft", "changes_requested"):
        domain.qualify(c, r)
        r = domain.move(c, r, user, "submitted")
    if r["lifecycle"] == "submitted":
        r = domain.decide(
            c, r, user, roles, Decision(purpose="approval", decision="approve", rationale=rationale)
        )
    return r


def grant_rights(c, project, user, source_revision_id, plan_id):
    """Same rule as the rights screen: a designated rights reviewer who did not create the source."""
    if domain.rights_ok(c, source_revision_id):
        return
    if not one(
        c,
        "SELECT 1 FROM anvil.project_assignments WHERE project_id=%s AND user_id=%s AND capability='rights_reviewer' AND active",
        (project, user),
    ):
        raise HTTPException(
            409, "Local evaluation rights need a Admin with the rights-reviewer capability"
        )
    source = domain.get_revision(c, source_revision_id, "case")
    c.execute(
        """INSERT INTO anvil.rights_grants(id,project_id,source_revision_id,operation,destination,status,reviewed_by,evidence,expires_at)
           VALUES(%s,%s,%s,'managed_evaluation','local_fixture','approved',%s,%s,NULL)
           ON CONFLICT(source_revision_id,operation,destination) DO UPDATE SET status='approved',
           reviewed_by=excluded.reviewed_by,evidence=excluded.evidence,row_version=anvil.rights_grants.row_version+1""",
        (
            uid(),
            project,
            source_revision_id,
            user,
            f"Local synthetic fixture evaluation approved by the Admin in evaluation plan {plan_id}.",
        ),
    )
    audit(
        c,
        project,
        user,
        "rights.approved",
        source["resource_id"],
        {
            "operation": "managed_evaluation",
            "destination": "local_fixture",
            "plan_id": str(plan_id),
        },
    )


def touch(c, pid, **fields):
    sets = ",".join(f"{k}=%s" for k in fields)
    values = [Jsonb(v) if isinstance(v, (dict, list)) else v for v in fields.values()]
    c.execute(
        f"UPDATE anvil.evaluation_plans SET {sets},row_version=row_version+1,updated_at=now() WHERE id=%s",
        (*values, pid),
    )


def routes(context, wrap, idempotent):
    @router.get("/options")
    def options(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *domain.CONTENT_ROLES)
            template = json.loads(fixtures.trusted("rubric-template.json"))
            cases = []
            for case in BUILT_IN:
                manifest = json.loads(fixtures.trusted(f"{case}/case.json"))
                cases.append(
                    {
                        "id": case,
                        "title": manifest["title"],
                        "capabilities": manifest["capabilities"],
                        "split": manifest["split"],
                    }
                )
            names = {
                str(r["id"]): r["name"]
                for r in c.execute(
                    "SELECT u.id,u.name FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id WHERE m.project_id=%s AND m.active",
                    (project,),
                ).fetchall()
            }
            people = lambda ids: [{"id": i, "name": names.get(i, i)} for i in ids]  # noqa: E731
            return wrap(
                {
                    "cases": cases,
                    "rubric_template": {
                        "criteria": template["criteria"],
                        "threshold": template["threshold"],
                    },
                    "reviewers": people(members(c, project, "reviewer")),
                    "admins": people(domain.administrators(c, project)),
                    "default_graders": people(default_graders(c, project, user)),
                },
                request,
            )

    @router.get("")
    def list_plans(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *domain.CONTENT_ROLES, "admin")
            rows = c.execute(
                "SELECT * FROM anvil.evaluation_plans ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
            return wrap([view(c, r) for r in rows], request)

    @router.get("/{pid}")
    def detail(project: UUID, pid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *domain.CONTENT_ROLES, "admin")
            return wrap(view(c, get_plan(c, pid)), request)

    @router.post("", status_code=201)
    def create(project: UUID, body: NewPlan, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher")

            def act():
                content = domain.validate_content(
                    c,
                    project,
                    "objective",
                    objective_content(
                        user,
                        body.title,
                        body.hypothesis,
                        body.success_criteria,
                        body.business_context,
                    ),
                )
                objective = domain.create(c, project, user, "objective", content)
                pid = uid()
                c.execute(
                    "INSERT INTO anvil.evaluation_plans(id,project_id,title,objective_id,created_by,grader_ids) VALUES(%s,%s,%s,%s,%s,%s)",
                    (
                        pid,
                        project,
                        body.title,
                        objective["id"],
                        user,
                        Jsonb(default_graders(c, project, user)),
                    ),
                )
                audit(c, project, user, "evaluation_plan.created", pid)
                return view(c, get_plan(c, pid))

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.patch("/{pid}")
    def update(project: UUID, pid: UUID, body: PlanUpdate, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher")

            def act():
                plan = get_plan(c, pid, True)
                domain.etag(plan, request.headers.get("if-match"))
                if plan["state"] not in EDITABLE:
                    raise HTTPException(409, "Submitted evaluations cannot be edited")
                if str(plan["created_by"]) != str(user):
                    raise HTTPException(403, "Only the evaluation author can edit it")
                objective_fields = ("title", "hypothesis", "success_criteria", "business_context")
                if any(getattr(body, k) is not None for k in objective_fields):
                    r = domain.get_resource(c, plan["objective_id"], True)
                    if r["lifecycle"] not in EDITABLE:
                        raise HTTPException(409, "The objective is no longer a draft")
                    old = r["content"]
                    content = domain.validate_content(
                        c,
                        project,
                        "objective",
                        objective_content(
                            user,
                            body.title or old["title"],
                            body.hypothesis or old["hypothesis"],
                            body.success_criteria or old["measurement_plan"],
                            body.business_context
                            if body.business_context is not None
                            else old["business_context"],
                        ),
                    )
                    if content != old:
                        domain.revise(c, r, user, content)
                fields = {}
                if body.title:
                    fields["title"] = body.title
                if body.background_notes is not None or body.sources is not None:
                    background = dict(plan["background"])
                    if body.background_notes is not None:
                        background["notes"] = body.background_notes
                    if body.sources is not None:
                        background["sources"] = [s.model_dump() for s in body.sources]
                    fields["background"] = background
                if body.case_ids is not None:
                    fields["case_ids"] = list(dict.fromkeys(body.case_ids))
                if body.rubric is not None:
                    fields["rubric"] = body.rubric.model_dump(mode="json")
                if body.benchmark is not None:
                    fields["benchmark"] = body.benchmark.model_dump(mode="json")
                if body.grader_ids is not None:
                    graders = [str(g) for g in body.grader_ids]
                    allowed = set(members(c, project, "reviewer")) | set(
                        domain.administrators(c, project)
                    )
                    if (
                        not graders
                        or not set(graders) <= allowed
                        or len(set(graders)) != len(graders)
                    ):
                        raise HTTPException(
                            422, "Graders must be distinct project Reviewers or Admins"
                        )
                    fields["grader_ids"] = graders
                if body.candidates is not None:
                    fields["candidates"] = list(dict.fromkeys(body.candidates))
                if fields:
                    touch(c, pid, **fields)
                audit(c, project, user, "evaluation_plan.updated", pid, {"fields": sorted(fields)})
                return view(c, get_plan(c, pid))

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/{pid}/submit")
    def submit(project: UUID, pid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher")

            def act():
                plan = get_plan(c, pid, True)
                domain.etag(plan, request.headers.get("if-match"))
                if plan["state"] not in EDITABLE:
                    raise HTTPException(409, "Evaluation already submitted")
                if str(plan["created_by"]) != str(user):
                    raise HTTPException(403, "Only the evaluation author can submit it")
                gaps = missing(plan)
                if gaps:
                    raise HTTPException(422, "; ".join(gaps))
                objective = domain.get_resource(c, plan["objective_id"], True)
                if objective["lifecycle"] in EDITABLE:
                    domain.qualify(c, objective)
                    domain.move(c, objective, user, "submitted")
                task_ids = plan["task_ids"]
                if not task_ids:
                    rubric = {"title": f"{plan['title']} rubric", **plan["rubric"]}
                    tasks = fixtures.load(
                        c, project, user, FixtureImport(case_ids=plan["case_ids"]), rubric
                    )
                    task_ids = [str(t["id"]) for t in tasks]
                touch(c, pid, state="submitted", task_ids=task_ids)
                audit(c, project, user, "evaluation_plan.submitted", pid)
                return view(c, get_plan(c, pid))

            return wrap(idempotent(c, project, user, request, {}, act), request)

    @router.post("/{pid}/decision")
    def decide(project: UUID, pid: UUID, body: PlanDecision, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "product-owner")

            def act():
                plan = get_plan(c, pid, True)
                domain.etag(plan, request.headers.get("if-match"))
                if plan["state"] != "submitted":
                    raise HTTPException(409, "Only submitted evaluations can be decided")
                self_approved = str(plan["created_by"]) == str(user)
                if body.decision == "changes_requested":
                    objective = domain.get_resource(c, plan["objective_id"], True)
                    if objective["lifecycle"] == "submitted":
                        domain.decide(
                            c,
                            objective,
                            user,
                            roles,
                            Decision(
                                purpose="approval",
                                decision="changes_requested",
                                rationale=body.rationale,
                            ),
                        )
                    c.execute(
                        "UPDATE anvil.evaluation_plans SET state='changes_requested',decided_by=%s,decided_at=now(),decision_rationale=%s,self_approved=%s,row_version=row_version+1,updated_at=now() WHERE id=%s",
                        (user, body.rationale, self_approved, pid),
                    )
                    audit(c, project, user, "evaluation_plan.changes_requested", pid)
                    return view(c, get_plan(c, pid))
                note = f"Approved in evaluation plan {pid}: {body.rationale}"
                objective = approve_component(c, plan["objective_id"], user, roles, note)
                tasks = []
                for tid in plan["task_ids"]:
                    task = domain.get_resource(c, tid, True)
                    grant_rights(c, project, user, task["content"]["source_revision_id"], pid)
                    rubric = domain.get_revision(c, task["content"]["rubric_revision_id"], "rubric")
                    approve_component(c, rubric["resource_id"], user, roles, note)
                    task = approve_component(c, tid, user, roles, note)
                    if task["lifecycle"] == "qualified":
                        domain.qualify(c, task)
                        task = domain.move(c, task, user, "published")
                    tasks.append(task)
                bench = plan["benchmark"] or {}
                suite_content = {
                    "title": f"{plan['title']} suite",
                    "objective_revision_id": str(objective["current_revision_id"]),
                    "task_revision_ids": [str(t["current_revision_id"]) for t in tasks],
                    "selection_method": "Selected by the author in the evaluation wizard: "
                    + ", ".join(plan["case_ids"]),
                    "exposure_note": "Original ADI synthetic fixtures; development split, illustrative only.",
                    "planned_source_count": len(tasks),
                }
                if bench.get("recommendation_revision_id"):
                    suite_content.update(
                        benchmark_revision_ids=bench["benchmark_revision_ids"],
                        recommendation_revision_id=bench["recommendation_revision_id"],
                        recommendation_override_reason=bench.get("override_reason", ""),
                    )
                suite = domain.create(
                    c,
                    project,
                    plan["created_by"],
                    "suite",
                    domain.validate_content(c, project, "suite", suite_content),
                )
                suite = approve_component(c, suite["id"], user, roles, note)
                domain.qualify(c, suite)
                suite = domain.move(c, suite, user, "frozen")
                threshold = plan["rubric"]["threshold"]
                protocol = domain.create(
                    c,
                    project,
                    plan["created_by"],
                    "protocol",
                    domain.validate_content(
                        c,
                        project,
                        "protocol",
                        {
                            "title": f"{plan['title']} protocol",
                            "objective_revision_id": str(objective["current_revision_id"]),
                            "suite_revision_id": str(suite["current_revision_id"]),
                            "candidates": plan["candidates"],
                            "reviewer_ids": plan["grader_ids"],
                            "comparison_policy": "Descriptive comparison of fixture candidates on the same frozen suite; no statistical claim.",
                            "pass_policy": f"Pass when the rubric score is at least {threshold} with no critical violation.",
                        },
                    ),
                )
                protocol = approve_component(c, protocol["id"], user, roles, note)
                run = uid()
                c.execute(
                    "INSERT INTO anvil.runs(id,project_id,protocol_revision_id,origin,created_by) VALUES(%s,%s,%s,'illustrative',%s)",
                    (run, project, protocol["current_revision_id"], plan["created_by"]),
                )
                audit(c, project, user, "run.prepared", run, {"plan_id": str(pid)})
                c.execute(
                    "UPDATE anvil.evaluation_plans SET state='approved',suite_id=%s,protocol_id=%s,run_id=%s,decided_by=%s,decided_at=now(),decision_rationale=%s,self_approved=%s,row_version=row_version+1,updated_at=now() WHERE id=%s",
                    (suite["id"], protocol["id"], run, user, body.rationale, self_approved, pid),
                )
                audit(
                    c,
                    project,
                    user,
                    "evaluation_plan.approved",
                    pid,
                    {"self_approved": self_approved},
                )
                return view(c, get_plan(c, pid))

            return wrap(idempotent(c, project, user, request, body, act), request)

    return router
