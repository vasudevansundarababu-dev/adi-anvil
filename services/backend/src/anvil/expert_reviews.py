"""Optional, evidence-bound human assessments over immutable grader projections.

No candidate endpoint creates automated targets. Human review never writes native
scores, clears a critical gate, triggers rescoring, or dispatches a model request.
"""

import io
import json
from collections import defaultdict
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from pydantic import Field, StrictBool, field_validator, model_validator

from anvil.db import Jsonb, audit, digest, one, uid
from anvil.schemas import Strict

SHA = r"^[a-f0-9]{64}$"


class Review(Strict):
    expected_review_revision: str = Field(pattern=SHA)
    snapshot_sha256: str = Field(pattern=SHA)
    rationale: str = Field(min_length=10, max_length=4000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("evidence_ids")
    @classmethod
    def distinct_evidence(cls, value):
        if len(value) != len(set(value)) or any(not x or len(x) > 200 for x in value):
            raise ValueError("Unique bounded evidence identifiers required")
        return value


class RatioMeasure(Strict):
    kind: Literal["ratio"]
    numerator: int = Field(ge=0, le=1000000000, strict=True)
    denominator: int = Field(ge=1, le=1000000000, strict=True)

    @model_validator(mode="after")
    def bounded(self):
        if self.numerator > self.denominator:
            raise ValueError("Numerator cannot exceed the declared denominator")
        return self


class CountMeasure(Strict):
    kind: Literal["count"]
    value: int = Field(ge=0, le=1000000000, strict=True)


class Assess(Review):
    status: Literal["scored", "unscored", "not_applicable", "comment_only"]
    award: int | None = Field(default=None, strict=True)
    measurements: dict[str, RatioMeasure | CountMeasure] | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def numerical_award(self):
        numerical = self.award is not None or bool(self.measurements)
        if (self.status == "scored") != numerical or self.award is not None and self.measurements:
            raise ValueError(
                "A scored assessment carries one native award or typed diagnostic measurements"
            )
        if self.status != "comment_only" and not self.evidence_ids:
            raise ValueError("Assessment requires evidence references")
        return self


class Diagnose(Review):
    failure_mode: Literal[
        "no_failure",
        "input_omission",
        "extraction_error",
        "policy_selection",
        "policy_application",
        "stale_version",
        "handoff",
        "tool_failure",
        "evidence_unavailable",
        "reference_ambiguity",
        "unresolved",
    ]
    attribution: Literal["agent", "environment_tool", "task_reference", "none", "unresolved"]
    certainty: Literal["observed", "likely", "unresolved"]
    evaluator_finding: Literal[
        "agrees", "false_pass", "false_fail", "insufficient_evidence", "unresolved"
    ]

    @model_validator(mode="after")
    def cited(self):
        if not self.evidence_ids:
            raise ValueError("Diagnosis requires evidence references")
        return self


class Resolve(Assess):
    review_ids: list[UUID] = Field(min_length=2, max_length=100)


class Correction(Review):
    issue: Literal[
        "task_instruction",
        "reference_answer",
        "policy_interpretation",
        "rubric_definition",
        "evaluator",
        "missing_evidence",
    ]
    suggested_change: str = Field(min_length=10, max_length=4000)


class Freeze(Strict):
    expected_review_revision: str = Field(pattern=SHA)
    snapshot_sha256: str = Field(pattern=SHA)
    sample_selection: str = Field(min_length=10, max_length=1000)


class Assign(Strict):
    user_id: UUID
    active: StrictBool


def permissions(roles):
    return {
        "sme_review": bool({"admin", "sme-reviewer"} & roles),
        "rl_diagnosis": bool({"admin", "rl-engineer"} & roles),
    }


def require_reader(roles):
    if not {"admin", "rl-engineer", "sme-reviewer"} & roles:
        raise HTTPException(403, "Assigned project result access required")


def navigation(c, project):
    rows = c.execute(
        "SELECT anvil.result_run_navigation(project_id,run_id) AS value FROM anvil.expert_review_executions WHERE project_id=%s ORDER BY created_at DESC,run_id DESC LIMIT 100",
        (project,),
    ).fetchall()
    runs = [x["value"] for x in rows]
    groups = {
        r["snapshot"]["task_group_id"]: {
            "id": r["snapshot"]["task_group_id"],
            "name": r["project_name"],
        }
        for r in runs
        if r["snapshot"]["task_group_id"]
    }
    return {
        "runs": runs,
        "groups": list(groups.values()),
        "plans": [],
        "methods": [],
        "models": [],
        "provider_calls": None,
        "read_only": True,
    }


def register_execution(
    c, project, run, snapshot_sha256, origin, gates, *, kind="benchmark_run", expected_scope=None
):
    """Trusted grader/worker only; SQL verifies the persisted execution identity."""
    c.execute(
        "INSERT INTO anvil.expert_review_executions(project_id,run_id,kind,snapshot_sha256,origin,gates,expected_scope) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (project, run, kind, snapshot_sha256, origin, Jsonb(gates), Jsonb(expected_scope or {})),
    )
    row = one(
        c,
        "SELECT * FROM anvil.expert_review_executions WHERE project_id=%s AND run_id=%s",
        (project, run),
    )
    if (
        not row
        or row["snapshot_sha256"] != snapshot_sha256
        or row["origin"] != origin
        or row["gates"] != gates
        or row["expected_scope"] != (expected_scope or {})
    ):
        raise ValueError("Immutable execution review projection mismatch")


def register_target(c, project, run, key, content):
    """Persist a private-grader's deliberately public-safe bounded evidence view.

    Callers must never pass a private reference, future observation or full case.
    Only the declared fields cross this boundary; the public API cannot call it.
    """
    allowed = {
        "case_id",
        "model_key",
        "repetition",
        "role",
        "step",
        "skill_id",
        "skill",
        "criterion_id",
        "scale",
        "automated",
        "expected",
        "observed",
        "evidence",
        "source",
        "weight",
        "official",
        "applicability",
        "evidence_contract",
        "skill_name",
        "design_role",
        "design_step",
        "capability_association",
        "success_condition",
        "proposed_evaluator",
        "evidence_required",
        "counting_unit_or_trigger",
        "step_status",
        "role_mapping_status",
        "design_metadata_sha256",
        "design_source_sha256",
        "authored_steps",
        "skill_mapping_sha256",
        "skill_mapping_binding",
    }
    if (
        set(content) - allowed
        or not {
            "case_id",
            "model_key",
            "repetition",
            "role",
            "step",
            "scale",
            "automated",
            "evidence",
            "official",
            "applicability",
        }
        <= content.keys()
    ):
        raise ValueError("Explicit public-safe target projection required")
    if content["official"] and content["scale"]["levels"] not in ([0, 2, 5], [0, 1, 2, 3, 4]):
        raise ValueError("Native official rubric scale required")
    if (
        content["automated"]["award"] is not None
        and content["automated"]["award"] not in content["scale"]["levels"]
    ):
        raise ValueError("Automated award outside the bound scale")
    if len(content["evidence"]) > 100 or len({e["id"] for e in content["evidence"]}) != len(
        content["evidence"]
    ):
        raise ValueError("Unique bounded public evidence projection required")
    identifier, fingerprint = uid(), digest(content)
    c.execute(
        "INSERT INTO anvil.expert_review_targets(id,project_id,run_id,target_key,content,content_sha256) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(run_id,target_key) DO NOTHING",
        (identifier, project, run, key, Jsonb(content), fingerprint),
    )
    row = one(
        c,
        "SELECT id,content_sha256 FROM anvil.expert_review_targets WHERE project_id=%s AND run_id=%s AND target_key=%s",
        (project, run, key),
    )
    if row["content_sha256"] != fingerprint:
        raise ValueError("Automated baseline cannot be overwritten")
    return str(row["id"])


def register_evidence(c, project, run, title, content):
    fingerprint = digest(content)
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.expert_review_evidence(id,project_id,run_id,title,content,sha256) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(run_id,sha256) DO NOTHING",
        (identifier, project, run, title, Jsonb(content), fingerprint),
    )
    row = one(
        c,
        "SELECT id,title FROM anvil.expert_review_evidence WHERE project_id=%s AND run_id=%s AND sha256=%s",
        (project, run, fingerprint),
    )
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "sha256": fingerprint,
        "excerpt": json.dumps(content, ensure_ascii=False)[:1500],
        "excerpt_only": True,
    }


def register_kyc_cell(c, project, run, cell, result, *, kind="benchmark_run", snapshot_sha256=None):
    """Actual KYC grader producer; no private expectation fields are projected."""
    if snapshot_sha256 is None:
        execution = one(
            c,
            "SELECT snapshot_sha256,snapshot FROM anvil.benchmark_runs WHERE project_id=%s AND id=%s",
            (project, run),
        )
        snapshot_sha256 = execution["snapshot_sha256"]
        scope_snapshot = execution["snapshot"]
        model_ids = [str(x["id"]) for x in scope_snapshot.get("models", [])]
        count = scope_snapshot["planned_cells"] // len(model_ids) if model_ids else None
        repetitions = range(scope_snapshot.get("repetitions", 0))
    else:
        execution = one(
            c,
            "SELECT snapshot FROM anvil.workspace_execution_groups WHERE project_id=%s AND id=%s",
            (project, run),
        )
        scope_snapshot = execution["snapshot"]["preparation"]
        model_ids = [str(x["id"]) for x in scope_snapshot.get("models", [])]
        count = scope_snapshot.get("case_count", 0) * scope_snapshot.get("trials_per_model", 1)
        repetitions = range(1, scope_snapshot.get("trials_per_model", 0) + 1)
    from anvil.golden_kyc_evaluators import CRITERIA

    expected_scope = {
        "criterion_ids": list(CRITERIA),
        "episodes_per_model": count,
        "model_keys": model_ids,
        "scope_origin": "frozen_execution_manifest",
        # Case identities come only from the frozen plan, never observed results.
        # Native benchmark cells use zero-based repetition; workspace trials use
        # one-based repetition. Preserve those wire identities without coercion.
        "episodes": [
            {"case_id": assignment["application_id"], "repetition": repetition}
            for assignment in scope_snapshot.get("case_assignments", [])
            for repetition in repetitions
        ],
    }
    group_id = scope_snapshot.get("task_group_id") or (
        scope_snapshot.get("project_binding") or {}
    ).get("task_group_id")
    source_group = (
        one(
            c,
            "SELECT content,content_sha256 FROM anvil.benchmark_task_groups WHERE project_id=%s AND id=%s",
            (project, group_id),
        )
        if group_id
        else None
    )
    if source_group and digest(source_group["content"]) != source_group["content_sha256"]:
        raise ValueError("Diagnostic task source integrity mismatch")
    source_task = (
        next(
            (
                task
                for task in source_group["content"].get("tasks", [])
                if task["task_id"] == cell["task_key"]
            ),
            None,
        )
        if source_group
        else None
    )
    register_execution(
        c,
        project,
        run,
        snapshot_sha256,
        "native_kyc_sealed_evidence",
        {
            "evaluation": "Per-episode original gates are retained on each target; human awards never clear them"
        },
        kind=kind,
        expected_scope=expected_scope,
    )
    captured = cell["capture"]
    recommendation = one(
        c,
        "SELECT content FROM banking.recommendations WHERE project_id=%s AND trial_id=%s AND generation=%s",
        (project, captured["trial_id"], captured["generation"]),
    )
    evidence = [
        register_evidence(
            c,
            project,
            run,
            "Sealed actor recommendation",
            {
                "trial_id": captured["trial_id"],
                "generation": captured["generation"],
                "final": recommendation["content"] if recommendation else None,
            },
        ),
        register_evidence(
            c,
            project,
            run,
            "Native evaluation and evidence custody",
            {
                key: result[key]
                for key in (
                    "state_sha256",
                    "events_sha256",
                    "checks",
                    "critical_failures",
                    "decision_correctness",
                    "mandatory_conditions",
                    "evaluation_coverage",
                    "issues",
                    "task_safety",
                )
                if key in result
            },
        ),
    ]
    from anvil.golden_targets import design_metadata, requirements
    from anvil.skill_step_bindings import mapped, public_mapping

    diagnostic_task = source_task or {
        "task_id": cell["task_key"],
        "task_version": None,
        "payload_sha256": None,
        "source": {
            "schema_version": "anvil.golden-kyc.task.v1",
            "identity_status": "unresolved_native_execution_source",
        },
    }
    descriptors = {row["id"]: row for row in mapped(requirements(diagnostic_task), scope_snapshot)}

    for criterion, award in result["checks"].items():
        metadata = design_metadata("kyc", criterion)
        descriptor = descriptors.get(criterion) or metadata | {"role": "kyc_analyst", "step": None}
        content = {
            **metadata,
            **public_mapping(descriptor),
            "case_id": cell.get("case_key") or cell["task_key"],
            "model_key": cell["model_key"],
            "repetition": cell["repetition"],
            "role": descriptor["role"],
            "step": descriptor["step"],
            "skill_id": None,
            "skill": metadata["skill_name"],
            "criterion_id": criterion,
            "scale": {"levels": [0, 2, 5], "maximum": 5, "unit": "points"},
            "weight": 5,
            "official": True,
            "applicability": "required" if source_task else "unknown",
            "automated": {
                "award": award,
                "reason": "; ".join(result["issues"])
                if award is None
                else "Sealed native KYC criterion award",
                "evaluator": "golden-kyc-sealed-evidence-v2",
                "origin": result["origin"],
            },
            "expected": "Apply the original reviewed criterion and 5/2/0 anchors; private reference access is not granted by this projection",
            "observed": "Inspect the sealed recommendation, award and evidence custody",
            "evidence": evidence,
            "source": {
                key: source_task[key] for key in ("task_id", "task_version", "payload_sha256")
            }
            if source_task
            else captured.get("source_identity", {}),
            "evidence_contract": {
                "trial_id": captured["trial_id"],
                "generation": captured["generation"],
                "state_sha256": result["state_sha256"],
                "events_sha256": result["events_sha256"],
                "gates": {
                    key: result[key]
                    for key in ("critical_failures", "decision_correctness", "mandatory_conditions")
                },
            },
        }
        register_target(c, project, run, str(cell["id"]) + ":" + criterion, content)
    from anvil.diagnostic_producers import kyc as diagnostic_kyc

    diagnostic_kyc(
        c,
        project,
        run,
        cell,
        diagnostic_task,
        evidence,
        source_resolved=source_task is not None,
        preparation=scope_snapshot,
    )


def latest_assessments(history):
    latest = {}
    for row in history:
        if row["kind"] == "assessment":
            latest[str(row["created_by"])] = row
    return list(latest.values())


def expert_for(history):
    latest = latest_assessments(history)
    if not latest:
        return None, False
    values = {
        (
            x["content"]["status"],
            x["content"].get("award"),
            digest(x["content"].get("measurements")),
        )
        for x in latest
    }
    if len(values) == 1:
        return latest[-1], False
    current_ids = {str(x["id"]) for x in latest}
    resolutions = [
        x
        for x in history
        if x["kind"] == "resolution" and set(x["content"]["review_ids"]) == current_ids
    ]
    return (resolutions[-1], False) if resolutions else (None, True)


def public_review(row):
    if row is None:
        return None
    return row["content"] | {
        "id": str(row["id"]),
        "reviewer": row.get("reviewer", str(row["created_by"])),
        "reviewer_id": str(row["created_by"]),
        "created_at": row["created_at"],
        "revision": row["revision"],
        "origin": "human",
    }


def comparable(item):
    expert, automated = item.get("expert"), item["automated"]
    if not expert or expert["status"] != "scored":
        return False
    if item["official"]:
        return expert.get("award") is not None and automated.get("award") is not None
    human, original = expert.get("measurements"), automated.get("measurements")
    if not human or not original or set(human) != set(original):
        return False
    declared = item["scale"].get("measures")
    if declared and set(human) != set(declared):
        return False
    return all(
        human[k].get("kind") == original[k].get("kind")
        and (
            human[k]["kind"] == "count"
            or human[k].get("denominator") == original[k].get("denominator")
        )
        for k in human
    )


def same_award(item):
    return (
        item["expert"].get("award") == item["automated"].get("award")
        if item["official"]
        else item["expert"].get("measurements") == item["automated"].get("measurements")
    )


def coverage(items):
    eligible = [x for x in items if x["applicability"] != "not_applicable"]
    assessed = [x for x in eligible if x.get("expert") is not None]
    paired = [x for x in assessed if comparable(x)]
    result = {
        "eligible": len(eligible),
        "assessed": len(assessed),
        "comparable": len(paired),
        "comment_only": sum(x["expert"]["status"] == "comment_only" for x in assessed),
        "unscored": sum(x["expert"]["status"] == "unscored" for x in assessed),
        "not_applicable": sum(
            x["applicability"] == "not_applicable"
            or (x.get("expert") or {}).get("status") == "not_applicable"
            for x in items
        ),
        "applicability_unknown": sum(
            x["applicability"] not in {"applicable", "required", "not_applicable"} for x in items
        ),
        "disputed": sum(x.get("disputed", False) for x in eligible),
        "agrees": sum(same_award(x) for x in paired),
        "differs": sum(not same_award(x) for x in paired),
    }
    diagnostics = [x for x in eligible if not x["official"] and x["scale"].get("measures")]
    if diagnostics:

        def measured(item, kind):
            values = (item.get(kind) or {}).get("measurements") or {}
            return {
                key
                for key, spec in item["scale"]["measures"].items()
                if isinstance(values.get(key), dict) and values[key].get("kind") == spec["kind"]
            }

        result["diagnostic_components"] = {
            "required": sum(len(x["scale"]["measures"]) for x in diagnostics),
            "automated_measured": sum(len(measured(x, "automated")) for x in diagnostics),
            "expert_measured": sum(len(measured(x, "expert")) for x in diagnostics),
            "fully_measured_targets": sum(
                measured(x, "automated") == set(x["scale"]["measures"]) for x in diagnostics
            ),
            "fully_reviewed_targets": sum(
                measured(x, "expert") == set(x["scale"]["measures"]) for x in diagnostics
            ),
            "comparable_targets": sum(comparable(x) for x in diagnostics),
        }
    return result


def model_comparisons(items, expected_scope=None):
    """Matched sample only; diagnostic awards do not add official rubric points."""
    groups = defaultdict(list)
    for item in items:
        groups[item["model_key"]].append(item)
    result = []
    for model, rows in sorted(groups.items()):
        required = [x for x in rows if x["official"] and x["applicability"] != "not_applicable"]
        paired = [
            x
            for x in required
            if x["expert"]
            and x["expert"]["status"] == "scored"
            and x["automated"]["award"] is not None
        ]

        def percentage(selected, kind):
            if not selected:
                return None
            denominator = sum(x["weight"] for x in selected)
            return (
                100
                * sum(x["weight"] * x[kind]["award"] / x["scale"]["maximum"] for x in selected)
                / denominator
                if denominator
                else None
            )

        full = bool(required) and all(
            x["expert"]
            and x["expert"]["status"] == "scored"
            and x["applicability"] in {"applicable", "required"}
            for x in required
        )
        episodes = defaultdict(list)
        for row in rows:
            if not row["official"]:
                continue
            episodes[(row.get("case_id"), row.get("repetition"))].append(row)
        scope = expected_scope or {}
        expected_criteria = set(scope.get("criterion_ids", []))
        declared = scope.get("episodes", [])
        expected_episodes = {(episode["case_id"], episode["repetition"]) for episode in declared}
        full = (
            full
            and model in scope.get("model_keys", [])
            and bool(expected_criteria)
            and bool(expected_episodes)
            and len(expected_episodes) == len(declared)
            and set(episodes) == expected_episodes
            and len(episodes) == scope.get("episodes_per_model")
            and all(
                len(values) == len(expected_criteria)
                and {x["criterion_id"] for x in values} == expected_criteria
                for values in episodes.values()
            )
        )
        result.append(
            {
                "model_key": model,
                "coverage": coverage(rows),
                "matched_generated_score": percentage(paired, "automated"),
                "matched_expert_score": percentage(paired, "expert"),
                "full_expert_score": percentage(required, "expert") if full else None,
                "official_gates_unchanged": True,
            }
        )
    return result


def projection(c, project, run, roles):
    require_reader(roles)
    execution = one(
        c,
        "SELECT * FROM anvil.expert_review_executions WHERE project_id=%s AND run_id=%s",
        (project, run),
    )
    if not execution:
        raise HTTPException(404, "No sealed, reviewable result projection for this execution")
    targets = c.execute(
        "SELECT * FROM anvil.expert_review_targets WHERE project_id=%s AND run_id=%s ORDER BY target_key,id LIMIT 20001",
        (project, run),
    ).fetchall()
    if len(targets) > 20000:
        raise HTTPException(
            422,
            "Review projection exceeds supported snapshot capacity; no evidence was silently omitted",
        )
    reviews = c.execute(
        "SELECT r.*,u.name AS reviewer FROM anvil.expert_result_reviews r JOIN anvil.users u ON u.id=r.created_by WHERE r.project_id=%s AND r.run_id=%s ORDER BY r.created_at,r.id",
        (project, run),
    ).fetchall()
    revision = digest(
        {
            "snapshot": execution["snapshot_sha256"],
            "targets": [(str(x["id"]), x["content_sha256"]) for x in targets],
            "reviews": [str(x["id"]) for x in reviews],
        }
    )
    by_target = defaultdict(list)
    for row in reviews:
        by_target[str(row["target_id"])].append(row)
    items = []
    for row in targets:
        history = by_target[str(row["id"])]
        expert, disputed = expert_for(history)
        diagnoses = [x for x in history if x["kind"] == "diagnosis"]
        items.append(
            row["content"]
            | {
                "id": str(row["id"]),
                "expert": public_review(expert),
                "disputed": disputed,
                "expert_assessments": [public_review(x) for x in latest_assessments(history)],
                "diagnosis": public_review(diagnoses[-1]) if diagnoses else None,
                "diagnoses": [public_review(x) for x in diagnoses],
                "history": [
                    {
                        "id": str(x["id"]),
                        "kind": x["kind"],
                        "reviewer": x["reviewer"],
                        "created_at": x["created_at"],
                        "summary": x["content"]["rationale"],
                    }
                    for x in history
                ],
                "correction_flags": [
                    public_review(x) for x in history if x["kind"] == "source_correction"
                ],
            }
        )
    comparisons = model_comparisons(items, execution["expected_scope"])
    return {
        "run_id": str(run),
        "snapshot_sha256": execution["snapshot_sha256"],
        "review_revision": revision,
        "origin": execution["origin"],
        "permissions": permissions(set(roles)),
        "items": items,
        "coverage": coverage(items),
        "model_comparisons": comparisons,
        "full_expert_score": comparisons[0]["full_expert_score"] if len(comparisons) == 1 else None,
        "gates": execution["gates"],
        "expected_scope": execution["expected_scope"],
        "official_gates_unchanged": True,
        "stage_2": "awaiting_expert_review"
        if not reviews
        else "disputed"
        if any(x["disputed"] for x in items)
        else "expert_assessments_available",
        "paid_dispatch_authorized": False,
    }


def write(c, project, run, item_id, user, roles, body, kind):
    needed = "rl_diagnosis" if kind == "diagnosis" else "sme_review"
    if not permissions(set(roles))[needed]:
        raise HTTPException(403, "Explicit SME review or RL engineering duty required")
    # Serialize all run reviews. The transaction also holds membership row locks
    # so revocation cannot race the authorization-to-insert boundary.
    c.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("expert-review:" + str(run),)
    )
    c.execute("SELECT anvil.lock_result_reviewer(%s)", (project,))
    rows = c.execute(
        "SELECT m.role FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active",
        (project, user),
    ).fetchall()
    roles = {x["role"] for x in rows}
    if not permissions(roles)[needed]:
        raise HTTPException(403, "Review assignment is no longer active")
    current = projection(c, project, run, roles)
    if (
        current["snapshot_sha256"] != body.snapshot_sha256
        or current["review_revision"] != body.expected_review_revision
    ):
        raise HTTPException(409, "Review or execution snapshot changed; reload before saving")
    item = next((x for x in current["items"] if x["id"] == str(item_id)), None)
    if not item:
        raise HTTPException(404, "Review target not found in this execution")
    if set(body.evidence_ids) - {x["id"] for x in item["evidence"]}:
        raise HTTPException(422, "Use authorized evidence from this exact target")
    if (
        isinstance(body, Assess)
        and body.award is not None
        and body.award not in item["scale"]["levels"]
    ):
        raise HTTPException(422, "Award must use the bound native scale")
    if isinstance(body, Assess) and body.status == "scored":
        if item["official"] and body.measurements:
            raise HTTPException(422, "Official criterion uses native points, not diagnostic ratios")
        if not item["official"]:
            allowed = item["scale"].get("measures", {})
            if (
                body.award is not None
                or not body.measurements
                or set(body.measurements) - set(allowed)
                or any(
                    value.kind != allowed[key]["kind"] for key, value in body.measurements.items()
                )
            ):
                raise HTTPException(
                    422, "Use only the exact diagnostic measures and units bound to this target"
                )
    if isinstance(body, Resolve):
        if not item["disputed"] or {str(x) for x in body.review_ids} != {
            x["id"] for x in item["expert_assessments"]
        }:
            raise HTTPException(409, "Resolution must cite every current conflicting assessment")
    content = body.model_dump(mode="json", exclude={"snapshot_sha256", "expected_review_revision"})
    if isinstance(body, Correction):
        source = item.get("source") or {}
        exact = all(source.get(k) for k in ("task_id", "task_version", "payload_sha256"))
        content |= {
            "source": source,
            "source_status": "exact_revision" if exact else "unresolved_source",
            "owner": "anvil"
            if body.issue == "evaluator"
            else "evidence_owner"
            if body.issue == "missing_evidence"
            else "praxis",
            "sent_to_praxis": False,
            "publication_or_rescore": False,
        }
    revision = one(
        c,
        "SELECT coalesce(max(revision),0)+1 AS value FROM anvil.expert_result_reviews WHERE target_id=%s AND kind=%s AND created_by=%s",
        (item_id, kind, user),
    )["value"]
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.expert_result_reviews(id,project_id,run_id,target_id,kind,revision,content,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (identifier, project, run, item_id, kind, revision, Jsonb(content), user),
    )
    audit(
        c,
        project,
        user,
        "result.human_" + kind,
        identifier,
        {"run_id": str(run), "target_id": str(item_id), "revision": revision},
    )
    return projection(c, project, run, roles)


def render_pdf(snapshot):
    """Same frozen JSON as the API; no fresh queries or score recalculation."""
    from xml.sax.saxutils import escape

    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    output, styles = io.BytesIO(), getSampleStyleSheet()
    story = []

    def line(text):
        story.append(Paragraph(escape(str(text)), styles["Normal"]))
        story.append(Spacer(1, 5))

    line("ADIForge — Workflow Metrics / Agent Performance")
    line("Execution " + str(snapshot["run_id"]))
    line("Frozen review revision " + snapshot["review_revision"])
    line("Snapshot " + str(snapshot["id"]) + " · " + str(snapshot["created_at"]))
    content = snapshot["content"]
    line("Frozen content SHA-256: " + str(snapshot["content_sha256"]))
    line("Execution manifest SHA-256: " + str(content.get("snapshot_sha256")))
    line("Sample: " + content["sample_selection"])
    line("Stage 1: ADIForge generated awards. Stage 2: " + content["stage_2"])
    line("Coverage: " + str(content["coverage"]))
    line("Full expert score: " + str(content.get("full_expert_score")))
    line("Expected native scope: " + json.dumps(content.get("expected_scope", {}), sort_keys=True))
    from anvil.report_visuals import matched_model_chart

    chart = matched_model_chart(content.get("model_comparisons", []))
    if chart is not None:
        line("Workflow Metrics — matched model score comparison")
        line("Teal: ADIForge generated. Purple: Human / Expert reviewed. Scale: 0–100.")
        line(
            "Each model's two bars use its same reviewed official rubric observations. "
            "Different model samples are not directly comparable. Missing values stay unscored. "
            "Diagnostic measures add no official points; critical and safety gates remain in force."
        )
        story.append(chart)
    for comparison in content.get("model_comparisons", []):
        line("Model comparison: " + str(comparison["model_key"]))
        line("Matched generated score: " + str(comparison["matched_generated_score"]))
        line("Matched expert score: " + str(comparison["matched_expert_score"]))
        line("Full expert score: " + str(comparison["full_expert_score"]))
        line("Matched comparison coverage: " + str(comparison["coverage"]))
        line("Official gates unchanged: " + str(comparison["official_gates_unchanged"]))
    line("Official critical and safety gates remain unchanged: " + str(content["gates"]))
    for item in content["items"]:
        line(
            f"{item['case_id']} | {item['model_key']} | repetition {item['repetition']} | {item['role']} | {item.get('criterion_id') or item.get('skill_id')}"
        )
        design = item.get("automated", {}).get("judge_design")
        if isinstance(design, dict):
            line("Evaluator design: " + str(design.get("selection", "Unknown")))
            model = design.get("model") or {}
            line(
                "Judge model: "
                + str(model.get("provider", "Unknown"))
                + " / "
                + str(model.get("model_id", "Unknown"))
            )
            line("Judge binding SHA256: " + str(design.get("judge_model_binding_sha256")))
            line("Candidate binding SHA256: " + str(design.get("candidate_model_binding_sha256")))
            overlap = design.get("same_model_as_candidate")
            line("Judge/candidate same model: " + ("Unknown" if overlap is None else str(overlap)))
            line("Calibration SHA256: " + str(item.get("automated", {}).get("calibration_sha256")))
            line(str(design.get("limitation", "Evaluator comparison coverage must be inspected.")))
        if item.get("skill_name"):
            line(
                "Skill: "
                + item["skill_name"]
                + " · Capability association: "
                + str(item.get("capability_association"))
            )
            line(
                "Design step: "
                + str(item.get("design_step"))
                + " · Authored mapping: "
                + str(item.get("step_status"))
            )
            line(
                "Design role: "
                + str(item.get("design_role"))
                + " · Role mapping: "
                + str(item.get("role_mapping_status"))
            )
            line("Design metadata SHA-256: " + str(item.get("design_metadata_sha256")))
        if item.get("authored_steps"):
            line(
                "Frozen authored step mappings: "
                + json.dumps(item["authored_steps"], sort_keys=True)
            )
            line("Skill mapping SHA-256: " + str(item.get("skill_mapping_sha256")))
        line("Native target weight: " + str(item.get("weight")))
        source = item.get("source") or {}
        line(
            "Source task: "
            + str(source.get("task_id"))
            + " · Version: "
            + str(source.get("task_version"))
        )
        line("Source payload SHA-256: " + str(source.get("payload_sha256")))
        contract = item.get("evidence_contract") or {}
        if contract.get("normalizer_scope"):
            line("Measurement scope: " + str(contract["normalizer_scope"]))
        if "gates" in contract:
            line("Observation gates: " + json.dumps(contract["gates"], sort_keys=True))
        if "critical_failures" in contract:
            line(
                "Observation critical failures: "
                + json.dumps(contract["critical_failures"], sort_keys=True)
            )
        line("Generated: " + str(item["automated"]) + " · Scale: " + str(item["scale"]))
        line("Expert: " + str(item["expert"]) + " · Disputed: " + str(item["disputed"]))
        line("Engineering: " + str(item["diagnosis"]))
        for evidence in item["evidence"]:
            line(
                "Evidence "
                + evidence["id"]
                + " · "
                + evidence.get("title", "")
                + " · "
                + str(evidence.get("sha256"))
            )
    SimpleDocTemplate(output).build(story)
    return output.getvalue()


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/benchmark")

    @router.get("/review-runs")
    def review_runs(
        project: UUID,
        request: Request,
        limit: int = Query(30, ge=1, le=100),
        after: UUID | None = None,
    ):
        with context(request, project) as (c, user, roles):
            require_reader(roles)
            rows = c.execute(
                "SELECT run_id,kind,snapshot_sha256,origin,created_at FROM anvil.expert_review_executions WHERE project_id=%s AND (%s::uuid IS NULL OR run_id>%s) ORDER BY run_id LIMIT %s",
                (project, after, after, limit + 1),
            ).fetchall()
            return wrap(
                {
                    "items": rows[:limit],
                    "next_cursor": str(rows[limit - 1]["run_id"]) if len(rows) > limit else None,
                    "permissions": permissions(set(roles)),
                },
                request,
            )

    @router.put("/expert-review-membership")
    def assign(project: UUID, body: Assign, request: Request):
        with context(request, project) as (c, user, roles):
            if "admin" not in roles:
                raise HTTPException(403, "Only the project Admin may assign SME review")

            def change():
                c.execute(
                    "SELECT anvil.set_sme_result_membership(%s,%s,%s)",
                    (project, body.user_id, body.active),
                )
                audit(
                    c,
                    project,
                    user,
                    "result.sme_membership_changed",
                    str(body.user_id),
                    {"active": body.active},
                )
                return {
                    "user_id": str(body.user_id),
                    "role": "sme-reviewer",
                    "active": body.active,
                    "execution_privileges_added": False,
                }

            return wrap(
                idempotent(c, project, user, request, body.model_dump(mode="json"), change), request
            )

    @router.get("/runs/{run}/expert-review")
    def get(project: UUID, run: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            return wrap(projection(c, project, run, roles), request)

    @router.get("/runs/{run}/expert-review/{item}/evidence/{evidence}")
    def evidence(project: UUID, run: UUID, item: UUID, evidence: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            require_reader(roles)
            target = one(
                c,
                "SELECT content FROM anvil.expert_review_targets WHERE project_id=%s AND run_id=%s AND id=%s",
                (project, run, item),
            )
            if not target or str(evidence) not in {x["id"] for x in target["content"]["evidence"]}:
                raise HTTPException(404, "Evidence not assigned to this review target")
            row = one(
                c,
                "SELECT * FROM anvil.expert_review_evidence WHERE project_id=%s AND run_id=%s AND id=%s",
                (project, run, evidence),
            )
            if not row or digest(row["content"]) != row["sha256"]:
                raise HTTPException(409, "Review evidence missing or integrity mismatch")
            return wrap(row, request)

    @router.post("/runs/{run}/expert-review/{item}/assess")
    def assess(project: UUID, run: UUID, item: UUID, body: Assess, request: Request):
        with context(request, project) as (c, user, roles):
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body.model_dump(mode="json"),
                    lambda: write(c, project, run, item, user, roles, body, "assessment"),
                ),
                request,
            )

    @router.post("/runs/{run}/expert-review/{item}/diagnose")
    def diagnose(project: UUID, run: UUID, item: UUID, body: Diagnose, request: Request):
        with context(request, project) as (c, user, roles):
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body.model_dump(mode="json"),
                    lambda: write(c, project, run, item, user, roles, body, "diagnosis"),
                ),
                request,
            )

    @router.post("/runs/{run}/expert-review/{item}/resolve")
    def resolve(project: UUID, run: UUID, item: UUID, body: Resolve, request: Request):
        with context(request, project) as (c, user, roles):
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body.model_dump(mode="json"),
                    lambda: write(c, project, run, item, user, roles, body, "resolution"),
                ),
                request,
            )

    @router.post("/runs/{run}/expert-review/{item}/correction")
    def correction(project: UUID, run: UUID, item: UUID, body: Correction, request: Request):
        with context(request, project) as (c, user, roles):
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body.model_dump(mode="json"),
                    lambda: write(c, project, run, item, user, roles, body, "source_correction"),
                ),
                request,
            )

    @router.post("/runs/{run}/report-snapshots")
    def freeze(project: UUID, run: UUID, body: Freeze, request: Request):
        with context(request, project) as (c, user, roles):

            def create():
                c.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    ("expert-review:" + str(run),),
                )
                data = projection(c, project, run, roles)
                if (
                    data["review_revision"] != body.expected_review_revision
                    or data["snapshot_sha256"] != body.snapshot_sha256
                ):
                    raise HTTPException(409, "Report or execution changed; reload before freezing")
                data.pop("permissions")
                data["sample_selection"] = body.sample_selection
                value = jsonable_encoder(data)
                identifier = uid()
                c.execute(
                    "INSERT INTO anvil.expert_report_snapshots(id,project_id,run_id,review_revision,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (
                        identifier,
                        project,
                        run,
                        data["review_revision"],
                        Jsonb(value),
                        digest(value),
                        user,
                    ),
                )
                audit(
                    c,
                    project,
                    user,
                    "result.report_snapshot_frozen",
                    identifier,
                    {"review_revision": data["review_revision"]},
                )
                return one(
                    c, "SELECT * FROM anvil.expert_report_snapshots WHERE id=%s", (identifier,)
                )

            return wrap(
                idempotent(c, project, user, request, body.model_dump(mode="json"), create), request
            )

    @router.get("/runs/{run}/report-snapshots/{snapshot}")
    def snapshot(
        project: UUID,
        run: UUID,
        snapshot: UUID,
        request: Request,
        format: Literal["json", "pdf"] = Query("json"),
    ):
        with context(request, project) as (c, user, roles):
            require_reader(roles)
            row = one(
                c,
                "SELECT * FROM anvil.expert_report_snapshots WHERE id=%s AND project_id=%s AND run_id=%s",
                (snapshot, project, run),
            )
            if not row:
                raise HTTPException(404, "Report snapshot not found in this execution")
            if digest(row["content"]) != row["content_sha256"]:
                raise HTTPException(409, "Report snapshot integrity mismatch")
            if format == "pdf":
                return Response(
                    render_pdf(row),
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": 'attachment; filename="anvil-result-review.pdf"',
                        "X-Anvil-Report-SHA256": row["content_sha256"],
                    },
                )
            return wrap(row, request)

    return router
