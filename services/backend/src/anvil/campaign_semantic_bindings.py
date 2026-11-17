"""Server-derived judge templates; drafts do not invent qualification or inputs.

Only opaque source/reference/calibration identities enter public bindings. The
private judge projection is built after a real sealed execution, by the grader.
"""

import os
from collections import defaultdict

from fastapi import HTTPException

from anvil.campaign_ordinal import supports_target
from anvil.campaign_semantic_contract import Template, parse_template
from anvil.db import digest
from anvil.diagnostic_measures import valid_sha


def binding_record(ref, config):
    program = config["configuration"].get("native_semantic")
    if program is None:
        return None
    return {
        "target": ref["target"],
        "configuration_id": str(ref["id"]),
        "configuration_sha256": ref["sha256"],
        "program_sha256": digest(program),
    }


def compatible(config, descriptor):
    program = config["configuration"].get("native_semantic")
    return bool(
        program is not None
        and supports_target(descriptor)
        and descriptor["id"] in program["criterion_ids"]
    )


def templates_for_case(
    task, case, config, reference_binding, role_mapping_sha256, controls, release, evaluator_source
):
    """Pure projection of independently qualified case/model controls, not QA."""
    from anvil.native_semantic import VERSION

    program, validation = config["configuration"]["native_semantic"], config["validation"]
    fixed = program.get("model_selection") == "fixed"
    fixed_binding = config["configuration"].get("semantic_judge_model")
    if fixed and (
        not isinstance(fixed_binding, dict)
        or fixed_binding.get("id") != program.get("judge_model_profile_id")
    ):
        raise ValueError("The exact saved fixed judge snapshot is required")
    fixed_sha = digest(fixed_binding) if fixed else None
    expected = {
        **{key: task[key] for key in ("task_id", "task_version", "payload_sha256")},
        "case_id": case["case_id"],
        "case_snapshot_sha256": case["snapshot_sha256"],
        "configuration_id": str(config["id"]),
        "configuration_sha256": config["configuration_sha256"],
        "validation_receipt_id": str(validation["id"]),
        "validation_receipt_sha256": validation["evidence_sha256"],
        "criterion_ids": program["criterion_ids"],
        "source_reference_binding_sha256": digest(reference_binding),
        "evaluator_source_sha256": evaluator_source,
        "dispatcher_source_sha256": evaluator_source,
        "evaluator_version": VERSION,
        "deployment_release_sha256": release,
        "role_mapping_sha256": role_mapping_sha256,
    }
    supported = set(validation["evidence"].get("supported_model_binding_sha256", []))
    candidates, templates = defaultdict(set), {}
    for control in controls:
        if not isinstance(control, dict) or any(
            control.get(key) != value for key, value in expected.items()
        ):
            continue
        if (
            control.get("kind") != "private_native_semantic_qualification"
            or control.get("status") != "passed"
        ):
            continue
        if (
            not all(
                valid_sha(control.get(key))
                for key in (
                    "calibration_sha256",
                    "rights_review_receipt_sha256",
                    "source_qualification_receipt_sha256",
                    "evidence_sha256",
                    "model_binding_sha256",
                )
            )
            or control["model_binding_sha256"] not in supported
            or fixed
            and control["model_binding_sha256"] != fixed_sha
        ):
            continue
        body = {
            key: value
            for key, value in expected.items()
            if key not in {"role_mapping_sha256", "dispatcher_source_sha256"}
        }
        body.update(
            schema_version="anvil.campaign-semantic-judge-template.v2"
            if fixed
            else "anvil.campaign-semantic-judge-template.v1",
            model_selection="fixed" if fixed else "candidate",
            calibration_sha256=control["calibration_sha256"],
            max_input_bytes=program["max_input_bytes"],
            max_output_tokens=program["max_output_tokens"],
            max_calls=1,
        )
        if fixed:
            body.update(
                judge_model_profile_id=program["judge_model_profile_id"],
                judge_model_binding_sha256=fixed_sha,
            )
        template = parse_template(body).model_dump(mode="json")
        key = digest(template)
        candidates[key].add(control["model_binding_sha256"])
        templates[key] = template
        # Preserve each legitimate variant; group admission selects by the
        # exact candidate model and fails ambiguous/absent matches.
    claimed_models = set()
    for models in candidates.values():
        if claimed_models.intersection(models):
            raise ValueError("Ambiguous case calibration for the same judge model")
        claimed_models.update(models)
    return [
        {"template": templates[key], "model_bindings": sorted(candidates[key])}
        for key in sorted(templates)
    ]


def recommendation_ready(c, imported, descriptors, config, descriptor):
    """Use the same case-purpose checks before ranking as before binding.

    Read the current saved input and workflow mappings. This constructs a
    candidate binding for validation only; it neither saves choices nor changes
    authority, qualification, prices or the model used for recommendation.
    """
    from anvil.project_bindings import current

    if config["status"] != "ready" or not compatible(config, descriptor):
        return False
    program = config["configuration"]["native_semantic"]
    rows = [
        row
        for row in descriptors["skill_requirements"]
        if row["task_id"] == descriptor["task_id"] and compatible(config, row)
    ]
    if {row["id"] for row in rows} != set(program["criterion_ids"]):
        return False
    saved = current(c, imported["project_id"], imported["id"])
    baseline = saved["snapshot"] if saved else {}
    if saved and digest(baseline) != saved["snapshot_sha256"]:
        return False
    if not baseline.get("skill_mapping_bindings"):
        return False
    snapshot = {section: [] for section in ("workflow", "policy", "data", "rubric", "safety")} | {
        "skill_mapping_bindings": baseline.get("skill_mapping_bindings", []),
        "rubric": [
            {
                "kind": "evaluator",
                "id": str(config["id"]),
                "sha256": config["configuration_sha256"],
                "target": row["target"],
            }
            for row in rows
        ],
    }
    if baseline.get("execution_data"):
        snapshot["execution_data"] = baseline["execution_data"]
    result = freeze(c, imported["project_id"], imported, snapshot, descriptors)
    return bool(
        result.get("native_semantic_bindings")
        and result.get("semantic_judge_batches")
        and result.get("semantic_judge_model_support")
        and not result.get("semantic_judge_gaps")
    )


def freeze(c, project, imported, snapshot, descriptors):
    """Save incomplete drafts with explicit gaps, never silently omit a judge."""
    from anvil.campaign_reference_bindings import bound
    from anvil.campaign_reference_bindings import freeze as freeze_references
    from anvil.evaluator_configurations import get
    from anvil.project_inputs import default_dataset, frozen

    records, gaps, batches, model_support, judge_models = [], [], [], {}, {}
    profiles, selected = {}, defaultdict(list)
    targets = {row["target"]: row for row in descriptors["skill_requirements"]}
    for section, ref in (
        (section, ref)
        for section in ("workflow", "policy", "data", "rubric", "safety")
        for ref in snapshot[section]
    ):
        if ref["kind"] != "evaluator":
            continue
        key = str(ref["id"])
        if key not in profiles:
            profiles[key] = get(c, ref["id"])
        config = profiles[key]
        record = binding_record(ref, config)
        if record is None:
            continue
        descriptor = targets.get(ref["target"])
        if section != "rubric" or not descriptor or not compatible(config, descriptor):
            raise HTTPException(
                422, {"code": "native_semantic_target_not_supported", "target": ref["target"]}
            )
        if (
            sum(
                other["target"] == ref["target"] and other["kind"] in {"evaluator", "custom_python"}
                for other in snapshot["rubric"]
            )
            != 1
        ):
            raise HTTPException(
                422, {"code": "ambiguous_native_semantic_binding", "target": ref["target"]}
            )
        records.append(record)
        selected[key].append(descriptor)
    if not records:
        return {}

    def gap(code, **scope):
        gaps.append({"section": "rubric", "code": code, "owner": "anvil", **scope})

    result = {
        "native_semantic_bindings": records,
        "semantic_judge_batches": batches,
        "semantic_judge_model_support": model_support,
        "semantic_judge_gaps": gaps,
        "semantic_judge_models": judge_models,
    }
    release = os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256")
    if not release:
        gap("native_semantic_current_release_required")
        return result
    if not {"case_id", "case_snapshot_sha256"} <= Template.model_fields.keys():
        gap("native_semantic_case_contract_required")
        return result
    try:
        from anvil.campaign_semantic_runtime import source_hash
        from anvil.golden_kyc_anvil import source_hash as runtime_hash
        from anvil.governed_ai_catalogue import proof_valid
        from anvil.harbor_agents import code_digest
    except ImportError:
        gap("native_semantic_dispatch_runtime_required")
        return result
    try:
        members = (
            frozen(c, project, imported, snapshot["execution_data"])["selection"]["sample"][
                "members"
            ]
            if snapshot.get("execution_data")
            else default_dataset(c, project, imported)["manifest"]["cases"]
        )
        cases = [
            {"case_id": member["id"], "snapshot_sha256": member["snapshot_sha256"]}
            for member in members
        ]
        if (
            not 1 <= len(cases) <= 10000
            or len({case["case_id"] for case in cases}) != len(cases)
            or not all(valid_sha(case["snapshot_sha256"]) for case in cases)
        ):
            raise ValueError("Exact bounded selected cases required")
        references = freeze_references(c, imported["id"], cases)
    except HTTPException as error:
        if error.status_code not in {404, 409, 503}:
            raise
        gap("native_semantic_selected_input_required")
        return result
    except (ValueError, KeyError, TypeError):
        gap("native_semantic_selected_input_required")
        return result
    control_rows = c.execute(
        "SELECT q.* FROM anvil.task_capability_qualifications q WHERE q.project_id=%s AND q.task_group_id=%s AND q.kind='evaluator' AND q.source_sha256=%s AND q.release_sha256=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.task_capability_revocations r WHERE r.qualification_id=q.id) ORDER BY q.created_at DESC,q.id DESC LIMIT 10001",
        (project, imported["id"], imported["content_sha256"], release),
    ).fetchall()
    if len(control_rows) > 10000:
        gap("native_semantic_qualification_catalogue_bound_exceeded")
        return result
    actual_runtime, actual_broker, actual_source = runtime_hash(), code_digest(), source_hash()
    tasks = {task["task_id"]: task for task in imported["content"]["tasks"]}
    for key, rows in selected.items():
        config = profiles[key]
        program = config["configuration"]["native_semantic"]
        if program.get("model_selection") == "fixed":
            from anvil.native_semantic import fixed_model, fixed_runtime_available
            from anvil.workspace_preparation import model

            try:
                judge = fixed_model(
                    program, config["configuration"], model(c, program["judge_model_profile_id"])
                )
            except (HTTPException, ValueError, KeyError, TypeError):
                gap("native_semantic_fixed_judge_changed_or_unavailable", configuration_id=key)
                continue
            judge_models[digest(judge)] = judge
            if not fixed_runtime_available(c):
                gap("native_semantic_fixed_judge_admission_required", configuration_id=key)
                continue
        if config["status"] != "ready":
            gap("native_semantic_profile_qualification_required", configuration_id=key)
            continue
        if len({row["task_id"] for row in rows}) != 1 or {row["id"] for row in rows} != set(
            program["criterion_ids"]
        ):
            gap("native_semantic_complete_criterion_batch_required", configuration_id=key)
            continue
        mapping = {entry["target"]: entry for entry in snapshot.get("skill_mapping_bindings", [])}
        if any(row["target"] not in mapping for row in rows):
            gap("native_semantic_exact_role_mapping_required", configuration_id=key)
            continue
        role_mapping = digest(
            [mapping[row["target"]] for row in sorted(rows, key=lambda row: row["id"])]
        )
        coverage, bodies, seen = defaultdict(set), {}, set()
        required_targets = {row["target"] for row in rows}
        for proof in control_rows:
            identity = (proof["target"], str(proof["candidate_id"]))
            if identity in seen:
                continue
            seen.add(identity)  # A newer failed proof cannot resurrect an older pass.
            if (
                str(proof["candidate_id"]) != key
                or proof["candidate_sha256"] != config["configuration_sha256"]
                or proof["target"] not in required_targets
                or not proof_valid(proof, imported, actual_runtime, actual_broker)
            ):
                continue
            extra = proof["evidence"].get("native_semantic", [])
            if isinstance(extra, list) and len(extra) <= 10000:
                for control in extra:
                    if isinstance(control, dict):
                        body = {name: value for name, value in control.items() if name != "target"}
                        fingerprint = digest(body)
                        coverage[fingerprint].add(proof["target"])
                        bodies[fingerprint] = body
        controls = [
            bodies[fingerprint]
            for fingerprint in bodies
            if coverage[fingerprint] == required_targets
        ]
        task = tasks[rows[0]["task_id"]]
        for case in cases:
            reference = bound(
                references | {"case_assignments": cases},
                task,
                case["case_id"],
                case["snapshot_sha256"],
            )
            if reference["reference_id"] is None:
                gap(
                    "native_semantic_case_reference_required",
                    case_id=case["case_id"],
                    configuration_id=key,
                )
                continue
            try:
                variants = templates_for_case(
                    task, case, config, reference, role_mapping, controls, release, actual_source
                )
            except (ValueError, TypeError):
                variants = []
            if not variants:
                gap(
                    "native_semantic_case_purpose_calibration_required",
                    case_id=case["case_id"],
                    configuration_id=key,
                )
            for variant in variants:
                template = variant["template"]
                batches.append(template)
                model_support[digest(template)] = variant["model_bindings"]
                if len(batches) > 1000:
                    batches.clear()
                    model_support.clear()
                    gap("native_semantic_batch_bound_exceeded_no_population_reduced")
                    return result
    return result
