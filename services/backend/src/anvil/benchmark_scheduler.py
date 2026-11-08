"""Fenced offline trial claims over canonical comparison identity.

No worker automatically reclaims an intent: an unobserved dispatch is unknown,
even when a lease expired. This module never makes a provider request.
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from anvil.benchmark_execution import protocol_gates
from anvil.benchmark_protocol import Protocol
from anvil.db import one, uid


def claim(c, project, run_id):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    run = one(c, "SELECT r.*,b.protocol_revision_id FROM anvil.runs r JOIN anvil.benchmark_comparisons b ON b.project_id=r.project_id AND b.run_id=r.id WHERE r.id=%s FOR UPDATE OF r", (run_id,))
    if run is None:
        raise HTTPException(404, "Comparison not found")
    if run["cancel_requested"]:
        return None
    projection, blockers = protocol_gates(c, run["protocol_revision_id"])
    if blockers:
        raise HTTPException(409, "Comparison policy no longer permits a claim")
    frozen = Protocol.model_validate(projection["protocol"])
    rows = c.execute("""SELECT rt.*,cell.cell_id,cell.task_revision_id,cell.slot,cell.repetition
        FROM anvil.benchmark_offline_runtime rt JOIN
        (SELECT c.*,c.id cell_id,a.id attempt_id FROM anvil.benchmark_cells c JOIN anvil.benchmark_cell_attempts a
        ON a.project_id=c.project_id AND a.cell_id=c.id AND a.attempt_no=1) cell
        ON cell.project_id=rt.project_id AND cell.attempt_id=rt.attempt_id
        WHERE rt.run_id=%s AND rt.state='queued' ORDER BY cell.task_revision_id,cell.slot,cell.repetition
        FOR UPDATE OF rt""", (run_id,)).fetchall()
    for row in rows:
        slot = frozen.slots[row["slot"]]
        claims = c.execute("SELECT * FROM anvil.benchmark_capacity_claims WHERE project_id=%s AND state<>'released'", (project,)).fetchall()
        if len(claims) >= 3 or any(x["run_id"] == run_id and x["slot"] == row["slot"] for x in claims):
            continue
        if sum(x["provider"] == slot.binding.provider for x in claims) >= slot.provider_concurrency:
            continue
        until = datetime.now(timezone.utc) + timedelta(seconds=frozen.limits.task_timeout_seconds + 120)
        c.execute("INSERT INTO anvil.benchmark_capacity_claims(id,project_id,run_id,cell_id,attempt_id,provider,slot,fence,generation,lease_until,state) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,1,%s,'held')", (uid(), project, run_id, row["cell_id"], row["attempt_id"], slot.binding.provider, row["slot"], row["fence"], until))
        c.execute("UPDATE anvil.benchmark_offline_runtime SET state='claimed',lease_until=%s,updated_at=now() WHERE attempt_id=%s", (until, row["attempt_id"]))
        c.execute("UPDATE anvil.runs SET state='running',row_version=row_version+1 WHERE id=%s", (run_id,))
        return {**row, "lease_until": until, "protocol": frozen}
    return None


def current(c, project, run_id, attempt_id, fence, states):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    row = one(c, "SELECT * FROM anvil.benchmark_offline_runtime WHERE run_id=%s AND attempt_id=%s FOR UPDATE", (run_id, attempt_id))
    if row is None or row["fence"] != fence or row["state"] not in states or row["lease_until"] is None or row["lease_until"] <= datetime.now(timezone.utc):
        raise HTTPException(409, "Trial fence, state or lease is no longer current")
    return row


def intent(c, project, claim):
    current(c, project, claim["run_id"], claim["attempt_id"], claim["fence"], {"claimed"})
    cancelled = one(c, "SELECT cancel_requested FROM anvil.runs WHERE id=%s", (claim["run_id"],))
    if cancelled["cancel_requested"]:
        raise HTTPException(409, "Cancellation precedes dispatch")
    _, blockers = protocol_gates(c, one(c, "SELECT protocol_revision_id FROM anvil.runs WHERE id=%s", (claim["run_id"],))["protocol_revision_id"])
    if blockers:
        raise HTTPException(409, "Comparison policy changed before dispatch")
    c.execute("UPDATE anvil.benchmark_offline_runtime SET state='intent',updated_at=now() WHERE attempt_id=%s", (claim["attempt_id"],))
    c.execute("INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence) VALUES(%s,%s,%s,'running','pending',%s)", (uid(), project, claim["attempt_id"], claim["fence"]))


def expire(c, project, run_id):
    """Explicit reconciliation of elapsed leases; no execution or requeue."""
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    expired = c.execute("SELECT * FROM anvil.benchmark_offline_runtime WHERE run_id=%s AND state IN ('claimed','intent') AND lease_until<now() FOR UPDATE", (run_id,)).fetchall()
    for row in expired:
        unknown = row["state"] == "intent"
        state = "dispatch_unknown" if unknown else "operational_failed"
        validity = "unresolved" if unknown else "invalid"
        c.execute("UPDATE anvil.benchmark_offline_runtime SET state=%s,reason_code='lease_expired',updated_at=now() WHERE attempt_id=%s", (state, row["attempt_id"]))
        c.execute("UPDATE anvil.benchmark_capacity_claims SET state=%s WHERE attempt_id=%s AND state='held'", ("dispatch_unknown" if unknown else "released", row["attempt_id"]))
        c.execute("INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence,reason_code) VALUES(%s,%s,%s,%s,%s,%s,'lease_expired')", (uid(), project, row["attempt_id"], state, validity, row["fence"]))
    return len(expired)
