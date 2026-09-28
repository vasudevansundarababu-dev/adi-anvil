import json

import pytest

from anvil import worker
from anvil.config import ROOT
from anvil.db import one, transaction, uid
from anvil.evaluation import GRAPH_VERSION


def prepared_job(graph_version):
    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    project = journey["project_id"]
    user = json.loads((ROOT / ".local/demo-identities.json").read_text())["researcher"]
    rid, eid, jid, token = uid(), uid(), uid(), uid()
    with transaction(project, user) as c:
        task = one(
            c,
            "SELECT task_revision_id FROM anvil.episodes WHERE id=%s",
            (journey["episodes"][0]["id"],),
        )
        c.execute(
            "INSERT INTO anvil.runs(id,project_id,protocol_revision_id,origin,created_by,state) VALUES(%s,%s,%s,'illustrative',%s,'queued')",
            (rid, project, journey["protocol"]["current_revision_id"], user),
        )
        c.execute(
            "INSERT INTO anvil.episodes(id,project_id,run_id,task_revision_id,candidate_key,thread_id,graph_version) VALUES(%s,%s,%s,%s,'fixture-correct',%s,%s)",
            (eid, project, rid, task["task_revision_id"], uid(), graph_version),
        )
        c.execute(
            "INSERT INTO anvil.jobs(id,project_id,kind,target_id,operation_key,status,lease_token,lease_until) VALUES(%s,%s,'episode',%s,%s,'leased',%s,now()+interval '60 seconds')",
            (jid, project, eid, "isolated-worker-test:" + jid, token),
        )
        return one(c, "SELECT * FROM anvil.jobs WHERE id=%s", (jid,))


def test_stale_worker_token_cannot_mutate_or_invoke():
    job = prepared_job(GRAPH_VERSION)
    with transaction(job["project_id"], worker=True) as c:
        with pytest.raises(RuntimeError, match="lease_lost"):
            worker.guard(c, {**job, "lease_token": uid()})
        e = one(
            c, "SELECT state,invocation_count FROM anvil.episodes WHERE id=%s", (job["target_id"],)
        )
        assert e["state"] == "queued" and e["invocation_count"] == 0
        c.execute("UPDATE anvil.jobs SET status='cancelled' WHERE id=%s", (job["id"],))
        c.execute("UPDATE anvil.episodes SET state='cancelled' WHERE id=%s", (job["target_id"],))


def test_graph_version_mismatch_is_operational_invalidity_not_candidate_failure(monkeypatch):
    job = prepared_job("unsupported-test-graph-version")
    original = worker.one

    def claim(c, query, params=()):
        return job if query == "SELECT * FROM anvil.claim_job()" else original(c, query, params)

    monkeypatch.setattr(worker, "one", claim)
    assert worker.tick()
    with transaction(job["project_id"], worker=True) as c:
        e = one(c, "SELECT * FROM anvil.episodes WHERE id=%s", (job["target_id"],))
        assert e["state"] == "failed_operational" and e["outcome"] == "invalid"
        assert e["score"] is None and e["invocation_count"] == 0
        assert (
            one(c, "SELECT state FROM anvil.runs WHERE id=%s", (e["run_id"],))["state"]
            == "execution_complete"
        )
        assert (
            one(c, "SELECT error_code FROM anvil.jobs WHERE id=%s", (job["id"],))["error_code"]
            == "graph_version_mismatch"
        )
