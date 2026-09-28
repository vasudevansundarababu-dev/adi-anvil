"""Resume a copied pending review using only the restored DB and copied artifact store."""

import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from anvil import worker
from anvil.api import app
from anvil.auth import hashed
from anvil.config import ROOT, setting
from anvil.db import one, transaction, uid

folder = Path((ROOT / ".local/latest-backup").read_text())
assert folder.resolve().is_relative_to((ROOT / ".local/backups").resolve())
target = json.loads((folder / "restore-verification.json").read_text())["target_database"]
assert target.startswith("anvil_restore_") and target != "anvil_local"
original_owner = setting("MIGRATION_DATABASE_URL")
owner_url = urlsplit(original_owner)._replace(path="/" + target).geturl()
with psycopg.connect(owner_url, row_factory=dict_row) as c:
    episode = c.execute(
        "SELECT e.*,v.content protocol FROM anvil.episodes e JOIN anvil.runs r ON r.id=e.run_id JOIN anvil.revisions v ON v.id=r.protocol_revision_id WHERE e.state='awaiting_review' AND e.output_artifact_id IS NOT NULL AND NOT r.cancel_requested ORDER BY e.created_at LIMIT 1"
    ).fetchone()
assert episode is not None, (
    "No pending restored review available; create a review checkpoint before backup"
)
eid, project = episode["id"], episode["project_id"]


def original_state():
    with psycopg.connect(original_owner) as c:
        return c.execute(
            "SELECT state,invocation_count,final_assessment_id FROM anvil.episodes WHERE id=%s",
            (eid,),
        ).fetchone()


before = original_state()
saved = {
    key: os.environ.get(key) for key in ("DATABASE_URL", "WORKER_DATABASE_URL", "ARTIFACT_ROOT")
}
tokens = []
try:
    for key in ("DATABASE_URL", "WORKER_DATABASE_URL"):
        os.environ[key] = urlsplit(setting(key))._replace(path="/" + target).geturl()
    os.environ["ARTIFACT_ROOT"] = str(folder / "artifacts")

    def client_for(user):
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with transaction() as c:
            c.execute(
                "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
                (hashed(token), user, hashed(csrf)),
            )
        tokens.append(hashed(token))
        client = TestClient(app)
        client.cookies.set("anvil_session", token)
        client.headers.update({"Origin": "http://127.0.0.1:3202", "X-CSRF-Token": csrf})
        return client

    def assess(user, action):
        client = client_for(user)
        path = f"/api/v1/projects/{project}"
        response = client.get(path + f"/reviews/{eid}")
        assert response.status_code == 200
        detail = response.json()["data"]
        quote = detail["output"][:80]
        scores = {x["id"]: 4 for x in detail["rubric"]["criteria"]}
        response = client.post(
            path + f"/episodes/{eid}/{action}",
            headers={"If-Match": str(detail["row_version"]), "Idempotency-Key": uid()},
            json={
                "scores": scores,
                "critical": [],
                "evidence": {k: quote for k in scores},
                "rationale": "Synthetic restore-resume rehearsal only; no scientific or model-performance claim.",
            },
        )
        assert response.status_code == 200, response.text

    for reviewer in episode["protocol"]["reviewer_ids"]:
        with transaction(project, reviewer) as c:
            prior = one(
                c,
                "SELECT 1 FROM anvil.assessments WHERE episode_id=%s AND reviewer_id=%s",
                (eid, reviewer),
            )
        if not prior:
            assess(reviewer, "assessments")
    with transaction(project, worker=True) as c:
        current = one(c, "SELECT state FROM anvil.episodes WHERE id=%s", (eid,))
    if current["state"] == "disputed":
        assess(episode["protocol"]["adjudicator_id"], "adjudicate")
    with transaction(project, worker=True) as c:
        job = c.execute(
            "UPDATE anvil.jobs SET status='leased',lease_token=%s,lease_until=now()+interval '60 seconds' WHERE id=(SELECT id FROM anvil.jobs WHERE kind='resume' AND target_id=%s AND status='queued' LIMIT 1) RETURNING *",
            (uid(), eid),
        ).fetchone()
    assert job, "Expected a single authorized restored resume job"
    original_one = worker.one
    worker.one = lambda c, query, params=(): (
        job if query == "SELECT * FROM anvil.claim_job()" else original_one(c, query, params)
    )
    try:
        worker.tick()
    finally:
        worker.one = original_one
    with transaction(project, worker=True) as c:
        resumed = one(c, "SELECT state,invocation_count FROM anvil.episodes WHERE id=%s", (eid,))
    assert resumed["state"] == "finalized"
    assert resumed["invocation_count"] == episode["invocation_count"]
    assert original_state() == before
    result = {
        "status": "passed",
        "target_database": target,
        "episode_id": str(eid),
        "restored_artifact_root_used": True,
        "invocation_count_unchanged": True,
        "original_episode_unchanged": True,
        "resume_state": resumed["state"],
    }
    (folder / "restore-resume-verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
finally:
    with transaction() as c:
        for token_hash in tokens:
            c.execute(
                "UPDATE anvil.sessions SET revoked_at=now() WHERE token_hash=%s", (token_hash,)
            )
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
