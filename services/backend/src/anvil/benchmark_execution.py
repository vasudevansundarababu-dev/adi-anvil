"""Revision-bound benchmark publication and read-only execution projections.

Publication consumes current native qualification; it never manufactures a
receipt, invokes a provider, or grants permission from source authenticity.
"""

from fastapi import HTTPException

from anvil import benchmark_pipeline as pipeline
from anvil import domain
from anvil.benchmark_conversation import Binding
from anvil.benchmark_protocol import Protocol
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.workspace_preparation import model


def version(c, identifier):
    binding = one(c, "SELECT * FROM anvil.benchmark_version_bindings WHERE benchmark_revision_id=%s", (identifier,))
    if binding is None:
        raise HTTPException(404, "Benchmark version not found")
    revision = domain.get_revision(c, identifier, "benchmark")
    tasks = c.execute(
        """SELECT t.task_revision_id,t.source_id,t.package_id,t.qualification_id,
        t.possible_points,t.criterion_count,q.package_sha256,q.environment_digest,
        q.tool_schema_sha256,q.evaluator_binding_id
        FROM anvil.benchmark_version_tasks t JOIN anvil.benchmark_qualifications q
        ON q.project_id=t.project_id AND q.id=t.qualification_id
        WHERE t.benchmark_revision_id=%s ORDER BY t.ordinal""", (identifier,)
    ).fetchall()
    return {"benchmark_revision_id": str(binding["benchmark_revision_id"]),
            "suite_revision_id": str(binding["suite_revision_id"]),
            "subject_sha256": binding["subject_sha256"],
            "build_id": revision["content"]["build_id"],
            "tasks": [{k: int(v) if k in ("possible_points", "criterion_count") else str(v)
                       for k, v in task.items()} for task in tasks]}


def publish(c, project, user, build_id, expected, manifest):
    # Lock the parent before taking any subordinate bindings. API performs the
    # expensive archive/rights validation before entering this transaction.
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    build = pipeline.record(c, "benchmark_builds", build_id)
    if build["subject_sha256"] != expected:
        raise HTTPException(409, "Build changed before benchmark freeze")
    review = pipeline.record(c, "benchmark_source_reviews", build["review_id"])
    if pipeline.review_status(c, review, build["receipt_id"]):
        raise HTTPException(409, "Current source review is required")
    existing = one(c, """SELECT b.benchmark_revision_id FROM anvil.benchmark_version_bindings b
                      JOIN anvil.revisions r ON r.project_id=b.project_id AND r.id=b.benchmark_revision_id
                      WHERE r.content->>'build_id'=%s""", (str(build_id),))
    if existing:
        return version(c, existing["benchmark_revision_id"])
    operation = one(c, "SELECT * FROM anvil.benchmark_qualification_operations WHERE build_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (build_id,))
    if operation is None or operation["state"] != "passed":
        raise HTTPException(409, "Current native qualification must pass before freeze")
    tasks = c.execute(
        """SELECT t.*,q.id qualification_id,q.package_sha256,q.evaluator_binding_id,
        q.outcome FROM anvil.benchmark_build_tasks t
        JOIN anvil.benchmark_operation_results o ON o.project_id=t.project_id
        AND o.source_id=t.source_id AND o.package_id=t.package_id
        JOIN anvil.benchmark_qualifications q ON q.project_id=o.project_id AND q.id=o.qualification_id
        WHERE t.build_id=%s AND o.operation_id=%s AND q.outcome='passed'
        AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_qualification_events e WHERE e.qualification_id=q.id)
        ORDER BY t.task_id""", (build_id, operation["id"])
    ).fetchall()
    by_id = {t.id: t for t in manifest.tasks}
    if len(tasks) != 3 or set(by_id) != {t["task_id"] for t in tasks}:
        raise HTTPException(409, "Three exact qualified tasks are required")
    totals = [sum(criterion.possible_points for criterion in by_id[t["task_id"]].criteria) for t in tasks]
    if sorted(totals) != [6, 24, 51]:
        raise HTTPException(409, "The primary benchmark requires 24/6/51 task points")
    scoring = {"profile": "sme-primary-81-v1", "source_manifest_sha256": manifest.model_dump(mode="json"),
               "task_points": totals}
    scoring_hash = digest(scoring)
    # Private criterion rules remain exclusively in the raw/evaluator vault.
    task_revisions = []
    for task, points in zip(tasks, totals, strict=True):
        resource = domain.create(c, project, user, "task", {
            "profile": "sme-frozen-task-v1", "source_id": str(task["source_id"]),
            "package_id": str(task["package_id"]), "qualification_id": str(task["qualification_id"]),
            "possible_points": points, "criterion_count": len(by_id[task["task_id"]].criteria),
        })
        task_revisions.append(resource["current_revision_id"])
    suite = domain.create(c, project, user, "suite", {"profile": "sme-suite-v1", "task_revision_ids": [str(t) for t in task_revisions]})
    subject = digest({"build": expected, "tasks": [str(t) for t in task_revisions],
                      "qualifications": [str(t["qualification_id"]) for t in tasks], "scoring": scoring_hash})
    benchmark = domain.create(c, project, user, "benchmark", {"profile": "sme-benchmark-v1", "build_id": str(build_id),
                              "subject_sha256": subject, "origin": manifest.source.classification})
    bid = benchmark["current_revision_id"]
    c.execute("INSERT INTO anvil.benchmark_version_bindings(project_id,benchmark_revision_id,suite_revision_id,subject_sha256,scoring_policy_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
              (project, bid, suite["current_revision_id"], subject, scoring_hash, user))
    for ordinal, (task, revision, points) in enumerate(zip(tasks, task_revisions, totals, strict=True)):
        c.execute("INSERT INTO anvil.benchmark_version_tasks(project_id,benchmark_revision_id,ordinal,task_revision_id,source_id,package_id,qualification_id,possible_points,criterion_count) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                  (project, bid, ordinal, revision, task["source_id"], task["package_id"], task["qualification_id"], points, len(by_id[task["task_id"]].criteria)))
    audit(c, project, user, "benchmark.version_frozen", bid, {"subject_sha256": subject})
    return version(c, bid)


def protocol(c, identifier):
    row = domain.get_revision(c, identifier, "protocol")
    if row["content"].get("profile") != "sme-comparison-v1":
        raise HTTPException(404, "Benchmark protocol not found")
    frozen = Protocol.model_validate(row["content"])
    return {"protocol_revision_id": str(identifier), "subject_sha256": frozen.subject_sha256,
            "protocol": frozen.model_dump(mode="json"), "state": "frozen"}


def freeze_protocol(c, project, user, body):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    current = version(c, body.benchmark_revision_id)
    if current["subject_sha256"] != body.expected_benchmark_sha256:
        raise HTTPException(409, "Benchmark version changed before protocol freeze")
    benchmark = domain.get_revision(c, body.benchmark_revision_id, "benchmark")
    if benchmark["content"].get("origin") != "original_synthetic_fixture":
        raise HTTPException(409, "Offline conformance requires explicitly fictional source data")
    version_binding = one(c, "SELECT * FROM anvil.benchmark_version_bindings WHERE benchmark_revision_id=%s", (body.benchmark_revision_id,))
    slots = []
    for selection in body.slots:
        snapshot = model(c, selection.connection_id)
        if snapshot["config_hash"] != selection.configuration_sha256:
            raise HTTPException(409, "Model configuration changed before protocol freeze")
        binding = Binding(provider=snapshot["provider"], model_id=snapshot["model_id"],
                          destination=snapshot["destination"],
                          max_output_tokens=min(snapshot["max_output_tokens"] or 2048, 8192))
        slots.append({"connection_id": str(selection.connection_id), "binding": binding.model_dump(),
                      "configuration_sha256": selection.configuration_sha256,
                      "transport": selection.transport})
    frozen = Protocol.model_validate({
        "benchmark_revision_id": str(body.benchmark_revision_id),
        "benchmark_subject_sha256": current["subject_sha256"], "tasks": current["tasks"],
        "slots": slots, "origin": "original_synthetic_fixture",
        "scoring_policy_sha256": version_binding["scoring_policy_sha256"],
        "evaluator_policy_sha256": digest([t["evaluator_binding_id"] for t in current["tasks"]]),
        "spend": {"currency": "USD", "candidate_cap_micro_usd": 0,
                  "judge_cap_micro_usd": 0, "pricing_sha256": digest({"offline": True}),
                  "authority_sha256": digest({"project": str(project), "user": str(user), "scope": "offline-software-conformance"}),
                  "expires_at": body.expires_at.isoformat()},
    })
    revision = domain.create(c, project, user, "protocol", frozen.model_dump(mode="json"))
    return protocol(c, revision["current_revision_id"])


def protocol_gates(c, identifier):
    projection = protocol(c, identifier)
    frozen = Protocol.model_validate(projection["protocol"])
    blockers = frozen.authority_blockers()
    current = version(c, frozen.benchmark_revision_id)
    build = pipeline.record(c, "benchmark_builds", current["build_id"])
    review = pipeline.record(c, "benchmark_source_reviews", build["review_id"])
    if pipeline.review_status(c, review, build["receipt_id"]):
        blockers.append("source_review_stale")
    for task in frozen.tasks:
        qualified = one(c, "SELECT 1 FROM anvil.benchmark_qualifications q WHERE q.id=%s AND q.outcome='passed' AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_qualification_events e WHERE e.qualification_id=q.id)", (task.qualification_id,))
        if not qualified:
            blockers.append("qualification_stale")
    for slot in frozen.slots:
        current = model(c, slot.connection_id)
        if current["config_hash"] != slot.configuration_sha256:
            blockers.append("model_binding_stale")
    return projection, sorted(set(blockers))


def comparison(c, run_id):
    row = one(c, "SELECT b.*,r.state,r.cancel_requested FROM anvil.benchmark_comparisons b JOIN anvil.runs r ON r.project_id=b.project_id AND r.id=b.run_id WHERE b.run_id=%s", (run_id,))
    if row is None:
        raise HTTPException(404, "Benchmark comparison not found")
    cells = c.execute("""SELECT c.id cell_id,c.task_revision_id,c.slot,c.repetition,
        coalesce(e.state,'queued') state,coalesce(e.validity,'pending') validity
        FROM anvil.benchmark_cells c LEFT JOIN anvil.benchmark_cell_attempts a
        ON a.project_id=c.project_id AND a.cell_id=c.id AND a.attempt_no=1
        LEFT JOIN LATERAL (SELECT state,validity FROM anvil.benchmark_attempt_events
        WHERE project_id=a.project_id AND attempt_id=a.id ORDER BY event_seq DESC LIMIT 1) e ON true
        WHERE c.run_id=%s ORDER BY c.task_revision_id,c.slot,c.repetition""", (run_id,)).fetchall()
    score = one(c, "SELECT redacted_projection FROM anvil.benchmark_score_revisions WHERE run_id=%s ORDER BY revision DESC LIMIT 1", (run_id,))
    return {"run_id": str(run_id), "protocol_revision_id": str(row["protocol_revision_id"]),
            "subject_sha256": row["subject_sha256"], "state": row["state"],
            "origin": "original_synthetic_fixture", "planned_cells": row["planned_cells"],
            "cells": [{k: str(v) if k in ("cell_id", "task_revision_id") else v for k, v in item.items()} for item in cells],
            "scorecard": score["redacted_projection"] if score else None, "blockers": []}


def admit_offline(c, project, user, identifier, expected):
    """Atomic whole-parent installation; no individual child can launch itself."""
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    projection, reasons = protocol_gates(c, identifier)
    if projection["subject_sha256"] != expected or reasons:
        raise HTTPException(409, {"message": "Comparison admission blocked", "blockers": reasons})
    frozen = Protocol.model_validate(projection["protocol"])
    if any(slot.transport != "offline_contract" for slot in frozen.slots):
        raise HTTPException(409, "Live comparison activation is separately gated")
    runner = one(c, "SELECT id,config_hash FROM anvil.workspace_framework_profiles WHERE framework='harbor' AND config->>'runtime_version'='0.25.0' ORDER BY created_at,id LIMIT 1")
    if not runner:
        raise HTTPException(409, "A reviewed pinned Harbor runner profile is required")
    run_id = uid()
    c.execute("INSERT INTO anvil.runs(id,project_id,protocol_revision_id,origin,created_by,state) VALUES(%s,%s,%s,'illustrative',%s,'queued')", (run_id, project, identifier, user))
    c.execute("INSERT INTO anvil.benchmark_comparisons(project_id,run_id,benchmark_revision_id,protocol_revision_id,subject_sha256,planned_cells,created_by) VALUES(%s,%s,%s,%s,%s,18,%s)", (project, run_id, frozen.benchmark_revision_id, identifier, expected, user))
    windows = {}
    for purpose in ("candidate", "judge"):
        window = uid()
        c.execute("INSERT INTO anvil.evaluation_spend_windows(id,project_id,cap_micro_usd,end_at,status,authority_reference) VALUES(%s,%s,0,%s,'active',%s)", (window, project, frozen.spend.expires_at, "offline:" + expected + ":" + purpose))
        c.execute("INSERT INTO anvil.benchmark_spend_bindings(project_id,run_id,purpose,window_id,cap_micro_usd,pricing_sha256,authority_sha256) VALUES(%s,%s,%s,%s,0,%s,%s)", (project, run_id, purpose, window, frozen.spend.pricing_sha256, frozen.spend.authority_sha256))
        windows[purpose] = window
    for task in frozen.tasks:
        preset, prep, group = uid(), uid(), uid()
        snapshot = {"profile": "sme-offline-comparison-v1", "run_id": run_id,
                    "package_id": str(task.package_id), "protocol_sha256": expected,
                    "execution_order": "parent-fenced", "fixture_only": True}
        c.execute("INSERT INTO anvil.workspace_execution_presets(id,project_id,name,runner_profile_id,snapshot,subject_hash,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)", (preset, project, "Offline benchmark comparison", runner["id"], Jsonb(snapshot), digest(snapshot), user))
        c.execute("INSERT INTO anvil.workspace_run_preparations(id,project_id,preset_id,package_id,snapshot,subject_hash,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)", (prep, project, preset, task.package_id, Jsonb(snapshot), digest(snapshot), user))
        c.execute("INSERT INTO anvil.workspace_execution_groups(id,project_id,preparation_id,created_by,snapshot,subject_hash) VALUES(%s,%s,%s,%s,%s,%s)", (group, project, prep, user, Jsonb(snapshot), digest(snapshot)))
        c.execute("INSERT INTO anvil.benchmark_comparison_groups(project_id,run_id,benchmark_revision_id,task_revision_id,group_id) VALUES(%s,%s,%s,%s,%s)", (project, run_id, frozen.benchmark_revision_id, task.task_revision_id, group))
        for slot_no, slot in enumerate(frozen.slots):
            c.execute("INSERT INTO anvil.workspace_preset_models(project_id,preset_id,connection_id) VALUES(%s,%s,%s)", (project, preset, slot.connection_id))
            c.execute("INSERT INTO anvil.workspace_preparation_models(project_id,preparation_id,preset_id,connection_id) VALUES(%s,%s,%s,%s)", (project, prep, preset, slot.connection_id))
            for repetition in range(2):
                plan, cell, attempt, job, fence = uid(), uid(), uid(), uid(), uid()
                config = {**snapshot, "workspace_execution_group": group,
                          "slot": slot_no, "repetition": repetition,
                          "binding": slot.binding.model_dump(), "transport": "offline_contract"}
                c.execute("INSERT INTO anvil.harbor_agent_plans(id,project_id,package_id,connection_id,created_by,config,subject_hash) VALUES(%s,%s,%s,%s,%s,%s,%s)", (plan, project, task.package_id, slot.connection_id, user, Jsonb(config), digest(config)))
                c.execute("INSERT INTO anvil.workspace_execution_models(project_id,group_id,ordinal,plan_id) VALUES(%s,%s,%s,%s)", (project, group, slot_no * 2 + repetition, plan))
                c.execute("INSERT INTO anvil.benchmark_cells(id,project_id,run_id,benchmark_revision_id,task_revision_id,slot,repetition) VALUES(%s,%s,%s,%s,%s,%s,%s)", (cell, project, run_id, frozen.benchmark_revision_id, task.task_revision_id, slot_no, repetition))
                c.execute("INSERT INTO anvil.jobs(id,project_id,kind,target_id,operation_key) VALUES(%s,%s,'benchmark_offline_trial',%s,%s)", (job, project, attempt, "benchmark-offline:" + attempt))
                c.execute("INSERT INTO anvil.benchmark_cell_attempts(id,project_id,cell_id,attempt_no,plan_id,job_id) VALUES(%s,%s,%s,1,%s,%s)", (attempt, project, cell, plan, job))
                c.execute("INSERT INTO anvil.benchmark_offline_runtime(project_id,attempt_id,run_id,state,fence) VALUES(%s,%s,%s,'queued',%s)", (project, attempt, run_id, fence))
                c.execute("INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence) VALUES(%s,%s,%s,'queued','pending',%s)", (uid(), project, attempt, fence))
    audit(c, project, user, "benchmark.offline_comparison_admitted", run_id, {"cells": 18, "subject_sha256": expected, "paid_calls": False})
    return comparison(c, run_id)


def cancel(c, project, user, run_id, expected, rationale):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    current = comparison(c, run_id)
    if current["subject_sha256"] != expected:
        raise HTTPException(409, "Comparison subject changed")
    c.execute("UPDATE anvil.runs SET cancel_requested=true,state='cancel_requested',row_version=row_version+1 WHERE id=%s", (run_id,))
    pending = c.execute("UPDATE anvil.benchmark_offline_runtime SET state='cancelled',reason_code='user_cancelled',updated_at=now() WHERE run_id=%s AND state IN ('queued','claimed') RETURNING attempt_id,fence", (run_id,)).fetchall()
    for attempt in pending:
        c.execute("INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence,reason_code) VALUES(%s,%s,%s,'cancelled','invalid',%s,'user_cancelled')", (uid(), project, attempt["attempt_id"], attempt["fence"]))
    # Intent/capture work is never requeued; its operator reconciles the exact
    # dispatched attempt after capture. Cancellation does not invent an outcome.
    audit(c, project, user, "benchmark.comparison_cancel_requested", run_id, {"rationale": rationale})
    return comparison(c, run_id)
