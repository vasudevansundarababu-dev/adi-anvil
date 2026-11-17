"""Private semantic awards, after current authority and exact sealed custody.

Pending evaluation never creates a final target. Private judge rationale remains
private; software-only transport tests never become model-performance awards.
"""

import os

from anvil.campaign_reference_bindings import bound
from anvil.campaign_semantic_contract import FixedBlueprint, parse_blueprint
from anvil.db import digest, one


def prepared_matches_binding(prepared, snapshot):
    return (
        prepared.get("semantic_judge_templates", []) == snapshot.get("semantic_judge_batches", [])
        and prepared.get("semantic_judge_model_support", {})
        == snapshot.get("semantic_judge_model_support", {})
        and prepared.get("skill_mapping_bindings", []) == snapshot.get("skill_mapping_bindings", [])
        and prepared.get("semantic_judge_models", {}) == snapshot.get("semantic_judge_models", {})
    )


def frozen_blueprint(spec, prepared, task, case, reference):
    """No case, model, reference or batch can inherit another one's binding."""
    frozen = prepared.get("project_binding") or {}
    if (
        str(spec.binding_id) != frozen.get("id")
        or spec.binding_snapshot_sha256 != frozen.get("snapshot_sha256")
        or any(
            getattr(spec, key) != task[key] for key in ("task_id", "task_version", "payload_sha256")
        )
        or spec.case_id != case["case_id"]
        or spec.case_snapshot_sha256 != case["snapshot_sha256"]
        or spec.source_reference_binding_sha256 != digest(reference)
    ):
        return False
    template = spec.model_dump(
        mode="json",
        exclude={
            "schema_version",
            "binding_id",
            "binding_snapshot_sha256",
            "model_binding_sha256",
            "candidate_model_binding_sha256",
        },
    ) | {
        "schema_version": "anvil.campaign-semantic-judge-template.v1",
        "model_selection": "candidate",
    }
    if isinstance(spec, FixedBlueprint):
        template.update(
            schema_version="anvil.campaign-semantic-judge-template.v2",
            model_selection="fixed",
            judge_model_binding_sha256=spec.model_binding_sha256,
        )
        saved = prepared.get("semantic_judge_models", {}).get(spec.model_binding_sha256)
        if (
            not isinstance(saved, dict)
            or digest(saved) != spec.model_binding_sha256
            or saved.get("id") != str(spec.judge_model_profile_id)
        ):
            return False
    support = prepared.get("semantic_judge_model_support") or {}
    return (
        template in prepared.get("semantic_judge_templates", [])
        and isinstance(support, dict)
        and isinstance(support.get(digest(template)), list)
        and spec.model_binding_sha256 in support[digest(template)]
    )


def public_awards(result, spec, *, judge_model=None, candidate_model=None):
    """Return observed awards without private prompts, rationale or anchors."""
    fixed = isinstance(spec, FixedBlueprint)
    candidate_sha = spec.candidate_model_binding_sha256 if fixed else spec.model_binding_sha256
    for model, expected in (
        (judge_model, spec.model_binding_sha256),
        (candidate_model, candidate_sha),
    ):
        if model is not None and (not isinstance(model, dict) or digest(model) != expected):
            raise ValueError("Report model labels must match exact frozen evaluator identities")
    same_model = True if not fixed else None
    if (
        fixed
        and judge_model
        and candidate_model
        and all(
            isinstance(model.get(key), str) and model[key]
            for model in (judge_model, candidate_model)
            for key in ("provider", "model_id")
        )
    ):
        same_model = all(
            judge_model[key] == candidate_model[key] for key in ("provider", "model_id")
        )
    design = {
        "selection": "fixed" if fixed else "candidate",
        "judge_model_binding_sha256": spec.model_binding_sha256,
        "candidate_model_binding_sha256": candidate_sha,
        "same_model_as_candidate": same_model,
        "model": {
            key: judge_model[key]
            for key in ("name", "provider", "model_id")
            if judge_model and isinstance(judge_model.get(key), str)
        },
        "limitation": "A fixed judge does not remove judge bias or replace calibration."
        if fixed
        else "The judge changes with the candidate; this is not a fixed-evaluator comparison.",
    }
    common = {
        "evaluator": spec.evaluator_version,
        "configuration_id": str(spec.configuration_id),
        "configuration_sha256": spec.configuration_sha256,
        "calibration_sha256": spec.calibration_sha256,
        "binding_id": str(spec.binding_id),
        "binding_sha256": spec.binding_snapshot_sha256,
        "semantic_job_id": result["job_id"],
        "result_sha256": result["result_sha256"],
        "dispatch_origin": result.get("dispatch_origin"),
        "human_calibration_established_by_software": False,
        "judge_design": design,
    }
    if result["status"] != "completed" or result.get("dispatch_origin") != "provider":
        return {
            key: common
            | {
                "award": None,
                "status": "unscored",
                "reason": "semantic_software_only_or_evaluator_failure",
            }
            for key in spec.criterion_ids
        }
    return {
        award["criterion_id"]: common
        | {
            "award": award["level"],
            "status": "scored" if award["level"] is not None else "unscored",
            "reason": "reviewed_native_anchor"
            if award["level"] is not None
            else "semantic_evidence_insufficient",
            "observed_evidence_refs": award["evidence_refs"],
        }
        for award in result["criteria"]
    }


def collect(c, project, job, prepared, task, sealed, reference, case):
    from anvil import campaign_semantic_custody as custody
    from anvil.campaign_semantic_runtime import VERSION, purpose_control, source_hash
    from anvil.evaluator_configurations import get
    from anvil.golden_targets import requirements

    frozen = prepared.get("project_binding") or {}

    def waiting(reason):
        return {"status": "pending", "awards": {}, "reason": reason}

    descriptors = {row["id"]: row for row in requirements(task) if row["official"]}
    task_targets = {row["target"] for row in descriptors.values()}
    records = prepared.get("native_semantic_bindings", [])
    # Preparation stores binding metadata under project_binding as well as its
    # frozen snapshot, so consult the actual persisted version below.
    binding = (
        one(
            c,
            "SELECT * FROM anvil.project_binding_versions WHERE project_id=%s AND id=%s",
            (project, frozen.get("id")),
        )
        if frozen.get("id")
        else None
    )
    snapshot = binding["snapshot"] if binding else {}
    if frozen.get("id") and not binding:
        return waiting("semantic_current_frozen_binding_required")
    records = [
        row
        for row in snapshot.get("native_semantic_bindings", records)
        if row["target"] in task_targets
    ]
    templates = [
        row
        for row in prepared.get("semantic_judge_templates", [])
        if all(row.get(key) == task[key] for key in ("task_id", "task_version", "payload_sha256"))
    ]
    if not records and not templates:
        return {"status": "not_configured", "awards": {}}

    release = os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256")
    if (
        not release
        or not binding
        or binding["snapshot_sha256"] != frozen.get("snapshot_sha256")
        or digest(snapshot) != binding["snapshot_sha256"]
        or not records
        or job["kind"] != "workspace_group"
        or not job.get("plan_id")
    ):
        return waiting("semantic_current_frozen_binding_required")
    if not prepared_matches_binding(prepared, snapshot):
        return waiting("semantic_preparation_differs_from_frozen_binding")
    available = one(
        c, "SELECT to_regprocedure('anvil.lock_native_ordinal_award(uuid,uuid)') AS function"
    )
    if not available or not available["function"]:
        return waiting("semantic_authority_runtime_required")
    qualification = one(
        c,
        "SELECT q.* FROM anvil.project_binding_qualifications q WHERE q.project_id=%s AND q.binding_id=%s AND q.release_sha256=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id) ORDER BY q.created_at DESC,q.id DESC LIMIT 1",
        (project, binding["id"], release),
    )
    if not qualification or digest(qualification["evidence"]) != qualification["evidence_sha256"]:
        return waiting("semantic_current_qualification_required")
    quotes = c.execute(
        "SELECT * FROM marketing_runtime.semantic_quotes WHERE project_id=%s AND group_id=%s AND plan_id=%s ORDER BY batch_index",
        (project, job["run_id"], job["plan_id"]),
    ).fetchall()
    if not quotes:
        return waiting("semantic_upfront_quote_required")
    mappings = {item["target"]: item for item in prepared.get("skill_mapping_bindings", [])}
    reference_identity = bound(prepared, task, case["case_id"], case["snapshot_sha256"])
    specs, covered = [], set()
    for quote in quotes:
        spec = parse_blueprint(quote["blueprint"])
        candidate_binding = None
        if isinstance(spec, FixedBlueprint):
            candidate = one(
                c,
                "SELECT marketing_runtime.semantic_candidate_binding(%s) AS binding",
                (job["id"],),
            )
            if (
                not candidate
                or not isinstance(candidate.get("binding"), dict)
                or digest(candidate["binding"]) != spec.candidate_model_binding_sha256
            ):
                return waiting("semantic_exact_separate_candidate_binding_required")
            candidate_binding = candidate["binding"]
        if digest(quote["blueprint"]) != quote["blueprint_sha256"] or not frozen_blueprint(
            spec, prepared, task, case, reference_identity
        ):
            raise ValueError("Semantic quote differs from the exact frozen binding")
        if covered.intersection(spec.criterion_ids):
            raise ValueError("Duplicate semantic criterion batch cannot supply an award")
        covered.update(spec.criterion_ids)
        active = one(
            c,
            "SELECT anvil.lock_native_ordinal_award(%s,%s) AS allowed",
            (binding["id"], spec.configuration_id),
        )
        if not active or not active["allowed"]:
            return waiting("semantic_current_author_access_required")
        config = get(c, spec.configuration_id)
        program, validation = config["configuration"].get("native_semantic"), config["validation"]
        from anvil.native_semantic import profile_matches

        if (
            config["status"] != "ready"
            or config["configuration_sha256"] != spec.configuration_sha256
            or not program
            or not profile_matches(program, config["configuration"], spec)
            or not validation
            or str(validation["id"]) != str(spec.validation_receipt_id)
            or validation["evidence_sha256"] != spec.validation_receipt_sha256
            or spec.model_binding_sha256
            not in validation["evidence"].get("supported_model_binding_sha256", [])
            or any(
                program.get(key) != getattr(spec, key)
                for key in ("criterion_ids", "max_input_bytes", "max_output_tokens", "max_calls")
            )
            or spec.deployment_release_sha256 != release
            or spec.evaluator_source_sha256 != source_hash()
            or spec.evaluator_version != VERSION
        ):
            return waiting("semantic_current_saved_profile_required")
        if any(
            {
                "target": descriptors[key]["target"],
                "configuration_id": str(spec.configuration_id),
                "configuration_sha256": spec.configuration_sha256,
                "program_sha256": digest(program),
            }
            not in records
            for key in spec.criterion_ids
        ):
            return waiting("semantic_exact_target_program_binding_required")
        rows = [descriptors.get(key) for key in sorted(spec.criterion_ids)]
        if any(not row or row["target"] not in mappings for row in rows):
            return waiting("semantic_exact_role_mapping_required")
        role_hash = digest([mappings[row["target"]] for row in rows])
        if not purpose_control(spec, qualification["evidence"], role_hash):
            return waiting("semantic_current_case_model_purpose_required")
        specs.append((quote, spec, candidate_binding))
    targets = {row["target"] for row in records}
    if {descriptors[key]["target"] for key in covered} != targets:
        return waiting("semantic_complete_bound_criterion_coverage_required")
    queued = custody.pending(c, job, prepared, task, sealed, reference, case)
    if queued["status"] != "terminal":
        return waiting(queued.get("reason", "semantic_private_evaluation_pending"))
    awards = {}
    for quote, spec, candidate_binding in specs:
        entry = one(
            c,
            "SELECT id FROM campaign_private.semantic_jobs WHERE project_id=%s AND quote_id=%s",
            (project, quote["id"]),
        )
        result = custody.result(c, entry["id"], quote["blueprint"], job, sealed)
        if result["status"] == "pending":
            return waiting(result["reason"])
        awards.update(
            public_awards(
                result,
                spec,
                judge_model=quote.get("model_binding")
                if isinstance(spec, FixedBlueprint)
                else None,
                candidate_model=candidate_binding,
            )
        )
    current = one(
        c,
        "SELECT q.id FROM anvil.project_binding_qualifications q WHERE q.project_id=%s AND q.id=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id)",
        (project, qualification["id"]),
    )
    if not current:
        return waiting("semantic_qualification_expired_or_revoked")
    return {"status": "completed", "awards": awards}
