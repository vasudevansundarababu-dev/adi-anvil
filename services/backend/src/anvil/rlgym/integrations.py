"""Outbound integrations (local stubs only): Studio registry and inbox, ADI Forge. Plus the outbox dispatcher.

Base URLs come from RLGYM_STUDIO_URL / RLGYM_FORGE_URL and must be loopback: this build never talks to a real
Studio, registry or ADI Forge.
"""

import json
import logging
import os
import threading
import time
from urllib.parse import urlsplit

import httpx

from anvil.rlgym.common import GymError, set_scope, sign, system_scope

log = logging.getLogger("anvil.rlgym.dispatcher")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _base(name, default):
    url = os.environ.get(name, default).rstrip("/")
    host = urlsplit(url).hostname
    if host not in LOOPBACK:
        raise RuntimeError(f"{name} must point at a local stub (loopback), not {host}")
    return url


STUB_STUDIO = "http://127.0.0.1:8211"


def studio_url():
    return _base("RLGYM_STUDIO_URL", STUB_STUDIO)


def loopback(url):
    """A recorded registry URL (where a mirrored version came from); loopback only, like the configured ones."""
    url = (url or "").rstrip("/")
    if urlsplit(url).hostname not in LOOPBACK:
        raise RuntimeError(f"registry {url!r} is not a local (loopback) registry")
    return url


def forge_url():
    return _base("RLGYM_FORGE_URL", "http://127.0.0.1:8212")


def _headers(extra=None):
    return {"Authorization": f"Bearer {os.environ.get('RLGYM_ANVIL_KEY', '')}", **(extra or {})}


def registry_get(path, params=None, audience=None, timeout=10, base=None):
    """Read from a registry. `base` is the registry a mirrored version came from (its own data is read there, so the
    stub's versions keep working after the RL Gym switches to Studio); default: the registry followed now."""
    extra = {"X-ADI-Audience": audience} if audience else None
    root = loopback(base) if base else studio_url()
    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            r = client.get(root + "/api/v1/registry" + path, params=params, headers=_headers(extra))
    except httpx.HTTPError as exc:
        raise GymError(
            "REGISTRY_UNAVAILABLE",
            "Studio's registry is not answering; try again",
            {"cause": type(exc).__name__},
        ) from None
    if r.status_code == 404:
        raise GymError("NOT_FOUND", "Not in the registry")
    if r.status_code >= 400:
        raise GymError("REGISTRY_UNAVAILABLE", f"Registry answered {r.status_code}")
    return r.json()


def forge_package(task):
    """Fetch an exported task package from ADI Forge (or its stub) by `package_sha256`, always from the configured
    ADI Forge URL with the RL Gym's key. `package_ref` is provenance only and is never followed: it must be
    `stub://forge/…` or `forge://packages/<package_sha256>` (the same hash); anything else is refused."""
    ref = task.get("package_ref", "")
    forge_ref = f"forge://packages/{task.get('package_sha256')}"
    if not (ref.startswith("stub://forge/") or ref == forge_ref):
        raise GymError(
            "VALIDATION_FAILED",
            "package_ref must be forge://packages/<package_sha256> (or a stub://forge/ reference)",
            {"task_id": task.get("task_id")},
        )
    try:
        with httpx.Client(timeout=10, trust_env=False) as client:
            r = client.get(
                f"{forge_url()}/api/v1/packages/{task['package_sha256']}", headers=_headers()
            )
    except httpx.HTTPError:
        raise GymError("FORGE_UNAVAILABLE", "ADI Forge is not answering; try again") from None
    if r.status_code != 200:
        raise GymError(
            "FORGE_UNAVAILABLE", f"ADI Forge answered {r.status_code} for {task['task_id']}"
        )
    return r.content


DESTINATIONS = {
    # topic → (destination base, path)
    "inbox_item.send": ("studio", "/api/v1/inbox-items"),
    "registry.receipt": ("studio", "/api/v1/registry/receipts"),
    "registry.usage": ("studio", "/api/v1/registry/usage"),
    "evaluator.event": ("studio", "/api/v1/rlgym-events"),
    "forge.template_qualification": (
        "forge",
        "/api/v1/integrations/anvil/templates/qualifications",
    ),
    "forge.run_review": ("forge", None),
}


class Refused(RuntimeError):
    """The receiver refused the content (4xx other than 408/429): retrying the same body cannot succeed."""


def wire_payload(topic, payload):
    """The body as the receiver's contract wants it. Inbox items: `evidence[]` is a list (REGISTRY.md: one entry per
    data-plan cell plus the plan-level fields); the RL Gym keeps the object form internally."""
    if topic != "inbox_item.send":
        return payload
    evidence = payload.get("evidence")
    if isinstance(evidence, list):
        return payload
    evidence = dict(evidence or {})
    entries = []
    if isinstance(evidence.get("cells"), list):
        entries = [{"type": "cell", **cell} for cell in evidence.pop("cells")]
    if evidence:
        entries.append({"type": "plan" if entries else "detail", **evidence})
    return {**payload, "evidence": entries}


def deliver(row):
    body = row["payload"]["data"]
    dest = row["destination"]
    if body.get("_base"):
        base = loopback(
            body["_base"]
        )  # a receipt goes back to the registry that released the version
    else:
        base = studio_url() if dest in ("studio", "registry") else forge_url()
    path = body.get("_path") or DESTINATIONS.get(row["topic"], (None, None))[1]
    if not path:
        raise RuntimeError(f"no route for {row['topic']}")
    payload = wire_payload(row["topic"], {k: v for k, v in body.items() if not k.startswith("_")})
    raw = (
        json.dumps({**row["payload"], "data": payload}, sort_keys=True).encode()
        if row["topic"] == "evaluator.event"
        else json.dumps(payload).encode()
    )
    ts = str(int(time.time()))
    headers = _headers(
        {
            **(body.get("_headers") or {}),
            "Content-Type": "application/json",
            "Idempotency-Key": str(row["id"]),
            "X-ADI-Timestamp": ts,
            "X-ADI-Signature": sign(os.environ.get("RLGYM_REGISTRY_WEBHOOK_SECRET", ""), ts, raw),
        }
    )
    with httpx.Client(timeout=10, trust_env=False) as client:
        r = client.post(base + path, content=raw, headers=headers)
    if r.status_code >= 300:
        if 400 <= r.status_code < 500 and r.status_code not in (408, 429):
            raise Refused(f"{dest} refused it ({r.status_code}): {r.text[:300]}")
        raise RuntimeError(f"{dest} answered {r.status_code}: {r.text[:200]}")
    return r.json() if r.content else {}


def dispatch_once(limit=50):
    """Deliver pending external outbox rows in order. Each row is delivered at most once successfully; failures
    stay pending with the error recorded and are retried (Idempotency-Key = outbox id)."""
    from anvil.rlgym.catalog import inbox

    delivered = 0
    with system_scope() as c:
        rows = c.execute(
            """SELECT * FROM infra.outbox WHERE published_at IS NULL AND destination <> 'internal' AND attempts < 20
               AND NOT refused AND (next_attempt_at IS NULL OR next_attempt_at <= now())
               ORDER BY created_at LIMIT %s FOR UPDATE SKIP LOCKED""",
            (limit,),
        ).fetchall()
        for row in rows:
            try:
                result = deliver(row)
            except (
                Refused
            ) as exc:  # the receiver refused this body: never retried; shown as a To do card
                c.execute(
                    "UPDATE infra.outbox SET attempts=attempts+1, refused=true, last_error=%s WHERE id=%s",
                    (str(exc)[:500], row["id"]),
                )
                if row["workspace_id"]:
                    from anvil.rlgym.common import emit

                    set_scope(c, row["workspace_id"])
                    emit(
                        c,
                        row["workspace_id"],
                        "delivery.refused",
                        str(row["id"]),
                        {
                            "topic": row["topic"],
                            "key": row["key"],
                            "destination": row["destination"],
                            "error": str(exc)[:300],
                        },
                    )
                continue
            except (
                Exception
            ) as exc:  # recorded, retried later with growing waits (2 s, 4 s … up to 5 min)
                c.execute(
                    """UPDATE infra.outbox SET attempts=attempts+1, last_error=%s,
                         next_attempt_at=now() + make_interval(secs => least(300, power(2, attempts + 1)))
                       WHERE id=%s""",
                    (str(exc)[:500], row["id"]),
                )
                continue
            c.execute(
                "UPDATE infra.outbox SET published_at=now(), attempts=attempts+1, last_error=NULL WHERE id=%s",
                (row["id"],),
            )
            if row["topic"] == "forge.run_review" and row["workspace_id"]:
                from anvil.rlgym.results import sme

                set_scope(c, row["workspace_id"])
                sme.sent(c, row["workspace_id"], row["payload"]["data"]["_batch_id"], result)
            if row["workspace_id"]:
                # A later delivery of the same item closes any "Delivery refused" card for it.
                from anvil.rlgym.admin import todo

                set_scope(c, row["workspace_id"])
                todo.close_items(
                    c, row["workspace_id"], None, "delivery_refused", subject=row["key"]
                )
            if row["topic"] == "inbox_item.send" and row["workspace_id"]:
                set_scope(c, row["workspace_id"])
                inbox.accepted(c, row["workspace_id"], row["payload"]["data"]["_item_id"], result)
            delivered += 1
    return delivered


_started = False


def start_dispatcher(interval=1.5):
    global _started
    if (
        _started
        or os.environ.get("RLGYM_V2", "0") != "1"
        or os.environ.get("RLGYM_DISPATCHER", "on") == "off"
    ):
        return
    _started = True

    def loop():
        while True:
            try:
                dispatch_once()
            except Exception as exc:  # keep the loop alive; the outbox keeps the work
                log.warning("dispatch pass failed: %s", type(exc).__name__)
            time.sleep(interval)

    threading.Thread(target=loop, name="rlgym-dispatcher", daemon=True).start()
