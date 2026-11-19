"""Durable notifications; explicit server caller only, no implicit live dispatcher."""

from anvil.db import Jsonb, uid
from anvil.praxis_generic_contract import RevocationEvent, digest
from anvil.praxis_template_client import PraxisCallError, qualification_envelope


def enqueue(c, project, user, kind, body, event_key):
    if kind == "qualification" and body.get("publication_basis", {}).get("kind") == "po_attested_offline":
        raise ValueError("Local offline PO provenance has no authenticated Authoring delivery contract")
    if kind == "revocation":
        RevocationEvent.model_validate(body)
    envelope = (
        {"kind": kind, "event": body, "event_sha256": digest(body)}
        if kind == "revocation"
        else qualification_envelope(body)
    )
    fingerprint = digest(envelope)
    old = c.execute(
        "SELECT * FROM anvil.praxis_template_events WHERE project_id=%s AND event_key=%s",
        (project, event_key),
    ).fetchone()
    if old:
        if old["body_sha256"] != fingerprint:
            raise ValueError("Event identity is immutable")
        return old
    return c.execute(
        "INSERT INTO anvil.praxis_template_events(id,project_id,event_key,kind,body,body_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (uid(), project, event_key, kind, Jsonb(envelope), fingerprint, user),
    ).fetchone()


def pending(c, project):
    # Offline acknowledgements cannot suppress real delivery.
    return c.execute(
        "SELECT e.* FROM anvil.praxis_template_events e WHERE e.project_id=%s AND NOT EXISTS(SELECT 1 FROM anvil.praxis_template_delivery_attempts a WHERE a.project_id=e.project_id AND a.event_id=e.id AND a.status='acknowledged') AND NOT EXISTS(SELECT 1 FROM anvil.praxis_template_events successor WHERE successor.project_id=e.project_id AND successor.event_key='qualification-wire-v2:'||e.id::text) ORDER BY e.created_at,e.id LIMIT 100",
        (project,),
    ).fetchall()


def upgrade_pending_qualifications(c, project, user, *, limit=100, after=None):
    """Append a new wire event; never change a receipt or an old attempt identity.

    Acknowledged events remain acknowledged. Ambiguous or conflicting prior
    sends require reconciliation; changing their body under the same remote
    idempotency key would be unsafe. This helper makes no network request.
    """
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    if not c.execute(
        "SELECT anvil.benchmark_is_admin(%s,%s) AS allowed", (project, user)
    ).fetchone()["allowed"]:
        raise ValueError("Active sponsoring project Admin required")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Bounded upgrade batch required")
    if after and not c.execute("SELECT 1 FROM anvil.praxis_template_events WHERE project_id=%s AND id=%s", (project, after)).fetchone():
        raise ValueError("Cursor must name this project's retained event")
    rows = c.execute(
        "SELECT e.* FROM anvil.praxis_template_events e WHERE e.project_id=%s AND e.kind='qualification' AND e.body->>'kind'='qualification' AND NOT EXISTS(SELECT 1 FROM anvil.praxis_template_delivery_attempts a WHERE a.project_id=e.project_id AND a.event_id=e.id AND a.status='acknowledged') AND NOT EXISTS(SELECT 1 FROM anvil.praxis_template_events s WHERE s.project_id=e.project_id AND s.event_key='qualification-wire-v2:'||e.id::text) AND (%s::uuid IS NULL OR (e.created_at,e.id)>(SELECT created_at,id FROM anvil.praxis_template_events WHERE project_id=e.project_id AND id=%s)) ORDER BY e.created_at,e.id LIMIT %s",
        (project, after, after, limit),
    ).fetchall()
    result = []
    for old in rows:
        body = old["body"]
        if digest(body) != old["body_sha256"] or digest(body["receipt"]) != body.get("receipt_sha256"):
            raise ValueError("Legacy qualification integrity changed")
        attempts = c.execute(
            "SELECT status,result FROM anvil.praxis_template_delivery_attempts WHERE project_id=%s AND event_id=%s",
            (project, old["id"]),
        ).fetchall()
        known_rejections = {"praxis_http_400", "praxis_http_401", "praxis_http_403", "praxis_http_404", "praxis_http_422", "praxis_legacy_qualification_wire_upgrade_required"}
        if any(a["status"] != "failed" or a["result"].get("code") not in known_rejections for a in attempts):
            result.append({"event_id": str(old["id"]), "status": "reconciliation_required"})
            continue
        successor = enqueue(c, project, user, "qualification", body["receipt"], "qualification-wire-v2:" + str(old["id"]))
        result.append({"event_id": str(old["id"]), "successor_event_id": str(successor["id"]), "status": "wire_upgrade_prepared"})
    return {"items": result, "scanned": len(rows), "next_cursor": str(rows[-1]["id"]) if len(rows) == limit else None, "network_requests": 0}


def deliver(c, project, user, event_id, client):
    """One attempt, never retries here. Caller commits the attempt, even on failure.

    A project lock serializes bounded attempts. The supplied client is configured
    by trusted server code, never from uploaded author data or an arbitrary URL.
    An ambiguous POST can be repeated only with this same durable identity/body.
    """
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    if not c.execute(
        "SELECT anvil.benchmark_is_admin(%s,%s) AS allowed", (project, user)
    ).fetchone()["allowed"]:
        raise ValueError("Active sponsoring project Admin required")
    row = c.execute(
        "SELECT * FROM anvil.praxis_template_events WHERE project_id=%s AND id=%s",
        (project, event_id),
    ).fetchone()
    if not row or digest(row["body"]) != row["body_sha256"]:
        raise ValueError("Unknown or corrupt event")
    prior = c.execute(
        "SELECT result FROM anvil.praxis_template_delivery_attempts WHERE project_id=%s AND event_id=%s AND status='acknowledged' LIMIT 1",
        (project, event_id),
    ).fetchone()
    if prior:
        return {"status": "already_acknowledged", "event_id": str(event_id)}
    try:
        if row["kind"] == "qualification" and row["body"].get("kind") == "qualification":
            raise PraxisCallError("praxis_legacy_qualification_wire_upgrade_required")
        body = row["body"].get("event", row["body"].get("receipt"))
        from anvil.praxis_template_registry import environment

        if body.get("project_id") != str(project) or body.get("environment") != environment():
            raise PraxisCallError("praxis_event_environment_mismatch")
        if client.origin != "offline_fixture" and body.get("environment") == "local":
            raise PraxisCallError("praxis_local_event_live_delivery_forbidden")
        reply = client.call(
            "POST",
            "/qualifications",
            row["body"],
            idempotency_key="anvil-template-event-" + str(row["id"]),
        )["data"]
        expected = (
            {
                "event_id": body["event_id"],
                "event_sha256": digest(body),
                "sequence": body["sequence"],
            }
            if row["kind"] == "revocation"
            else {"receipt_id": body["receipt_id"], "receipt_sha256": digest(body)}
        )
        if reply.get("status") not in {"applied", "already_applied"} or any(
            type(reply.get(k)) is not type(v) or reply[k] != v for k, v in expected.items()
        ):
            raise PraxisCallError("praxis_acknowledgement_invalid", ambiguous=True)
        status = "offline_fixture" if client.origin == "offline_fixture" else "acknowledged"
        safe = expected | {"status": status}
    except PraxisCallError as exc:
        status = "ambiguous" if exc.ambiguous else "failed"
        safe = {"status": status, "code": exc.code, "upstream_code": exc.remote_code, "upstream_request_id": exc.request_id}
    c.execute(
        "INSERT INTO anvil.praxis_template_delivery_attempts(id,project_id,event_id,status,result,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
        (uid(), project, event_id, status, Jsonb(safe), user),
    )
    return safe
