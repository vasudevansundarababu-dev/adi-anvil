"""Explicit local system test; stops/restarts only the disposable Neo4j service."""

import json
import secrets
import subprocess
import time

from fastapi.testclient import TestClient
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from anvil.api import app
from anvil.auth import hashed
from anvil.cli import PROJECT
from anvil.config import ROOT
from anvil.db import digest, transaction
from anvil.graph import project_graph

compose = [
    "docker",
    "compose",
    "--env-file",
    str(ROOT / ".env"),
    "-f",
    str(ROOT / "infra/local/compose.yaml"),
]
user = json.loads((ROOT / ".local/demo-identities.json").read_text())["researcher"]
token = secrets.token_urlsafe(48)
with transaction() as c:
    c.execute(
        "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
        (hashed(token), user, hashed("test-only")),
    )


def scores():
    with transaction(PROJECT, user) as c:
        return digest(
            c.execute(
                "SELECT id::text,state,outcome,score::text FROM anvil.episodes ORDER BY id"
            ).fetchall()
        )


try:
    before = scores()
    client = TestClient(app)
    client.cookies.set("anvil_session", token)
    original = client.get(f"/api/v1/projects/{PROJECT}/diagnostics").json()["data"]
    subprocess.run(compose + ["stop", "neo4j"], check=True, cwd=ROOT)
    degraded = client.get(f"/api/v1/projects/{PROJECT}/diagnostics").json()["data"]
    assert degraded["projection_status"] == "unavailable"
    assert original["nodes"] == degraded["nodes"] and original["edges"] == degraded["edges"]
    assert scores() == before
    print("Actual Neo4j outage: canonical fallback and unchanged episode scores passed.")
finally:
    subprocess.run(compose + ["start", "neo4j"], check=True, cwd=ROOT)
    with transaction() as c:
        c.execute(
            "UPDATE anvil.sessions SET revoked_at=now() WHERE token_hash=%s", (hashed(token),)
        )

for attempt in range(30):
    try:
        restored = project_graph(PROJECT)
        assert restored["nodes"] == original["nodes"]
        assert restored["edges"] == original["edges"]
        assert scores() == before
        print("Neo4j restart/rebuild: canonical nodes, relationships and episode scores preserved.")
        break
    except (OSError, RuntimeError, Neo4jError, ServiceUnavailable):
        if attempt == 29:
            raise
        time.sleep(1)
