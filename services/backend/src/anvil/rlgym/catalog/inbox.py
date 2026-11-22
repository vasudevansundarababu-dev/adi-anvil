"""Studio's next-version inbox (D17, PLATFORM.md): the one channel for more data, new case kinds, environment
defects, evaluator defects (only when the S7 criterion itself must change) and template wording. No item changes a
released version or a task; Studio answers with status events."""

import datetime as dt

from psycopg.types.json import Jsonb

from anvil.rlgym.common import GymError, audit, emit, new_id, require

KINDS = {"more_data", "new_case_kind", "environment_defect", "evaluator_defect", "template_wording"}


def _link(item):
    if item["kind"] == "environment_defect" and item.get("environment_version_id"):
        return f"/gym/admin/environments/{item['environment_version_id']}"
    if item.get("project_id"):
        return f"/gym/projects/{item['project_id']}"
    return f"/gym/admin/templates/{item['template_id']}/{item['template_version']}"


def create(c, ws, actor, body, urgent=False):
    kind = body.get("kind")
    require(kind in KINDS, "VALIDATION_FAILED", "Unknown inbox item kind", field="kind")
    summary = (body.get("summary") or "").strip()
    require(summary, "VALIDATION_FAILED", "A summary for Studio is required", field="summary")
    require(
        body.get("template_id") and body.get("version"),
        "VALIDATION_FAILED",
        "template_id and version are required",
    )
    if kind == "environment_defect":
        require(
            body.get("environment_version"),
            "VALIDATION_FAILED",
            "environment_version is required",
            field="environment_version",
        )
        open_item = c.execute(
            """SELECT id FROM catalog.inbox_items WHERE workspace_id=%s AND kind='environment_defect'
               AND environment_version_id=%s AND state NOT IN ('declined','closed','released')""",
            (ws, body["environment_version"]),
        ).fetchone()
        if open_item:
            raise GymError(
                "CONFLICT",
                "An environment defect item is already open for this version",
                {"item": open_item["id"]},
            )
    if kind == "evaluator_defect":
        require(
            body.get("criterion_text_must_change") is True,
            "VALIDATION_FAILED",
            "Grader fixes are new RL Gym configuration versions; send evaluator_defect only when the S7 criterion itself must change",
            field="criterion_text_must_change",
        )
    needed_by = body.get("needed_by")
    if needed_by:
        try:
            needed_by = dt.date.fromisoformat(needed_by)
        except ValueError:
            raise GymError(
                "VALIDATION_FAILED", "needed_by must be a date", {"field": "needed_by"}
            ) from None
    item_id = new_id("rgi-")
    evidence = body.get("evidence") or {}
    if kind == "new_case_kind":
        evidence = {**evidence, "edge_case": edge_case_parts(body.get("edge_case"))}
    c.execute(
        """INSERT INTO catalog.inbox_items(id,workspace_id,project_id,suite_version_id,kind,template_id,template_version,
             environment_version_id,evaluator_configuration,summary,evidence,needed_by,urgent,state,sent_by,timeline)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued',%s,%s)""",
        (
            item_id,
            ws,
            body.get("project_id"),
            body.get("suite_version_id"),
            kind,
            body["template_id"],
            int(body["version"]),
            body.get("environment_version"),
            body.get("evaluator_configuration"),
            summary,
            Jsonb(evidence),
            needed_by,
            urgent,
            actor.id if hasattr(actor, "id") else str(actor),
            Jsonb([{"state": "queued", "at": dt.datetime.now(dt.UTC).isoformat()}]),
        ),
    )
    payload = {
        "_item_id": item_id,
        "kind": kind,
        "source": "rlgym",
        "template_id": body["template_id"],
        "version": int(body["version"]),
        "environment_version": body.get("environment_version"),
        "evaluator_configuration": body.get("evaluator_configuration"),
        "project_id": body.get("project_id"),
        "summary": summary,
        "evidence": evidence,
        "needed_by": needed_by.isoformat() if needed_by else None,
        "urgent": urgent,
        "rlgym_item_id": item_id,
    }
    emit(c, ws, "inbox_item.send", item_id, payload, destination="studio")
    audit(c, ws, actor, "inbox_item.created", item_id, details={"kind": kind, "urgent": urgent})
    row = c.execute("SELECT * FROM catalog.inbox_items WHERE id=%s", (item_id,)).fetchone()
    emit(c, ws, "inbox_item.status", item_id, {**_status_payload(row)})
    return row


EDGE_PARTS = ("scenario_context", "twist", "expected_outcome")


def edge_case_parts(edge):
    """A new case kind carries the same four plain-English parts as an S4 edge case (2.12): scenario context, the
    edge-case twist, the expected outcome and rationale, and slice tags (complexity, archetype)."""
    edge = edge or {}
    missing = [k for k in EDGE_PARTS if not str(edge.get(k) or "").strip()]
    tags = edge.get("slice_tags") or {}
    missing += [
        f"slice_tags.{k}" for k in ("complexity", "archetype") if not str(tags.get(k) or "").strip()
    ]
    require(
        not missing,
        "VALIDATION_FAILED",
        "A new case kind needs the four parts: scenario context, twist, expected outcome and rationale, slice tags",
        field="edge_case",
        missing=missing,
    )
    return {
        **{k: str(edge[k]).strip() for k in EDGE_PARTS},
        "rationale": str(edge.get("rationale") or "").strip() or None,
        "slice_tags": {k: str(tags[k]).strip() for k in ("complexity", "archetype")},
    }


def _status_payload(row):
    return {
        "item_id": row["id"],
        "label": row["studio_id"] or row["id"],
        "kind": row["kind"],
        "state": row["state"],
        "summary": row["summary"],
        "project_id": row["project_id"],
        "planned_version": row["planned_version"],
        "released_version": row["released_version"],
        "decline_reason": row["decline_reason"],
        "link": _link(row),
    }


def accepted(c, ws, item_id, result):
    """Studio answered 202 {id}: record Studio's id."""
    studio_id = result.get("id")
    row = c.execute(
        """UPDATE catalog.inbox_items SET state='sent', studio_id=%s,
             timeline=timeline || jsonb_build_array(jsonb_build_object('state','sent','at',now(),'studio_id',%s::text))
           WHERE workspace_id=%s AND id=%s AND state='queued' RETURNING *""",
        (studio_id, studio_id, ws, item_id),
    ).fetchone()
    if row:
        emit(c, ws, "inbox_item.status", item_id, _status_payload(row))


def status_changed(c, ws, item):
    """`inbox_item.status` from Studio (received, planned, released, declined)."""
    state = item.get("state")
    if state not in ("received", "planned", "released", "declined"):
        return
    row = c.execute(
        """UPDATE catalog.inbox_items SET state=%s, planned_version=coalesce(%s, planned_version),
             released_version=coalesce(%s, released_version), decline_reason=coalesce(%s, decline_reason),
             timeline=timeline || jsonb_build_array(jsonb_build_object('state',%s::text,'at',now(),
               'planned_version',%s::text,'released_version',%s::text,'decline_reason',%s::text))
           WHERE workspace_id=%s AND (studio_id=%s OR (studio_id IS NULL AND id=%s)) RETURNING *""",
        (
            state,
            item.get("planned_version"),
            item.get("released_version"),
            item.get("decline_reason"),
            state,
            item.get("planned_version"),
            item.get("released_version"),
            item.get("decline_reason"),
            ws,
            item["id"],
            # Studio may push "received" inside the request that creates the item, before the RL Gym has stored
            # Studio's id; the RL Gym's own id (rlgym_item_id) then finds it.
            item.get("rlgym_item_id"),
        ),
    ).fetchone()
    if row and not row["studio_id"]:
        row = c.execute(
            "UPDATE catalog.inbox_items SET studio_id=%s WHERE id=%s RETURNING *",
            (item["id"], row["id"]),
        ).fetchone()
    if row:
        emit(c, ws, "inbox_item.status", row["id"], _status_payload(row))


def close_for_version(c, ws, contract_id, qualified_version_id):
    """When a released version qualifies, the RL Gym closes the environment-defect items it answered."""
    rows = c.execute(
        """UPDATE catalog.inbox_items SET state='closed',
             timeline=timeline || jsonb_build_array(jsonb_build_object('state','qualified','at',now(),'version',%s::text))
           WHERE workspace_id=%s AND kind='environment_defect' AND state='released' AND released_version=%s RETURNING *""",
        (qualified_version_id, ws, qualified_version_id),
    ).fetchall()
    for row in rows:
        emit(c, ws, "inbox_item.status", row["id"], {**_status_payload(row), "state": "closed"})


def list_items(
    c, ws, kind=None, state=None, template_id=None, environment_version=None, project_id=None
):
    sql, params = "SELECT * FROM catalog.inbox_items WHERE workspace_id=%s", [ws]
    for col, val in [
        ("kind", kind),
        ("state", state),
        ("template_id", template_id),
        ("environment_version_id", environment_version),
        ("project_id", project_id),
    ]:
        if val:
            sql += f" AND {col}=%s"
            params.append(val)
    return c.execute(sql + " ORDER BY sent_at DESC", params).fetchall()
