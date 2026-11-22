"""LOCAL STUB of Studio and its central registry (work package 2.1). Not the real Studio.

Serves ARCHITECTURE 9.4 registry reads (environment versions by contract and seed family, case catalog, event log),
receives qualification receipts, usage and next-version inbox items from the RL Gym, and calls into the RL Gym:
signed registry events, qualification requests, A-06 evaluator creation/tests and A-03 template activation.
It also hosts a tiny per-version environment simulator so the RL Gym's six qualification checks run against a real
HTTP endpoint (Docker-built golden-kyc-openenv arrives with work package 2.7).

State is kept in memory and mirrored to .local/stubs/studio-state.json. Seeded with Golden KYC V8 (synthetic).
"""

import hashlib
import hmac
import json
import os
import threading
import time
import uuid
from pathlib import Path

import golden_kyc as g
import httpx
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / ".local/stubs/studio-state.json"
LOCK = threading.RLock()
VERSIONS = g.environment_versions()
PUBLIC = {vid: {k: v for k, v in ver.items() if k != "_cases"} for vid, ver in VERSIONS.items()}

app = FastAPI(title="Studio stub (local only)", version="0.1.0")


def _blank():
    return {
        "seq": 0,
        "events": [],
        "state": {},
        "inbox": [],
        "inbox_seq": 41,
        "receipts": [],
        "usage": [],
        "rlgym_events": [],
        "faults": {},
        "bootstrapped": False,
    }


def _load():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return _blank()


S = _load()


def _save():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(S, indent=1))
    tmp.replace(STATE_FILE)


def _rlgym():
    return os.environ.get("RLGYM_API_URL", "http://127.0.0.1:8200").rstrip("/")


def _ws():
    return os.environ.get("RLGYM_WORKSPACE", "adi-labs-research")


def _client_headers(extra=None):
    return {
        "Authorization": f"Bearer {os.environ['RLGYM_STUDIO_CLIENT_KEY']}",
        "Idempotency-Key": str(uuid.uuid4()),
        **(extra or {}),
    }


def _check_rlgym_key(request: Request):
    expected = os.environ.get("RLGYM_ANVIL_KEY", "")
    if not expected or not hmac.compare_digest(
        request.headers.get("authorization", ""), f"Bearer {expected}"
    ):
        raise HTTPException(401, "RL Gym key required")


def _version_view(vid):
    v = dict(PUBLIC[vid])
    v["state"] = S["state"].get(vid, {}).get("state", "unregistered")
    v["state_seq"] = S["state"].get(vid, {}).get("seq", 0)
    return v


def _publish(event_type, vid=None, data=None):
    """Append one event to the registry log and push it to the RL Gym as a signed webhook."""
    with LOCK:
        S["seq"] += 1
        seq = S["seq"]
        if vid:
            S["state"].setdefault(vid, {})
            if event_type.startswith("version."):
                S["state"][vid] = {
                    "state": {
                        "version.registered": "registered",
                        "version.qualified": "qualified",
                        "version.revoked": "revoked",
                        "version.deprecated": "deprecated",
                    }.get(event_type, "registered"),
                    "seq": seq,
                }
        payload = {"seq": seq, **(data or {})}
        if vid:
            payload["version"] = _version_view(vid)
        event = {
            "specversion": "1.0",
            "id": f"reg-{seq:05d}",
            "type": event_type,
            "source": "studio-registry-stub",
            "subject": vid or payload.get("item", {}).get("id", ""),
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "data": payload,
        }
        S["events"].append(event)
        _save()
    _push(event)
    return event


def _push(event):
    raw = json.dumps(event).encode()
    ts = str(int(time.time()))
    sig = hmac.new(
        os.environ["RLGYM_REGISTRY_WEBHOOK_SECRET"].encode(),
        f"{ts}.".encode() + raw,
        hashlib.sha256,
    ).hexdigest()
    try:
        with httpx.Client(timeout=30, trust_env=False) as client:
            r = client.post(
                _rlgym() + "/api/v1/registry-events",
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-ADI-Timestamp": ts,
                    "X-ADI-Signature": sig,
                },
            )
        return r.status_code
    except httpx.HTTPError:
        return None  # the RL Gym resyncs from /events on its next event or at startup


def _ask_qualification(vid):
    with httpx.Client(timeout=60, trust_env=False) as client:
        r = client.post(
            _rlgym() + "/api/v1/qualifications",
            headers=_client_headers(),
            json={
                "subject": {
                    "kind": "environment_version",
                    "id": vid,
                    "sha256": PUBLIC[vid]["spec_sha256"],
                },
                "checks_requested": [
                    "health",
                    "known_fixtures",
                    "write_state",
                    "reset",
                    "state_cleared",
                    "pending_cleared",
                ],
            },
        )
    return r.json()


def _gym(method, path, body=None):
    with httpx.Client(timeout=120, trust_env=False) as client:
        r = client.request(
            method,
            f"{_rlgym()}/api/v1/workspaces/{_ws()}{path}",
            headers=_client_headers(),
            json=body,
        )
    try:
        data = r.json()
    except ValueError:
        data = {"raw": r.text}
    return r.status_code, data


# --- registry reads (RL Gym → registry) ------------------------------------------------------------------------


@app.get("/api/v1/registry/contracts/{cid}/versions")
def contract_versions(
    cid: str, request: Request, state: str | None = None, seed_family: str | None = None
):
    _check_rlgym_key(request)
    rows = [
        _version_view(vid)
        for vid in PUBLIC
        if PUBLIC[vid]["contract_id"] == cid and vid in S["state"]
    ]
    rows = [
        r
        for r in rows
        if (not state or r["state"] == state)
        and (not seed_family or r["seed_family"] == seed_family)
    ]
    return {"versions": sorted(rows, key=lambda r: r["version"], reverse=True)}


@app.get("/api/v1/registry/versions/{vid}")
def version(vid: str, request: Request):
    _check_rlgym_key(request)
    if vid not in S["state"]:
        raise HTTPException(404, "unknown version")
    return _version_view(vid)


@app.get("/api/v1/registry/versions/{vid}/case-catalog")
def case_catalog(vid: str, request: Request):
    _check_rlgym_key(request)
    if vid not in S["state"]:
        raise HTTPException(404, "unknown version")
    return PUBLIC[vid]["case_catalog"]


@app.get("/api/v1/registry/versions/{vid}/cases")
def cases(vid: str, request: Request):
    """Actor-visible case records only (no reference answers): used by data plans and runs."""
    _check_rlgym_key(request)
    if vid not in S["state"]:
        raise HTTPException(404, "unknown version")
    return {
        "cases": [
            {k: c[k] for k in ("case_id", "application_type", "completeness", "edge_cases")}
            for c in VERSIONS[vid]["_cases"]
        ]
    }


IMAGE_DIR = Path(__file__).resolve().parent / "env_image"


@app.get("/api/v1/registry/versions/{vid}/image-context")
def image_context(vid: str, request: Request):
    """The image recipe of a released version: Dockerfile, tool server and the case seed (actor records and
    environment facts, no reference answers). The RL Gym builds the image locally with Docker from this context."""
    _check_rlgym_key(request)
    if vid not in S["state"]:
        raise HTTPException(404, "unknown version")
    seed = g.image_seed(VERSIONS[vid]["_cases"])
    files = {
        "Dockerfile": (IMAGE_DIR / "Dockerfile").read_text(),
        "golden_kyc_env.py": (IMAGE_DIR / "golden_kyc_env.py").read_text(),
        "cases.jsonl": seed,
    }
    return {
        "version_id": vid,
        "recipe": PUBLIC[vid]["image_recipe"],
        "files": files,
        "files_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items()},
        "image_seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
        "cases": len(VERSIONS[vid]["_cases"]),
        "synthetic": True,
    }


@app.get("/api/v1/registry/versions/{vid}/references")
def references(vid: str, request: Request, ids: str = ""):
    """Private reference answers (schema table reference_answers), for the RL Gym scorer only. Never part of the image,
    the case list or anything a candidate sees."""
    _check_rlgym_key(request)
    if request.headers.get("x-adi-audience") != "scorer":
        raise HTTPException(403, "reference answers are for the scorer audience only")
    if vid not in S["state"]:
        raise HTTPException(404, "unknown version")
    wanted = set(filter(None, ids.split(",")))
    out = {
        c["case_id"]: {"reference": c["reference"], "reference_sha256": g.sha(c["reference"])}
        for c in VERSIONS[vid]["_cases"]
        if not wanted or c["case_id"] in wanted
    }
    return {"version_id": vid, "references": out}


@app.get("/api/v1/registry/events")
def events(request: Request, after_seq: int = 0):
    _check_rlgym_key(request)
    return {"events": [e for e in S["events"] if e["data"]["seq"] > after_seq]}


@app.post("/api/v1/registry/receipts")
def receipts(request: Request, body: dict = Body(...)):
    _check_rlgym_key(request)
    vid = body["subject"]["id"]
    with LOCK:
        S["receipts"].append({**body, "received_at": time.time()})
        _save()
        current = S["state"].get(vid, {}).get("state")
    if body["result"] == "qualified" and current == "registered":
        threading.Thread(target=_publish, args=("version.qualified", vid), daemon=True).start()
    return {"accepted": True}


@app.post("/api/v1/registry/usage")
def usage(request: Request, body: dict = Body(...)):
    _check_rlgym_key(request)
    with LOCK:
        S["usage"].append(body)
        _save()
    return {"accepted": True}


# --- next-version inbox (RL Gym → Studio) ------------------------------------------------------------------------


@app.post("/api/v1/inbox-items", status_code=202)
def inbox_create(request: Request, body: dict = Body(...)):
    _check_rlgym_key(request)
    key = request.headers.get("idempotency-key")
    with LOCK:
        existing = next((i for i in S["inbox"] if key and i.get("idempotency_key") == key), None)
        if existing:
            return {"id": existing["id"]}
        S["inbox_seq"] += 1
        item = {
            **body,
            "id": f"inb-{S['inbox_seq']:04d}",
            "state": "received",
            "idempotency_key": key,
            "received_at": time.time(),
        }
        S["inbox"].append(item)
        _save()

    def ack():
        time.sleep(0.5)
        _publish("inbox_item.status", data={"item": {"id": item["id"], "state": "received"}})

    threading.Thread(target=ack, daemon=True).start()
    return {"id": item["id"]}


@app.post("/api/v1/rlgym-events")
async def rlgym_events(request: Request):
    raw = await request.body()
    ts = request.headers.get("x-adi-timestamp", "")
    expected = hmac.new(
        os.environ["RLGYM_REGISTRY_WEBHOOK_SECRET"].encode(),
        f"{ts}.".encode() + raw,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("x-adi-signature", "")):
        raise HTTPException(401, "bad signature")
    with LOCK:
        S["rlgym_events"].append(json.loads(raw))
        _save()
    return {"accepted": True}


# --- environment simulator (qualification target) ------------------------------------------------------------------

ENV = {}


def _env(vid):
    if vid not in VERSIONS or vid not in S["state"]:
        raise HTTPException(404, "unknown version")
    return ENV.setdefault(vid, {"rows": [], "pending": 0})


@app.post("/stub/env/{vid}/episodes")
def env_episode(vid: str):
    env = _env(vid)
    env["rows"], env["pending"] = [], 0
    return {"ok": True}


@app.get("/stub/env/{vid}/health")
def env_health(vid: str):
    _env(vid)
    if S["faults"].get(vid) == "unhealthy":
        return JSONResponse({"status": "starting"}, status_code=503)
    return {"status": "ok"}


@app.get("/stub/env/{vid}/fixtures")
def env_fixtures(vid: str, ids: str = ""):
    _env(vid)
    have = {c["case_id"] for c in VERSIONS[vid]["_cases"]}
    return {"found": [i for i in ids.split(",") if i in have]}


@app.post("/stub/env/{vid}/tools/finding.write")
def env_write(vid: str, body: dict = Body(...)):
    env = _env(vid)
    env["rows"].append(
        {"table": "findings", "id": f"f-{len(env['rows']) + 1}", "case_id": body.get("case_id")}
    )
    return {"ok": True}


@app.post("/stub/env/{vid}/reset")
def env_reset(vid: str):
    env = _env(vid)
    if S["faults"].get(vid) != "reset_keeps_findings":
        env["rows"] = []
    env["pending"] = 0
    return {"ok": True}


@app.get("/stub/env/{vid}/state")
def env_state(vid: str):
    env = _env(vid)
    return {"writable_rows": len(env["rows"]), "rows": env["rows"]}


@app.get("/stub/env/{vid}/pending")
def env_pending(vid: str):
    return {"pending": _env(vid)["pending"]}


# --- stub controls (local demo and tests; each names the real trigger it stands for) -------------------------------


def _wait_state(vid, want, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if S["state"].get(vid, {}).get("state") == want:
            return True
        time.sleep(0.25)
    return False


@app.post("/stub/bootstrap")
def bootstrap():
    """Golden KYC V8 as Studio would have released it: golden-kyc-openenv v2 (rel-0412) and v3 (rel-0431) registered and
    qualified by the RL Gym, 20 S7 evaluator bindings sent through A-06 and tested, the template validated, its
    known-case tests run and the exact hash activated (A-03). Idempotent."""
    out = {"versions": {}, "evaluators": [], "activation": None}
    for vid in ("golden-kyc-openenv@v2", "golden-kyc-openenv@v3"):
        if vid not in S["state"]:
            _publish("version.registered", vid)
        if S["state"][vid]["state"] == "registered":
            out["versions"][vid] = _ask_qualification(vid).get("data", {}).get("result")
            _wait_state(vid, "qualified")
        out["versions"][vid] = S["state"][vid]["state"]
    for binding in g.evaluator_bindings():
        status, created = _gym("POST", "/evaluators", binding)
        if status >= 300:
            out["evaluators"].append({"id": binding["id"], "error": created})
            continue
        d = created["data"]
        if d["state"] != "qualified":
            _, tested = _gym("POST", f"/evaluators/{binding['id']}/test", {"version": d["version"]})
            d = {**d, "state": tested.get("data", {}).get("state")}
        out["evaluators"].append({"id": d["id"], "version": d["version"], "state": d["state"]})
    template = g.template()
    _, out["validate"] = _gym("POST", "/templates/validate", template)
    _, kct = _gym(
        "POST",
        "/templates/known-case-tests",
        {
            "template_id": g.TEMPLATE_ID,
            "version": g.TEMPLATE_VERSION,
            "criteria": [
                {"criterion_id": c["criterion_id"], "configuration_id": c["configuration_id"]}
                for c in template["criteria"]
            ],
        },
    )
    out["known_case_tests_passed"] = kct.get("data", {}).get("passed")
    status, act = _gym("POST", "/templates/activations", template)
    out["activation"] = act.get("data", act)
    with LOCK:
        S["bootstrapped"] = True
        _save()
    return out


def _release(vid):
    if vid not in S["state"]:
        _publish("version.registered", vid)
    result = None
    if S["state"][vid]["state"] == "registered":
        result = _ask_qualification(vid).get("data", {})
        if result.get("result") == "qualified":
            _wait_state(vid, "qualified")
    return {
        "version": vid,
        "state": S["state"][vid]["state"],
        "qualification": result and result.get("result"),
        "failure_class": result and result.get("failure_class"),
    }


@app.post("/stub/scenarios/release-v4")
def release_v4():
    """Stands for: Studio releases golden-kyc-openenv v4, another seed family (kyc_cases-20261203). This release lacks
    the template's known fixtures, so the RL Gym's qualification fails it (environment defect)."""
    return _release("golden-kyc-openenv@v4")


@app.post("/stub/scenarios/release-v5")
def release_v5():
    """Stands for: Studio's fixed release of the second seed family (kyc_cases-20261203) after v4 failed."""
    return _release("golden-kyc-openenv@v5")


@app.post("/stub/scenarios/fault/{vid}")
def set_fault(vid: str, body: dict = Body(default={})):
    """Stands for: a released version that starts failing (here: its reset leaves rows in `findings`)."""
    with LOCK:
        if body.get("fault"):
            S["faults"][vid] = body["fault"]
        else:
            S["faults"].pop(vid, None)
        _save()
    return {"version": vid, "fault": S["faults"].get(vid)}


@app.post("/stub/scenarios/requalify/{vid}")
def requalify(vid: str):
    """Stands for: the registry asks the RL Gym to re-qualify a released version (same digest, same seed)."""
    return _ask_qualification(vid)


@app.post("/stub/scenarios/revoke/{vid}")
def revoke(vid: str, body: dict = Body(default={})):
    """Stands for: a Studio registry owner revokes a version."""
    return _publish(
        "version.revoked", vid, {"reason": body.get("reason", "revoked by registry owner")}
    )


@app.post("/stub/inbox-items/{item_id}/status")
def inbox_status(item_id: str, body: dict = Body(...)):
    """Stands for: Studio's designer plans, releases or declines an inbox item."""
    with LOCK:
        item = next((i for i in S["inbox"] if i["id"] == item_id), None)
        if not item:
            raise HTTPException(404, "unknown item")
        item.update(
            {
                k: body.get(k)
                for k in ("state", "planned_version", "released_version", "decline_reason")
                if body.get(k)
            }
        )
        _save()
    _publish(
        "inbox_item.status",
        data={
            "item": {
                "id": item_id,
                **{
                    k: item.get(k)
                    for k in ("state", "planned_version", "released_version", "decline_reason")
                },
            }
        },
    )
    return item


@app.get("/stub/state")
def state():
    return {
        "seq": S["seq"],
        "versions": {vid: S["state"].get(vid) for vid in PUBLIC},
        "inbox": S["inbox"],
        "receipts": len(S["receipts"]),
        "rlgym_events": S["rlgym_events"][-30:],
        "faults": S["faults"],
        "bootstrapped": S["bootstrapped"],
        "synthetic": True,
    }


@app.get("/")
def root():
    return {
        "service": "Studio stub (local only, synthetic Golden KYC V8)",
        "registry": "/api/v1/registry",
        "state": "/stub/state",
    }
