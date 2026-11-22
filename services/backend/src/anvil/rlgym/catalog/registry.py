"""Mirror of Studio's central registry (environment and data versions only, option B) and environment qualification.

Events arrive as signed webhooks with a registry sequence number. A duplicate is ignored; a gap triggers a resync
from the registry's event log, so the mirror never skips a revoke. The mirror is written only here.
"""

import time

import httpx
from psycopg.types.json import Jsonb

from anvil.rlgym.common import GymError, all_workspaces, emit, new_id, set_scope, sha
from anvil.rlgym.integrations import registry_get, studio_url

CONSUMER = "rlgym-catalog"
IDENTITY = [
    "id",
    "contract_id",
    "version",
    "spec_sha256",
    "image_digest",
    "seed_ref",
    "seed_sha256",
    "seed_family",
]


def registry_id():
    """The registry the mirror currently follows (RLGYM_STUDIO_URL): the local Studio stub or the local Studio."""
    from anvil.rlgym.integrations import studio_url

    return studio_url()


def consumer():
    return f"{CONSUMER}@{registry_id()}"


CHECKS = ["health", "known_fixtures", "write_state", "reset", "state_cleared", "pending_cleared"]
KNOWN_FIXTURES = ["kyc-individual-001", "kyc-teen-joint-003", "kyc-custodial-005"]
VERSION_FIELDS = [
    "id",
    "contract_id",
    "version",
    "spec_sha256",
    "image_digest",
    "seed_ref",
    "seed_sha256",
    "seed_family",
    "runtime_profile",
    "tools",
    "release_id",
    "released_at",
    "reset_strategy",
]
STATE_EVENTS = {
    "version.qualified": "qualified",
    "version.deprecated": "deprecated",
    "version.revoked": "revoked",
    "version.emergency_revoked": "revoked",
    "version.deleted": "deleted",
    "version.failed": "failed",
}


def _identity_conflict(existing, v):
    return [f for f in IDENTITY if str(existing.get(f)) != str(v.get(f))]


def _upsert_version(c, v, seq, state, reg):
    """Insert a version, or confirm it. A different registry may confirm a mirrored version only with the same
    identity; anything else is a conflict, recorded and never applied (released versions are final)."""
    existing = c.execute(
        "SELECT * FROM catalog.environment_versions WHERE id=%s", (v["id"],)
    ).fetchone()
    if not existing:
        clash = c.execute(
            "SELECT id FROM catalog.environment_versions WHERE contract_id=%s AND version=%s",
            (v.get("contract_id"), v.get("version")),
        ).fetchone()
        if clash:
            return [f"id (already released as {clash['id']})"]
    if existing:
        diff = _identity_conflict(existing, v)
        if diff:
            return diff
        c.execute(
            """UPDATE catalog.environment_versions SET state=%s, state_seq=%s, registry=%s,
                 case_catalog=coalesce(%s, case_catalog), mirrored_at=now()
               WHERE id=%s AND (registry<>%s OR state_seq < %s)""",
            (
                state,
                seq,
                reg,
                Jsonb(v.get("case_catalog")) if v.get("case_catalog") else None,
                v["id"],
                reg,
                seq,
            ),
        )
        return []
    c.execute(
        f"""INSERT INTO catalog.environment_versions({",".join(VERSION_FIELDS)},operations,schema_tables,image_recipe,
              case_catalog,state,state_seq,registry)
            VALUES({",".join(["%s"] * len(VERSION_FIELDS))},%s,%s,%s,%s,%s,%s,%s)""",
        (
            *[v.get(f) for f in VERSION_FIELDS],
            Jsonb(v.get("operations")),
            Jsonb(v.get("schema_tables") or []),
            Jsonb(v.get("image_recipe")),
            Jsonb(v.get("case_catalog")),
            state,
            seq,
            reg,
        ),
    )
    return []


def _conflict(c, vid, diff, reg, kind):
    for ws in all_workspaces(c):
        set_scope(c, ws["id"])
        emit(
            c,
            ws["id"],
            "registry.identity_conflict",
            vid,
            {"version_id": vid, "registry": reg, "fields": diff, "event": kind},
        )


def apply_event(c, ev, via):
    from anvil.rlgym.catalog import inbox
    from anvil.rlgym.projects import service as projects

    data = ev["data"]
    seq = int(data["seq"])
    reg = registry_id()
    if c.execute(
        "SELECT 1 FROM catalog.registry_events WHERE registry=%s AND seq=%s", (reg, seq)
    ).fetchone():
        return False
    c.execute(
        "INSERT INTO catalog.registry_events(registry,seq,event_id,type,subject,payload,via) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (reg, seq, ev["id"], ev["type"], ev.get("subject", ""), Jsonb(ev), via),
    )
    kind = ev["type"]
    if kind == "version.registered":
        diff = _upsert_version(c, data["version"], seq, "registered", reg)
        if diff:
            _conflict(c, data["version"]["id"], diff, reg, kind)
    elif kind in STATE_EVENTS:
        vid = data["version"]["id"]
        diff = _upsert_version(c, data["version"], seq - 1 if seq > 1 else 0, "registered", reg)
        if diff:
            _conflict(c, vid, diff, reg, kind)
            return True
        c.execute(
            """UPDATE catalog.environment_versions SET state=%s, state_reason=%s, state_seq=%s, registry=%s, mirrored_at=now()
               WHERE id=%s AND (registry<>%s OR state_seq < %s)""",
            (STATE_EVENTS[kind], data.get("reason"), seq, reg, vid, reg, seq),
        )
        for ws in all_workspaces(c):
            set_scope(c, ws["id"])
            projects.reselect_all(
                c,
                ws["id"],
                trigger={"event": kind, "version_id": vid, "reason": data.get("reason")},
            )
            emit(
                c,
                ws["id"],
                f"registry.{kind}",
                vid,
                {"version_id": vid, "reason": data.get("reason")},
            )
    elif kind == "inbox_item.status":
        for ws in all_workspaces(c):
            set_scope(c, ws["id"])
            inbox.status_changed(c, ws["id"], data["item"])
    return True


def receive(ev, via="webhook"):
    """Apply one webhook event in sequence order, resyncing on a gap."""
    from anvil.rlgym.common import system_scope

    seq = int(ev["data"]["seq"])
    with system_scope() as c:
        c.execute(
            "INSERT INTO catalog.registry_cursor(consumer,last_seq) VALUES(%s,0) ON CONFLICT DO NOTHING",
            (consumer(),),
        )
        last = c.execute(
            "SELECT last_seq FROM catalog.registry_cursor WHERE consumer=%s FOR UPDATE",
            (consumer(),),
        ).fetchone()["last_seq"]
        if seq <= last:
            return {"status": "duplicate", "last_seq": last}
        applied, top = 0, last
        if seq > last + 1:
            # Gap: replay the registry's own log in order; the cursor moves only as far as events really applied.
            log = registry_get("/events", {"after_seq": last})
            for item in sorted(log["events"], key=lambda e: e["data"]["seq"]):
                if item["data"]["seq"] <= seq:
                    applied += apply_event(c, item, "resync")
                    top = max(top, int(item["data"]["seq"]))
            c.execute(
                "UPDATE catalog.registry_cursor SET resynced_at=now() WHERE consumer=%s",
                (consumer(),),
            )
        else:
            applied += apply_event(c, ev, via)
            top = seq
        c.execute(
            "UPDATE catalog.registry_cursor SET last_seq=%s, updated_at=now() WHERE consumer=%s",
            (top, consumer()),
        )
        return {
            "status": "applied" if top >= seq else "gap_unresolved",
            "applied": applied,
            "last_seq": top,
            "resynced": seq > last + 1,
        }


def resync():
    """Pull every event after the cursor (used at startup and by the gap path)."""
    from anvil.rlgym.common import system_scope

    with system_scope() as c:
        c.execute(
            "INSERT INTO catalog.registry_cursor(consumer,last_seq) VALUES(%s,0) ON CONFLICT DO NOTHING",
            (consumer(),),
        )
        last = c.execute(
            "SELECT last_seq FROM catalog.registry_cursor WHERE consumer=%s FOR UPDATE",
            (consumer(),),
        ).fetchone()["last_seq"]
        log = registry_get("/events", {"after_seq": last})
        top = last
        for item in sorted(log["events"], key=lambda e: e["data"]["seq"]):
            apply_event(c, item, "resync")
            top = max(top, int(item["data"]["seq"]))
        c.execute(
            "UPDATE catalog.registry_cursor SET last_seq=%s, resynced_at=now(), updated_at=now() WHERE consumer=%s",
            (top, consumer()),
        )
        return {"last_seq": top, "applied": top - last}


# --- qualification -------------------------------------------------------------------------------------------


def _probe(client, base, check):
    """One check against the environment endpoint. Returns (ok, evidence). Raises httpx errors on infrastructure."""
    if check == "health":
        r = client.get(base + "/health")
        return r.status_code == 200 and r.json().get("status") == "ok", {"status": r.status_code}
    if check == "known_fixtures":
        r = client.get(base + "/fixtures", params={"ids": ",".join(KNOWN_FIXTURES)})
        found = r.json().get("found", []) if r.status_code == 200 else []
        return sorted(found) == sorted(KNOWN_FIXTURES), {"expected": KNOWN_FIXTURES, "found": found}
    if check == "write_state":
        r = client.post(
            base + "/tools/finding.write",
            json={"case_id": KNOWN_FIXTURES[0], "text": "qualification probe"},
        )
        state = client.get(base + "/state").json()
        return r.status_code == 200 and state.get("writable_rows", 0) > 0, {
            "writable_rows": state.get("writable_rows")
        }
    if check == "reset":
        r = client.post(base + "/reset")
        return r.status_code == 200, {"status": r.status_code}
    if check == "state_cleared":
        state = client.get(base + "/state").json()
        return state.get("writable_rows", 1) == 0, {
            "writable_rows": state.get("writable_rows"),
            "rows": state.get("rows", []),
        }
    if check == "pending_cleared":
        pending = client.get(base + "/pending").json()
        return pending.get("pending", 1) == 0, {"pending": pending.get("pending")}
    raise ValueError(check)


LIKELY_CAUSE = {
    "state_cleared": "finding.write writes `findings` but the reset does not restore it",
    "pending_cleared": "queued work survives the reset",
    "known_fixtures": "the seed snapshot does not contain the template's known fixtures",
    "write_state": "the write operation does not persist",
    "health": "the environment does not report ready",
    "reset": "the reset operation is refused",
}


def qualify(version_id, requested_by="registry", attempt=1):
    """Run the six checks in a disposable episode of the version (locally: the Studio stub's environment
    simulator; Docker-built environments arrive with work package 2.7). Infrastructure failures retry once."""
    from anvil.rlgym.common import system_scope

    with system_scope() as c:
        v = c.execute(
            "SELECT * FROM catalog.environment_versions WHERE id=%s", (version_id,)
        ).fetchone()
    if not v:
        raise GymError("NOT_FOUND", "Version not in the registry mirror")
    base = f"{studio_url()}/stub/env/{version_id}"
    episode = new_id("qep-")
    checks, failure_class = [], None
    try:
        with httpx.Client(timeout=5, trust_env=False) as client:
            client.post(base + "/episodes", json={"episode": episode})
            for name in CHECKS:
                ok, evidence = _probe(client, base, name)
                checks.append(
                    {"name": name, "result": "pass" if ok else "fail", "evidence": evidence}
                )
                if not ok:
                    failure_class = "environment_defect"
                    checks[-1]["likely_cause"] = LIKELY_CAUSE[name]
                    break
    except (httpx.HTTPError, ValueError) as exc:
        failure_class = "infrastructure"
        checks.append(
            {
                "name": CHECKS[len(checks)] if len(checks) < len(CHECKS) else "runner",
                "result": "fail",
                "evidence": {"error": type(exc).__name__},
                "likely_cause": "runner lost or environment unreachable",
            }
        )
    if failure_class == "infrastructure" and attempt < 2:
        time.sleep(0.5)
        return qualify(version_id, requested_by, attempt + 1)
    result = "failed" if failure_class else "qualified"
    receipt = {
        "subject": {"kind": "environment_version", "id": version_id, "sha256": v["spec_sha256"]},
        "checks": checks,
        "result": result,
        "failure_class": failure_class,
        "episode": episode,
        "mode": "stub_environment_simulator",
        "attempt": attempt,
    }
    receipt_id = "qr-" + sha(receipt)[:12]
    with system_scope() as c:
        previous = c.execute(
            """SELECT result FROM catalog.qualification_receipts WHERE subject_kind='environment_version' AND subject_id=%s
               ORDER BY issued_at DESC LIMIT 1""",
            (version_id,),
        ).fetchone()
        c.execute(
            """INSERT INTO catalog.qualification_receipts(receipt_id,subject_kind,subject_id,subject_version,result,failure_class,mode,checks,receipt_sha256)
               VALUES(%s,'environment_version',%s,%s,%s,%s,'stub_environment_simulator',%s,%s) ON CONFLICT DO NOTHING""",
            (
                receipt_id,
                version_id,
                str(v["version"]),
                result,
                failure_class,
                Jsonb(checks),
                sha(receipt),
            ),
        )
        c.execute(
            "INSERT INTO infra.outbox(id,workspace_id,topic,key,payload,destination) VALUES(gen_random_uuid(),NULL,'registry.receipt',%s,%s,'registry')",
            (
                version_id,
                Jsonb({"type": "registry.receipt", "data": {"receipt_id": receipt_id, **receipt}}),
            ),
        )
        requalification_failed = result == "failed" and (
            v["state"] == "qualified" or (previous and previous["result"] == "qualified")
        )
        if result == "failed" or (previous and previous["result"] == "failed"):
            from anvil.rlgym.projects import service as projects

            for ws in all_workspaces(c):
                set_scope(c, ws["id"])
                projects.reselect_all(
                    c,
                    ws["id"],
                    trigger={
                        "event": "qualification.failed"
                        if result == "failed"
                        else "qualification.passed",
                        "version_id": version_id,
                        "receipt_id": receipt_id,
                        "urgent": requalification_failed,
                        "failure_class": failure_class,
                        "checks": checks,
                    },
                )
    return {"receipt_id": receipt_id, **receipt}


def latest_receipts(c, version_id, limit=5):
    return c.execute(
        """SELECT * FROM catalog.qualification_receipts WHERE subject_kind='environment_version' AND subject_id=%s
           ORDER BY issued_at DESC LIMIT %s""",
        (version_id, limit),
    ).fetchall()
