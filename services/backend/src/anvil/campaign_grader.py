"""Separate private campaign grader and real47-target report producer.

Current deterministic findings do not become guessed0–4 semantic awards.
Missing calibrated criterion/diagnostic evaluations remain explicit Anvil gaps.
No candidate/API/scheduler can read the private reference store or create grades.
"""

from fastapi.encoders import jsonable_encoder

from anvil.campaign_effects import SCOPE as TOOL_EFFECT_SCOPE
from anvil.campaign_effects import load as load_tool_effects
from anvil.campaign_effects import observations as tool_effect_observations
from anvil.campaign_ordinal import collect as collect_ordinal
from anvil.campaign_reference_bindings import bound as bound_reference
from anvil.db import Jsonb, digest, one
from anvil.diagnostic_producers import register as register_diagnostics
from anvil.expert_reviews import register_evidence, register_execution, register_target
from anvil.golden_targets import design_metadata, requirements
from anvil.marketing_task2_contract import score
from anvil.marketing_task2_evaluators import inspect_capture
from anvil.praxis_generic_contract import digest as custody_digest
from anvil.skill_step_bindings import mapped, public_mapping


def original_rubric(task):
    native = task.get("rubric", {}).get("native_contract") or {}
    expected = {
        row["id"]: row["maximum_contribution"] for row in requirements(task) if row["official"]
    }
    actual = {
        criterion["id"]: criterion.get("points")
        for criterion in task.get("rubric", {}).get("criteria", [])
    }
    if not expected or actual != expected or len(actual) != len(task["rubric"]["criteria"]):
        raise ValueError("Exact original campaign criterion identities and weights required")
    return {
        "formula": native["formula"],
        "domains": {
            group: {
                "weight": weight,
                "criteria": {
                    key.split(".", 1)[1]: points
                    for key, points in actual.items()
                    if key.startswith(group + ".")
                },
            }
            for group, weight in native["groups"].items()
        },
    }


def scope(snapshot, task, kind):
    prepared = snapshot["preparation"] if kind == "workspace_group" else snapshot
    repeats = (
        range(1, prepared.get("trials_per_model", 0) + 1)
        if kind == "workspace_group"
        else range(prepared.get("repetitions", 0))
    )
    return {
        "model_keys": [str(model["id"]) for model in prepared.get("models", [])],
        "criterion_ids": [row["id"] for row in requirements(task) if row["official"]],
        "episodes": [
            {"case_id": assignment["case_id"], "repetition": repeat}
            for assignment in prepared.get("case_assignments", [])
            for repeat in repeats
        ],
        "episodes_per_model": len(prepared.get("case_assignments", [])) * len(repeats),
        "scope_origin": "frozen_execution_manifest",
    }


def grade_one(connections, project):
    with connections() as c:
        semantic_runtime = one(
            c,
            "SELECT to_regprocedure('marketing_runtime.campaign_grade_ready(uuid)') AS function",
        )
        ready_clause = (
            " AND marketing_runtime.campaign_grade_ready(id)"
            if semantic_runtime and semantic_runtime["function"]
            else ""
        )
        job = one(
            c,
            "SELECT * FROM marketing_runtime.grading_jobs WHERE project_id=%s AND state='queued'"
            + ready_clause
            + " ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1",
            (project,),
        )
        if not job:
            return None
        sealed = one(
            c,
            "SELECT * FROM marketing_runtime.seals WHERE project_id=%s AND episode_id=%s AND generation=%s",
            (project, job["episode_id"], job["generation"]),
        )
        if not sealed or custody_digest(sealed["capture"]) != sealed["capture_sha256"]:
            raise ValueError("Exact immutable campaign seal required")
        metadata = one(
            c,
            "SELECT case_id,dataset_id,dataset_version,dataset_sha256,snapshot_sha256 FROM marketing_runtime.episodes WHERE project_id=%s AND id=%s",
            (project, job["episode_id"]),
        )
        source = one(
            c,
            "SELECT content,content_sha256 FROM anvil.benchmark_task_groups WHERE project_id=%s AND id=%s",
            (project, job["task_group_id"]),
        )
        if not source or digest(source["content"]) != source["content_sha256"]:
            raise ValueError("Frozen campaign task source required")
        dataset = source["content"].get("case_dataset") or {}
        if any(
            dataset.get(key) != metadata[field]
            for key, field in (
                ("id", "dataset_id"),
                ("version", "dataset_version"),
                ("sha256", "dataset_sha256"),
            )
        ):
            raise ValueError("Sealed campaign dataset differs from exact imported source")
        task = next(
            (
                task
                for task in source["content"].get("tasks", [])
                if task["task_id"] == job["task_id"]
            ),
            None,
        )
        if task is None or len(requirements(task)) != 47:
            raise ValueError("Exact published campaign task and47 target contracts required")
        if job["kind"] == "workspace_group":
            execution = one(
                c,
                "SELECT snapshot,subject_hash AS snapshot_sha256 FROM anvil.workspace_execution_groups WHERE project_id=%s AND id=%s",
                (project, job["run_id"]),
            )
        else:
            execution = one(
                c,
                "SELECT snapshot,snapshot_sha256 FROM anvil.benchmark_runs WHERE project_id=%s AND id=%s",
                (project, job["run_id"]),
            )
        if not execution:
            raise ValueError("Persisted campaign execution identity required")
        prepared = (
            execution["snapshot"]["preparation"]
            if job["kind"] == "workspace_group"
            else execution["snapshot"]
        )
        bound_group = (
            (prepared.get("project_binding") or {}).get("task_group_id")
            if job["kind"] == "workspace_group"
            else prepared.get("task_group_id")
        )
        if str(bound_group) != str(job["task_group_id"]):
            raise ValueError("Campaign execution belongs to another frozen task source")
        assignment = next(
            (
                row
                for row in prepared.get("case_assignments", [])
                if row["case_id"] == metadata["case_id"]
            ),
            None,
        )
        if not assignment or assignment.get("snapshot_sha256") != metadata["snapshot_sha256"]:
            raise ValueError("Campaign case snapshot differs from frozen execution assignment")
        expected = scope(execution["snapshot"], task, job["kind"])
        if (
            job["model_key"] not in expected["model_keys"]
            or {"case_id": metadata["case_id"], "repetition": job["repetition"]}
            not in expected["episodes"]
        ):
            raise ValueError("Campaign case/model/repetition not in frozen scope")
        reference_binding = bound_reference(
            prepared, task, metadata["case_id"], metadata["snapshot_sha256"]
        )
        reference = (
            one(
                c,
                "SELECT content,content_sha256 FROM campaign_private.references WHERE project_id=%s AND id=%s AND content_sha256=%s AND task_id=%s AND task_version=%s AND payload_sha256=%s AND case_id=%s AND case_sha256=%s",
                (
                    project,
                    reference_binding["reference_id"],
                    reference_binding["reference_sha256"],
                    task["task_id"],
                    task["task_version"],
                    task["payload_sha256"],
                    metadata["case_id"],
                    metadata["snapshot_sha256"],
                ),
            )
            if reference_binding["reference_id"]
            else None
        )
        if reference_binding["reference_id"] and not reference:
            raise ValueError("Frozen campaign private reference revision unavailable")
        if reference and digest(reference["content"]) != reference["content_sha256"]:
            raise ValueError("Campaign private reference custody mismatch")
        reference = reference["content"] if reference else {}
        from anvil.campaign_semantic_collect import collect as collect_semantic

        semantic = collect_semantic(c, project, job, prepared, task, sealed, reference, metadata)
        if semantic["status"] == "pending":
            # Leaving the context commits newly queued evaluator jobs. No
            # immutable execution, target or result has been registered yet.
            return {"status": "pending", "job_id": str(job["id"]), "reason": semantic["reason"]}
        native = original_rubric(task)
        ordinal = collect_ordinal(c, project, prepared, task, sealed, reference, metadata)
        ordinal.update(semantic["awards"])
        levels = {identifier: result["award"] for identifier, result in ordinal.items()}
        deterministic = inspect_capture(sealed["capture"], budget_minor=20000000)
        aggregate = score(
            native,
            levels,
            deterministic["observed_critical_failures"],
            outputs_or_correct_hold=None,
        )
        aggregate.update(
            output_gate=None,
            output_gate_status="workflow_deliverables_or_justified_hold_not_qualified",
        )
        register_execution(
            c,
            project,
            job["run_id"],
            execution["snapshot_sha256"],
            "native_campaign_sealed_evidence",
            {
                "evaluation": "Original campaign gates retained per episode; diagnostic measures add no points"
            },
            kind=job["kind"],
            expected_scope=expected,
        )
        evidence = [
            register_evidence(
                c,
                project,
                job["run_id"],
                "Sealed campaign episode custody",
                {
                    "episode_id": str(job["episode_id"]),
                    "generation": job["generation"],
                    "case_id": metadata["case_id"],
                    "capture_sha256": sealed["capture_sha256"],
                    "dataset_sha256": metadata["dataset_sha256"],
                    "deterministic_checks": deterministic,
                    "model_performance": False,
                },
            )
        ]
        cell = {
            "id": str(job["id"]),
            "model_key": job["model_key"],
            "repetition": job["repetition"],
            "capture": {"origin": "sealed_campaign_origin_not_model_qualified"},
        }
        descriptors = mapped(requirements(task), prepared)
        for row in descriptors:
            if not row["official"]:
                continue
            register_target(
                c,
                project,
                job["run_id"],
                str(job["id"]) + ":" + row["id"],
                {
                    **design_metadata("marketing", row["id"]),
                    **public_mapping(row),
                    "case_id": metadata["case_id"],
                    "model_key": job["model_key"],
                    "repetition": job["repetition"],
                    "role": row["role"],
                    "step": row["step"],
                    "skill_id": None,
                    "skill": row["skill_name"],
                    "criterion_id": row["id"],
                    "scale": row["scale"],
                    "weight": row["maximum_contribution"],
                    "official": True,
                    "applicability": "required",
                    "automated": {
                        **ordinal[row["id"]],
                        "owner": "anvil",
                    },
                    "expected": row["evidence_contract"],
                    "observed": "Exact sealed episode; subjective levels are not inferred from Boolean checks",
                    "evidence": evidence,
                    "source": {
                        key: task[key] for key in ("task_id", "task_version", "payload_sha256")
                    },
                    "evidence_contract": {
                        "capture_sha256": sealed["capture_sha256"],
                        "critical_failures": aggregate["critical_failures"],
                        "reference_binding": reference_binding,
                    },
                },
            )
        context = {
            "task_id": task["task_id"],
            "revision": task["task_version"],
            "payload_sha256": task["payload_sha256"],
            "case_id": metadata["case_id"],
            "snapshot_sha256": metadata["snapshot_sha256"],
        }
        receipts = c.execute(
            "SELECT * FROM marketing_runtime.tool_receipts WHERE project_id=%s AND episode_id=%s AND generation=%s ORDER BY created_at,id",
            (project, job["episode_id"], job["generation"]),
        ).fetchall()
        tool_effects = load_tool_effects(c, project, job["episode_id"], job["generation"])
        from anvil.diagnostic_projection import SUPPORTED, campaign_sources, normalize

        observed_sources = (
            campaign_sources(sealed["capture"], receipts)
            if any(
                isinstance(value, dict) and value.get("observation_projection")
                for value in (reference.get("diagnostic_references") or {}).values()
            )
            else []
        )
        actuals = {}
        source_digest = digest(
            {
                "capture_sha256": sealed["capture_sha256"],
                "tool_receipts": jsonable_encoder(receipts),
                "private_tool_effect_custody": {
                    key: {
                        field: str(row[field])
                        for field in (
                            "post_state_sha256",
                            "full_state_sha256",
                            "arguments_sha256",
                            "intent_job",
                            "intent_lease",
                            "linked_job",
                            "linked_lease",
                            "episode_id",
                            "generation",
                            "capture_episode",
                            "capture_generation",
                        )
                    }
                    for key, row in tool_effects.items()
                },
            }
        )
        for descriptor in descriptors:
            if descriptor["official"]:
                continue
            invocations, available = [], False
            if descriptor["id"].startswith("M.TOOL."):
                invocations, available = tool_effect_observations(
                    receipts,
                    tool_effects,
                    descriptor["role"],
                    (reference.get("diagnostic_references") or {}).get(descriptor["id"]),
                )
            projection = (
                normalize(
                    descriptor["id"],
                    context | {"role": descriptor["role"]},
                    (reference.get("diagnostic_references") or {}).get(descriptor["id"]),
                    observed_sources,
                    # A seal proves bytes, not a completed role workflow.
                    # The actual reconstructed role-closure receipt must be
                    # connected before Marketing projections can score.
                    complete_capture=False,
                )
                if not available and descriptor["id"] in SUPPORTED
                else None
            )
            if projection and projection["available"]:
                available = True
            actuals[descriptor["id"]] = {
                "execution_receipt_sha256": source_digest,
                "source_evidence_sha256": source_digest,
                "complete_capture": available,
                "normalizer_available": available,
                "context_sha256": digest(context | {"role": descriptor["role"]}),
                "observed_invocations": invocations,
                "observed_records": projection["records"] if projection else [],
                "invalid_record_count": projection["invalid_record_count"] if projection else 0,
                "normalizer_scope": projection["scope"] if projection else TOOL_EFFECT_SCOPE,
                "normalizer_gap": projection.get("reason") if projection else None,
                "observation_projection_sha256": projection.get("projection_sha256")
                if projection
                else None,
                "normalizer_source_sha256": projection.get("projection_source_sha256")
                if projection
                else None,
                "observed_source_refs": projection.get("observed_source_refs", [])
                if projection
                else [],
            }
        diagnostics = register_diagnostics(
            c,
            project,
            job["run_id"],
            cell,
            task,
            context,
            evidence,
            actuals,
            reference.get("diagnostic_references") or {},
            reference_metadata=reference_binding,
            preparation=prepared,
        )
        result = {
            "schema_version": "anvil.campaign-private-result.v1",
            "aggregate": aggregate,
            "diagnostics": diagnostics,
            "capture_sha256": sealed["capture_sha256"],
            "source_evidence_sha256": source_digest,
            "reference_binding": reference_binding,
            "grading_status": "unscored_qualification_gaps",
            "model_performance": False,
            # The grader cannot infer candidate billing from a sealed capture.
            # Retain observed evaluator calls without asserting absent spend.
            "paid_calls": True
            if any(row.get("dispatch_origin") == "provider" for row in semantic["awards"].values())
            else None,
            "semantic_total_provider_attempts": None,
            "semantic_completed_provider_result_jobs": len(
                {
                    row["semantic_job_id"]
                    for row in semantic["awards"].values()
                    if row.get("dispatch_origin") == "provider"
                }
            ),
        }
        c.execute(
            "INSERT INTO campaign_private.results(project_id,job_id,result,result_sha256) VALUES(%s,%s,%s,%s)",
            (project, job["id"], Jsonb(result), digest(result)),
        )
        c.execute(
            "UPDATE marketing_runtime.grading_jobs SET state='completed' WHERE id=%s", (job["id"],)
        )
        return result
