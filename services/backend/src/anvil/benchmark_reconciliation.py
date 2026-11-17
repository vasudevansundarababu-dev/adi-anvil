"""Explicit stopped-actor attestation, never a fabricated result or inference retry."""

from fastapi import HTTPException

from anvil.benchmark_execution import comparison, protocol_gates
from anvil.db import audit, one, uid


def resume(c, project, user, run_id, body):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    current = comparison(c, run_id)
    if (
        current["subject_sha256"] != body.expected_subject_sha256
        or current["checkpoint_event_seq"] != body.expected_event_seq
    ):
        raise HTTPException(409, "Comparison checkpoint changed")
    parent = one(
        c,
        "SELECT cancel_requested,protocol_revision_id FROM anvil.runs WHERE id=%s FOR UPDATE",
        (run_id,),
    )
    if parent["cancel_requested"]:
        raise HTTPException(409, "Cancellation is terminal; it cannot be undone by resume")
    _, blockers = protocol_gates(c, parent["protocol_revision_id"])
    if blockers:
        raise HTTPException(409, "Current frozen execution policy is required")
    active = one(
        c,
        "SELECT count(*) n FROM anvil.benchmark_offline_runtime WHERE run_id=%s AND state IN ('claimed','intent')",
        (run_id,),
    )["n"]
    if active:
        raise HTTPException(409, "A worker still owns this run; reconcile its exact lease first")
    count = one(
        c,
        "SELECT count(*) n FROM anvil.benchmark_offline_runtime WHERE run_id=%s AND state IN ('queued','captured')",
        (run_id,),
    )["n"]
    if not count:
        raise HTTPException(
            409,
            "No untouched queue or durable capture remains; failed/unknown attempts are never retried",
        )
    c.execute(
        "UPDATE anvil.runs SET state='queued',row_version=row_version+1 WHERE id=%s", (run_id,)
    )
    audit(
        c,
        project,
        user,
        "benchmark.resume_requested",
        run_id,
        {
            "checkpoint_event_seq": body.expected_event_seq,
            "resumable": count,
            "new_attempts": 0,
            "new_reservations": 0,
        },
    )
    return {"resumable": count, "new_attempts": 0, "comparison": comparison(c, run_id)}


def attest_stopped(c, project, user, run_id, body):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    current = comparison(c, run_id)
    if current["subject_sha256"] != body.expected_subject_sha256:
        raise HTTPException(409, "Comparison subject changed")
    row = one(
        c,
        "SELECT rt.* FROM anvil.benchmark_cells cell JOIN anvil.benchmark_cell_attempts a ON a.project_id=cell.project_id AND a.cell_id=cell.id AND a.attempt_no=1 JOIN anvil.benchmark_offline_runtime rt ON rt.project_id=a.project_id AND rt.attempt_id=a.id WHERE cell.run_id=%s AND cell.id=%s FOR UPDATE OF rt",
        (run_id, body.cell_id),
    )
    if row is None:
        raise HTTPException(404, "Cell not found")
    event = one(
        c,
        "SELECT event_seq FROM anvil.benchmark_attempt_events WHERE attempt_id=%s ORDER BY event_seq DESC LIMIT 1",
        (row["attempt_id"],),
    )
    if row["state"] != "dispatch_unknown" or event["event_seq"] != body.expected_event_seq:
        raise HTTPException(409, "Exact unknown attempt checkpoint is required")
    if not body.owned_actors_stopped_confirmed:
        raise HTTPException(409, "The human operator must confirm stopped owned actors")
    if one(
        c,
        "SELECT 1 FROM anvil.benchmark_offline_reconciliations WHERE attempt_id=%s",
        (row["attempt_id"],),
    ):
        raise HTTPException(409, "This immutable operator reconciliation already exists")
    evidence = one(
        c,
        "SELECT id,sha256 FROM anvil.artifacts WHERE id=%s AND classification='benchmark_trace'",
        (body.evidence_artifact_id,),
    )
    if evidence is None or evidence["sha256"] != body.evidence_sha256:
        raise HTTPException(403, "Current private operator evidence with exact bytes is required")
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_offline_reconciliations(id,project_id,attempt_id,fence,operator_id,evidence_artifact_id,evidence_sha256,disposition) VALUES(%s,%s,%s,%s,%s,%s,%s,'operator_attested_stopped_outcome_unknown')",
        (
            identifier,
            project,
            row["attempt_id"],
            row["fence"],
            user,
            body.evidence_artifact_id,
            body.evidence_sha256,
        ),
    )
    c.execute(
        "UPDATE anvil.benchmark_capacity_claims SET state='released' WHERE attempt_id=%s AND state='dispatch_unknown'",
        (row["attempt_id"],),
    )
    c.execute(
        "UPDATE anvil.jobs SET status='failed',error_code='operator_stopped_unknown' WHERE target_id=%s AND kind='benchmark_offline_trial'",
        (row["attempt_id"],),
    )
    c.execute(
        "INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence,reason_code) VALUES(%s,%s,%s,'dispatch_unknown','unresolved',%s,'operator_stopped_unknown')",
        (uid(), project, row["attempt_id"], row["fence"]),
    )
    audit(
        c,
        project,
        user,
        "benchmark.unknown_actor_stop_attested",
        row["attempt_id"],
        {
            "reconciliation_id": identifier,
            "outcome": "unknown_unscored",
            "capacity_released": True,
            "retry": False,
        },
    )
    return {
        "reconciliation_id": identifier,
        "outcome": "unknown_unscored",
        "capacity_released": True,
        "retry": False,
        "comparison": comparison(c, run_id),
    }
