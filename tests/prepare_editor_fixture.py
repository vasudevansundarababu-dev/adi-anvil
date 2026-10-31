"""New isolated synthetic draft for browser editing; never changes original run bindings."""

import json

from anvil import domain
from anvil.config import ROOT
from anvil.db import transaction

journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
users = json.loads((ROOT / ".local/demo-identities.json").read_text())
with transaction(journey["project_id"], users["researcher"]) as connection:
    protocol = domain.get_revision(
        connection, journey["protocol"]["current_revision_id"], "protocol"
    )
    suite = domain.get_revision(connection, protocol["content"]["suite_revision_id"], "suite")
    task = domain.get_revision(connection, suite["content"]["task_revision_ids"][0], "task")
    rubric = domain.get_revision(connection, task["content"]["rubric_revision_id"], "rubric")
    clone = domain.create(
        connection,
        journey["project_id"],
        users["researcher"],
        "rubric",
        {**rubric["content"], "title": "Test-only browser successor rubric"},
    )
    print(
        json.dumps(
            {
                "project_id": journey["project_id"],
                "revision_id": str(clone["current_revision_id"]),
                "return_run": journey["run_id"],
            }
        )
    )
