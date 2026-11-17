"""Private post-seal projection/queue; no SDK or public-input fallback.

The private grader commits a pending queue before final target registration.
Missing reference/calibration stays an Anvil gap, never a guessed native award.
"""

import re

from anvil.campaign_reference_bindings import bound as bound_reference
from anvil.campaign_semantic_contract import (
    FixedBlueprint,
    bounded_json,
    parse_batch,
    parse_blueprint,
    prompt,
    validate_result,
)
from anvil.db import Jsonb, digest, one
from anvil.diagnostic_measures import valid_sha
from anvil.golden_targets import requirements
from anvil.praxis_generic_contract import canonical
from anvil.praxis_generic_contract import digest as wire_digest
from anvil.skill_step_bindings import mapped


def selected(capture, pointer):
    if (
        type(pointer) is not str
        or not pointer.startswith("/")
        or len(pointer) > 500
        or len(pointer.split("/")) > 17
        or re.search(r"~(?![01])", pointer)
    ):
        raise ValueError("Reviewed bounded capture pointer required")
    value = capture
    for key in pointer.split("/")[1:]:
        key = key.replace("~1", "/").replace("~0", "~")
        if type(value) is dict and key in value:
            value = value[key]
        elif (
            type(value) is list
            and key.isascii()
            and key.isdecimal()
            and (key == "0" or not key.startswith("0"))
            and int(key) < len(value)
        ):
            value = value[int(key)]
        else:
            raise ValueError("Reviewed capture selector has no observed value")
    return value


def project(blueprint, job, task, sealed, calibration, descriptors):
    """Reviewed selectors choose facts; the model cannot name its own evidence."""
    spec = parse_blueprint(blueprint)
    bounded_json(calibration, 65536)
    if not isinstance(calibration, dict) or digest(calibration) != spec.calibration_sha256:
        raise ValueError("Exact reviewed private calibration required")
    expected = {
        key: getattr(spec, key)
        for key in (
            "task_id",
            "task_version",
            "payload_sha256",
            "case_id",
            "case_snapshot_sha256",
            "criterion_ids",
            "configuration_sha256",
            "evaluator_source_sha256",
            "evaluator_version",
        )
    }
    if (
        calibration.get("schema_version") != "anvil.native-semantic-calibration.v1"
        or calibration.get("status") != "reviewed"
        or any(calibration.get(key) != value for key, value in expected.items())
        or any(
            task.get(key) != getattr(spec, key)
            for key in ("task_id", "task_version", "payload_sha256")
        )
        or not all(
            valid_sha(calibration.get(key))
            for key in (
                "reviewed_examples_sha256",
                "reference_set_sha256",
                "blind_holdout_receipt_sha256",
                "rights_review_receipt_sha256",
                "source_qualification_receipt_sha256",
            )
        )
    ):
        raise ValueError("Reviewed calibration task, case, source or receipt differs")
    targets = {
        item["id"]: item
        for item in descriptors
        if item["official"] and item["id"] in spec.criterion_ids
    }
    if set(targets) != set(spec.criterion_ids) or any(
        not valid_sha(item.get("skill_mapping_sha256")) for item in targets.values()
    ):
        raise ValueError("Exact reviewed criterion role/skill mappings required")
    bounded_json(sealed["capture"], 16777216, max_nodes=200000)
    if wire_digest(sealed["capture"]) != sealed["capture_sha256"]:
        raise ValueError("Exact immutable observed campaign seal required")
    custody = {
        "grading_job_id": str(job["id"]),
        "episode_id": str(job["episode_id"]),
        "generation": job["generation"],
        "capture_sha256": sealed["capture_sha256"],
        "case_id": spec.case_id,
        "case_snapshot_sha256": spec.case_snapshot_sha256,
    }
    criteria, refs = {}, []
    declared = calibration.get("criteria")
    if not isinstance(declared, dict) or set(declared) != set(spec.criterion_ids):
        raise ValueError("Every batch criterion needs a reviewed private projection")
    for identifier in spec.criterion_ids:
        recipe, descriptor = declared[identifier], targets[identifier]
        if not isinstance(recipe, dict) or any(
            recipe.get(key) != descriptor.get(key)
            for key in ("target", "role", "skill_mapping_sha256")
        ):
            raise ValueError("Criterion projection differs from the frozen responsible role")
        anchors = recipe.get("anchors")
        if (
            not isinstance(anchors, list)
            or len(anchors) != 5
            or any(
                not isinstance(item, dict)
                or type(item.get("level")) is not int
                or type(item.get("description")) is not str
                or not 1 <= len(item["description"]) <= 1000
                for item in anchors
            )
            or {item["level"] for item in anchors} != set(range(5))
        ):
            raise ValueError("All five explicit reviewed native anchors required")
        selectors = recipe.get("capture_selectors")
        if not isinstance(selectors, dict) or not 1 <= len(selectors) <= 80:
            raise ValueError("Explicit bounded reviewed observation selectors required")
        observations = {}
        for name, pointer in selectors.items():
            if type(name) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", name):
                raise ValueError("Bounded reviewed observation name required")
            value = selected(sealed["capture"], pointer)
            # Reserve work before placing any selected subtree in the projection.
            bounded_json(value, spec.max_input_bytes)
            ref = "capture:" + sealed["capture_sha256"] + "#" + pointer
            observations[name] = {"evidence_ref": ref, "value": value}
            if ref not in refs:
                refs.append(ref)
            if len(refs) > 500:
                raise ValueError("Observed evidence inventory exceeds the batch bound")
        criteria[identifier] = {
            "target": descriptor["target"],
            "role": descriptor["role"],
            "skill_mapping_sha256": descriptor["skill_mapping_sha256"],
            "anchors": anchors,
            "observations": observations,
        }
        bounded_json(criteria, spec.max_input_bytes)
    projection = {
        "schema_version": "anvil.campaign-semantic-projection.v1",
        "custody": custody,
        "task": {key: task[key] for key in ("task_id", "task_version", "payload_sha256")},
        "criteria": criteria,
        "evidence_refs": refs,
    }
    bounded_json(projection, spec.max_input_bytes)
    batch = parse_batch(
        spec.model_dump(mode="json")
        | {
            "schema_version": "anvil.campaign-semantic-judge-batch.v2"
            if isinstance(spec, FixedBlueprint)
            else "anvil.campaign-semantic-judge-batch.v1",
            "input_projection_sha256": wire_digest(projection),
        }
    )
    return batch, projection


def pending(c, job, prepared, task, sealed, reference, case):
    """Commit pending jobs before grading; never finalize/retry an uncertain call.

    Return status=pending while at least one one-shot job is queued/dispatching;
    terminal jobs are read privately by the semantic collector. The caller owns
    current binding/purpose checks and final grading transaction/locks.
    """
    if job["kind"] != "workspace_group" or not job.get("plan_id"):
        return {"status": "not_configured", "jobs": []}
    quotes = c.execute(
        "SELECT * FROM marketing_runtime.semantic_quotes WHERE project_id=%s AND group_id=%s AND plan_id=%s ORDER BY batch_index",
        (job["project_id"], job["run_id"], job["plan_id"]),
    ).fetchall()
    if not quotes:
        return {"status": "not_configured", "jobs": []}
    identity = bound_reference(prepared, task, case["case_id"], case["snapshot_sha256"])
    if identity["reference_id"] is None:
        return {
            "status": "unavailable",
            "reason": "semantic_frozen_private_reference_missing",
            "jobs": [],
        }
    actual_reference = one(
        c,
        "SELECT content,content_sha256 FROM campaign_private.references WHERE project_id=%s AND id=%s",
        (job["project_id"], identity["reference_id"]),
    )
    if (
        not actual_reference
        or actual_reference["content_sha256"] != identity["reference_sha256"]
        or actual_reference["content"] != reference
        or digest(reference) != identity["reference_sha256"]
    ):
        raise ValueError("Exact frozen private semantic reference required")
    descriptors = mapped(requirements(task), prepared)
    jobs, unresolved, prepared_jobs = [], False, []
    for quote in quotes:
        old = one(
            c,
            "SELECT s.*,EXISTS(SELECT 1 FROM campaign_private.semantic_dispositions d WHERE d.project_id=s.project_id AND d.semantic_job_id=s.id AND d.disposition='unscored_final') AS unscored_final FROM campaign_private.semantic_jobs s WHERE s.project_id=%s AND s.quote_id=%s",
            (job["project_id"], quote["id"]),
        )
        if old:
            if (
                str(old["grading_job_id"]) != str(job["id"])
                or str(old["episode_id"]) != str(job["episode_id"])
                or old["generation"] != job["generation"]
                or old["capture_sha256"] != sealed["capture_sha256"]
            ):
                raise ValueError("Existing semantic job belongs to another exact sealed episode")
            jobs.append(str(old["id"]))
            unresolved |= (
                old["state"] in {"queued", "dispatching", "execution_unknown"}
                and not old["unscored_final"]
            )
            continue
        spec = parse_blueprint(quote["blueprint"])
        if (
            digest(quote["blueprint"]) != quote["blueprint_sha256"]
            or digest(identity) != spec.source_reference_binding_sha256
            or spec.case_id != case["case_id"]
            or spec.case_snapshot_sha256 != case["snapshot_sha256"]
        ):
            raise ValueError("Frozen semantic quote source/case changed")
        calibration = reference.get("native_semantic_calibrations", {}).get(
            str(spec.configuration_id)
        )
        if calibration is None:
            return {
                "status": "unavailable",
                "reason": "semantic_reviewed_private_calibration_missing",
                "jobs": jobs,
            }
        batch, projection = project(quote["blueprint"], job, task, sealed, calibration, descriptors)
        # Complete prompt size includes schema/bindings. A temporary UUID only
        # sizes the fixed-length job field; it is not a fabricated run/job receipt.
        prompt(batch, projection, "00000000-0000-0000-0000-000000000000")
        prepared_jobs.append((quote, batch, projection))
    # Validate all source/calibration/size requirements before the first enqueue.
    # The caller's one transaction then commits all jobs together, or none.
    for quote, batch, projection in prepared_jobs:
        identifier = one(
            c,
            "SELECT campaign_private.enqueue_semantic_job(%s,%s,%s,%s,%s) AS id",
            (
                quote["id"],
                job["id"],
                Jsonb(batch.model_dump(mode="json")),
                Jsonb(projection),
                batch.input_projection_sha256,
            ),
        )["id"]
        if identifier is None:
            raise ValueError("Semantic private job scope or quota not admitted")
        jobs.append(str(identifier))
        unresolved = True
    ready = one(c, "SELECT marketing_runtime.campaign_grade_ready(%s) AS ready", (job["id"],))[
        "ready"
    ]
    return {"status": "pending" if unresolved or not ready else "terminal", "jobs": jobs}


def result(c, semantic_job_id, blueprint, grading_job, sealed):
    """Private collector interface; caller still rechecks current grading authority."""
    row = one(
        c,
        "SELECT s.*,q.bound_micro_usd,campaign_private.semantic_result_on_time(s.id) AS on_time,EXISTS(SELECT 1 FROM campaign_private.semantic_dispositions d WHERE d.project_id=s.project_id AND d.semantic_job_id=s.id AND d.disposition='unscored_final') AS unscored_final FROM campaign_private.semantic_jobs s JOIN marketing_runtime.semantic_quotes q ON q.id=s.quote_id AND q.project_id=s.project_id WHERE s.id=%s AND s.project_id=%s",
        (semantic_job_id, grading_job["project_id"]),
    )
    if (
        not row
        or str(row["grading_job_id"]) != str(grading_job["id"])
        or str(row["episode_id"]) != str(grading_job["episode_id"])
        or row["generation"] != grading_job["generation"]
        or row["capture_sha256"] != sealed["capture_sha256"]
    ):
        raise ValueError("Exact private semantic episode/job/seal required")
    spec, batch = parse_blueprint(blueprint), parse_batch(row["batch"])
    if (
        spec.model_dump(exclude={"schema_version"})
        != batch.model_dump(exclude={"schema_version", "input_projection_sha256"})
        or batch.input_projection_sha256 != row["input_projection_sha256"]
    ):
        raise ValueError("Private semantic job differs from its upfront bound blueprint")
    if row["unscored_final"]:
        return {
            "status": "unscored",
            "criteria": None,
            "reason": "operator_closed_expired_semantic_attempt_unscored",
            "job_id": str(row["id"]),
            "result_sha256": row["result_sha256"],
        }
    if row["state"] in {"queued", "dispatching", "execution_unknown"} or (
        row["state"] == "completed" and not row["on_time"]
    ):
        return {
            "status": "pending",
            "criteria": None,
            "reason": "private_semantic_result_or_reconciliation_pending",
        }
    receipt = row["result"]
    bounded_json(receipt, 262144, max_nodes=10000)
    if digest(receipt) != row["result_sha256"]:
        raise ValueError("Private semantic terminal receipt custody changed")
    if row["state"] != "completed":
        return {
            "status": "unscored",
            "criteria": None,
            "reason": "private_semantic_evaluator_failure_or_reconciled_unknown",
            "job_id": str(row["id"]),
            "result_sha256": row["result_sha256"],
        }
    if (
        not row["broker_claimed"]
        or type(row["actual_micro_usd"]) is not int
        or not 0 <= row["actual_micro_usd"] <= row["bound_micro_usd"]
        or receipt.get("status") != "completed"
        or receipt.get("dispatch_origin") not in {"provider", "sdk_mock"}
    ):
        raise ValueError("Exact completed and metered private evaluator receipt required")
    accepted = receipt.get("result")
    bounded_json(accepted, 65536)
    accepted = validate_result(canonical(accepted).decode(), batch, row["projection"], row["id"])
    return {
        "status": "completed",
        "criteria": accepted["criteria"],
        "job_id": str(row["id"]),
        "result_sha256": row["result_sha256"],
        "dispatch_origin": receipt["dispatch_origin"],
        "model_performance_validated": False,
    }
