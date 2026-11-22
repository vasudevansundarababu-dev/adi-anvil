"""LOCAL STUB of ADI Forge (work package 2.1). Not the real ADI Forge.

Serves ARCHITECTURE 9.3 (run-review batches, template qualification records, proposal reads) and the exported task
packages, and calls into the RL Gym: project export and re-export (9.2) and SME decisions. Seeded with the KYC
November project (prj_7f3a91c2) on Golden KYC V8: 40 synthetic authored tasks. SMEs decide only here, never in the
RL Gym; this stub records decisions sent to it by a test or a person operating the stub.
"""

import hmac
import json
import os
import threading
import time
from pathlib import Path

import golden_kyc as g
import httpx
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import Response

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / ".local/stubs/forge-state.json"
LOCK = threading.RLock()
app = FastAPI(title="ADI Forge stub (local only)", version="0.1.0")


def _load():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "packages": {},
        "exports": [],
        "qualifications": [],
        "run_reviews": [],
        "decisions": [],
        "batch_seq": 220,
    }


S = _load()


def _save():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(S))
    tmp.replace(STATE_FILE)


def _rlgym():
    return os.environ.get("RLGYM_API_URL", "http://127.0.0.1:8200").rstrip("/")


def _ws():
    return os.environ.get("RLGYM_WORKSPACE", "adi-labs-research")


def _check_rlgym_key(request: Request):
    expected = os.environ.get("RLGYM_ANVIL_KEY", "")
    if not expected or not hmac.compare_digest(
        request.headers.get("authorization", ""), f"Bearer {expected}"
    ):
        raise HTTPException(401, "ANVIL key required")


@app.get("/api/v1/packages/{sha}")
def package(sha: str, request: Request):
    _check_rlgym_key(request)
    pkg = S["packages"].get(sha)
    if pkg is None:
        raise HTTPException(404, "unknown package")
    return Response(g.canonical(pkg).encode(), media_type="application/json")


@app.post("/api/v1/projects/{pid}/run-reviews", status_code=202)
def run_reviews(pid: str, request: Request, body: dict = Body(...)):
    _check_rlgym_key(request)
    with LOCK:
        existing = next(
            (b for b in S["run_reviews"] if b["batch_id"] == body.get("batch_id")), None
        )
        if existing:
            return {"forge_batch_ref": existing["forge_batch_ref"]}
        S["batch_seq"] += 1
        record = {
            **body,
            "project_id": pid,
            "forge_batch_ref": f"rr-{S['batch_seq']}",
            "received_at": time.time(),
        }
        S["run_reviews"].append(record)
        _save()
    return {"forge_batch_ref": record["forge_batch_ref"]}


@app.post("/api/v1/integrations/anvil/templates/qualifications")
def qualifications(request: Request, body: dict = Body(...)):
    _check_rlgym_key(request)
    with LOCK:
        if not any(q.get("event_sha256") == body.get("event_sha256") for q in S["qualifications"]):
            S["qualifications"].append({**body, "received_at": time.time()})
            _save()
    return {"accepted": True}


@app.get("/api/v1/integrations/anvil/templates/proposals/{pid}")
def proposal(pid: str, request: Request):
    _check_rlgym_key(request)
    t = g.template()
    return {
        "id": pid,
        "template_id": t["template_id"],
        "version": t["version"],
        "template_version_hash": t["spec_sha256"],
    }


# --- stub controls -----------------------------------------------------------------------------------------------


def _send(body, packages):
    with LOCK:
        S["packages"].update(packages)
        _save()
    with httpx.Client(timeout=120, trust_env=False) as client:
        r = client.post(
            f"{_rlgym()}/api/v1/workspaces/{_ws()}/projects/{body['project_id']}/exports",
            json=body,
            headers={
                "Authorization": f"Bearer {os.environ['RLGYM_FORGE_CLIENT_KEY']}",
                "Idempotency-Key": body["export_sha256"],
            },
        )
    result = {"status": r.status_code, "response": r.json() if r.content else None}
    with LOCK:
        S["exports"].append(
            {
                "export_id": body["export_id"],
                "sha256": body["export_sha256"],
                "status": r.status_code,
                "at": time.time(),
            }
        )
        _save()
    return result


@app.post("/stub/projects/{pid}/export")
def export(pid: str, body: dict = Body(default={})):
    """Stands for: an ADI Forge PM exports (or re-exports) the KYC November project to the RL Gym."""
    if pid != g.FORGE_PROJECT_ID:
        raise HTTPException(404, "the stub knows only the KYC November project")
    export_id = body.get("export_id", "exp-0001")
    reason = body.get("reason", "first export of KYC November")
    payload, packages = g.project_export(export_id, reason, body.get("corrections"))
    return _send(payload, packages)


@app.post("/stub/projects/{pid}/sme-decisions/{batch_id}")
def send_decisions(pid: str, batch_id: str, body: dict = Body(...)):
    """Stands for: SMEs decide a review batch in ADI Forge; ADI Forge posts the decisions back (9.2)."""
    with httpx.Client(timeout=60, trust_env=False) as client:
        r = client.post(
            f"{_rlgym()}/api/v1/workspaces/{_ws()}/sme-review-batches/{batch_id}/decisions",
            json={"schema": "rlgym.sme-decisions.v1", "batch_id": batch_id, **body},
            headers={
                "Authorization": f"Bearer {os.environ['RLGYM_FORGE_CLIENT_KEY']}",
                "Idempotency-Key": f"{batch_id}-decisions",
            },
        )
    with LOCK:
        S["decisions"].append({"batch_id": batch_id, "status": r.status_code, "at": time.time()})
        _save()
    return {"status": r.status_code, "response": r.json() if r.content else None}


@app.get("/stub/state")
def state():
    return {
        "packages": len(S["packages"]),
        "exports": S["exports"],
        "qualifications": S["qualifications"],
        "run_reviews": [
            {k: v for k, v in b.items() if k != "items"} | {"items": len(b.get("items", []))}
            for b in S["run_reviews"]
        ],
        "decisions": S["decisions"],
        "synthetic": True,
    }


@app.get("/")
def root():
    return {
        "service": "ADI Forge stub (local only, synthetic KYC November)",
        "state": "/stub/state",
    }
