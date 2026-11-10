"""Versioned matching metadata in the existing registry; no new execution boundary."""

from fractions import Fraction
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, field_validator

from anvil import auth, domain
from anvil.db import audit
from anvil.schemas import Strict

FIELDS = (
    "domain",
    "subdomain",
    "modality",
    "task_type",
    "agent_type",
    "horizon",
    "interaction_model",
    "environment",
    "tools",
    "capabilities",
    "output_artifact",
    "language_locale",
    "risk",
    "evaluation_target",
)
WEIGHTS = {
    "domain": 20,
    "modality": 20,
    "task_type": 20,
    "capabilities": 15,
    "interaction_horizon": 10,
    "evaluator": 10,
    "operational": 5,
}
POLICY = "deterministic-overlap-v1"
LIMIT = 100


class Selection(Strict):
    objective_revision_id: UUID
    task_revision_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("task_revision_ids")
    @classmethod
    def unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Select unique task revisions")
        return sorted(value, key=str)


class Confirm(Selection):
    title: str = Field(min_length=3, max_length=200)
    dimensions: dict[str, list[str]]

    @field_validator("dimensions")
    @classmethod
    def dimensions_valid(cls, value):
        if set(value) != set(FIELDS):
            raise ValueError("Confirm all fourteen required TaskProfile dimensions")
        result = {}
        for key in FIELDS:
            values = value[key]
            if not 1 <= len(values) <= 30 or any(
                not x.strip()
                or x.strip().casefold() == "unconfirmed"
                or len(x) > 100
                or "\x00" in x
                for x in values
            ):
                raise ValueError(f"Invalid dimension: {key}")
            result[key] = sorted({x.strip().casefold() for x in values})
        return result


class Recommend(Strict):
    profile_revision_id: UUID
    threshold: int = Field(default=75, ge=1, le=100, strict=True)


class Select(Strict):
    recommendation_revision_id: UUID
    benchmark_revision_ids: list[UUID] = Field(min_length=1, max_length=10)
    title: str = Field(min_length=3, max_length=200)
    advisor_id: UUID
    override_reason: str = Field(default="", max_length=2000)


def selection(c, body):
    domain.get_revision(c, body.objective_revision_id, "objective", ["approved"])
    tasks = [domain.get_revision(c, tid, "task", ["published"]) for tid in body.task_revision_ids]
    for task in tasks:
        source = domain.current_source(c, task["content"]["source_revision_id"])
        if (
            task["content"].get("origin") != "original_synthetic_fixture"
            or source["content"].get("source_origin") != "original_synthetic_fixture"
        ):
            raise HTTPException(
                409,
                "This increment profiles qualified original synthetic tasks only; partner intake remains separately governed",
            )
    return tasks


def infer(c, tasks):
    dimensions = {key: ["unconfirmed"] for key in FIELDS}
    dimensions.update(
        modality=["text"],
        agent_type=["language-model"],
        tools=["none"],
        output_artifact=["structured-answer"],
        language_locale=["en-us"],
        risk=["synthetic-development"],
        evaluation_target=["anchored-rubric"],
        task_type=["decision-support"],
    )
    sources = [domain.get_revision(c, t["content"]["source_revision_id"], "case") for t in tasks]
    dimensions["domain"] = sorted(
        {s.casefold() for source in sources for s in source["content"].get("subjects", [])}
    ) or ["unconfirmed"]
    dimensions["capabilities"] = sorted({v for t in tasks for v in t["content"]["capabilities"]})
    dimensions["interaction_model"] = sorted({t["content"]["mode"] for t in tasks})
    dimensions["environment"] = sorted(
        {t["content"].get("environment_version") or "static-input" for t in tasks}
    )
    dimensions["horizon"] = sorted(
        {
            "12-weeks" if t["content"].get("environment_version") else "single-response"
            for t in tasks
        }
    )
    mixed = [
        key
        for key in ("domain", "interaction_model", "environment", "horizon")
        if len(dimensions[key]) > 1
    ]
    return {
        "dimensions": dimensions,
        "evidence": {
            key: {
                "confidence": 1.0
                if key in ("capabilities", "interaction_model", "environment")
                else 0.3,
                "basis": "task/source metadata"
                if key in ("domain", "capabilities", "interaction_model", "environment")
                else "provisional default; human confirmation required",
                "task_revision_ids": [str(t["id"]) for t in tasks],
            }
            for key in FIELDS
        },
        "heterogeneity": mixed,
        "segmentation_advice": "Separate populations by " + ", ".join(mixed)
        if mixed
        else "No incompatible population detected in declared metadata",
    }


def overlap(required, available):
    return Fraction(len(set(required) & set(available)), len(set(required)))


def rank(profile, candidates, threshold):
    """Pure exact rational scoring, stable tie breaks and bounded greedy composition."""
    p = profile["dimensions"]
    ranked, excluded = [], []
    for candidate in sorted(candidates, key=lambda b: b["revision_id"]):
        b = candidate["dimensions"]
        reasons = list(candidate.get("blockers", []))
        for key in ("modality", "environment", "output_artifact", "agent_type", "language_locale"):
            if not set(p[key]) <= set(b[key]):
                reasons.append("incompatible_" + key)
        if reasons:
            excluded.append(
                {
                    "revision_id": candidate["revision_id"],
                    "title": candidate["title"],
                    "reasons": sorted(set(reasons)),
                }
            )
            continue
        scores = {
            key: overlap(p[key], b[key])
            for key in ("domain", "modality", "task_type", "capabilities")
        }
        scores["interaction_horizon"] = (
            overlap(p["interaction_model"], b["interaction_model"])
            + overlap(p["horizon"], b["horizon"])
        ) / 2
        scores["evaluator"] = overlap(p["evaluation_target"], b["evaluation_target"])
        scores["operational"] = (
            overlap(p["tools"], b["tools"]) + overlap(p["risk"], b["risk"])
        ) / 2
        total = sum(WEIGHTS[k] * v for k, v in scores.items())
        gaps = {
            key: sorted(set(values) - set(b[key]))
            for key, values in p.items()
            if not set(values) <= set(b[key])
        }
        ranked.append(
            {
                **candidate,
                "total_score": round(float(total), 4),
                "dimension_scores": {k: round(float(v * 100), 4) for k, v in scores.items()},
                "uncovered_requirements": gaps,
                "reasons": [
                    f"{key}: {len(set(p[key]) & set(b[key]))}/{len(p[key])} requirements matched"
                    for key in FIELDS
                ],
                "task_coverage": {
                    "catalog_tasks": len(candidate["task_revision_ids"]),
                    "selected_tasks": len(
                        set(profile["task_revision_ids"]) & set(candidate["task_revision_ids"])
                    ),
                    "basis": "exact task IDs; capability overlap is not performance",
                },
                "runtime_seconds": None,
                "cost_usd_range": None,
                "estimate_reason": "No measured runtime or approved pricing for this metadata selection",
            }
        )
    ranked.sort(key=lambda x: (-x["total_score"], x["revision_id"]))
    uncovered = set(p["capabilities"])
    composition = []
    remaining = list(ranked)
    while uncovered and remaining and len(composition) < 10:
        best = min(
            remaining,
            key=lambda x: (
                -len(uncovered & set(x["dimensions"]["capabilities"])),
                len(set(x["dimensions"]["capabilities"]) - uncovered),
                -x["total_score"],
                x["revision_id"],
            ),
        )
        if not uncovered & set(best["dimensions"]["capabilities"]):
            break
        composition.append(best["revision_id"])
        uncovered -= set(best["dimensions"]["capabilities"])
        # Do not compose benchmarks with differing evaluator contracts.
        remaining = [
            x
            for x in remaining
            if x["revision_id"] not in composition
            and x["dimensions"]["evaluation_target"] == best["dimensions"]["evaluation_target"]
        ]
    return {
        "ranked": ranked,
        "excluded": excluded,
        "composition": composition,
        "composition_uncovered_capabilities": sorted(uncovered),
        "composition_policy": "greedy capability coverage, duplicate minimization, equal evaluator; cost unknown",
        "strategy": "direct_use"
        if ranked
        and ranked[0]["total_score"] >= threshold
        and not ranked[0]["uncovered_requirements"]
        else "compose_or_extend"
        if composition and not uncovered
        else "create_from_gaps",
        "below_threshold": not ranked or ranked[0]["total_score"] < threshold,
    }


def catalog(c):
    items = c.execute("""SELECT r.id,r.current_revision_id,r.lifecycle,v.content FROM anvil.resources r
        JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE r.kind='benchmark'
        AND NOT(v.content ? 'profile') AND jsonb_typeof(v.content->'dimensions')='object'
        AND v.content ?& ARRAY['title','dimensions','task_revision_ids','objective_revision_id','provenance']
        ORDER BY r.id LIMIT 101""").fetchall()
    if len(items) > LIMIT:
        raise HTTPException(
            409, "Catalog scope exceeds 100 versions; segment the project before ranking"
        )
    return items


def candidate(c, record):
    content = record["content"]
    if (
        content.get("profile")
        or not isinstance(content.get("dimensions"), dict)
        or set(content["dimensions"]) != set(FIELDS)
    ):
        raise HTTPException(409, "This version is not a legacy TaskProfile catalog entry")
    blockers = []
    if record["lifecycle"] != "registered":
        blockers.append("metadata_not_registered")
    dimensions = content["dimensions"]
    supported = {
        "modality": ["text"],
        "agent_type": ["language-model"],
        "environment": ["static-input"],
        "output_artifact": ["structured-answer"],
        "evaluation_target": ["anchored-rubric"],
        "tools": ["none"],
    }
    for key, values in supported.items():
        if dimensions[key] != values:
            blockers.append("unsupported_adapter_contract_" + key)
    for tid in content["task_revision_ids"]:
        try:
            task = domain.get_revision(c, tid, "task", ["published"])
            source = task["content"]["source_revision_id"]
            domain.current_source(c, source)
            if not domain.rights_ok(c, source):
                blockers.append("rights_not_approved_for_local_fixture")
            if task["content"]["mode"] != "static":
                blockers.append("requires_separate_interactive_runtime_qualification")
        except HTTPException:
            blockers.append("task_or_source_not_current_and_qualified")
    return {
        **{
            k: content[k]
            for k in (
                "title",
                "dimensions",
                "task_revision_ids",
                "objective_revision_id",
                "provenance",
            )
        },
        "revision_id": str(record["current_revision_id"]),
        "resource_id": str(record["id"]),
        "blockers": sorted(set(blockers)),
        "readiness": "metadata_only; manifest/adapter smoke release remains pending",
    }


def qualify_suite(c, body):
    """Also applies to generic Suite edits/creation: factory provenance cannot be bypassed."""
    if not body.get("recommendation_revision_id"):
        raise HTTPException(422, "Benchmark-bound suites require an exact recommendation")
    rec = domain.get_revision(c, body["recommendation_revision_id"], "recommendation")
    profile = domain.get_revision(
        c, rec["content"]["profile_revision_id"], "task_profile", ["confirmed"]
    )
    if body["objective_revision_id"] != profile["content"]["objective_revision_id"]:
        raise HTTPException(409, "Recommendation/objective mismatch")
    ranks = rec["content"]["ranked"]
    selected = body["benchmark_revision_ids"]
    if len(set(selected)) != len(selected) or not set(selected) <= {
        x["revision_id"] for x in ranks
    }:
        raise HTTPException(422, "Benchmarks must be compatible versions from the recommendation")
    if (
        selected != [ranks[0]["revision_id"]]
        or rec["content"]["below_threshold"]
        or any(x["uncovered_requirements"] for x in ranks if x["revision_id"] in selected)
    ) and len(body.get("recommendation_override_reason", "").strip()) < 10:
        raise HTTPException(422, "Recorded override rationale required")
    expected = set()
    for rid in selected:
        b = domain.get_revision(c, rid, "benchmark", ["registered"])
        if candidate(
            c,
            {
                "id": b["resource_id"],
                "current_revision_id": b["id"],
                "lifecycle": b["lifecycle"],
                "content": b["content"],
            },
        )["blockers"]:
            raise HTTPException(409, "Catalog qualification or rights changed")
        expected.update(b["content"]["task_revision_ids"])
    if set(body["task_revision_ids"]) != expected:
        raise HTTPException(409, "Suite task selection must equal pinned benchmark task versions")


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/factory")

    @router.get("/recommendations/{rid}")
    def snapshot(project: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *domain.CONTENT_ROLES)
            result = domain.get_revision(c, rid, "recommendation")
            audit(c, project, user, "factory.recommendation_read", result["resource_id"])
            return wrap(result, request)

    @router.get("/profiles")
    def profiles(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *domain.CONTENT_ROLES)
            result = c.execute("""SELECT r.id,r.current_revision_id,v.content FROM anvil.resources r
                JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE r.kind='task_profile'
                AND r.lifecycle='confirmed' ORDER BY r.created_at DESC LIMIT 100""").fetchall()
            audit(c, project, user, "factory.profiles_read")
            return wrap(result, request)

    @router.get("")
    def list_catalog(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *domain.CONTENT_ROLES)
            result = [candidate(c, item) for item in catalog(c)]
            audit(c, project, user, "factory.catalog_read")
            return wrap(result, request)

    @router.post("/profile-preview")
    def preview(project: UUID, body: Selection, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher")
            tasks = selection(c, body)
            audit(c, project, user, "factory.profile_preview")
            return wrap(infer(c, tasks), request)

    @router.post("/profiles")
    @router.post("/benchmarks")
    def confirm(project: UUID, body: Confirm, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher")

            def act():
                tasks = selection(c, body)
                inferred = infer(c, tasks)
                benchmark = request.url.path.endswith("/benchmarks")
                content = body.model_dump(mode="json") | {
                    "inference": inferred,
                    "confirmed_by": str(user),
                    "provenance": "original_synthetic_fixture",
                }
                if benchmark:
                    if not set(body.dimensions["capabilities"]) <= set(
                        inferred["dimensions"]["capabilities"]
                    ):
                        raise HTTPException(
                            422, "Catalog capabilities must exist on the selected tasks"
                        )
                    content["catalog_version"] = "1.0.0"
                    content["readiness"] = "metadata_only"
                links = [(str(body.objective_revision_id), "objective")] + [
                    (str(t["id"]), "profile_task") for t in tasks
                ]
                record = domain.create(
                    c, project, user, "benchmark" if benchmark else "task_profile", content, links
                )
                return domain.move(c, record, user, "registered" if benchmark else "confirmed")

            return wrap(
                idempotent(c, project, user, request, body.model_dump(mode="json"), act), request
            )

    @router.post("/recommendations")
    def recommend(project: UUID, body: Recommend, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher")

            def act():
                profile = domain.get_revision(
                    c, body.profile_revision_id, "task_profile", ["confirmed"]
                )
                selection(
                    c,
                    Selection.model_validate(
                        {
                            k: profile["content"][k]
                            for k in ("objective_revision_id", "task_revision_ids")
                        }
                    ),
                )
                versions = [candidate(c, x) for x in catalog(c)]
                content = {
                    "title": "Recommendations for " + profile["content"]["title"],
                    "profile_revision_id": str(profile["id"]),
                    "policy": POLICY,
                    "weights": WEIGHTS,
                    "threshold": body.threshold,
                    "catalog_revision_ids": sorted(x["revision_id"] for x in versions),
                    **rank(profile["content"], versions, body.threshold),
                }
                return domain.create(
                    c, project, user, "recommendation", content, [(str(profile["id"]), "profile")]
                )

            return wrap(
                idempotent(c, project, user, request, body.model_dump(mode="json"), act), request
            )

    @router.post("/suite-drafts")
    def suite(project: UUID, body: Select, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher")

            def act():
                rec = domain.get_revision(c, body.recommendation_revision_id, "recommendation")
                profile = domain.get_revision(
                    c, rec["content"]["profile_revision_id"], "task_profile", ["confirmed"]
                )
                ranks = rec["content"]["ranked"]
                selected = [str(x) for x in body.benchmark_revision_ids]
                if len(set(selected)) != len(selected) or not set(selected) <= {
                    x["revision_id"] for x in ranks
                }:
                    raise HTTPException(
                        422, "Select unique compatible versions from this recommendation"
                    )
                needs_reason = (
                    selected != ([ranks[0]["revision_id"]] if ranks else [])
                    or rec["content"]["below_threshold"]
                    or any(
                        x["uncovered_requirements"] for x in ranks if x["revision_id"] in selected
                    )
                )
                if needs_reason and len(body.override_reason.strip()) < 10:
                    raise HTTPException(
                        422,
                        "Explain the override or uncovered-requirements selection (10 characters minimum)",
                    )
                tasks = set()
                for rid in selected:
                    b = domain.get_revision(c, rid, "benchmark", ["registered"])
                    if candidate(
                        c,
                        {
                            "id": b["resource_id"],
                            "current_revision_id": b["id"],
                            "lifecycle": b["lifecycle"],
                            "content": b["content"],
                        },
                    )["blockers"]:
                        raise HTTPException(
                            409, "Selected benchmark now has rights/qualification blockers"
                        )
                    tasks.update(b["content"]["task_revision_ids"])
                content = domain.validate_content(
                    c,
                    project,
                    "suite",
                    {
                        "title": body.title,
                        "objective_revision_id": profile["content"]["objective_revision_id"],
                        "task_revision_ids": sorted(tasks),
                        "benchmark_revision_ids": selected,
                        "recommendation_revision_id": str(rec["id"]),
                        "advisor_id": str(body.advisor_id),
                        "recommendation_override_reason": body.override_reason,
                        "selection_method": "Factory recommendation "
                        + str(rec["id"])
                        + "; "
                        + body.override_reason,
                        "exposure_note": "ADI synthetic development tasks; metadata match is not model performance or smoke qualification",
                        "planned_source_count": len(tasks),
                    },
                )
                r = domain.create(c, project, user, "suite", content)
                domain.qualify(c, r)
                return r

            return wrap(
                idempotent(c, project, user, request, body.model_dump(mode="json"), act), request
            )

    @router.post("/recommendations/{rid}/gap-draft")
    def gap(project: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher")

            def act():
                rec = domain.get_revision(c, rid, "recommendation")
                p = domain.get_revision(
                    c, rec["content"]["profile_revision_id"], "task_profile", ["confirmed"]
                )
                selection(
                    c,
                    Selection.model_validate(
                        {k: p["content"][k] for k in ("objective_revision_id", "task_revision_ids")}
                    ),
                )
                content = p["content"] | {
                    "title": "Gap draft: " + p["content"]["title"],
                    "recommendation_revision_id": str(rec["id"]),
                    "readiness": "draft; human review and runtime qualification required",
                    "uncovered_requirements": rec["content"]["ranked"][0]["uncovered_requirements"]
                    if rec["content"]["ranked"]
                    else p["content"]["dimensions"],
                }
                return domain.create(
                    c,
                    project,
                    user,
                    "benchmark",
                    content,
                    [(str(p["id"]), "profile"), (str(rec["id"]), "recommendation")],
                )

            return wrap(idempotent(c, project, user, request, {}, act), request)

    return router
